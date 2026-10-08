(function () {
  'use strict';
  const Core = window.ParticleCore;
  const Zip = window.ParticleZip;
  const Storage = window.ParticleStorage;
  const Preview = window.ParticlePreview;
  const Scrub = window.ParticleScrub;
  const SpineMerge = window.ParticleSpineMerge;
  const FlowPlayback = window.ParticleFlowPlayback;
  const AttachmentPreview = window.ParticleAttachmentPreview;
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
  let curveEditor = null, gradientEditor = null, attachmentUi = null, assetsUi = null;
  let previewAttached = true, showBones = true, previewSkin = '', attachedError = '';
  const attachedCache = new Map();
  let integration = null;
  const builtinImages = {};
  let project = Core.createProject();
  let selectedId = project.emitters[0].id;
  let liveBake = null, baked = null, exported = null, bakedPreview = null, liveError = '';
  let liveFlowBake = null, flowBaked = null, phase = 'loop', sequence = false, exitRequested = false;
  let revision = 0, bakedRevision = -1;
  let mode = 'live', playing = true, time = 0;
  let zoom = 1, panX = 0, panY = 40, stageW = 1, stageH = 1;
  let liveTimer = null, draftTimer = null, messageTimer = null;
  let interaction = null, busy = false, initialized = false;

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
    try { record.value = AttachmentPreview.compile({session: integration, localBake: snapshot, phase: group ? key : null,
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
    else if (dirty) { status.append('參數已修改 · 待更新烘焙'); status.classList.add('dirty'); }
    else { status.append('烘焙已更新 · 可輸出'); status.classList.add('baked'); }
    $('exportButton').disabled = !baked || dirty || busy;
    $('bakeButton').disabled = busy;
    $('modeBaked').disabled = !baked;
    $('modeLive').classList.toggle('active', mode === 'live');
    $('modeLive').setAttribute('aria-pressed', String(mode === 'live'));
    $('modeBaked').classList.toggle('active', mode === 'baked');
    $('modeBaked').setAttribute('aria-pressed', String(mode === 'baked'));
    $('exportButton').querySelector('span').textContent = integration && integration.settings.enabled !== false ? '輸出追加包' : '輸出 Spine';
    if (attachmentUi) attachmentUi.refresh();
    if (assetsUi) assetsUi.refresh();
    refreshFlowUi();
    refreshAttachmentPreview();
  }
  function renderEmitters() {
    const list = $('emitterList'); list.replaceChildren();
    const shapeNames = {point: '點形', direction: '定向', line: '線形', circle: '圓形', ring: '圓環', box: '矩形'};
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
      const type = document.createElement('span'); type.className = 'emitter-type'; type.textContent = (shapeNames[item.shape] || '點形') + (['box', 'circle', 'ring'].includes(item.shape) ? emitFrom(item) === 'edge' ? ' · 邊框' : ' · 區域內' : '');
      const color = document.createElement('span'); color.className = 'emitter-color-dot'; color.style.setProperty('--emitter-color', item.colorGradient && item.colorGradient.length ? item.colorGradient[0].color : item.colorStart); color.setAttribute('aria-hidden', 'true');
      tags.append(type, color); copy.append(name, meta, tags);
      const index = document.createElement('span'); index.className = 'emitter-index'; index.textContent = String(layerIndex + 1).padStart(2, '0'); index.setAttribute('aria-hidden', 'true');
      button.append(icon, copy, index); button.addEventListener('click', () => { selectedId = item.id; renderEmitters(); renderInspector(); });
      row.append(check, button); list.append(row);
    });
    const index = project.emitters.findIndex(item => item.id === selectedId);
    $('addEmitter').disabled = project.emitters.length >= 8;
    $('duplicateEmitter').disabled = project.emitters.length >= 8;
    $('deleteEmitter').disabled = project.emitters.length <= 1;
    $('moveEmitterUp').disabled = index <= 0;
    $('moveEmitterDown').disabled = index === project.emitters.length - 1;
    renderHandles();
    if (attachmentUi) attachmentUi.refresh();
    refreshAttachmentPreview();
  }
  function selectEmitter(id) {
    selectedId = id; renderEmitters(); renderInspector();
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
  function finishInteraction() {
    if (interaction && interaction.type === 'emitter') {
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
  function renderInspector() {
    const e = emitter();
    controls.forEach(input => { if (input.type === 'checkbox') input.checked = !!e[input.dataset.field]; else input.value = input.dataset.field === 'emitFrom' ? emitFrom(e) : e[input.dataset.field]; });
    document.querySelectorAll('[data-shape-for]').forEach(group => { group.hidden = !group.dataset.shapeFor.split(/\s+/).includes(e.shape); });
    $('emitFromHint').textContent = emitFrom(e) === 'edge' ? (e.shape === 'box' ? '沿矩形四邊發射，按邊長分配粒子。' : '從圓形或橢圓的輪廓線發射；圓環仍可限制弧段角度。') + '粒子出生後依速度與外力移動。' : '從形狀內部發射；圓環會沿用設定的弧段範圍。';
    document.querySelectorAll('[data-readout]').forEach(output => { output.textContent = e[output.dataset.readout]; });
    const image = e.image || builtinImages.glow;
    $('textureThumbnail').src = image.dataUrl; $('textureThumbnail').hidden = false;
    $('textureInfo').textContent = (e.image ? e.image.name : '內建柔光') + ' · ' + image.width + ' × ' + image.height + ' px';
    drawCurves();
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
    $('zoom').value = Math.round(zoom * 100); $('zoomLabel').textContent = Math.round(zoom * 100) + '%';
    refreshFlowUi();
  }
  function refreshLive() {
    clearTimeout(liveTimer); liveTimer = null;
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
  function queueDraft() {
    if (!initialized) return;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(async () => {
      try {
        const raw = JSON.parse(Storage.serialize(project, baked ? baked.project : null, viewState(), integration));
        await Storage.saveDraft(raw);
        $('appStatus').textContent = '本機草稿已保存';
      } catch (error) { $('appStatus').textContent = error.message || '請儲存專案檔'; }
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
      ctx.strokeStyle = chosen ? '#87b9af' : '#738194'; ctx.globalAlpha = e.enabled ? (chosen ? 0.7 : 0.35) : 0.2;
      const edge = ['box', 'circle', 'ring'].includes(e.shape) && emitFrom(e) === 'edge';
      ctx.lineWidth = (edge && chosen ? 1.6 : 1) / zoom; ctx.setLineDash([4 / zoom, 4 / zoom]);
      ctx.beginPath();
      if (e.shape === 'box') ctx.rect(-e.width / 2, -e.height / 2, e.width, e.height);
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
      else {
        const a = e.angle * Math.PI / 180, length = 55 / zoom;
        ctx.moveTo(0, 0); ctx.lineTo(Math.cos(a) * length, -Math.sin(a) * length);
        if (e.spread < 360) [-0.5, 0.5].forEach(sign => { const angle = a + e.spread * Math.PI / 180 * sign; ctx.moveTo(0, 0); ctx.lineTo(Math.cos(angle) * length, -Math.sin(angle) * length); });
      }
      if (!edge && ['box', 'circle', 'ring'].includes(e.shape) && !(e.shape === 'ring' && (e.arcAngle || 360) < 360)) { ctx.fillStyle = '#87b9af12'; ctx.fill(); }
      ctx.stroke();
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
      if (bitmap.complete && bitmap.naturalWidth) ctx.drawImage(bitmap, bg.x - bg.image.width * bg.scale / 2, -bg.y - bg.image.height * bg.scale / 2, bg.image.width * bg.scale, bg.image.height * bg.scale);
    }
    const attached = attachedFor();
    const particles = attached ? attached.sample(time) : mode === 'baked' && bakedPreview ? bakedPreview.sample(time) : Core.sample(snapshot, time); let visible = 0;
    const offsets = new Map(), hiddenEmitters = new Set();
    if (mode === 'live') snapshot.project.emitters.forEach(old => {
      const current = project.emitters.find(e => e.id === old.id);
      if (!current || !current.enabled) hiddenEmitters.add(old.id);
      else offsets.set(old.id, {x: current.x - old.x, y: current.y - old.y});
    });
    for (const p of particles) {
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
    if (attached && showBones) drawBones(attached);
    drawGizmos(mode === 'live' ? project : snapshot.project); ctx.restore();
    const statistics = mode === 'baked' && exported ? exported.stats : snapshot.stats;
    $('stats').textContent = '可見 ' + visible + ' · 骨骼 ' + statistics.bones + (statistics.keyframes ? ' · KEY ' + statistics.keyframes.toLocaleString() + ' · JSON ' + (statistics.jsonBytes / 1024).toFixed(0) + ' KB' : ' · ' + snapshot.fps + ' FPS 烘焙');
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
  function syncTimeline() {
    const duration = previewDuration(), fps = activeFps();
    time = clamp(time, 0, duration);
    $('timeline').max = Math.round(duration * fps); $('timeline').step = 1;
    $('timeline').value = Math.round(time * fps);
    $('timeline').setAttribute('aria-valuetext', time.toFixed(2) + ' 秒');
    $('timeLabel').textContent = (currentFlowBake() ? phase.toUpperCase() + ' · ' : '') + time.toFixed(2) + ' / ' + duration.toFixed(2) + ' 秒 · ' + Math.round(time * fps) + ' 幀';
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
  }

  function download(data, name, type) {
    const blob = new Blob([data], {type}); const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  function saveProject() {
    try { download(Storage.serialize(project, baked ? baked.project : null, viewState(), integration), safeName() + '.particle.json', 'application/json'); queueDraft(); notify('已開始下載專案檔，包含參數、素材與烘焙快照。'); }
    catch (error) { notify(error.message, true); }
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
  function exportZip() {
    if (integration && integration.settings.enabled !== false) { exportMergedZip(); return; }
    if (!baked || revision !== bakedRevision || !exported) { notify('請先更新烘焙再輸出。', true); return; }
    try {
      const name = safeName();
      const animationGuide = flowBaked ? ['in', 'loop', 'out'].map(kind => {
        const item = exported.manifest.phases[kind];
        return kind.toUpperCase() + '：' + item.animationName + '，' + item.duration + ' 秒（' + (item.loop ? '反覆播放' : '播放一次') + '）';
      }).join('；') + '。先播 IN，再反覆 LOOP；需要結束時，等 LOOP 完整一輪結束後播放 OUT。' : '播放 effect 動畫。此動畫的循環設定：' + (baked.loop ? '循環；請開啟 Spine 循環播放' : '單次') + '。';
      const entries = [
        {name: name + '.json', data: JSON.stringify(exported.json)},
        {name: name + '.particle.json', data: Storage.serialize(project, baked.project, viewState(), integration)},
        {name: '匯入說明.txt', data: 'Particle Studio 原創粒子工具\n目標：Spine Editor ' + exported.json.skeleton.spine + '\n\n1. 解壓縮此 ZIP。\n2. 在 Spine ' + exported.json.skeleton.spine + ' 使用 File → Import Data，選擇 ' + name + '.json。\n3. Images 路徑指向同層 images/。\n4. ' + animationGuide + '\n5. 存為新的 .spine 專案。需合併到既有動畫時，可透過 Import Project 匯入此專案。\n\n' + name + '.particle.json 是本工具的編輯專案，不是 Spine skeleton。\n背景參考圖不匯出到 Spine；圖集請在 Spine 匯出時建立。\n\n烘焙：' + baked.fps + ' FPS\n骨骼：' + exported.stats.bones + '；關鍵幀：' + exported.stats.keyframes + '\n' + exported.stats.warnings.join('\n')}
      ];
      if (flowBaked) entries.push({name: '動畫段落.json', data: JSON.stringify(exported.manifest, null, 2)});
      exported.images.forEach(image => { entries.push({name: 'images/' + image.name, data: Zip.decodeDataUrl(image.dataUrl || builtinImages.glow.dataUrl)}); });
      download(Zip.create(entries), name + '_spine' + Core.spineProfile(exported.json.skeleton.spine).family + '.zip', 'application/zip');
      notify('已開始下載 ZIP：Spine JSON、圖片、編輯專案與匯入說明。');
    } catch (error) { notify(error.message, true); }
  }
  function exportMergedZip() {
    if (!baked || revision !== bakedRevision || !exported || busy) { notify('請先更新粒子烘焙再輸出追加包。', true); return; }
    try {
      const options = flowBaked ? attachmentUi.validateFlowOptions(exported) : attachmentUi.validateOptions(exported, baked.duration);
      const result = flowBaked ? SpineMerge.mergeFlow(integration.json, exported, options) : SpineMerge.merge(integration.json, exported, options);
      const animationGuide = result.manifest.phases ? ['in', 'loop', 'out'].map(kind => {
        const item = result.manifest.phases[kind];
        return kind.toUpperCase() + ' → ' + item.animationName + '，' + item.startTime + '–' + item.endTime + ' 秒' + (item.loop ? '（反覆播放）' : '（播放一次）');
      }).join('\n') + '\n請在 LOOP 完整一輪結束後接 OUT；任意時點切换需另外設定動畫混合。' : '播放「' + result.manifest.animationName + '」；粒子段落 ' + result.manifest.startTime + '–' + result.manifest.endTime + ' 秒。';
      let stem = integration.fileName.replace(/\.json$/i, '').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/^[. ]+|[. ]+$/g, '').slice(0, 64) || 'spine';
      if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(stem)) stem = 'spine_' + stem;
      const name = stem + '_particles';
      const text = 'Particle Studio v1.9 · 既有 Spine ' + result.json.skeleton.spine + ' 追加包\n\n' +
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
        result.warnings.join('\n');
      const entries = [
        {name: name + '.json', data: JSON.stringify(result.json)},
        {name: name + '.particle.json', data: Storage.serialize(project, baked.project, viewState(), integration)},
        {name: '追加清單.json', data: JSON.stringify(result.manifest, null, 2)},
        {name: '追加說明.txt', data: text}
      ];
      result.images.forEach(asset => entries.push({name: 'new_images/' + asset.name, data: Zip.decodeDataUrl(asset.dataUrl || builtinImages.glow.dataUrl)}));
      download(Zip.create(entries), name + '_append.zip', 'application/zip');
      notify('已開始下載追加包：合併骨架、粒子新素材與掛接設定。原工程請保留並另存新版本。');
    } catch (error) { notify(error.message, true); }
  }
  async function loadImage(file) {
    if (!file || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error('請選擇 PNG、JPEG 或 WebP 圖片。');
    if (file.size > 8 * 1024 * 1024) throw new Error('圖片超過 8 MB，請先縮小素材。');
    const source = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('無法讀取圖片。')); reader.readAsDataURL(file); });
    const image = await new Promise((resolve, reject) => { const i = new Image(); i.onload = () => resolve(i); i.onerror = () => reject(new Error('圖片無法解碼。')); i.src = source; });
    const ratio = Math.min(1, 2048 / Math.max(image.naturalWidth, image.naturalHeight));
    const surface = document.createElement('canvas'); surface.width = Math.max(1, Math.round(image.naturalWidth * ratio)); surface.height = Math.max(1, Math.round(image.naturalHeight * ratio));
    surface.getContext('2d').drawImage(image, 0, 0, surface.width, surface.height);
    const result = {name: file.name, mime: 'image/png', width: surface.width, height: surface.height, dataUrl: surface.toDataURL('image/png')};
    if (result.dataUrl.length > 4 * 1024 * 1024 * 4 / 3) throw new Error('轉換後的 PNG 超過 4 MB，請縮小素材。');
    return result;
  }
  function freshId() { return 'e_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6); }
  function addEmitter() {
    if (project.emitters.length >= 8) return;
    try {
      const preset = $('preset').value; const names = {glow: '柔光粒子', sparks: '迸射火花', coins: '金幣噴發', bubbles: '漂浮氣泡'};
      const e = Core.createEmitter(freshId(), names[preset], preset);
      if (preset !== 'glow') e.image = clone(builtinImages[preset]);
      project.emitters.unshift(e); selectedId = e.id; changed(); renderEmitters(); renderInspector();
    } catch (error) { notify(error.message, true); }
  }
  function setTab(tab) {
    document.querySelectorAll('[data-tab]').forEach(button => { const active = button.dataset.tab === tab; button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active)); });
    document.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== tab; }); drawCurves();
  }

  async function adopt(parsed) {
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
    imageCache.clear(); tintCache.clear();
    attachedCache.clear();
    project = parsed.project; liveFlowBake = nextLiveFlow; liveBake = nextLive; liveError = nextError; flowBaked = nextFlow; baked = nextBaked; exported = nextExport; bakedPreview = nextPreview; selectedId = project.emitters[0].id;
    phase = nextPhase; stopSequence();
    revision = 1; bakedRevision = nextBaked && simulationSignature(nextBaked.project) === simulationSignature(project) ? 1 : -1;
    const view = parsed.view || {}; time = view.time || 0; zoom = view.zoom || 1; panX = view.panX || 0; panY = view.panY || 0; mode = view.mode === 'baked' && baked ? 'baked' : 'live';
    previewAttached = view.previewAttached !== false; showBones = view.showBones !== false; previewSkin = view.skinName || '';
    renderGlobals(); renderEmitters(); renderInspector(); updateBakeStatus();
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
        if (!custom && typeof attachmentUi !== 'undefined' && attachmentUi) custom = attachmentUi.bindingFor(input);
        if (!custom && typeof flowBindingFor === 'function') custom = flowBindingFor(input);
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
        changed(); renderEmitters(); if (key === 'shape' || key === 'emitFrom') renderInspector(); document.querySelectorAll('[data-readout]').forEach(output => { output.textContent = e[output.dataset.readout]; });
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
    $('addEmitter').addEventListener('click', addEmitter);
    $('centerEmitter').addEventListener('click', () => { const e = emitter(); e.x = e.y = 0; changed(); renderInspector(); });
    $('duplicateEmitter').addEventListener('click', () => { if (project.emitters.length >= 8) return; const e = clone(emitter()); e.id = freshId(); e.name = (e.name + ' 複本').slice(0, 80); project.emitters.unshift(e); selectedId = e.id; changed(); renderEmitters(); renderInspector(); });
    $('deleteEmitter').addEventListener('click', () => { if (project.emitters.length <= 1) return; project.emitters = project.emitters.filter(e => e.id !== selectedId); selectedId = project.emitters[0].id; changed(); renderEmitters(); renderInspector(); });
    [['moveEmitterUp', -1], ['moveEmitterDown', 1]].forEach(([id, delta]) => { $(id).addEventListener('click', () => { const index = project.emitters.findIndex(e => e.id === selectedId), next = index + delta; if (next < 0 || next >= project.emitters.length) return; const item = project.emitters.splice(index, 1)[0]; project.emitters.splice(next, 0, item); changed(); renderEmitters(); }); });
    $('saveProject').addEventListener('click', saveProject); $('bakeButton').addEventListener('click', bakeNow); $('exportButton').addEventListener('click', exportZip);
    $('spineVersion').addEventListener('change', () => {
      if (integration && integration.settings.enabled !== false) { updateBakeStatus(); return; }
      try { project.spineVersion = Core.spineProfile($('spineVersion').value).version; updateBakeStatus(); queueDraft(); notify('輸出版本已切換至 Spine ' + project.spineVersion + '。'); }
      catch (error) { renderGlobals(); notify(error.message, true); }
    });
    $('loadProject').addEventListener('click', () => $('projectFile').click());
    $('projectFile').addEventListener('change', async event => {
      const file = event.target.files[0]; if (!file) return;
      try { if (file.size > 48 * 1024 * 1024) throw new Error('專案檔超過 48 MB。'); const parsed = Storage.parse(await file.text(), Core); await adopt(parsed); queueDraft(); notify(liveError ? '已載入專案，請調整參數：' + liveError : '已載入專案與素材。', !!liveError); }
      catch (error) { notify(error.message, true); } finally { event.target.value = ''; }
    });
    $('modeLive').addEventListener('click', () => { stopSequence(); mode = 'live'; updateBakeStatus(); queueDraft(); });
    $('modeBaked').addEventListener('click', () => { if (!baked) return; stopSequence(); mode = 'baked'; updateBakeStatus(); queueDraft(); });
    $('playButton').addEventListener('click', () => { const snapshot = activeBake(); if (!snapshot || attachedMode() && !attachedFor()) return; playing = !playing; if (playing && time >= previewDuration()) time = 0; refreshFlowUi(); updatePlayButton(); queueDraft(); });
    $('restartButton').addEventListener('click', () => { stopSequence(); time = 0; refreshFlowUi(); syncTimeline(); queueDraft(); });
    $('timeline').addEventListener('input', () => { stopSequence(); playing = false; time = Number($('timeline').value) / activeFps(); refreshFlowUi(); updatePlayButton(); syncTimeline(); queueDraft(); });
    [['framePrev', -1], ['frameNext', 1]].forEach(([id, delta]) => { $(id).addEventListener('click', () => { const snapshot = activeBake(); if (!snapshot) return; const fps = activeFps(); stopSequence(); playing = false; time = clamp((Math.round(time * fps) + delta) / fps, 0, previewDuration()); refreshFlowUi(); updatePlayButton(); syncTimeline(); queueDraft(); }); });
    $('zoom').addEventListener('input', () => { zoom = Number($('zoom').value) / 100; $('zoomLabel').textContent = Math.round(zoom * 100) + '%'; queueDraft(); });
    $('centerView').addEventListener('click', () => { panX = panY = 0; zoom = 1; renderGlobals(); queueDraft(); });
    $('backgroundColor').addEventListener('input', () => { project.background.color = $('backgroundColor').value; queueDraft(); });
    $('backgroundButton').addEventListener('click', () => $('backgroundFile').click());
    $('backgroundFile').addEventListener('change', async event => {
      try {
        const file = event.target.files[0]; if (!file) return;
        const image = await loadImage(file);
        const candidate = {...project, background: {...project.background, image, scale: clamp(Math.min(stageW / image.width, stageH / image.height) / zoom * 0.9, 0.01, 20)}};
        project.background = Core.normalizeProject(candidate).background; renderGlobals(); queueDraft();
      } catch (error) { notify(error.message, true); } finally { event.target.value = ''; }
    });
    $('removeBackground').addEventListener('click', () => { project.background.image = null; renderGlobals(); queueDraft(); });
    $('textureButton').addEventListener('click', () => $('textureFile').click());
    $('textureFile').addEventListener('change', async event => { const selected = emitter(); try { const file = event.target.files[0]; if (!file) return; const image = await loadImage(file); const previous = selected.image; selected.image = image; try { Core.normalizeProject(project); } catch (error) { selected.image = previous; throw error; } changed(); renderEmitters(); renderInspector(); } catch (error) { notify(error.message, true); } finally { event.target.value = ''; } });
    $('removeTexture').addEventListener('click', () => { emitter().image = null; changed(); renderEmitters(); renderInspector(); });
    document.querySelectorAll('[data-tab]').forEach(button => { button.addEventListener('click', () => setTab(button.dataset.tab)); });
    const tabs = Array.from(document.querySelectorAll('[data-tab]'));
    document.querySelector('.inspector-tabs').addEventListener('keydown', event => { if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return; const index = tabs.indexOf(event.target); if (index < 0) return; event.preventDefault(); const target = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]; target.focus(); target.click(); });
    $('helpButton').addEventListener('click', () => $('helpDialog').showModal()); $('closeHelp').addEventListener('click', () => $('helpDialog').close());
    const lifecycleChange = () => { changed(); renderEmitters(); drawCurves(); };
    curveEditor = window.ParticleCurveEditor.mount({getEmitter: emitter, onChange: lifecycleChange, math: window.ParticleCurveMath, Core});
    gradientEditor = window.ParticleGradientEditor.mount({getEmitter: emitter, onChange: lifecycleChange, math: window.ParticleCurveMath, Core});
    canvas.addEventListener('contextmenu', event => event.preventDefault());
    canvas.addEventListener('pointerdown', event => {
      if (![0, 1, 2].includes(event.button)) return;
      interaction = {type: 'pan', x: event.clientX, y: event.clientY, originalX: panX, originalY: panY};
      canvas.setPointerCapture(event.pointerId); event.preventDefault();
    });
    canvas.addEventListener('pointermove', moveInteraction);
    canvas.addEventListener('pointerup', finishInteraction); canvas.addEventListener('pointercancel', finishInteraction); canvas.addEventListener('lostpointercapture', finishInteraction);
    handleLayer.addEventListener('contextmenu', event => event.preventDefault());
    $('canvasStage').addEventListener('wheel', event => { event.preventDefault(); zoom = clamp(zoom * Math.exp(-event.deltaY * 0.001), 0.25, 2); $('zoom').value = Math.round(zoom * 100); $('zoomLabel').textContent = Math.round(zoom * 100) + '%'; queueDraft(); }, {passive: false});
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveProject(); return; }
      if (event.target.closest('input,select,textarea,button,canvas.curve-canvas') || $('helpDialog').open || $('spineMergeDialog').open || $('flowDialog').open) return;
      if (event.code === 'Space') { event.preventDefault(); $('playButton').click(); }
      if (event.key === 'ArrowLeft') { event.preventDefault(); $('framePrev').click(); }
      if (event.key === 'ArrowRight') { event.preventDefault(); $('frameNext').click(); }
    });
    let priorAssets = integration && integration.assets, priorSource = integration && integration.json;
    const integrationChanged = () => {
      if (priorAssets !== (integration && integration.assets) || priorSource !== (integration && integration.json)) { imageCache.clear(); tintCache.clear(); }
      priorAssets = integration && integration.assets; priorSource = integration && integration.json;
      attachedCache.clear(); queueDraft(); updateBakeStatus();
    };
    attachmentUi = window.ParticleSpineAttachmentUI.mount({Merge: SpineMerge, getProject: () => project,
      getSession: () => integration, setSession: value => {
        const newSource = value && (!integration || value.json !== integration.json);
        integration = value;
        if (newSource) { previewAttached = true; previewSkin = ''; time = 0; stopSequence(); }
      },
      onChange: integrationChanged, onExport: exportMergedZip, onBake: bakeNow, managePreviewChip: false,
      canExport: () => !!baked && revision === bakedRevision && !!exported && !busy, notify});
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
    wireNumberScrub();
    window.addEventListener('pagehide', () => { try { Storage.saveDraft(JSON.parse(Storage.serialize(project, baked ? baked.project : null, viewState(), integration))).catch(() => {}); } catch (_) {} });
  }

  async function init() {
    project.name = '金色光塵'; project.emitters[0].shape = 'box'; project.emitters[0].width = 180; project.emitters[0].height = 30; project.emitters[0].count = 48; project.emitters[0].emissionDuration = 3; project.emitters[0].spread = 70; project.emitters[0].size = 18; project.emitters[0].speed = 90;
    refreshLive(); renderGlobals(); renderEmitters(); renderInspector(); wireEvents(); updateBakeStatus(); updatePlayButton();
    new ResizeObserver(resize).observe($('canvasStage')); new ResizeObserver(drawCurves).observe(document.querySelector('.inspector'));
    resize(); requestAnimationFrame(animate);
    const startingProject = project, startingRevision = revision, startingIntegration = integration;
    try {
      const draft = await Storage.loadDraft();
      if (draft && project === startingProject && revision === startingRevision && integration === startingIntegration) { await adopt(Storage.parse(JSON.stringify(draft), Core)); $('appStatus').textContent = '已恢復本機草稿'; }
      else $('appStatus').textContent = '就緒 · 圖片與運算留在本機';
    } catch (error) { $('appStatus').textContent = '草稿恢復不可用，請使用專案檔'; }
    initialized = true;
  }
  init().catch(error => { notify('初始化失敗：' + error.message, true); $('appStatus').textContent = '請重新開啟工具'; });
})();
