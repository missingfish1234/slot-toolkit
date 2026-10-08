(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleScrub = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const fail = message => { throw new Error(message); };

  function finite(value, label) {
    if (typeof value !== 'number' || !Number.isFinite(value)) fail(label + '必須是有限數值。');
    return value;
  }

  function bound(value, fallback, label) {
    if (value === undefined || value === fallback) return fallback;
    return finite(value, label);
  }

  function decimalPlaces(value) {
    const parts = Math.abs(value).toString().toLowerCase().split('e');
    const decimals = (parts[0].split('.')[1] || '').length;
    return Math.max(0, decimals - Number(parts[1] || 0));
  }

  function nearestInteger(value) {
    // Unlike Math.round(-0.5), displacement ties behave symmetrically in both directions.
    return value < 0 ? -Math.floor(-value + 0.5) : Math.floor(value + 0.5);
  }

  function floorGrid(value) {
    // Decimal quotients such as 0.3 / 0.1 can fall a few ulps below an integer.
    const tolerance = Math.min(1e-7, Number.EPSILON * Math.max(1, Math.abs(value)) * 8);
    return Math.floor(value + tolerance);
  }

  /**
   * valueAtDrag({value, deltaX, step, min?, max?, pixelsPerStep=6, modifier='none'})
   *
   * Always pass the gesture's ORIGINAL value and total horizontal displacement.
   * The original value snaps to its nearest grid point; cumulative displacement
   * adds whole grid steps. Positive deltas increase values. Shift speeds up 10x;
   * Alt slows down 10x by requiring more pixels, without inventing fractional steps.
   * A finite min is the HTML grid origin; otherwise origin is zero. Missing bounds,
   * min=-Infinity and max=Infinity are unbounded. Off-grid maxima clamp inward.
   * The caller owns click/drag thresholds, modifier selection and DOM updates.
   */
  function valueAtDrag(options) {
    if (!options || typeof options !== 'object' || Array.isArray(options)) fail('需要有效的數值拖曳參數。');
    const value = finite(options.value, '拖曳起始值');
    const deltaX = finite(options.deltaX, '拖曳距離');
    const step = finite(options.step, '數值步長');
    const pixels = finite(options.pixelsPerStep === undefined ? 6 : options.pixelsPerStep, '每步像素');
    if (step <= 0 || pixels <= 0) fail('數值步長與每步像素必須大於 0。');
    const minimum = bound(options.min, -Infinity, '最小值');
    const maximum = bound(options.max, Infinity, '最大值');
    if (minimum > maximum) fail('最小值不能大於最大值。');
    const modifier = options.modifier === undefined ? 'none' : options.modifier;
    if (!['none', 'shift', 'alt'].includes(modifier)) fail('拖曳修飾鍵必須是 none、shift 或 alt。');
    const gain = modifier === 'shift' ? 10 : modifier === 'alt' ? 0.1 : 1;
    const origin = Number.isFinite(minimum) ? minimum : 0;
    const anchor = nearestInteger((value - origin) / step);
    const displacement = nearestInteger(deltaX / pixels * gain);
    const lower = Number.isFinite(minimum) ? 0 : -Infinity;
    const upper = Number.isFinite(maximum) ? floorGrid((maximum - origin) / step) : Infinity;
    let index = Math.min(upper, Math.max(lower, anchor + displacement));
    if (!Number.isFinite(index)) fail('拖曳結果超出可表示的數值範圍。');
    const precision = Math.max(decimalPlaces(step), decimalPlaces(origin));
    function valueFor(gridIndex) {
      const raw = origin + gridIndex * step;
      if (!Number.isFinite(raw)) fail('拖曳結果超出可表示的數值範圍。');
      // Keep ordinary HTML decimal steps canonical (e.g. 0.3 instead of
      // 0.30000000000000004); tiny/exponential steps retain their numeric precision.
      const clean = precision <= 100 && Math.abs(raw) < 1e21 ? Number(raw.toFixed(precision)) : raw;
      return Object.is(clean, -0) ? 0 : clean;
    }
    let result = valueFor(index);
    // Enforce real bounds after decimal cleanup: tolerance must never admit a
    // grid point above a genuinely off-grid maximum (including negative bounds).
    if (result > maximum) { index--; result = valueFor(index); }
    if (result < minimum) { index++; result = valueFor(index); }
    if (result < minimum || result > maximum) fail('指定範圍內沒有可用的數值步長位置。');
    return result;
  }
  return {valueAtDrag};
});
