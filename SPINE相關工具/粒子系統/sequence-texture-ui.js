(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleSequenceTextureUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MAX_FRAMES = 120;
  const MAX_MATERIAL = 16 * 1024 * 1024;

  // Number runs are compared as decimal strings, so long frame numbers do not
  // lose precision. Equal names retain the file picker's original order.
  function sortFiles(files) {
    return Array.from(files).map((file, index) => ({file, index})).sort((a, b) => {
      const left = String(a.file.name).toLowerCase().match(/\d+|\D+/g) || [];
      const right = String(b.file.name).toLowerCase().match(/\d+|\D+/g) || [];
      for (let i = 0; i < Math.min(left.length, right.length); i++) {
        const x = left[i], y = right[i];
        if (x === y) continue;
        if (/^\d+$/.test(x) && /^\d+$/.test(y)) {
          const n = x.replace(/^0+/, '') || '0', m = y.replace(/^0+/, '') || '0';
          if (n.length !== m.length) return n.length - m.length;
          if (n !== m) return n < m ? -1 : 1;
        } else return x < y ? -1 : 1;
      }
      return left.length - right.length || a.index - b.index;
    }).map(item => item.file);
  }

  function mount(options) {
    const doc = options.document || document;
    const $ = id => doc.getElementById(id);
    let request = 0, lastOwner = null, lastEmitter = null;
    const pending = new Map();
    const generation = () => options.getGeneration ? options.getGeneration() : null;
    const context = () => ({owner: options.getProject(), selected: options.getEmitter(), generation: generation()});
    const sameContext = current => current.owner === options.getProject() && current.selected === options.getEmitter() &&
      current.owner.emitters.includes(current.selected) && current.generation === generation();
    const validRequest = current => current.request === request && sameContext(current);

    function refresh() {
      const owner = options.getProject(), selected = options.getEmitter();
      if (owner !== lastOwner || selected !== lastEmitter) { request++; lastOwner = owner; lastEmitter = selected; }
      const sequence = selected.sequence, hasSequence = !!(sequence && sequence.frames && sequence.frames.length);
      const active = hasSequence && sequence.enabled !== false;
      const randomMode = active && sequence.mode === 'random';
      const image = active ? sequence.frames[0] : selected.image || options.defaultImage;
      $('textureThumbnail').src = image.dataUrl; $('textureThumbnail').hidden = false;
      $('textureThumbnail').alt = randomMode ? '隨機圖片第一張' : active ? '連續圖第一張' : '目前粒子貼圖';
      $('textureInfo').textContent = randomMode ? '隨機圖片 · ' + sequence.frames.length + ' 張' :
        active ? '連續圖 · ' + sequence.frames.length + ' 張 · ' + image.width + ' × ' + image.height + ' px' :
        (selected.image ? selected.image.name : '內建柔光') + ' · ' + image.width + ' × ' + image.height + ' px';
      $('textureModeField').hidden = !hasSequence;
      $('textureMode').value = randomMode ? 'random' : active ? 'sequence' : 'single';
      $('sequenceTextureControls').hidden = !active;
      const playback = $('sequencePlaybackRow'), strip = $('randomTextureStrip');
      if (playback) playback.hidden = randomMode;
      if ($('sequencePlaybackHint')) $('sequencePlaybackHint').textContent = randomMode
        ? '每顆粒子出生時從這些圖片隨機挑一張，整個生命都維持同一張；挑選結果跟著發射器種子，按「換一組」可重新分配。'
        : '每顆粒子出生後從第一張播放；FPS 控制貼圖速度，可與專案幀率不同。';
      if (strip) {
        strip.hidden = !randomMode; strip.replaceChildren();
        if (randomMode) sequence.frames.forEach(frame => {
          const thumb = doc.createElement('img'); thumb.src = frame.dataUrl; thumb.alt = frame.name; thumb.title = frame.name + ' · ' + frame.width + ' × ' + frame.height + ' px';
          strip.append(thumb);
        });
      }
      if (hasSequence) {
        if (doc.activeElement !== $('sequenceFps')) $('sequenceFps').value = sequence.fps;
        if (sequence.mode !== 'random') $('sequenceMode').value = sequence.mode;
        $('sequenceTextureInfo').textContent = randomMode
          ? sequence.frames.length + ' 張隨機挑選 · 大小依最大的一張等比例縮放'
          : sequence.frames.length + ' 張 · 每輪 ' + Number((sequence.frames.length / sequence.fps).toFixed(3)) + ' 秒 · ' + sequence.frames[0].name +
            (sequence.frames.length > 1 ? ' → ' + sequence.frames[sequence.frames.length - 1].name : '');
        if (options.prepareImages) options.prepareImages(sequence.frames);
      }
    }

    function apply(selected, patch, command = true) {
      const owner = options.getProject(), index = owner.emitters.indexOf(selected);
      if (index < 0 || options.getEmitter() !== selected) return false;
      const normalizedPatch = {};
      const keys = Object.keys(patch), previous = selected.sequence, next = patch.sequence;
      // FPS drags reuse already validated frame assets. Validate their small
      // metadata directly instead of rescanning/serializing all PNGs per move.
      if (keys.length === 1 && keys[0] === 'sequence' && previous && next && next.frames === previous.frames) {
        if (typeof next.enabled !== 'boolean') throw new Error('連續圖啟用狀態必須是布林值。');
        if (!Number.isInteger(next.fps) || next.fps < 1 || next.fps > 120) throw new Error('連續圖 FPS 必須是 1–120 的整數。');
        if (!['loop', 'once', 'random'].includes(next.mode)) throw new Error('連續圖播放方式不正確。');
        if (next.enabled === previous.enabled && next.fps === previous.fps && next.mode === previous.mode) return false;
        normalizedPatch.sequence = {enabled: next.enabled, fps: next.fps, mode: next.mode, frames: previous.frames};
      } else {
        const candidate = {...owner, emitters: owner.emitters.map((e, i) => i === index ? {...e, ...patch} : e)};
        // New asset batches and resets check the entire proposed project before
        // touching the live emitter, including all retained/disabled textures.
        const checked = options.normalize(candidate).emitters[index];
        for (const key of keys) normalizedPatch[key] = checked[key];
        if (keys.every(key => JSON.stringify(selected[key]) === JSON.stringify(normalizedPatch[key]))) return false;
      }
      options.onApply(selected, normalizedPatch, command);
      refresh();
      return true;
    }

    function wirePicker(buttonId, inputId, multiple, randomPick) {
      const input = $(inputId);
      $(buttonId).addEventListener('click', () => { pending.set(input, context()); input.click(); });
      input.addEventListener('cancel', () => pending.delete(input));
      input.addEventListener('change', async () => {
        const files = Array.from(input.files || []), captured = pending.get(input) || context();
        pending.delete(input);
        if (!files.length) return;
        const current = {...captured, request: ++request};
        try {
          if (!validRequest(current)) return;
          if (multiple) {
            if (files.length > MAX_FRAMES) throw new Error('連續圖最多可載入 120 張，請減少張數。');
            const frames = []; let material = 0;
            for (const file of sortFiles(files)) {
              if (!validRequest(current)) return;
              const image = await options.loadImage(file);
              if (!validRequest(current)) return;
              material += image.dataUrl.length;
              if (material > MAX_MATERIAL) throw new Error('連續圖素材總量超過 16 MiB，請縮小圖片後重試。');
              frames.push(image);
            }
            const previous = current.selected.sequence;
            const priorMode = previous && previous.mode !== 'random' ? previous.mode : 'loop';
            apply(current.selected, {sequence: {enabled: true, fps: previous ? previous.fps : 12, mode: randomPick ? 'random' : priorMode, frames}});
            options.notify(randomPick ? '已載入 ' + frames.length + ' 張隨機圖片，每顆粒子會隨機挑一張噴發。'
              : '已載入 ' + frames.length + ' 張連續圖，依檔名數字排序；可直接調整 FPS。');
          } else {
            const image = await options.loadImage(files[0]);
            if (!validRequest(current)) return;
            const patch = {image};
            if (current.selected.sequence) patch.sequence = {...current.selected.sequence, enabled: false};
            apply(current.selected, patch);
          }
        } catch (error) {
          if (validRequest(current)) options.notify(error.message, true);
        } finally { input.value = ''; }
      });
    }

    wirePicker('textureButton', 'textureFile', false);
    wirePicker('sequenceTextureButton', 'sequenceTextureFile', true);
    if ($('randomTextureButton')) wirePicker('randomTextureButton', 'randomTextureFile', true, true);
    $('removeTexture').addEventListener('click', () => {
      request++;
      try { apply(options.getEmitter(), {image: null, sequence: undefined}); }
      catch (error) { options.notify(error.message, true); }
    });
    $('textureMode').addEventListener('change', () => {
      request++;
      const selected = options.getEmitter();
      if (!selected.sequence) return;
      const choice = $('textureMode').value, prior = selected.sequence;
      const mode = choice === 'random' ? 'random' : choice === 'sequence' && prior.mode === 'random' ? ($('sequenceMode').value === 'once' ? 'once' : 'loop') : prior.mode;
      try { apply(selected, {sequence: {...prior, enabled: choice !== 'single', mode}}); }
      catch (error) { refresh(); options.notify(error.message, true); }
    });
    $('sequenceMode').addEventListener('change', () => {
      const selected = options.getEmitter(); if (!selected.sequence) return;
      try { apply(selected, {sequence: {...selected.sequence, mode: $('sequenceMode').value}}); }
      catch (error) { refresh(); options.notify(error.message, true); }
    });
    const fpsInput = $('sequenceFps');
    function updateFps(duringInput) {
      const selected = options.getEmitter(); if (!selected.sequence) return;
      if (!fpsInput.checkValidity() || !fpsInput.value.trim()) {
        if (!duringInput) { fpsInput.reportValidity(); fpsInput.value = selected.sequence.fps; }
        return;
      }
      const fps = fpsInput.valueAsNumber;
      if (fps === selected.sequence.fps) return;
      try { apply(selected, {sequence: {...selected.sequence, fps}}, false); }
      catch (error) { if (!duringInput) { fpsInput.value = selected.sequence.fps; options.notify(error.message, true); } }
    }
    fpsInput.addEventListener('input', () => updateFps(true));
    fpsInput.addEventListener('change', () => updateFps(false));

    refresh();
    return {
      refresh,
      invalidate() { request++; },
      bindingFor(input) {
        if (input !== fpsInput) return null;
        const selected = options.getEmitter(), before = selected.sequence;
        if (!before) return null;
        return {source: before, key: 'fps', restore() { selected.sequence = before; fpsInput.value = before.fps; refresh(); }};
      }
    };
  }
  return {sortFiles, mount};
});
