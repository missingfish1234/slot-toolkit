(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleSpineCanvasRenderer = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const geometry = value => value && typeof value.length === 'number' && value.length >= 6 && value.length % 2 === 0 && Array.from(value).every(finite);
  // Canvas transform(a,b,c,d,e,f) maps source texture pixels to Spine world XY.
  // The caller's camera transform (including Y-up to screen Y-down) stays intact.
  function affine(source, target) {
    if (!geometry(source) || !geometry(target) || source.length !== 6 || target.length !== 6) return null;
    const ux = source[2] - source[0], uy = source[3] - source[1], vx = source[4] - source[0], vy = source[5] - source[1];
    const determinant = ux * vy - vx * uy;
    if (Math.abs(determinant) < 1e-12) return null;
    const xx = target[2] - target[0], xy = target[3] - target[1], yx = target[4] - target[0], yy = target[5] - target[1];
    if (Math.abs(xx * yy - yx * xy) < 1e-12) return null;
    const a = (xx * vy - yx * uy) / determinant, c = (ux * yx - vx * xx) / determinant;
    const b = (xy * vy - yy * uy) / determinant, d = (ux * yy - vx * xy) / determinant;
    return {a, b, c, d, x: target[0] - a * source[0] - c * source[1], y: target[1] - b * source[0] - d * source[1]};
  }
  function polygon(ctx, points) {
    ctx.beginPath(); ctx.moveTo(points[0], points[1]);
    for (let i = 2; i < points.length; i += 2) ctx.lineTo(points[i], points[i + 1]);
    ctx.closePath();
  }
  function mappedTriangle(vertices, uvs, indices, width, height) {
    const source = [], target = [];
    for (const index of indices) {
      if (!Number.isInteger(index) || index < 0 || index * 2 + 1 >= vertices.length || index * 2 + 1 >= uvs.length) return null;
      source.push(uvs[index * 2] * width, uvs[index * 2 + 1] * height);
      target.push(vertices[index * 2], vertices[index * 2 + 1]);
    }
    const transform = affine(source, target); return transform ? {transform, source, target} : null;
  }
  function draw(ctx, state, texture) {
    if (!ctx || !state || !texture || !geometry(state.vertices) || !geometry(state.uvs) || state.vertices.length !== state.uvs.length) return false;
    const width = texture.naturalWidth || texture.width, height = texture.naturalHeight || texture.height;
    if (!finite(width) || !finite(height) || width <= 0 || height <= 0 || !finite(state.alpha) || state.alpha <= 0) return false;
    const triangles = state.triangles || (state.vertices.length === 8 ? [0, 1, 2, 2, 3, 0] : []);
    if (!triangles.length || triangles.length % 3) return false;
    const modes = {normal: 'source-over', additive: 'lighter', multiply: 'multiply', screen: 'screen'};
    let drawn = false;
    ctx.save();
    try {
      ctx.globalAlpha = (finite(ctx.globalAlpha) ? ctx.globalAlpha : 1) * Math.min(1, state.alpha);
      ctx.globalCompositeOperation = Object.prototype.hasOwnProperty.call(modes, state.blend) ? modes[state.blend] : 'source-over';
      for (const clip of state.clipPolygons || []) {
        const vertices = clip && clip.vertices || clip;
        if (!geometry(vertices)) return false;
        polygon(ctx, vertices); ctx.clip();
      }
      const quad = state.type !== 'mesh' && state.vertices.length === 8 ? mappedTriangle(state.vertices, state.uvs, [0, 1, 2], width, height) : null;
      if (quad) {
        // A region is one affine quad even for shear, reflection, and rotated
        // atlas packing. Draw it once to avoid a translucent diagonal seam.
        const u = state.uvs[6] * width, v = state.uvs[7] * height, m = quad.transform;
        const predictedX = m.a * u + m.c * v + m.x, predictedY = m.b * u + m.d * v + m.y;
        if (Math.hypot(predictedX - state.vertices[6], predictedY - state.vertices[7]) < 0.00001) {
          polygon(ctx, state.vertices); ctx.clip(); ctx.transform(m.a, m.b, m.c, m.d, m.x, m.y);
          ctx.drawImage(texture, 0, 0); drawn = true; return drawn;
        }
      }
      for (let i = 0; i < triangles.length; i += 3) {
        const mapped = mappedTriangle(state.vertices, state.uvs, [triangles[i], triangles[i + 1], triangles[i + 2]], width, height);
        if (!mapped) continue;
        ctx.save();
        try {
          polygon(ctx, mapped.target); ctx.clip(); const m = mapped.transform;
          ctx.transform(m.a, m.b, m.c, m.d, m.x, m.y); ctx.drawImage(texture, 0, 0); drawn = true;
        } finally { ctx.restore(); }
      }
    } finally { ctx.restore(); }
    return drawn;
  }
  return {draw, affine};
});
