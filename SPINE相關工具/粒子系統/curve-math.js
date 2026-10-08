(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleCurveMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const fail = message => { throw new Error(message); };
  function bounded(value, low, high, label) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high) fail(label + '必須是 ' + low + ' 到 ' + high + ' 的有限數值。');
    return value;
  }
  function normalize(points, maxValue, label) {
    maxValue = maxValue === undefined ? 4 : maxValue;
    label = label || '生命週期曲線';
    if (typeof maxValue !== 'number' || !Number.isFinite(maxValue) || maxValue <= 0) fail('曲線最大值必須是正的有限數值。');
    if (!Array.isArray(points) || points.length < 2 || points.length > 32) fail(label + '必須有 2 到 32 個控制點。');
    let previous = -1;
    const result = points.map(point => {
      if (!point || typeof point !== 'object' || Array.isArray(point)) fail(label + '控制點格式不正確。');
      const t = bounded(point.t, 0, 1, label + '時間');
      const v = bounded(point.v, 0, maxValue, label + '數值');
      if (t <= previous) fail(label + '時間必須嚴格遞增，不能有重複控制點。');
      previous = t;
      const normalized = {t, v};
      if (point.curve !== undefined) {
        if (!['linear', 'bezier', 'stepped'].includes(point.curve)) fail(label + '區段必須是 linear、bezier 或 stepped。');
        normalized.curve = point.curve;
      }
      ['in', 'out'].forEach(kind => {
        if (point[kind] === undefined) return;
        const handle = point[kind];
        if (!handle || typeof handle !== 'object' || Array.isArray(handle)) fail(label + 'Bezier 把手格式不正確。');
        normalized[kind] = {x: bounded(handle.x, 0, 1, label + '把手 X'), y: bounded(handle.y, 0, maxValue, label + '把手 Y')};
      });
      return normalized;
    });
    if (result[0].t !== 0 || result[result.length - 1].t !== 1) fail(label + '必須包含 t=0 與 t=1 的端點。');
    for (let i = 1; i < result.length; i++) {
      const x1 = result[i - 1].out ? result[i - 1].out.x : 1 / 3;
      const x2 = result[i].in ? result[i].in.x : 2 / 3;
      if (x1 > x2) fail(label + 'Bezier 把手 X 必須符合 out.x ≤ in.x，不能交叉。');
    }
    return result;
  }

  const cubic = (a, b, c, d) => [a, 3 * (b - a), 3 * (a - 2 * b + c), d - a + 3 * (b - c)];
  const polynomial = (coefficients, parameter) => ((coefficients[3] * parameter + coefficients[2]) * parameter + coefficients[1]) * parameter + coefficients[0];
  function solveX(coefficients, target) {
    if (target <= 0) return 0;
    if (target >= 1) return 1;
    let low = 0, high = 1;
    for (let iteration = 0; iteration < 36; iteration++) {
      const middle = (low + high) / 2;
      if (polynomial(coefficients, middle) < target) low = middle;
      else high = middle;
    }
    return (low + high) / 2;
  }
  function areaCoefficients(x, y) {
    const product = Array(6).fill(0);
    for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) product[i + j] += y[i] * x[j + 1] * (j + 1);
    return product.map((value, index) => value / (index + 1));
  }
  function areaAt(coefficients, parameter) {
    let value = coefficients[5];
    for (let index = 4; index >= 0; index--) value = value * parameter + coefficients[index];
    return value * parameter;
  }

  /** Compiles once: cached per-key prefix areas plus exact polynomial ∫Y(s)X'(s)ds.
   * Handle x coordinates are normalized segment progress; handle y is absolute value.
   * sample/integral clamp normalized lifetime time to [0,1]; alpha uses maxValue=1.
   */
  function compile(raw, maxValue) {
    maxValue = maxValue === undefined ? 4 : maxValue;
    const points = normalize(raw, maxValue), segments = [], prefix = [0], dense = [0, 1];
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i], duration = b.t - a.t;
      const mode = a.curve || 'linear';
      const segment = {a, b, duration, mode};
      if (mode === 'bezier') {
        const out = a.out || {x: 1 / 3, y: a.v}, incoming = b.in || {x: 2 / 3, y: b.v};
        segment.x = cubic(0, out.x, incoming.x, 1);
        segment.y = cubic(a.v, out.y, incoming.y, b.v);
        segment.area = areaCoefficients(segment.x, segment.y);
        segment.total = duration * areaAt(segment.area, 1);
        for (let sample = 1; sample < 32; sample++) dense.push(a.t + duration * polynomial(segment.x, sample / 32));
      } else segment.total = duration * (mode === 'stepped' ? a.v : (a.v + b.v) / 2);
      segments.push(segment); prefix.push(prefix[prefix.length - 1] + segment.total); dense.push(a.t, b.t);
    }
    function time(value) {
      if (typeof value !== 'number' || !Number.isFinite(value)) fail('曲線取樣時間必須是有限數值。');
      return clamp(value, 0, 1);
    }
    function indexAt(value) {
      let low = 0, high = segments.length - 1;
      while (low < high) {
        const middle = (low + high) >>> 1;
        if (segments[middle].b.t <= value) low = middle + 1;
        else high = middle;
      }
      return low;
    }
    function sample(value) {
      const t = time(value);
      if (t === 0) return points[0].v;
      if (t === 1) return points[points.length - 1].v;
      const segment = segments[indexAt(t)], progress = (t - segment.a.t) / segment.duration;
      if (segment.mode === 'stepped') return segment.a.v;
      if (segment.mode === 'linear') return segment.a.v + (segment.b.v - segment.a.v) * progress;
      return clamp(polynomial(segment.y, solveX(segment.x, progress)), 0, maxValue);
    }
    function integral(value) {
      const t = time(value);
      if (t === 0) return 0;
      if (t === 1) return prefix[prefix.length - 1];
      const index = indexAt(t), segment = segments[index], progress = (t - segment.a.t) / segment.duration;
      let partial;
      if (segment.mode === 'stepped') partial = segment.a.v * (t - segment.a.t);
      else if (segment.mode === 'linear') partial = segment.duration * (segment.a.v * progress + (segment.b.v - segment.a.v) * progress * progress / 2);
      else partial = segment.duration * areaAt(segment.area, solveX(segment.x, progress));
      return prefix[index] + partial;
    }
    return {sample, evaluate: sample, integral, sampleTimes: Array.from(new Set(dense)).sort((a, b) => a - b)};
  }
  function evaluate(points, t, maxValue) { return compile(points, maxValue).sample(t); }
  return {normalize, compile, evaluate};
});
