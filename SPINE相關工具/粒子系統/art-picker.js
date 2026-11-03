(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleArtPicker = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  // "Click the character": find the topmost visible original attachment under
  // the pointer (region or mesh, honouring transparent pixels when the texture
  // is loaded) so one click can choose the bone, the position and the layer.
  const ALPHA_THRESHOLD = 24;
  function barycentric(px, py, ax, ay, bx, by, cx, cy) {
    const v0x = bx - ax, v0y = by - ay, v1x = cx - ax, v1y = cy - ay, v2x = px - ax, v2y = py - ay;
    const den = v0x * v1y - v1x * v0y;
    if (Math.abs(den) < 1e-12) return null;
    const v = (v2x * v1y - v1x * v2y) / den, w = (v0x * v2y - v2x * v0y) / den, u = 1 - v - w;
    const eps = -1e-6;
    return u >= eps && v >= eps && w >= eps ? [u, v, w] : null;
  }
  // Returns {u, v} texture coordinates of point inside the item, or null.
  function locate(item, point) {
    const vertices = item && item.vertices, uvs = item && item.uvs;
    if (!vertices || vertices.length < 6) return null;
    const triangles = item.triangles && item.triangles.length ? item.triangles : vertices.length === 8 ? [0, 1, 2, 2, 3, 0] : [];
    for (let i = 0; i + 2 < triangles.length; i += 3) {
      const a = triangles[i], b = triangles[i + 1], c = triangles[i + 2];
      const weights = barycentric(point.x, point.y, vertices[a * 2], vertices[a * 2 + 1], vertices[b * 2], vertices[b * 2 + 1], vertices[c * 2], vertices[c * 2 + 1]);
      if (!weights) continue;
      if (!uvs || uvs.length < vertices.length) return {u: 0.5, v: 0.5};
      return {u: weights[0] * uvs[a * 2] + weights[1] * uvs[b * 2] + weights[2] * uvs[c * 2],
        v: weights[0] * uvs[a * 2 + 1] + weights[1] * uvs[b * 2 + 1] + weights[2] * uvs[c * 2 + 1]};
    }
    return null;
  }
  // items are in draw order (back to front). alphaAt(item, u, v) returns 0–255,
  // or null when the texture is not available (then the triangle area counts).
  function hitTest(items, point, alphaAt) {
    let fallback = null;
    for (let index = items.length - 1; index >= 0; index--) {
      const item = items[index];
      if (!item || item.isParticle || !(item.alpha > 0.02)) continue;
      const uv = locate(item, point);
      if (!uv) continue;
      const alpha = typeof alphaAt === 'function' ? alphaAt(item, uv.u, uv.v) : null;
      if (alpha === null || alpha === undefined) { if (!fallback) fallback = {item, uv, exact: false}; continue; }
      if (alpha >= ALPHA_THRESHOLD) return {item, uv, exact: true};
    }
    return fallback;
  }
  // Outline edges of a triangle list (edges used by exactly one triangle).
  function outline(item) {
    const vertices = item.vertices, triangles = item.triangles && item.triangles.length ? item.triangles : [0, 1, 2, 2, 3, 0];
    const counts = new Map();
    for (let i = 0; i + 2 < triangles.length; i += 3) {
      [[triangles[i], triangles[i + 1]], [triangles[i + 1], triangles[i + 2]], [triangles[i + 2], triangles[i]]].forEach(([a, b]) => {
        const key = a < b ? a + ':' + b : b + ':' + a; counts.set(key, (counts.get(key) || 0) + 1);
      });
    }
    const edges = [];
    counts.forEach((count, key) => {
      if (count !== 1) return;
      const [a, b] = key.split(':').map(Number);
      edges.push([vertices[a * 2], vertices[a * 2 + 1], vertices[b * 2], vertices[b * 2 + 1]]);
    });
    return edges;
  }
  // Browser pixel reader with a per-image cache.
  function createAlphaSampler(imageFor, doc = globalThis.document) {
    const cache = new WeakMap();
    return function alphaAt(item, u, v) {
      if (!item.image || !item.image.dataUrl || typeof imageFor !== 'function' || !doc) return null;
      const element = imageFor(item.image);
      if (!element || !element.complete || !element.naturalWidth) return null;
      let pixels = cache.get(element);
      if (!pixels) {
        const canvas = doc.createElement('canvas'); canvas.width = element.naturalWidth; canvas.height = element.naturalHeight;
        const context = canvas.getContext('2d', {willReadFrequently: true}); context.drawImage(element, 0, 0);
        try { pixels = {width: canvas.width, height: canvas.height, data: context.getImageData(0, 0, canvas.width, canvas.height).data}; }
        catch (_) { return null; }
        cache.set(element, pixels);
      }
      const x = Math.min(pixels.width - 1, Math.max(0, Math.floor(u * pixels.width)));
      const y = Math.min(pixels.height - 1, Math.max(0, Math.floor(v * pixels.height)));
      return pixels.data[(y * pixels.width + x) * 4 + 3];
    };
  }
  function toWorld(point, view) { return {x: (point.x - view.width / 2 - view.panX) / view.zoom, y: -(point.y - view.height / 2 - view.panY) / view.zoom}; }

  function mount({canvas, button, hint, getItems, getView, alphaAt, onPick, onState, canStart, notify, document: doc = globalThis.document}) {
    let active = false, hover = null, selected = null;
    const stage = canvas.parentElement, listeners = [];
    const listen = (target, type, callback, options) => { target.addEventListener(type, callback, options); listeners.push([target, type, callback, options]); };
    function label(hit) { return hit.item.attachmentName + ' · 插槽 ' + hit.item.slotName + ' · 骨骼 ' + hit.item.boneName; }
    function updateHint() {
      hint.hidden = !active;
      if (active) hint.textContent = (hover ? label(hover) + ' · 點一下選擇' : '在角色圖片上點一下，選擇粒子要出現的位置') + ' · Esc 結束';
      button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
      stage.classList.toggle('art-picking', active);
    }
    function stop() {
      if (!active) return;
      active = false; hover = null; updateHint();
      if (typeof onState === 'function') onState(false);
    }
    function start() {
      if (active) { stop(); return false; }
      const reason = typeof canStart === 'function' ? canStart() : '';
      if (reason) { if (notify) notify(reason, true); return false; }
      active = true; hover = null; selected = null;
      if (typeof onState === 'function') onState(true);
      updateHint(); canvas.focus(); return true;
    }
    function find(event) {
      const rect = canvas.getBoundingClientRect(), screen = {x: event.clientX - rect.left, y: event.clientY - rect.top};
      const world = toWorld(screen, getView());
      const hit = hitTest(getItems() || [], world, alphaAt);
      return hit ? {...hit, world, screen: {x: event.clientX, y: event.clientY}} : null;
    }
    listen(button, 'click', start);
    listen(canvas, 'pointermove', event => {
      if (!active) return;
      const next = find(event);
      if ((next && next.item.slotName) !== (hover && hover.item.slotName)) { hover = next; updateHint(); }
      else hover = next;
    });
    listen(canvas, 'pointerleave', () => { if (active) { hover = null; updateHint(); } });
    listen(canvas, 'pointerdown', event => {
      if (!active || event.button !== 0) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const hit = find(event);
      if (!hit) { if (notify) notify('這裡沒有角色圖片；請點在角色身上，或按 Esc 結束。', true); return; }
      selected = hit; hover = null; active = false; updateHint();
      if (typeof onState === 'function') onState(false);
      try { onPick(hit, event); } catch (error) { selected = null; if (notify) notify(error.message, true); }
    }, true);
    listen(doc, 'keydown', event => {
      if (event.key !== 'Escape' || !active) return;
      event.preventDefault(); event.stopImmediatePropagation(); stop();
    }, true);
    function drawItem(context, item, zoom, color, width) {
      context.strokeStyle = color; context.lineWidth = width / zoom; context.beginPath();
      outline(item).forEach(([ax, ay, bx, by]) => { context.moveTo(ax, -ay); context.lineTo(bx, -by); });
      context.stroke();
    }
    function draw(context, zoom) {
      const shown = active ? hover : selected;
      if (!shown) return;
      context.save(); context.globalCompositeOperation = 'source-over'; context.globalAlpha = 1; context.setLineDash([]);
      drawItem(context, shown.item, zoom, '#1b1206', 4);
      drawItem(context, shown.item, zoom, '#ffd27a', 2);
      if (!active && selected) {
        context.fillStyle = '#ffd27a'; context.strokeStyle = '#1b1206'; context.lineWidth = 2 / zoom;
        context.beginPath(); context.arc(selected.world.x, -selected.world.y, 6 / zoom, 0, Math.PI * 2); context.fill(); context.stroke();
      }
      context.restore();
    }
    return {start, stop, draw, clearSelection() { selected = null; }, get active() { return active; }, get selected() { return selected; },
      destroy() { stop(); listeners.forEach(args => args[0].removeEventListener(args[1], args[2], args[3])); }};
  }
  return {hitTest, locate, outline, createAlphaSampler, toWorld, mount, ALPHA_THRESHOLD};
});
