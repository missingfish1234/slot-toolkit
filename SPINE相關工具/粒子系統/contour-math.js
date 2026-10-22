(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleContourMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const LIMIT = 2048, MAX_CONTOURS = 32, MAX_POINTS = 256;
  const fail = message => { throw new Error(message); };
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  function area(points) { return points.reduce((sum, p, i) => { const q = points[(i + 1) % points.length]; return sum + p.x * q.y - q.x * p.y; }, 0) / 2; }
  function normalize(raw) {
    if (raw == null) return null;
    const width = Number(raw.width), height = Number(raw.height);
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > LIMIT || height > LIMIT) fail('輪廓圖片尺寸需為 1–2048 像素。');
    if (!Array.isArray(raw.contours) || !raw.contours.length || raw.contours.length > MAX_CONTOURS) fail('輪廓需包含 1–32 個封閉區塊。');
    let count = 0;
    const contours = raw.contours.map(points => {
      if (!Array.isArray(points) || points.length < 3 || points.length > MAX_POINTS) fail('每個物件輪廓需有 3–256 個控制點。');
      count += points.length;
      return points.map(point => { const x = Number(point.x), y = Number(point.y); if (!Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > width / 2 + 1 || Math.abs(y) > height / 2 + 1) fail('輪廓控制點超出圖片範圍。'); return {x, y}; });
    });
    if (count > 2048) fail('輪廓過於複雜，總控制點不可超過 2048。');
    const threshold = raw.threshold === undefined ? 24 : Number(raw.threshold);
    if (!Number.isInteger(threshold) || threshold < 1 || threshold > 255) fail('透明度閾值需為 1–255。');
    const result = {width, height, contours, threshold, includeHoles: raw.includeHoles === true, showImage: raw.showImage !== false, sourceName: String(raw.sourceName || '透明 PNG').slice(0, 160)};
    if (raw.image) result.image = JSON.parse(JSON.stringify(raw.image));
    return result;
  }
  function distanceSquared(p, a, b) {
    const dx = b.x - a.x, dy = b.y - a.y, length = dx * dx + dy * dy;
    const u = length ? clamp(((p.x - a.x) * dx + (p.y - a.y) * dy) / length, 0, 1) : 0;
    return (p.x - a.x - u * dx) ** 2 + (p.y - a.y - u * dy) ** 2;
  }
  function simplifyOpen(points, tolerance) {
    const keep = new Uint8Array(points.length); keep[0] = keep[points.length - 1] = 1;
    const stack = [[0, points.length - 1]];
    while (stack.length) {
      const [first, last] = stack.pop(); let maximum = tolerance * tolerance, at = -1;
      for (let i = first + 1; i < last; i++) { const d = distanceSquared(points[i], points[first], points[last]); if (d > maximum) { maximum = d; at = i; } }
      if (at >= 0) { keep[at] = 1; stack.push([first, at], [at, last]); }
    }
    return points.filter((_, index) => keep[index]);
  }
  function simplifyClosed(points) {
    let far = 1, maximum = -1;
    points.forEach((p, i) => { const distance = (p.x - points[0].x) ** 2 + (p.y - points[0].y) ** 2; if (distance > maximum) { maximum = distance; far = i; } });
    let tolerance = .6, result;
    do {
      const a = simplifyOpen(points.slice(0, far + 1), tolerance), b = simplifyOpen(points.slice(far).concat([points[0]]), tolerance);
      result = a.slice(0, -1).concat(b.slice(0, -1)); tolerance *= 1.5;
    } while (result.length > MAX_POINTS);
    return result.length >= 3 ? result : [points[0], points[Math.floor(points.length / 3)], points[Math.floor(points.length * 2 / 3)]];
  }
  function scan(input) {
    const width = Number(input.width), height = Number(input.height), data = input.data;
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > LIMIT || height > LIMIT || !data || data.length !== width * height * 4) fail('請提供 2048 像素以內的 PNG 像素資料。');
    const threshold = Number(input.threshold === undefined ? 24 : input.threshold);
    if (!Number.isInteger(threshold) || threshold < 1 || threshold > 255) fail('透明度閾值需為 1–255。');
    const mask = new Uint8Array(width * height); let filled = 0;
    for (let i = 0; i < mask.length; i++) if (data[i * 4 + 3] >= threshold) { mask[i] = 1; filled++; }
    if (!filled) fail('此閾值下沒有可掃描的物件；請降低透明度閾值或更換圖片。');
    const stride = width + 1, edges = [], starts = new Map();
    function add(x1, y1, x2, y2, direction) {
      if (edges.length >= 100000) fail('圖片邊緣碎片過多，請提高閾值或先清理透明雜點。');
      const start = y1 * stride + x1, end = y2 * stride + x2, edge = {start, end, direction, used: false};
      edges.push(edge); const list = starts.get(start) || []; list.push(edge); starts.set(start, list);
    }
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      if (!mask[y * width + x]) continue;
      if (!y || !mask[(y - 1) * width + x]) add(x, y, x + 1, y, 0);
      if (x === width - 1 || !mask[y * width + x + 1]) add(x + 1, y, x + 1, y + 1, 1);
      if (y === height - 1 || !mask[(y + 1) * width + x]) add(x + 1, y + 1, x, y + 1, 2);
      if (!x || !mask[y * width + x - 1]) add(x, y + 1, x, y, 3);
    }
    const loops = [];
    for (const first of edges) {
      if (first.used) continue;
      const points = []; let current = first, closed = false;
      while (current && !current.used) {
        current.used = true; points.push({x: current.start % stride - width / 2, y: height / 2 - Math.floor(current.start / stride)});
        if (current.end === first.start) { closed = true; break; }
        const available = (starts.get(current.end) || []).filter(edge => !edge.used);
        // Keep diagonally touching islands separate by taking a right turn first.
        const rank = direction => ({1: 0, 0: 1, 3: 2, 2: 3})[(direction - current.direction + 4) % 4];
        available.sort((a, b) => rank(a.direction) - rank(b.direction)); current = available[0];
      }
      if (closed && points.length >= 4 && Math.abs(area(points)) >= 1) loops.push(simplifyClosed(points));
    }
    if (!loops.length) fail('未找到有效封閉輪廓，請檢查圖片透明度。');
    const result = normalize({width, height, contours: loops, threshold, includeHoles: input.includeHoles, sourceName: input.sourceName});
    result.opaque = filled === width * height; return result;
  }
  function compile(raw, targetWidth, targetHeight) {
    const outline = normalize(raw); if (!outline) fail('請先載入透明 PNG 並掃描物件輪廓。');
    const sx = targetWidth === undefined ? 1 : targetWidth / outline.width, sy = targetHeight === undefined ? 1 : targetHeight / outline.height;
    if (!Number.isFinite(sx) || !Number.isFinite(sy) || sx < 0 || sy < 0) fail('輪廓顯示尺寸不正確。');
    const contours = outline.contours.filter(points => outline.includeHoles || area(points) < 0).map(points => points.map(p => ({x: p.x * sx, y: p.y * sy})));
    const segments = []; let totalLength = 0;
    contours.forEach(points => points.forEach((a, i) => {
      const b = points[(i + 1) % points.length], dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy);
      // Scan orients solid pixels to the right of every segment. Its left
      // normal points into transparent space, including the inside of holes.
      // Compute after resizing so anisotropic scaling keeps true normals.
      if (length > 1e-9) { segments.push({a, b, length, start: totalLength, nx: -dy / length, ny: dx / length}); totalLength += length; }
    }));
    function sample(ratio, withNormal) {
      if (!segments.length) {
        const first = contours[0] && contours[0][0] || {x: 0, y: 0};
        return withNormal ? {x: first.x, y: first.y, nx: 0, ny: 0} : first;
      }
      const distance = clamp(Number(ratio) || 0, 0, 1) * totalLength;
      let low = 0, high = segments.length - 1;
      while (low < high) { const middle = Math.floor((low + high) / 2); if (segments[middle].start + segments[middle].length < distance) low = middle + 1; else high = middle; }
      const edge = segments[low], u = clamp((distance - edge.start) / edge.length, 0, 1);
      const point = {x: edge.a.x + (edge.b.x - edge.a.x) * u, y: edge.a.y + (edge.b.y - edge.a.y) * u};
      return withNormal ? {...point, nx: edge.nx, ny: edge.ny} : point;
    }
    return {contours, totalLength, sample: ratio => sample(ratio), sampleNormal: ratio => sample(ratio, true)};
  }
  const PATH_POINTS = 48, PATH_EPS = 1e-9;
  function distinctPoints(points) {
    const result = points.filter((point, index) => !index || Math.hypot(point.x - points[index - 1].x, point.y - points[index - 1].y) > PATH_EPS);
    if (result.length > 1 && Math.hypot(result[0].x - result[result.length - 1].x, result[0].y - result[result.length - 1].y) <= PATH_EPS) result.pop();
    return result;
  }
  function pathOutline(raw) {
    const outline = normalize(raw);
    if (!outline) fail('請先載入透明 PNG 並掃描物件輪廓。');
    return outline;
  }
  function pathContourInfo(outline) {
    return outline.contours.map((points, index) => {
      const clean = distinctPoints(points), signedArea = area(clean);
      return {index, hole: signedArea > 0, area: signedArea, pointCount: clean.length};
    }).filter(info => info.pointCount >= 3 && Math.abs(info.area) > PATH_EPS)
      .sort((a, b) => Number(a.hole) - Number(b.hole) || Math.abs(b.area) - Math.abs(a.area) || a.index - b.index);
  }
  function pathContours(raw) {
    const result = pathContourInfo(pathOutline(raw));
    if (!result.length) fail('物件輪廓沒有有效的封閉路徑。');
    return result;
  }
  function crossing(a, b, c, d) {
    const cross = (p, q, r) => (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
    const side = value => value > PATH_EPS ? 1 : value < -PATH_EPS ? -1 : 0;
    const abC = side(cross(a, b, c)), abD = side(cross(a, b, d)), cdA = side(cross(c, d, a)), cdB = side(cross(c, d, b));
    if (abC * abD < 0 && cdA * cdB < 0) return true;
    const on = (p, q, r) => r.x >= Math.min(p.x, q.x) - PATH_EPS && r.x <= Math.max(p.x, q.x) + PATH_EPS && r.y >= Math.min(p.y, q.y) - PATH_EPS && r.y <= Math.max(p.y, q.y) + PATH_EPS;
    return !abC && on(a, b, c) || !abD && on(a, b, d) || !cdA && on(c, d, a) || !cdB && on(c, d, b);
  }
  function simplifyPath(points) {
    if (points.length <= PATH_POINTS) return points;
    const kept = points.map((point, index) => index), winding = Math.sign(area(points));
    while (kept.length > PATH_POINTS) {
      const candidates = [];
      // Cost includes every original vertex already removed from this arc.
      // Keeping existing vertices preserves corners instead of cutting them by
      // uniformly resampling the perimeter. The image's first vertex stays put.
      for (let i = 1; i < kept.length; i++) {
        const before = kept[(i + kept.length - 1) % kept.length], after = kept[(i + 1) % kept.length];
        let error = 0;
        for (let j = (before + 1) % points.length; j !== after; j = (j + 1) % points.length) error = Math.max(error, distanceSquared(points[j], points[before], points[after]));
        candidates.push({i, before, after, error});
      }
      candidates.sort((a, b) => a.error - b.error || kept[a.i] - kept[b.i]);
      let removed = false;
      for (const candidate of candidates) {
        const a = points[candidate.before], b = points[candidate.after];
        const intersects = kept.some((index, i) => {
          const next = kept[(i + 1) % kept.length];
          if (index === candidate.before || next === candidate.before || index === candidate.after || next === candidate.after) return false;
          return crossing(a, b, points[index], points[next]);
        });
        if (intersects) continue;
        const old = points[kept[candidate.i]], signedArea = area(kept.map(index => points[index])) - (a.x * old.y - old.x * a.y + old.x * b.y - b.x * old.y - a.x * b.y + b.x * a.y) / 2;
        if (Math.sign(signedArea) !== winding || Math.abs(signedArea) <= PATH_EPS) continue;
        kept.splice(candidate.i, 1); removed = true; break;
      }
      if (!removed) fail('物件輪廓過於複雜，無法轉成 48 點以內的有效路徑。');
    }
    return kept.map(index => points[index]);
  }
  function toPath(raw, targetWidth, targetHeight, index) {
    const outline = pathOutline(raw), info = pathContourInfo(outline);
    if (index === undefined) {
      const exterior = info.find(contour => !contour.hole);
      if (!exterior) fail('未找到有效的物件外側輪廓。');
      index = exterior.index;
    }
    if (!Number.isInteger(index) || index < 0 || index >= outline.contours.length) fail('請選擇有效的物件輪廓。');
    if (!info.some(contour => contour.index === index)) fail('選取的物件輪廓沒有有效的封閉路徑。');
    const width = targetWidth === undefined ? outline.width : targetWidth, height = targetHeight === undefined ? outline.height : targetHeight;
    if (typeof width !== 'number' || typeof height !== 'number' || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) fail('物件路徑寬高需為大於 0 的有限數值。');
    const points = distinctPoints(outline.contours[index].map(point => ({x: point.x * width / outline.width, y: point.y * height / outline.height})));
    if (points.some(point => !Number.isFinite(point.x) || !Number.isFinite(point.y) || Math.abs(point.x) > 4000 || Math.abs(point.y) > 4000)) fail('物件路徑座標需在 −4000 到 4000 之內，請縮小物件寬高。');
    const length = points.reduce((sum, point, i) => sum + Math.hypot(point.x - points[(i + 1) % points.length].x, point.y - points[(i + 1) % points.length].y), 0);
    if (points.length < 3 || Math.abs(area(points)) <= PATH_EPS || length < 1e-6) fail('物件路徑長度過短，請放大物件寬高。');
    return {points: simplifyPath(points), closed: true, smooth: 0};
  }
  return {normalize, scan, compile, area, pathContours, toPath};
});
