(function (root, factory) {
  'use strict';
  const curveMath = typeof module === 'object' && module.exports ? require('./curve-math.js') : root.ParticleCurveMath;
  const api = factory(curveMath);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleTrail = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (CurveMath) {
  'use strict';
  const MAX_LENGTH = 10, MAX_TIME = 10;
  const DEFAULTS = Object.freeze({enabled: false, mode: 'stretch', duration: .35, samples: 8, segments: 16, opacity: .65, width: 1, taper: .8,
    coverage: 'history', showHead: true, axis: 'auto', flipTexture: false, lengthCurve: null,
    moveDuration: null, lengthDuration: null});
  const RANGES = {duration: [.05, 3], samples: [2, 24, true], segments: [4, 32, true], opacity: [0, 1], width: [.1, 4], taper: [0, 1]};
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const compiledLengths = new WeakMap();
  function defaults() { return {...DEFAULTS}; }
  function normalize(raw) {
    const source = raw === undefined ? {} : raw;
    if (!source || typeof source !== 'object' || Array.isArray(source)) throw new Error('拖尾設定必須是物件。');
    const result = defaults();
    if (source.enabled !== undefined) {
      if (typeof source.enabled !== 'boolean') throw new Error('拖尾開關必須是布林值。');
      result.enabled = source.enabled;
    }
    if (source.mode !== undefined) result.mode = source.mode;
    if (!['stretch', 'afterimage'].includes(result.mode)) throw new Error('拖尾模式僅支援 stretch／afterimage。');
    for (const [key, values] of Object.entries({coverage: ['history', 'path'], axis: ['auto', 'x', 'y']})) {
      if (source[key] !== undefined) result[key] = source[key];
      if (!values.includes(result[key])) throw new Error('拖尾「' + key + '」僅支援 ' + values.join('／') + '。');
    }
    for (const key of ['showHead', 'flipTexture']) {
      if (source[key] === undefined) continue;
      if (typeof source[key] !== 'boolean') throw new Error('拖尾「' + key + '」必須是布林值。');
      result[key] = source[key];
    }
    for (const [key, [low, high, integer]] of Object.entries(RANGES)) {
      const value = source[key] === undefined ? result[key] : source[key];
      if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high || integer && !Number.isInteger(value)) throw new Error('拖尾「' + key + '」必須介於 ' + low + '–' + high + (integer ? ' 的整數' : '') + '。');
      result[key] = value;
    }
    if (source.lengthCurve !== undefined && source.lengthCurve !== null) {
      if (!CurveMath) throw new Error('拖尾長度曲線模組尚未載入，請先載入 curve-math.js。');
      result.lengthCurve = CurveMath.normalize(source.lengthCurve, MAX_LENGTH, '拖尾長度曲線');
    }
    for (const key of ['moveDuration', 'lengthDuration']) {
      if (source[key] === undefined || source[key] === null) continue;
      if (typeof source[key] !== 'number' || !Number.isFinite(source[key]) || source[key] < .01 || source[key] > MAX_TIME)
        throw new Error('拖尾「' + key + '」必須介於 0.01–' + MAX_TIME + ' 秒。');
      result[key] = source[key];
    }
    return result;
  }
  function maxLength(settings) {
    if (!(settings && settings.mode === 'stretch' && settings.lengthCurve)) return 1;
    return Math.max(1, ...settings.lengthCurve.flatMap(point => [point.v, point.in ? point.in.y : 0, point.out ? point.out.y : 0]));
  }
  function segmentCount(settings, base) {
    return Math.min(320, (base === undefined ? settings.segments : base) * Math.ceil(maxLength(settings)));
  }
  function lengthAt(settings, age, life) {
    const points = settings && settings.lengthCurve;
    if (!points) return 1;
    if (!CurveMath) throw new Error('拖尾長度曲線模組尚未載入，請先載入 curve-math.js。');
    let compiled = compiledLengths.get(points);
    if (!compiled) { compiled = CurveMath.compile(points, MAX_LENGTH); compiledLengths.set(points, compiled); }
    const duration = settings.lengthDuration == null ? life : settings.lengthDuration;
    const evaluatedAge = clamp(age, 0, duration);
    const node = points.find(point => Math.abs(evaluatedAge - point.t * duration) <= .000000501);
    return compiled.sample(node ? node.t : evaluatedAge / duration);
  }
  function active(emitter) { return emitter.kind !== 'lightning' && !!(emitter.trail && emitter.trail.enabled); }
  function lanes(settings) {
    if (!settings || !settings.enabled) return [];
    if (settings.mode === 'stretch') return [{index: 0, mode: 'stretch'}];
    return Array.from({length: settings.samples}, (_, index) => ({index, mode: 'afterimage', delay: Math.round(settings.duration * (settings.samples - index) / settings.samples * 1e6) / 1e6}));
  }
  function horizontalAxis(image, settings) {
    return settings && settings.axis === 'x' || !(settings && settings.axis === 'y') && (!image || image.width >= image.height);
  }
  function strip(segments, image, settings) {
    segments = segmentCount(settings, segments);
    const horizontal = horizontalAxis(image, settings), uvs = [], triangles = [];
    const longitudinal = t => {
      const value = settings && settings.coverage === 'path' ? t : 1 - t;
      return settings && settings.flipTexture ? 1 - value : value;
    };
    for (let i = 0; i <= segments; i++) { const t = longitudinal(i / segments); uvs.push(...(horizontal ? [t, 0] : [0, t])); }
    for (let i = segments; i >= 0; i--) { const t = longitudinal(i / segments); uvs.push(...(horizontal ? [t, 1] : [1, t])); }
    const bottom = i => segments * 2 + 1 - i;
    for (let i = 0; i < segments; i++) triangles.push(i, bottom(i), i + 1, i + 1, bottom(i), bottom(i + 1));
    return {uvs, triangles, hull: (segments + 1) * 2};
  }
  function state(settings, lane, age, life, atAge, atPath, lengthFactor) {
    if (lane.mode === 'afterimage') {
      const source = atAge(age - lane.delay), fade = Math.pow(1 - lane.delay / (settings.duration + settings.duration / settings.samples), 1.3);
      const historyAge = age - lane.delay, edge = Math.min(life / 2, settings.duration / settings.samples);
      const envelope = clamp(historyAge / edge, 0, 1) * clamp((life - historyAge) / edge, 0, 1);
      const alpha = source.alpha * settings.opacity * fade * envelope;
      const size = settings.width;
      return {...source, width: source.width * size, height: source.height * size, scale: source.scale * size,
        ...(source.scaleX === undefined ? {} : {scaleX: source.scaleX * size, scaleY: source.scaleY * size}),
        alpha, alive: source.alive, isTrail: true, trailMode: 'afterimage', trailIndex: lane.index};
    }
    const wholePath = settings.coverage === 'path';
    if (wholePath && typeof atPath !== 'function') throw new Error('整條路徑光帶需要先啟用有效路徑，並設定至少兩個不同的路徑點。');
    const length = lengthFactor === undefined ? lengthAt(settings, age, life) : clamp(lengthFactor, 0, MAX_LENGTH);
    const segments = segmentCount(settings);
    const points = [], widths = [], sources = [], current = wholePath ? atAge(clamp(age, 0, Math.max(0, life - 1e-7))) : null;
    for (let i = 0; i <= segments; i++) {
      const t = i / segments, historyAge = age - t * settings.duration * length;
      const source = wholePath ? current : atAge(clamp(historyAge, 0, Math.max(0, life - 1e-7)));
      sources.push(source); points.push(wholePath ? atPath(t * length) : {x: source.x, y: source.y});
      // Length changes move longitudinal samples only. Keep the original
      // width envelope so shortening never also narrows the ribbon.
      const widthAge = age - t * settings.duration;
      const widthSource = wholePath || length === 1 ? source : atAge(clamp(widthAge, 0, Math.max(0, life - 1e-7)));
      const thickness = wholePath ? (horizontalAxis(source.image, settings) ? source.height : source.width) : Math.min(widthSource.width, widthSource.height);
      // Keep ribbon geometry continuous at birth/death. A hard zero-width
      // cutoff can select opposite sides of a floating-point Spine key time.
      const growth = wholePath ? 1 : clamp(widthAge / Math.max(.0001, Math.min(life, settings.duration / settings.segments)), 0, 1);
      const decay = wholePath ? 1 : clamp(1 - Math.max(0, widthAge - life) / settings.duration, 0, 1);
      widths.push(Math.max(0, thickness) * settings.width / 2 * (1 - settings.taper * t) * growth * decay);
    }
    const top = [], bottom = [];
    for (let i = 0; i < points.length; i++) {
      const a = points[Math.max(0, i - 1)], b = points[Math.min(segments, i + 1)];
      let tx = b.x - a.x, ty = b.y - a.y, distance = Math.hypot(tx, ty);
      if (distance <= 1e-8) {
        // Clamping at a birth/death endpoint repeats positions. Search for a
        // real history tangent instead of flipping to the head's direction.
        let before = null, after = null;
        for (let j = i - 1; j >= 0; j--) if (Math.hypot(points[j].x - points[i].x, points[j].y - points[i].y) > 1e-8) { before = points[j]; break; }
        for (let j = i + 1; j < points.length; j++) if (Math.hypot(points[j].x - points[i].x, points[j].y - points[i].y) > 1e-8) { after = points[j]; break; }
        const first = before || points[i], last = after || points[i];
        tx = last.x - first.x; ty = last.y - first.y; distance = Math.hypot(tx, ty);
        if (distance <= 1e-8 && after) { tx = after.x - points[i].x; ty = after.y - points[i].y; distance = Math.hypot(tx, ty); }
      }
      const angle = sources[0].rotation * Math.PI / 180;
      const nx = distance > 1e-8 ? -ty / distance : Math.sin(angle), ny = distance > 1e-8 ? tx / distance : -Math.cos(angle);
      top.push(points[i].x + nx * widths[i], points[i].y + ny * widths[i]);
      bottom.push(points[i].x - nx * widths[i], points[i].y - ny * widths[i]);
    }
    const vertices = top.slice();
    for (let i = segments; i >= 0; i--) vertices.push(bottom[i * 2], bottom[i * 2 + 1]);
    const head = sources[0], geometry = strip(settings.segments, head.image, settings);
    const fade = clamp(1 - Math.max(0, age - life) / settings.duration, 0, 1);
    const alpha = length <= 1e-9 || age < 0 || age >= life + settings.duration ? 0 : (wholePath ? head.alpha : Math.max(...sources.map(s => s.alpha))) * settings.opacity * fade;
    return {type: 'mesh', isTrail: true, trailMode: 'stretch', trailIndex: lane.index,
      emitterId: head.emitterId, index: head.index, x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
      y: points.reduce((sum, p) => sum + p.y, 0) / points.length, width: 0, height: 0, rotation: 0, scale: 1,
      vertices, uvs: geometry.uvs, triangles: geometry.triangles, hull: geometry.hull,
      color: head.color.slice(), alpha, alive: age >= -1e-9 && age < life + settings.duration - 1e-9, blend: head.blend, image: head.image,
      ...(head.sequenceFrame === undefined ? {} : {sequenceFrame: head.sequenceFrame})};
  }
  function states(settings, age, life, atAge, atPath, lengthFactor) { return lanes(settings).map(lane => state(settings, lane, age, life, atAge, atPath, lengthFactor)); }
  return {MAX_LENGTH, MAX_TIME, DEFAULTS, RANGES, defaults, normalize, maxLength, segmentCount, lengthAt, active, lanes, strip, state, states};
});
