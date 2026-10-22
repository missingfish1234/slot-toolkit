(function (root, factory) {
  'use strict';
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticlePathEditor = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const round = value => Math.round(value * 1000) / 1000;
  const MAX_POINTS = 48;
  const IDS = ['pathDialog', 'pathCanvas', 'pathPreset', 'pathWidth', 'pathHeight', 'pathApplyPreset',
    'pathClosed', 'pathReverse', 'pathSmooth', 'pathReset', 'pathCancel', 'pathApply', 'pathPointX',
    'pathPointY', 'pathDeletePoint', 'pathAddPoint', 'pathEditorInfo', 'pathDialogClose'];

  function mount({getEmitter, onApply, getScene, loadOutline, contourMath = root.ParticleContourMath,
    math = root.ParticlePathMath, document: doc = root.document}) {
    if (!math || !['defaults', 'normalize', 'preset', 'compile'].every(key => typeof math[key] === 'function')) {
      throw new Error('路徑編輯器需要 ParticlePathMath。');
    }
    const nodes = Object.fromEntries(IDS.map(id => [id, doc.getElementById(id)]));
    for (const id of ['pathShowReference', 'pathFitView', 'pathOutlineControls', 'pathOutlineContour',
      'pathLoadOutline', 'pathOutlineFile', 'pathOutlineInfo', 'pathPointCurve', 'pathHandleHint', 'pathSimplify', 'pathSmoothField', 'pathPointSelect']) nodes[id] = doc.getElementById(id);
    const $ = id => nodes[id];
    for (const id of IDS) if (!$(id)) throw new Error('路徑編輯器缺少 #' + id + '。');
    const dialog = $('pathDialog'), canvas = $('pathCanvas'), listeners = [];
    const dimensions = {width: 320, height: 180};
    let draft = null, openingDraft = null, openingDimensions = null, openingEmitter = null, selected = 0, view = null, drag = null, opened = false;
    let notice = '', observer = null;
    let scene = null, sceneNotice = '', matrix = null, editable = true;
    let reference = null, referenceLinked = false, referenceImported = false, contours = [], contourIndex = null;
    let loading = false, loadToken = 0;
    let openingPreset = 'custom';
    let mixedCurveOption = null;
    let pointSelectCount = -1;
    canvas.tabIndex = 0;
    if (canvas.style) canvas.style.touchAction = 'none';
    function listen(target, type, handler, options) {
      target.addEventListener(type, handler, options);
      listeners.push([target, type, handler, options]);
    }
    function geometry() {
      const rect = canvas.getBoundingClientRect();
      return {width: rect.width || 640, height: rect.height || 360, left: rect.left || 0, top: rect.top || 0};
    }
    function worldPoint(point) {
      if (!matrix) return point;
      return {x: matrix.x + matrix.a * point.x + matrix.b * point.y,
        y: matrix.y + matrix.c * point.x + matrix.d * point.y};
    }
    function localPoint(point) {
      if (!matrix) return point;
      if (!editable) return null;
      const determinant = matrix.a * matrix.d - matrix.b * matrix.c;
      const x = point.x - matrix.x, y = point.y - matrix.y;
      return {x: (matrix.d * x - matrix.b * y) / determinant,
        y: (-matrix.c * x + matrix.a * y) / determinant};
    }
    function fit() {
      if (!draft) return;
      const g = geometry(), points = draft.points.map(worldPoint);
      try { points.push(...math.compile(draft).points.map(worldPoint)); } catch (_) {}
      handlesFor(selected).forEach(handle => points.push(worldPoint(handle.point)));
      if (scene && Array.isArray(scene.bounds)) points.push(...scene.bounds.filter(p => p && Number.isFinite(p.x) && Number.isFinite(p.y)));
      const xs = points.map(p => p.x), ys = points.map(p => p.y);
      const left = Math.min(...xs), right = Math.max(...xs), bottom = Math.min(...ys), top = Math.max(...ys);
      view = {x: (left + right) / 2, y: (bottom + top) / 2,
        scale: clamp(Math.min(Math.max(1, g.width - 80) / Math.max(scene ? 1 : 320, right - left),
          Math.max(1, g.height - 72) / Math.max(scene ? 1 : 180, top - bottom)), .001, 1000)};
    }
    function worldScreen(point, g = geometry()) {
      return {x: g.width / 2 + (point.x - view.x) * view.scale,
        y: g.height / 2 - (point.y - view.y) * view.scale};
    }
    function screen(point, g = geometry()) { return worldScreen(worldPoint(point), g); }
    function eventPoint(event) {
      const g = geometry();
      // All transforms use CSS pixels. A high-DPI backing store does not change hit tests.
      const x = event.clientX - g.left, y = event.clientY - g.top;
      const world = {x: view.x + (x - g.width / 2) / view.scale, y: view.y - (y - g.height / 2) / view.scale};
      const local = localPoint(world);
      return {screen: {x, y}, world, local: local && {x: round(clamp(local.x, -4000, 4000)), y: round(clamp(local.y, -4000, 4000))}};
    }
    function hit(point) {
      let nearest = -1, distance = 11;
      draft.points.forEach((p, index) => {
        const q = screen(p), d = Math.hypot(q.x - point.x, q.y - point.y);
        if (d > 11) return;
        if (nearest >= 0) {
          const previous = draft.points[nearest], previousScreen = screen(previous);
          const overlapping = Math.hypot(p.x - previous.x, p.y - previous.y) <= 1e-5 &&
            Math.hypot(q.x - previousScreen.x, q.y - previousScreen.y) <= .5 && Math.abs(d - distance) <= 1;
          if (overlapping && (nearest === selected || index === selected)) {
            if (index === selected) { nearest = index; distance = d; }
            return;
          }
        }
        if (d <= distance) { nearest = index; distance = d; }
      });
      return nearest;
    }
    function selectedPoint() {
      selected = clamp(selected, 0, draft.points.length - 1);
      return draft.points[selected];
    }
    function boundedAnchor(point, axis, value) {
      const offsets = [0, ...['in', 'out'].filter(side => point[side]).map(side => point[side][axis])];
      return clamp(round(value), -4000 - Math.min(...offsets), 4000 - Math.max(...offsets));
    }
    function hasBezier() {
      return draft.points.some((point, index) => segmentBezier(index));
    }
    function neighbor(index, offset) {
      const next = index + offset;
      return draft.closed ? (next + draft.points.length) % draft.points.length : next >= 0 && next < draft.points.length ? next : -1;
    }
    function segmentBezier(index) {
      const end = neighbor(index, 1); if (end < 0) return false;
      const point = draft.points[index];
      return point.curve !== 'linear' && (point.curve === 'bezier' || !!point.out || !!draft.points[end].in);
    }
    function handlesFor(index) {
      const point = draft.points[index], previous = neighbor(index, -1), result = [];
      if (previous >= 0 && segmentBezier(previous) && point.in) result.push({side: 'in', point: {x: point.x + point.in.x, y: point.y + point.in.y}});
      if (segmentBezier(index) && point.out) result.push({side: 'out', point: {x: point.x + point.out.x, y: point.y + point.out.y}});
      return result;
    }
    function hitControl(point) {
      const index = hit(point);
      const anchorDistance = index < 0 ? Infinity : Math.hypot(screen(draft.points[index]).x - point.x, screen(draft.points[index]).y - point.y);
      let closest = null, distance = Math.min(10, anchorDistance);
      if (editable) handlesFor(selected).forEach(handle => {
        const mark = screen(handle.point), nextDistance = Math.hypot(mark.x - point.x, mark.y - point.y);
        if (nextDistance < distance) { closest = {kind: 'handle', index: selected, side: handle.side}; distance = nextDistance; }
      });
      return closest || (index < 0 ? null : {kind: 'point', index});
    }
    function inferPreset(points) {
      for (const name of ['line', 'rectangle', 'ellipse', 's', 'figure8', 'spiral']) {
        const unit = math.preset(name, 1, 1).points; if (unit.length !== points.length) continue;
        const axisSize = axis => {
          const sum = unit.reduce((value, p) => value + p[axis] * p[axis], 0);
          return sum > 1e-9 ? points.reduce((value, p, i) => value + p[axis] * unit[i][axis], 0) / sum : axis === 'x' ? 320 : 180;
        };
        const width = axisSize('x'), height = axisSize('y');
        if (width < 1 || width > 2000 || height < 1 || height > 2000) continue;
        const sameControl = (point, expected, key) => {
          if (!!point[key] !== !!expected[key]) return false;
          return !point[key] || (Math.abs(point[key].x - expected[key].x * width) < .002 && Math.abs(point[key].y - expected[key].y * height) < .002);
        };
        if (points.every((p, i) => Math.abs(p.x - unit[i].x * width) < .002 && Math.abs(p.y - unit[i].y * height) < .002 &&
          p.curve === unit[i].curve && sameControl(p, unit[i], 'in') && sameControl(p, unit[i], 'out'))) return {name, width: round(width), height: round(height)};
      }
      return null;
    }
    function markCustom() { if (loading) stopOutlineLoad(); $('pathPreset').value = 'custom'; }
    function setReference() {
      if (scene && typeof scene.setReference === 'function') scene.setReference(reference.outline, reference.width, reference.height);
    }
    function originalReference() {
      return openingEmitter && openingEmitter.outline ? {outline: clone(openingEmitter.outline),
        width: openingEmitter.width, height: openingEmitter.height} : null;
    }
    function outlineChoices() {
      contours = reference && contourMath && typeof contourMath.pathContours === 'function' ? contourMath.pathContours(reference.outline) : [];
      if (!contours.some(item => item.index === contourIndex)) contourIndex = contours.length ? contours[0].index : null;
      if ($('pathOutlineContour')) {
        $('pathOutlineContour').innerHTML = contours.map((item, i) => '<option value="' + item.index + '">' +
          (item.hole ? '內孔' : '外框') + ' ' + (item.index + 1) + (i === 0 && !item.hole ? ' · 最大外框' : '') + '</option>').join('');
        $('pathOutlineContour').value = contourIndex === null ? '' : String(contourIndex);
      }
    }
    function outlineFields() {
      const active = $('pathPreset').value === 'outline';
      if ($('pathOutlineControls')) $('pathOutlineControls').hidden = !active;
      if ($('pathOutlineContour')) $('pathOutlineContour').disabled = !editable || loading || !reference || !contours.length;
      if ($('pathLoadOutline')) $('pathLoadOutline').disabled = !editable || typeof loadOutline !== 'function';
      if ($('pathOutlineInfo')) $('pathOutlineInfo').textContent = loading ? '正在掃描 PNG 輪廓…' : reference ?
        (reference.outline.sourceName || '透明 PNG') + ' · 原圖 ' + reference.outline.width + ' × ' + reference.outline.height + ' px · ' + contours.length +
        ' 個獨立邊界；一次選一圈，可再拖曳控制點。' : '請載入透明 PNG，或先在發射頁掃描物件；會直接產生可編輯的封閉路徑。';
    }
    function syncReferenceSize() {
      if (!referenceLinked || !reference) return;
      reference.width = dimensions.width; reference.height = dimensions.height; setReference();
    }
    function applyOutline(refit = true) {
      if (!reference) { notice = '請先載入透明 PNG，才能產生輪廓路徑。'; refresh(false, true); return; }
      if (!contourMath || typeof contourMath.toPath !== 'function') throw new Error('目前無法轉換物件輪廓，請重新開啟新版工具。');
      const shape = contourMath.toPath(reference.outline, reference.width, reference.height, contourIndex === null ? undefined : contourIndex);
      Object.assign(draft, clone(shape), {offsets: false});
      dimensions.width = round(reference.width); dimensions.height = round(reference.height);
      referenceLinked = true; selected = 0; notice = ''; setReference(); refresh(refit, true);
    }
    function stopOutlineLoad() { loadToken++; loading = false; }
    function resizeAxis(axis, previous, value) {
      if (previous === value || previous <= 1e-9) return;
      if (loading) stopOutlineLoad();
      // Scale the edited points about the emitter origin; never regenerate a template.
      draft.points.forEach(point => {
        const before = point[axis]; point[axis] = round(clamp(before * value / previous, -4000, 4000));
        for (const side of ['in', 'out']) if (point[side]) {
          const endpoint = clamp((before + point[side][axis]) * value / previous, -4000, 4000);
          point[side][axis] = round(endpoint - point[axis]);
        }
      });
      syncReferenceSize();
    }
    function fields(force = false) {
      if (!draft) return;
      const point = selectedPoint();
      if ($('pathPointSelect')) {
        if (pointSelectCount !== draft.points.length) {
          $('pathPointSelect').innerHTML = draft.points.map((_, index) => '<option value="' + index + '">第 ' + (index + 1) + ' 點' + (index === 0 ? ' · 起點' : '') + '</option>').join('');
          pointSelectCount = draft.points.length;
        }
        $('pathPointSelect').value = String(selected);
      }
      for (const [id, value] of [['pathPointX', point.x], ['pathPointY', point.y],
        ['pathWidth', dimensions.width], ['pathHeight', dimensions.height]]) {
        if (force || doc.activeElement !== $(id)) $(id).value = String(round(value));
      }
      $('pathClosed').checked = !!draft.closed;
      $('pathReverse').checked = !!draft.reverse;
      $('pathSmooth').value = String(draft.smooth);
      const bezier = hasBezier();
      if ($('pathPointCurve')) {
        const previous = neighbor(selected, -1), next = neighbor(selected, 1), modes = [];
        if (previous >= 0) modes.push(segmentBezier(previous) ? 'bezier' : 'linear');
        if (next >= 0) modes.push(segmentBezier(selected) ? 'bezier' : 'linear');
        const mixed = modes.length === 2 && modes[0] !== modes[1];
        if (mixed && !mixedCurveOption && typeof doc.createElement === 'function') {
          mixedCurveOption = doc.createElement('option'); mixedCurveOption.value = 'mixed';
          mixedCurveOption.textContent = '兩側不同'; mixedCurveOption.disabled = true; $('pathPointCurve').append(mixedCurveOption);
        } else if (!mixed && mixedCurveOption) { mixedCurveOption.remove(); mixedCurveOption = null; }
        $('pathPointCurve').value = mixed ? 'mixed' : modes[0] || 'linear';
        $('pathPointCurve').disabled = !editable;
      }
      if ($('pathHandleHint')) $('pathHandleHint').textContent = bezier ? '藍色控制柄調整弧度；拖曳會平衡兩側，按住 Ctrl 可單獨調整一側。' : '選擇「貝茲」可拉出控制柄；原有折線也可用「減少控制點」轉換。';
      if ($('pathSimplify')) $('pathSimplify').disabled = !editable || loading || typeof math.convertToBezier !== 'function' || bezier || draft.points.length <= 2;
      $('pathDeletePoint').disabled = !editable || draft.points.length <= 2;
      $('pathAddPoint').disabled = !editable || draft.points.length >= MAX_POINTS;
      $('pathApplyPreset').disabled = !editable || $('pathPreset').value === 'custom';
      for (const id of ['pathPreset', 'pathWidth', 'pathHeight', 'pathPointX', 'pathPointY', 'pathClosed', 'pathReverse', 'pathSmooth', 'pathReset']) $(id).disabled = !editable;
      const explicit = draft.points.some(point => point.in || point.out || point.curve);
      if ($('pathSmoothField')) $('pathSmoothField').hidden = !!explicit;
      $('pathSmooth').disabled = !editable || explicit;
      $('pathSmooth').title = explicit ? '貝茲路徑直接以藍色控制柄調整弧度。' : '舊折線路徑的平滑程度。';
      $('pathApplyPreset').title = $('pathApplyPreset').disabled ? '自訂路徑可用「回到開啟時」還原；選取預設會立即更新形狀。' : '依目前寬高重新產生所選形狀，還原預設封閉與平滑設定。';
      outlineFields();
    }
    function draw() {
      if (!opened || !draft) return;
      if (!view) fit();
      const g = geometry(), dpr = Math.min(2, root.devicePixelRatio || 1);
      canvas.width = Math.max(1, Math.round(g.width * dpr));
      canvas.height = Math.max(1, Math.round(g.height * dpr));
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, g.width, g.height);
      ctx.fillStyle = '#101a25'; ctx.fillRect(0, 0, g.width, g.height);
      if (scene && typeof scene.draw === 'function' && (!$('pathShowReference') || $('pathShowReference').checked)) {
        ctx.save();
        try {
          // The shared scene draws in world coordinates with Canvas' downwards Y axis.
          ctx.translate(g.width / 2 - view.x * view.scale, g.height / 2 + view.y * view.scale);
          ctx.scale(view.scale, view.scale); scene.draw(ctx);
        } catch (error) { sceneNotice = '參考畫面暫時無法顯示：' + error.message; }
        finally { ctx.restore(); }
      }
      const origin = screen({x: 0, y: 0}, g);
      const basisScale = matrix ? Math.max(.001, Math.min(Math.hypot(matrix.a, matrix.c), Math.hypot(matrix.b, matrix.d))) : 1;
      const localScale = view.scale * basisScale;
      const grid = Math.pow(10, Math.floor(Math.log10(52 / localScale)));
      let step = grid * (52 / localScale / grid > 5 ? 10 : 52 / localScale / grid > 2 ? 5 : 2);
      ctx.strokeStyle = '#223340'; ctx.lineWidth = 1; ctx.beginPath();
      const halfWidth = g.width / (2 * view.scale), halfHeight = g.height / (2 * view.scale);
      const corners = [[-1, -1], [-1, 1], [1, -1], [1, 1]].map(([x, y]) => localPoint({x: view.x + halfWidth * x, y: view.y + halfHeight * y}));
      if (corners.every(Boolean)) {
        const left = Math.min(...corners.map(p => p.x)), right = Math.max(...corners.map(p => p.x));
        const bottom = Math.min(...corners.map(p => p.y)), top = Math.max(...corners.map(p => p.y));
        while ((right - left + top - bottom) / step > 300) step *= 2;
        for (let x = Math.ceil(left / step) * step; x <= right; x += step) {
          const a = screen({x, y: bottom}, g), b = screen({x, y: top}, g); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
        }
        for (let y = Math.ceil(bottom / step) * step; y <= top; y += step) {
          const a = screen({x: left, y}, g), b = screen({x: right, y}, g); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
        }
        ctx.stroke(); ctx.strokeStyle = '#456070'; ctx.beginPath();
        const xa = screen({x: left, y: 0}, g), xb = screen({x: right, y: 0}, g);
        const ya = screen({x: 0, y: bottom}, g), yb = screen({x: 0, y: top}, g);
        ctx.moveTo(xa.x, xa.y); ctx.lineTo(xb.x, xb.y); ctx.moveTo(ya.x, ya.y); ctx.lineTo(yb.x, yb.y);
      }
      ctx.stroke();
      let compiled;
      try { compiled = math.compile(draft); } catch (error) { notice = error.message; }
      const line = compiled ? compiled.points : draft.points;
      ctx.strokeStyle = '#72d6b5'; ctx.lineWidth = 2; ctx.beginPath();
      line.forEach((p, index) => { const q = screen(p, g); if (!index) ctx.moveTo(q.x, q.y); else ctx.lineTo(q.x, q.y); });
      if (draft.closed) ctx.closePath(); ctx.stroke();
      if (compiled && compiled.totalLength > 0) {
        [.2, .6].forEach(progress => {
          const p = compiled.sample(progress), q = screen(p, g);
          const direction = p.angle * Math.PI / 180, dx = Math.cos(direction), dy = Math.sin(direction);
          const tangent = matrix ? {x: matrix.a * dx + matrix.b * dy, y: matrix.c * dx + matrix.d * dy} : {x: dx, y: dy};
          const angle = -Math.atan2(tangent.y, tangent.x);
          ctx.save(); ctx.translate(q.x, q.y); ctx.rotate(angle); ctx.fillStyle = '#72d6b5'; ctx.beginPath();
          ctx.moveTo(7, 0); ctx.lineTo(-4, -4); ctx.lineTo(-4, 4); ctx.closePath(); ctx.fill(); ctx.restore();
        });
      }
      const chosen = draft.points[selected], anchor = screen(chosen, g);
      handlesFor(selected).forEach(handle => {
        const q = screen(handle.point, g);
        ctx.strokeStyle = '#6ab8ef'; ctx.lineWidth = 1; ctx.beginPath();
        ctx.moveTo(anchor.x, anchor.y); ctx.lineTo(q.x, q.y); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(q.x, q.y - 6); ctx.lineTo(q.x + 6, q.y);
        ctx.lineTo(q.x, q.y + 6); ctx.lineTo(q.x - 6, q.y); ctx.closePath();
        ctx.fillStyle = '#6ab8ef'; ctx.fill();
      });
      draft.points.forEach((p, index) => {
        const q = screen(p, g); ctx.beginPath(); ctx.arc(q.x, q.y, index === selected ? 7 : 5, 0, Math.PI * 2);
        ctx.fillStyle = index === selected ? '#f8e1ad' : '#182b38'; ctx.fill();
        ctx.lineWidth = 1.5; ctx.strokeStyle = index === selected ? '#f8e1ad' : '#72d6b5'; ctx.stroke();
        ctx.fillStyle = '#adc1cb'; ctx.font = '10px sans-serif'; ctx.fillText(String(index + 1), q.x + 8, q.y - 8);
      });
      if (compiled) {
        const start = screen(compiled.sample(0), g); ctx.fillStyle = '#75dfa8';
        ctx.fillRect(start.x - 3, start.y - 3, 6, 6); ctx.font = '11px sans-serif'; ctx.fillText('起點', start.x + 9, start.y + 16);
      }
      if (scene) {
        ctx.strokeStyle = '#f2818c'; ctx.lineWidth = 1.5; ctx.beginPath();
        ctx.moveTo(origin.x - 6, origin.y); ctx.lineTo(origin.x + 6, origin.y);
        ctx.moveTo(origin.x, origin.y - 6); ctx.lineTo(origin.x, origin.y + 6); ctx.stroke();
      }
      ctx.fillStyle = '#8faaba'; ctx.font = '11px sans-serif';
      ctx.fillText(scene ? '控制點 X／Y · 發射器局部座標' : 'X →  Y ↑ · 發射器局部座標', 12, g.height - 13);
      const info = compiled ? `${draft.points.length} 點 · 長度 ${round(compiled.totalLength)} px · 第 ${selected + 1} 點` : `${draft.points.length} 點`;
      const message = !editable ? sceneNotice || '掛接骨骼目前縮放為 0，請切換動畫時間後再編輯路徑。' : notice || sceneNotice;
      $('pathEditorInfo').textContent = message ? message + '　' + info : info;
      $('pathApply').disabled = !editable || loading || ($('pathPreset').value === 'outline' && (!reference || !contours.length)) || !compiled || compiled.totalLength <= 1e-8;
    }
    function refresh(refit = false, force = false) { if (refit && !drag) fit(); fields(force); draw(); }
    function geometryRefresh(force = true) { refresh(!scene, force); }
    function releaseDrag(cancel = false) {
      if (!drag) return;
      const previous = drag; drag = null;
      if (cancel) {
        if (previous.kind === 'pan') view = previous.before;
        else { draft = previous.beforeDraft; selected = previous.index; $('pathPreset').value = previous.preset; }
        notice = '';
      }
      try { if (canvas.hasPointerCapture(previous.pointerId)) canvas.releasePointerCapture(previous.pointerId); } catch (_) {}
      refresh(!scene && previous.kind !== 'pan', true);
    }
    function close() {
      stopOutlineLoad();
      releaseDrag(true); opened = false; draft = null; openingDraft = null; openingDimensions = null; openingEmitter = null; view = null; notice = '';
      const previous = scene; scene = null; matrix = null; editable = true; sceneNotice = '';
      reference = null; referenceLinked = false; referenceImported = false; contours = []; contourIndex = null;
      if (previous && typeof previous.dispose === 'function') previous.dispose();
      if (dialog.open && typeof dialog.close === 'function') dialog.close();
    }
    function open({preset} = {}) {
      const emitter = getEmitter(); if (!emitter) return false;
      if (opened) close();
      openingEmitter = emitter; draft = clone(math.normalize(emitter.path) || math.defaults()); openingDraft = clone(draft);
      selected = 0; notice = ''; opened = true;
      if (typeof getScene === 'function') {
        try { scene = getScene(emitter) || null; }
        catch (error) { editable = false; sceneNotice = '參考畫面暫時無法顯示：' + error.message; }
      }
      if (scene && scene.matrix) {
        const source = scene.matrix;
        const valid = ['a', 'b', 'c', 'd', 'x', 'y'].every(key => Number.isFinite(source[key]));
        matrix = valid ? {a: source.a, b: source.b, c: source.c, d: source.d, x: source.x, y: source.y} : {a: 0, b: 0, c: 0, d: 0, x: 0, y: 0};
        editable = valid && Math.abs(matrix.a * matrix.d - matrix.b * matrix.c) >= 1e-8;
      }
      const xs = draft.points.map(p => p.x), ys = draft.points.map(p => p.y);
      dimensions.width = round(clamp(Math.max(...xs) - Math.min(...xs) || 320, 1, 2000));
      dimensions.height = round(clamp(Math.max(...ys) - Math.min(...ys) || 180, 1, 2000));
      openingDimensions = clone(dimensions);
      const matched = inferPreset(draft.points);
      if (matched) { dimensions.width = matched.width; dimensions.height = matched.height; openingDimensions = clone(dimensions); }
      openingPreset = matched ? matched.name : 'custom'; $('pathPreset').value = openingPreset;
      reference = originalReference(); referenceLinked = false; referenceImported = false; contourIndex = null;
      try { outlineChoices(); } catch (error) { notice = error.message; }
      if (!dialog.open && typeof dialog.showModal === 'function') dialog.showModal();
      view = null; refresh(true, true);
      if (preset === 'outline' && editable) { $('pathPreset').value = 'outline'; applyPreset(); }
      canvas.focus(); return true;
    }
    function deletePoint() {
      if (!opened || !editable || draft.points.length <= 2) return;
      releaseDrag(false); draft.points.splice(selected, 1); selected = Math.min(selected, draft.points.length - 1);
      markCustom(); notice = ''; geometryRefresh();
    }
    function addPoint(point, index) {
      if (!editable || !point) return;
      if (!opened || draft.points.length >= MAX_POINTS) { notice = '最多可新增至 48 個控制點。'; draw(); return; }
      draft.points.splice(index, 0, {x: round(clamp(point.x, -4000, 4000)), y: round(clamp(point.y, -4000, 4000))});
      selected = index; markCustom(); notice = ''; geometryRefresh();
    }
    function nearestSegment(point) {
      let best = Infinity, result = {index: draft.points.length - 2, t: .5};
      const count = draft.closed ? draft.points.length : draft.points.length - 1;
      for (let i = 0; i < count; i++) {
        const first = draft.points[i], last = draft.points[(i + 1) % draft.points.length], curved = segmentBezier(i);
        const a = screen(first), b = screen(last);
        const firstControl = screen(first.out ? {x: first.x + first.out.x, y: first.y + first.out.y} : first);
        const lastControl = screen(last.in ? {x: last.x + last.in.x, y: last.y + last.in.y} : last);
        const evaluate = t => {
          if (!curved) return {x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t};
          const u = 1 - t;
          return {x: u * u * u * a.x + 3 * u * u * t * firstControl.x + 3 * u * t * t * lastControl.x + t * t * t * b.x,
            y: u * u * u * a.y + 3 * u * u * t * firstControl.y + 3 * u * t * t * lastControl.y + t * t * t * b.y};
        };
        const steps = curved ? 96 : 1;
        let previous = a;
        for (let piece = 0; piece < steps; piece++) {
          const next = evaluate((piece + 1) / steps), dx = next.x - previous.x, dy = next.y - previous.y, square = dx * dx + dy * dy;
          const projected = square ? clamp(((point.x - previous.x) * dx + (point.y - previous.y) * dy) / square, 0, 1) : 0;
          const distance = Math.hypot(point.x - previous.x - projected * dx, point.y - previous.y - projected * dy);
          if (distance < best) { best = distance; result = {index: i, t: clamp((piece + projected) / steps, .001, .999)}; }
          previous = next;
        }
      }
      return result;
    }
    function splitAt(index, t = .5) {
      if (!opened || !editable || draft.points.length >= MAX_POINTS) { notice = '最多可新增至 48 個控制點。'; draw(); return; }
      if (typeof math.splitSegment !== 'function') return;
      draft = clone(math.splitSegment(draft, index, t)); selected = index + 1;
      markCustom(); notice = ''; geometryRefresh();
    }
    function setPointCurve() {
      if (!opened || !editable) return;
      const choice = $('pathPointCurve').value;
      if (!['linear', 'bezier'].includes(choice)) return;
      releaseDrag(false);
      const curved = choice === 'bezier';
      if (curved && draft.smooth > 0 && !draft.points.some(point => point.in || point.out || point.curve)) {
        if (typeof math.convertToBezier !== 'function') { notice = '請先將平滑折線精簡為貝茲路徑。'; refresh(false, true); return; }
        const previousSelection = selectedPoint();
        try {
          const nextDraft = clone(math.convertToBezier(draft));
          selected = nextDraft.points.reduce((best, point, index, points) =>
            Math.hypot(point.x - previousSelection.x, point.y - previousSelection.y) < Math.hypot(points[best].x - previousSelection.x, points[best].y - previousSelection.y) ? index : best, 0);
          draft = nextDraft;
        } catch (error) { notice = error.message; refresh(false, true); return; }
      }
      const point = selectedPoint(), previousIndex = neighbor(selected, -1), nextIndex = neighbor(selected, 1);
      const previous = previousIndex >= 0 ? draft.points[previousIndex] : null, next = nextIndex >= 0 ? draft.points[nextIndex] : null;
      if (!curved) {
        if (previous) previous.curve = 'linear';
        if (next) point.curve = 'linear';
      } else {
        const direction = previous && next ? {x: next.x - previous.x, y: next.y - previous.y} :
          next ? {x: next.x - point.x, y: next.y - point.y} : {x: point.x - previous.x, y: point.y - previous.y};
        const length = Math.hypot(direction.x, direction.y) || 1;
        if (previous) {
          previous.curve = 'bezier';
          if (!point.in) { const span = Math.hypot(point.x - previous.x, point.y - previous.y) / 3;
            point.in = {x: round(clamp(point.x - direction.x / length * span, -4000, 4000) - point.x), y: round(clamp(point.y - direction.y / length * span, -4000, 4000) - point.y)}; }
        }
        if (next) {
          point.curve = 'bezier';
          if (!point.out) { const span = Math.hypot(next.x - point.x, next.y - point.y) / 3;
            point.out = {x: round(clamp(point.x + direction.x / length * span, -4000, 4000) - point.x), y: round(clamp(point.y + direction.y / length * span, -4000, 4000) - point.y)}; }
        }
      }
      markCustom(); notice = ''; geometryRefresh();
    }
    function moveHandle(local, ctrlKey) {
      if (!drag || drag.kind !== 'handle' || !local) return;
      drag.lastLocal = local; drag.ctrlKey = !!ctrlKey;
      const source = drag.before, point = clone(source), side = drag.side;
      let vector = {x: source[side].x + local.x - drag.anchor.x, y: source[side].y + local.y - drag.anchor.y};
      const opposite = side === 'in' ? 'out' : 'in';
      const balanced = !ctrlKey && handlesFor(drag.index).some(handle => handle.side === opposite);
      let shortening = 1;
      for (const sign of balanced ? [1, -1] : [1]) for (const axis of ['x', 'y']) {
        const offset = vector[axis] * sign;
        if (offset > 0) shortening = Math.min(shortening, (4000 - source[axis]) / offset);
        else if (offset < 0) shortening = Math.min(shortening, (-4000 - source[axis]) / offset);
      }
      vector = {x: round(vector.x * shortening), y: round(vector.y * shortening)};
      for (const axis of ['x', 'y']) {
        const limit = 4000 - Math.abs(source[axis]);
        vector[axis] = balanced ? clamp(vector[axis], -limit, limit) : clamp(vector[axis], -4000 - source[axis], 4000 - source[axis]);
      }
      point[side] = vector;
      if (balanced) point[opposite] = {x: -vector.x, y: -vector.y};
      draft.points[drag.index] = point; markCustom(); notice = ''; refresh(false, true);
    }
    function bindNumber(id, object, key, minimum, maximum, refit, onEdit) {
      const input = $(id); input.min = String(minimum); input.max = String(maximum); input.step = '1';
      ['input', 'change'].forEach(type => listen(input, type, () => {
        if (!opened || !editable || !input.value.trim()) return;
        const value = Number(input.value); if (!Number.isFinite(value) || value < minimum || value > maximum) return;
        const source = object(), previous = source[key]; source[key] = round(value);
        if (onEdit && previous !== source[key]) onEdit(previous, source[key]);
        notice = ''; refresh(refit && !scene);
      }));
      listen(input, 'blur', () => { if (opened) refresh(refit && !scene, true); });
    }
    bindNumber('pathWidth', () => dimensions, 'width', 1, 2000, true, (previous, value) => resizeAxis('x', previous, value));
    bindNumber('pathHeight', () => dimensions, 'height', 1, 2000, true, (previous, value) => resizeAxis('y', previous, value));
    bindNumber('pathPointX', selectedPoint, 'x', -4000, 4000, true, () => { const point = selectedPoint(); point.x = boundedAnchor(point, 'x', point.x); markCustom(); });
    bindNumber('pathPointY', selectedPoint, 'y', -4000, 4000, true, () => { const point = selectedPoint(); point.y = boundedAnchor(point, 'y', point.y); markCustom(); });
    ['pathClosed', 'pathReverse', 'pathSmooth'].forEach(id => listen($(id), 'change', () => {
      if (!opened || !editable) return;
      const key = {pathClosed: 'closed', pathReverse: 'reverse', pathSmooth: 'smooth'}[id];
      draft[key] = id === 'pathSmooth' ? clamp(Math.round(Number($(id).value) || 0), 0, 3) : $(id).checked;
      notice = ''; refresh();
    }));
    if ($('pathPointCurve')) listen($('pathPointCurve'), 'change', setPointCurve);
    if ($('pathPointSelect')) listen($('pathPointSelect'), 'change', () => {
      if (!opened) return;
      const index = Number($('pathPointSelect').value);
      if (!Number.isInteger(index) || index < 0 || index >= draft.points.length) return;
      releaseDrag(false); selected = index; refresh(false, true);
    });
    if ($('pathSimplify')) listen($('pathSimplify'), 'click', event => {
      event.preventDefault(); if (!opened || $('pathSimplify').disabled) return;
      releaseDrag(false);
      try {
        const beforeCount = draft.points.length, next = clone(math.convertToBezier(draft));
        math.compile(next); draft = next; selected = 0; markCustom();
        notice = '已精簡：' + beforeCount + ' → ' + draft.points.length + ' 個控制點，可拖曳藍色貝茲控制柄。'; geometryRefresh();
      } catch (error) { notice = error.message; refresh(false, true); }
    });
    function applyPreset() {
      if (!opened || !editable) return;
      stopOutlineLoad();
      if ($('pathPreset').value === 'custom') { notice = ''; refresh(); return; }
      if ($('pathPreset').value === 'outline') {
        try { releaseDrag(false); applyOutline(); }
        catch (error) { notice = error.message; refresh(false, true); }
        return;
      }
      referenceLinked = false;
      if (![$('pathWidth'), $('pathHeight')].every(input => input.value.trim() && Number.isFinite(Number(input.value)) && Number(input.value) >= 1 && Number(input.value) <= 2000)) {
        notice = '路徑寬高請輸入 1–2000。'; draw(); return;
      }
      try { releaseDrag(false); const shape = math.preset($('pathPreset').value, dimensions.width, dimensions.height);
        Object.assign(draft, clone(shape)); selected = 0; notice = ''; refresh(true, true);
      } catch (error) { notice = error.message; draw(); }
    }
    listen($('pathPreset'), 'change', applyPreset);
    listen($('pathApplyPreset'), 'click', event => { event.preventDefault(); applyPreset(); });
    if ($('pathOutlineContour')) listen($('pathOutlineContour'), 'change', () => {
      if (!opened || !editable || loading || !reference) return;
      const index = Number($('pathOutlineContour').value); if (!contours.some(item => item.index === index)) return;
      contourIndex = index; $('pathPreset').value = 'outline';
      try { releaseDrag(false); applyOutline(); }
      catch (error) { notice = error.message; refresh(false, true); }
    });
    if ($('pathLoadOutline') && $('pathOutlineFile')) listen($('pathLoadOutline'), 'click', event => {
      event.preventDefault(); if (!opened || !editable || typeof loadOutline !== 'function') return;
      $('pathOutlineFile').value = ''; $('pathOutlineFile').click();
    });
    if ($('pathOutlineFile')) {
      $('pathOutlineFile').accept = 'image/png';
      listen($('pathOutlineFile'), 'change', async () => {
        const file = $('pathOutlineFile').files && $('pathOutlineFile').files[0];
        $('pathOutlineFile').value = '';
        if (!file || !opened || !editable || typeof loadOutline !== 'function') return;
        const token = ++loadToken, target = openingEmitter; loading = true; notice = '';
        $('pathPreset').value = 'outline'; refresh(false, true);
        try {
          const loaded = await loadOutline(file, target);
          if (!opened || token !== loadToken || target !== openingEmitter || getEmitter() !== target) return;
          if (!loaded || !loaded.outline || !Number.isFinite(loaded.width) || !Number.isFinite(loaded.height) || loaded.width < 1 || loaded.width > 2000 || loaded.height < 1 || loaded.height > 2000) throw new Error('PNG 參考物件尺寸需為 1–2000。');
          if (!contourMath || typeof contourMath.pathContours !== 'function') throw new Error('目前無法轉換物件輪廓，請重新開啟新版工具。');
          const nextContours = contourMath.pathContours(loaded.outline);
          if (!nextContours.length) throw new Error('PNG 沒有有效邊界，請檢查透明度或改用其他圖片。');
          // Prepare the geometry before replacing this transaction's reference.
          const shape = contourMath.toPath(loaded.outline, loaded.width, loaded.height, nextContours[0].index);
          reference = {outline: clone(loaded.outline), width: loaded.width, height: loaded.height};
          referenceImported = true; referenceLinked = true; contourIndex = nextContours[0].index;
          outlineChoices(); Object.assign(draft, clone(shape), {offsets: false});
          dimensions.width = round(reference.width); dimensions.height = round(reference.height); selected = 0;
          loading = false; notice = ''; setReference(); refresh(true, true);
        } catch (error) {
          if (!opened || token !== loadToken || target !== openingEmitter || getEmitter() !== target) return;
          loading = false; notice = 'PNG 載入失敗：' + error.message; refresh(false, true);
        }
      });
    }
    listen($('pathReset'), 'click', event => {
      event.preventDefault(); if (!opened || !editable) return;
      releaseDrag(false); draft = clone(openingDraft); Object.assign(dimensions, openingDimensions);
      stopOutlineLoad(); reference = originalReference(); referenceLinked = false; referenceImported = false; contourIndex = null;
      try { outlineChoices(); if (scene && typeof scene.setReference === 'function') scene.setReference(null); }
      catch (error) { notice = error.message; }
      $('pathPreset').value = openingPreset;
      selected = 0; notice = ''; refresh(true, true);
    });
    listen($('pathAddPoint'), 'click', event => {
      event.preventDefault(); if (!opened || !editable) return;
      const p = selectedPoint(), next = draft.points[selected + 1] || (draft.closed ? draft.points[0] : null);
      if (next && segmentBezier(selected)) splitAt(selected);
      else if (next) addPoint({x: (p.x + next.x) / 2, y: (p.y + next.y) / 2}, selected + 1);
      else { const prev = draft.points[Math.max(0, selected - 1)], dx = p.x - prev.x, dy = p.y - prev.y, length = Math.hypot(dx, dy) || 1;
        addPoint({x: p.x + (dx || (!dy ? 1 : 0)) / length * 40, y: p.y + dy / length * 40}, selected + 1); }
    });
    listen($('pathDeletePoint'), 'click', event => { event.preventDefault(); deletePoint(); });
    ['pathCancel', 'pathDialogClose'].forEach(id => listen($(id), 'click', event => { event.preventDefault(); close(); }));
    listen(dialog, 'cancel', event => { event.preventDefault(); close(); });
    listen(dialog, 'close', () => { if (opened) close(); });
    listen($('pathApply'), 'click', event => {
      event.preventDefault(); if (!opened || $('pathApply').disabled) return;
      if (getEmitter() !== openingEmitter) { notice = '發射器已切換，請取消後重新開啟路徑。'; draw(); return; }
      try {
        const next = clone(math.normalize(draft)), compiled = math.compile(next);
        if (compiled.totalLength <= 1e-8) throw new Error('路徑至少需要兩個不同位置的控制點。');
        const changedReference = reference && (referenceImported || reference.width !== openingEmitter.width || reference.height !== openingEmitter.height);
        onApply(next, openingEmitter, changedReference ? clone(reference) : undefined); close();
      } catch (error) { notice = error.message; draw(); }
    });
    listen(canvas, 'pointerdown', event => {
      if (!opened || event.button !== 0) return;
      event.preventDefault(); canvas.focus(); const point = eventPoint(event), control = hitControl(point.screen);
      if (!control || !editable) drag = {kind: 'pan', pointerId: event.pointerId, before: {...view}, screen: point.screen};
      else {
        selected = control.index; drag = {kind: control.kind, index: control.index, side: control.side, pointerId: event.pointerId, before: clone(draft.points[control.index]),
          beforeDraft: clone(draft), anchor: point.local, lastLocal: point.local, ctrlKey: !!event.ctrlKey, preset: $('pathPreset').value};
      }
      try { canvas.setPointerCapture(event.pointerId); } catch (_) {} refresh(false, true);
    });
    listen(canvas, 'pointermove', event => {
      if (!opened || !drag || event.pointerId !== drag.pointerId) return;
      event.preventDefault(); const eventLocation = eventPoint(event);
      if (drag.kind === 'pan') {
        view.x = drag.before.x - (eventLocation.screen.x - drag.screen.x) / drag.before.scale;
        view.y = drag.before.y + (eventLocation.screen.y - drag.screen.y) / drag.before.scale;
        draw(); return;
      }
      if (drag.kind === 'handle') { moveHandle(eventLocation.local, event.ctrlKey); return; }
      const point = {...clone(drag.before), x: boundedAnchor(drag.before, 'x', drag.before.x + eventLocation.local.x - drag.anchor.x),
        y: boundedAnchor(drag.before, 'y', drag.before.y + eventLocation.local.y - drag.anchor.y)};
      const previous = draft.points[drag.index];
      if (point.x !== previous.x || point.y !== previous.y) { draft.points[drag.index] = point; markCustom(); }
      notice = ''; refresh(false, true);
    });
    listen(canvas, 'pointerup', event => { if (drag && event.pointerId === drag.pointerId) releaseDrag(false); });
    listen(canvas, 'pointercancel', event => { if (drag && event.pointerId === drag.pointerId) releaseDrag(true); });
    listen(canvas, 'lostpointercapture', event => { if (drag && event.pointerId === drag.pointerId) releaseDrag(false); });
    listen(canvas, 'dblclick', event => {
      if (!opened || !editable || event.button !== 0) return;
      event.preventDefault(); const point = eventPoint(event), index = hit(point.screen);
      if (index >= 0) { selected = index; refresh(false, true); return; }
      const nearest = nearestSegment(point.screen);
      if (segmentBezier(nearest.index)) splitAt(nearest.index, nearest.t);
      else addPoint(point.local, nearest.index + 1);
    });
    listen(canvas, 'contextmenu', event => {
      event.preventDefault(); if (!opened || !editable) return;
      const index = hit(eventPoint(event).screen); if (index >= 0) { selected = index; deletePoint(); }
    });
    listen(canvas, 'wheel', event => {
      if (!opened || !view || !Number.isFinite(event.deltaY)) return;
      event.preventDefault(); releaseDrag(false);
      const anchor = eventPoint(event), g = geometry(), factor = Math.exp(clamp(-event.deltaY * .0015, -1, 1));
      view.scale = clamp(view.scale * factor, .001, 1000);
      view.x = anchor.world.x - (anchor.screen.x - g.width / 2) / view.scale;
      view.y = anchor.world.y + (anchor.screen.y - g.height / 2) / view.scale;
      draw();
    }, {passive: false});
    if ($('pathShowReference')) {
      $('pathShowReference').checked = true;
      listen($('pathShowReference'), 'change', () => { if (opened) draw(); });
    }
    if ($('pathFitView')) listen($('pathFitView'), 'click', event => { event.preventDefault(); if (opened) { releaseDrag(false); refresh(true, true); } });
    listen(dialog, 'keydown', event => {
      if (!opened) return;
      if (event.key === 'Control' && drag && drag.kind === 'handle') { moveHandle(drag.lastLocal, true); return; }
      const target = event.target, tag = target && target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (target && target.isContentEditable)) return;
      if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); deletePoint(); }
      else if (event.key === 'Escape' && drag) { event.preventDefault(); releaseDrag(true); }
    });
    listen(dialog, 'keyup', event => {
      if (opened && event.key === 'Control' && drag && drag.kind === 'handle') moveHandle(drag.lastLocal, false);
    });
    if (typeof root.ResizeObserver === 'function') {
      observer = new root.ResizeObserver(() => { if (opened) refresh(!drag && !scene); }); observer.observe(canvas);
    }
    function bindingFor(input) {
      if (!opened || !draft || !editable) return null;
      const pointKey = input === $('pathPointX') ? 'x' : input === $('pathPointY') ? 'y' : null;
      if (pointKey) {
        const source = selectedPoint(), index = selected, before = clone(draft.points), preset = $('pathPreset').value;
        return {source, key: pointKey, affectsParticles: false, restore() {
          if (!opened || !draft) return; draft.points = clone(before); selected = index; $('pathPreset').value = preset; geometryRefresh();
        }};
      }
      const key = input === $('pathWidth') ? 'width' : input === $('pathHeight') ? 'height' : null;
      if (!key) return null;
      const previous = dimensions[key], before = clone(draft.points), preset = $('pathPreset').value;
      return {source: dimensions, key, affectsParticles: false, restore() {
        dimensions[key] = previous; if (opened && draft) { draft.points = clone(before); $('pathPreset').value = preset; syncReferenceSize(); geometryRefresh(); }
      }};
    }
    return {open, close, bindingFor, refresh() { if (opened) refresh(false, true); }, destroy() {
      close(); if (observer) observer.disconnect();
      listeners.forEach(([target, type, handler, options]) => target.removeEventListener(type, handler, options));
    }};
  }
  return {mount, MAX_POINTS};
});
