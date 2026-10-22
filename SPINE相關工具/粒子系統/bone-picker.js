(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleBonePicker = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function screen(point, view) {
    return {x: view.width / 2 + view.panX + point.x * view.zoom,
      y: view.height / 2 + view.panY - point.y * view.zoom};
  }
  function nearest(bones, point, view, radius = 11) {
    let best = null, distance = radius;
    for (const bone of bones) {
      if (bone.active === false || ![bone.x, bone.y, bone.endX, bone.endY].every(Number.isFinite)) continue;
      const a = screen(bone, view), b = screen({x: bone.endX, y: bone.endY}, view);
      const dx = b.x - a.x, dy = b.y - a.y, square = dx * dx + dy * dy;
      const u = square ? Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / square)) : 0;
      const d = Math.hypot(point.x - a.x - u * dx, point.y - a.y - u * dy);
      if (d <= distance) { best = bone; distance = d; }
    }
    return best;
  }
  function reparentPoint(value, oldMatrix, nextMatrix) {
    const finite = matrix => matrix && ['a', 'b', 'c', 'd', 'x', 'y'].every(key => Number.isFinite(matrix[key]));
    if (!finite(oldMatrix) || !finite(nextMatrix)) throw new Error('無法取得掛接骨骼的位置，請換一個動畫時間後再試。');
    const determinant = nextMatrix.a * nextMatrix.d - nextMatrix.b * nextMatrix.c;
    if (Math.abs(determinant) < 1e-10) throw new Error('這個骨骼目前縮放為零，無法保持紅點位置；請改選其他骨骼。');
    const x = oldMatrix.x + oldMatrix.a * value.x + oldMatrix.b * value.y - nextMatrix.x;
    const y = oldMatrix.y + oldMatrix.c * value.x + oldMatrix.d * value.y - nextMatrix.y;
    return {x: (nextMatrix.d * x - nextMatrix.b * y) / determinant,
      y: (-nextMatrix.c * x + nextMatrix.a * y) / determinant};
  }
  function mount({canvas, button, hint, keepWorld, getScene, getView, onPick, onState, notify, document: doc = globalThis.document}) {
    let scene = null, hover = null;
    const stage = canvas.parentElement, listeners = [];
    const listen = (target, type, callback, options) => { target.addEventListener(type, callback, options); listeners.push([target, type, callback, options]); };
    function updateHint() {
      hint.hidden = !scene;
      if (scene) hint.textContent = '選擇「' + scene.emitterName + '」的掛接骨骼 · ' + (hover ? hover.name + ' · 點一下套用' : '滑過骨骼後點選') + ' · Esc 取消';
      button.classList.toggle('active', !!scene); button.setAttribute('aria-pressed', String(!!scene));
      stage.classList.toggle('bone-picking', !!scene);
    }
    function cancel() {
      if (!scene) return;
      const previous = scene; scene = null; hover = null; updateHint();
      if (typeof onState === 'function') onState(false, previous);
    }
    function start() {
      if (scene) { cancel(); return false; }
      try {
        const next = getScene();
        if (!next || !Array.isArray(next.bones) || !next.bones.some(b => b.active !== false)) throw new Error('目前沒有可選擇的骨骼，請先載入並啟用掛接預覽。');
        scene = next; hover = null;
        if (typeof onState === 'function') onState(true, scene);
        updateHint(); canvas.focus(); return true;
      } catch (error) { cancel(); if (notify) notify(error.message, true); return false; }
    }
    function location(event) { const rect = canvas.getBoundingClientRect(); return {x: event.clientX - rect.left, y: event.clientY - rect.top}; }
    listen(button, 'click', start);
    listen(doc, 'pointerdown', event => {
      if (!scene) return;
      const keepLabel = keepWorld && keepWorld.closest('label');
      if (canvas.contains(event.target) || button.contains(event.target) || keepLabel && keepLabel.contains(event.target)) return;
      cancel();
    }, true);
    listen(canvas, 'pointermove', event => { if (scene) { hover = nearest(scene.bones, location(event), getView()); updateHint(); } });
    listen(canvas, 'pointerleave', () => { if (scene) { hover = null; updateHint(); } });
    listen(canvas, 'pointerdown', event => {
      if (!scene || event.button !== 0) return;
      event.preventDefault(); event.stopImmediatePropagation(); canvas.focus();
      hover = nearest(scene.bones, location(event), getView()); updateHint();
      if (!hover) return;
      try { if (onPick(hover, scene) !== false) cancel(); }
      catch (error) { if (notify) notify(error.message, true); }
    }, true);
    listen(doc, 'keydown', event => {
      if (!scene || event.key !== 'Escape') return;
      event.preventDefault(); event.stopImmediatePropagation(); cancel();
    }, true);
    function draw(context) {
      if (!scene) return;
      const view = getView(), zoom = Math.max(.001, view.zoom);
      context.save(); context.globalCompositeOperation = 'source-over'; context.setLineDash([]);
      for (const bone of scene.bones) {
        if (bone.active === false) continue;
        const chosen = hover && bone.name === hover.name;
        context.globalAlpha = chosen ? 1 : .65; context.strokeStyle = chosen ? '#ffe0a2' : '#90c3c3';
        context.fillStyle = context.strokeStyle; context.lineWidth = (chosen ? 3 : 1.5) / zoom;
        context.beginPath(); context.moveTo(bone.x, -bone.y); context.lineTo(bone.endX, -bone.endY); context.stroke();
        context.beginPath(); context.arc(bone.x, -bone.y, (chosen ? 5 : 3) / zoom, 0, Math.PI * 2); context.fill();
        if (chosen) { context.font = '600 ' + 12 / zoom + 'px sans-serif'; context.textAlign = 'left'; context.fillText(bone.name, bone.x + 9 / zoom, -bone.y - 9 / zoom); }
      }
      context.restore();
    }
    return {start, cancel, draw, get active() { return !!scene; }, destroy() { cancel(); listeners.forEach(args => args[0].removeEventListener(args[1], args[2], args[3])); }};
  }
  return {screen, nearest, reparentPoint, mount};
});
