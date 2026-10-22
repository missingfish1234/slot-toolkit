(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleEmitterLanes = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  // Per-layer timing lanes: each enabled emitter shows when it starts, how long it
  // emits and how far its last particles live. Dragging edits startDelay and
  // emissionDuration; everything else stays in the inspector.
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const finite = (value, fallback) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  const round = value => Math.round(value * 1e6) / 1e6 || 0;

  function layout(emitter, duration) {
    const span = Math.max(1e-6, finite(duration, 1));
    const delay = clamp(finite(emitter.startDelay, 0), 0, span);
    const window = clamp(finite(emitter.emissionDuration, 0), 0, span - delay);
    const life = Math.max(0, finite(emitter.life, 0)) + Math.max(0, finite(emitter.lifeRandom, 0));
    const tailEnd = clamp(delay + window + life, delay, span);
    return {delay, window, tailEnd, start: delay / span, width: window / span, tail: (tailEnd - delay) / span};
  }

  // Snap to whole frames unless the caller asks for free values.
  function snap(seconds, fps, free) {
    if (free || !(fps > 0)) return round(seconds);
    return round(Math.round(seconds * fps) / fps);
  }

  function mount({host, getContext, onSelect, onBegin, onChange, onEnd, document: documentOverride} = {}) {
    if (!host) return {refresh() {}, destroy() {}};
    const doc = documentOverride || host.ownerDocument || globalThis.document;
    const element = (tag, className, text) => {
      const node = doc.createElement(tag); if (className) node.className = className;
      if (text !== undefined) node.textContent = text; return node;
    };
    const wrapper = element('div', 'emitter-lanes');
    const heading = element('div', 'emitter-lanes-heading');
    const title = element('span', 'emitter-lanes-title', '圖層時間');
    const hint = element('span', 'emitter-lanes-hint', '拖曳色條調整開始時間，拖右端調整發射長度；Alt 不對齊幀');
    const toggle = element('button', 'emitter-lanes-toggle'); toggle.type = 'button';
    heading.append(title, hint, toggle);
    const body = element('div', 'emitter-lanes-body');
    const playhead = element('div', 'emitter-lanes-playhead'); playhead.setAttribute('aria-hidden', 'true');
    wrapper.append(heading, body);
    host.append(wrapper);
    let collapsed = false, rows = new Map(), structure = '', drag = null;
    // Short screens start folded so the canvas keeps its height; the user's choice wins afterwards.
    const shortScreen = () => !!(doc.defaultView && doc.defaultView.innerHeight < 820);
    try {
      const stored = globalThis.localStorage ? globalThis.localStorage.getItem('particle-studio-lanes-collapsed') : null;
      collapsed = stored === null ? shortScreen() : stored === '1';
    } catch (_) { collapsed = shortScreen(); }
    toggle.addEventListener('click', () => {
      collapsed = !collapsed;
      try { globalThis.localStorage.setItem('particle-studio-lanes-collapsed', collapsed ? '1' : '0'); } catch (_) { /* preference is optional */ }
      refresh();
    });

    function build(context) {
      body.replaceChildren(); rows = new Map();
      const track = element('div', 'emitter-lanes-grid');
      context.emitters.forEach(emitter => {
        const row = element('div', 'emitter-lane'); row.dataset.emitterId = emitter.id;
        const label = element('button', 'emitter-lane-label'); label.type = 'button';
        const dot = element('span', 'emitter-lane-dot'); const name = element('span', 'emitter-lane-name');
        label.append(dot, name);
        label.addEventListener('click', () => { if (typeof onSelect === 'function') onSelect(emitter.id); });
        const lane = element('div', 'emitter-lane-track');
        const tail = element('div', 'emitter-lane-tail');
        const bar = element('div', 'emitter-lane-bar'); bar.tabIndex = 0; bar.setAttribute('role', 'slider');
        const handle = element('div', 'emitter-lane-handle'); handle.setAttribute('aria-hidden', 'true');
        bar.append(handle); lane.append(tail, bar); row.append(label, lane); track.append(row);
        const start = (event, kind) => {
          if (event.button !== 0) return;
          event.preventDefault(); event.stopPropagation();
          const current = (getContext() || {}).emitters || [];
          const target = current.find(item => item.id === emitter.id); if (!target) return;
          if (typeof onSelect === 'function') onSelect(emitter.id);
          drag = {id: emitter.id, kind, x: event.clientX, width: lane.getBoundingClientRect().width || 1,
            delay: finite(target.startDelay, 0), emission: finite(target.emissionDuration, 0), pointerId: event.pointerId, moved: false};
          bar.focus({preventScroll: true});
          if (typeof onBegin === 'function') onBegin(emitter.id);
          (kind === 'move' ? bar : handle).setPointerCapture(event.pointerId);
        };
        bar.addEventListener('pointerdown', event => { if (event.target !== handle) start(event, 'move'); });
        handle.addEventListener('pointerdown', event => start(event, 'resize'));
        const move = event => {
          if (!drag || drag.id !== emitter.id || event.pointerId !== drag.pointerId) return;
          const context = getContext() || {}, duration = finite(context.duration, 1), fps = finite(context.fps, 30);
          const seconds = (event.clientX - drag.x) / drag.width * duration;
          if (Math.abs(event.clientX - drag.x) < 2 && !drag.moved) return;
          drag.moved = true;
          const patch = drag.kind === 'move'
            ? {startDelay: clamp(snap(drag.delay + seconds, fps, event.altKey), 0, Math.max(0, round(duration - 1 / fps)))}
            : {emissionDuration: clamp(snap(drag.emission + seconds, fps, event.altKey), 0, 30)};
          if (typeof onChange === 'function') onChange(drag.id, patch);
        };
        const finish = event => {
          if (!drag || drag.id !== emitter.id || event.pointerId !== drag.pointerId) return;
          const done = drag; drag = null;
          if (typeof onEnd === 'function') onEnd(done.id, done.moved, event.type === 'pointercancel');
        };
        [bar, handle].forEach(node => {
          node.addEventListener('pointermove', move);
          node.addEventListener('pointerup', finish); node.addEventListener('pointercancel', finish);
        });
        bar.addEventListener('keydown', event => {
          const step = {ArrowLeft: -1, ArrowRight: 1}[event.key]; if (!step) return;
          event.preventDefault(); event.stopPropagation();
          const context = getContext() || {}, fps = finite(context.fps, 30), duration = finite(context.duration, 1);
          const target = (context.emitters || []).find(item => item.id === emitter.id); if (!target) return;
          const amount = (event.shiftKey ? 10 : 1) / fps;
          if (typeof onBegin === 'function') onBegin(emitter.id);
          if (typeof onChange === 'function') onChange(emitter.id, {startDelay: clamp(round(finite(target.startDelay, 0) + step * amount), 0, Math.max(0, round(duration - 1 / fps)))});
          if (typeof onEnd === 'function') onEnd(emitter.id, true, false);
        });
        rows.set(emitter.id, {row, dot, name, bar, tail, label});
      });
      track.append(playhead);
      body.append(track);
    }

    function refresh() {
      const context = getContext ? getContext() || {} : {};
      const emitters = Array.isArray(context.emitters) ? context.emitters : [];
      wrapper.hidden = !emitters.length || context.hidden === true;
      toggle.textContent = collapsed ? '展開' : '收合';
      title.textContent = collapsed ? '圖層時間 · ' + emitters.length + ' 層' : '圖層時間';
      toggle.setAttribute('aria-expanded', String(!collapsed));
      body.hidden = collapsed; hint.hidden = collapsed;
      if (wrapper.hidden || collapsed) return;
      const key = emitters.map(e => e.id).join('|');
      if (key !== structure) { structure = key; build(context); }
      const duration = Math.max(1e-6, finite(context.duration, 1));
      emitters.forEach(emitter => {
        const view = rows.get(emitter.id); if (!view) return;
        const box = layout(emitter, duration);
        view.name.textContent = emitter.name;
        view.dot.style.background = emitter.color || '#edc98c';
        view.row.classList.toggle('selected', emitter.id === context.selectedId);
        view.row.classList.toggle('disabled', emitter.enabled === false);
        view.row.classList.toggle('muted', !!emitter.muted);
        view.bar.style.left = (box.start * 100) + '%';
        view.bar.style.width = 'max(4px, ' + (box.width * 100) + '%)';
        view.bar.style.setProperty('--lane-color', emitter.color || '#81e8c6');
        view.tail.style.left = (box.start * 100) + '%';
        view.tail.style.width = (box.tail * 100) + '%';
        view.tail.style.setProperty('--lane-color', emitter.color || '#81e8c6');
        const text = emitter.name + '：開始 ' + box.delay.toFixed(2) + ' 秒，發射 ' + box.window.toFixed(2) + ' 秒，粒子最晚到 ' + box.tailEnd.toFixed(2) + ' 秒';
        view.bar.title = text + '。拖曳移動，拖右端改長度，方向鍵逐幀';
        view.bar.setAttribute('aria-label', text);
        view.bar.setAttribute('aria-valuemin', '0'); view.bar.setAttribute('aria-valuemax', String(duration));
        view.bar.setAttribute('aria-valuenow', String(box.delay));
      });
      const time = clamp(finite(context.time, 0), 0, duration);
      playhead.style.setProperty('--lane-progress', String(time / duration));
    }
    return {refresh, destroy() { wrapper.remove(); }};
  }
  return {layout, snap, mount};
});
