(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleLightning = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  // Mesh lightning: one texture is cut into a strip mesh along its length.
  // Every flicker step the strip is re-bent into a new random bolt, exported as
  // stepped Spine deform keys. Optional extra bolts, branches, and width /
  // brightness jumps. Everything is a pure function of (settings, seed, step),
  // so live preview, baked preview and the three Spine exports agree exactly.
  const DEG = Math.PI / 180;
  const EPS = 1e-9;
  const round = value => Math.round(value * 1e6) / 1e6 || 0;
  const round2 = value => Math.round(value * 100) / 100 || 0;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const fail = message => { throw new Error(message); };
  const DEFAULTS = Object.freeze({
    mode: 'fixed', length: 320, angle: -90, thickness: 48, segments: 16, amplitude: 38, roughness: 0.55, rate: 18,
    bolts: 1, boltSpread: 24, boltAngle: 10, branches: 0, branchChance: 0.55, branchLength: 0.4, branchAngle: 35,
    widthJitter: 0.35, alphaJitter: 0.3, gap: 0.08, tailSwing: 25, lengthJitter: 0.25, taper: 0.55
  });
  const RANGES = {
    length: [10, 4000, '閃電長度'], angle: [-3600, 3600, '閃電方向'], thickness: [1, 600, '閃電粗細'], segments: [4, 48, '網格段數', true],
    amplitude: [0, 600, '扭曲幅度'], roughness: [0, 1, '鋸齒程度'], rate: [1, 60, '變化速度', false], bolts: [1, 4, '同時條數', true],
    boltSpread: [0, 600, '多條間距'], boltAngle: [0, 90, '多條角度差'], branches: [0, 3, '分岔數', true], branchChance: [0, 1, '分岔機率'],
    branchLength: [0.1, 1, '分岔長度'], branchAngle: [0, 90, '分岔角度'], widthJitter: [0, 1, '粗細跳動'], alphaJitter: [0, 1, '亮度跳動'],
    gap: [0, 0.9, '閃斷機率'], tailSwing: [0, 180, '尾端擺動'], lengthJitter: [0, 0.9, '長度變化'], taper: [0, 1, '尖端收細']
  };
  function normalize(raw, label = '閃電') {
    const source = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    if (raw !== undefined && raw !== null && source !== raw) fail(label + '設定格式不正確。');
    const result = {mode: source.mode === undefined ? DEFAULTS.mode : source.mode};
    if (!['fixed', 'free'].includes(result.mode)) fail(label + '的兩端模式必須是 fixed 或 free。');
    Object.keys(RANGES).forEach(key => {
      const [low, high, name, integer] = RANGES[key], value = source[key] === undefined ? DEFAULTS[key] : source[key];
      if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high || integer && !Number.isInteger(value)) fail(label + '的「' + name + '」必須介於 ' + low + '–' + high + (integer ? ' 的整數' : '') + '。');
      result[key] = value;
    });
    return result;
  }
  // Deterministic per (seed, bolt, step) stream; independent of other steps.
  function hash(a, b, c) {
    let h = (a >>> 0) ^ 0x9e3779b9;
    h = Math.imul(h ^ (b + 0x7f4a7c15), 0x85ebca6b) >>> 0;
    h = Math.imul(h ^ (c + 0x165667b1), 0xc2b2ae35) >>> 0;
    return (h ^ (h >>> 16)) >>> 0;
  }
  function stream(seed) {
    let t = seed >>> 0;
    return () => { t = (t + 0x6d2b79f5) >>> 0; let x = Math.imul(t ^ (t >>> 15), 1 | t); x ^= x + Math.imul(x ^ (x >>> 7), 61 | x); return ((x ^ (x >>> 14)) >>> 0) / 4294967296; };
  }
  // Strip mesh: top row 0..S, then bottom row S..0, so the first 2(S+1)
  // vertices run around the hull as Spine expects.
  function strip(segments, image) {
    const S = segments, horizontal = !image || image.width >= image.height, uvs = [], triangles = [];
    for (let i = 0; i <= S; i++) { const t = i / S; if (horizontal) uvs.push(t, 0); else uvs.push(0, t); }
    for (let i = S; i >= 0; i--) { const t = i / S; if (horizontal) uvs.push(t, 1); else uvs.push(1, t); }
    const bottom = i => S + 1 + (S - i);
    for (let i = 0; i < S; i++) triangles.push(i, bottom(i), i + 1, i + 1, bottom(i), bottom(i + 1));
    return {segments: S, uvs, triangles, hull: 2 * (S + 1), vertexCount: 2 * (S + 1)};
  }
  function branchSegments(settings) { return Math.max(4, Math.round(settings.segments / 2)); }
  // Vertices of a polyline with per-point half widths, in the strip order.
  function ribbon(points, halfWidths) {
    const S = points.length - 1, top = [], bottom = [];
    for (let i = 0; i <= S; i++) {
      const a = points[Math.max(0, i - 1)], b = points[Math.min(S, i + 1)];
      let tx = b.x - a.x, ty = b.y - a.y; const length = Math.hypot(tx, ty) || 1; tx /= length; ty /= length;
      const nx = -ty, ny = tx, h = halfWidths[i];
      top.push(points[i].x + nx * h, points[i].y + ny * h);
      bottom.push(points[i].x - nx * h, points[i].y - ny * h);
    }
    const vertices = top.slice();
    for (let i = S; i >= 0; i--) vertices.push(bottom[i * 2], bottom[i * 2 + 1]);
    return vertices.map(round2);
  }
  // Midpoint displacement with fixed ends; free tails get a random end offset.
  function displacement(rand, segments, amplitude, roughness, freeTail) {
    const d = new Array(segments + 1).fill(0);
    if (freeTail) d[segments] = (rand() * 2 - 1) * amplitude;
    (function split(lo, hi, amp) {
      if (hi - lo < 2) return;
      const mid = (lo + hi) >> 1;
      d[mid] = (d[lo] * (hi - mid) + d[hi] * (mid - lo)) / (hi - lo) + (rand() * 2 - 1) * amp;
      const next = amp * (0.35 + 0.65 * roughness);
      split(lo, mid, next); split(mid, hi, next);
    })(0, segments, amplitude);
    // A little extra per-point jitter makes high roughness look electric.
    for (let i = 1; i < segments; i++) d[i] += (rand() * 2 - 1) * amplitude * 0.25 * roughness;
    const limit = amplitude * 1.5;
    return d.map(value => clamp(value, -limit, limit));
  }
  function taperAt(t, taper, freeTail) {
    return freeTail ? 1 - taper * Math.pow(t, 1.4) : 1 - taper * (1 - Math.sin(Math.PI * t));
  }
  function bolt(rand, {start, angle, length, segments, amplitude, roughness, half, taper, freeTail}) {
    const dx = Math.cos(angle * DEG), dy = Math.sin(angle * DEG), nx = -dy, ny = dx;
    const d = displacement(rand, segments, amplitude, roughness, freeTail), points = [], widths = [];
    for (let i = 0; i <= segments; i++) {
      const t = i / segments;
      points.push({x: start.x + dx * length * t + nx * d[i], y: start.y + dy * length * t + ny * d[i]});
      widths.push(Math.max(0.2, half * taperAt(t, taper, freeTail)));
    }
    return {points, vertices: ribbon(points, widths)};
  }
  // Straight setup geometry; deform keys move every vertex from here.
  function setupVertices(settings, branch) {
    const S = branch ? branchSegments(settings) : settings.segments, length = branch ? settings.length * settings.branchLength : settings.length;
    const angle = branch ? 0 : settings.angle, half = (branch ? settings.thickness * 0.6 : settings.thickness) / 2;
    const dx = Math.cos(angle * DEG), dy = Math.sin(angle * DEG), points = [], widths = [];
    for (let i = 0; i <= S; i++) { points.push({x: dx * length * i / S, y: dy * length * i / S}); widths.push(half); }
    return ribbon(points, widths);
  }
  function strike(settings, seed, boltIndex, step) {
    const rand = stream(hash(seed, boltIndex + 1, step + 1)), free = settings.mode === 'free';
    const visible = rand() >= settings.gap;
    const alpha = visible ? clamp(1 - settings.alphaJitter * rand(), 0.05, 1) : 0;
    const widthScale = clamp(1 + (rand() * 2 - 1) * settings.widthJitter * 0.7, 0.15, 2);
    let angle = settings.angle, start = {x: 0, y: 0}, length = settings.length;
    if (settings.bolts > 1) {
      const spreadDraw = rand() * 2 - 1, angleDraw = rand() * 2 - 1;
      if (free) {
        const nx = -Math.sin(settings.angle * DEG), ny = Math.cos(settings.angle * DEG);
        start = {x: nx * spreadDraw * settings.boltSpread / 2, y: ny * spreadDraw * settings.boltSpread / 2};
        angle += angleDraw * settings.boltAngle;
      }
    }
    if (free) { angle += (rand() * 2 - 1) * settings.tailSwing; length *= 1 - settings.lengthJitter * rand(); }
    const amplitude = settings.amplitude * (settings.bolts > 1 && !free ? 0.75 + 0.5 * rand() : 1);
    const main = bolt(rand, {start, angle, length, segments: settings.segments, amplitude, roughness: settings.roughness,
      half: settings.thickness / 2 * widthScale, taper: settings.taper, freeTail: free});
    const branches = [];
    for (let j = 0; j < settings.branches; j++) {
      const show = visible && rand() < settings.branchChance;
      const at = 0.2 + 0.55 * rand(), side = rand() < 0.5 ? -1 : 1, spread = settings.branchAngle * (0.5 + 0.5 * rand());
      const lengthScale = 0.55 + 0.45 * rand();
      if (!show) { branches.push({visible: false, alpha: 0, vertices: null}); continue; }
      const index = clamp(Math.round(at * settings.segments), 1, settings.segments - 1);
      const a = main.points[index - 1], b = main.points[index + 1], base = main.points[index];
      const tangent = Math.atan2(b.y - a.y, b.x - a.x) / DEG;
      const branchLength = settings.length * settings.branchLength * lengthScale;
      const shape = bolt(rand, {start: base, angle: tangent + side * spread, length: branchLength, segments: branchSegments(settings),
        amplitude: settings.amplitude * settings.branchLength, roughness: settings.roughness, half: settings.thickness * 0.6 / 2 * widthScale,
        taper: Math.max(0.7, settings.taper), freeTail: true});
      branches.push({visible: true, alpha: alpha * (0.65 + 0.35 * rand()), vertices: shape.vertices});
    }
    return {visible, alpha, vertices: main.vertices, branches};
  }
  // Flicker steps inside the layer's active window. A looping full-length
  // window divides the loop exactly so the last step meets the first.
  function timing({duration, loop, startDelay = 0, activeDuration, rate, flow}) {
    let start = 0, active = duration;
    if (!flow) {
      start = Math.min(startDelay, duration);
      active = activeDuration > 0 ? Math.min(activeDuration, duration - start) : duration - start;
    }
    if (active <= EPS) return {start, end: start, steps: []};
    const fullLoop = flow ? flow === 'loop' : loop && start <= EPS && active >= duration - EPS;
    const count = fullLoop ? Math.max(1, Math.round(active * rate)) : Math.max(1, Math.ceil(active * rate - 1e-6));
    const step = fullLoop ? active / count : 1 / rate;
    const steps = [];
    for (let i = 0; i < count; i++) steps.push(round(start + i * step));
    return {start, end: round(start + active), steps, step};
  }
  function flowFactor(flow, time, duration) {
    return flow === 'in' ? clamp(time / duration, 0, 1) : flow === 'out' ? clamp(1 - time / duration, 0, 1) : 1;
  }
  // Slot layout per emitter: for each bolt its main strip then its branches.
  function lanes(settings) {
    const result = [];
    for (let b = 0; b < settings.bolts; b++) {
      result.push({bolt: b, branch: -1});
      for (let j = 0; j < settings.branches; j++) result.push({bolt: b, branch: j});
    }
    return result;
  }
  function stepIndexAt(plan, time) {
    if (!plan.steps.length || time < plan.start - EPS || time >= plan.end - EPS) return -1;
    const index = Math.floor((time - plan.start) / plan.step + 1e-9);
    return clamp(index, 0, plan.steps.length - 1);
  }
  // States in emitter-local coordinates (the caller adds the emitter origin).
  function states({settings, seed, duration, loop, startDelay, activeDuration, flow, time, color, blend, image, emitterId}) {
    const plan = timing({duration, loop, startDelay, activeDuration, rate: settings.rate, flow});
    const at = loop ? ((time % duration) + duration) % duration : clamp(time, 0, duration);
    const index = stepIndexAt(plan, at), factor = flowFactor(flow, at, duration);
    const result = [], main = strip(settings.segments, image), branch = strip(branchSegments(settings), image);
    lanes(settings).forEach((lane, laneIndex) => {
      const geometry = lane.branch < 0 ? main : branch;
      let alpha = 0, vertices = null;
      if (index >= 0) {
        const shot = strike(settings, seed, lane.bolt, index), part = lane.branch < 0 ? shot : shot.branches[lane.branch];
        alpha = part.visible ? part.alpha * factor : 0; vertices = part.vertices;
      }
      result.push({type: 'mesh', emitterId, lane: laneIndex, index: laneIndex, vertices: vertices || setupVertices(settings, lane.branch >= 0),
        uvs: geometry.uvs, triangles: geometry.triangles, color: color.slice(), alpha, blend, image, alive: alpha > 0, isLightning: true});
    });
    return result;
  }
  function hex(color, alpha) {
    return color.concat(alpha).map(value => Math.round(clamp(value, 0, 1) * 255).toString(16).padStart(2, '0')).join('');
  }
  // Bones, slots, mesh attachments and stepped timelines for one emitter.
  function exportEmitter({e, settings, seed, duration, loop, flow, family, colorTimeline, path, image, color, startIndex}) {
    const plan = timing({duration, loop, startDelay: e.startDelay || 0, activeDuration: e.emissionDuration, rate: settings.rate, flow});
    const main = strip(settings.segments, image), branch = strip(branchSegments(settings), image);
    const width = image ? image.width : 256, height = image ? image.height : 64;
    const bones = [], slots = [], attachments = {}, slotTracks = {}, deform = {};
    const shots = plan.steps.map((time, step) => ({time, shots: Array.from({length: settings.bolts}, (_, b) => strike(settings, seed, b, step))}));
    let keyframes = 0;
    lanes(settings).forEach((lane, laneIndex) => {
      const boneName = 'em_' + e.id + '_p' + (startIndex + laneIndex), slotName = boneName + '_slot', geometry = lane.branch < 0 ? main : branch;
      const setup = setupVertices(settings, lane.branch >= 0);
      bones.push({name: boneName, parent: 'em_' + e.id});
      slots.push({name: slotName, bone: boneName, color: hex(color, 0), attachment: 'particle', blend: e.blend});
      attachments[slotName] = {particle: {type: 'mesh', path, uvs: geometry.uvs.map(round), triangles: geometry.triangles.slice(),
        vertices: setup, hull: geometry.hull, width, height}};
      const colors = [], deforms = [], attachment = [];
      if (!plan.steps.length || plan.steps[0] > EPS) colors.push({color: hex(color, 0), curve: 'stepped'});
      shots.forEach(({time, shots: shot}) => {
        const part = lane.branch < 0 ? shot[lane.bolt] : shot[lane.bolt].branches[lane.branch];
        const alpha = part.visible ? round(part.alpha * flowFactor(flow, time, duration)) : 0;
        const key = {color: hex(color, alpha), curve: 'stepped'}; if (time > EPS) key.time = time;
        colors.push(key);
        if (part.visible && part.vertices) {
          const offsets = part.vertices.map((value, i) => round2(value - setup[i]));
          const frame = {vertices: offsets, curve: 'stepped'}; if (time > EPS) frame.time = time;
          deforms.push(frame);
        }
      });
      const fullLoop = flow ? flow === 'loop' : loop && plan.start <= EPS && plan.end >= duration - EPS;
      if (!fullLoop && plan.steps.length) colors.push({time: round(plan.end), color: hex(color, 0), curve: 'stepped'});
      const last = colors[colors.length - 1];
      if ((last.time || 0) < duration - EPS) colors.push({time: round(duration), color: last.color});
      // Remove the redundant stepped curve on the final key.
      if (colors.length) delete colors[colors.length - 1].curve;
      if (deforms.length) delete deforms[deforms.length - 1].curve;
      attachment.push({name: 'particle'});
      if (deforms.length && deforms[0].time) deforms.unshift({vertices: deforms[0].vertices.slice(), curve: 'stepped'});
      slotTracks[slotName] = {[colorTimeline]: colors, attachment};
      if (deforms.length) deform[slotName] = {particle: deforms};
      keyframes += colors.length + deforms.length + attachment.length;
    });
    const animation = {slots: slotTracks};
    if (Object.keys(deform).length) {
      if (family === '4.2') animation.attachments = {default: Object.fromEntries(Object.entries(deform).map(([slot, map]) => [slot, {particle: {deform: map.particle}}]))};
      else animation.deform = {default: deform};
    }
    return {bones, slots, attachments, animation, keyframes, laneCount: lanes(settings).length};
  }
  return {DEFAULTS, RANGES, normalize, strike, strip, setupVertices, timing, lanes, states, exportEmitter, branchSegments, hash, stream};
});
