(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleSpineAttachmentUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const owns = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const phases = ['in', 'loop', 'out'];
  function mount({Merge, EffectUpdate, getEffectiveSession, getProject, getSession, setSession, getGeneration, onChange, onExport, onBake, onPickBone, canExport, notify, managePreviewChip = true, document: doc = document}) {
    const $ = id => doc.getElementById(id);
    const ids = ['spineMergeButton', 'spineMergeDialog', 'spineCloseMerge', 'spineCloseMergeFooter',
      'spineLoadSource', 'spineSourceFile', 'spineClearSource', 'spineSourceInfo', 'spineMergeEnabled',
      'spineMergeFields', 'spineParentFilter', 'spineParentBone', 'spineParentPath', 'spineAnimationMode',
      'spineAnimationSelect', 'spineExistingAnimationField', 'spineNewAnimationField', 'spineNewAnimation',
      'spineStartTime', 'spineDrawOrder', 'spineAfterSlotField', 'spineAfterSlot', 'spinePrefix',
      'spineEmitterBindings', 'spineMergeSummary', 'spineBakeMerge', 'spineExportMerge', 'spineTargetChip', 'spineMergeFeedback',
      'spineSingleAnimationFields', 'spineFlowAnimationFields', 'spineFlowHint', 'spineLoadReceipt', 'spineReceiptFile', 'spineUpdateMode', 'spineUpdateModeField', 'spineUpdateInfo'];
    const ui = Object.fromEntries(ids.map(id => [id, $(id)]));
    const flowRows = Object.fromEntries(phases.map(phase => {
      const stem = 'spineFlow' + phase[0].toUpperCase() + phase.slice(1);
      return [phase, Object.fromEntries(['Mode', 'Select', 'Name', 'Start', 'ExistingField', 'NewField'].map(key => [key, $(stem + key)]))];
    }));
    let source = null, info = null, bindingsSignature = '', contextSignature = '', loading = false, sourceRequest = 0;
    const bindingRows = new Map();
    function activeSession() { return typeof getEffectiveSession === 'function' ? getEffectiveSession() : getSession(); }
    function baseJson() { const session = activeSession(); return session && session.json; }
    function refreshUpdate() {
      if (!ui.spineLoadReceipt) return;
      const session = getSession(), update = session && session.update;
      ui.spineLoadReceipt.disabled = !session || loading;
      ui.spineUpdateModeField.hidden = !update;
      ui.spineUpdateMode.disabled = loading;
      ui.spineUpdateMode.value = update ? update.mode : 'append';
      ui.spinePrefix.disabled = !!update && update.mode === 'replace';
      ui.spinePrefix.maxLength = update && update.mode === 'replace' ? 64 : 48;
      if (!update) { ui.spineUpdateInfo.textContent = '只有記錄中確認屬於該效果的資料會被更新。'; return; }
      try {
        const summary = EffectUpdate.inspectReceipt(update.receipt, session.json).summary;
        ui.spineUpdateInfo.textContent = '群組 ' + summary.namespace + ' · ' + summary.removedBones + ' 骨骼 · ' + summary.removedSlots + ' 插槽 · ' + summary.animations.join('、') + (update.mode === 'replace' ? ' · 預覽與輸出會替換此效果' : ' · 保留原效果，另追加一組') + (summary.legacy ? '。舊版記錄會保留原動畫容器。' : '。');
      } catch (error) { ui.spineUpdateInfo.textContent = error.message; }
    }
    function adaptAnimationModes(settings, json) {
      const mode = name => owns(json.animations || {}, name) ? 'existing' : 'new';
      settings.animationMode = mode(settings.animationName);
      Object.values(settings.flowTargets || {}).forEach(target => { target.animationMode = mode(target.animationName); });
    }
    function prepareUpdate(session, raw, restoreSettings) {
      const cleaned = EffectUpdate.remove(session.json, raw), receipt = cleaned.receipt, manifest = receipt.manifest;
      const settings = clone(session.settings);
      if (restoreSettings) {
        ['parentBone', 'emitterParents', 'emitterLayers', 'drawOrder', 'afterSlot'].forEach(key => {
          if (manifest[key] !== undefined) settings[key] = clone(manifest[key]);
          else if (key === 'emitterLayers') delete settings[key];
        });
        if (manifest.phases) settings.flowTargets = Object.fromEntries(phases.map(phase => {
          const target = manifest.phases[phase];
          return [phase, {animationName: target.animationName, startTime: target.startTime || 0}];
        }));
        else { settings.animationName = manifest.animationName; settings.startTime = manifest.startTime || 0; }
      }
      settings.prefix = manifest.namespace;
      adaptAnimationModes(settings, cleaned.json);
      // Validate against the cleaned source before changing the live session.
      Merge.normalizeSession({fileName: session.fileName, json: cleaned.json, settings});
      const next = Merge.normalizeSession({...session, settings, update: {mode: 'replace', receipt}});
      next.json = session.json;
      if (session.assets) next.assets = session.assets;
      return next;
    }
    function option(select, value, label) {
      const node = doc.createElement('option'); node.value = value; node.textContent = label; select.append(node);
    }
    function fill(select, entries, value) {
      select.replaceChildren(); entries.forEach(([v, label]) => option(select, v, label)); select.value = value;
      if (select.selectedIndex < 0 && select.options.length) select.selectedIndex = 0;
    }
    function bonePath(name) {
      const byName = new Map(info.bones.map(b => [b.name, b])), path = [];
      let bone = byName.get(name);
      while (bone) { path.unshift(bone.name); bone = byName.get(bone.parent); }
      return path.join(' / ');
    }
    function boneEntries(filter) {
      const query = (filter || '').trim().toLowerCase();
      const selected = getSession().settings.parentBone;
      return info.bones.filter(b => b.name === selected || !query || b.name.toLowerCase().includes(query))
        .map(b => [b.name, bonePath(b.name)]);
    }
    function selectedAnimationMode(session) { return session.settings.animationMode || (owns(baseJson().animations || {}, session.settings.animationName) ? 'existing' : 'new'); }
    function flowEnabled() { return !!(getProject().flow && getProject().flow.enabled); }
    function ensureFlowTargets() {
      const session = getSession(); if (!session || !flowEnabled() || session.settings.flowTargets) return;
      const targets = {}, used = new Set();
      phases.forEach(phase => {
        const existing = info.animations.find(animation => animation.name.toLowerCase() === phase);
        const stem = getProject().flow[phase].name || phase;
        let animationName = existing ? existing.name : stem, index = 2;
        if (!existing) while (owns(baseJson().animations || {}, animationName) || used.has(animationName)) animationName = stem + '_' + index++;
        used.add(animationName); targets[phase] = {animationName, animationMode: existing ? 'existing' : 'new', startTime: 0};
      });
      session.settings.flowTargets = targets;
    }
    function flowIssue(exported) {
      const session = getSession(), targets = session && session.settings.flowTargets;
      if (!targets) return '請設定 IN、LOOP、OUT 三段的目標動畫。';
      const names = new Set();
      for (const phase of phases) {
        const target = targets[phase];
        if (!target || !target.animationName.trim()) return phase.toUpperCase() + ' 請設定目標動畫名稱。';
        if (names.has(target.animationName)) return 'IN、LOOP、OUT 必須選擇三個不同的目標動畫。';
        names.add(target.animationName);
        const original = info.animations.find(animation => animation.name === target.animationName);
        if (target.animationMode === 'new' && original) return phase.toUpperCase() + ' 新動畫名稱已存在，請選擇追加至原動畫或設定其他名稱。';
        if (target.animationMode === 'existing' && !original) return phase.toUpperCase() + ' 目標動畫不存在。';
        if (phase === 'loop') {
          if (target.startTime !== 0) return 'LOOP 必須從 0 秒開始，才能連續重播完整動畫。';
          const duration = exported ? exported.manifest.phases.loop.duration : getProject().flow.loop.duration;
          if (original && original.duration > duration + .000001) return '原 LOOP 動畫 ' + original.duration.toFixed(2) + ' 秒，長於粒子 LOOP ' + duration.toFixed(2) + ' 秒；請增加 LOOP 長度或新增動畫。';
        }
      }
      return '';
    }
    function commit() { ui.spineMergeFeedback.hidden = true; onChange(); refresh(); }
    function summary() {
      const session = getSession(), enabled = session && session.settings.enabled !== false;
      ui.spineTargetChip.hidden = !enabled;
      ui.spineMergeButton.classList.toggle('attached', !!enabled);
      ui.spineMergeButton.querySelector('span').textContent = session ? '掛接設定' : '掛接骨架';
      if (!session) {
        ui.spineMergeSummary.textContent = '載入原骨架後，選擇粒子的父骨骼與要追加的動畫。'; return;
      }
      const settings = session.settings;
      const custom = Object.values(settings.emitterParents || {}).filter(Boolean).length;
      ui.spineParentPath.textContent = bonePath(settings.parentBone);
      ui.spineAfterSlotField.hidden = settings.drawOrder !== 'after';
      const mode = selectedAnimationMode(session);
      ui.spineExistingAnimationField.hidden = mode !== 'existing'; ui.spineNewAnimationField.hidden = mode !== 'new';
      const flow = flowEnabled(); ui.spineSingleAnimationFields.hidden = flow; ui.spineFlowAnimationFields.hidden = !flow;
      if (flow) {
        const targets = settings.flowTargets, issue = flowIssue();
        ui.spineMergeSummary.textContent = '輸出 Spine ' + info.version + ' · ' + phases.map(phase => phase.toUpperCase() + ' → ' + targets[phase].animationName).join(' · ') +
          (issue ? ' · ' + issue : canExport() ? ' · 可輸出三段追加包（自動烘焙）' : ' · 正在更新粒子烘焙');
        if (managePreviewChip) ui.spineTargetChip.textContent = '掛接骨架 · 父骨骼 ' + settings.parentBone + (custom ? '＋自訂掛接' : '') + ' · IN / LOOP / OUT';
        ui.spineFlowHint.textContent = issue || '三段使用同一組粒子骨骼與素材。LOOP 從 0 秒循環，在完整循環邊界接 OUT，以 0 混合時間銜接。';
        if (managePreviewChip) ui.spineTargetChip.title = '合併輸出保留 Spine ' + info.version + '；載入角色素材可在畫布檢查掛接位置。';
        return;
      }
      const duration = getProject().duration, end = settings.startTime + duration;
      ui.spineMergeSummary.textContent = '輸出 Spine ' + info.version + ' · ' + (mode === 'existing' ? '追加至 ' : '新增動畫 ') + settings.animationName +
        ' · ' + settings.startTime.toFixed(2) + '–' + end.toFixed(2) + ' 秒 · ' + (custom ? custom + ' 個發射器自訂掛接' : '使用預設父骨骼') +
        (canExport() ? ' · 可輸出追加包（自動烘焙）' : ' · 正在更新粒子烘焙');
      if (managePreviewChip) {
        ui.spineTargetChip.textContent = '掛接骨架 · 父骨骼 ' + settings.parentBone + (custom ? '＋自訂掛接' : '') + ' · ' + settings.animationName;
        ui.spineTargetChip.title = '合併輸出保留原骨架的 Spine ' + info.version + ' 版本。粒子 X/Y 是父骨骼的局部座標；載入角色素材可在畫布檢查掛接位置。';
      }
    }
    function refreshBindings() {
      const project = getProject(), session = getSession();
      const signature = JSON.stringify([project.emitters.map(e => [e.id, e.name, e.enabled]), session.settings.emitterParents, session.settings.emitterLayers, session.settings.enabled]);
      if (signature === bindingsSignature) return; bindingsSignature = signature;
      const keep = new Set(project.emitters.map(e => e.id));
      for (const [id, row] of bindingRows) if (!keep.has(id)) { row.element.remove(); bindingRows.delete(id); }
      project.emitters.forEach(e => {
        let row = bindingRows.get(e.id);
        if (!row) {
          const element = doc.createElement('div'); element.className = 'spine-binding-row'; element.setAttribute('data-emitter-id', e.id);
          const heading = doc.createElement('div'); heading.className = 'spine-binding-heading';
          const label = doc.createElement('span'), select = doc.createElement('select'), pick = doc.createElement('button');
          pick.type = 'button'; pick.className = 'text-button emitter-bone-pick'; pick.textContent = '畫布選骨骼'; pick.hidden = typeof onPickBone !== 'function';
          pick.setAttribute('data-emitter-id', e.id); pick.addEventListener('click', () => { if (typeof onPickBone === 'function') onPickBone(e.id); });
          heading.append(label, pick); select.className = 'emitter-parent-select'; select.setAttribute('data-emitter-id', e.id);
          select.setAttribute('aria-label', e.name + ' 的父骨骼');
          const parentField = doc.createElement('label'); parentField.className = 'field';
          const parentLabel = doc.createElement('span'); parentLabel.textContent = '父骨骼'; parentField.append(parentLabel, select);
          const layer = doc.createElement('select'); layer.className = 'emitter-layer-select'; layer.setAttribute('data-emitter-id', e.id);
          const slot = doc.createElement('select'); slot.className = 'emitter-layer-slot-select'; slot.setAttribute('data-emitter-id', e.id);
          const layerField = doc.createElement('label'); layerField.className = 'field';
          const layerLabel = doc.createElement('span'); layerLabel.textContent = '前後圖層'; layerField.append(layerLabel, layer);
          const slotField = doc.createElement('label'); slotField.className = 'field';
          const slotLabel = doc.createElement('span'); slotLabel.textContent = '參考插槽'; slotField.append(slotLabel, slot);
          const fields = doc.createElement('div'); fields.className = 'spine-binding-layer-fields'; fields.append(layerField, slotField);
          element.append(heading, parentField, fields); row = {element, label, select, pick, layer, slot, slotField}; bindingRows.set(e.id, row);
          select.addEventListener('change', () => {
            const settings = getSession().settings, key = 'em_' + e.id;
            if (select.value) Object.defineProperty(settings.emitterParents, key, {value: select.value, writable: true, enumerable: true, configurable: true});
            else delete settings.emitterParents[key];
            commit();
          });
          const applyLayer = () => {
            const session = getSession(); if (!session) return;
            const key = 'em_' + e.id, settings = session.settings;
            if (!layer.value) {
              if (settings.emitterLayers) { delete settings.emitterLayers[key]; if (!Object.keys(settings.emitterLayers).length) delete settings.emitterLayers; }
            } else {
              if (!['front', 'back', 'after'].includes(layer.value)) return;
              if (layer.value === 'after' && !info.slots.some(item => item.name === slot.value)) return;
              if (!settings.emitterLayers) settings.emitterLayers = {};
              Object.defineProperty(settings.emitterLayers, key, {value: {drawOrder: layer.value, afterSlot: layer.value === 'after' ? slot.value : ''}, writable: true, enumerable: true, configurable: true});
            }
            commit();
          };
          layer.addEventListener('change', applyLayer); slot.addEventListener('change', applyLayer);
        }
        row.label.textContent = e.name + (e.enabled ? '' : '（停用）'); row.select.disabled = !e.enabled;
        row.pick.disabled = !e.enabled || session.settings.enabled === false;
        row.select.setAttribute('aria-label', e.name + ' 的父骨骼');
        fill(row.select, [['', '使用預設父骨骼'], ...info.bones.map(b => [b.name, bonePath(b.name)])], session.settings.emitterParents['em_' + e.id] || '');
        const override = session.settings.emitterLayers && session.settings.emitterLayers['em_' + e.id];
        fill(row.layer, [['', '沿用共用圖層'], ['front', '最前方'], ['back', '最後方'], ...(info.slots.length ? [['after', '指定插槽之後']] : [])], override ? override.drawOrder : '');
        fill(row.slot, info.slots.map(s => [s.name, s.name]), override && override.afterSlot || session.settings.afterSlot || (info.slots[0] || {}).name || '');
        row.slotField.hidden = !override || override.drawOrder !== 'after'; row.layer.disabled = row.slot.disabled = !e.enabled;
        row.layer.setAttribute('aria-label', e.name + ' 的前後圖層'); row.slot.setAttribute('aria-label', e.name + ' 的參考插槽');
        ui.spineEmitterBindings.append(row.element);
      });
    }
    function refresh() {
      const session = getSession(), valid = !!session;
      refreshUpdate();
      ui.spineMergeEnabled.disabled = !valid; ui.spineMergeEnabled.checked = valid && session.settings.enabled !== false;
      ui.spineClearSource.disabled = !valid; ui.spineMergeFields.hidden = !valid;
      ui.spineExportMerge.disabled = !valid || session.settings.enabled === false || !canExport();
      ui.spineBakeMerge.disabled = loading;
      if (source !== baseJson()) {
        source = baseJson(); info = source ? Merge.inspect(source) : null;
        bindingsSignature = ''; contextSignature = ''; bindingRows.clear(); ui.spineEmitterBindings.replaceChildren();
        ui.spineParentFilter.value = '';
      }
      if (!valid) {
        ui.spineSourceInfo.textContent = '尚未載入原骨架'; contextSignature = ''; summary(); return;
      }
      ensureFlowTargets();
      ui.spineSourceInfo.textContent = session.fileName + ' · Spine ' + info.version + ' · ' + info.bones.length + ' 骨骼 · ' + info.slots.length + ' 插槽 · ' + info.animations.length + ' 動畫';
      const settings = session.settings, fingerprint = JSON.stringify([settings, getProject().flow || null]);
      ui.spineAnimationMode.options[0].disabled = !info.animations.length;
      ui.spineDrawOrder.options[2].disabled = !info.slots.length;
      if (fingerprint !== contextSignature) {
        contextSignature = fingerprint;
        fill(ui.spineParentBone, boneEntries(ui.spineParentFilter.value), settings.parentBone);
        fill(ui.spineAnimationSelect, info.animations.map(a => [a.name, a.name + ' · ' + a.duration.toFixed(2) + ' 秒']), settings.animationName);
        fill(ui.spineAfterSlot, info.slots.map(s => [s.name, s.name]), settings.afterSlot || (info.slots[0] && info.slots[0].name) || '');
        ui.spineAnimationMode.value = selectedAnimationMode(session);
        if (doc.activeElement !== ui.spineNewAnimation) ui.spineNewAnimation.value = selectedAnimationMode(session) === 'new' ? settings.animationName : 'particle_effect';
        if (doc.activeElement !== ui.spineStartTime) ui.spineStartTime.value = String(settings.startTime);
        if (doc.activeElement !== ui.spinePrefix) ui.spinePrefix.value = settings.prefix;
        ui.spineDrawOrder.value = settings.drawOrder;
        if (settings.flowTargets) phases.forEach(phase => {
          const row = flowRows[phase], target = settings.flowTargets[phase];
          row.Mode.options[0].disabled = !info.animations.length; row.Mode.value = target.animationMode;
          fill(row.Select, info.animations.map(animation => [animation.name, animation.name + ' · ' + animation.duration.toFixed(2) + ' 秒']), target.animationName);
          row.ExistingField.hidden = target.animationMode !== 'existing'; row.NewField.hidden = target.animationMode !== 'new';
          if (doc.activeElement !== row.Name) row.Name.value = target.animationMode === 'new' ? target.animationName : getProject().flow && getProject().flow[phase].name || phase;
          if (doc.activeElement !== row.Start) row.Start.value = String(target.startTime);
          row.Start.disabled = phase === 'loop';
        });
        bindingsSignature = '';
      }
      refreshBindings(); summary();
      if (flowEnabled() && flowIssue()) ui.spineExportMerge.disabled = true;
    }
    function filteredParents(exported, settings) {
      const boneNames = new Set(exported.json.bones.map(bone => bone.name)), parents = {};
      Object.entries(settings.emitterParents || {}).forEach(([name, parent]) => {
        if (boneNames.has(name) && parent) Object.defineProperty(parents, name, {value: parent, enumerable: true});
      });
      return parents;
    }
    function exportSettings(exported, settings) {
      const result = {...settings, emitterParents: filteredParents(exported, settings)};
      if (settings.emitterLayers) {
        const names = new Set(exported.json.bones.filter(b => b.parent === 'root').map(b => b.name));
        const entries = Object.entries(settings.emitterLayers).filter(([name]) => names.has(name));
        if (entries.length) result.emitterLayers = Object.fromEntries(entries);
        else delete result.emitterLayers;
      }
      return result;
    }
    function validateOptions(exported, duration) {
      const session = getSession(); if (!session || session.settings.enabled === false) throw new Error('請先載入並啟用既有骨架掛接。');
      const settings = session.settings;
      if (!settings.animationName.trim()) throw new Error('請設定目標動畫名稱。');
      if (ui.spineAnimationMode.value === 'new' && owns(baseJson().animations || {}, settings.animationName)) throw new Error('此動畫名稱已存在；請選擇追加至原動畫，或設定新的名稱。');
      return {...exportSettings(exported, settings), duration};
    }
    function validateFlowOptions(exported) {
      const session = getSession(); if (!session || session.settings.enabled === false) throw new Error('請先載入並啟用既有骨架掛接。');
      ensureFlowTargets();
      if (!exported.manifest || !exported.manifest.phases || !exported.manifest.phases.loop) throw new Error('請先更新 IN、LOOP、OUT 三段烘焙。');
      const issue = flowIssue(exported); if (issue) throw new Error(issue);
      return {...exportSettings(exported, session.settings), flowTargets: clone(session.settings.flowTargets)};
    }
    ui.spineMergeButton.addEventListener('click', () => { ui.spineMergeFeedback.hidden = true; refresh(); ui.spineMergeDialog.showModal(); });
    [ui.spineCloseMerge, ui.spineCloseMergeFooter].forEach(button => button.addEventListener('click', () => ui.spineMergeDialog.close()));
    ui.spineLoadSource.addEventListener('click', () => ui.spineSourceFile.click());
    if (ui.spineLoadReceipt && EffectUpdate) {
      ui.spineLoadReceipt.addEventListener('click', () => ui.spineReceiptFile.click());
      ui.spineReceiptFile.addEventListener('change', async event => {
        const file = event.target.files[0], session = getSession(); if (!file || !session) return;
        const request = ++sourceRequest, generation = typeof getGeneration === 'function' ? getGeneration() : null;
        loading = true; refresh();
        try {
          if (file.size > 8 * 1024 * 1024) throw new Error('效果更新記錄超過 8 MiB。');
          const text = await file.text();
          if (request !== sourceRequest || getSession() !== session || typeof getGeneration === 'function' && getGeneration() !== generation) return;
          let raw; try { raw = JSON.parse(text.replace(/^\uFEFF/, '')); } catch (_) { throw new Error('效果更新記錄不是有效的 JSON。'); }
          const next = prepareUpdate(session, raw, true);
          setSession(next); commit(); notify('已確認原效果，掛接預覽與輸出將更新這組粒子。');
        } catch (error) { notify(error.message, true); }
        finally { loading = false; event.target.value = ''; refresh(); }
      });
      ui.spineUpdateMode.addEventListener('change', () => {
        const session = getSession(); if (!session || !session.update || loading) return;
        try {
          let next;
          if (ui.spineUpdateMode.value === 'replace') next = prepareUpdate(session, session.update.receipt, false);
          else {
            const settings = clone(session.settings); adaptAnimationModes(settings, session.json);
            next = Merge.normalizeSession({...session, settings, update: {...session.update, mode: 'append'}});
            next.json = session.json;
            if (session.assets) next.assets = session.assets;
          }
          setSession(next); commit();
        } catch (error) { notify(error.message, true); refresh(); }
      });
    }
    ui.spineSourceFile.addEventListener('change', async event => {
      const file = event.target.files[0]; if (!file) return;
      const request = ++sourceRequest, generation = typeof getGeneration === 'function' ? getGeneration() : null;
      loading = true; refresh();
      try {
        if (/\.spine$/i.test(file.name)) throw new Error('原生 .spine 請先用附帶的「Spine 工程轉換」或 Spine 的 JSON 匯出，再載入此處。');
        if (file.size > 32 * 1024 * 1024) throw new Error('骨架 JSON 超過 32 MiB，請縮小匯出資料。');
        const text = await file.text();
        if (request !== sourceRequest || typeof getGeneration === 'function' && getGeneration() !== generation) return;
        let json; try { json = JSON.parse(text.replace(/^\uFEFF/, '')); } catch (_) { throw new Error('這個檔案不是有效的 Spine JSON。'); }
        const inspected = Merge.inspect(json), first = inspected.animations[0];
        const next = Merge.normalizeSession({fileName: file.name, json, settings: {enabled: true,
          animationMode: first ? 'existing' : 'new', animationName: first ? first.name : 'particle_effect'}});
        if (request !== sourceRequest || typeof getGeneration === 'function' && getGeneration() !== generation) return;
        setSession(next); commit(); notify('已載入原骨架；請選擇父骨骼、動畫與圖層。');
      } catch (error) { notify(error.message, true); }
      finally { loading = false; event.target.value = ''; refresh(); }
    });
    ui.spineClearSource.addEventListener('click', () => { sourceRequest++; setSession(null); commit(); });
    ui.spineMergeEnabled.addEventListener('change', () => { const s = getSession(); if (s) { s.settings.enabled = ui.spineMergeEnabled.checked; commit(); } });
    ui.spineParentFilter.addEventListener('input', () => { if (getSession()) fill(ui.spineParentBone, boneEntries(ui.spineParentFilter.value), getSession().settings.parentBone); });
    [[ui.spineParentBone, 'parentBone'], [ui.spineAnimationSelect, 'animationName'], [ui.spineAfterSlot, 'afterSlot']].forEach(([input, key]) => {
      input.addEventListener('change', () => { const s = getSession(); if (s) { s.settings[key] = input.value; commit(); } });
    });
    ui.spineDrawOrder.addEventListener('change', () => {
      const s = getSession(); if (!s) return;
      if (ui.spineDrawOrder.value === 'after') {
        if (!info.slots.length) { s.settings.drawOrder = 'front'; ui.spineDrawOrder.value = 'front'; commit(); return; }
        if (!s.settings.afterSlot) s.settings.afterSlot = ui.spineAfterSlot.value || info.slots[0].name;
      }
      s.settings.drawOrder = ui.spineDrawOrder.value; commit();
    });
    ui.spineAnimationMode.addEventListener('change', () => {
      const s = getSession(); if (!s) return;
      s.settings.animationMode = ui.spineAnimationMode.value;
      if (ui.spineAnimationMode.value === 'existing') {
        if (!info.animations.length) { s.settings.animationMode = 'new'; ui.spineAnimationMode.value = 'new'; commit(); return; }
        s.settings.animationName = ui.spineAnimationSelect.value || info.animations[0].name;
      } else {
        let name = ui.spineNewAnimation.value.trim() || 'particle_effect', index = 2;
        const stem = name; while (owns(baseJson().animations || {}, name)) name = stem + '_' + index++;
        s.settings.animationName = name;
      }
      commit();
    });
    [[ui.spineStartTime, 'startTime'], [ui.spinePrefix, 'prefix'], [ui.spineNewAnimation, 'animationName']].forEach(([input, key]) => {
      const apply = () => {
        const s = getSession(); if (!s || !input.value.trim() || !input.checkValidity()) return;
        const value = key === 'startTime' ? input.valueAsNumber : input.value.trim();
        if (s.settings[key] === value) return; s.settings[key] = value; commit();
      };
      input.addEventListener('input', apply); input.addEventListener('change', apply);
      input.addEventListener('blur', () => { const s = getSession(); if (s) input.value = String(s.settings[key]); });
    });
    phases.forEach(phase => {
      const row = flowRows[phase], target = () => getSession() && getSession().settings.flowTargets && getSession().settings.flowTargets[phase];
      row.Mode.addEventListener('change', () => {
        const value = target(); if (!value) return;
        value.animationMode = row.Mode.value;
        if (value.animationMode === 'existing') {
          if (!info.animations.length) { value.animationMode = 'new'; commit(); return; }
          value.animationName = row.Select.value || info.animations[0].name;
        } else {
          const stem = row.Name.value.trim() || getProject().flow[phase].name || phase;
          let next = stem, index = 2;
          const used = new Set(phases.filter(other => other !== phase).map(other => getSession().settings.flowTargets[other].animationName));
          while (owns(baseJson().animations || {}, next) || used.has(next)) next = stem + '_' + index++;
          value.animationName = next;
        }
        commit();
      });
      row.Select.addEventListener('change', () => { const value = target(); if (value) { value.animationName = row.Select.value; commit(); } });
      [[row.Name, 'animationName'], [row.Start, 'startTime']].forEach(([input, key]) => {
        const apply = () => {
          const value = target(); if (!value || input.disabled || !input.value.trim() || !input.checkValidity()) return;
          const next = key === 'startTime' ? input.valueAsNumber : input.value.trim();
          if (value[key] !== next) { value[key] = next; commit(); }
        };
        input.addEventListener('input', apply); input.addEventListener('change', apply);
        input.addEventListener('blur', () => { const value = target(); if (value) input.value = String(value[key]); });
      });
    });
    ui.spineBakeMerge.addEventListener('click', async () => { await onBake(); refresh(); });
    ui.spineExportMerge.addEventListener('click', onExport);
    function bindingFor(input) {
      if (!getSession()) return null;
      const phase = phases.find(value => input === flowRows[value].Start);
      if (input !== ui.spineStartTime && (!phase || phase === 'loop' || !getSession().settings.flowTargets)) return null;
      const session = getSession(), before = clone(session.settings);
      return {source: phase ? session.settings.flowTargets[phase] : session.settings, key: 'startTime', affectsParticles: false,
        restore() { session.settings = before; contextSignature = ''; onChange(); refresh(); }};
    }
    refresh(); return {refresh, validateOptions, validateFlowOptions, bindingFor};
  }
  return {mount};
});
