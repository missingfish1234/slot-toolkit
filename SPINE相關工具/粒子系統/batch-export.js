(function (root, factory) {
  'use strict';
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleBatchExport = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  // Batch export: one ZIP holding several Spine versions and colour variants of the
  // current project. Variants only recolour; motion, seeds and timing never change.
  const VERSIONS = [
    {version: '3.8.99', label: 'Spine 3.8'},
    {version: '4.0.56', label: 'Spine 4.0'},
    {version: '4.2.43', label: 'Spine 4.2'}
  ];
  const HUES = [60, 120, 180, 240, 300];
  const clone = value => JSON.parse(JSON.stringify(value));

  function hexToHsl(hex) {
    const value = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
    if (!value) return null;
    const n = parseInt(value[1], 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
    if (max === min) return {h: 0, s: 0, l};
    const d = max - min, s = l > .5 ? d / (2 - max - min) : d / (max + min);
    const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return {h: h * 60, s, l};
  }
  function hslToHex({h, s, l}) {
    const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
    const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return '#' + [f(0), f(8), f(4)].map(x => Math.round(Math.max(0, Math.min(1, x)) * 255).toString(16).padStart(2, '0')).join('');
  }
  function hueShift(hex, degrees) {
    const hsl = hexToHsl(hex); if (!hsl) return hex;
    if (hsl.s < 1e-6) return hex.toLowerCase();
    return hslToHex({h: ((hsl.h + degrees) % 360 + 360) % 360, s: hsl.s, l: hsl.l});
  }

  function variantLabel(variant, presets) {
    if (!variant || variant.kind === 'original') return '原色';
    if (variant.kind === 'hue') return '色相' + (variant.degrees > 0 ? '+' : '') + variant.degrees + '°';
    const preset = presets && presets.get ? presets.get('color', variant.id) : null;
    return preset ? preset.label : variant.id;
  }
  function variantSlug(variant) {
    if (!variant || variant.kind === 'original') return 'original';
    if (variant.kind === 'hue') return 'hue' + variant.degrees;
    return String(variant.id);
  }

  // Returns a recoloured deep copy; the source project is never touched.
  function applyVariant(project, variant, presets) {
    const result = clone(project);
    if (!variant || variant.kind === 'original') return result;
    result.emitters.forEach(e => {
      if (variant.kind === 'hue') {
        if (Array.isArray(e.colorGradient)) e.colorGradient = e.colorGradient.map(point => Object.assign({}, point, {color: hueShift(point.color, variant.degrees)}));
        if (e.colorStart) e.colorStart = hueShift(e.colorStart, variant.degrees);
        if (e.colorEnd) e.colorEnd = hueShift(e.colorEnd, variant.degrees);
      } else if (variant.kind === 'palette') {
        if (!presets || !presets.apply) throw new Error('配色預設尚未載入。');
        presets.apply(e, 'color', variant.id);
      }
    });
    return result;
  }

  function plan(versions, variants) {
    const jobs = [];
    variants.forEach(variant => versions.forEach(version => jobs.push({version, variant})));
    return jobs;
  }

  function mount(options) {
    options = options || {};
    const doc = options.document || root.document, presets = options.presets || root.ParticleLookPresets;
    const opener = doc.getElementById('batchExportButton');
    if (!opener) return {refresh() {}};
    const dialog = doc.createElement('dialog'); dialog.id = 'batchExportDialog'; dialog.className = 'help-dialog batch-export-dialog';
    dialog.setAttribute('aria-labelledby', 'batchExportTitle');
    const paletteItems = presets && presets.list ? presets.list('color') : [];
    const check = (name, value, label, checked) => '<label class="batch-chip"><input type="checkbox" name="' + name + '" value="' + value + '"' + (checked ? ' checked' : '') + '><span>' + label + '</span></label>';
    dialog.innerHTML = '<div class="dialog-header"><div><span class="section-eyebrow">BATCH EXPORT</span><h2 id="batchExportTitle">批次輸出</h2></div>' +
      '<button type="button" class="icon-button" data-batch-close aria-label="關閉批次輸出">×</button></div>' +
      '<div class="dialog-content batch-export-body">' +
      '<p class="field-hint">一次產生多個 Spine 版本與配色變體，全部放進同一個 ZIP，每組各自一個資料夾（含 JSON、圖片、編輯專案與匯入說明）。變體只改顏色，動態、亂數與時間完全相同。</p>' +
      '<section class="batch-section"><h3>Spine 版本</h3><div class="batch-chips" data-batch-versions>' +
      VERSIONS.map(item => check('version', item.version, item.label, false)).join('') + '</div></section>' +
      '<section class="batch-section"><h3>色相變體 <small>整組顏色一起轉，保留層與層之間的配色關係</small></h3><div class="batch-chips">' +
      check('variant', 'original', '原色', true) + HUES.map(degrees => check('variant', 'hue:' + degrees, '色相 +' + degrees + '°', false)).join('') + '</div></section>' +
      '<section class="batch-section"><h3>配色預設 <small>所有圖層套用同一組漸層</small></h3><div class="batch-chips">' +
      paletteItems.map(item => check('variant', 'palette:' + item.id, item.label, false)).join('') + '</div></section>' +
      '<p class="field-hint batch-note">貼圖 PNG 本身不會重新上色；白色或灰階貼圖的換色效果最明顯。</p>' +
      '<p class="batch-summary" data-batch-summary role="status" aria-live="polite"></p></div>' +
      '<div class="spine-merge-footer"><button type="button" class="quiet-button" data-batch-close>取消</button><button type="button" class="primary-button" data-batch-run>開始批次輸出</button></div>';
    doc.body.append(dialog);
    const summary = dialog.querySelector('[data-batch-summary]'), runButton = dialog.querySelector('[data-batch-run]');
    let running = false;
    function selection() {
      const versions = Array.from(dialog.querySelectorAll('input[name=version]:checked')).map(input => input.value);
      const variants = Array.from(dialog.querySelectorAll('input[name=variant]:checked')).map(input => {
        const [kind, value] = input.value.split(':');
        return kind === 'original' ? {kind: 'original'} : kind === 'hue' ? {kind: 'hue', degrees: Number(value)} : {kind: 'palette', id: value};
      });
      return {versions, variants};
    }
    function refresh() {
      const blocked = typeof options.blockedReason === 'function' ? options.blockedReason() : '';
      const {versions, variants} = selection(), count = versions.length * variants.length;
      runButton.disabled = running || !!blocked || !count;
      summary.classList.toggle('is-error', !!blocked);
      summary.textContent = running ? summary.textContent : blocked || (count ? '將輸出 ' + count + ' 組（' + variants.length + ' 種顏色 × ' + versions.length + ' 個版本）。' : '請至少選擇一個版本與一種顏色。');
      opener.title = blocked || '一次輸出多個 Spine 版本與配色變體';
    }
    function open() {
      const current = typeof options.getVersion === 'function' ? options.getVersion() : '4.0.56';
      if (!dialog.querySelector('input[name=version]:checked')) {
        dialog.querySelectorAll('input[name=version]').forEach(input => { input.checked = input.value === current; });
      }
      refresh(); if (!dialog.open) dialog.showModal();
    }
    opener.addEventListener('click', open);
    dialog.addEventListener('change', refresh);
    dialog.querySelectorAll('[data-batch-close]').forEach(button => button.addEventListener('click', () => { if (!running) dialog.close(); }));
    dialog.addEventListener('cancel', event => { if (running) event.preventDefault(); });
    runButton.addEventListener('click', async () => {
      if (running) return;
      const {versions, variants} = selection(), jobs = plan(versions, variants);
      if (!jobs.length) return;
      running = true; refresh();
      try {
        const result = await options.run(jobs, (done, total, label) => { summary.textContent = '正在輸出 ' + done + ' / ' + total + '：' + label + '…'; });
        summary.textContent = '完成：已輸出 ' + jobs.length + ' 組' + (result && result.fileName ? '（' + result.fileName + '）' : '') + '。';
      } catch (error) {
        summary.classList.add('is-error'); summary.textContent = error.message || '批次輸出失敗。';
        if (typeof options.notify === 'function') options.notify(summary.textContent, true);
      } finally { running = false; runButton.disabled = false; }
    });
    return {refresh, open, dialog};
  }
  return {VERSIONS, HUES, hueShift, applyVariant, plan, variantLabel, variantSlug, mount};
});
