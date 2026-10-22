(function () {
  'use strict';
  const Core = window.ParticleCore;
  const Zip = window.ParticleZip;
  const Storage = window.ParticleStorage;
  const Preview = window.ParticlePreview;
  const Scrub = window.ParticleScrub;
  const SpineMerge = window.ParticleSpineMerge;
  const EffectUpdate = window.ParticleEffectUpdate;
  const FlowPlayback = window.ParticleFlowPlayback;
  const AttachmentPreview = window.ParticleAttachmentPreview;
  const PathMath = window.ParticlePathMath;
  const ContourMath = window.ParticleContourMath;
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const controls = Array.from(document.querySelectorAll('[data-field]'));
  const canvas = $('previewCanvas');
  const ctx = canvas.getContext('2d', {alpha: false});
  const handleLayer = $('emitterHandles');
  const handles = new Map();
  const imageCache = new Map();
  const tintCache = new Map();
  const imageIds = new WeakMap();
  let nextImageId = 1;
  let curveEditor = null, gradientEditor = null, lookPresetsUi = null, libraryUi = null, timelineView = null, pathEditor = null, attachmentUi = null, assetsUi = null, textureUi = null;
  let bonePicker = null;
  let previewAttached = true, showBones = true, previewSkin = '', attachedError = '';
  const attachedCache = new Map();
  const pathGizmoCache = new Map();
  const outlineGizmoCache = new WeakMap();
  let outlineRequest = 0;
  let backgroundRequest = 0;
  let textureRequest = 0, projectRequest = 0;
  const inspectorScrollPositions = new Map();
  let integration = null;
  let updateBaseCache = null;
  const builtinImages = {};
  let project = createInitialProject();
  let selectedId = project.emitters[0].id;
  let liveBake = null, baked = null, exported = null, bakedPreview = null, liveError = '';
  let liveFlowBake = null, flowBaked = null, phase = 'loop', sequence = false, exitRequested = false;
  let revision = 0, bakedRevision = -1;
  let mode = 'live', playing = true, time = 0;
  let zoom = 1, panX = 0, panY = 40, stageW = 1, stageH = 1;
  let liveTimer = null, draftTimer = null, messageTimer = null;
  let interaction = null, busy = false, initialized = false;
  let resettingProject = false, initialInterface = null;
  let draftWrite = Promise.resolve();
  let history = null, historyRestoring = false, historyGroup = null;
  let priorAssets = null, priorSource = null, emitterLanes = null, batchUi = null;
  // Preview-only visibility; never changes the project, bake or export.
  const previewHidden = new Set(); let soloId = null;
  const MAX_ZOOM = 8;

  function createInitialProject(name = '金色光塵') {
    const fresh = Core.createProject(); fresh.name = name;
    Object.assign(fresh.emitters[0], {shape: 'box', width: 180, height: 30, count: 48,
      emissionDuration: 3, spread: 70, size: 18, speed: 90});
    return fresh;
  }

  function historyState() { return {project, integration, selectedId}; }
  function effectiveIntegration(session = integration) {
    if (!session || !session.update || session.update.mode !== 'replace') return session;
    if (!updateBaseCache || updateBaseCache.source !== session.json || updateBaseCache.receipt !== session.update.receipt) {
      const cleaned = EffectUpdate.remove(session.json, session.update.receipt);
      updateBaseCache = {source: session.json, receipt: session.update.receipt, json: cleaned.json};
    }
    return {...session, json: updateBaseCache.json, settings: {...session.settings, prefix: session.update.receipt.manifest.namespace}};
  }
  function updateHistoryStatus() {
    if (!history) return;
    const state = history.info(), blocked = busy || !!historyGroup && historyGroup.kind === 'pointer' || !!($('pathDialog') && $('pathDialog').open);
    const undo = $('historyUndo'), redo = $('historyRedo');
    if (undo) { undo.disabled = blocked || !(state.canUndo || historyGroup && historyGroup.pending); undo.title = '復原上一步（Ctrl＋Z）' + (state.canUndo ? ' · ' + state.undoCount + ' 步可復原' : ''); }
    if (redo) { redo.disabled = blocked || !state.canRedo; redo.title = '重做（Ctrl＋Y／Ctrl＋Shift＋Z）'; }
  }
  function recordHistory() {
    if (history && !historyRestoring) {
      history.observe(historyState());
      if (historyGroup) { historyGroup.pending = true; updateHistoryStatus(); }
    }
  }
  function historyBegin(kind = 'command', target = null, pointerId = null) {
    if (!history || historyRestoring) return;
    historyEnd(); history.begin(historyState()); historyGroup = {kind, target, pointerId, pending: false}; updateHistoryStatus();
  }
  function historyEnd() {
    if (!history || !historyGroup) return;
    historyGroup = null; history.end(historyState()); updateHistoryStatus();
  }
  function integrationChanged() {
    if (priorAssets !== (integration && integration.assets) || priorSource !== (integration && integration.json)) { imageCache.clear(); tintCache.clear(); }
    priorAssets = integration && integration.assets; priorSource = integration && integration.json;
    attachedCache.clear(); queueDraft(); updateBakeStatus();
  }
  function restoreHistory(state) {
    if (!state) return;
    if (bonePicker) bonePicker.cancel();
    // Validation precedes assignment. Generated keys are discarded so an older
    // bake can never be exported as if it matched the restored edit state.
    const nextProject = Core.normalizeProject(state.project);
    const nextIntegration = state.integration ? SpineMerge.normalizeSession(state.integration) : null;
    historyRestoring = true;
    try {
      clearTimeout(liveTimer); liveTimer = null;
      outlineRequest++; backgroundRequest++; textureRequest++; projectRequest++;
      project = nextProject; integration = nextIntegration;
      selectedId = project.emitters.some(e => e.id === state.selectedId) ? state.selectedId : project.emitters[0].id;
      revision++; bakedRevision = -1; mode = 'live'; stopSequence();
      baked = null; flowBaked = null; exported = null; bakedPreview = null;
      liveBake = null; liveFlowBake = null; attachedCache.clear(); imageCache.clear(); tintCache.clear(); pathGizmoCache.clear();
      priorAssets = integration && integration.assets; priorSource = integration && integration.json;
      refreshLive(); renderGlobals(); renderEmitters(); renderInspector();
      if (attachmentUi) attachmentUi.refresh(); if (assetsUi) assetsUi.refresh();
      updateBakeStatus(); updatePlayButton(); syncTimeline(); queueDraft();
    } finally { historyRestoring = false; updateHistoryStatus(); }
  }
  function applyHistory(direction) {
    if (!history || busy || $('pathDialog').open || historyGroup && historyGroup.kind === 'pointer') return;
    historyEnd();
    try { restoreHistory(direction === 'undo' ? history.undo() : history.redo()); }
    catch (error) { notify('無法復原這筆操作：' + error.message, true); }
  }
  function wireHistory() {
    if (!window.ParticleHistory) return;
    history = window.ParticleHistory.create({maxSteps: 100, maxBytes: 96 * 1024 * 1024,
      immutable: (value, path) => path === 'integration.json' || path === 'integration.assets' || !!value.dataUrl,
      same: (a, b) => !!a && !!b && a.project === b.project && a.integration === b.integration,
      onChange: updateHistoryStatus});
    history.reset(historyState());
    const pathDraft = target => !!target.closest('#pathDialog');
    const textField = target => !!target.closest('input[type="text"],input[type="number"],textarea,[contenteditable="true"]');
    // Browsers may drain microtasks between native event listeners. A timer
    // waits for both capture and target cancel/restore handlers to finish.
    const deferEnd = token => setTimeout(() => { if (historyGroup === token) historyEnd(); }, 0);
    document.addEventListener('pointerdown', event => {
      historyEnd();
      recordHistory();
      if (pathDraft(event.target) || busy) return;
      if (event.target.closest('.emitter-handle,canvas.curve-canvas,.gradient-key-track,input[type="number"],input[type="range"],input[type="color"]')) {
        historyBegin('pointer', event.target, event.pointerId);
      }
    }, true);
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) document.addEventListener(type, event => {
      if (historyGroup && historyGroup.kind === 'pointer' && historyGroup.pointerId === event.pointerId) deferEnd(historyGroup);
    }, true);
    document.addEventListener('focusin', event => {
      if (!historyGroup && !pathDraft(event.target) && textField(event.target)) historyBegin('field', event.target);
    }, true);
    document.addEventListener('input', event => {
      if (!historyGroup && !pathDraft(event.target) && event.target.closest('input:not([type="file"]),textarea')) historyBegin('field', event.target);
    }, true);
    for (const type of ['focusout', 'change']) document.addEventListener(type, event => {
      if (historyGroup && historyGroup.kind === 'field' && historyGroup.target === event.target) deferEnd(historyGroup);
    }, true);
    // Cancel handlers on the target run before the deferred capture commits.
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && historyGroup && historyGroup.kind === 'pointer') {
        if (interaction && interaction.type === 'emitter') {
          event.preventDefault(); interaction.e.x = interaction.originalX; interaction.e.y = interaction.originalY;
          changed(); renderInspector(); finishInteraction();
        }
        deferEnd(historyGroup);
      }
    }, true);
    document.addEventListener('keydown', event => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || pathDraft(event.target) || textField(event.target) || busy) return;
      const key = event.key.toLowerCase();
      if (key === 'z' || key === 'y') { event.preventDefault(); applyHistory(key === 'y' || event.shiftKey ? 'redo' : 'undo'); }
    });
    window.addEventListener('blur', () => { if (historyGroup) deferEnd(historyGroup); });
    const undo = $('historyUndo'), redo = $('historyRedo');
    if (undo) undo.addEventListener('click', () => applyHistory('undo'));
    if (redo) redo.addEventListener('click', () => applyHistory('redo'));
    $('pathDialog').addEventListener('close', updateHistoryStatus);
    updateHistoryStatus();
  }

  function makeTexture(kind) {
    const surface = document.createElement('canvas');
    surface.width = surface.height = 64;
    const c = surface.getContext('2d');
    if (kind === 'glow') {
      const pixels = c.createImageData(64, 64);
      for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
        const r = Math.hypot((x - 31.5) / 31.5, (y - 31.5) / 31.5);
        const offset = (y * 64 + x) * 4;
        pixels.data[offset] = pixels.data[offset + 1] = pixels.data[offset + 2] = 255;
        pixels.data[offset + 3] = r >= 1 ? 0 : Math.round(255 * Math.pow(1 - r, 2.2));
      }
      c.putImageData(pixels, 0, 0);
    } else if (kind === 'sparks') {
      const gradient = c.createRadialGradient(32, 32, 0, 32, 32, 30);
      gradient.addColorStop(0, '#ffffff'); gradient.addColorStop(1, '#ffffff00');
      c.fillStyle = gradient; c.fillRect(0, 0, 64, 64);
      c.fillStyle = '#ffffff'; c.beginPath(); c.moveTo(32, 3); c.lineTo(37, 27); c.lineTo(58, 32); c.lineTo(37, 37); c.lineTo(32, 61); c.lineTo(27, 37); c.lineTo(6, 32); c.lineTo(27, 27); c.closePath(); c.fill();
    } else if (kind === 'coins') {
      const gradient = c.createLinearGradient(12, 12, 53, 53);
      gradient.addColorStop(0, '#ffffff'); gradient.addColorStop(0.5, '#b0b0b0'); gradient.addColorStop(1, '#f7f7f7');
      c.fillStyle = gradient; c.beginPath(); c.arc(32, 32, 27, 0, Math.PI * 2); c.fill();
      c.lineWidth = 3; c.strokeStyle = '#f7f7f7'; c.beginPath(); c.arc(32, 32, 22, 0, Math.PI * 2); c.stroke();
      c.fillStyle = '#ffffff'; c.font = 'bold 30px sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('$', 32, 33);
    } else {
      const gradient = c.createRadialGradient(24, 20, 2, 32, 32, 27);
      gradient.addColorStop(0, '#ffffff75'); gradient.addColorStop(0.55, '#ffffff0a'); gradient.addColorStop(0.88, '#ffffff25'); gradient.addColorStop(1, '#ffffffd0');
      c.fillStyle = gradient; c.beginPath(); c.arc(32, 32, 27, 0, Math.PI * 2); c.fill();
      c.lineWidth = 2; c.strokeStyle = '#ffffffaa'; c.beginPath(); c.arc(32, 32, 26, 0, Math.PI * 2); c.stroke();
      c.fillStyle = '#ffffffc0'; c.beginPath(); c.ellipse(23, 19, 5, 3, -0.65, 0, Math.PI * 2); c.fill();
    }
    return {name: kind + '.png', mime: 'image/png', width: 64, height: 64, dataUrl: surface.toDataURL('image/png')};
  }
  ['glow', 'sparks', 'coins', 'bubbles'].forEach(kind => { builtinImages[kind] = makeTexture(kind); });

  function notify(message, error) {
    if ($('flowDialog').open) {
      const feedback = $('flowFeedback'); feedback.textContent = message;
      feedback.classList.toggle('error', !!error); feedback.hidden = false;
    }
    if ($('spineMergeDialog').open) {
      const feedback = $('spineMergeFeedback'); feedback.textContent = message;
      feedback.classList.toggle('error', !!error); feedback.hidden = false;
    }
    $('message').textContent = message;
    $('message').classList.toggle('error', !!error);
    $('message').hidden = false;
    clearTimeout(messageTimer);
    messageTimer = setTimeout(() => { $('message').hidden = true; }, error ? 12000 : 6500);
  }
  function emitter() { return project.emitters.find(item => item.id === selectedId) || project.emitters[0]; }
  function emitFrom(e) { return e.emitFrom || (e.shape === 'ring' ? 'edge' : 'area'); }
  function directionMode(e) { return e.directionMode || 'fixed'; }
  function currentFlowBake() { return mode === 'baked' && baked ? flowBaked : liveFlowBake; }
  function activeBake() {
    const group = currentFlowBake();
    return group ? group.phases[phase] : mode === 'baked' && baked ? baked : liveBake;
  }
  function attachedMode() { return previewAttached && integration && integration.settings.enabled !== false; }
  function attachedFor(kind) {
    if (!attachedMode()) return null;
    const group = currentFlowBake(), snapshot = group ? group.phases[kind || phase] : activeBake();
    if (!snapshot) return null;
    const key = group ? kind || phase : 'single';
    const cached = attachedCache.get(key);
    if (cached && cached.session === integration && cached.snapshot === snapshot && cached.exported === exported && cached.mode === mode && cached.skin === previewSkin) return cached.value;
    const record = {session: integration, snapshot, exported, mode, skin: previewSkin, value: null, error: ''};
    try { record.value = AttachmentPreview.compile({session: effectiveIntegration(), localBake: snapshot, phase: group ? key : null,
      baked: mode === 'baked', exported, fallbackImage: builtinImages.glow, skinName: previewSkin, getProject: () => project}); }
    catch (error) { record.error = error.message; }
    attachedCache.set(key, record); return record.value;
  }
  function previewDuration() { const attached = attachedFor(); const snapshot = activeBake(); return attached ? attached.timeline.duration : snapshot ? snapshot.duration : project.duration; }
  function refreshAttachmentPreview() {
    const enabled = !!integration && integration.settings.enabled !== false;
    $('attachmentPreviewBar').hidden = !enabled;
    $('previewAttached').classList.toggle('active', previewAttached); $('previewAttached').setAttribute('aria-pressed', String(previewAttached));
    $('previewLocal').classList.toggle('active', !previewAttached); $('previewLocal').setAttribute('aria-pressed', String(!previewAttached));
    $('previewBones').checked = showBones;
    const attached = attachedFor(), key = currentFlowBake() ? phase : 'single';
    attachedError = attachedMode() && !attached ? (attachedCache.get(key) || {}).error || '正在準備掛接預覽…' : '';
    const status = $('attachmentPreviewStatus'); status.classList.toggle('error', !!attachedError);
    status.textContent = !enabled ? '' : attachedError || (attached ? attached.timeline.animationName + ' · 粒子 ' + attached.timeline.startTime + '–' + attached.timeline.endTime + ' 秒' + (attached.timeline.holdsEnd ? ' · 末態保留到 IN 結束' : '') : '發射器局部座標');
    $('previewFocus').disabled = !attached; $('previewFxStart').disabled = !attached;
    $('previewPickBone').disabled = !attached;
    const skins = attached ? attached.metadata.skinNames : [], picker = $('previewSkin');
    if (Array.from(picker.options).map(o => o.value).join('\n') !== skins.join('\n')) {
      picker.replaceChildren(); skins.forEach(name => { const option = document.createElement('option'); option.value = name; option.textContent = name; picker.append(option); });
    }
    $('previewSkinField').hidden = skins.length < 2; if (attached) picker.value = attached.metadata.skinName;
    $('spineTargetChip').hidden = !enabled;
    if (enabled) $('spineTargetChip').textContent = attached ? '掛接 · ' + (integration.settings.emitterParents['em_' + selectedId] || integration.settings.parentBone) : attachedError ? '掛接預覽無法解析' : '粒子局部預覽';
    if (assetsUi) assetsUi.setPreviewInfo(attached ? (attached.metadata.missingAssets.length ? '原骨架有 ' + attached.metadata.missingAssets.length + ' 個圖片路徑未匹配：' + attached.metadata.missingAssets.slice(0, 4).map(a => a.path).join('、') : '原骨架素材已完整匹配。') : attachedError || '切換至掛接預覽以檢查素材。');
  }
  function focusAttachment() {
    const attached = attachedFor(), e = emitter(), value = attached && attached.emitterPoint(e.id, e, time);
    if (!value) { notify(attachedError || '目前掛接骨骼未啟用，請檢查 Skin 與骨骼設定。', true); return; }
    panX = -value.x * zoom; panY = value.y * zoom; queueDraft();
  }
  function compileBakedPreview(output, snapshot, group, chosenPhase) {
    if (!group) return Preview.compile(output, snapshot, builtinImages.glow);
    const selected = chosenPhase || phase, animationName = output.manifest.phases[selected].animationName;
    const single = {json: Object.assign({}, output.json, {animations: {effect: output.json.animations[animationName]}}), images: output.images};
    return Preview.compile(single, group.phases[selected], builtinImages.glow);
  }
  function startBonePick(id) {
    if (bonePicker && bonePicker.active) bonePicker.cancel();
    const next = project.emitters.find(e => e.id === id);
    if (!next || !next.enabled) { notify('請先啟用要掛接的發射器。', true); return; }
    selectedId = next.id; previewAttached = true;
    if (mode === 'baked' && revision !== bakedRevision) { mode = 'live'; refreshLive(); }
    renderEmitters(); renderInspector(); refreshAttachmentPreview();
    $('spineMergeDialog').close(); bonePicker.start();
  }
  function wireBonePicker() {
    bonePicker = window.ParticleBonePicker.mount({canvas, button: $('previewPickBone'), hint: $('bonePickHint'), keepWorld: $('previewKeepWorld'), notify,
      getView: () => ({width: stageW, height: stageH, zoom, panX, panY}),
      getScene() {
        const attached = attachedFor(), e = emitter();
        if (!attached || !e.enabled) throw new Error(attachedError || '請先載入、啟用原骨架與發射器。');
        const bones = attached.bones(time), parent = integration.settings.emitterParents['em_' + e.id] || integration.settings.parentBone;
        const original = bones.find(b => b.name === parent);
        return {bones, owner: project, source: integration.json, emitterId: e.id, emitterName: e.name,
          oldMatrix: original && {...original.matrix}, cursor: time, phase, wasPlaying: playing};
      },
      onState(active, scene) {
        if (active) playing = false;
        else if (scene.owner === project && integration && scene.source === integration.json) playing = scene.wasPlaying;
        $('emitterDragHint').hidden = active; updatePlayButton(); refreshFlowUi();
      },
      onPick(bone, scene) {
        if (project !== scene.owner || !integration || integration.json !== scene.source || selectedId !== scene.emitterId || phase !== scene.phase || time !== scene.cursor) throw new Error('預覽內容已改變，請按 Esc 後重新選擇骨骼。');
        const e = emitter(), settings = integration.settings;
        const position = $('previewKeepWorld').checked ? window.ParticleBonePicker.reparentPoint(e, scene.oldMatrix, bone.matrix) : {x: e.x, y: e.y};
        Core.normalizeProject({...project, emitters: project.emitters.map(item => item === e ? {...item, ...position} : item)});
        const previous = {x: e.x, y: e.y, parents: clone(settings.emitterParents)};
        historyBegin('command');
        try {
          Object.assign(e, position);
          Object.defineProperty(settings.emitterParents, 'em_' + e.id, {value: bone.name, enumerable: true, writable: true, configurable: true});
          changed(); integrationChanged(); refreshLive(); renderInspector(); if (attachmentUi) attachmentUi.refresh();
          notify('已將「' + e.name + '」掛接到 ' + bone.name + ($('previewKeepWorld').checked ? '，紅點位置保持不變。' : '，沿用原局部 X/Y。'));
        } catch (error) { e.x = previous.x; e.y = previous.y; settings.emitterParents = previous.parents; integrationChanged(); throw error; }
        finally { historyEnd(); }
      }
    });
  }
  function activeFps() { const snapshot = activeBake(); return snapshot ? snapshot.fps : project.fps; }
  function simulationSignature(value) { const {background, spineVersion, ...simulation} = value; return JSON.stringify(simulation); }
  function effectiveSpineVersion(sourceProject, session) {
    const p = sourceProject || project, s = session === undefined ? integration : session;
    return Core.spineProfile(s && s.settings.enabled !== false ? s.json.skeleton.spine : p.spineVersion).version;
  }
  function refreshSpineTarget() {
    const version = effectiveSpineVersion(), picker = $('spineVersion');
    if (picker) {
      if (!Array.from(picker.options).some(option => option.value === version)) {
        const option = document.createElement('option'); option.value = version; option.textContent = 'SPINE ' + version; picker.append(option);
      }
      picker.value = version; picker.disabled = !!integration && integration.settings.enabled !== false;
      picker.title = picker.disabled ? '掛接輸出跟隨原骨架：Spine ' + version : '輸出版本：Spine ' + version + '；3.8、4.0、4.2 可切換';
      $('spineTargetMode').textContent = picker.disabled ? '跟隨骨架' : '輸出版本';
    }
    if (baked && exported && exported.json.skeleton.spine !== version) {
      const nextExport = flowBaked ? Core.exportFlow(flowBaked, version) : Core.exportSpine(baked, version);
      const nextPreview = compileBakedPreview(nextExport, baked, flowBaked);
      exported = nextExport; bakedPreview = nextPreview;
    }
  }
  function safeName() {
    let name = project.name.trim().replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/^[. ]+|[. ]+$/g, '').slice(0, 64) || 'particles';
    if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) name = 'particles_' + name;
    return name;
  }
  function viewState() {
    const view = {time, mode, zoom, panX, panY, previewAttached, showBones, skinName: previewSkin};
    if (currentFlowBake() || project.flow.enabled) view.phase = phase;
    return view;
  }
  function stopSequence() { sequence = false; exitRequested = false; }
  function refreshFlowUi() {
    const config = currentFlowBake() ? currentFlowBake().project.flow : project.flow;
    const enabled = !!currentFlowBake() || (mode === 'live' && project.flow.enabled);
    $('flowPreviewBar').hidden = !enabled;
    $('flowSettingsButton').querySelector('span').textContent = project.flow.enabled ? 'In / Loop / Out' : '動畫段落';
    $('flowEnabled').checked = project.flow.enabled;
    ['in', 'loop', 'out'].forEach(kind => {
      const cap = kind[0].toUpperCase() + kind.slice(1);
      ['Name', 'Duration'].forEach(field => {
        const input = $('flow' + cap + field); input.disabled = !project.flow.enabled;
        if (document.activeElement !== input) input.value = project.flow[kind][field.toLowerCase()];
      });
      const button = $('previewFlow' + cap); button.classList.toggle('active', phase === kind); button.setAttribute('aria-pressed', String(phase === kind));
      button.title = config[kind].name + ' · ' + config[kind].duration + ' 秒';
    });
    $('flowPreviewStatus').textContent = !enabled ? '' : exitRequested ? '本輪結束後進入 OUT' : sequence && phase === 'loop' ? 'LOOP 持續播放' : phase.toUpperCase() + ' · ' + previewDuration() + ' 秒' + (attachedMode() ? '（原動畫時間）' : '');
    $('flowRequestOut').disabled = !enabled || phase !== 'loop' || !playing || exitRequested;
    $('flowPlaySequence').disabled = !enabled || !activeBake();
    $('duration').disabled = project.flow.enabled; $('loop').disabled = project.flow.enabled;
    $('duration').value = project.flow.enabled ? config[phase].duration : project.duration;
    $('loop').checked = project.flow.enabled ? phase === 'loop' : project.loop;
    $('flowBake').textContent = project.flow.enabled ? '更新三段烘焙' : '更新烘焙';
  }
  function selectPhase(kind, keepPlaying) {
    phase = kind; time = 0;
    if (!keepPlaying) { stopSequence(); playing = false; }
    if (baked && exported) bakedPreview = compileBakedPreview(exported, baked, flowBaked);
    refreshFlowUi(); refreshAttachmentPreview(); updatePlayButton(); syncTimeline(); queueDraft();
  }
  function flowBindingFor(input) {
    const match = /^flow(In|Loop|Out)Duration$/.exec(input.id); if (!match) return null;
    const before = clone(project.flow), kind = match[1].toLowerCase();
    return {source: project.flow[kind], key: 'duration', restore: () => { project.flow = clone(before); refreshFlowUi(); }};
  }
  function hasEmitterSeed(e) { return Object.prototype.hasOwnProperty.call(e, 'randomSeed'); }
  function renderEmitterSeed() {
    const e = emitter(), custom = hasEmitterSeed(e), input = $('emitterRandomSeed');
    $('emitterSeedMode').value = custom ? 'custom' : 'project';
    $('emitterSeedMode').disabled = busy;
    input.disabled = busy || !custom;
    if (document.activeElement !== input) input.value = Core.emitterSeed(project, e);
    $('randomizeEmitterSeed').disabled = busy;
    $('emitterSeedHint').textContent = custom ? '複製後保留相同變化；按「換一組」或改數值，讓這一層產生不同變化。' : '依專案種子與各發射器自動分組；按「換一組」即可獨立調整這一層。';
  }
  function seedBindingFor(input) {
    if (input.id !== 'emitterRandomSeed') return null;
    const e = emitter(), owned = hasEmitterSeed(e), before = e.randomSeed;
    return {source: e, key: 'randomSeed', restore() {
      if (owned) e.randomSeed = before; else delete e.randomSeed;
      renderEmitterSeed();
    }};
  }
  function setEmitterSeed(value) {
    if (busy) return false;
    const e = emitter(), owned = hasEmitterSeed(e), before = e.randomSeed;
    if (value === undefined ? !owned : owned && before === value) return false;
    if (value !== undefined) Core.emitterSeed(project, {id: e.id, randomSeed: value});
    if (value === undefined) delete e.randomSeed; else e.randomSeed = value;
    changed(); renderEmitterSeed(); return true;
  }
  function nextEmitterSeed(previous) {
    let next;
    try { const values = new Uint32Array(1); window.crypto.getRandomValues(values); next = values[0]; }
    catch (_) { next = Math.floor(Math.random() * 4294967296); }
    return next === previous ? (previous + 1) >>> 0 : next;
  }
  function wireEmitterSeed() {
    const mode = $('emitterSeedMode'), input = $('emitterRandomSeed');
    mode.addEventListener('change', () => {
      if (busy) { renderEmitterSeed(); return; }
      historyBegin('command');
      try { setEmitterSeed(mode.value === 'custom' ? Core.emitterSeed(project, emitter()) : undefined); }
      catch (error) { renderEmitterSeed(); notify(error.message, true); }
      finally { historyEnd(); }
    });
    $('randomizeEmitterSeed').addEventListener('click', () => {
      if (busy) return;
      historyBegin('command');
      try { setEmitterSeed(nextEmitterSeed(Core.emitterSeed(project, emitter()))); }
      catch (error) { renderEmitterSeed(); notify(error.message, true); }
      finally { historyEnd(); }
    });
    const apply = duringInput => {
      if (busy || input.disabled) return;
      if (!input.checkValidity()) { if (!duringInput) input.reportValidity(); return; }
      if (!input.value.trim()) return;
      try { setEmitterSeed(Number(input.value)); }
      catch (error) { if (!duringInput) { renderEmitterSeed(); notify(error.message, true); } }
    };
    input.addEventListener('input', () => apply(true));
    input.addEventListener('change', () => apply(false));
    input.addEventListener('blur', renderEmitterSeed);
  }

  function updateBakeStatus() {
    refreshSpineTarget();
    refreshFlowUi();
    const status = $('bakeStatus');
    status.classList.remove('dirty', 'baked');
    const dot = document.createElement('span'); dot.className = 'status-dot'; dot.setAttribute('aria-hidden', 'true');
    status.replaceChildren(dot);
    const dirty = baked && revision !== bakedRevision;
    if (busy) status.append('正在烘焙…');
    else if (!baked) status.append('尚未烘焙');
    else if (dirty) { status.append('參數已修改 · 輸出時自動烘焙'); status.classList.add('dirty'); }
    else { status.append('烘焙已更新 · 可輸出'); status.classList.add('baked'); }
    $('exportButton').disabled = busy;
    $('exportButton').title = baked && !dirty ? '輸出目前烘焙結果（Ctrl＋E）' : '自動更新烘焙後輸出（Ctrl＋E）';
    $('bakeButton').disabled = busy;
    $('newProject').disabled = busy || resettingProject;
    $('modeBaked').disabled = !baked;
    updateHistoryStatus();
    $('modeLive').classList.toggle('active', mode === 'live');
    $('modeLive').setAttribute('aria-pressed', String(mode === 'live'));
    $('modeBaked').classList.toggle('active', mode === 'baked');
    $('modeBaked').setAttribute('aria-pressed', String(mode === 'baked'));
    if (batchUi) batchUi.refresh();
    $('exportButton').querySelector('span').textContent = integration && integration.settings.enabled !== false ? '輸出追加包' : '輸出 Spine';
    if (attachmentUi) attachmentUi.refresh();
    if (assetsUi) assetsUi.refresh();
    refreshFlowUi();
    refreshAttachmentPreview();
    renderEmitterSeed();
    renderBakeCheck();
    renderPathFacing();
  }
  function renderEmitters() {
    const list = $('emitterList'); list.replaceChildren();
    const shapeNames = {point: '點形', direction: '定向', line: '線形', circle: '圓形', ring: '圓環', box: '矩形', outline: '物件輪廓'};
    const shapeIcons = {
      point: 'M12 8v8M8 12h8M5 5h.01M19 5h.01M5 19h.01M19 19h.01',
      direction: 'M12 18V6m-4 4 4-4 4 4M5 15l7-12 7 12',
      line: 'M5 12h14M5 8v8M19 8v8',
      circle: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16M12 9v6M9 12h6',
      ring: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8',
      box: 'M5 5h14v14H5zM9 12h6M12 9v6',
      sparks: 'm12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3Z',
      coins: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M14.5 8.5h-4a2 2 0 0 0 0 4h3a2 2 0 0 1 0 4h-4M12 7v11',
      bubbles: 'M10 6a7 7 0 1 0 0 14 7 7 0 0 0 0-14M7 9l-1 2M19 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4'
    };
    project.emitters.forEach((item, layerIndex) => {
      const row = document.createElement('div'); row.className = 'emitter-item'; row.classList.toggle('selected', item.id === selectedId);
      row.classList.toggle('disabled', !item.enabled);
      const check = document.createElement('input'); check.type = 'checkbox'; check.checked = item.enabled; check.setAttribute('aria-label', '啟用 ' + item.name);
      check.addEventListener('change', () => { item.enabled = check.checked; changed(); renderEmitters(); });
      const button = document.createElement('button'); button.type = 'button'; button.className = 'emitter-info'; button.setAttribute('aria-pressed', String(item.id === selectedId)); button.setAttribute('aria-label', '選擇 ' + item.name);
      const icon = document.createElement('span'); icon.className = 'emitter-icon'; icon.setAttribute('aria-hidden', 'true');
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '1.5'); svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const textureKind = item.shape === 'point' && item.image ? item.image.name.replace(/\.png$/i, '') : '';
      path.setAttribute('d', shapeIcons[textureKind] || shapeIcons[item.shape] || shapeIcons.point); svg.append(path); icon.append(svg);
      const copy = document.createElement('span'); copy.className = 'emitter-copy';
      const name = document.createElement('span'); name.className = 'emitter-name'; name.textContent = item.name;
      const meta = document.createElement('span'); meta.className = 'emitter-meta'; meta.textContent = item.count + ' 顆 · ' + (item.blend === 'additive' ? '加色' : '一般');
      const tags = document.createElement('span'); tags.className = 'emitter-tags';
      const type = document.createElement('span'); type.className = 'emitter-type'; type.textContent = item.path && item.path.enabled ? '沿路徑移動' : (shapeNames[item.shape] || '點形') + (['box', 'circle', 'ring'].includes(item.shape) ? emitFrom(item) === 'edge' ? ' · 邊框' : ' · 區域內' : '');
      const color = document.createElement('span'); color.className = 'emitter-color-dot'; color.style.setProperty('--emitter-color', item.colorGradient && item.colorGradient.length ? item.colorGradient[0].color : item.colorStart); color.setAttribute('aria-hidden', 'true');
      tags.append(type, color); copy.append(name, meta, tags);
      const index = document.createElement('span'); index.className = 'emitter-index'; index.textContent = String(layerIndex + 1).padStart(2, '0'); index.setAttribute('aria-hidden', 'true');
      button.append(icon, copy, index); button.addEventListener('click', () => selectEmitter(item.id));
      const tools = document.createElement('span'); tools.className = 'emitter-preview-tools';
      const muted = soloId ? soloId !== item.id : previewHidden.has(item.id);
      row.classList.toggle('preview-muted', muted);
      const eye = document.createElement('button'); eye.type = 'button'; eye.className = 'emitter-tool emitter-eye';
      eye.setAttribute('aria-pressed', String(previewHidden.has(item.id)));
      eye.title = previewHidden.has(item.id) ? '預覽中已隱藏（不影響輸出）· H' : '只在預覽隱藏此層（不影響輸出）· H';
      eye.setAttribute('aria-label', (previewHidden.has(item.id) ? '顯示 ' : '預覽隱藏 ') + item.name);
      eye.innerHTML = previewHidden.has(item.id) ? '<svg aria-hidden="true" viewBox="0 0 20 20"><path d="M3 3l14 14M8.5 5.2A8 8 0 0 1 10 5c4.5 0 7.5 5 7.5 5a14 14 0 0 1-2.3 2.8M12.8 14.3A7 7 0 0 1 10 15c-4.5 0-7.5-5-7.5-5a14 14 0 0 1 3-3.4"/></svg>' : '<svg aria-hidden="true" viewBox="0 0 20 20"><path d="M2.5 10S5.5 5 10 5s7.5 5 7.5 5-3 5-7.5 5-7.5-5-7.5-5Z"/><circle cx="10" cy="10" r="2.2"/></svg>';
      eye.addEventListener('click', event => { event.stopPropagation(); togglePreviewHidden(item.id); });
      const solo = document.createElement('button'); solo.type = 'button'; solo.className = 'emitter-tool emitter-solo';
      solo.setAttribute('aria-pressed', String(soloId === item.id)); solo.textContent = 'S';
      solo.title = soloId === item.id ? '取消單獨顯示 · S' : '預覽只顯示此層（不影響輸出）· S';
      solo.setAttribute('aria-label', (soloId === item.id ? '取消單獨顯示 ' : '單獨顯示 ') + item.name);
      solo.addEventListener('click', event => { event.stopPropagation(); toggleSolo(item.id); });
      tools.append(solo, eye);
      row.append(check, button, tools); list.append(row);
    });
    const index = project.emitters.findIndex(item => item.id === selectedId);
    $('addEmitter').disabled = project.emitters.length >= 8;
    $('addEmitter').title = project.emitters.length >= 8 ? '已達 8 個發射器上限' : '快速新增柔光粒子';
    $('duplicateEmitter').disabled = project.emitters.length >= 8;
    $('deleteEmitter').disabled = project.emitters.length <= 1;
    $('moveEmitterUp').disabled = index <= 0;
    $('moveEmitterDown').disabled = index === project.emitters.length - 1;
    renderHandles();
    if (attachmentUi) attachmentUi.refresh();
    refreshAttachmentPreview();
  }
  function togglePreviewHidden(id) {
    if (previewHidden.has(id)) previewHidden.delete(id); else previewHidden.add(id);
    if (soloId) soloId = null;
    renderEmitters();
  }
  function toggleSolo(id) { soloId = soloId === id ? null : id; renderEmitters(); }
  function selectEmitter(id) {
    selectedId = id; recordHistory(); renderEmitters(); renderInspector();
  }
  function moveInteraction(event) {
    if (!interaction) return;
    const dx = event.clientX - interaction.x, dy = event.clientY - interaction.y;
    if (interaction.type === 'pan') { panX = interaction.originalX + dx; panY = interaction.originalY + dy; return; }
    const e = interaction.e;
    const delta = interaction.matrix ? AttachmentPreview.inverseDelta(interaction.matrix, {x: dx / zoom, y: -dy / zoom}) : {x: dx / zoom, y: -dy / zoom};
    if (!delta) return;
    const x = Math.round(clamp(interaction.originalX + delta.x, -4000, 4000));
    const y = Math.round(clamp(interaction.originalY + delta.y, -4000, 4000));
    if (e.x === x && e.y === y) return;
    e.x = x; e.y = y; changed(); renderInspector();
  }
  function finishInteraction(event) {
    if (interaction && interaction.type === 'emitter') {
      if (event && event.type === 'pointercancel') {
        interaction.e.x = interaction.originalX; interaction.e.y = interaction.originalY;
        changed(); renderInspector();
      }
      refreshLive(); if (interaction.wasPlaying !== undefined) { playing = interaction.wasPlaying; updatePlayButton(); }
    }
    interaction = null; queueDraft();
  }
  function renderHandles() {
    for (const [id, button] of handles) {
      if (!project.emitters.some(e => e.id === id)) { button.remove(); handles.delete(id); }
    }
    project.emitters.forEach((item, index) => {
      let button = handles.get(item.id);
      if (!button) {
        button = document.createElement('button'); button.type = 'button'; button.className = 'emitter-handle';
        button.dataset.emitterId = item.id;
        const label = document.createElement('span'); label.className = 'emitter-handle-label'; button.append(label);
        const id = item.id;
        button.addEventListener('click', () => selectEmitter(id));
        button.addEventListener('pointerdown', event => {
          if (![0, 1, 2].includes(event.button)) return;
          event.preventDefault(); event.stopPropagation(); button.focus({preventScroll: true});
          if (event.button === 0) {
            const target = project.emitters.find(e => e.id === id); if (!target) return;
            selectEmitter(id);
            interaction = {type: 'emitter', e: target, x: event.clientX, y: event.clientY, originalX: target.x, originalY: target.y};
            if (attachedMode()) {
              const attached = attachedFor(), frame = attached && attached.emitterFrame(id, time);
              if (!frame || !frame.draggable) { interaction = null; notify('目前骨骼未啟用或縮放為零，無法拖曳掛接點。', true); return; }
              interaction.matrix = {...frame.matrix}; interaction.wasPlaying = playing; playing = false; updatePlayButton();
            }
          } else interaction = {type: 'pan', x: event.clientX, y: event.clientY, originalX: panX, originalY: panY};
          button.setPointerCapture(event.pointerId);
        });
        button.addEventListener('pointermove', moveInteraction);
        button.addEventListener('pointerup', finishInteraction);
        button.addEventListener('pointercancel', finishInteraction);
        button.addEventListener('lostpointercapture', finishInteraction);
        button.addEventListener('keydown', event => {
          const delta = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1]}[event.key];
          if (!delta) return;
          event.preventDefault(); event.stopPropagation(); const e = project.emitters.find(item => item.id === id); if (!e) return;
          selectEmitter(id); const step = event.shiftKey ? 10 : 1;
          e.x = clamp(e.x + delta[0] * step, -4000, 4000); e.y = clamp(e.y + delta[1] * step, -4000, 4000);
          changed(); renderInspector();
        });
        handles.set(id, button); handleLayer.append(button);
      }
      button.classList.toggle('selected', item.id === selectedId);
      button.classList.toggle('inactive', !item.enabled);
      button.setAttribute('aria-pressed', String(item.id === selectedId));
      button.setAttribute('aria-label', '選取並移動發射器 ' + item.name);
      button.style.zIndex = item.id === selectedId ? 20 : String(project.emitters.length - index);
      button.querySelector('.emitter-handle-label').textContent = item.name + (item.enabled ? '' : '（停用）');
    });
    updateHandlePositions();
  }
  function updateHandlePositions() {
    const attached = attachedFor();
    project.emitters.forEach(e => {
      const button = handles.get(e.id); if (!button) return;
      const position = attachedMode() ? attached && attached.emitterPoint(e.id, e, time) : e;
      if (!position) { button.hidden = true; return; }
      const frame = attached && attached.emitterFrame(e.id, time); button.disabled = !!frame && !frame.draggable;
      const x = stageW / 2 + panX + position.x * zoom, y = stageH / 2 + panY - position.y * zoom;
      button.style.left = x + 'px'; button.style.top = y + 'px';
      button.classList.toggle('label-left', x > stageW - 180);
      button.hidden = x < -13 || y < -13 || x > stageW + 13 || y > stageH + 13;
      button.title = e.name + ' · 局部 X ' + e.x + ' / Y ' + e.y + (frame ? ' · 掛接 ' + frame.parentBone : '') + ' · 拖曳移動；方向鍵調整局部 X/Y，Shift 加速';
    });
  }
  // Shared controls edit the same emitter field without disrupting active typing.
  function syncEmitterPeers(input, e = emitter()) {
    const field = input.dataset.field;
    if (!field) return;
    controls.forEach(peer => {
      if (peer === input || peer.dataset.field !== field) return;
      if (peer.type === 'checkbox') peer.checked = !!e[field];
      else peer.value = e[field];
    });
  }
  function renderInspector() {
    const e = emitter();
    controls.forEach(input => {
      if (input.type === 'checkbox') input.checked = !!e[input.dataset.field];
      else input.value = input.dataset.field === 'emitFrom' ? emitFrom(e) : input.dataset.field === 'directionMode' ? directionMode(e) : input.dataset.field === 'directionSpread' ? e.directionSpread || 0 : input.dataset.field === 'startDelay' ? e.startDelay || 0 : e[input.dataset.field];
    });
    document.querySelectorAll('[data-shape-for]').forEach(group => { group.hidden = !group.dataset.shapeFor.split(/\s+/).includes(e.shape); });
    $('emitFromHint').textContent = emitFrom(e) === 'edge' ? (e.shape === 'box' ? '沿矩形四邊發射，按邊長分配粒子。' : '從圓形或橢圓的輪廓線發射；圓環仍可限制弧段角度。') + '粒子出生後依速度與外力移動。' : '從形狀內部發射；圓環會沿用設定的弧段範圍。';
    document.querySelectorAll('[data-readout]').forEach(output => { output.textContent = e[output.dataset.readout]; });
    renderEmitterSeed();
    if (textureUi) textureUi.refresh();
    else {
      const image = e.sequence && e.sequence.enabled ? e.sequence.frames[0] : e.image || builtinImages.glow;
      $('textureThumbnail').src = image.dataUrl; $('textureThumbnail').hidden = false;
      $('textureInfo').textContent = (e.image ? e.image.name : '內建柔光') + ' · ' + image.width + ' × ' + image.height + ' px';
    }
    renderPathInspector();
    renderOutlineInspector();
    drawCurves();
    if (libraryUi && $('effectLibraryDialog').open) libraryUi.refresh();
  }
  function pathFor(e) { return e.path || PathMath.defaults(); }
  function renderOutlineInspector() {
    const e = emitter(), outline = e.outline;
    $('outlineThreshold').value = outline ? outline.threshold : 24; $('outlineHoles').checked = !!(outline && outline.includeHoles);
    $('outlineShowImage').checked = !outline || outline.showImage !== false;
    $('outlineThumbnail').hidden = !(outline && outline.image);
    if (outline && outline.image) $('outlineThumbnail').src = outline.image.dataUrl;
    $('rescanOutline').disabled = !(outline && outline.image);
    $('outlineSummary').textContent = outline ? outline.sourceName + ' · ' + outline.contours.length + ' 個輪廓 · ' + outline.width + ' × ' + outline.height + ' px' : '請載入含透明背景的 PNG。';
  }
  async function scanOutline(image, selected, threshold, includeHoles) {
    const request = ++outlineRequest;
    const outline = await scanOutlineImage(image, threshold, includeHoles, selected.outline ? selected.outline.showImage !== false : true);
    if (request !== outlineRequest || !project.emitters.includes(selected)) return;
    const result = outline, previous = {outline: selected.outline, shape: selected.shape, emitFrom: selected.emitFrom, width: selected.width, height: selected.height};
    selected.outline = outline; selected.shape = 'outline'; selected.emitFrom = 'edge';
    if (!previous.outline || previous.outline.image && previous.outline.image.dataUrl !== image.dataUrl) { selected.width = Math.min(2000, image.width); selected.height = Math.min(2000, image.height); }
    try { Core.normalizeProject(project); } catch (error) { Object.assign(selected, previous); throw error; }
    changed(); renderEmitters(); renderInspector();
    notify(result.opaque ? '圖片沒有透明背景，掃描結果是整張圖片的矩形邊界；請載入去背 PNG 取得物件輪廓。' : selected.path && selected.path.enabled && !selected.path.offsets ? '已掃描輪廓；請停用路徑或勾選「疊加發射範圍與外力」，以使用輪廓發射。' : '已掃描物件輪廓；可調整發射大小、速度與生命曲線。');
  }
  async function scanOutlineImage(image, threshold, includeHoles, showImage = true) {
    if (!Number.isInteger(threshold) || threshold < 1 || threshold > 255) throw new Error('透明度閾值需為 1–255。');
    const source = new Image(); source.src = image.dataUrl; await source.decode();
    const surface = document.createElement('canvas'); surface.width = image.width; surface.height = image.height;
    const c = surface.getContext('2d', {willReadFrequently: true}); c.drawImage(source, 0, 0);
    const result = ContourMath.scan({width: image.width, height: image.height, data: c.getImageData(0, 0, image.width, image.height).data, threshold, includeHoles, sourceName: image.name});
    return Object.assign({}, result, {image, showImage});
  }
  async function loadPathOutline(file, selected) {
    if (!file || file.type !== 'image/png') throw new Error('請選擇含透明背景的 PNG 物件圖片。');
    const image = await loadImage(file), previous = selected.outline;
    const outline = await scanOutlineImage(image, previous ? previous.threshold : 24, previous ? previous.includeHoles : false, previous ? previous.showImage !== false : true);
    const ratio = Math.min(1, 2000 / image.width, 2000 / image.height);
    return {outline, width: Math.max(1, image.width * ratio), height: Math.max(1, image.height * ratio)};
  }
  function renderPathFacing() {
    const e = emitter(), active = !!(e.path && e.path.enabled), aligned = !!e.alignDirection;
    $('pathFacingOffsetField').hidden = !aligned;
    $('pathFacingSpinHint').hidden = !aligned || !(e.spin || e.spinRandom);
    $('pathStopSpin').disabled = busy || !active || !aligned || !(e.spin || e.spinRandom);
    $('pathFacingHint').textContent = aligned ?
      '貼圖朝右為 0°；原圖朝上時，偏移設 −90°。與外觀頁的起始旋轉同步；箭頭或長條貼圖較容易看出轉向。' + (active && e.path.offsets ? '朝向以原路徑方向為準，不含外力造成的位移。' : '') :
      '勾選後，貼圖會隨路徑轉彎；箭頭或長條貼圖較容易看出差異。與外觀頁的方向對齊設定同步。';
  }
  function renderPathInspector() {
    const e = emitter(), path = pathFor(e), active = !!path.enabled;
    $('enablePath').checked = active; $('pathMotionFields').hidden = !active;
    $('pathSection').classList.toggle('path-inactive', !active);
    $('pathSummary').hidden = !e.path;
    $('pathMotionHint').hidden = !active;
    $('editPath').textContent = active ? '編輯路徑與控制點' : e.path ? '編輯已保存的路徑' : '設定移動路徑';
    $('pathMode').value = path.mode; $('pathOffsets').checked = !!path.offsets;
    let compiled = null, errorMessage = '';
    if (active) { try { compiled = PathMath.compile(path); } catch (error) { errorMessage = error.message; } }
    $('pathSummary').textContent = errorMessage || (active ? (path.closed ? '封閉' : '開放') + ' · ' + path.points.length + ' 個控制點 · ' + Math.round(compiled.totalLength) + ' px' + (path.reverse ? ' · 反向' : '') : e.path ? '已停用 · 保留控制點與設定' : '未啟用路徑');
    const message = !active ? '' : (path.mode === 'lifetime' ? '每個粒子在生命期間走完整條路徑。' : '依像素速度前進；開放路徑到終點停止。') + (path.offsets ? '已疊加發射範圍與外力。' : '粒子貼合路徑。');
    $('pathMotionHint').textContent = message;
    ['speed', 'speedRandom'].forEach(field => { const input = controls.find(control => control.dataset.field === field); if (input) { input.disabled = active && path.mode === 'lifetime'; input.title = input.disabled ? '生命期間走完整條模式，以粒子生命長度決定總時間。' : '每秒移動像素；可左右拖曳調值'; } });
    ['shape', 'emitFrom', 'width', 'height', 'lineLength', 'lineRotation', 'arcAngle', 'arcRotation', 'wind', 'gravity'].forEach(field => { const input = controls.find(control => control.dataset.field === field); if (input) input.disabled = active && !path.offsets; });
    ['angle', 'spread'].forEach(field => { const input = controls.find(control => control.dataset.field === field); if (input) input.disabled = active; });
    const strict = active && !path.offsets;
    $('emissionPathNotice').hidden = !active;
    $('emissionPathHint').textContent = strict ? '目前粒子貼合路徑，發射範圍與發射方向暫停作用；原設定會保留。' : '目前沿路徑移動，已疊加發射範圍；發射方向由路徑決定。';
    $('speedModeHint').hidden = !(active && path.mode === 'lifetime');
    $('speedModeHint').textContent = '目前以生命長度控制走完整條路徑的時間，像素速度暫停作用；原數值會保留。';
    $('forceModeHint').hidden = !strict;
    $('forceModeHint').textContent = '目前粒子貼合路徑，風力與重力暫停作用；可在下方「更多路徑選項」啟用疊加。';
    ['shape', 'emitFrom', 'width', 'height', 'lineLength', 'lineRotation', 'arcAngle', 'arcRotation', 'wind', 'gravity', 'angle', 'spread'].forEach(field => {
      const input = controls.find(control => control.dataset.field === field);
      if (input) input.title = input.disabled ? ['angle', 'spread'].includes(field) ? '沿路徑移動時，由路徑決定方向；停用路徑後恢復原值。' : '貼合路徑時暫停作用；可開啟「疊加發射範圍與外力」，原數值會保留。' : input.type === 'number' ? '按住左右拖曳調值；Shift 加速、Alt 微調；點一下可直接輸入' : '';
    });
    $('speedCurveHint').textContent = (active && path.mode === 'lifetime' ? '曲線決定前進節奏，會正規化總距離；整條為 0 時停在起點。' : '0 為停止，1 為基礎速度，4 為四倍速度。') + '中間節點選貝茲可調整左右兩側；拖控制柄預設平衡，Ctrl 單側調整。';
    const alignment = controls.find(input => input.dataset.field === 'alignDirection');
    if (alignment) alignment.parentElement.lastChild.textContent = active ? '貼圖朝向路徑切線' : '貼圖朝向移動方向';
    renderPathFacing();
    renderEmissionDirection();
  }
  function renderEmissionDirection() {
    const e = emitter(), mode = directionMode(e), alongPath = !!(e.path && e.path.enabled);
    const outward = mode === 'radial' || mode === 'normal', directionalLine = e.shape === 'direction';
    $('emitterDirectionMode').disabled = alongPath;
    $('emitterDirectionMode').title = alongPath ? '沿路徑移動時方向由路徑決定；停用路徑後恢復原設定。' : '選擇粒子出生時的移動方向';
    $('fixedDirectionFields').hidden = mode !== 'fixed' && !directionalLine;
    $('fixedSpreadField').hidden = mode !== 'fixed';
    $('shapeDirectionFields').hidden = !outward;
    const angle = controls.find(input => input.dataset.field === 'angle'), spread = controls.find(input => input.dataset.field === 'spread');
    if (angle) { angle.disabled = alongPath || (mode !== 'fixed' && !directionalLine); if (!alongPath) angle.title = angle.disabled ? '此模式由中心或輪廓決定方向，原指定角度保留。' : '按住左右拖曳調值；Shift 加速、Alt 微調；點一下可直接輸入'; }
    if (spread) { spread.disabled = alongPath || mode !== 'fixed'; if (!alongPath) spread.title = spread.disabled ? '此模式使用自己的方向散射，原指定角度的散射值保留。' : '按住左右拖曳調值；Shift 加速、Alt 微調；點一下可直接輸入'; }
    $('directionSpread').disabled = alongPath || !outward;
    $('directionSpread').title = alongPath ? '沿路徑移動時方向散射暫停，原設定保留。' : '0 為沿選定方向；增加可讓粒子偏離中心方向或輪廓法線，360 為全方向。';
    $('directionAngleLabel').innerHTML = directionalLine && mode !== 'fixed' ? '定向軸角度 <small>°</small>' : '方向角度 <small>°</small>';
    let hint = mode === 'random' ? '每顆粒子的方向隨機分布於 360°，不受指定角度影響。' : mode === 'radial' ? '以發射器紅點為中心，沿粒子的出生位置向外；方向散射為 0 時完全向外。' : mode === 'normal' ? (e.shape === 'outline' ? '沿 PNG 邊界垂直向外；啟用內孔時朝孔內空白區發射。' : e.shape === 'box' ? '沿矩形邊界垂直向外；區域內的粒子依最近一邊向外。' : e.shape === 'line' ? '沿線段的垂直方向發射；線段 0° 時朝上，方向散射為 0 時方向一致。' : '沿形狀的外法線發射；正圓以中心向外，橢圓沿邊界垂直向外。') : '0° 向右，90° 向上；散射角控制左右偏移範圍。';
    if (outward && e.shape === 'point') hint = '點狀沒有輪廓或半徑，會沿原指定角度發射；選圓形、矩形或 PNG 輪廓可製作向外效果。';
    if (alongPath) hint = '目前沿路徑移動，發射方向暫停作用；停用路徑後恢復所選方向。';
    $('emissionDirectionHint').textContent = hint;
  }
  function changePath(field, value) {
    const e = emitter(), prior = e.path;
    try {
      e.path = PathMath.normalize(Object.assign({}, pathFor(e), {[field]: value}));
      if (e.path.enabled) PathMath.compile(e.path);
      Core.normalizeProject(project); changed(); renderEmitters(); renderInspector();
    } catch (error) { e.path = prior; renderInspector(); notify(error.message, true); }
  }
  function renderGlobals() {
    refreshSpineTarget();
    $('projectName').value = project.name; $('duration').value = project.duration;
    if (!Array.from($('fps').options).some(option => Number(option.value) === project.fps)) {
      const option = document.createElement('option'); option.value = project.fps; option.textContent = project.fps + ' FPS'; $('fps').append(option);
    }
    $('fps').value = String(project.fps); $('loop').checked = project.loop;
    $('projectSeed').value = project.seed; $('backgroundColor').value = project.background.color;
    $('removeBackground').disabled = !project.background.image;
    $('backgroundActualSize').hidden = !project.background.image;
    const bg = project.background, size = bg.image && {width: bg.sourceWidth || bg.image.width, height: bg.sourceHeight || bg.image.height};
    $('backgroundInfo').hidden = !size;
    $('backgroundInfo').textContent = size ? (bg.sourceWidth ? '原圖 ' : '參考圖 ') + size.width + ' × ' + size.height + ' px' : '';
    $('backgroundInfo').title = bg.sourceWidth ? '背景依來源像素尺寸與物件、粒子對齊。' : '舊案未保存原圖尺寸；重新載入原背景圖即可保留原始像素大小。';
    $('zoom').value = Math.round(zoom * 100); $('zoomLabel').textContent = Math.round(zoom * 100) + '%';
    refreshFlowUi();
  }
  function refreshLive() {
    clearTimeout(liveTimer); liveTimer = null;
    preloadParticleImages();
    try {
      liveFlowBake = project.flow.enabled ? Core.bakeFlow(project) : null;
      liveBake = liveFlowBake ? liveFlowBake.phases.loop : Core.bake(project); liveError = '';
    } catch (error) { liveBake = null; liveFlowBake = null; liveError = error.message; notify(error.message, true); }
    refreshFlowUi(); refreshAttachmentPreview();
  }
  function changed(updateInspector) {
    stopSequence();
    revision++; mode = 'live';
    if (!liveTimer) liveTimer = setTimeout(refreshLive, 35);
    updateBakeStatus();
    if (updateInspector) renderInspector();
    queueDraft();
  }
  function saveDraftSnapshot(raw) {
    const pending = draftWrite.catch(() => {}).then(() => Storage.saveDraft(raw));
    draftWrite = pending;
    return pending;
  }
  function queueDraft() {
    recordHistory();
    if (!initialized) return;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(async () => {
      const owner = project;
      try {
        const raw = JSON.parse(Storage.serialize(project, baked ? baked.project : null, viewState(), integration));
        await saveDraftSnapshot(raw);
        if (owner === project) $('appStatus').textContent = '本機草稿已保存';
      } catch (error) { if (owner === project) $('appStatus').textContent = error.message || '請儲存專案檔'; }
    }, 700);
  }
  function imageFor(image) {
    const data = image ? image.dataUrl : builtinImages.glow.dataUrl;
    if (imageCache.has(data)) return imageCache.get(data);
    const element = new Image(); element.src = data; imageIds.set(element, nextImageId++);
    imageCache.set(data, element);
    // Keep every image of the current rig; cycling through a 20-image cache
    // prevented rigs with many slots from finishing image decoding.
    return element;
  }
  function preloadParticleImages() {
    project.emitters.forEach(e => {
      if (e.image) imageFor(e.image);
      if (e.sequence) e.sequence.frames.forEach(imageFor);
    });
  }
  function tinted(image, color, dark) {
    const source = imageFor(image);
    if (!source.complete || !source.naturalWidth) return null;
    const channels = color.map(value => Math.round(clamp(value, 0, 1) * 255));
    if (channels.every(value => value === 255) && (!dark || dark.every(value => value === 0)) && !(image && image.pma)) return source;
    const shadows = dark ? dark.map(value => Math.round(clamp(value, 0, 1) * 255)) : [0, 0, 0];
    const key = imageIds.get(source) + ':' + channels.join(',') + ':' + shadows.join(',') + ':' + !!(image && image.pma);
    if (tintCache.has(key)) return tintCache.get(key);
    const surface = document.createElement('canvas');
    const scale = Math.min(1, 384 / Math.max(source.naturalWidth, source.naturalHeight));
    surface.width = Math.max(1, Math.round(source.naturalWidth * scale)); surface.height = Math.max(1, Math.round(source.naturalHeight * scale));
    const c = surface.getContext('2d');
    c.drawImage(source, 0, 0, surface.width, surface.height);
    const pixels = c.getImageData(0, 0, surface.width, surface.height);
    for (let offset = 0; offset < pixels.data.length; offset += 4) {
      const unpremultiply = image && image.pma && pixels.data[offset + 3] ? 255 / pixels.data[offset + 3] : 1;
      for (let channel = 0; channel < 3; channel++) {
        const light = Math.min(255, pixels.data[offset + channel] * unpremultiply);
        pixels.data[offset + channel] = Math.round((light * channels[channel] + (255 - light) * shadows[channel]) / 255);
      }
    }
    c.putImageData(pixels, 0, 0);
    tintCache.set(key, surface);
    if (tintCache.size > 80) tintCache.delete(tintCache.keys().next().value);
    return surface;
  }
  function resize() {
    const rect = canvas.getBoundingClientRect();
    stageW = Math.max(1, rect.width); stageH = Math.max(1, rect.height);
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(stageW * dpr); canvas.height = Math.round(stageH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawCurves();
  }
  function drawGizmos(source) {
    const attached = attachedFor();
    ctx.save(); ctx.globalCompositeOperation = 'source-over';
    source.emitters.forEach(e => {
      const frame = attachedMode() ? attached && attached.emitterFrame(e.id, time) : null;
      if (attachedMode() && !frame) return;
      ctx.save();
      if (frame) { const m = frame.matrix; ctx.transform(m.a, -m.c, -m.b, m.d, m.x, -m.y); }
      ctx.translate(e.x, -e.y);
      const chosen = e.id === selectedId;
      if (e.path && e.path.enabled) {
        const key = JSON.stringify(e.path); let compiled = pathGizmoCache.get(key);
        if (!compiled) { compiled = PathMath.compile(e.path); pathGizmoCache.set(key, compiled); if (pathGizmoCache.size > 16) pathGizmoCache.delete(pathGizmoCache.keys().next().value); }
        ctx.strokeStyle = chosen ? '#6cdec7' : '#738194'; ctx.globalAlpha = e.enabled ? (chosen ? .75 : .3) : .2;
        ctx.lineWidth = (chosen ? 1.6 : 1) / zoom; ctx.setLineDash([6 / zoom, 4 / zoom]); ctx.beginPath();
        compiled.points.forEach((point, index) => { if (index) ctx.lineTo(point.x, -point.y); else ctx.moveTo(point.x, -point.y); });
        if (e.path.closed) ctx.closePath(); ctx.stroke(); ctx.setLineDash([]);
        if (chosen) {
          ctx.fillStyle = '#6cdec7'; compiled.points.slice(0, 1).forEach(point => { ctx.beginPath(); ctx.arc(point.x, -point.y, 4 / zoom, 0, Math.PI * 2); ctx.fill(); });
          const point = compiled.sample(.08), a = -point.angle * Math.PI / 180, length = 9 / zoom;
          ctx.beginPath(); ctx.moveTo(point.x - Math.cos(a - .5) * length, -point.y - Math.sin(a - .5) * length); ctx.lineTo(point.x, -point.y); ctx.lineTo(point.x - Math.cos(a + .5) * length, -point.y - Math.sin(a + .5) * length); ctx.stroke();
        }
        if (!e.path.offsets) { ctx.restore(); return; }
      }
      ctx.strokeStyle = chosen ? '#87b9af' : '#738194'; ctx.globalAlpha = e.enabled ? (chosen ? 0.7 : 0.35) : 0.2;
      const edge = e.shape === 'outline' || ['box', 'circle', 'ring'].includes(e.shape) && emitFrom(e) === 'edge';
      ctx.lineWidth = (edge && chosen ? 1.6 : 1) / zoom; ctx.setLineDash([4 / zoom, 4 / zoom]);
      ctx.beginPath();
      if (e.shape === 'outline' && e.outline) {
        let record = outlineGizmoCache.get(e.outline);
        if (!record || record.width !== e.width || record.height !== e.height || record.holes !== e.outline.includeHoles) { record = {width: e.width, height: e.height, holes: e.outline.includeHoles, compiled: ContourMath.compile(e.outline, e.width, e.height)}; outlineGizmoCache.set(e.outline, record); }
        record.compiled.contours.forEach(points => { points.forEach((p, i) => { if (i) ctx.lineTo(p.x, -p.y); else ctx.moveTo(p.x, -p.y); }); ctx.closePath(); });
      }
      else if (e.shape === 'box') ctx.rect(-e.width / 2, -e.height / 2, e.width, e.height);
      else if (e.shape === 'line') {
        const a = (e.lineRotation || 0) * Math.PI / 180, half = (e.lineLength || 0) / 2;
        const x = Math.cos(a) * half, y = -Math.sin(a) * half;
        ctx.moveTo(-x, -y); ctx.lineTo(x, y);
        const tx = Math.sin(a) * 5 / zoom, ty = Math.cos(a) * 5 / zoom;
        ctx.moveTo(-x - tx, -y - ty); ctx.lineTo(-x + tx, -y + ty);
        ctx.moveTo(x - tx, y - ty); ctx.lineTo(x + tx, y + ty);
      }
      else if (e.shape === 'ring' && (e.arcAngle || 360) < 360) {
        const rx = e.width / 2, ry = e.height / 2, half = e.arcAngle / 2;
        const parameter = degrees => { const a = degrees * Math.PI / 180; return rx === 0 || ry === 0 ? a : Math.atan2(rx * Math.sin(a), ry * Math.cos(a)); };
        const start = parameter(e.arcRotation - half), finish = parameter(e.arcRotation + half);
        const sweep = ((finish - start) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2);
        if (!edge) ctx.moveTo(0, 0);
        ctx.ellipse(0, 0, rx, ry, 0, -start, -(start + sweep), true);
        if (!edge) { ctx.lineTo(0, 0); ctx.closePath(); ctx.fillStyle = '#87b9af12'; ctx.fill(); }
        ctx.stroke(); ctx.globalAlpha *= 0.45; ctx.beginPath();
        [start, start + sweep].forEach(a => { ctx.moveTo(0, 0); ctx.lineTo(rx * Math.cos(a), -ry * Math.sin(a)); });
      }
      else if (e.shape === 'circle' || e.shape === 'ring') ctx.ellipse(0, 0, e.width / 2, e.height / 2, 0, 0, Math.PI * 2);
      else if (!chosen && !(e.path && e.path.enabled)) {
        const a = e.angle * Math.PI / 180, length = 55 / zoom;
        ctx.moveTo(0, 0); ctx.lineTo(Math.cos(a) * length, -Math.sin(a) * length);
        if (e.spread < 360) [-0.5, 0.5].forEach(sign => { const angle = a + e.spread * Math.PI / 180 * sign; ctx.moveTo(0, 0); ctx.lineTo(Math.cos(angle) * length, -Math.sin(angle) * length); });
      }
      if (!edge && ['box', 'circle', 'ring'].includes(e.shape) && !(e.shape === 'ring' && (e.arcAngle || 360) < 360)) { ctx.fillStyle = '#87b9af12'; ctx.fill(); }
      ctx.stroke();
      if (chosen && directionMode(e) !== 'fixed' && !(e.path && e.path.enabled)) {
        const snapshot = activeBake(), samples = snapshot ? snapshot.particles.filter(p => p.emitterId === e.id && p.cycleIndex === 0) : [];
        const interval = Math.max(1, Math.ceil(samples.length / 8)), length = 14 / zoom;
        ctx.setLineDash([]); ctx.lineWidth = 1.2 / zoom; ctx.beginPath();
        for (let i = 0; i < samples.length; i += interval) {
          const p = samples[i], magnitude = Math.hypot(p.vx, p.vy), angle = magnitude > 1e-9 ? Math.atan2(p.vy, p.vx) : p.direction * Math.PI / 180;
          const x = p.sx + Math.cos(angle) * length, y = -p.sy - Math.sin(angle) * length, wing = 4 / zoom;
          ctx.moveTo(p.sx, -p.sy); ctx.lineTo(x, y);
          ctx.moveTo(x - Math.cos(angle - .5) * wing, y + Math.sin(angle - .5) * wing); ctx.lineTo(x, y); ctx.lineTo(x - Math.cos(angle + .5) * wing, y + Math.sin(angle + .5) * wing);
        }
        ctx.stroke();
      }
      if (chosen) window.ParticleEmissionGuides.draw(ctx, e, {pixelRatio: Math.min(2, window.devicePixelRatio || 1)});
      ctx.restore();
    }); ctx.restore();
  }
  function draw() {
    updateHandlePositions();
    const snapshot = activeBake();
    ctx.save(); ctx.fillStyle = project.background.color; ctx.fillRect(0, 0, stageW, stageH);
    if (!snapshot || (attachedMode() && !attachedFor())) {
      ctx.fillStyle = '#b7a293'; ctx.font = '13px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText(attachedMode() ? attachedError || '請檢查掛接設定' : liveError || '準備預覽…', stageW / 2, stageH / 2);
      ctx.restore(); $('stats').textContent = '請調整參數後重新預覽'; return;
    }
    ctx.translate(stageW / 2 + panX, stageH / 2 + panY); ctx.scale(zoom, zoom);
    const grid = 50;
    ctx.lineWidth = 1 / zoom; ctx.strokeStyle = '#8c98a412'; ctx.beginPath();
    const left = (-stageW / 2 - panX) / zoom, right = (stageW / 2 - panX) / zoom;
    const top = (-stageH / 2 - panY) / zoom, bottom = (stageH / 2 - panY) / zoom;
    for (let x = Math.floor(left / grid) * grid; x < right; x += grid) { ctx.moveTo(x, top); ctx.lineTo(x, bottom); }
    for (let y = Math.floor(top / grid) * grid; y < bottom; y += grid) { ctx.moveTo(left, y); ctx.lineTo(right, y); }
    ctx.stroke();
    const bg = project.background;
    if (bg.image) {
      const bitmap = imageFor(bg.image);
      const size = Core.backgroundSize(bg);
      if (bitmap.complete && bitmap.naturalWidth) ctx.drawImage(bitmap, bg.x - size.width / 2, -bg.y - size.height / 2, size.width, size.height);
    }
    const attached = attachedFor();
    (mode === 'live' ? project : snapshot.project).emitters.forEach(e => {
      if (!e.enabled || !(e.shape === 'outline' || e.path && e.path.enabled) || !e.outline || !e.outline.image || e.outline.showImage === false) return;
      const frame = attachedMode() ? attached && attached.emitterFrame(e.id, time) : null; if (attachedMode() && !frame) return;
      const bitmap = imageFor(e.outline.image); if (!bitmap.complete || !bitmap.naturalWidth) return;
      ctx.save(); if (frame) { const m = frame.matrix; ctx.transform(m.a, -m.c, -m.b, m.d, m.x, -m.y); }
      ctx.translate(e.x, -e.y); ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = .75;
      ctx.drawImage(bitmap, -e.width / 2, -e.height / 2, e.width, e.height); ctx.restore();
    });
    const particles = attached ? attached.sample(time) : mode === 'baked' && bakedPreview ? bakedPreview.sample(time) : Core.sample(snapshot, time); let visible = 0;
    const offsets = new Map(), hiddenEmitters = new Set(), previewMuted = previewMutedIds();
    if (mode === 'live') snapshot.project.emitters.forEach(old => {
      const current = project.emitters.find(e => e.id === old.id);
      if (!current || !current.enabled) hiddenEmitters.add(old.id);
      else offsets.set(old.id, {x: current.x - old.x, y: current.y - old.y});
    });
    for (const p of particles) {
      if (previewMuted.size && previewMuted.has(particleEmitterId(p))) continue;
      if (attached) {
        if (p.alpha <= .0001) continue;
        if (!p.image) {
          ctx.save(); ctx.strokeStyle = '#98afa4'; ctx.globalAlpha = .4; ctx.lineWidth = 1 / zoom; ctx.setLineDash([3 / zoom, 3 / zoom]); ctx.beginPath();
          for (let i = 0; i < p.vertices.length; i += 2) { if (!i) ctx.moveTo(p.vertices[i], -p.vertices[i + 1]); else ctx.lineTo(p.vertices[i], -p.vertices[i + 1]); }
          ctx.closePath(); ctx.stroke(); ctx.restore(); continue;
        }
        const texture = tinted(p.image, p.color, p.darkColor);
        ctx.save(); ctx.scale(1, -1);
        if (texture && window.ParticleSpineCanvasRenderer.draw(ctx, p, texture) && p.isParticle) visible++;
        ctx.restore();
        continue;
      }
      if (hiddenEmitters.has(p.emitterId)) continue;
      if (p.alpha <= 0.0001 || p.width <= 0 || p.height <= 0) continue;
      const texture = tinted(p.image, p.color); if (!texture) continue;
      visible++;
      ctx.save(); ctx.globalCompositeOperation = p.blend === 'additive' ? 'lighter' : 'source-over'; ctx.globalAlpha = p.alpha;
      const offset = offsets.get(p.emitterId) || {x: 0, y: 0};
      ctx.translate(p.x + offset.x, -p.y - offset.y); ctx.rotate(-p.rotation * Math.PI / 180);
      ctx.drawImage(texture, -p.width / 2, -p.height / 2, p.width, p.height); ctx.restore();
    }
    if (attached && showBones && !(bonePicker && bonePicker.active)) drawBones(attached);
    if (bonePicker && bonePicker.active) bonePicker.draw(ctx);
    else drawGizmos(mode === 'live' ? project : snapshot.project);
    ctx.restore();
    const statistics = mode === 'baked' && exported ? exported.stats : snapshot.stats;
    $('stats').textContent = (previewMuted.size ? (soloId ? '單獨顯示 · ' : '預覽隱藏 ' + previewMuted.size + ' 層 · ') : '') + '可見 ' + visible + ' · 骨骼 ' + statistics.bones + (statistics.keyframes ? ' · KEY ' + statistics.keyframes.toLocaleString() + ' · JSON ' + (statistics.jsonBytes / 1024).toFixed(0) + ' KB' : ' · ' + snapshot.fps + ' FPS 烘焙');
  }
  function previewMutedIds() {
    if (soloId && !project.emitters.some(e => e.id === soloId)) soloId = null;
    for (const id of previewHidden) if (!project.emitters.some(e => e.id === id)) previewHidden.delete(id);
    return soloId ? new Set(project.emitters.filter(e => e.id !== soloId).map(e => e.id)) : previewHidden;
  }
  function particleEmitterId(p) {
    if (p.emitterId) return p.emitterId;
    const match = typeof p.slotName === 'string' && /^em_(.+)_p\d+_slot$/.exec(p.slotName);
    return match ? match[1] : null;
  }
  function drawBones(attached) {
    const parent = (integration.settings.emitterParents || {})['em_' + selectedId] || integration.settings.parentBone;
    ctx.save(); ctx.globalCompositeOperation = 'source-over'; ctx.lineWidth = 1 / zoom; ctx.setLineDash([]);
    const bones = attached.bones(time), byName = new Map(bones.map(b => [b.name, b]));
    bones.filter(b => b.active).forEach(b => {
      const selected = b.name === parent, ancestor = byName.get(b.parentName);
      ctx.globalAlpha = selected ? .95 : .45; ctx.strokeStyle = selected ? '#b6f2d2' : '#80b6ba'; ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath(); if (ancestor) { ctx.moveTo(ancestor.x, -ancestor.y); ctx.lineTo(b.x, -b.y); }
      ctx.moveTo(b.x, -b.y); ctx.lineTo(b.endX, -b.endY); ctx.stroke();
      ctx.beginPath(); ctx.arc(b.x, -b.y, (selected ? 4 : 2.5) / zoom, 0, Math.PI * 2); ctx.fill();
      if (selected) { ctx.font = (11 / zoom) + 'px sans-serif'; ctx.textAlign = 'left'; ctx.fillText(b.name, b.x + 8 / zoom, -b.y - 7 / zoom); }
    }); ctx.restore();
  }
  function pathScene(selected) {
    const owner = project, cursor = time, wasPlaying = playing, attached = attachedFor();
    const frame = attached && attached.emitterFrame(selected.id, cursor);
    if (attachedMode() && !frame) throw new Error(attachedError || '目前掛接骨骼未啟用，請先檢查掛接設定。');
    const parent = frame ? {...frame.matrix} : {a: 1, b: 0, c: 0, d: 1, x: 0, y: 0};
    const matrix = {...parent, ...AttachmentPreview.point(parent, selected)};
    const original = attached ? attached.rig.sample(cursor) : [];
    const bg = {...project.background}, references = [], bounds = [], watching = new Set();
    let disposed = false;
    const redraw = () => { if (!disposed && pathEditor) pathEditor.refresh(); };
    function bitmapFor(image) {
      const bitmap = imageFor(image);
      if (!bitmap.complete && !watching.has(bitmap)) { watching.add(bitmap); bitmap.addEventListener('load', redraw); }
      return bitmap;
    }
    project.emitters.forEach(e => {
      if (!e.outline || !e.outline.image || (e !== selected && (!e.enabled || !(e.shape === 'outline' || e.path && e.path.enabled) || e.outline.showImage === false))) return;
      const binding = attached && attached.emitterFrame(e.id, cursor); if (attachedMode() && !binding) return;
      const basis = binding ? {...binding.matrix} : {a: 1, b: 0, c: 0, d: 1, x: 0, y: 0};
      const origin = {...basis, ...AttachmentPreview.point(basis, e)};
      references.push({image: e.outline.image, width: e.width, height: e.height, matrix: origin, selected: e === selected});
      if (e === selected) for (const [x, y] of [[-e.width / 2, -e.height / 2], [-e.width / 2, e.height / 2], [e.width / 2, e.height / 2], [e.width / 2, -e.height / 2]]) bounds.push(AttachmentPreview.point(origin, {x, y}));
      bitmapFor(e.outline.image);
    });
    references.sort((a, b) => Number(a.selected) - Number(b.selected));
    const openingReference = references.find(reference => reference.selected);
    function setReference(outline, width, height) {
      if (disposed) return;
      const existing = references.findIndex(reference => reference.selected);
      if (existing >= 0) references.splice(existing, 1);
      bounds.length = 0;
      const reference = outline ? outline.image && {image: outline.image, width, height, matrix, selected: true} : openingReference;
      if (reference) {
        references.push(reference);
        for (const [x, y] of [[-reference.width / 2, -reference.height / 2], [-reference.width / 2, reference.height / 2], [reference.width / 2, reference.height / 2], [reference.width / 2, -reference.height / 2]]) bounds.push(AttachmentPreview.point(reference.matrix, {x, y}));
        bitmapFor(reference.image);
      }
      redraw();
    }
    if (bg.image) bitmapFor(bg.image);
    original.forEach(state => { if (state.image) bitmapFor(state.image); });
    const description = attached ? '掛接 ' + frame.parentBone + ' · ' + attached.timeline.animationName + ' · 定格 ' + cursor.toFixed(2) + ' 秒' : '背景與物件以原比例對齊 · 發射器紅點為路徑原點';
    $('pathSceneInfo').textContent = description;
    playing = false; updatePlayButton(); refreshFlowUi();
    return {matrix, bounds, setReference,
      draw(context) {
        context.save(); context.globalCompositeOperation = 'source-over';
        if (bg.image) {
          const bitmap = bitmapFor(bg.image), size = Core.backgroundSize(bg);
          if (bitmap.complete && bitmap.naturalWidth) context.drawImage(bitmap, bg.x - size.width / 2, -bg.y - size.height / 2, size.width, size.height);
        }
        for (const state of original) {
          if (state.alpha <= .0001) continue;
          const texture = state.image ? tinted(state.image, state.color, state.darkColor) : null;
          if (texture) { context.save(); context.scale(1, -1); window.ParticleSpineCanvasRenderer.draw(context, state, texture); context.restore(); }
          else if (state.vertices && state.vertices.length >= 6) {
            context.save(); context.strokeStyle = '#87a9a0'; context.globalAlpha = .4; context.beginPath();
            for (let i = 0; i < state.vertices.length; i += 2) { if (i) context.lineTo(state.vertices[i], -state.vertices[i + 1]); else context.moveTo(state.vertices[i], -state.vertices[i + 1]); }
            context.closePath(); context.stroke(); context.restore();
          }
        }
        for (const reference of references) {
          const bitmap = bitmapFor(reference.image); if (!bitmap.complete || !bitmap.naturalWidth) continue;
          const m = reference.matrix; context.save(); context.transform(m.a, -m.c, -m.b, m.d, m.x, -m.y); context.globalAlpha = reference.selected ? .8 : .45;
          context.drawImage(bitmap, -reference.width / 2, -reference.height / 2, reference.width, reference.height); context.restore();
        }
        context.restore();
      },
      dispose() {
        if (disposed) return; disposed = true; watching.forEach(bitmap => bitmap.removeEventListener('load', redraw)); watching.clear();
        if (project === owner) { playing = wasPlaying; updatePlayButton(); refreshFlowUi(); }
      }
    };
  }
  function syncTimeline() {
    const duration = previewDuration(), fps = activeFps();
    time = clamp(time, 0, duration);
    $('timeline').max = Math.round(duration * fps); $('timeline').step = 1;
    $('timeline').value = Math.round(time * fps);
    $('timeline').setAttribute('aria-valuetext', time.toFixed(2) + ' 秒');
    $('timeLabel').textContent = (currentFlowBake() ? phase.toUpperCase() + ' · ' : '') + time.toFixed(2) + ' / ' + duration.toFixed(2) + ' 秒 · ' + Math.round(time * fps) + ' 幀';
    if (timelineView) timelineView.refresh();
    if (emitterLanes) emitterLanes.refresh();
  }
  function updatePlayButton() {
    $('playButton').setAttribute('aria-label', playing ? '暫停' : '播放');
    $('playButton').innerHTML = playing ? '<svg aria-hidden="true" viewBox="0 0 20 20"><path d="M6 4h3v12H6z M12 4h3v12h-3z"/></svg>' : '<svg aria-hidden="true" viewBox="0 0 20 20"><path d="m7 4 9 6-9 6Z"/></svg>';
  }
  let previousTime = 0;
  function animate(stamp) {
    const delta = previousTime ? Math.min(0.08, (stamp - previousTime) / 1000) : 0; previousTime = stamp;
    const snapshot = activeBake();
    if (playing && snapshot && !document.hidden) {
      if (attachedMode() && !attachedFor()) { playing = false; updatePlayButton(); }
      else {
      const group = currentFlowBake();
      if (group) {
        const durations = Object.fromEntries(['in', 'loop', 'out'].map(kind => { const attached = attachedFor(kind); return [kind, attached ? attached.timeline.duration : group.phases[kind].duration]; }));
        const next = FlowPlayback.advance({phase, time, playing, sequence, exitRequested}, delta, durations);
        const switched = next.phase !== phase, wasPlaying = playing;
        phase = next.phase; time = next.time; playing = next.playing; sequence = next.sequence; exitRequested = next.exitRequested;
        if (switched && baked && exported) bakedPreview = compileBakedPreview(exported, baked, flowBaked);
        if (switched || wasPlaying !== playing) { refreshFlowUi(); refreshAttachmentPreview(); updatePlayButton(); queueDraft(); }
      } else {
        time += delta;
        const duration = previewDuration();
        if (time >= duration) {
          if (snapshot.loop) time %= duration;
          else { time = duration; playing = false; updatePlayButton(); }
        }
      }
      }
    }
    syncTimeline(); draw(); requestAnimationFrame(animate);
  }

  function drawCurves() {
    if (curveEditor) curveEditor.refresh();
    if (gradientEditor) gradientEditor.refresh();
    if (lookPresetsUi) lookPresetsUi.refresh();
  }

  function download(data, name, type) {
    const blob = new Blob([data], {type}); const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  function saveProject() {
    try { download(Storage.serialize(project, baked ? baked.project : null, viewState(), integration), safeName() + '.particle.json', 'application/json'); queueDraft(); notify('已開始下載專案檔，包含參數、素材與烘焙快照。'); return true; }
    catch (error) { notify(error.message, true); return false; }
  }
  async function bakeNow() {
    if (busy) return; busy = true; updateBakeStatus();
    await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 0)));
    try {
      const nextFlow = project.flow.enabled ? Core.bakeFlow(project) : null;
      const nextBake = nextFlow ? nextFlow.phases.loop : Core.bake(project);
      const nextExport = nextFlow ? Core.exportFlow(nextFlow, effectiveSpineVersion()) : Core.exportSpine(nextBake, effectiveSpineVersion());
      const nextPreview = compileBakedPreview(nextExport, nextBake, nextFlow);
      flowBaked = nextFlow; baked = nextBake; exported = nextExport; bakedPreview = nextPreview; bakedRevision = revision; mode = 'baked';
      $('appStatus').textContent = '已烘焙 ' + exported.stats.bones + ' 根骨骼 · ' + exported.stats.keyframes.toLocaleString() + ' KEY';
      if (exported.stats.warnings.length) notify(exported.stats.warnings.join(' '));
      else notify('烘焙完成，可以輸出 Spine ' + nextExport.json.skeleton.spine + '。');
      queueDraft();
    } catch (error) { notify(error.message, true); }
    finally { busy = false; updateBakeStatus(); }
  }
  function renderBakeCheck() {
    if (!$('bakeCheckDialog').open) return;
    const profile = Core.qualityProfile(project);
    $('bakeQuality').value = profile.name;
    $('bakeQuality').disabled = busy;
    $('bakeCheckBake').disabled = busy;
    const t = profile.tolerances;
    $('bakeQualityHint').textContent = profile.label + ' · 局部曲線精簡容許：位移 ' + t.position + ' px、旋轉 ' + t.rotation + '°。不改變亂數種子與生命週期；最終 KEY 數依效果而定。';
    const metrics = (id, entries) => {
      const container = $(id); container.replaceChildren();
      entries.forEach(([label, value]) => {
        const node = document.createElement('div'); node.className = 'bake-cost-metric';
        const text = document.createElement('span'), number = document.createElement('strong');
        text.textContent = label; number.textContent = typeof value === 'number' ? value.toLocaleString() : value;
        node.append(text, number); container.append(node);
      });
    };
    try {
      const estimate = Core.estimateCost({...project, spineVersion: effectiveSpineVersion()});
      metrics('bakeCostEstimate', [['粒子骨骼', estimate.bones], ['粒子插槽', estimate.slots], ['補採樣前估算上限', estimate.estimatedSamples], ['精簡前 KEY 估算', estimate.estimatedDenseKeyframes]]);
      $('bakeCostWarning').textContent = (estimate.flow ? '三段共用粒子池。' : '') + '估算未含曲線補採樣，最終 KEY 數請看試烘焙。' + (estimate.budgetRisk ? '取樣量偏高，建議減少數量、幀率或生命長度。' : '') + (estimate.warnings || []).join(' ');
    } catch (error) { $('bakeCostEstimate').textContent = error.message; $('bakeCostWarning').textContent = ''; }
    if (exported && baked && bakedRevision === revision) {
      const stats = exported.stats, reduction = stats.denseKeyframes ? (100 * (1 - stats.keyframes / stats.denseKeyframes)).toFixed(1) + '%' : '—';
      const bytes = stats.jsonBytes === undefined ? new TextEncoder().encode(JSON.stringify(exported.json)).length : stats.jsonBytes;
      metrics('bakeCostActual', [['實際 KEY 數', stats.keyframes], ['KEY 減少比例', reduction], ['粒子 JSON', bytes < 1024 * 1024 ? (bytes / 1024).toFixed(1) + ' KiB' : (bytes / (1024 * 1024)).toFixed(2) + ' MiB'], ['輸出版本 / 品質', Core.spineProfile(exported.json.skeleton.spine).family + ' / ' + (stats.qualityLabel || '標準')]]);
    } else {
      const empty = document.createElement('p'); empty.className = 'bake-cost-empty';
      empty.textContent = busy ? '正在烘焙，完成後顯示實際數據…' : baked ? '設定已修改，請試烘焙取得本次結果。' : '試烘焙後會顯示 KEY 數與 JSON 大小。';
      $('bakeCostActual').replaceChildren(empty);
    }
  }
  function wireBakeCheck() {
    $('bakeCheckButton').addEventListener('click', () => { $('bakeCheckDialog').showModal(); renderBakeCheck(); });
    ['bakeCheckClose', 'bakeCheckDone'].forEach(id => $(id).addEventListener('click', () => $('bakeCheckDialog').close()));
    $('bakeQuality').addEventListener('change', () => {
      if (busy || !['fine', 'standard', 'compact'].includes($('bakeQuality').value)) return;
      project.bakeQuality = $('bakeQuality').value; changed(); renderBakeCheck();
    });
    $('bakeCheckBake').addEventListener('click', bakeNow);
  }
  function bakeFresh() { return !!baked && revision === bakedRevision && !!exported; }
  // Exporting always uses the current parameters: bake first when anything changed.
  async function ensureBaked() {
    if (busy) return false;
    if (bakeFresh()) return true;
    await bakeNow();
    return bakeFresh();
  }
  async function exportZip() {
    if (!(await ensureBaked())) return;
    if (integration && integration.settings.enabled !== false) { exportMergedZip(); return; }
    if (!bakeFresh()) { notify('烘焙未完成，無法輸出。', true); return; }
    try {
      const name = safeName();
      const entries = standaloneEntries(name, exported, baked, flowBaked, project);
      download(Zip.create(entries), name + '_spine' + Core.spineProfile(exported.json.skeleton.spine).family + '.zip', 'application/zip');
      notify('已開始下載 ZIP：Spine JSON、圖片、編輯專案與匯入說明。');
    } catch (error) { notify(error.message, true); }
  }
  // Files of one standalone Spine package; prefix places them in a sub-folder.
  function standaloneEntries(name, exp, snapshot, flowSnapshot, sourceProject, prefix = '', session = integration) {
    const animationGuide = flowSnapshot ? ['in', 'loop', 'out'].map(kind => {
      const item = exp.manifest.phases[kind];
      return kind.toUpperCase() + '：' + item.animationName + '，' + item.duration + ' 秒（' + (item.loop ? '反覆播放' : '播放一次') + '）';
    }).join('；') + '。先播 IN，再反覆 LOOP；需要結束時，等 LOOP 完整一輪結束後播放 OUT。' : '播放 effect 動畫。此動畫的循環設定：' + (snapshot.loop ? '循環；請開啟 Spine 循環播放' : '單次') + '。';
    const entries = [
      {name: name + '.json', data: JSON.stringify(exp.json)},
      {name: name + '.particle.json', data: Storage.serialize(sourceProject, snapshot.project, viewState(), session)},
      {name: '匯入說明.txt', data: 'Particle Studio 原創粒子工具\n目標：Spine Editor ' + exp.json.skeleton.spine + '\n\n1. 解壓縮此 ZIP。\n2. 在 Spine ' + exp.json.skeleton.spine + ' 使用 File → Import Data，選擇 ' + name + '.json。\n3. Images 路徑指向同層 images/。\n4. ' + animationGuide + '\n5. 存為新的 .spine 專案。需合併到既有動畫時，可透過 Import Project 匯入此專案。\n\n' + name + '.particle.json 是本工具的編輯專案，不是 Spine skeleton。\n背景參考圖不匯出到 Spine；圖集請在 Spine 匯出時建立。\n\n烘焙：' + snapshot.fps + ' FPS\n骨骼：' + exp.stats.bones + '；關鍵幀：' + exp.stats.keyframes + '\n' + exp.stats.warnings.join('\n')}
    ];
    if (flowSnapshot) entries.push({name: '動畫段落.json', data: JSON.stringify(exp.manifest, null, 2)});
    exp.images.forEach(image => { entries.push({name: 'images/' + image.name, data: Zip.decodeDataUrl(image.dataUrl || builtinImages.glow.dataUrl)}); });
    return prefix ? entries.map(entry => ({...entry, name: prefix + entry.name})) : entries;
  }
  async function runBatchExport(jobs, progress) {
    if (busy) throw new Error('正在烘焙，請稍候再試。');
    if (integration && integration.settings.enabled !== false) throw new Error('掛接既有骨架時無法批次輸出。');
    const Batch = window.ParticleBatchExport, presets = window.ParticleLookPresets;
    const base = safeName(), entries = [];
    busy = true; updateBakeStatus();
    try {
      for (let index = 0; index < jobs.length; index++) {
        const job = jobs[index], label = Batch.variantLabel(job.variant, presets) + ' · Spine ' + Core.spineProfile(job.version).family;
        progress(index + 1, jobs.length, label);
        await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 0)));
        const variant = Batch.applyVariant(project, job.variant, presets);
        variant.spineVersion = Core.spineProfile(job.version).version;
        const flow = variant.flow.enabled ? Core.bakeFlow(variant) : null;
        const snapshot = flow ? flow.phases.loop : Core.bake(variant);
        const exp = flow ? Core.exportFlow(flow, variant.spineVersion) : Core.exportSpine(snapshot, variant.spineVersion);
        const stem = jobs.some(other => other.variant !== job.variant) || job.variant.kind !== 'original' ? base + '_' + Batch.variantSlug(job.variant) : base;
        const folder = stem + '_spine' + Core.spineProfile(job.version).family + '/';
        entries.push(...standaloneEntries(stem, exp, snapshot, flow, variant, folder));
      }
      const fileName = base + '_批次' + jobs.length + '組.zip';
      download(Zip.create(entries), fileName, 'application/zip');
      notify('已開始下載批次 ZIP：' + jobs.length + ' 組，各自一個資料夾。');
      return {fileName};
    } finally { busy = false; updateBakeStatus(); }
  }
  function exportMergedZip() {
    if (!baked || revision !== bakedRevision || !exported || busy) { notify('請先更新粒子烘焙再輸出追加包。', true); return; }
    try {
      const options = flowBaked ? attachmentUi.validateFlowOptions(exported) : attachmentUi.validateOptions(exported, baked.duration);
      const emitterRoots = new Set(exported.json.bones.filter(bone => /^em_/.test(bone.name)).map(bone => bone.name));
      for (const field of ['emitterParents', 'emitterLayers']) if (options[field]) {
        options[field] = Object.fromEntries(Object.entries(options[field]).filter(([name]) => emitterRoots.has(name)));
      }
      const base = effectiveIntegration();
      const result = flowBaked ? SpineMerge.mergeFlow(base.json, exported, options) : SpineMerge.merge(base.json, exported, options);
      const receipt = EffectUpdate.createReceipt(base.json, result, options);
      const animationGuide = result.manifest.phases ? ['in', 'loop', 'out'].map(kind => {
        const item = result.manifest.phases[kind];
        return kind.toUpperCase() + ' → ' + item.animationName + '，' + item.startTime + '–' + item.endTime + ' 秒' + (item.loop ? '（反覆播放）' : '（播放一次）');
      }).join('\n') + '\n請在 LOOP 完整一輪結束後接 OUT；任意時點切换需另外設定動畫混合。' : '播放「' + result.manifest.animationName + '」；粒子段落 ' + result.manifest.startTime + '–' + result.manifest.endTime + ' 秒。';
      let stem = integration.fileName.replace(/\.json$/i, '').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/^[. ]+|[. ]+$/g, '').slice(0, 64) || 'spine';
      if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(stem)) stem = 'spine_' + stem;
      const name = stem + '_particles';
      const text = 'Particle Studio v1.26 · 既有 Spine ' + result.json.skeleton.spine + (integration.update && integration.update.mode === 'replace' ? ' 效果更新包\n\n' : ' 追加包\n\n') +
        '1. 保留原 .spine 工程及其全部素材。此包不包含原角色的圖片或音效。\n' +
        '2. 把 new_images/ 裡的「' + result.manifest.imageDirectory + '」資料夾，複製進原工程的 Images 根目錄。\n' +
        '   原 JSON Images 設定：' + result.manifest.originalImagesPath + '\n' +
        '3. 將 ' + name + '.json 放在原骨架 JSON 的同層，維持原 Images 相對路徑。\n' +
        '4. 用 Spine File → Import Data 匯入，或以附帶的「Spine 工程轉換」轉成新的 .spine。\n' +
        '5. 依下方動畫段落播放，檢查原角色動態與新增粒子，再另存新的工程。\n\n' + animationGuide + '\n\n' +
        '父骨骼：' + result.manifest.parentBone + '\n' +
        '新增群組：' + result.manifest.namespace + '\n新增骨骼：' + result.stats.addedBones + '；新增插槽：' + result.stats.addedSlots + '\n\n' +
        '掛接使用骨骼的局部座標，會隨父骨骼變形。工具的「掛接預覽」會播放原骨架完整動畫，並依開始時間顯示粒子；「粒子單獨」使用粒子自己的時間。\n' +
        '原圖片或 Atlas 可在掛接設定中載入供預覽，隨 .particle.json 保存；追加包只輸出新增粒子 PNG，原角色素材沿用原 Images 目錄。\n' +
        'JSON 往返只保留匯出的資料；未匯出的編輯器資料無法由本工具復原。\n' +
        '再次調整時，保留「效果更新記錄.json」。先開啟粒子編輯專案，再載入 Spine 修改後的骨架 JSON 與這份記錄，選擇更新此效果。新素材請覆蓋對應群組的圖片；JSON 與圖片需使用同一次輸出。\n' +
        result.warnings.join('\n');
      const entries = [
        {name: name + '.json', data: JSON.stringify(result.json)},
        {name: name + '.particle.json', data: Storage.serialize(project, baked.project, viewState(), integration)},
        {name: '追加清單.json', data: JSON.stringify(result.manifest, null, 2)},
        {name: '效果更新記錄.json', data: JSON.stringify(receipt, null, 2)},
        {name: '追加說明.txt', data: text}
      ];
      result.images.forEach(asset => entries.push({name: 'new_images/' + asset.name, data: Zip.decodeDataUrl(asset.dataUrl || builtinImages.glow.dataUrl)}));
      download(Zip.create(entries), name + (integration.update && integration.update.mode === 'replace' ? '_update.zip' : '_append.zip'), 'application/zip');
      notify('已開始下載：合併骨架、粒子新素材與效果更新記錄。原工程請保留並另存新版本。');
    } catch (error) { notify(error.message, true); }
  }
  async function loadImage(file, includeSourceSize) {
    if (!file || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error('請選擇 PNG、JPEG 或 WebP 圖片。');
    if (file.size > 8 * 1024 * 1024) throw new Error('圖片超過 8 MB，請先縮小素材。');
    const source = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('無法讀取圖片。')); reader.readAsDataURL(file); });
    const image = await new Promise((resolve, reject) => { const i = new Image(); i.onload = () => resolve(i); i.onerror = () => reject(new Error('圖片無法解碼。')); i.src = source; });
    const ratio = Math.min(1, 2048 / Math.max(image.naturalWidth, image.naturalHeight));
    const surface = document.createElement('canvas'); surface.width = Math.max(1, Math.round(image.naturalWidth * ratio)); surface.height = Math.max(1, Math.round(image.naturalHeight * ratio));
    surface.getContext('2d').drawImage(image, 0, 0, surface.width, surface.height);
    const result = {name: file.name, mime: 'image/png', width: surface.width, height: surface.height, dataUrl: surface.toDataURL('image/png')};
    if (includeSourceSize === true) { result.sourceWidth = image.naturalWidth; result.sourceHeight = image.naturalHeight; }
    if (result.dataUrl.length > 4 * 1024 * 1024 * 4 / 3) throw new Error('轉換後的 PNG 超過 4 MB，請縮小素材。');
    return result;
  }
  function fitBackgroundView() {
    const bg = project.background, size = Core.backgroundSize(bg); if (!size) return;
    // Change the shared camera, keeping PNG pixels and particle coordinates in one space.
    const fit = clamp(Math.min(stageW / size.width, stageH / size.height) * .9, .05, 2);
    zoom = clamp(Math.floor(fit * 100) / 100, .05, 2);
    panX = -bg.x * zoom; panY = bg.y * zoom;
    renderGlobals(); queueDraft();
  }
  // Keep the world point under (screenX, screenY) fixed while zooming.
  function zoomAt(next, screenX, screenY) {
    if (!Number.isFinite(next) || next === zoom) return;
    const worldX = (screenX - stageW / 2 - panX) / zoom, worldY = (screenY - stageH / 2 - panY) / zoom;
    zoom = next; panX = screenX - stageW / 2 - worldX * zoom; panY = screenY - stageH / 2 - worldY * zoom;
    $('zoom').value = Math.round(zoom * 100); $('zoomLabel').textContent = Math.round(zoom * 100) + '%'; queueDraft();
  }
  function focusSelectedEmitter() {
    const e = emitter(); if (!e) return;
    const attached = attachedMode() ? attachedFor() : null;
    const point = attached ? attached.emitterPoint(e.id, e, time) : e;
    if (!point) { notify('目前無法定位這個發射器。', true); return; }
    panX = -point.x * zoom; panY = point.y * zoom; queueDraft();
  }
  function freshId() { return 'e_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6); }
  const BUILTIN_EFFECTS = [
    {id: 'glow', name: '柔光粒子', description: '柔和光點，適合光塵與氛圍', symbol: '✦', gradient: 'radial-gradient(circle,#fff8dc,#ffc13b 45%,#3a2a12)'},
    {id: 'sparks', name: '迸射火花', description: '短促爆發的火花', symbol: '✸', gradient: 'linear-gradient(135deg,#fff2b0,#f34b23 70%,#4a1420)'},
    {id: 'coins', name: '金幣噴發', description: '金幣向上噴出再落下', symbol: '◉', gradient: 'linear-gradient(135deg,#ffe58a,#e8a018 70%,#3a2a12)'},
    {id: 'bubbles', name: '漂浮氣泡', description: '緩慢上飄的氣泡', symbol: '○', gradient: 'linear-gradient(135deg,#f1fcff,#4b99ff 70%,#1b2550)'}
  ];
  function builtinEmitter(preset, id = freshId()) {
    const names = Object.fromEntries(BUILTIN_EFFECTS.map(item => [item.id, item.name]));
    if (!names[preset]) throw new Error('找不到內建效果：' + preset);
    const e = Core.createEmitter(id, names[preset], preset);
    if (preset !== 'glow') e.image = clone(builtinImages[preset]);
    return e;
  }
  function insertEmitter(e) {
    if (project.emitters.length >= 8) throw new Error('每個專案最多 8 個發射器。');
    historyBegin('command');
    try {
      const index = Math.max(0, project.emitters.findIndex(item => item.id === selectedId));
      project.emitters.splice(index, 0, e); selectedId = e.id; changed(); renderEmitters(); renderInspector();
    } finally { historyEnd(); }
  }
  function addEmitter(preset = 'glow') {
    if (project.emitters.length >= 8) { notify('每個專案最多 8 個發射器。', true); return; }
    try { insertEmitter(builtinEmitter(preset)); } catch (error) { notify(error.message, true); }
  }
  function setTab(tab) {
    const panels = Array.from(document.querySelectorAll('[data-panel]'));
    if (!panels.some(panel => panel.dataset.panel === tab)) return;
    const scroller = document.querySelector('.inspector-scroll'), previous = panels.find(panel => !panel.hidden);
    if (scroller && previous) inspectorScrollPositions.set(previous.dataset.panel, scroller.scrollTop);
    document.querySelectorAll('[data-tab]').forEach(button => { const active = button.dataset.tab === tab; button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active)); });
    panels.forEach(panel => { panel.hidden = panel.dataset.panel !== tab; });
    if (scroller) scroller.scrollTop = inspectorScrollPositions.get(tab) || 0;
    drawCurves();
  }

  async function adopt(parsed) {
    if (bonePicker) bonePicker.cancel();
    historyEnd();
    outlineRequest++; backgroundRequest++; textureRequest++;
    let nextLive = null, nextLiveFlow = null, nextError = '';
    const nextPhase = parsed.view && ['in', 'loop', 'out'].includes(parsed.view.phase) ? parsed.view.phase : 'loop';
    try { nextLiveFlow = parsed.project.flow.enabled ? Core.bakeFlow(parsed.project) : null; nextLive = nextLiveFlow ? nextLiveFlow.phases.loop : Core.bake(parsed.project); } catch (error) { nextError = error.message; }
    let nextBaked = null, nextFlow = null, nextExport = null, nextPreview = null;
    if (parsed.bakedProject) {
      nextFlow = parsed.bakedProject.flow.enabled ? Core.bakeFlow(parsed.bakedProject) : null;
      nextBaked = nextFlow ? nextFlow.phases.loop : Core.bake(parsed.bakedProject);
      const version = effectiveSpineVersion(parsed.project, parsed.integration || null);
      nextExport = nextFlow ? Core.exportFlow(nextFlow, version) : Core.exportSpine(nextBaked, version);
      nextPreview = compileBakedPreview(nextExport, nextBaked, nextFlow, nextPhase);
    }
    integration = parsed.integration || null;
    previewHidden.clear(); soloId = null;
    imageCache.clear(); tintCache.clear();
    attachedCache.clear();
    project = parsed.project; liveFlowBake = nextLiveFlow; liveBake = nextLive; liveError = nextError; flowBaked = nextFlow; baked = nextBaked; exported = nextExport; bakedPreview = nextPreview; selectedId = project.emitters[0].id;
    preloadParticleImages();
    phase = nextPhase; stopSequence();
    revision = 1; bakedRevision = nextBaked && simulationSignature(nextBaked.project) === simulationSignature(project) ? 1 : -1;
    const view = parsed.view || {}; time = view.time || 0; zoom = view.zoom || 1; panX = view.panX || 0; panY = view.panY || 0; mode = view.mode === 'baked' && baked ? 'baked' : 'live';
    previewAttached = view.previewAttached !== false; showBones = view.showBones !== false; previewSkin = view.skinName || '';
    renderGlobals(); renderEmitters(); renderInspector(); updateBakeStatus();
    historyGroup = null;
    if (history) history.reset(historyState());
  }
  function captureInterfaceDefaults() {
    initialInterface = {
      fields: Array.from(document.querySelectorAll('input:not([type="file"]),select,textarea')).map(node => ({
        node, value: node.value, checked: node.checked,
        options: node.tagName === 'SELECT' ? Array.from(node.options, option => option.cloneNode(true)) : null
      })),
      details: Array.from(document.querySelectorAll('details')).map(node => ({node, open: node.open}))
    };
  }
  function restoreInterfaceDefaults() {
    if (initialInterface) {
      for (const {node, value, checked, options} of initialInterface.fields) {
        if (options) node.replaceChildren(...options.map(option => option.cloneNode(true)));
        node.value = value;
        if (node.type === 'checkbox' || node.type === 'radio') node.checked = checked;
      }
      for (const {node, open} of initialInterface.details) node.open = open;
    }
    document.querySelectorAll('input[type="file"]').forEach(input => { input.value = ''; });
    document.querySelectorAll('[data-panel] .inspector-section').forEach(section => setSectionCollapsed(section, false, false));
    try { localStorage.removeItem(SECTION_KEY); } catch (_) { /* optional layout preference */ }
    setTab('basic'); inspectorScrollPositions.clear();
    document.querySelectorAll('.inspector-scroll,.emitter-list,.timeline-panel').forEach(node => { node.scrollTop = 0; node.scrollLeft = 0; });
  }
  async function resetProject() {
    if (busy || resettingProject) return false;
    resettingProject = true; updateBakeStatus();
    try {
      historyEnd();
      if (pathEditor) pathEditor.close();
      if (bonePicker) bonePicker.cancel();
      if (libraryUi) libraryUi.close();
      if (textureUi) textureUi.invalidate();
      document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
      clearTimeout(liveTimer); clearTimeout(draftTimer); clearTimeout(messageTimer);
      liveTimer = draftTimer = messageTimer = null;
      projectRequest++;
      interaction = null; pathGizmoCache.clear(); updateBaseCache = null;
      priorAssets = priorSource = null;
      await adopt({project: createInitialProject('未命名專案'), bakedProject: null, integration: null,
        view: {time: 0, mode: 'live', zoom: 1, panX: 0, panY: 40, previewAttached: true, showBones: true, skinName: '', phase: 'loop'}});
      playing = true; previousTime = 0;
      restoreInterfaceDefaults();
      renderGlobals(); renderEmitters(); renderInspector(); updateBakeStatus(); updatePlayButton(); syncTimeline(); draw();
      try {
        await saveDraftSnapshot(JSON.parse(Storage.serialize(project, null, viewState(), null)));
        $('appStatus').textContent = '新專案已建立 · 初始設定已保存';
        notify('已重設介面並建立新專案，可直接開始編輯。');
      } catch (error) {
        $('appStatus').textContent = '新專案已建立 · 請手動儲存';
        notify('新專案已建立，但本機草稿保存失敗。請按「儲存專案」保存。', true);
      }
      return true;
    } catch (error) {
      notify('無法建立新專案：' + error.message, true); return false;
    } finally { resettingProject = false; updateBakeStatus(); }
  }
  function wireNumberScrub() {
    let gesture = null, suppressClick = null;
    const modifier = event => event.altKey ? 'alt' : event.shiftKey ? 'shift' : 'none';
    const bound = (input, name, fallback) => {
      const raw = input.getAttribute(name); return raw === null || raw.trim() === '' ? fallback : Number(raw);
    };
    function finish(cancel) {
      const current = gesture; if (!current) return; gesture = null;
      current.input.classList.remove('scrubbing'); document.body.classList.remove('number-scrubbing');
      if (current.active) {
        suppressClick = current.input;
        if (cancel) {
          if (current.restore) current.restore();
          else current.source[current.key] = current.sourceValue;
          current.input.value = current.text;
          if (current.input.dataset.field) syncEmitterPeers(current.input, current.source);
          if (current.affectsParticles === false) queueDraft(); else changed();
          mode = current.mode;
          try { if (baked && simulationSignature(Core.normalizeProject(project)) === simulationSignature(baked.project)) bakedRevision = revision; } catch (_) {}
          renderEmitters(); drawCurves(); updateBakeStatus();
        } else current.input.dispatchEvent(new Event('change', {bubbles: true}));
        refreshLive(); queueDraft();
      }
      try { if (current.input.hasPointerCapture(current.pointerId)) current.input.releasePointerCapture(current.pointerId); } catch (_) {}
    }
    document.querySelectorAll('input[type="number"]').forEach(input => {
      input.classList.add('number-scrubbable');
      input.title = (input.title ? input.title + '；' : '') + '按住左右拖曳調值；Shift 加速、Alt 微調；點一下可直接輸入';
      input.addEventListener('pointerdown', event => {
        if (event.button !== 0 || event.pointerType === 'touch' || input.disabled || input.readOnly) return;
        const rect = input.getBoundingClientRect();
        // Keep the native spinner arrows available at the right edge.
        if (event.clientX >= rect.right - 18) return;
        const value = input.valueAsNumber; if (!Number.isFinite(value)) return;
        let custom = null;
        if (typeof curveEditor !== 'undefined' && curveEditor) custom = curveEditor.bindingFor(input);
        if (!custom && typeof gradientEditor !== 'undefined' && gradientEditor) custom = gradientEditor.bindingFor(input);
        if (!custom && typeof pathEditor !== 'undefined' && pathEditor) custom = pathEditor.bindingFor(input);
        if (!custom && textureUi) custom = textureUi.bindingFor(input);
        if (!custom && input.id === 'outlineThreshold') { const original = input.value, source = {get value() { return input.valueAsNumber; }, set value(value) { input.value = value; }}; custom = {source, key: 'value', affectsParticles: false, restore() { input.value = original; }}; }
        if (!custom && typeof attachmentUi !== 'undefined' && attachmentUi) custom = attachmentUi.bindingFor(input);
        if (!custom && typeof flowBindingFor === 'function') custom = flowBindingFor(input);
        if (!custom && typeof seedBindingFor === 'function') custom = seedBindingFor(input);
        const key = custom ? custom.key : input.dataset.field || {duration: 'duration', projectSeed: 'seed'}[input.id]; if (!key) return;
        if (gesture) finish(false);
        const source = custom ? custom.source : input.dataset.field ? emitter() : project;
        const step = input.step && input.step !== 'any' ? Number(input.step) : 1;
        gesture = {input, source, key, restore: custom && custom.restore, affectsParticles: custom && custom.affectsParticles, sourceValue: source[key], text: input.value, mode,
          pointerId: event.pointerId, downX: event.clientX, downY: event.clientY,
          anchorX: event.clientX, anchorValue: value, step,
          min: bound(input, 'min', -Infinity), max: bound(input, 'max', Infinity),
          modifier: modifier(event), active: false};
        // A plain click keeps the browser's focus, caret and direct typing behavior.
      });
    });
    document.addEventListener('pointerdown', () => { suppressClick = null; }, true);
    document.addEventListener('pointermove', event => {
      const current = gesture; if (!current || event.pointerId !== current.pointerId) return;
      if (!current.active) {
        const dx = Math.abs(event.clientX - current.downX), dy = Math.abs(event.clientY - current.downY);
        if (dy > 8 && dy > dx * 2) { gesture = null; return; }
        if (dx < 4) return;
        current.active = true; current.input.classList.add('scrubbing'); document.body.classList.add('number-scrubbing');
        try { current.input.setPointerCapture(event.pointerId); } catch (_) {}
      }
      event.preventDefault(); event.stopPropagation();
      const nextModifier = modifier(event);
      if (nextModifier !== current.modifier) {
        current.anchorX = event.clientX; current.anchorValue = current.input.valueAsNumber; current.modifier = nextModifier;
      }
      try {
        const value = Scrub.valueAtDrag({value: current.anchorValue, deltaX: event.clientX - current.anchorX,
          step: current.step, min: current.min, max: current.max, modifier: current.modifier});
        if (current.input.valueAsNumber !== value) {
          current.input.value = String(value); current.input.dispatchEvent(new Event('input', {bubbles: true}));
        }
        const deltaX = event.clientX - current.anchorX;
        if ((value === current.min && deltaX < 0) || (value === current.max && deltaX > 0)) {
          current.anchorX = event.clientX; current.anchorValue = value;
        }
      } catch (error) { finish(true); notify(error.message, true); }
    }, {capture: true, passive: false});
    document.addEventListener('pointerup', event => {
      if (!gesture || event.pointerId !== gesture.pointerId) return;
      if (gesture.active) { event.preventDefault(); event.stopPropagation(); }
      finish(false);
    }, true);
    document.addEventListener('pointercancel', event => { if (gesture && event.pointerId === gesture.pointerId) finish(true); }, true);
    document.addEventListener('lostpointercapture', event => { if (gesture && event.pointerId === gesture.pointerId) finish(false); }, true);
    document.addEventListener('click', event => {
      if (suppressClick && event.target === suppressClick) { event.preventDefault(); event.stopPropagation(); }
      suppressClick = null;
    }, true);
    document.addEventListener('keydown', event => {
      if (gesture && gesture.active && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(true); }
    }, true);
    window.addEventListener('blur', () => finish(false));
  }
  function wireEvents() {
    wireHistory();
    wireEmitterSeed();
    pathEditor = window.ParticlePathEditor.mount({getEmitter: emitter, getScene: pathScene, loadOutline: loadPathOutline, onApply: (path, e, reference) => {
      const prior = {path: e.path, outline: e.outline, width: e.width, height: e.height};
      try {
        if (!project.emitters.includes(e)) throw new Error('發射器已切換，請重新開啟路徑。');
        if (reference) Object.assign(e, {outline: reference.outline, width: reference.width, height: reference.height});
        e.path = PathMath.normalize(Object.assign({}, path, {enabled: true})); PathMath.compile(e.path); Core.normalizeProject(project);
        changed(); renderEmitters(); renderInspector(); notify('已套用路徑，請更新烘焙以輸出 Spine。');
      }
      catch (error) { Object.assign(e, prior); notify(error.message, true); throw error; }
    }});
    $('editPath').addEventListener('click', () => { try { pathEditor.open(); updateHistoryStatus(); } catch (error) { notify(error.message, true); } });
    $('pathUseOutline').addEventListener('click', () => { try { pathEditor.open({preset: 'outline'}); updateHistoryStatus(); } catch (error) { notify(error.message, true); } });
    $('enablePath').addEventListener('change', () => changePath('enabled', $('enablePath').checked));
    $('pathMode').addEventListener('change', () => changePath('mode', $('pathMode').value));
    $('pathOffsets').addEventListener('change', () => changePath('offsets', $('pathOffsets').checked));
    $('pathStopSpin').addEventListener('click', () => {
      const e = emitter();
      if (busy || !e.alignDirection || !(e.path && e.path.enabled) || !(e.spin || e.spinRandom)) return;
      e.spin = e.spinRandom = 0; changed(); renderInspector();
    });
    $('adjustPath').addEventListener('click', () => { setTab('motion'); $('pathAdvanced').open = true; expandSectionFor($('pathSection')); $('pathSection').scrollIntoView({block: 'nearest'}); });
    $('loadOutline').addEventListener('click', () => $('outlineFile').click());
    $('outlineFile').addEventListener('change', async event => {
      const selected = emitter(), owner = project, threshold = Number($('outlineThreshold').value), includeHoles = $('outlineHoles').checked;
      const request = ++outlineRequest;
      try {
        const file = event.target.files[0]; if (!file) return; const image = await loadImage(file);
        if (owner !== project || request !== outlineRequest || !project.emitters.includes(selected)) return;
        await scanOutline(image, selected, threshold, includeHoles);
      }
      catch (error) { notify(error.message, true); } finally { event.target.value = ''; }
    });
    $('rescanOutline').addEventListener('click', async () => {
      const selected = emitter(); if (!selected.outline || !selected.outline.image) return;
      try { await scanOutline(selected.outline.image, selected, Number($('outlineThreshold').value), $('outlineHoles').checked); }
      catch (error) { notify(error.message, true); }
    });
    $('outlineHoles').addEventListener('change', () => {
      const e = emitter(); if (!e.outline) return; e.outline = Object.assign({}, e.outline, {includeHoles: $('outlineHoles').checked}); changed(); renderOutlineInspector();
    });
    $('outlineShowImage').addEventListener('change', () => {
      const e = emitter(); if (!e.outline) return; e.outline = Object.assign({}, e.outline, {showImage: $('outlineShowImage').checked}); changed(); renderOutlineInspector();
    });
    $('flowSettingsButton').addEventListener('click', () => { refreshFlowUi(); $('flowFeedback').hidden = true; $('flowDialog').showModal(); });
    ['closeFlow', 'flowCloseFooter'].forEach(id => $(id).addEventListener('click', () => $('flowDialog').close()));
    $('flowAttach').addEventListener('click', () => { $('flowDialog').close(); $('spineMergeButton').click(); });
    $('flowBake').addEventListener('click', async () => { $('flowDialog').close(); await bakeNow(); });
    const applyFlow = (input, kind, field, duringInput) => {
      if (!input.checkValidity() || (input.type !== 'checkbox' && !input.value.trim())) {
        if (!duringInput) { refreshFlowUi(); notify('請輸入有效的動畫名稱或 0.05–30 秒的長度。', true); }
        return;
      }
      const candidate = clone(project.flow);
      if (field === 'enabled') candidate.enabled = input.checked;
      else candidate[kind][field] = field === 'duration' ? Number(input.value) : input.value.trim();
      try {
        const normalized = Core.normalizeFlow(candidate, project.duration);
        if (JSON.stringify(normalized) === JSON.stringify(project.flow)) return;
        project.flow = normalized; time = 0; playing = false; changed(); refreshFlowUi(); updatePlayButton();
      } catch (error) {
        if (!duringInput) { input.value = project.flow[kind][field]; notify(error.message, true); }
      }
    };
    $('flowEnabled').addEventListener('change', () => applyFlow($('flowEnabled'), null, 'enabled', false));
    ['in', 'loop', 'out'].forEach(kind => {
      const cap = kind[0].toUpperCase() + kind.slice(1);
      ['name', 'duration'].forEach(field => {
        const input = $('flow' + cap + field[0].toUpperCase() + field.slice(1));
        input.addEventListener('input', () => applyFlow(input, kind, field, true));
        input.addEventListener('change', () => applyFlow(input, kind, field, false));
      });
      $('previewFlow' + cap).addEventListener('click', () => selectPhase(kind, false));
    });
    $('flowPlaySequence').addEventListener('click', () => {
      if (!currentFlowBake()) return;
      sequence = true; exitRequested = false; playing = true; selectPhase('in', true);
    });
    $('flowRequestOut').addEventListener('click', () => {
      if (!currentFlowBake() || phase !== 'loop' || !playing) return;
      sequence = true; exitRequested = true; refreshFlowUi(); queueDraft();
    });
    controls.forEach(input => {
      const apply = duringInput => {
        const key = input.dataset.field, e = emitter();
        if (!input.checkValidity()) { if (!duringInput) input.reportValidity(); return; }
        if (duringInput && input.type !== 'checkbox' && !input.value.trim()) return;
        const value = input.type === 'checkbox' ? input.checked : (input.type === 'range' || input.type === 'number') ? Number(input.value) : input.value;
        if (typeof value === 'number' && !Number.isFinite(value)) return;
        const previous = e[key]; if (value === previous) return; e[key] = value;
        try { Core.normalizeProject(project); } catch (error) { e[key] = previous; if (!duringInput) { input.value = previous; notify(error.message, true); } return; }
        syncEmitterPeers(input);
        changed(); renderEmitters(); if (key === 'shape' || key === 'emitFrom' || key === 'directionMode') renderInspector(); document.querySelectorAll('[data-readout]').forEach(output => { output.textContent = e[output.dataset.readout]; });
      };
      input.addEventListener('input', () => apply(true));
      input.addEventListener('change', () => apply(false));
    });
    [['duration', 'duration'], ['fps', 'fps'], ['projectSeed', 'seed'], ['loop', 'loop'], ['projectName', 'name']].forEach(([id, key]) => {
      const input = $(id); const apply = duringInput => {
        if (!input.checkValidity()) { if (!duringInput) input.reportValidity(); return; }
        if (duringInput && input.type !== 'checkbox' && !input.value.trim()) return;
        const previous = project[key]; const value = key === 'name' ? input.value.trim() : key === 'loop' ? input.checked : Number(input.value);
        if (value === previous) return; project[key] = value;
        try { Core.normalizeProject(project); } catch (error) { project[key] = previous; if (!duringInput) { renderGlobals(); notify(error.message, true); } return; }
        changed(); syncTimeline();
      }; input.addEventListener('input', () => apply(true)); input.addEventListener('change', () => apply(false));
    });
    $('addEmitter').addEventListener('click', () => addEmitter('glow'));
    $('centerEmitter').addEventListener('click', () => { const e = emitter(); e.x = e.y = 0; changed(); renderInspector(); });
    $('duplicateEmitter').addEventListener('click', () => {
      if (project.emitters.length >= 8) return;
      const source = emitter(), e = clone(source); e.id = freshId(); e.name = (e.name + ' 複本').slice(0, 80);
      if (integration) for (const field of ['emitterParents', 'emitterLayers']) {
        const map = integration.settings[field]; if (map && map['em_' + source.id] !== undefined) map['em_' + e.id] = clone(map['em_' + source.id]);
      }
      project.emitters.unshift(e); selectedId = e.id; changed(); renderEmitters(); renderInspector();
    });
    $('deleteEmitter').addEventListener('click', () => {
      if (project.emitters.length <= 1) return;
      if (integration) for (const field of ['emitterParents', 'emitterLayers']) {
        const map = integration.settings[field]; if (map) delete map['em_' + selectedId];
      }
      project.emitters = project.emitters.filter(e => e.id !== selectedId); selectedId = project.emitters[0].id;
      changed(); renderEmitters(); renderInspector();
    });
    [['moveEmitterUp', -1], ['moveEmitterDown', 1]].forEach(([id, delta]) => { $(id).addEventListener('click', () => { const index = project.emitters.findIndex(e => e.id === selectedId), next = index + delta; if (next < 0 || next >= project.emitters.length) return; const item = project.emitters.splice(index, 1)[0]; project.emitters.splice(next, 0, item); changed(); renderEmitters(); }); });
    $('saveProject').addEventListener('click', saveProject); $('bakeButton').addEventListener('click', bakeNow); $('exportButton').addEventListener('click', exportZip);
    $('newProject').addEventListener('click', () => { if (!busy && !resettingProject) $('newProjectDialog').showModal(); });
    $('resetProjectCancel').addEventListener('click', () => $('newProjectDialog').close());
    $('resetProjectConfirm').addEventListener('click', resetProject);
    $('resetProjectSave').addEventListener('click', () => { if (!busy && !resettingProject && saveProject()) resetProject(); });
    $('spineVersion').addEventListener('change', () => {
      if (integration && integration.settings.enabled !== false) { updateBakeStatus(); return; }
      try { project.spineVersion = Core.spineProfile($('spineVersion').value).version; updateBakeStatus(); queueDraft(); notify('輸出版本已切換至 Spine ' + project.spineVersion + '。'); }
      catch (error) { renderGlobals(); notify(error.message, true); }
    });
    $('loadProject').addEventListener('click', () => $('projectFile').click());
    $('projectFile').addEventListener('change', async event => {
      const file = event.target.files[0]; if (!file) return;
      const request = ++projectRequest;
      try {
        if (file.size > 48 * 1024 * 1024) throw new Error('專案檔超過 48 MB。');
        const parsed = Storage.parse(await file.text(), Core); if (request !== projectRequest) return;
        await adopt(parsed); queueDraft(); notify(liveError ? '已載入專案，請調整參數：' + liveError : '已載入專案與素材。', !!liveError);
      }
      catch (error) { notify(error.message, true); } finally { event.target.value = ''; }
    });
    $('modeLive').addEventListener('click', () => { stopSequence(); mode = 'live'; updateBakeStatus(); queueDraft(); });
    $('modeBaked').addEventListener('click', () => { if (!baked) return; stopSequence(); mode = 'baked'; updateBakeStatus(); queueDraft(); });
    $('playButton').addEventListener('click', () => { const snapshot = activeBake(); if (!snapshot || attachedMode() && !attachedFor()) return; playing = !playing; if (playing && time >= previewDuration()) time = 0; refreshFlowUi(); updatePlayButton(); queueDraft(); });
    $('restartButton').addEventListener('click', () => { stopSequence(); time = 0; refreshFlowUi(); syncTimeline(); queueDraft(); });
    $('timeline').addEventListener('input', () => { stopSequence(); playing = false; time = Number($('timeline').value) / activeFps(); refreshFlowUi(); updatePlayButton(); syncTimeline(); queueDraft(); });
    [['framePrev', -1], ['frameNext', 1]].forEach(([id, delta]) => { $(id).addEventListener('click', () => { const snapshot = activeBake(); if (!snapshot) return; const fps = activeFps(); stopSequence(); playing = false; time = clamp((Math.round(time * fps) + delta) / fps, 0, previewDuration()); refreshFlowUi(); updatePlayButton(); syncTimeline(); queueDraft(); }); });
    $('zoom').addEventListener('input', () => { zoomAt(clamp(Number($('zoom').value) / 100, 0.05, MAX_ZOOM), stageW / 2, stageH / 2); });
    $('centerView').addEventListener('click', () => { panX = panY = 0; zoom = 1; renderGlobals(); queueDraft(); });
    $('backgroundColor').addEventListener('input', () => { project.background.color = $('backgroundColor').value; queueDraft(); });
    $('backgroundButton').addEventListener('click', () => $('backgroundFile').click());
    $('backgroundFile').addEventListener('change', async event => {
      const request = ++backgroundRequest, owner = project;
      try {
        const file = event.target.files[0]; if (!file) return;
        const loaded = await loadImage(file, true);
        if (request !== backgroundRequest || owner !== project) return;
        const {sourceWidth, sourceHeight, ...image} = loaded;
        const candidate = {...project, background: {...project.background, image, sourceWidth, sourceHeight, scale: 1}};
        project.background = Core.normalizeProject(candidate).background; fitBackgroundView();
      } catch (error) { notify(error.message, true); } finally { event.target.value = ''; }
    });
    $('backgroundActualSize').addEventListener('click', () => {
      if (!project.background.image) return;
      project.background.scale = 1; fitBackgroundView();
      notify(project.background.sourceWidth ? '背景與物件已使用相同像素比例，已調整視角。' : '背景已按保存的像素尺寸校正；舊版縮圖需重新載入原背景圖，才能恢復原始大小。');
    });
    $('removeBackground').addEventListener('click', () => { backgroundRequest++; project.background.image = null; delete project.background.sourceWidth; delete project.background.sourceHeight; renderGlobals(); queueDraft(); });
    textureUi = window.ParticleSequenceTextureUI.mount({getProject: () => project, getEmitter: emitter,
      getGeneration: () => textureRequest, defaultImage: builtinImages.glow, normalize: Core.normalizeProject, loadImage, notify,
      prepareImages: frames => frames.forEach(imageFor), onApply: (selected, patch, command) => {
        if (command) historyBegin('command');
        try {
          for (const key of Object.keys(patch)) { if (patch[key] === undefined) delete selected[key]; else selected[key] = patch[key]; }
          changed(); renderEmitters(); renderInspector();
        } finally { if (command) historyEnd(); }
      }});
    document.querySelectorAll('[data-tab]').forEach(button => { button.addEventListener('click', () => setTab(button.dataset.tab)); });
    const tabs = Array.from(document.querySelectorAll('[data-tab]'));
    document.querySelector('.inspector-tabs').addEventListener('keydown', event => { if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return; const index = tabs.indexOf(event.target); if (index < 0) return; event.preventDefault(); const target = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]; target.focus(); target.click(); });
    $('helpButton').addEventListener('click', () => $('helpDialog').showModal()); $('closeHelp').addEventListener('click', () => $('helpDialog').close());
    const lifecycleChange = () => { changed(); renderEmitters(); drawCurves(); };
    curveEditor = window.ParticleCurveEditor.mount({getEmitter: emitter, onChange: lifecycleChange, math: window.ParticleCurveMath, Core});
    gradientEditor = window.ParticleGradientEditor.mount({getEmitter: emitter, onChange: lifecycleChange, math: window.ParticleCurveMath, Core});
    $('alphaAdvanced').addEventListener('toggle', drawCurves);
    lookPresetsUi = window.ParticleLookPresetsUI.mount({getEmitter: emitter, onApply: (kind, id) => {
      if (busy) return;
      historyBegin('command');
      try {
        if (window.ParticleLookPresets.apply(emitter(), kind, id)) { changed(); renderEmitters(); renderInspector(); }
      } catch (error) { notify(error.message, true); }
      finally { historyEnd(); }
    }});
    libraryUi = window.ParticleEffectLibraryUI.mount({Core, getEmitter: emitter, getGeneration: () => project,
      builtins: BUILTIN_EFFECTS,
      addBlockedReason: () => busy ? '目前正在烘焙，請稍候。' : project.emitters.length >= 8 ? '已達 8 個發射器上限，請先刪除或停用不需要的圖層。' : '',
      onAdd: choice => {
        if (busy) throw new Error('目前正在烘焙，請完成後再新增。');
        if (choice.builtin) { insertEmitter(builtinEmitter(choice.builtin)); return; }
        const blank = Core.createEmitter(freshId(), choice.template.name.slice(0, 80));
        const next = window.ParticleEffectLibrary.instantiate(choice.template, Object.assign(blank, {name: choice.template.name.slice(0, 80)}));
        insertEmitter(next);
      },
      onApplyBuiltin: preset => {
        if (busy) throw new Error('目前正在烘焙，請完成後再套用效果。');
        const current = emitter(), index = project.emitters.indexOf(current);
        if (index < 0) throw new Error('目前發射器已改變，請重新選取。');
        const next = builtinEmitter(preset, current.id);
        Object.assign(next, {name: current.name, x: current.x, y: current.y, enabled: current.enabled});
        historyBegin('command');
        try { outlineRequest++; textureRequest++; project.emitters[index] = next; changed(); renderEmitters(); renderInspector(); }
        finally { historyEnd(); }
      },
      notify: message => notify(message, true), onApply: template => {
        if (busy) throw new Error('目前正在烘焙，請完成後再套用效果。');
        const current = emitter(), next = window.ParticleEffectLibrary.instantiate(template, current);
        if (JSON.stringify(current) === JSON.stringify(next)) return false;
        historyBegin('command');
        try {
          const index = project.emitters.indexOf(current);
          if (index < 0) throw new Error('目前發射器已改變，請重新選取。');
          outlineRequest++; textureRequest++;
          project.emitters[index] = next;
          changed(); renderEmitters(); renderInspector();
          return true;
        } finally { historyEnd(); }
      }});
    timelineView = window.ParticleTimelineView.mount({host: $('timelineTracks'), getContext: () => {
      const group = currentFlowBake(), attached = attachedFor();
      return {flow: group ? group.project.flow : mode === 'live' && project.flow.enabled ? project.flow : null,
        phase, time, duration: previewDuration(), fps: activeFps(), attached: !!attached, timeline: attached && attached.timeline};
    }, onSeek: seconds => {
      if (busy) return;
      stopSequence(); playing = false;
      const duration = previewDuration();
      time = seconds >= duration ? duration : clamp(Math.round(seconds * activeFps()) / activeFps(), 0, duration);
      refreshFlowUi(); updatePlayButton(); syncTimeline(); queueDraft();
    }, onSelectPhase: kind => { if (!busy) selectPhase(kind, false); }});
    document.querySelector('.timeline-panel').classList.add('timeline-upgraded');
    emitterLanes = window.ParticleEmitterLanes.mount({host: document.querySelector('.timeline-panel'), getContext: () => {
      const muted = previewMutedIds(), attached = attachedFor(), flow = project.flow.enabled;
      const duration = flow ? project.flow.loop.duration : project.duration;
      let local = attached ? time - attached.timeline.startTime : time;
      if (flow && phase !== 'loop') local = 0;
      return {duration, fps: project.fps, time: local, selectedId,
        emitters: project.emitters.map(e => ({id: e.id, name: e.name, enabled: e.enabled, muted: muted.has(e.id),
          startDelay: e.startDelay || 0, emissionDuration: e.emissionDuration, life: e.life, lifeRandom: e.lifeRandom,
          color: e.colorGradient && e.colorGradient.length ? e.colorGradient[Math.floor(e.colorGradient.length / 2)].color : e.colorStart}))};
    }, onSelect: id => { if (id !== selectedId) selectEmitter(id); },
    onBegin: () => { if (!busy) historyBegin('command'); },
    onChange: (id, patch) => {
      const e = project.emitters.find(item => item.id === id); if (!e || busy) return;
      const prior = {startDelay: e.startDelay, emissionDuration: e.emissionDuration};
      Object.assign(e, patch); if (e.startDelay === 0) delete e.startDelay;
      try { Core.normalizeProject(project); } catch (error) { Object.assign(e, prior); if (prior.startDelay === undefined) delete e.startDelay; notify(error.message, true); return; }
      changed(); renderInspector();
    },
    onEnd: () => { historyEnd(); }});
    canvas.addEventListener('contextmenu', event => event.preventDefault());
    canvas.addEventListener('pointerdown', event => {
      if (![0, 1, 2].includes(event.button)) return;
      interaction = {type: 'pan', x: event.clientX, y: event.clientY, originalX: panX, originalY: panY};
      canvas.setPointerCapture(event.pointerId); event.preventDefault();
    });
    canvas.addEventListener('pointermove', moveInteraction);
    canvas.addEventListener('pointerup', finishInteraction); canvas.addEventListener('pointercancel', finishInteraction); canvas.addEventListener('lostpointercapture', finishInteraction);
    handleLayer.addEventListener('contextmenu', event => event.preventDefault());
    // Zoom around the cursor so the detail under the pointer stays in place.
    $('canvasStage').addEventListener('wheel', event => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const next = clamp(zoom * Math.exp(-event.deltaY * 0.0015), 0.05, MAX_ZOOM);
      zoomAt(next, event.clientX - rect.left, event.clientY - rect.top);
    }, {passive: false});
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveProject(); return; }
      if (event.target.closest('input,select,textarea,button,canvas.curve-canvas') || $('helpDialog').open || $('spineMergeDialog').open || $('flowDialog').open || $('pathDialog').open || $('bakeCheckDialog').open || $('effectLibraryDialog').open) return;
      if (event.code === 'Space') { event.preventDefault(); $('playButton').click(); }
      if (event.key === 'ArrowLeft') { event.preventDefault(); $('framePrev').click(); }
      if (event.key === 'ArrowRight') { event.preventDefault(); $('frameNext').click(); }
    });
    priorAssets = integration && integration.assets; priorSource = integration && integration.json;
    wireBakeCheck();
    attachmentUi = window.ParticleSpineAttachmentUI.mount({Merge: SpineMerge, EffectUpdate, getEffectiveSession: effectiveIntegration, getProject: () => project, getGeneration: () => project, onPickBone: startBonePick,
      getSession: () => integration, setSession: value => {
        const newSource = value && (!integration || value.json !== integration.json);
        if (bonePicker && value && integration && value.update !== integration.update) bonePicker.cancel();
        integration = value;
        if (newSource) { previewAttached = true; previewSkin = ''; time = 0; stopSequence(); }
      },
      onChange: integrationChanged, onExport: async () => { if (await ensureBaked()) exportMergedZip(); }, onBake: bakeNow, managePreviewChip: false,
      canExport: () => !busy, notify});
    assetsUi = window.ParticleSpineAssetsUI.mount({Merge: SpineMerge, getSession: () => integration,
      setSession: value => { integration = value; }, onChange: integrationChanged, imageLoader: loadImage, notify});
    $('previewFocus').addEventListener('click', focusAttachment);
    $('spineFocusParent').addEventListener('click', () => { previewAttached = true; refreshAttachmentPreview(); $('spineMergeDialog').close(); focusAttachment(); });
    $('previewFxStart').addEventListener('click', () => { const attached = attachedFor(); if (!attached) return; stopSequence(); playing = false; time = attached.timeline.startTime; updatePlayButton(); syncTimeline(); queueDraft(); });
    [['previewAttached', true], ['previewLocal', false]].forEach(([id, value]) => $(id).addEventListener('click', () => {
      if (previewAttached === value) return;
      const attached = attachedFor(); stopSequence(); playing = false;
      const local = attached ? clamp(time - attached.timeline.startTime, 0, attached.timeline.fxDuration) : time; previewAttached = value; refreshAttachmentPreview();
      const next = attachedFor(); time = next ? (local || 0) + next.timeline.startTime : local || 0;
      refreshFlowUi(); syncTimeline(); updatePlayButton(); queueDraft();
    }));
    $('previewBones').addEventListener('change', () => { showBones = $('previewBones').checked; queueDraft(); });
    $('previewSkin').addEventListener('change', () => { previewSkin = $('previewSkin').value; attachedCache.clear(); refreshAttachmentPreview(); queueDraft(); });
    wireBonePicker(); wireNumberScrub(); wireShortcuts(); wireDropZone(); wireSectionCollapse();
    batchUi = window.ParticleBatchExport.mount({run: runBatchExport, notify, getVersion: () => effectiveSpineVersion(),
      blockedReason: () => integration && integration.settings.enabled !== false ? '目前掛接既有骨架，版本跟隨原骨架；請用「輸出追加包」，或先移除掛接再批次輸出。' : busy ? '正在烘焙，請稍候。' : ''});
    window.addEventListener('pagehide', () => { try { saveDraftSnapshot(JSON.parse(Storage.serialize(project, baked ? baked.project : null, viewState(), integration))).catch(() => {}); } catch (_) {} });
  }


  // Inspector sections fold open/closed; the choice is remembered per section.
  const SECTION_KEY = 'particle-studio-collapsed-sections';
  function sectionHeading(section) {
    return Array.from(section.children).find(child => child.tagName === 'H3' || child.classList.contains('inspector-section-heading')) || null;
  }
  function setSectionCollapsed(section, collapsed, remember = true) {
    section.classList.toggle('collapsed', collapsed);
    const toggle = section.querySelector(':scope > .section-toggle-host .section-toggle, :scope > h3 .section-toggle, :scope > .inspector-section-heading .section-toggle');
    if (toggle) { toggle.setAttribute('aria-expanded', String(!collapsed)); toggle.title = collapsed ? '展開此區塊' : '收合此區塊'; }
    if (!collapsed && initialized) requestAnimationFrame(drawCurves);
    if (!remember) return;
    try {
      const stored = JSON.parse(localStorage.getItem(SECTION_KEY) || '{}');
      if (collapsed) stored[section.dataset.sectionKey] = 1; else delete stored[section.dataset.sectionKey];
      localStorage.setItem(SECTION_KEY, JSON.stringify(stored));
    } catch (_) { /* optional preference */ }
  }
  function expandSectionFor(node) {
    const section = node && node.closest('.inspector-section');
    if (section && section.classList.contains('collapsed')) setSectionCollapsed(section, false);
  }
  function wireSectionCollapse() {
    let stored = {};
    try { stored = JSON.parse(localStorage.getItem(SECTION_KEY) || '{}') || {}; } catch (_) { stored = {}; }
    document.querySelectorAll('[data-panel] .inspector-section').forEach((section, index) => {
      const heading = sectionHeading(section); if (!heading) return;
      const h3 = heading.tagName === 'H3' ? heading : heading.querySelector('h3'); if (!h3) return;
      const panel = section.closest('[data-panel]').dataset.panel;
      section.dataset.sectionKey = panel + ':' + (h3.textContent.trim() || index);
      const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'section-toggle';
      toggle.setAttribute('aria-label', '收合或展開「' + h3.textContent.trim() + '」');
      toggle.innerHTML = '<svg aria-hidden="true" viewBox="0 0 20 20"><path d="m6 8 4 4 4-4"/></svg>';
      h3.classList.add('section-title-toggle'); h3.prepend(toggle);
      toggle.addEventListener('click', event => { event.stopPropagation(); setSectionCollapsed(section, !section.classList.contains('collapsed')); });
      h3.addEventListener('click', event => {
        if (event.target.closest('button:not(.section-toggle), input, select, label, a')) return;
        setSectionCollapsed(section, !section.classList.contains('collapsed'));
      });
      setSectionCollapsed(section, !!stored[section.dataset.sectionKey], false);
    });
  }

  // ---- Workflow: shortcuts, emitter clipboard and drag & drop ----
  const CLIPBOARD_KEY = 'particle-studio-emitter-clipboard';
  let emitterClipboard = null;
  function anyDialogOpen() { return Array.from(document.querySelectorAll('dialog')).some(dialog => dialog.open); }
  function copyEmitter() {
    const source = emitter(); if (!source) return;
    emitterClipboard = {format: 'particle-studio-emitter', version: 1, emitter: clone(source)};
    try { localStorage.setItem(CLIPBOARD_KEY, JSON.stringify(emitterClipboard)); } catch (_) { /* memory copy still works in this window */ }
    notify('已複製「' + source.name + '」。在任何專案按 Ctrl＋V 貼上為新圖層。');
  }
  function pasteEmitter() {
    let data = null;
    try { const text = localStorage.getItem(CLIPBOARD_KEY); data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
    data = data && data.format === 'particle-studio-emitter' ? data : emitterClipboard;
    if (!data || !data.emitter) { notify('尚未複製發射器。先選取圖層按 Ctrl＋C。', true); return; }
    if (project.emitters.length >= 8) { notify('每個專案最多 8 個發射器。', true); return; }
    try {
      const candidate = clone(data.emitter); candidate.id = freshId();
      if (project.emitters.some(e => e.name === candidate.name)) candidate.name = (candidate.name + ' 貼上').slice(0, 80);
      const next = Core.normalizeProject({...clone(project), emitters: [candidate].concat(clone(project.emitters))}).emitters[0];
      historyBegin('command');
      try {
        const index = Math.max(0, project.emitters.findIndex(e => e.id === selectedId));
        project.emitters.splice(index, 0, next); selectedId = next.id; changed(); renderEmitters(); renderInspector();
      } finally { historyEnd(); }
      notify('已貼上「' + next.name + '」。');
    } catch (error) { notify('無法貼上發射器：' + error.message, true); }
  }
  function selectAdjacentEmitter(delta) {
    const index = project.emitters.findIndex(e => e.id === selectedId), next = project.emitters[index + delta];
    if (next) selectEmitter(next.id);
  }
  function wireShortcuts() {
    document.addEventListener('keydown', event => {
      if (anyDialogOpen() || busy || event.defaultPrevented) return;
      const target = event.target instanceof Element ? event.target : document.body;
      const typing = !!target.closest('input:not([type="checkbox"]):not([type="radio"]):not([type="range"]),textarea,select,[contenteditable="true"]');
      const ctrl = event.ctrlKey || event.metaKey, key = event.key.toLowerCase();
      if (ctrl && !event.altKey) {
        const selection = window.getSelection && String(window.getSelection());
        const actions = {
          o: () => $('loadProject').click(), b: () => bakeNow(), e: () => exportZip(),
          d: () => typing ? null : $('duplicateEmitter').click(),
          c: () => typing || selection ? null : copyEmitter(), v: () => typing ? null : pasteEmitter()
        };
        if (!event.shiftKey && actions[key] && !(typing && ['c', 'v', 'd'].includes(key))) { event.preventDefault(); actions[key](); }
        return;
      }
      if (typing || event.altKey || event.repeat && !['[', ']'].includes(key)) return;
      if (key === 'delete' || key === 'backspace') {
        // Only from neutral focus: the layer list, canvas or page, never a curve or field.
        if (!(target === document.body || target === document.documentElement || target.closest('.emitter-list, #canvasStage, .timeline-panel'))) return;
        if (target.closest('canvas.curve-canvas, [role="slider"], input')) return;
        event.preventDefault(); if (!$('deleteEmitter').disabled) $('deleteEmitter').click(); else notify('至少要保留 1 個發射器。', true);
      } else if (key === 'f') { event.preventDefault(); focusSelectedEmitter(); }
      else if (key === '0') { event.preventDefault(); zoomAt(1, stageW / 2, stageH / 2); }
      else if (key === 'h') { event.preventDefault(); togglePreviewHidden(selectedId); }
      else if (key === 's' && !event.shiftKey) { event.preventDefault(); toggleSolo(selectedId); }
      else if (key === '[') { event.preventDefault(); selectAdjacentEmitter(-1); }
      else if (key === ']') { event.preventDefault(); selectAdjacentEmitter(1); }
    });
  }
  function feedInput(id, files) {
    const input = $(id); if (!input) return false;
    const transfer = new DataTransfer(); files.forEach(file => transfer.items.add(file));
    input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
  }
  const isImage = file => /^image\/(png|jpeg|webp)$/.test(file.type) || /\.(png|jpe?g|webp)$/i.test(file.name);
  const numericOrder = (a, b) => a.name.localeCompare(b.name, undefined, {numeric: true, sensitivity: 'base'});
  async function routeJsonFile(file) {
    if (file.size > 48 * 1024 * 1024) throw new Error('檔案超過 48 MB：' + file.name);
    const owner = project, request = projectRequest, text = await file.text();
    if (owner !== project || request !== projectRequest) return '';
    let data; try { data = JSON.parse(text); } catch (_) { throw new Error('「' + file.name + '」不是有效的 JSON。'); }
    if (data && data.format === 'particle-studio') return feedInput('projectFile', [file]) && '專案';
    if (data && data.format === 'particle-studio-fx-library') { await libraryUi.open(); if (owner !== project || request !== projectRequest) return ''; return feedInput('effectLibraryFile', [file]) && '效果庫'; }
    if (data && data.format === 'particle-studio-emitter') {
      emitterClipboard = data; try { localStorage.setItem(CLIPBOARD_KEY, JSON.stringify(data)); } catch (_) {}
      pasteEmitter(); return '發射器';
    }
    if (data && data.skeleton && Array.isArray(data.bones)) {
      $('spineMergeButton').click(); return feedInput('spineSourceFile', [file]) && 'Spine 骨架';
    }
    if (data && (data.manifest || data.format === 'particle-studio-effect-update') && integration) {
      $('spineMergeButton').click(); return feedInput('spineReceiptFile', [file]) && '效果更新記錄';
    }
    throw new Error('無法辨識「' + file.name + '」。支援粒子專案、效果庫或 Spine 骨架 JSON。');
  }
  function wireDropZone() {
    const overlay = document.createElement('div'); overlay.id = 'dropOverlay'; overlay.className = 'drop-overlay'; overlay.hidden = true;
    overlay.innerHTML = '<div class="drop-panel"><p class="drop-title">放開以載入檔案</p><div class="drop-zones"></div><p class="drop-hint">多張圖片可做成連續圖（依序播放）或隨機圖片（每顆隨機一張）。按 Esc 取消。</p></div>';
    document.body.append(overlay);
    const zonesHost = overlay.querySelector('.drop-zones');
    let depth = 0, activeZone = null;
    const zone = (key, title, text) => {
      const node = document.createElement('div'); node.className = 'drop-zone'; node.dataset.zone = key;
      const strong = document.createElement('strong'); strong.textContent = title; const small = document.createElement('span'); small.textContent = text;
      node.append(strong, small); return node;
    };
    const hasFiles = event => event.dataTransfer && Array.from(event.dataTransfer.types || []).includes('Files');
    function show(event) {
      const items = Array.from(event.dataTransfer.items || []).filter(item => item.kind === 'file');
      const images = items.filter(item => /^image\//.test(item.type)).length, others = items.length - images;
      const target = emitter() ? '「' + emitter().name + '」' : '目前發射器';
      zonesHost.replaceChildren();
      if (images && !others) {
        zonesHost.append(zone('texture', images > 1 ? '連續圖' : '粒子貼圖', images > 1 ? images + ' 張依檔名順序播放 → ' + target : '換成' + target + '的貼圖'));
        if (images > 1) zonesHost.append(zone('random', '隨機圖片', images + ' 張 → 每顆粒子隨機挑一張'));
        if (images === 1) {
          zonesHost.append(zone('outline', '物件輪廓', '掃描 PNG 外形，沿輪廓發射'));
          zonesHost.append(zone('background', '參考背景', '只在畫布對照，不會輸出'));
        }
        if (integration) zonesHost.append(zone('rig', '原骨架圖片', '掛接預覽用的角色素材'));
      } else zonesHost.append(zone('auto', '自動辨識', '粒子專案、效果庫、Spine 骨架 JSON 或 Atlas'));
      overlay.hidden = false;
    }
    function hide() { depth = 0; activeZone = null; overlay.hidden = true; }
    window.addEventListener('dragenter', event => {
      if (!hasFiles(event) || anyDialogOpen() && !$('spineMergeDialog').open) return;
      event.preventDefault(); if (depth++ === 0) show(event);
    });
    window.addEventListener('dragover', event => {
      if (!hasFiles(event) || overlay.hidden) return;
      event.preventDefault(); event.dataTransfer.dropEffect = 'copy';
      const node = event.target instanceof Element && event.target.closest('.drop-zone');
      if (node !== activeZone) { if (activeZone) activeZone.classList.remove('active'); activeZone = node || null; if (node) node.classList.add('active'); }
    });
    window.addEventListener('dragleave', event => { if (!hasFiles(event) || overlay.hidden) return; if (--depth <= 0) hide(); });
    window.addEventListener('keydown', event => { if (event.key === 'Escape' && !overlay.hidden) hide(); });
    window.addEventListener('drop', async event => {
      if (!hasFiles(event) || overlay.hidden) return;
      event.preventDefault();
      const node = event.target instanceof Element && event.target.closest('.drop-zone');
      const choice = node ? node.dataset.zone : (zonesHost.querySelector('.drop-zone') || {dataset: {}}).dataset.zone;
      const files = Array.from(event.dataTransfer.files || []); hide();
      if (!files.length || busy) return;
      const owner = project;
      try {
        const images = files.filter(isImage).sort(numericOrder), rest = files.filter(file => !isImage(file));
        const loaded = [];
        if (images.length) {
          if (choice === 'background') feedInput('backgroundFile', [images[0]]) && loaded.push('參考背景');
          else if (choice === 'outline') { setTab('basic'); feedInput('outlineFile', [images[0]]) && loaded.push('物件輪廓'); }
          else if (choice === 'rig') feedInput('spineImagesFile', images) && loaded.push(images.length + ' 張原骨架圖片');
          else if (choice === 'random') { setTab('look'); feedInput('randomTextureFile', images) && loaded.push(images.length + ' 張隨機圖片'); }
          else {
            setTab('look');
            if (images.length > 1) feedInput('sequenceTextureFile', images) && loaded.push(images.length + ' 張連續圖');
            else feedInput('textureFile', images) && loaded.push('粒子貼圖');
          }
        }
        for (const file of rest) {
          if (owner !== project) return;
          if (/\.atlas(\.txt)?$/i.test(file.name)) { $('spineMergeButton').click(); feedInput('spineAtlasFile', [file]); loaded.push('Atlas'); }
          else if (/\.json$/i.test(file.name) || file.type === 'application/json') loaded.push(await routeJsonFile(file));
          else throw new Error('不支援的檔案類型：' + file.name);
        }
        if (loaded.some(Boolean) && owner === project) $('appStatus').textContent = '拖放載入：' + loaded.filter(Boolean).join('、');
      } catch (error) { notify(error.message, true); }
    });
  }

  async function init() {
    refreshLive(); renderGlobals(); renderEmitters(); renderInspector(); wireEvents(); updateBakeStatus(); updatePlayButton();
    captureInterfaceDefaults();
    new ResizeObserver(resize).observe($('canvasStage')); new ResizeObserver(drawCurves).observe(document.querySelector('.inspector'));
    resize(); requestAnimationFrame(animate);
    const startingProject = project, startingRevision = revision, startingIntegration = integration;
    try {
      const draft = await Storage.loadDraft();
      if (draft && project === startingProject && revision === startingRevision && integration === startingIntegration && (!history || history.info().undoCount === 0 && !historyGroup)) { await adopt(Storage.parse(JSON.stringify(draft), Core)); $('appStatus').textContent = '已恢復本機草稿'; }
      else $('appStatus').textContent = '就緒 · 圖片與運算留在本機';
    } catch (error) { $('appStatus').textContent = '草稿恢復不可用，請使用專案檔'; }
    initialized = true;
  }
  init().catch(error => { notify('初始化失敗：' + error.message, true); $('appStatus').textContent = '請重新開啟工具'; });
})();
