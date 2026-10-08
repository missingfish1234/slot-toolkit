(function (root, factory) {
  'use strict';
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleGradientEditor = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const rgb = hex => [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16));
  const hex = channels => '#' + channels.map(value => Math.round(clamp(value, 0, 255)).toString(16).padStart(2, '0')).join('');
  const percent = value => Number((value * 100).toFixed(1));

  function mount(options) {
    options = options || {};
    const document = options.document || root.document;
    const math = options.math || root.ParticleCurveMath;
    const Core = options.Core || root.ParticleCore;
    if (!document || !math || typeof math.compile !== 'function' || typeof options.getEmitter !== 'function' || !Core || typeof Core.createEmitter !== 'function') {
      throw new Error('漸層編輯器需要有效的畫面、粒子核心與曲線運算模組。');
    }
    const getEmitter = options.getEmitter;
    const onChange = typeof options.onChange === 'function' ? options.onChange : function () {};
    const element = id => {
      const value = document.getElementById(id);
      if (!value) throw new Error('漸層編輯器缺少畫面欄位：' + id);
      return value;
    };
    const ui = Object.fromEntries(['gradientEditor', 'gradientPreview', 'alphaKeyTrack', 'colorKeyTrack',
      'gradientKeyTime', 'gradientKeyColor', 'gradientKeyAlpha', 'gradientTimeField',
      'gradientColorField', 'gradientAlphaField', 'gradientSelectionInfo', 'deleteGradientKey',
      'addColorKey', 'addAlphaKey', 'resetGradient'].map(id => [id, element(id)]));
    const states = new WeakMap();
    const buttons = {color: new Map(), alpha: new Map()};
    const buttonKeys = new WeakMap();
    let drag = null;
    let previousSelection = null;

    function stateFor(emitter) {
      let state = states.get(emitter);
      if (!state) {
        state = {kind: 'color', index: 0, point: null, fallbackColors: [
          {t: 0, color: emitter.colorStart}, {t: 1, color: emitter.colorEnd}
        ]};
        states.set(emitter, state);
      }
      if (emitter.colorGradient === null || emitter.colorGradient === undefined) {
        state.fallbackColors[0].color = emitter.colorStart;
        state.fallbackColors[state.fallbackColors.length - 1].color = emitter.colorEnd;
      }
      return state;
    }
    function keysFor(emitter, kind) {
      return kind === 'alpha' ? emitter.alphaCurve : emitter.colorGradient || stateFor(emitter).fallbackColors;
    }
    function selection(emitter) {
      const state = stateFor(emitter), keys = keysFor(emitter, state.kind);
      let index = keys.indexOf(state.point);
      if (index === -1) index = clamp(state.index, 0, keys.length - 1);
      state.index = index; state.point = keys[index];
      return {emitter, state, kind: state.kind, keys, index, point: state.point};
    }
    function select(emitter, kind, point) {
      const state = stateFor(emitter);
      state.kind = kind; state.point = point; state.index = Math.max(0, keysFor(emitter, kind).indexOf(point));
      refresh();
    }
    function materializeColors(emitter) {
      if (emitter.colorGradient === null || emitter.colorGradient === undefined) emitter.colorGradient = stateFor(emitter).fallbackColors;
      return emitter.colorGradient;
    }
    function colorAt(keys, time) {
      if (time <= keys[0].t) return rgb(keys[0].color);
      for (let index = 1; index < keys.length; index++) {
        if (time <= keys[index].t) {
          const left = keys[index - 1], right = keys[index], progress = (time - left.t) / (right.t - left.t);
          const a = rgb(left.color), b = rgb(right.color);
          return a.map((channel, c) => channel + (b[c] - channel) * progress);
        }
      }
      return rgb(keys[keys.length - 1].color);
    }
    function notifyChange() { refresh(); onChange(); }
    function resetSegment(points, index) {
      if (index < 0 || index + 1 >= points.length) return;
      const left = points[index], right = points[index + 1];
      left.out = {x: 1 / 3, y: left.v};
      right.in = {x: 2 / 3, y: right.v};
    }
    function timeBounds(keys, index) {
      if (index <= 0 || index >= keys.length - 1) return null;
      const before = keys[index - 1].t, after = keys[index + 1].t;
      const gap = Math.min(0.002, (after - before) / 4);
      const minimum = before + gap, maximum = after - gap;
      // Use the declared 0.1% input grid whenever there is room. Very tight
      // imported keys retain a continuous, strictly ordered interval instead.
      const gridMinimum = Math.ceil((minimum * 1000) - 1e-9) / 1000;
      const gridMaximum = Math.floor((maximum * 1000) + 1e-9) / 1000;
      return gridMinimum <= gridMaximum ? [gridMinimum, gridMaximum] : [minimum, maximum];
    }
    function writeTime(context, value) {
      if (!finite(value)) return false;
      const keys = keysFor(context.emitter, context.kind), bounds = timeBounds(keys, context.index);
      if (!bounds) return false;
      const point = keys[context.index], next = clamp(value / 100, bounds[0], bounds[1]);
      if (point.t === next) return false;
      if (context.kind === 'color') materializeColors(context.emitter);
      point.t = next;
      return true;
    }
    function writeAlpha(context, value) {
      if (!finite(value) || context.kind !== 'alpha') return false;
      const point = keysFor(context.emitter, 'alpha')[context.index], next = Math.round(clamp(value, 0, 1) * 1000) / 1000;
      if (point.v === next) return false;
      const delta = next - point.v;
      point.v = next;
      ['in', 'out'].forEach(kind => { if (point[kind]) point[kind].y = clamp(point[kind].y + delta, 0, 1); });
      return true;
    }
    function addKey(kind) {
      const emitter = getEmitter(); if (!emitter) return;
      const keys = keysFor(emitter, kind); if (keys.length >= 32) return;
      let index = 0, largestGap = -1;
      for (let i = 0; i < keys.length - 1; i++) {
        const gap = keys[i + 1].t - keys[i].t;
        if (gap > largestGap) { largestGap = gap; index = i; }
      }
      const time = keys[index].t + largestGap / 2;
      const point = kind === 'color' ? {t: time, color: hex(colorAt(keys, time))} :
        {t: time, v: math.compile(keys, 1).sample(time), curve: keys[index].curve || 'linear'};
      if (kind === 'color') materializeColors(emitter);
      keys.splice(index + 1, 0, point);
      if (kind === 'alpha') { resetSegment(keys, index); resetSegment(keys, index + 1); }
      const state = stateFor(emitter); state.kind = kind; state.index = index + 1; state.point = point;
      notifyChange();
    }
    function deleteKey(context) {
      const keys = keysFor(context.emitter, context.kind);
      if (context.index <= 0 || context.index >= keys.length - 1 || keys.length <= 2) return false;
      if (context.kind === 'color') materializeColors(context.emitter);
      keys.splice(context.index, 1);
      if (context.kind === 'alpha') resetSegment(keys, context.index - 1);
      const state = stateFor(context.emitter);
      state.kind = context.kind; state.index = Math.min(context.index, keys.length - 1); state.point = keys[state.index];
      notifyChange();
      return true;
    }
    function snapshot(emitter) {
      const selected = selection(emitter), state = stateFor(emitter);
      const colors = emitter.colorGradient === undefined || emitter.colorGradient === null ? null : clone(emitter.colorGradient);
      const alpha = clone(emitter.alphaCurve), fallback = clone(state.fallbackColors);
      return function restore() {
        emitter.colorGradient = colors === null ? null : clone(colors);
        emitter.alphaCurve = clone(alpha);
        state.fallbackColors = clone(fallback);
        state.kind = selected.kind; state.index = selected.index; state.point = null;
        refresh();
      };
    }
    function setInputValue(input, value, force) {
      // Preserve the caret and unfinished direct input while that field has focus.
      if (force || document.activeElement !== input) input.value = String(value);
    }
    function syncTrack(emitter, kind, keys, track, selected) {
      const keep = new Set(keys), map = buttons[kind];
      map.forEach((button, point) => { if (!keep.has(point)) { button.remove(); map.delete(point); } });
      keys.forEach((point, index) => {
        let button = map.get(point);
        if (!button) {
          button = document.createElement('button'); button.type = 'button';
          button.className = 'gradient-key ' + kind; map.set(point, button);
        }
        buttonKeys.set(button, {emitter, kind, point});
        const active = selected.kind === kind && selected.point === point;
        button.classList.toggle('selected', active); button.setAttribute('aria-pressed', String(active));
        button.style.left = (point.t * 100) + '%';
        const color = kind === 'color' ? point.color : 'rgba(255,255,255,' + clamp(point.v, 0, 1) + ')';
        button.style.setProperty('--key-color', color);
        const label = (kind === 'alpha' ? '透明度' : '顏色') + ' ' + percent(point.t) + '% · ' + (kind === 'alpha' ? Number(point.v.toFixed(3)) : point.color);
        button.setAttribute('aria-label', label);
        button.title = label + (index === 0 || index === keys.length - 1 ? '；端點位置固定' : '；左右拖曳調整，右鍵或 Delete 刪除');
        // Reuse nodes so focus and an ongoing pointer gesture remain stable.
        if (track.children[index] !== button) track.insertBefore(button, track.children[index] || null);
      });
    }
    function refresh() {
      const emitter = getEmitter(); if (!emitter) return;
      const selected = selection(emitter), colors = keysFor(emitter, 'color'), alpha = keysFor(emitter, 'alpha');
      const changedSelection = !previousSelection || previousSelection.emitter !== emitter || previousSelection.kind !== selected.kind || previousSelection.point !== selected.point;
      previousSelection = {emitter, kind: selected.kind, point: selected.point};
      const compiled = math.compile(alpha, 1), stops = [];
      // 64 segments (65 endpoints), with the same alpha evaluator as the simulator.
      for (let index = 0; index <= 64; index++) {
        const time = index / 64, channels = colorAt(colors, time).map(Math.round);
        stops.push('rgba(' + channels.join(',') + ',' + Number(compiled.sample(time).toFixed(6)) + ') ' + (time * 100) + '%');
      }
      ui.gradientPreview.style.background = 'linear-gradient(90deg,' + stops.join(',') + ')';
      syncTrack(emitter, 'alpha', alpha, ui.alphaKeyTrack, selected);
      syncTrack(emitter, 'color', colors, ui.colorKeyTrack, selected);
      const alphaSelected = selected.kind === 'alpha';
      ui.gradientColorField.hidden = alphaSelected; ui.gradientAlphaField.hidden = !alphaSelected;
      ui.gradientKeyColor.disabled = alphaSelected; ui.gradientKeyAlpha.disabled = !alphaSelected;
      ui.gradientKeyAlpha.step = '0.001';
      ui.gradientKeyTime.disabled = selected.index === 0 || selected.index === selected.keys.length - 1;
      const bounds = timeBounds(selected.keys, selected.index);
      ui.gradientKeyTime.min = String(Number(((bounds ? bounds[0] : selected.point.t) * 100).toFixed(10)));
      ui.gradientKeyTime.max = String(Number(((bounds ? bounds[1] : selected.point.t) * 100).toFixed(10)));
      const tinyBounds = bounds && bounds[1] - bounds[0] < 0.001;
      const onGrid = Math.abs(selected.point.t * 1000 - Math.round(selected.point.t * 1000)) <= 1e-7;
      const preciseTime = tinyBounds || !onGrid;
      ui.gradientKeyTime.step = preciseTime ? 'any' : '0.1';
      ui.deleteGradientKey.disabled = ui.gradientKeyTime.disabled || selected.keys.length <= 2;
      const selectedPercent = preciseTime ? Number((selected.point.t * 100).toFixed(8)) : percent(selected.point.t);
      setInputValue(ui.gradientKeyTime, selectedPercent, changedSelection);
      if (alphaSelected) setInputValue(ui.gradientKeyAlpha, Number(selected.point.v.toFixed(3)), changedSelection);
      else ui.gradientKeyColor.value = selected.point.color;
      ui.gradientSelectionInfo.textContent = (alphaSelected ? '上方 · 透明度節點' : '下方 · 顏色節點') +
        '　' + selectedPercent + '%' + (ui.gradientKeyTime.disabled ? ' · 端點位置固定' : '');
      ui.addAlphaKey.disabled = alpha.length >= 32; ui.addColorKey.disabled = colors.length >= 32;
    }
    function bindingFor(input) {
      if (input !== ui.gradientKeyTime && input !== ui.gradientKeyAlpha) return null;
      const emitter = getEmitter(); if (!emitter) return null;
      const selected = selection(emitter);
      if (input === ui.gradientKeyTime && !timeBounds(selected.keys, selected.index)) return null;
      if (input === ui.gradientKeyAlpha && selected.kind !== 'alpha') return null;
      const context = {emitter, kind: selected.kind, index: selected.index};
      const source = {};
      Object.defineProperty(source, 'value', {
        enumerable: true,
        get() { const point = keysFor(emitter, context.kind)[context.index]; return input === ui.gradientKeyTime ? point.t * 100 : point.v; },
        set(value) { if (input === ui.gradientKeyTime) writeTime(context, value); else writeAlpha(context, value); refresh(); }
      });
      return {source, key: 'value', restore: snapshot(emitter)};
    }
    function handleNumeric(input, alphaValue) {
      const commitDisplay = () => {
        const emitter = getEmitter(); if (!emitter) return;
        const current = selection(emitter), tiny = input === ui.gradientKeyTime && input.step === 'any';
        if (alphaValue && current.kind !== 'alpha') return;
        input.value = String(alphaValue ? Number(current.point.v.toFixed(3)) : tiny ? Number((current.point.t * 100).toFixed(8)) : percent(current.point.t));
      };
      const listener = event => {
        const value = input.valueAsNumber, validity = input.validity;
        if (!finite(value) || (validity && (validity.badInput || validity.stepMismatch))) {
          if (event.type === 'change') commitDisplay();
          return;
        }
        const emitter = getEmitter(); if (!emitter) return;
        const context = selection(emitter);
        const changed = alphaValue ? writeAlpha(context, value) : writeTime(context, value);
        if (changed) notifyChange();
        if (event.type === 'change') commitDisplay();
      };
      input.addEventListener('input', listener); input.addEventListener('change', listener);
      input.addEventListener('blur', commitDisplay);
    }
    function contextFromEvent(event, track) {
      const button = event.target.closest ? event.target.closest('button.gradient-key') : null;
      if (!button || !track.contains(button)) return null;
      const record = buttonKeys.get(button);
      if (!record || record.emitter !== getEmitter()) return null;
      const keys = keysFor(record.emitter, record.kind), index = keys.indexOf(record.point);
      return index === -1 ? null : {emitter: record.emitter, kind: record.kind, keys, index, point: record.point, button};
    }
    function endDrag(cancel) {
      const current = drag; if (!current) return;
      drag = null;
      if (cancel && current.changed) { current.restore(); onChange(); }
      try { if (current.track.hasPointerCapture(current.pointerId)) current.track.releasePointerCapture(current.pointerId); } catch (_) {}
    }
    function wireTrack(track) {
      track.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        const context = contextFromEvent(event, track); if (!context) return;
        endDrag(false); select(context.emitter, context.kind, context.point);
        context.button.focus({preventScroll: true});
        if (!timeBounds(context.keys, context.index)) return;
        drag = {track, emitter: context.emitter, kind: context.kind, point: context.point,
          pointerId: event.pointerId, changed: false, restore: snapshot(context.emitter)};
        try { track.setPointerCapture(event.pointerId); } catch (_) {}
        event.preventDefault();
      });
      track.addEventListener('pointermove', event => {
        if (!drag || drag.track !== track || event.pointerId !== drag.pointerId) return;
        if (getEmitter() !== drag.emitter) { endDrag(false); return; }
        const rect = track.getBoundingClientRect(); if (!rect.width) return;
        const keys = keysFor(drag.emitter, drag.kind), index = keys.indexOf(drag.point);
        if (index === -1) { endDrag(false); return; }
        event.preventDefault();
        if (writeTime({emitter: drag.emitter, kind: drag.kind, index}, (event.clientX - rect.left) / rect.width * 100)) {
          drag.changed = true; notifyChange();
        }
      });
      track.addEventListener('pointerup', event => { if (drag && event.pointerId === drag.pointerId) endDrag(false); });
      track.addEventListener('pointercancel', event => { if (drag && event.pointerId === drag.pointerId) endDrag(true); });
      track.addEventListener('lostpointercapture', event => { if (drag && event.pointerId === drag.pointerId) endDrag(false); });
      track.addEventListener('click', event => { const context = contextFromEvent(event, track); if (context) select(context.emitter, context.kind, context.point); });
      track.addEventListener('contextmenu', event => {
        const context = contextFromEvent(event, track); if (!context) return;
        event.preventDefault(); endDrag(false); select(context.emitter, context.kind, context.point); deleteKey(context);
      });
      track.addEventListener('keydown', event => {
        const context = contextFromEvent(event, track); if (!context) return;
        if (event.key === 'Escape' && drag) { event.preventDefault(); endDrag(true); return; }
        if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); endDrag(false); deleteKey(context); }
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
          event.preventDefault(); select(context.emitter, context.kind, context.point);
          if (writeTime(context, context.point.t * 100 + (event.key === 'ArrowRight' ? 1 : -1))) notifyChange();
        }
      });
    }
    handleNumeric(ui.gradientKeyTime, false); handleNumeric(ui.gradientKeyAlpha, true);
    const changeColor = () => {
      const emitter = getEmitter(); if (!emitter) return;
      const selected = selection(emitter), next = ui.gradientKeyColor.value.toLowerCase();
      if (selected.kind !== 'color' || !/^#[0-9a-f]{6}$/.test(next) || selected.point.color === next) return;
      materializeColors(emitter); selected.point.color = next; notifyChange();
    };
    ui.gradientKeyColor.addEventListener('input', changeColor); ui.gradientKeyColor.addEventListener('change', changeColor);
    ui.addColorKey.addEventListener('click', () => addKey('color'));
    ui.addAlphaKey.addEventListener('click', () => addKey('alpha'));
    ui.deleteGradientKey.addEventListener('click', () => { const emitter = getEmitter(); if (emitter) deleteKey(selection(emitter)); });
    ui.resetGradient.addEventListener('click', () => {
      const emitter = getEmitter(); if (!emitter) return;
      endDrag(false); emitter.colorGradient = null; emitter.alphaCurve = clone(Core.createEmitter('gradient-default').alphaCurve);
      states.delete(emitter); notifyChange();
    });
    wireTrack(ui.alphaKeyTrack); wireTrack(ui.colorKeyTrack);
    refresh();
    return {refresh, bindingFor};
  }
  return {mount};
});
