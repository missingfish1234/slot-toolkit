(function (root, factory) {
  'use strict';
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleLookPresetsUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  function mount({getEmitter, onApply, Presets = root.ParticleLookPresets, math = root.ParticleCurveMath, document: doc = root.document}) {
    const kinds = ['color', 'alpha', 'size', 'sizeX', 'sizeY', 'speed'], labels = {color: '配色', alpha: '透明度', size: '尺寸', sizeX: 'X 軸寬度', sizeY: 'Y 軸高度', speed: '速度'};
    const keys = {color: 'colorGradient', alpha: 'alphaCurve', size: 'sizeCurve', sizeX: 'sizeCurveX', sizeY: 'sizeCurveY', speed: 'speedCurve'};
    const svgNamespace = 'http://www.w3.org/2000/svg';
    const rows = new Map(); let currentEmitter = null;
    if (!Presets || !math || !doc || typeof getEmitter !== 'function' || typeof onApply !== 'function') throw new Error('生命預設工具尚未完整載入。');
    function svgNode(name, attributes) {
      const node = doc.createElementNS(svgNamespace, name);
      Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
      return node;
    }
    function actualPoints(kind, emitter) {
      if (kind === 'color') return emitter.colorGradient || [{t: 0, color: emitter.colorStart}, {t: 1, color: emitter.colorEnd}];
      return emitter[keys[kind]] || (kind === 'speed' ? emitter.inactiveSpeedCurve : kind === 'sizeX' || kind === 'sizeY' ? emitter.sizeCurve : null) || [{t: 0, v: 1}, {t: 1, v: 1}];
    }
    function matches(kind, emitter, preset) {
      const inherited = (kind === 'sizeX' || kind === 'sizeY') && !emitter[keys[kind]];
      return !Presets.apply(inherited ? {...emitter, [keys[kind]]: actualPoints(kind, emitter)} : {...emitter}, kind, preset.id);
    }
    function drawPreview(row, points) {
      if (row.kind === 'color') {
        row.preview.style.background = 'linear-gradient(90deg,' + points.map(p => p.color + ' ' + p.t * 100 + '%').join(',') + ')';
      } else {
        const max = row.kind === 'alpha' ? 1 : 4, compiled = math.compile(points, max), samples = [];
        for (let i = 0; i <= 48; i++) samples.push((i ? 'L' : 'M') + (3 + i / 48 * 54).toFixed(2) + ',' + (25 - compiled.sample(i / 48) / max * 22).toFixed(2));
        row.path.setAttribute('d', samples.join(' '));
      }
    }
    kinds.forEach(kind => {
      const host = doc.getElementById(kind + 'PresetTools');
      if (!host) throw new Error('缺少' + labels[kind] + '預設欄位。');
      const field = doc.createElement('div'); field.className = 'look-preset-row';
      const label = doc.createElement('label'); label.className = 'look-preset-select';
      const caption = doc.createElement('span'); caption.className = 'sr-only'; caption.textContent = labels[kind] + '預設';
      const select = doc.createElement('select'); select.id = kind + 'PresetSelect'; select.setAttribute('aria-label', labels[kind] + '預設');
      const placeholder = doc.createElement('option'); placeholder.value = ''; placeholder.textContent = '選擇' + labels[kind] + '預設…'; select.append(placeholder);
      Presets.list(kind).forEach(preset => { const option = doc.createElement('option'); option.value = preset.id; option.textContent = preset.label; select.append(option); });
      label.append(caption, select);
      const button = doc.createElement('button'); button.id = kind + 'PresetApply'; button.type = 'button'; button.className = 'look-preset-apply';
      button.textContent = '套用'; button.setAttribute('aria-label', '套用' + labels[kind] + '預設');
      const preview = kind === 'color' ? doc.createElement('div') : svgNode('svg', {viewBox: '0 0 60 28', preserveAspectRatio: 'none'});
      preview.id = kind + 'PresetPreview'; preview.classList.add('look-preset-preview'); preview.setAttribute('role', 'img');
      const hint = doc.createElement('p'); hint.id = kind + 'PresetHint'; hint.className = 'look-preset-hint'; hint.setAttribute('role', 'status');
      const row = {kind, select, placeholder, button, preview, hint, choice: ''};
      if (kind !== 'color') {
        preview.append(svgNode('path', {d: 'M3,25 H57 M3,3 V25', class: 'look-preset-axis'}));
        row.path = svgNode('path', {class: 'look-preset-line'}); preview.append(row.path);
      }
      field.append(label, preview, button); host.append(field, hint); rows.set(kind, row);
      select.addEventListener('change', () => { row.choice = select.value; refresh(); });
      button.addEventListener('click', () => {
        if (button.disabled || !row.choice) return;
        onApply(kind, row.choice); refresh();
      });
    });
    function refresh() {
      const emitter = getEmitter(); if (!emitter) return;
      if (emitter !== currentEmitter) { currentEmitter = emitter; rows.forEach(row => { row.choice = ''; }); }
      rows.forEach(row => {
        const preset = row.choice ? Presets.get(row.kind, row.choice) : null;
        const applied = preset && matches(row.kind, emitter, preset);
        row.select.value = row.choice; row.button.disabled = !preset || !!applied;
        if (!preset) {
          const matching = row.kind === 'speed' && !emitter.speedCurve ? null : Presets.list(row.kind).find(candidate => matches(row.kind, emitter, candidate));
          row.placeholder.textContent = matching ? '目前：' + matching.label : row.kind === 'speed' && !emitter.speedCurve ? '選擇速度預設…' : '選擇' + labels[row.kind] + '預設…';
        }
        const title = preset ? preset.label + ' · ' + preset.description : '目前' + labels[row.kind] + (row.kind === 'speed' && !emitter.speedCurve ? '（尚未啟用）' : '');
        row.preview.setAttribute('aria-label', title); row.preview.setAttribute('title', title);
        row.hint.textContent = preset ? (applied ? '已套用 · ' : '預覽 · ') + preset.description : row.kind === 'color' ? '只套用配色；透明度可另選曲線預設。' : row.kind === 'speed' ? '套用後啟用速度曲線，可繼續拖曳節點調整。' : '先挑曲線，再套用；節點與貝茲仍可編輯。';
        drawPreview(row, preset ? preset.points : actualPoints(row.kind, emitter));
      });
    }
    refresh(); return {refresh};
  }
  return {mount};
});
