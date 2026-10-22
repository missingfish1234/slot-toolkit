(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ParticleEmissionGuides = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const DEG = Math.PI / 180, TAU = Math.PI * 2;
  const finite = (value, fallback) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  const spanFor = (value, fallback) => Math.max(0, Math.min(360, finite(value, fallback)));
  const polar = (angle, radius) => ({x: Math.cos(angle * DEG) * radius, y: Math.sin(angle * DEG) * radius});
  const text = value => String(Math.round(value * 10) / 10);
  function sector(angle, span, radius) {
    const start = angle - span / 2, steps = Math.max(1, Math.ceil(span / 3));
    const points = Array.from({length: steps + 1}, (_, i) => polar(start + span * i / steps, radius));
    return {angle, span, full: span === 360, points, start: points[0], end: points[points.length - 1], center: polar(angle, radius)};
  }
  function ellipseArc(e) {
    const rx = Math.abs(finite(e.width, 0)) / 2, ry = Math.abs(finite(e.height, 0)) / 2;
    const angle = finite(e.arcRotation, 90), span = spanFor(e.arcAngle, 360), full = span === 360;
    const parameter = degrees => {
      const world = degrees * DEG;
      if (rx === 0 || ry === 0 || rx === ry) return world;
      const value = Math.atan2(rx * Math.sin(world), ry * Math.cos(world));
      return value + TAU * Math.round((world - value) / TAU);
    };
    const start = full ? 0 : parameter(angle - span / 2), end = full ? TAU : parameter(angle + span / 2);
    const point = value => ({x: Math.cos(value) * rx, y: Math.sin(value) * ry});
    const steps = Math.max(16, Math.ceil(Math.abs(end - start) / DEG / 3));
    const points = Array.from({length: steps + 1}, (_, i) => point(start + (end - start) * i / steps));
    return {angle, span, full, points, start: points[0], end: points[points.length - 1], center: point(parameter(angle)), label: '圓弧 ' + text(span) + '°'};
  }
  function geometry(e, options = {}) {
    const path = e.path && e.path.enabled, strictPath = path && !e.path.offsets;
    const radius = Math.max(0, finite(options.radius, 72));
    let direction = null, arc = null;
    if (!path) {
      const mode = e.directionMode || 'fixed', angle = finite(e.angle, 90);
      if (mode === 'fixed') {
        const span = spanFor(e.spread, 360);
        direction = {...sector(angle, span, radius), mode, label: '發射 ' + text(span) + '°' + (span === 360 ? ' · 全方向' : ' · ' + text(angle) + '°')};
      } else {
        const spread = spanFor(e.directionSpread, 0), suffix = spread ? ' · 散射 ' + text(spread) + '°' : '';
        direction = {mode, angle, span: mode === 'random' ? 360 : spread, full: mode === 'random', points: [],
          center: polar(90, radius), label: mode === 'random' ? '隨機方向 · 360°' : mode === 'radial' ? '中心向外' + suffix : '輪廓法線向外' + suffix};
      }
    }
    if (!strictPath && e.shape === 'ring') arc = ellipseArc(e);
    return {direction, arc};
  }
  // ctx already contains the camera, parent bone and emitter origin. Keep that
  // single transform for positions, then draw annotations in CSS screen pixels.
  function project(point, matrix, pixelRatio = 1) {
    return {x: (matrix.a * point.x - matrix.c * point.y + matrix.e) / pixelRatio,
      y: (matrix.b * point.x - matrix.d * point.y + matrix.f) / pixelRatio};
  }
  function draw(ctx, e, options = {}) {
    const pixelRatio = Math.max(.01, finite(options.pixelRatio, 1)), matrix = ctx.getTransform();
    const scale = Math.max(Math.hypot(matrix.a, matrix.b), Math.hypot(matrix.c, matrix.d)) / pixelRatio;
    if (!Number.isFinite(scale) || scale < 1e-9) return;
    const guides = geometry(e, {radius: 76 / scale}), origin = project({x: 0, y: 0}, matrix, pixelRatio);
    const toScreen = point => project(point, matrix, pixelRatio);
    ctx.save(); ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = e.enabled === false ? .42 : 1;
    ctx.setLineDash([]); ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    const labelBoxes = [];
    function line(points, color, width, dashed) {
      if (!points.length) return;
      ctx.beginPath(); ctx.moveTo(points[0].x, points[0].y);
      for (const point of points.slice(1)) ctx.lineTo(point.x, point.y);
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dashed ? [4, 4] : []); ctx.stroke(); ctx.setLineDash([]);
    }
    function arrow(end, color) {
      const length = Math.hypot(end.x - origin.x, end.y - origin.y); if (length < 2) return;
      line([origin, end], color, 1.7);
      const a = Math.atan2(end.y - origin.y, end.x - origin.x), wing = Math.min(7, length / 3);
      line([{x: end.x - Math.cos(a - .48) * wing, y: end.y - Math.sin(a - .48) * wing}, end,
        {x: end.x - Math.cos(a + .48) * wing, y: end.y - Math.sin(a + .48) * wing}], color, 1.7);
    }
    function label(caption, point, color, offsetY) {
      ctx.font = '11px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const width = ctx.measureText(caption).width + 16, height = 23;
      const canvasWidth = ctx.canvas.width / pixelRatio, canvasHeight = ctx.canvas.height / pixelRatio;
      const x = Math.max(width / 2 + 6, Math.min(canvasWidth - width / 2 - 6, point.x));
      const clampY = value => Math.max(height / 2 + 6, Math.min(canvasHeight - height / 2 - 6, value));
      let y = clampY(point.y + offsetY);
      for (const box of labelBoxes) if (Math.abs(x - box.x) < (width + box.width) / 2 + 4 && Math.abs(y - box.y) < height + 4) {
        const above = box.y - height - 5;
        y = above >= height / 2 + 6 ? above : clampY(box.y + height + 5);
      }
      labelBoxes.push({x, y, width});
      ctx.fillStyle = '#101c28ed'; ctx.fillRect(x - width / 2, y - height / 2, width, height);
      ctx.strokeStyle = color + '88'; ctx.lineWidth = 1; ctx.strokeRect(x - width / 2, y - height / 2, width, height);
      ctx.fillStyle = color; ctx.fillText(caption, x, y);
    }
    function region(guide, color, arc) {
      const points = guide.points.map(toScreen), center = toScreen(guide.center);
      if (!guide.full && guide.span > 0) {
        ctx.beginPath(); ctx.moveTo(origin.x, origin.y);
        for (const point of points) ctx.lineTo(point.x, point.y);
        ctx.closePath(); ctx.fillStyle = color + (arc ? '0d' : '15'); ctx.fill();
      }
      line(points, color, arc ? 2 : 1.5);
      if (!guide.full) {
        line([origin, toScreen(guide.start)], color, 1.25, true);
        if (guide.span > 0) line([origin, toScreen(guide.end)], color, 1.25, true);
        arrow(center, color);
      }
      const anchor = guide.full ? points.reduce((top, point) => point.y < top.y ? point : top, origin) : center;
      label(guide.label, anchor, color, guide.full ? -24 : arc ? 18 : -20);
    }
    if (guides.arc) region(guides.arc, '#70ebcc', true);
    if (guides.direction) {
      const direction = guides.direction;
      if (direction.mode === 'fixed') region(direction, '#ffce83', false);
      else {
        if (direction.mode === 'random') line(sector(0, 360, 76 / scale).points.map(toScreen), '#ffce83', 1, true);
        label(direction.label, {x: origin.x, y: origin.y - 76}, '#ffce83', -20);
      }
    }
    ctx.restore();
  }
  return {geometry, ellipseArc, project, draw};
});
