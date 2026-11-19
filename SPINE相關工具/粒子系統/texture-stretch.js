(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleTextureStretch = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const SEGMENTS = 6, EPS = 1e-10;
  const builtin = {width: 64, height: 64};
  const meshes = new WeakMap();
  const clamp = (value, low, high) => Math.max(low, Math.min(value, high));

  function prepare(referenceImage, angle) {
    const image = referenceImage || builtin;
    let byAngle = meshes.get(image);
    if (!byAngle) { byAngle = new Map(); meshes.set(image, byAngle); }
    const degrees = ((angle % 360) + 360) % 360;
    if (byAngle.has(degrees)) return byAngle.get(degrees);

    // In world coordinates +Y points up. For a tall image the top of the
    // texture leads, so the local +X axis starts a quarter turn clockwise.
    const radians = (degrees - (image.height > image.width ? 90 : 0)) * Math.PI / 180;
    const cos = Math.abs(Math.cos(radians)) < EPS ? 0 : Math.cos(radians);
    const sin = Math.abs(Math.sin(radians)) < EPS ? 0 : Math.sin(radians);
    const extent = Math.abs(image.width * cos) + Math.abs(image.height * sin);
    const projected = (u, v) => .5 + ((u - .5) * image.width * cos + (v - .5) * image.height * sin) / extent;

    // Slice the original rectangle perpendicular to motion. All intersections
    // lie on its perimeter; keeping every corner also preserves diagonal tips.
    const corners = [[0, 0], [1, 0], [1, 1], [0, 1]];
    const uvs = [], positions = [], triangles = [];
    for (let edge = 0; edge < 4; edge++) {
      const [u, v] = corners[edge], [endU, endV] = corners[(edge + 1) % 4];
      const a = projected(u, v), b = projected(endU, endV);
      uvs.push(u, v); positions.push(a);
      if (Math.abs(a - b) <= EPS) continue;
      const cuts = [];
      for (let i = 1; i < SEGMENTS; i++) {
        const q = i / SEGMENTS, t = (q - a) / (b - a);
        if (t > EPS && t < 1 - EPS) cuts.push({q, t});
      }
      cuts.sort((first, second) => first.t - second.t);
      for (const {q, t} of cuts) {
        uvs.push(u + (endU - u) * t, v + (endV - v) * t);
        positions.push(q);
      }
    }
    for (let band = 0; band < SEGMENTS; band++) {
      const indices = [];
      for (let j = 0; j < positions.length; j++) {
        if (positions[j] >= band / SEGMENTS - EPS && positions[j] <= (band + 1) / SEGMENTS + EPS) indices.push(j);
      }
      for (let j = 1; j < indices.length - 1; j++) triangles.push(indices[0], indices[j], indices[j + 1]);
    }
    const mesh = {uvs, triangles, hull: positions.length};
    const result = {mesh, cos, sin};
    byAngle.set(degrees, result);
    return result;
  }

  function geometry(referenceImage, angle) { return prepare(referenceImage, angle).mesh; }

  function state(settings, referenceImage, age, life, current, atAge) {
    const {mesh, cos, sin} = prepare(referenceImage, settings.angle);
    const headAge = clamp(age, 0, life), span = Math.min(headAge, settings.duration);
    const points = [], tangents = [], widths = [], heights = [];
    const frame = current.image || referenceImage || builtin;
    for (let i = 0; i <= SEGMENTS; i++) {
      // Tail to head. Use the current frame for the entire surface even when
      // its history crosses a sequence key with different image dimensions.
      const p = i === SEGMENTS || span === 0 ? current : atAge(headAge - span * (1 - i / SEGMENTS));
      const historicalFrame = p.image || referenceImage || builtin;
      points.push(p);
      widths.push(p.width * (frame.width / historicalFrame.width));
      heights.push(p.height * (frame.height / historicalFrame.height));
    }

    let lastTangent = null;
    for (let i = 0; i <= SEGMENTS; i++) {
      const before = points[Math.max(0, i - 1)], after = points[Math.min(SEGMENTS, i + 1)];
      const dx = after.x - before.x, dy = after.y - before.y, distance = Math.hypot(dx, dy);
      if (distance > EPS) lastTangent = {x: dx / distance, y: dy / distance};
      tangents.push(lastTangent);
    }
    if (!tangents[0]) {
      // At birth there is no history yet. A small forward sample gives the
      // opening pose the same heading as the first moving frame.
      let heading = tangents.find(Boolean);
      if (!heading) {
        const probeAge = Math.min(life, headAge + .0001);
        const probe = probeAge === headAge ? current : atAge(probeAge);
        const dx = probe.x - current.x, dy = probe.y - current.y, distance = Math.hypot(dx, dy);
        const rotation = (current.rotation || 0) * Math.PI / 180;
        heading = distance > EPS ? {x: dx / distance, y: dy / distance} : {x: Math.cos(rotation), y: Math.sin(rotation)};
      }
      for (let i = 0; i <= SEGMENTS && !tangents[i]; i++) tangents[i] = heading;
    }

    // Retain a full-sized rectangle at rest. Motion adds the sampled path
    // displacement to each slice; its own width and length follow that age's
    // head scaling, including independent X/Y curves and inward shrinkage.
    let width = current.width, height = current.height;
    let extent = Math.abs(width * cos) + Math.abs(height * sin);
    if (extent <= EPS) {
      width = frame.width; height = frame.height;
      extent = Math.abs(width * cos) + Math.abs(height * sin);
    }
    const vertices = [];
    for (let j = 0; j < mesh.uvs.length; j += 2) {
      const u = mesh.uvs[j] - .5, v = .5 - mesh.uvs[j + 1];
      const section = clamp(.5 + (u * width * cos - v * height * sin) / extent, 0, 1) * SEGMENTS;
      const a = Math.min(Math.floor(section), SEGMENTS - 1), b = a + 1, t = section - a;
      const tx = tangents[a].x + (tangents[b].x - tangents[a].x) * t;
      const ty = tangents[a].y + (tangents[b].y - tangents[a].y) * t;
      const magnitude = Math.hypot(tx, ty);
      const dx = magnitude > EPS ? tx / magnitude : tangents[b].x;
      const dy = magnitude > EPS ? ty / magnitude : tangents[b].y;
      const localX = u * (widths[a] + (widths[b] - widths[a]) * t);
      const localY = v * (heights[a] + (heights[b] - heights[a]) * t);
      const along = localX * cos - localY * sin, across = localX * sin + localY * cos;
      vertices.push(points[a].x + (points[b].x - points[a].x) * t + along * dx - across * dy,
        points[a].y + (points[b].y - points[a].y) * t + along * dy + across * dx);
    }
    return {...current, type: 'mesh', vertices, ...mesh};
  }
  return {geometry, state};
});
