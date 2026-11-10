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
    // Animation strip: IN/LOOP/OUT (or one main animation) plus extra animations such as BURN.
    const extraId = typeof context.extraId === 'string' ? context.extraId : null;
    const stripFlow = context.stripFlow && typeof context.stripFlow === 'object' ? context.stripFlow : null;
    const strip = {
      phases: stripFlow ? phases.map(key => ({phase: key, label: labels[key], name: stripFlow[key] && stripFlow[key].name || labels[key],
        duration: nonnegative(stripFlow[key] && stripFlow[key].duration), active: !extraId && key === (phases.includes(context.phase) ? context.phase : 'loop')})) : [],
      main: stripFlow ? null : {label: typeof context.mainLabel === 'string' ? context.mainLabel : '主要動畫', duration: nonnegative(context.mainDuration), active: !extraId},
      extras: Array.isArray(context.extras) ? context.extras.filter(item => item && typeof item.id === 'string').map(item => ({id: item.id,
        name: String(item.name), duration: nonnegative(item.duration), loop: !!item.loop, active: item.id === extraId})) : [],
      canAdd: context.canAddExtra === true
    };
    const showStrip = context.showStrip === true;
    const markers = attached && Array.isArray(context.markers) ? context.markers.filter(marker => marker && Number.isFinite(marker.time) && marker.time >= 0 && marker.time <= duration) : [];
    const movable = attached && context.canMoveFx === true;
    return {phase, flow, segments, strip, showStrip, attached, duration, time, fps, progress: duration ? time / duration : 0, markers, movable,
      startTime, endTime, fxDuration, holdsEnd, holdEnd,
      startProgress: duration ? startTime / duration : 0, endProgress: duration ? endTime / duration : 0,
      animationName: attached && typeof timeline.animationName === 'string' ? timeline.animationName : '粒子動畫'};
  }

  function mount({host, getContext, onSeek, onSelectPhase, onSelectMain, onSelectExtra, onAddExtra, onMoveFx, onMoveFxBegin, onMoveFxEnd, document: documentOverride} = {}) {
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
        const list = current.showStrip ? current.strip.phases : current.segments, segment = list.find(item => item.phase === key);
        if (segment && segment.duration > 0 && !segment.active && typeof onSelectPhase === 'function') onSelectPhase(key);
      });
    }
    // Extra-animation strip (shown whenever the app asks for it): main / IN·LOOP·OUT, BURN …, ＋.
    const mainButton = element('button', 'timeline-phase timeline-main-anim'); mainButton.type = 'button';
    const mainLabel = element('strong', 'timeline-phase-label'), mainDuration = element('span', 'timeline-phase-duration');
    mainButton.append(mainLabel, mainDuration);
    if (typeof phaseStrip.insertBefore === 'function' && phaseStrip.firstChild) phaseStrip.insertBefore(mainButton, phaseStrip.firstChild); else phaseStrip.append(mainButton);
    listen(mainButton, 'click', () => { if (typeof onSelectMain === 'function') onSelectMain(); });
    const extraHost = element('div', 'timeline-extra-strip'); phaseStrip.append(extraHost);
    const addButton = element('button', 'timeline-add-anim', '＋ 新增動畫'); addButton.type = 'button';
    addButton.title = '新增 BURN 之類的獨立動畫';
    listen(addButton, 'click', () => { if (typeof onAddExtra === 'function') onAddExtra(); });
    phaseStrip.append(addButton);
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
    const markerLayer = element('div', 'timeline-markers'); markerLayer.setAttribute('aria-hidden', 'true');
    track.append(original, markerLayer, fx, hold, playhead, seek);
    // Drag the particle segment to change when it starts in the original
    // animation. Snaps to events, keys and frames; Alt drags freely.
    let drag = null;
    listen(fx, 'pointerdown', event => {
      if (!model || !model.movable || event.button !== 0 || typeof onMoveFx !== 'function') return;
      event.preventDefault(); event.stopPropagation();
      const width = track.getBoundingClientRect().width || 1;
      drag = {x: event.clientX, start: model.startTime, perPixel: model.duration / width, pointerId: event.pointerId, moved: false};
      fx.setPointerCapture(event.pointerId); fx.classList.add('dragging');
      if (typeof onMoveFxBegin === 'function') onMoveFxBegin();
    });
    listen(fx, 'pointermove', event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      const perPixel = drag.perPixel, value = drag.start + (event.clientX - drag.x) * perPixel;
      drag.moved = drag.moved || Math.abs(event.clientX - drag.x) > 1;
      if (drag.moved) onMoveFx(value, {free: event.altKey, tolerance: 8 * perPixel});
    });
    const finish = event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      drag = null; fx.classList.remove('dragging');
      if (typeof onMoveFxEnd === 'function') onMoveFxEnd();
    };
    listen(fx, 'pointerup', finish); listen(fx, 'pointercancel', finish); listen(fx, 'lostpointercapture', finish);
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
      const key = JSON.stringify([model.flow, model.segments, model.strip, model.showStrip, model.attached, model.duration, model.fps, model.startTime,
        model.endTime, model.holdsEnd, model.animationName, model.markers, model.movable]);
      if (key !== structuralKey) {
        structuralKey = key;
        const strip = model.showStrip ? model.strip : null;
        phaseSection.hidden = !model.flow && !strip;
        phaseTitle.textContent = strip ? '動畫 · 點一下切換預覽' : '三段表演 · 粒子長度';
        mainButton.hidden = !strip || !strip.main; addButton.hidden = !strip; addButton.disabled = !strip || !strip.canAdd;
        if (strip && strip.main) {
          mainLabel.textContent = strip.main.label; mainDuration.textContent = seconds(strip.main.duration) + ' 秒';
          mainButton.classList.toggle('active', strip.main.active); mainButton.setAttribute('aria-pressed', String(strip.main.active));
        }
        if (typeof extraHost.replaceChildren === 'function') extraHost.replaceChildren(); else while (extraHost.firstChild) extraHost.removeChild(extraHost.firstChild);
        if (strip) strip.extras.forEach(item => {
          const button = element('button', 'timeline-phase timeline-extra-anim' + (item.active ? ' active' : '')); button.type = 'button';
          button.setAttribute('aria-pressed', String(item.active)); button.title = item.name + ' · ' + seconds(item.duration) + ' 秒' + (item.loop ? ' · 循環' : '') + ' · 點一下預覽並編輯';
          button.append(element('strong', 'timeline-phase-label', item.name.toUpperCase()), element('span', 'timeline-phase-duration', seconds(item.duration) + ' 秒'));
          listen(button, 'click', () => { if (!item.active && typeof onSelectExtra === 'function') onSelectExtra(item.id); });
          extraHost.append(button);
        });
        const phaseList = strip ? strip.phases : model.segments;
        phaseButtons.forEach(nodes => { nodes.button.hidden = !phaseList.length; });
        for (const segment of phaseList) {
          const nodes = phaseButtons.get(segment.phase);
          nodes.button.classList.toggle('active', segment.active);
          nodes.button.setAttribute('aria-pressed', String(segment.active));
          nodes.button.setAttribute('aria-label', segment.label + ' · ' + segment.name + ' · 粒子 ' + seconds(segment.duration) + ' 秒');
          nodes.button.title = segment.name + ' · 粒子長度 ' + seconds(segment.duration) + ' 秒';
          nodes.button.disabled = segment.duration <= 0;
          nodes.button.style.flexGrow = String(segment.weight || 1);
          nodes.duration.textContent = seconds(segment.duration) + ' 秒';
        }
        summary.textContent = (model.attached ? '掛接動畫「' + model.animationName + '」' : '粒子動畫') + ' · 粒子 ' +
          seconds(model.startTime) + '–' + seconds(model.endTime) + ' 秒' +
          (model.holdsEnd && model.holdEnd > model.endTime ? ' · 末態保留至 ' + seconds(model.holdEnd) + ' 秒' : '');
        original.title = (model.attached ? model.animationName : '粒子動畫') + ' · 0–' + seconds(model.duration) + ' 秒';
        original.setAttribute('aria-hidden', 'true');
        fx.style.left = model.startProgress * 100 + '%';
        fx.style.width = (model.endProgress - model.startProgress) * 100 + '%';
        fx.title = '粒子 ' + seconds(model.startTime) + '–' + seconds(model.endTime) + ' 秒' + (model.movable ? ' · 拖曳調整開始時間（吸附事件與關鍵幀，Alt 自由拖曳）' : '');
        fx.classList.toggle('movable', model.movable);
        markerLayer.replaceChildren();
        model.markers.forEach(marker => {
          const node = element('span', 'timeline-marker ' + (marker.kind === 'event' ? 'event' : 'key'));
          node.style.left = (model.duration ? marker.time / model.duration * 100 : 0) + '%';
          if (marker.kind === 'event') { node.title = '事件 ' + marker.name + ' · ' + seconds(marker.time) + ' 秒'; node.setAttribute('data-name', marker.name); }
          markerLayer.append(node);
        });
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
