(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticlePathMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const EPS = 1e-9, MAX_POINTS = 48, DEG = 180 / Math.PI;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const mod = (value, period) => ((value % period) + period) % period;
  function defaults() {
    return {enabled: false, points: [{x: -160, y: 0}, {x: 160, y: 0}], closed: false,
      smooth: 0, reverse: false, mode: 'lifetime', offsets: false};
  }
  function normalize(raw) {
    if (raw === null) return null;
    const source = raw === undefined ? {} : raw;
    if (!source || typeof source !== 'object' || Array.isArray(source)) throw new Error('路徑設定格式不正確。');
    const result = defaults();
    for (const key of ['enabled', 'closed', 'reverse', 'offsets']) {
      if (source[key] !== undefined) {
        if (typeof source[key] !== 'boolean') throw new Error('路徑 ' + key + ' 必須是布林值。');
        result[key] = source[key];
      }
    }
    if (source.smooth !== undefined) {
      if (!Number.isInteger(source.smooth) || source.smooth < 0 || source.smooth > 3) throw new Error('路徑平滑必須是 0 到 3 的整數。');
      result.smooth = source.smooth;
    }
    if (source.mode !== undefined) {
      if (!['lifetime', 'speed'].includes(source.mode)) throw new Error('路徑速度模式不正確。');
      result.mode = source.mode;
    }
    if (source.points !== undefined) {
      if (!Array.isArray(source.points) || source.points.length < 2 || source.points.length > MAX_POINTS) throw new Error('路徑必須包含 2 到 ' + MAX_POINTS + ' 個控制點。');
      result.points = source.points.map(point => {
        if (!point || typeof point !== 'object' || Array.isArray(point)) throw new Error('路徑控制點格式不正確。');
        for (const key of ['x', 'y']) if (typeof point[key] !== 'number' || !Number.isFinite(point[key]) || Math.abs(point[key]) > 4000) throw new Error('路徑控制點座標必須是 −4000 到 4000 的有限數值。');
        const next = {x: point.x, y: point.y};
        if (point.curve !== undefined) {
          if (!['linear', 'bezier'].includes(point.curve)) throw new Error('路徑控制點曲線必須是直線或貝茲。');
          next.curve = point.curve;
        }
        for (const side of ['in', 'out']) if (point[side] !== undefined) {
          const handle = point[side];
          if (!handle || typeof handle !== 'object' || Array.isArray(handle)) throw new Error('路徑貝茲控制柄格式不正確。');
          for (const axis of ['x', 'y']) if (typeof handle[axis] !== 'number' || !Number.isFinite(handle[axis]) ||
            Math.abs(handle[axis]) > 8000 || Math.abs(point[axis] + handle[axis]) > 4000 + EPS) throw new Error('路徑貝茲控制柄座標必須位於 −4000 到 4000。');
          next[side] = {x: handle.x, y: handle.y};
        }
        return next;
      });
    }
    return result;
  }
  function preset(name, width, height) {
    width = width === undefined ? 320 : width; height = height === undefined ? 180 : height;
    for (const value of [width, height]) if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 8000) throw new Error('路徑預設寬高必須是 0 到 8000。');
    const x = width / 2, y = height / 2, points = [];
    if (name === 'line') return {points: [{x: -x, y: 0}, {x, y: 0}], closed: false, smooth: 0};
    if (name === 'rectangle') return {points: [{x: -x, y: -y}, {x, y: -y}, {x, y}, {x: -x, y}], closed: true, smooth: 0};
    if (name === 'ellipse') {
      const k = 4 * (Math.sqrt(2) - 1) / 3;
      points.push({x, y: 0, in: {x: 0, y: -k * y}, out: {x: 0, y: k * y}, curve: 'bezier'},
        {x: 0, y, in: {x: k * x, y: 0}, out: {x: -k * x, y: 0}, curve: 'bezier'},
        {x: -x, y: 0, in: {x: 0, y: k * y}, out: {x: 0, y: -k * y}, curve: 'bezier'},
        {x: 0, y: -y, in: {x: -k * x, y: 0}, out: {x: k * x, y: 0}, curve: 'bezier'});
      return {points, closed: true, smooth: 0};
    }
    function hermite(count, closed, position, derivative) {
      const step = 1 / count;
      for (let i = 0; i < count + (closed ? 0 : 1); i++) {
        const u = i / count, p = position(u), d = derivative(u), point = {x: p.x, y: p.y, curve: 'bezier'};
        if (closed || i > 0) point.in = {x: -d.x * step / 3, y: -d.y * step / 3};
        if (closed || i < count) point.out = {x: d.x * step / 3, y: d.y * step / 3};
        points.push(point);
      }
      return {points, closed, smooth: 0};
    }
    if (name === 'figure8') return hermite(8, true,
      u => ({x: Math.sin(u * Math.PI * 2) * x, y: Math.sin(u * Math.PI * 4) * y}),
      u => ({x: Math.cos(u * Math.PI * 2) * x * Math.PI * 2, y: Math.cos(u * Math.PI * 4) * y * Math.PI * 4}));
    if (name === 's') {
      return hermite(4, false, u => ({x: (u * 2 - 1) * x, y: Math.sin(u * Math.PI * 2) * y}),
        u => ({x: 2 * x, y: Math.cos(u * Math.PI * 2) * y * Math.PI * 2}));
    }
    if (name === 'spiral') {
      return hermite(8, false, u => {const t = u * Math.PI * 4, radius = .05 + u * .95; return {x: Math.cos(t) * x * radius, y: Math.sin(t) * y * radius};},
        u => {const t = u * Math.PI * 4, radius = .05 + u * .95; return {x: x * (.95 * Math.cos(t) - radius * Math.PI * 4 * Math.sin(t)), y: y * (.95 * Math.sin(t) + radius * Math.PI * 4 * Math.cos(t))};});
    }
    throw new Error('不支援的路徑預設：' + name);
  }
  const add = (a, b) => ({x: a.x + b.x, y: a.y + b.y});
  const sub = (a, b) => ({x: a.x - b.x, y: a.y - b.y});
  const mul = (a, value) => ({x: a.x * value, y: a.y * value});
  const mix = (a, b, value) => ({x: a.x + (b.x - a.x) * value, y: a.y + (b.y - a.y) * value});
  const length = vector => Math.hypot(vector.x, vector.y);
  const dot = (a, b) => a.x * b.x + a.y * b.y;
  const cross = (a, b) => a.x * b.y - a.y * b.x;
  const unit = vector => length(vector) > EPS ? mul(vector, 1 / length(vector)) : {x: 0, y: 0};
  const unwrap = (angle, previous) => previous + mod(angle - previous + 180, 360) - 180;
  function isBezier(a, b) { return a.curve !== 'linear' && (a.curve === 'bezier' || !!a.out || !!b.in); }
  function hasBezier(path) { return path.points.some((point, i, points) => (path.closed || i < points.length - 1) && isBezier(point, points[(i + 1) % points.length])); }
  function segment(a, b) {
    return isBezier(a, b) ? [a, a.out ? add(a, a.out) : a, b.in ? add(b, b.in) : b, b] :
      [a, mix(a, b, 1 / 3), mix(a, b, 2 / 3), b];
  }
  function at(curve, t) {
    const u = 1 - t;
    return {x: u * u * u * curve[0].x + 3 * u * u * t * curve[1].x + 3 * u * t * t * curve[2].x + t * t * t * curve[3].x,
      y: u * u * u * curve[0].y + 3 * u * u * t * curve[1].y + 3 * u * t * t * curve[2].y + t * t * t * curve[3].y};
  }
  function derivative(curve, t) {
    const u = 1 - t;
    return add(add(mul(sub(curve[1], curve[0]), 3 * u * u), mul(sub(curve[2], curve[1]), 6 * u * t)), mul(sub(curve[3], curve[2]), 3 * t * t));
  }
  function tangent(curve, t, direction) {
    let result = derivative(curve, t);
    if (length(result) > EPS) return result;
    // A zero endpoint handle is common. Use the one-sided cubic limit, and
    // retain separate incoming/outgoing directions at an interior cusp.
    const delta = 1e-6, next = clamp(t + (direction || (t < 1 ? 1 : -1)) * delta, 0, 1);
    result = derivative(curve, next);
    return length(result) > EPS ? result : sub(curve[3], curve[0]);
  }
  function divide(curve, t) {
    const a = mix(curve[0], curve[1], t), b = mix(curve[1], curve[2], t), c = mix(curve[2], curve[3], t);
    const d = mix(a, b, t), e = mix(b, c, t), p = mix(d, e, t);
    return [[curve[0], a, d, p], [p, e, c, curve[3]]];
  }
  function flatten(curve, tolerance) {
    const result = [{t: 0, point: at(curve, 0)}];
    function visit(part, low, high, depth) {
      const chord = sub(part[3], part[0]), span = length(chord);
      const polygon = length(sub(part[1], part[0])) + length(sub(part[2], part[1])) + length(sub(part[3], part[2]));
      const flat = span > EPS ? Math.max(Math.abs(cross(sub(part[1], part[0]), chord)), Math.abs(cross(sub(part[2], part[0]), chord))) / span : polygon;
      // The arc-length lookup also needs a faithful parameter-to-distance
      // map on straight but nonuniform cubics (including a stop/reversal).
      const parameterError = Math.max(length(sub(part[1], mix(part[0], part[3], 1 / 3))), length(sub(part[2], mix(part[0], part[3], 2 / 3))));
      if (depth >= 18 || (flat <= tolerance && polygon - span <= tolerance && parameterError <= tolerance)) {
        result.push({t: high, point: at(curve, high)}); return;
      }
      if (result.length > 32768) throw new Error('路徑貝茲彎折過多，請縮短控制柄或增加控制點。');
      const halves = divide(part, .5), middle = (low + high) / 2;
      visit(halves[0], low, middle, depth + 1); visit(halves[1], middle, high, depth + 1);
    }
    visit(curve, 0, 1, 0); return result;
  }
  function roots(a, b, c) {
    if (Math.abs(a) < 1e-12) return Math.abs(b) < 1e-12 ? [] : [-c / b];
    const discriminant = b * b - 4 * a * c;
    if (discriminant < 0) return [];
    const q = -.5 * (b + (b < 0 ? -1 : 1) * Math.sqrt(discriminant));
    return Math.abs(q) > 1e-12 ? [q / a, c / q] : [-b / (2 * a)];
  }
  function critical(curve) {
    const c = mul(sub(curve[1], curve[0]), 3);
    const b = mul(add(sub(curve[2], mul(curve[1], 2)), curve[0]), 6);
    const a = mul(add(sub(curve[3], mul(curve[2], 3)), sub(mul(curve[1], 3), curve[0])), 3);
    return [...roots(a.x, b.x, c.x), ...roots(a.y, b.y, c.y), ...roots(-cross(a, b), 2 * cross(c, a), cross(c, b))]
      .filter(t => Number.isFinite(t) && t > 1e-8 && t < 1 - 1e-8);
  }
  function compileBezier(settings) {
    let anchors = settings.points;
    if (settings.reverse) anchors = settings.closed ? [anchors[0], ...anchors.slice(1).reverse()] : anchors.slice().reverse();
    const count = settings.closed ? anchors.length : anchors.length - 1, segments = [], leaves = [], points = [], cumulative = [0];
    let totalLength = 0, previousAngle;
    for (let i = 0; i < count; i++) {
      const a = anchors[i], b = anchors[(i + 1) % anchors.length];
      const curve = settings.reverse ? segment(b, a).reverse() : segment(a, b);
      const table = flatten(curve, .02), record = {curve, table, start: totalLength, events: [0, .5, 1, ...critical(curve)]};
      record.table[0].distance = 0;
      for (let j = 1; j < table.length; j++) {
        const first = table[j - 1], last = table[j], span = length(sub(last.point, first.point));
        last.distance = first.distance + span;
        if (span <= EPS) continue;
        const vector = tangent(curve, first.t, 1), endVector = tangent(curve, last.t, -1);
        let angle = Math.atan2(vector.y, vector.x) * DEG;
        if (previousAngle !== undefined) angle = unwrap(angle, previousAngle);
        const endAngle = unwrap(Math.atan2(endVector.y, endVector.x) * DEG, angle);
        leaves.push({curve, low: first.t, high: last.t, start: totalLength, span, angle, endAngle});
        points.push({x: first.point.x, y: first.point.y});
        totalLength += span; cumulative.push(totalLength); previousAngle = endAngle;
      }
      record.length = totalLength - record.start; segments.push(record);
    }
    if (totalLength < 1e-6 || !leaves.length) throw new Error('路徑長度過短，請拉開控制點。');
    if (!settings.closed) points.push({...at(leaves[leaves.length - 1].curve, 1)});
    const firstAngle = leaves[0].angle, lastAngle = leaves[leaves.length - 1].endAngle;
    const totalTurn = settings.closed ? Math.round((unwrap(firstAngle, lastAngle) - firstAngle) / 360) * 360 || 0 : 0;
    function distanceAt(record, t) {
      const table = record.table;
      let low = 0, high = table.length - 1;
      while (low + 1 < high) {const middle = (low + high) >> 1; if (table[middle].t <= t) low = middle; else high = middle;}
      const a = table[low], b = table[high];
      return record.start + a.distance + (b.distance - a.distance) * (t - a.t) / (b.t - a.t);
    }
    const knots = [0, 1], corners = [];
    segments.forEach((record, i) => {
      record.events.forEach(t => knots.push(distanceAt(record, t) / totalLength));
      if (i > 0 || settings.closed) {
        const previous = segments[(i + segments.length - 1) % segments.length];
        const incoming = tangent(previous.curve, 1, -1), outgoing = tangent(record.curve, 0, 1);
        const angle = Math.atan2(cross(incoming, outgoing), dot(incoming, outgoing)) * DEG;
        if (Math.abs(angle) > 1e-5 && length(incoming) > EPS && length(outgoing) > EPS) corners.push(i ? record.start / totalLength : 1);
      }
      critical(record.curve).forEach(t => {
        if (length(derivative(record.curve, t)) < 1e-6) {
          const before = tangent(record.curve, t, -1), after = tangent(record.curve, t, 1);
          if (dot(before, after) < 0) corners.push(distanceAt(record, t) / totalLength);
        }
      });
    });
    knots.push(...corners);
    const sampleFractions = knots.sort((a, b) => a - b).filter((value, i, all) => i === 0 || value - all[i - 1] > 1e-10);
    function sample(progress) {
      if (typeof progress !== 'number' || !Number.isFinite(progress)) throw new Error('路徑進度必須是有限數值。');
      const cycle = settings.closed ? Math.floor(progress) : 0;
      const u = settings.closed ? mod(progress, 1) : clamp(progress, 0, 1), distance = u * totalLength;
      let low = 0, high = leaves.length;
      while (low + 1 < high) { const middle = (low + high) >> 1; if (leaves[middle].start <= distance) low = middle; else high = middle; }
      const leaf = leaves[Math.min(leaves.length - 1, low)];
      const fraction = clamp((distance - leaf.start) / leaf.span, 0, 1), t = leaf.low + (leaf.high - leaf.low) * fraction;
      const point = at(leaf.curve, t), vector = tangent(leaf.curve, t, t < 1 ? 1 : -1);
      const reference = leaf.angle + (leaf.endAngle - leaf.angle) * fraction;
      return {x: point.x, y: point.y, angle: unwrap(Math.atan2(vector.y, vector.x) * DEG, reference) + cycle * totalTurn};
    }
    return {points, closed: settings.closed, totalLength, totalTurn, corners: corners.sort((a, b) => a - b), sampleFractions, sample};
  }
  function splitSegment(raw, index, t) {
    const path = normalize(raw), count = path.closed ? path.points.length : path.points.length - 1;
    t = t === undefined ? .5 : t;
    if (!Number.isInteger(index) || index < 0 || index >= count || !Number.isFinite(t) || t <= 0 || t >= 1) throw new Error('請選擇有效的路徑線段與分割位置。');
    if (path.points.length >= MAX_POINTS) throw new Error('路徑最多 ' + MAX_POINTS + ' 個控制點。');
    if (!hasBezier(path) && path.smooth > 0) throw new Error('請先精簡為貝茲，再加入保留形狀的控制點。');
    const a = path.points[index], b = path.points[(index + 1) % path.points.length];
    let middle;
    if (isBezier(a, b)) {
      const halves = divide(segment(a, b), t), left = halves[0], right = halves[1];
      a.out = sub(left[1], a); b.in = sub(right[2], b); a.curve = 'bezier';
      middle = {x: left[3].x, y: left[3].y, in: sub(left[2], left[3]), out: sub(right[1], right[0]), curve: 'bezier'};
    } else { middle = mix(a, b, t); if (a.curve !== undefined) middle.curve = a.curve; }
    path.points.splice(index + 1, 0, middle); return normalize(path);
  }
  function pointDistance(point, a, b) {
    const delta = sub(b, a), squared = dot(delta, delta), t = squared > EPS * EPS ? clamp(dot(sub(point, a), delta) / squared, 0, 1) : 0;
    return length(sub(point, mix(a, b, t)));
  }
  function convertToBezier(raw, tolerance) {
    const settings = normalize(raw);
    tolerance = tolerance === undefined ? .75 : tolerance;
    if (!Number.isFinite(tolerance) || tolerance <= 0 || tolerance > 20) throw new Error('路徑精簡誤差必須大於 0，且不超過 20 px。');
    if (hasBezier(settings)) return settings;
    const compiled = compile({...settings, reverse: false}), points = compiled.points.map(point => ({x: point.x, y: point.y}));
    if (settings.closed) points.push({...points[0]});
    const end = points.length - 1, boundaries = new Set([0, end]);
    // Preserve authored sharp corners. Small polygon steps of a circle are
    // fitted together; they are not mistaken for individual editable corners.
    for (let i = 1; i < end; i++) {
      const before = sub(points[i], points[i - 1]), after = sub(points[i + 1], points[i]);
      if (Math.abs(Math.atan2(cross(before, after), dot(before, after))) > Math.PI / 4 + 1e-8) boundaries.add(i);
    }
    const sharp = new Set(boundaries);
    if (settings.closed && boundaries.size === 2) for (let quarter = 1; quarter < 4; quarter++) boundaries.add(Math.round(end * quarter / 4));
    const cuts = Array.from(boundaries).sort((a, b) => a - b), curves = [];
    function direction(index, side) {
      if (sharp.has(index) && index > 0 && index < end) return unit(side > 0 ? sub(points[index + 1], points[index]) : sub(points[index - 1], points[index]));
      if (settings.closed && (index === 0 || index === end)) return unit(side > 0 ? sub(points[1], points[end - 1]) : sub(points[end - 1], points[1]));
      const before = points[Math.max(0, index - 1)], after = points[Math.min(end, index + 1)];
      return unit(side > 0 ? sub(after, before) : sub(before, after));
    }
    function fit(first, last) {
      const start = points[first], finish = points[last], tangentA = direction(first, 1), tangentB = direction(last, -1), distances = [0];
      if (last === first + 1) {
        curves.push([start, mix(start, finish, 1 / 3), mix(start, finish, 2 / 3), finish]);
        if (curves.length + (settings.closed ? 0 : 1) > MAX_POINTS) throw new Error('目前路徑無法在 ' + MAX_POINTS + ' 個控制點內保持精簡誤差，請保留原路徑或提高誤差。');
        return;
      }
      for (let i = first + 1; i <= last; i++) distances.push(distances[distances.length - 1] + length(sub(points[i], points[i - 1])));
      const total = distances[distances.length - 1];
      let c00 = 0, c01 = 0, c11 = 0, x0 = 0, x1 = 0;
      const params = distances.map(value => total > EPS ? value / total : 0);
      params.forEach((t, i) => {
        const u = 1 - t, b1 = 3 * u * u * t, b2 = 3 * u * t * t;
        const a1 = mul(tangentA, b1), a2 = mul(tangentB, b2);
        const base = add(mul(start, u * u * u + b1), mul(finish, t * t * t + b2));
        const error = sub(points[first + i], base);
        c00 += dot(a1, a1); c01 += dot(a1, a2); c11 += dot(a2, a2); x0 += dot(a1, error); x1 += dot(a2, error);
      });
      const determinant = c00 * c11 - c01 * c01;
      let alpha = determinant > 1e-12 ? (x0 * c11 - x1 * c01) / determinant : total / 3;
      let beta = determinant > 1e-12 ? (x1 * c00 - x0 * c01) / determinant : total / 3;
      if (alpha <= EPS || beta <= EPS || alpha > total * 4 || beta > total * 4) alpha = beta = total / 3;
      const bounded = point => ({x: clamp(point.x, -4000, 4000), y: clamp(point.y, -4000, 4000)});
      const curve = [start, bounded(add(start, mul(tangentA, alpha))), bounded(add(finish, mul(tangentB, beta))), finish];
      let error = 0, split = Math.floor((first + last) / 2);
      // Check the reverse distance too: a fitting curve must not cut outside
      // the source polyline between its vertices or across a concave corner.
      const flattened = flatten(curve, Math.min(.02, tolerance / 8));
      for (let i = first + 1; i < last; i++) {
        let closest = Infinity;
        for (let j = 1; j < flattened.length; j++) closest = Math.min(closest, pointDistance(points[i], flattened[j - 1].point, flattened[j].point));
        if (closest + Math.min(.02, tolerance / 8) > error) {error = closest + Math.min(.02, tolerance / 8); split = i;}
      }
      flattened.forEach(node => {
        let closest = Infinity;
        for (let i = first; i < last; i++) closest = Math.min(closest, pointDistance(node.point, points[i], points[i + 1]));
        error = Math.max(error, closest + Math.min(.02, tolerance / 8));
      });
      if (error <= tolerance) {curves.push(curve); if (curves.length + (settings.closed ? 0 : 1) > MAX_POINTS) throw new Error('目前路徑無法在 ' + MAX_POINTS + ' 個控制點內保持精簡誤差，請保留原路徑或提高誤差。'); return;}
      if (split <= first || split >= last) split = Math.floor((first + last) / 2);
      fit(first, split); fit(split, last);
    }
    for (let i = 1; i < cuts.length; i++) fit(cuts[i - 1], cuts[i]);
    const result = curves.map((curve, i) => {
      const point = {x: curve[0].x, y: curve[0].y, out: sub(curve[1], curve[0]), curve: 'bezier'};
      const previous = i ? curves[i - 1] : settings.closed ? curves[curves.length - 1] : null;
      if (previous) point.in = sub(previous[2], previous[3]);
      return point;
    });
    if (!settings.closed) {const last = curves[curves.length - 1]; result.push({x: last[3].x, y: last[3].y, in: sub(last[2], last[3]), curve: 'bezier'});}
    return normalize({...settings, points: result, smooth: 0});
  }
  function compile(raw) {
    const settings = normalize(raw);
    if (!settings) return null;
    if (hasBezier(settings)) return compileBezier(settings);
    let points = settings.points.filter((point, index, all) => index === 0 || Math.hypot(point.x - all[index - 1].x, point.y - all[index - 1].y) > EPS);
    if (settings.closed && points.length > 1 && Math.hypot(points[0].x - points[points.length - 1].x, points[0].y - points[points.length - 1].y) <= EPS) points = points.slice(0, -1);
    if (points.length < 2) throw new Error('路徑至少需要兩個不同位置的控制點。');
    for (let pass = 0; pass < settings.smooth; pass++) {
      const next = settings.closed ? [] : [{...points[0]}], count = settings.closed ? points.length : points.length - 1;
      for (let i = 0; i < count; i++) {
        const a = points[i], b = points[(i + 1) % points.length];
        next.push({x: a.x * 0.75 + b.x * 0.25, y: a.y * 0.75 + b.y * 0.25}, {x: a.x * 0.25 + b.x * 0.75, y: a.y * 0.25 + b.y * 0.75});
      }
      if (!settings.closed) next.push({...points[points.length - 1]});
      points = next;
    }
    if (settings.reverse) points = settings.closed ? [points[0], ...points.slice(1).reverse()] : points.slice().reverse();
    const count = settings.closed ? points.length : points.length - 1, cumulative = [0], segmentAngles = [];
    let totalLength = 0;
    const unwrap = (angle, previous) => previous + mod(angle - previous + 180, 360) - 180;
    for (let i = 0; i < count; i++) {
      const a = points[i], b = points[(i + 1) % points.length];
      totalLength += Math.hypot(b.x - a.x, b.y - a.y); cumulative.push(totalLength);
      const angle = Math.atan2(b.y - a.y, b.x - a.x) * DEG;
      segmentAngles.push(i ? unwrap(angle, segmentAngles[i - 1]) : angle);
    }
    if (totalLength < 1e-6) throw new Error('路徑長度過短，請拉開控制點。');
    const totalTurn = settings.closed ? Math.round((unwrap(segmentAngles[0], segmentAngles[count - 1]) - segmentAngles[0]) / 360) * 360 : 0;
    const nodeAngles = [];
    if (settings.smooth > 0) {
      for (let i = 0; i < points.length; i++) {
        const before = settings.closed ? points[(i + points.length - 1) % points.length] : points[Math.max(0, i - 1)];
        const after = settings.closed ? points[(i + 1) % points.length] : points[Math.min(points.length - 1, i + 1)];
        const angle = Math.atan2(after.y - before.y, after.x - before.x) * DEG;
        nodeAngles.push(i ? unwrap(angle, nodeAngles[i - 1]) : angle);
      }
      if (settings.closed) nodeAngles.push(nodeAngles[0] + totalTurn);
    }
    const sampleFractions = cumulative.map(value => value / totalLength);
    const corners = [];
    if (settings.smooth === 0) {
      for (let i = 1; i < count; i++) if (Math.abs(segmentAngles[i] - segmentAngles[i - 1]) > 1e-8) corners.push(sampleFractions[i]);
      if (settings.closed && Math.abs(segmentAngles[0] + totalTurn - segmentAngles[count - 1]) > 1e-8) corners.push(1);
    }
    function sample(progress) {
      if (typeof progress !== 'number' || !Number.isFinite(progress)) throw new Error('路徑進度必須是有限數值。');
      const cycle = settings.closed ? Math.floor(progress) : 0, u = settings.closed ? mod(progress, 1) : clamp(progress, 0, 1), distance = u * totalLength;
      let low = 0, high = count;
      while (low + 1 < high) { const middle = (low + high) >> 1; if (cumulative[middle] <= distance) low = middle; else high = middle; }
      const index = Math.min(count - 1, low), a = points[index], b = points[(index + 1) % points.length];
      const span = cumulative[index + 1] - cumulative[index], t = span > EPS ? clamp((distance - cumulative[index]) / span, 0, 1) : 0;
      const angle = settings.smooth > 0 ? nodeAngles[index] + (nodeAngles[index + 1] - nodeAngles[index]) * t : segmentAngles[index];
      return {x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, angle: angle + cycle * totalTurn};
    }
    return {points, closed: settings.closed, totalLength, totalTurn, corners, sampleFractions, sample};
  }
  return {defaults, normalize, preset, compile, splitSegment, convertToBezier, MAX_POINTS};
});
