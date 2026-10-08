(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleFlowPlayback = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function advance(state, delta, durations) {
    if (!state || !['in', 'loop', 'out'].includes(state.phase) || !Number.isFinite(state.time) || state.time < 0 || !Number.isFinite(delta) || delta < 0) throw new Error('動畫段落播放狀態無效。');
    ['in', 'loop', 'out'].forEach(phase => { if (!Number.isFinite(durations[phase]) || durations[phase] <= 0) throw new Error('動畫段落長度必須大於 0。'); });
    const next = Object.assign({}, state, {completed: false});
    if (!next.playing) return next;
    next.time += delta;
    if (next.sequence && next.phase === 'in' && next.time >= durations.in) {
      next.time -= durations.in; next.phase = 'loop';
    }
    if (next.phase === 'loop' && next.time >= durations.loop) {
      if (next.sequence && next.exitRequested) {
        next.time -= durations.loop; next.phase = 'out'; next.exitRequested = false;
      } else next.time %= durations.loop;
    }
    if (next.phase !== 'loop' && next.time >= durations[next.phase]) {
      next.time = durations[next.phase]; next.playing = false; next.sequence = false; next.completed = true;
    }
    return next;
  }
  return {advance};
});
