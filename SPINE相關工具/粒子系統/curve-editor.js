(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleCurveEditor = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const round = v => Math.round(v * 1000) / 1000;
  function mount({getEmitter, onChange, math, Core, document: doc = document}) {
    const $ = id => doc.getElementById(id);
    const fallback = new WeakMap();
    let currentEmitter = null;
    const specs = [
      {prefix: 'alpha', key: 'alphaCurve', max: 1, reset: 'resetAlpha', remove: 'deleteAlphaPoint'},
      {prefix: 'size', key: 'sizeCurve', max: 4, reset: 'resetSize', remove: 'deleteSizePoint'},
      {prefix: 'speed', key: 'speedCurve', max: 4, reset: 'resetSpeed', remove: 'deleteSpeedPoint'}
    ].map(spec => ({...spec, selected: 0, canvas: $(spec.prefix + 'CurveCanvas'),
      time: $(spec.prefix + 'CurveTime'), value: $(spec.prefix + 'CurveValue'),
      interpolation: $(spec.prefix + 'Interpolation'), deleteButton: $(spec.remove)}));
    function points(spec, e = getEmitter()) {
      if (e[spec.key]) return e[spec.key];
      if (spec.key === 'speedCurve' && e.inactiveSpeedCurve) return e.inactiveSpeedCurve;
      if (!fallback.has(e)) fallback.set(e, [{t: 0, v: 1}, {t: 1, v: 1}]);
      return fallback.get(e);
    }
    function editable(spec, e = getEmitter()) {
      if (!e[spec.key]) e[spec.key] = clone(points(spec, e));
      return e[spec.key];
    }
    function selected(spec, list = points(spec)) {
      spec.selected = clamp(spec.selected, 0, list.length - 1);
      return list[spec.selected];
    }
    function timeBounds(list, index) {
      const before = list[index - 1].t, after = list[index + 1].t;
      const gap = Math.min(.002, (after - before) / 4);
      const low = before + gap, high = after - gap;
      const gridLow = Math.ceil(low * 1000 - 1e-9) / 1000, gridHigh = Math.floor(high * 1000 + 1e-9) / 1000;
      return gridLow <= gridHigh ? [gridLow, gridHigh] : [low, high];
    }
    function geometry(spec) {
      const r = spec.canvas.getBoundingClientRect();
      return {w: r.width, h: r.height, left: 28, top: 10,
        width: Math.max(1, r.width - 40), height: Math.max(1, r.height - 30)};
    }
    function xy(spec, g, t, v) {
      return {x: g.left + t * g.width, y: g.top + (1 - v / spec.max) * g.height};
    }
    function handle(left, right, kind) {
      return kind === 'out' ? left.out || {x: 1 / 3, y: left.v} : right.in || {x: 2 / 3, y: right.v};
    }
    function resetHandles(list, segment) {
      if (segment < 0 || segment >= list.length - 1) return;
      list[segment].out = {x: 1 / 3, y: list[segment].v};
      list[segment + 1].in = {x: 2 / 3, y: list[segment + 1].v};
    }
    function handles(spec, g, list) {
      const result = [];
      [spec.selected - 1, spec.selected].forEach(segment => {
        if (segment < 0 || segment >= list.length - 1 || list[segment].curve !== 'bezier') return;
        const left = list[segment], right = list[segment + 1];
        ['out', 'in'].forEach(kind => {
          const h = handle(left, right, kind);
          result.push({segment, kind, ...xy(spec, g, left.t + h.x * (right.t - left.t), h.y),
            anchor: xy(spec, g, kind === 'out' ? left.t : right.t, kind === 'out' ? left.v : right.v)});
        });
      });
      return result;
    }
    function draw(spec) {
      if (!spec.canvas.offsetWidth) return;
      const g = geometry(spec), dpr = Math.min(2, typeof devicePixelRatio === 'number' ? devicePixelRatio : 1);
      spec.canvas.width = Math.round(g.w * dpr); spec.canvas.height = Math.round(g.h * dpr);
      const c = spec.canvas.getContext('2d'), list = points(spec);
      c.scale(dpr, dpr); c.lineWidth = 1; c.strokeStyle = '#263241'; c.beginPath();
      [0, .5, 1].forEach(t => { c.moveTo(g.left + t * g.width, g.top); c.lineTo(g.left + t * g.width, g.top + g.height); });
      [0, .5, 1].forEach(v => { c.moveTo(g.left, g.top + v * g.height); c.lineTo(g.left + g.width, g.top + v * g.height); }); c.stroke();
      c.fillStyle = '#7f8c9f'; c.font = '10px sans-serif'; c.fillText(String(spec.max), 4, g.top + 4); c.fillText('0', 12, g.top + g.height);
      c.strokeStyle = getEmitter()[spec.key] ? '#edc98c' : '#687991'; c.lineWidth = 2; c.beginPath();
      const start = xy(spec, g, list[0].t, list[0].v); c.moveTo(start.x, start.y);
      for (let i = 1; i < list.length; i++) {
        const left = list[i - 1], right = list[i], end = xy(spec, g, right.t, right.v);
        if (left.curve === 'bezier') {
          const a = handle(left, right, 'out'), b = handle(left, right, 'in');
          const p = xy(spec, g, left.t + a.x * (right.t - left.t), a.y), q = xy(spec, g, left.t + b.x * (right.t - left.t), b.y);
          c.bezierCurveTo(p.x, p.y, q.x, q.y, end.x, end.y);
        } else if (left.curve === 'stepped') {
          c.lineTo(end.x, xy(spec, g, right.t, left.v).y); c.lineTo(end.x, end.y);
        } else c.lineTo(end.x, end.y);
      }
      c.stroke();
      handles(spec, g, list).forEach(h => {
        c.lineWidth = 1; c.strokeStyle = '#72bdeb'; c.beginPath(); c.moveTo(h.anchor.x, h.anchor.y); c.lineTo(h.x, h.y); c.stroke();
        c.fillStyle = '#72bdeb'; c.beginPath(); c.moveTo(h.x, h.y - 5); c.lineTo(h.x + 5, h.y); c.lineTo(h.x, h.y + 5); c.lineTo(h.x - 5, h.y); c.closePath(); c.fill();
      });
      list.forEach((p, i) => {
        const pos = xy(spec, g, p.t, p.v); c.fillStyle = spec.selected === i ? '#fff0cc' : '#edc98c';
        c.beginPath(); c.arc(pos.x, pos.y, spec.selected === i ? 5 : 4, 0, Math.PI * 2); c.fill();
      });
    }
    function updateFields(spec) {
      const list = points(spec), p = selected(spec, list), segment = Math.min(spec.selected, list.length - 2);
      spec.time.disabled = spec.selected === 0 || spec.selected === list.length - 1;
      const bounds = spec.time.disabled ? [p.t, p.t] : timeBounds(list, spec.selected);
      spec.time.min = bounds[0] * 100;
      spec.time.max = bounds[1] * 100;
      const onGrid = n => Math.abs(n * 1000 - Math.round(n * 1000)) < 1e-7;
      spec.time.step = bounds.every(onGrid) && onGrid(p.t) ? '0.1' : 'any';
      if (doc.activeElement !== spec.time) spec.time.value = String(spec.time.step === 'any' ? p.t * 100 : round(p.t * 100));
      if (doc.activeElement !== spec.value) spec.value.value = String(round(p.v));
      spec.interpolation.value = list[segment].curve || 'linear';
      spec.deleteButton.disabled = spec.time.disabled;
    }
    function refresh() {
      const e = getEmitter(); if (!e) return;
      if (e !== currentEmitter) { currentEmitter = e; specs.forEach(s => { s.selected = 0; }); }
      $('enableSpeedCurve').checked = !!e.speedCurve;
      $('legacyMotionField').querySelector('select').disabled = !!e.speedCurve;
      specs.forEach(spec => { updateFields(spec); draw(spec); });
    }
    function change() { onChange(); refresh(); }
    function setValue(spec, kind, value, e = getEmitter()) {
      const before = points(spec, e);
      if (kind === 't' && (spec.selected === 0 || spec.selected === before.length - 1)) return;
      const wasDisabled = !e[spec.key];
      const list = editable(spec, e), p = selected(spec, list), old = p[kind];
      if (kind === 't') {
        const bounds = timeBounds(list, spec.selected);
        p.t = clamp(round(clamp(value / 100, bounds[0], bounds[1])), bounds[0], bounds[1]);
      } else {
        p.v = round(clamp(value, 0, spec.max)); const delta = p.v - old;
        ['in', 'out'].forEach(key => { if (p[key]) p[key].y = round(clamp(p[key].y + delta, 0, spec.max)); });
      }
      if (wasDisabled || p[kind] !== old) change();
    }
    function remove(spec) {
      const list = points(spec); if (spec.selected <= 0 || spec.selected >= list.length - 1) return;
      const next = editable(spec); next.splice(spec.selected, 1); resetHandles(next, spec.selected - 1);
      spec.selected--; change();
    }
    specs.forEach(spec => {
      let dragging = null;
      const position = event => {
        const r = spec.canvas.getBoundingClientRect(), g = geometry(spec);
        return {g, x: event.clientX - r.left, y: event.clientY - r.top,
          t: clamp((event.clientX - r.left - g.left) / g.width, 0, 1),
          v: clamp((1 - (event.clientY - r.top - g.top) / g.height) * spec.max, 0, spec.max)};
      };
      spec.canvas.addEventListener('contextmenu', event => event.preventDefault());
      spec.canvas.addEventListener('pointerdown', event => {
        if (event.button !== 0 && event.button !== 2) return;
        event.preventDefault(); spec.canvas.focus(); const pos = position(event), list = points(spec);
        let nearest = -1, distance = 9;
        list.forEach((p, i) => { const q = xy(spec, pos.g, p.t, p.v), d = Math.hypot(q.x - pos.x, q.y - pos.y); if (d < distance) { nearest = i; distance = d; } });
        if (event.button === 2) { if (nearest >= 0) { spec.selected = nearest; remove(spec); } return; }
        if (nearest >= 0) {
          spec.selected = nearest; dragging = {kind: 'point', index: nearest};
          if (!getEmitter()[spec.key]) { editable(spec); change(); }
        }
        else {
          const h = handles(spec, pos.g, list).find(item => Math.hypot(item.x - pos.x, item.y - pos.y) < 9);
          if (h) dragging = {kind: 'handle', segment: h.segment, handle: h.kind};
          else if (list.length < 32 && pos.t > .003 && pos.t < .997 && !list.some(p => Math.abs(p.t - pos.t) < .003)) {
            const next = editable(spec), index = next.findIndex(p => p.t > pos.t), left = next[index - 1];
            next.splice(index, 0, {t: round(pos.t), v: round(pos.v), curve: left.curve || 'linear'});
            resetHandles(next, index - 1); resetHandles(next, index);
            spec.selected = index; dragging = {kind: 'point', index}; change();
          }
        }
        if (dragging) spec.canvas.setPointerCapture(event.pointerId);
        refresh();
      });
      spec.canvas.addEventListener('pointermove', event => {
        if (!dragging) return; const pos = position(event), list = editable(spec);
        if (dragging.kind === 'point') {
          spec.selected = dragging.index; setValue(spec, 'v', pos.v); setValue(spec, 't', pos.t * 100);
        } else {
          const left = list[dragging.segment], right = list[dragging.segment + 1], kind = dragging.handle;
          const other = handle(left, right, kind === 'out' ? 'in' : 'out');
          const x = clamp((pos.t - left.t) / (right.t - left.t), kind === 'out' ? 0 : other.x, kind === 'out' ? other.x : 1);
          (kind === 'out' ? left : right)[kind] = {x, y: round(pos.v)}; left.curve = 'bezier'; change();
        }
      });
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => spec.canvas.addEventListener(type, () => { dragging = null; }));
      spec.canvas.addEventListener('keydown', event => {
        const p = selected(spec);
        if (event.key === 'Delete' || event.key === 'Backspace') remove(spec);
        else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') setValue(spec, 'v', p.v + (event.key === 'ArrowUp' ? 1 : -1) * spec.max * .02);
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') setValue(spec, 't', p.t * 100 + (event.key === 'ArrowRight' ? 1 : -1));
        else return;
        event.preventDefault();
      });
      spec.interpolation.addEventListener('change', () => {
        const list = editable(spec), segment = Math.min(spec.selected, list.length - 2);
        list[segment].curve = spec.interpolation.value;
        if (list[segment].curve === 'bezier') {
          if (!list[segment].out) list[segment].out = {x: 1 / 3, y: list[segment].v};
          if (!list[segment + 1].in) list[segment + 1].in = {x: 2 / 3, y: list[segment + 1].v};
        }
        change();
      });
      [[spec.time, 't'], [spec.value, 'v']].forEach(([input, kind]) => {
        ['input', 'change'].forEach(type => input.addEventListener(type, () => {
          if (input.value.trim() && input.checkValidity() && Number.isFinite(input.valueAsNumber)) setValue(spec, kind, input.valueAsNumber);
        }));
        input.addEventListener('blur', () => { const p = selected(spec); input.value = String(kind === 't' && input.step === 'any' ? p.t * 100 : round(kind === 't' ? p.t * 100 : p.v)); });
      });
      spec.deleteButton.addEventListener('click', () => remove(spec));
      $(spec.reset).addEventListener('click', () => {
        if (spec.key === 'speedCurve') { fallback.delete(getEmitter()); getEmitter().inactiveSpeedCurve = null; }
        getEmitter()[spec.key] = spec.key === 'speedCurve' ? null : clone(Core.createEmitter('temporary')[spec.key]);
        spec.selected = 0; change();
      });
    });
    $('enableSpeedCurve').addEventListener('change', () => {
      const e = getEmitter();
      if ($('enableSpeedCurve').checked) { e.speedCurve = clone(points(specs[2], e)); e.inactiveSpeedCurve = null; }
      else { if (e.speedCurve) e.inactiveSpeedCurve = clone(e.speedCurve); e.speedCurve = null; }
      change();
    });
    function bindingFor(input) {
      const spec = specs.find(s => s.time === input || s.value === input); if (!spec) return null;
      const e = getEmitter(), kind = spec.time === input ? 't' : 'v', before = clone(e[spec.key] || null), index = spec.selected;
      return {source: {get value() { const p = points(spec, e)[index]; return kind === 't' ? p.t * 100 : p.v; },
        set value(value) { spec.selected = index; setValue(spec, kind, value, e); }}, key: 'value',
        restore() { e[spec.key] = before; spec.selected = index; refresh(); }};
    }
    refresh(); return {refresh, bindingFor};
  }
  return {mount};
});
