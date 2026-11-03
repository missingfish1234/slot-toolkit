(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleAttachAssist = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  // Small, pure helpers for "enhance an existing Spine animation": timeline
  // markers, snapping, picking a layer relative to a clicked slot, and placing
  // a new layer at the playhead without moving the layers already timed.
  const round = value => Math.round(value * 1e6) / 1e6;
  const object = value => !!value && typeof value === 'object' && !Array.isArray(value);

  function collectTimes(value, out, depth = 0) {
    if (depth > 8 || value === null || typeof value !== 'object') return;
    if (Array.isArray(value)) {
      value.forEach(frame => {
        if (object(frame)) out.add(round(typeof frame.time === 'number' && Number.isFinite(frame.time) ? frame.time : 0));
      });
      return;
    }
    Object.keys(value).forEach(key => collectTimes(value[key], out, depth + 1));
  }
  // Key and event times of one animation. Events come first so they win ties.
  function animationMarkers(json, name, limit = 400) {
    const animation = json && json.animations && object(json.animations[name]) ? json.animations[name] : null;
    if (!animation) return [];
    const markers = [];
    (Array.isArray(animation.events) ? animation.events : []).forEach(event => {
      if (!object(event)) return;
      const time = round(typeof event.time === 'number' && Number.isFinite(event.time) ? event.time : 0);
      markers.push({time, kind: 'event', name: typeof event.name === 'string' ? event.name : '事件'});
    });
    const keys = new Set();
    Object.keys(animation).forEach(group => { if (group !== 'events') collectTimes(animation[group], keys); });
    const eventTimes = new Set(markers.map(marker => marker.time));
    Array.from(keys).sort((a, b) => a - b).filter(time => !eventTimes.has(time)).slice(0, limit)
      .forEach(time => markers.push({time, kind: 'key'}));
    return markers.sort((a, b) => a.time - b.time || (a.kind === 'event' ? -1 : 1));
  }
  // Snap to the closest marker inside the tolerance (seconds), else to a frame.
  function snapTime(value, {markers = [], fps = 30, duration = Infinity, tolerance = 0, free = false} = {}) {
    let time = Math.max(0, Math.min(duration, value));
    if (free) return {time: round(time), marker: null};
    let best = null, distance = tolerance;
    for (const marker of markers) {
      const gap = Math.abs(marker.time - time);
      if (gap <= distance && (!best || gap < distance || marker.kind === 'event' && best.kind !== 'event')) { best = marker; distance = gap; }
    }
    if (best) return {time: round(Math.min(duration, best.time)), marker: best};
    const step = fps > 0 ? 1 / fps : 0;
    time = step ? Math.round(time / step) * step : time;
    return {time: round(Math.max(0, Math.min(duration, time))), marker: null};
  }
  // Layer right above (after) or right below (before) a clicked slot, using
  // the setup draw order. "Below the first slot" is the back of the skeleton.
  function layerNextTo(slotOrder, slotName, below) {
    const index = slotOrder.indexOf(slotName);
    if (index < 0) throw new Error('找不到插槽：' + slotName);
    if (!below) return {drawOrder: 'after', afterSlot: slotName};
    return index === 0 ? {drawOrder: 'back', afterSlot: ''} : {drawOrder: 'after', afterSlot: slotOrder[index - 1]};
  }
  // Absolute time = session start + layer delay. Put a new layer at `at`
  // seconds of the original animation; if that is before the session start,
  // move the session start earlier and push existing layers later by the same
  // amount so they keep their absolute times.
  function placeAtTime({sessionStart = 0, at, delays = {}}) {
    if (!Number.isFinite(at) || at < 0) throw new Error('時間必須是 0 秒以上。');
    const start = Math.min(sessionStart, at), shift = round(sessionStart - start);
    const nextDelays = {};
    Object.keys(delays).forEach(id => { nextDelays[id] = round((delays[id] || 0) + shift); });
    return {sessionStart: round(start), delays: nextDelays, delay: round(at - start), shift};
  }
  // Seconds the particle animation must last so every layer can finish.
  function requiredDuration(emitters) {
    let longest = 0;
    (emitters || []).forEach(e => {
      if (!e || e.enabled === false) return;
      const life = (e.life || 0) * (1 + (e.lifeRandom || 0));
      longest = Math.max(longest, (e.startDelay || 0) + (e.emissionDuration || 0) + life);
    });
    return round(longest);
  }
  return {animationMarkers, snapTime, layerNextTo, placeAtTime, requiredDuration};
});
