(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleTimelineView = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const phases = ['in', 'loop', 'out'];
  const labels = {in: 'IN', loop: 'LOOP', out: 'OUT'};
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const nonnegative = (value, fallback = 0) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback;
  const seconds = value => String(Number(value.toFixed(3)));

  function compute(context = {}) {
    context = context && typeof context === 'object' ? context : {};
    const flow = !!context.flow && context.flow.enabled !== false;
    const phase = flow ? (phases.includes(context.phase) ? context.phase : 'loop') : null;
    const attached = !!context.attached && !!context.timeline;
    const timeline = attached ? context.timeline : null;
    const localDuration = nonnegative(context.duration, flow ? nonnegative(context.flow[phase] && context.flow[phase].duration) : 0);
    const duration = timeline ? nonnegative(timeline.duration, localDuration) : localDuration;
    const time = clamp(nonnegative(context.time), 0, duration);
    const startTime = timeline ? clamp(nonnegative(timeline.startTime), 0, duration) : 0;
    const fxDuration = timeline ? nonnegative(timeline.fxDuration, duration - startTime) : duration;
    const endTime = timeline ? clamp(nonnegative(timeline.endTime, startTime + fxDuration), startTime, duration) : duration;
    const holdsEnd = attached && phase === 'in' && timeline.holdsEnd === true;
    const holdEnd = holdsEnd ? duration : endTime;
    const fps = nonnegative(context.fps, 30) || 30;
    const longest = flow ? Math.max(...phases.map(key => nonnegative(context.flow[key] && context.flow[key].duration))) : 0;
    const relativeTotal = longest ? phases.reduce((sum, key) => sum + nonnegative(context.flow[key] && context.flow[key].duration) / longest, 0) : 0;
    const segments = flow ? phases.map(key => {
      const segment = context.flow[key] || {}, length = nonnegative(segment.duration);
      return {phase: key, label: labels[key], name: typeof segment.name === 'string' ? segment.name : labels[key],
        duration: length, weight: relativeTotal > 0 ? .15 + .55 * (length / longest) / relativeTotal : 1 / 3, active: key === phase};
    }) : [];
    return {phase, flow, segments, attached, duration, time, fps, progress: duration ? time / duration : 0,
      startTime, endTime, fxDuration, holdsEnd, holdEnd,
      startProgress: duration ? startTime / duration : 0, endProgress: duration ? endTime / duration : 0,
      animationName: attached && typeof timeline.animationName === 'string' ? timeline.animationName : '粒子動畫'};
  }

  function mount({host, getContext, onSeek, onSelectPhase, document: documentOverride} = {}) {
    if (!host) return {refresh: () => null, destroy() {}};
    const doc = documentOverride || host.ownerDocument || globalThis.document;
    const listeners = [];
    let model = null, structuralKey = '', destroyed = false;
    const element = (tag, className, text) => {
      const node = doc.createElement(tag); node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const listen = (node, type, callback) => { node.addEventListener(type, callback); listeners.push([node, type, callback]); };
    const phaseSection = element('div', 'timeline-phase-section');
    const phaseTitle = element('div', 'timeline-track-heading', '三段表演 · 粒子長度');
    const phaseStrip = element('div', 'timeline-phase-strip');
    phaseStrip.setAttribute('role', 'group'); phaseStrip.setAttribute('aria-label', '選擇動畫段落');
    const phaseButtons = new Map();
    for (const key of phases) {
      const button = element('button', 'timeline-phase'); button.type = 'button'; button.setAttribute('data-phase', key);
      const title = element('strong', 'timeline-phase-label', labels[key]);
      const duration = element('span', 'timeline-phase-duration');
      button.append(title, duration); phaseStrip.append(button); phaseButtons.set(key, {button, duration});
      listen(button, 'click', () => {
        const current = compute(typeof getContext === 'function' ? getContext() : {});
        const segment = current.segments.find(item => item.phase === key);
        if (segment && segment.duration > 0 && !segment.active && typeof onSelectPhase === 'function') onSelectPhase(key);
      });
    }
    phaseSection.append(phaseTitle, phaseStrip);
    const heading = element('div', 'timeline-track-heading');
    const summary = element('span', 'timeline-track-summary'); summary.id = 'timelineTrackSummary';
    const cursor = element('output', 'timeline-track-time'); cursor.id = 'timelineTrackTime'; cursor.setAttribute('aria-live', 'off');
    heading.append(summary, cursor);
    const track = element('div', 'timeline-track');
    const original = element('div', 'timeline-original-range');
    const fx = element('div', 'timeline-fx-range', '粒子');
    const hold = element('div', 'timeline-hold-range', '末態保留');
    const playhead = element('div', 'timeline-playhead'); playhead.setAttribute('aria-hidden', 'true');
    const seek = element('input', 'timeline-track-seek'); seek.id = 'timelineTrackSeek';
    seek.type = 'range'; seek.min = '0'; seek.setAttribute('aria-label', '在動畫時間軸定位');
    seek.setAttribute('aria-describedby', 'timelineTrackSummary');
    track.append(original, fx, hold, playhead, seek);
    const ruler = element('div', 'timeline-track-ruler'); ruler.setAttribute('aria-hidden', 'true');
    const ticks = [0, .25, .5, .75, 1].map(position => { const node = element('span', ''); ruler.append(node); return {node, position}; });
    host.replaceChildren(phaseSection, heading, track, ruler);
    listen(seek, 'input', () => {
      const current = compute(typeof getContext === 'function' ? getContext() : {});
      const value = Number(seek.value);
      if (current.duration > 0 && Number.isFinite(value) && typeof onSeek === 'function') onSeek(clamp(value, 0, current.duration));
    });
    listen(seek, 'keydown', event => {
      if (event.key !== 'Home' && event.key !== 'End') return;
      const current = compute(typeof getContext === 'function' ? getContext() : {});
      if (current.duration <= 0 || typeof onSeek !== 'function') return;
      event.preventDefault(); onSeek(event.key === 'Home' ? 0 : current.duration);
    });
    function refresh() {
      if (destroyed) return null;
      model = compute(typeof getContext === 'function' ? getContext() : {});
      const key = JSON.stringify([model.flow, model.segments, model.attached, model.duration, model.fps, model.startTime,
        model.endTime, model.holdsEnd, model.animationName]);
      if (key !== structuralKey) {
        structuralKey = key; phaseSection.hidden = !model.flow;
        for (const segment of model.segments) {
          const nodes = phaseButtons.get(segment.phase);
          nodes.button.classList.toggle('active', segment.active);
          nodes.button.setAttribute('aria-pressed', String(segment.active));
          nodes.button.setAttribute('aria-label', segment.label + ' · ' + segment.name + ' · 粒子 ' + seconds(segment.duration) + ' 秒');
          nodes.button.title = segment.name + ' · 粒子長度 ' + seconds(segment.duration) + ' 秒';
          nodes.button.disabled = segment.duration <= 0;
          nodes.button.style.flexGrow = String(segment.weight);
          nodes.duration.textContent = seconds(segment.duration) + ' 秒';
        }
        summary.textContent = (model.attached ? '掛接動畫「' + model.animationName + '」' : '粒子動畫') + ' · 粒子 ' +
          seconds(model.startTime) + '–' + seconds(model.endTime) + ' 秒' +
          (model.holdsEnd && model.holdEnd > model.endTime ? ' · 末態保留至 ' + seconds(model.holdEnd) + ' 秒' : '');
        original.title = (model.attached ? model.animationName : '粒子動畫') + ' · 0–' + seconds(model.duration) + ' 秒';
        original.setAttribute('aria-hidden', 'true');
        fx.style.left = model.startProgress * 100 + '%';
        fx.style.width = (model.endProgress - model.startProgress) * 100 + '%';
        fx.title = '粒子 ' + seconds(model.startTime) + '–' + seconds(model.endTime) + ' 秒';
        hold.hidden = !model.holdsEnd || model.holdEnd <= model.endTime;
        hold.style.left = model.endProgress * 100 + '%';
        hold.style.width = (model.duration ? (model.holdEnd - model.endTime) / model.duration * 100 : 0) + '%';
        hold.title = '末態保留至 IN 原動畫結束 · ' + seconds(model.holdEnd) + ' 秒';
        seek.max = String(model.duration); seek.step = String(1 / model.fps); seek.disabled = model.duration <= 0;
        ticks.forEach(({node, position}) => { node.textContent = seconds(model.duration * position) + ' 秒'; });
      }
      seek.value = String(model.time);
      seek.setAttribute('aria-valuetext', model.time.toFixed(2) + ' / ' + model.duration.toFixed(2) + ' 秒');
      cursor.textContent = model.time.toFixed(2) + ' / ' + model.duration.toFixed(2) + ' 秒';
      playhead.style.left = model.progress * 100 + '%';
      return model;
    }
    refresh();
    return {refresh, destroy() {
      if (destroyed) return;
      destroyed = true;
      listeners.forEach(([node, type, callback]) => node.removeEventListener(type, callback));
      host.replaceChildren();
    }};
  }
  return {compute, mount};
});
