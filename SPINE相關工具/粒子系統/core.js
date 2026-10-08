(function (root, factory) {
  'use strict';
  const curveMath = typeof module === 'object' && module.exports ? require('./curve-math.js') : root.ParticleCurveMath;
  var api = factory(curveMath);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (CurveMath) {
  'use strict';
  if (!CurveMath) throw new Error('粒子曲線模組尚未載入，請先載入 curve-math.js。');

  const TAU = Math.PI * 2;
  const DEG = Math.PI / 180;
  const EPS = 1e-9;
  const RESET_EPS = 0.0001;
  const MAX_POOL = 1200;
  const clone = value => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const mod = (value, divisor) => ((value % divisor) + divisor) % divisor;
  const round = value => Math.round(value * 1e6) / 1e6 || 0;
  const fail = message => { throw new Error(message); };
  const SPINE_TARGETS = Object.freeze([
    Object.freeze({family: '3.8', version: '3.8.99'}),
    Object.freeze({family: '4.0', version: '4.0.56'}),
    Object.freeze({family: '4.2', version: '4.2.43'})
  ]);
  function spineProfile(target) {
    const requested = target === undefined ? '4.0.56' : target;
    const preset = SPINE_TARGETS.find(item => item.family === requested);
    const version = preset ? preset.version : requested;
    if (typeof version !== 'string' || !/^(3\.8|4\.0|4\.2)\.\d+$/.test(version)) fail('Spine 輸出版本僅支援 3.8、4.0、4.2。');
    if (version === '3.8.75') fail('Spine 官方 runtime 不接受 3.8.75 資料，請使用 3.8.99 重新匯出。');
    const family = version.split('.').slice(0, 2).join('.');
    return {version, family, colorTimeline: family === '3.8' ? 'color' : 'rgba', rotationKey: family === '3.8' ? 'angle' : 'value'};
  }
  function freezeDeep(value) {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.keys(value).forEach(key => freezeDeep(value[key]));
      Object.freeze(value);
    }
    return value;
  }

  function createEmitter(id, name, preset) {
    const emitter = {
      id: String(id || 'emitter1'), name: String(name || '發射器 1'), enabled: true,
      x: 0, y: 0, shape: 'point', width: 120, height: 120,
      lineLength: 120, lineRotation: 0, arcAngle: 360, arcRotation: 90,
      angle: 90, spread: 80, count: 32, emissionDuration: 1,
      life: 1.6, lifeRandom: 0.2, speed: 80, speedRandom: 20,
      gravity: 0, wind: 0, windAngle: 0,
      size: 12, sizeRandom: 4, rotation: 0, spin: 0, spinRandom: 0,
      alignDirection: false, blend: 'additive', colorStart: '#fff1b0', colorEnd: '#ff9900',
      motionCurve: 'linear',
      sizeCurve: [{t: 0, v: 0.5}, {t: 0.2, v: 1}, {t: 1, v: 0}],
      alphaCurve: [{t: 0, v: 0}, {t: 0.12, v: 1}, {t: 0.8, v: 0.8}, {t: 1, v: 0}],
      speedCurve: null, inactiveSpeedCurve: null, colorGradient: null,
      image: null
    };
    switch (preset || 'glow') {
      case 'sparks':
      case 'spark':
        Object.assign(emitter, {count: 48, emissionDuration: 0.12, life: 1.1, speed: 220,
          speedRandom: 80, spread: 360, gravity: 160, size: 7, sizeRandom: 3,
          colorStart: '#fff6c8', colorEnd: '#ff6b19'});
        break;
      case 'coins':
        Object.assign(emitter, {blend: 'normal', count: 32, emissionDuration: 0.12,
          life: 2.2, lifeRandom: 0.3, speed: 280, speedRandom: 80, angle: 90,
          spread: 100, gravity: 280, size: 24, sizeRandom: 6,
          spin: 160, spinRandom: 220, colorStart: '#ffffff', colorEnd: '#ffffff',
          sizeCurve: [{t: 0, v: 0.7}, {t: 0.15, v: 1}, {t: 1, v: 1}],
          alphaCurve: [{t: 0, v: 0}, {t: 0.05, v: 1}, {t: 0.8, v: 1}, {t: 1, v: 0}]});
        break;
      case 'bubbles':
        Object.assign(emitter, {blend: 'normal', shape: 'box', width: 240, height: 60,
          count: 24, emissionDuration: 3, life: 3.2, lifeRandom: 0.6, speed: 55,
          speedRandom: 20, angle: 90, spread: 30, size: 24, sizeRandom: 10,
          colorStart: '#ffffff', colorEnd: '#ffffff',
          sizeCurve: [{t: 0, v: 0.3}, {t: 0.2, v: 0.8}, {t: 1, v: 1.3}],
          alphaCurve: [{t: 0, v: 0}, {t: 0.15, v: 0.8}, {t: 0.8, v: 0.6}, {t: 1, v: 0}]});
        break;
      case 'smoke':
        Object.assign(emitter, {blend: 'normal', count: 20, life: 2.8, lifeRandom: 0.4,
          speed: 35, speedRandom: 10, size: 40, sizeRandom: 10,
          colorStart: '#cbd5e1', colorEnd: '#64748b', spinRandom: 20,
          sizeCurve: [{t: 0, v: 0.4}, {t: 1, v: 1.8}],
          alphaCurve: [{t: 0, v: 0}, {t: 0.18, v: 0.4}, {t: 1, v: 0}]});
        break;
      case 'ring':
        Object.assign(emitter, {shape: 'ring', width: 160, height: 160, count: 36,
          spread: 360, speed: 20, speedRandom: 5, life: 1.8, size: 10});
        break;
      case 'confetti':
        Object.assign(emitter, {blend: 'normal', shape: 'box', width: 240, height: 10,
          count: 44, life: 2.5, lifeRandom: 0.4, speed: 140, speedRandom: 50,
          gravity: 150, size: 14, spin: 160, spinRandom: 120,
          colorStart: '#ffd86a', colorEnd: '#f472b6',
          sizeCurve: [{t: 0, v: 1}, {t: 1, v: 1}]});
        break;
      case 'glow': break;
      default: fail('不支援的粒子預設：' + preset);
    }
    return emitter;
  }

  function createProject() {
    return {
      format: 'particle-studio', schemaVersion: 1, name: 'particles', fps: 30, spineVersion: '4.0.56',
      duration: 3, loop: true, flow: normalizeFlow(undefined, 3), seed: 42, emitters: [createEmitter('emitter1', '金色光點')],
      background: {color: '#111827', image: null, x: 0, y: 0, scale: 1}
    };
  }

  function normalizeFlow(raw, fallbackLoopDuration) {
    const source = raw === undefined || raw === null ? {} : raw;
    if (typeof source !== 'object' || Array.isArray(source)) fail('In / Loop / Out 設定格式不正確。');
    const fallback = fallbackLoopDuration === undefined ? 3 : fallbackLoopDuration;
    if (typeof fallback !== 'number' || !Number.isFinite(fallback) || fallback < 0.05 || fallback > 30) fail('Loop 長度必須是 0.05 到 30 秒。');
    const result = {enabled: boolean(source, 'enabled', false, '三段動畫啟用')}, names = new Set();
    ['in', 'loop', 'out'].forEach(kind => {
      const phase = source[kind] === undefined ? {} : source[kind];
      if (!phase || typeof phase !== 'object' || Array.isArray(phase)) fail(kind + ' 動畫設定格式不正確。');
      const name = text(phase, 'name', kind, 80, kind + ' 動畫名稱');
      if (/[\u0000-\u001f\u007f]/.test(name) || Array.from(name).some(c => c.length === 1 && c.charCodeAt(0) >= 0xd800 && c.charCodeAt(0) <= 0xdfff)) fail(kind + ' 動畫名稱不可含控制字元或不完整的 Unicode 字元。');
      if (names.has(name)) fail('In、Loop、Out 動畫名稱必須各不相同。');
      names.add(name);
      result[kind] = {name, duration: round(number(phase, 'duration', kind === 'loop' ? fallback : 1, 0.05, 30, false, kind + ' 動畫長度'))};
    });
    return result;
  }

  function number(raw, key, fallback, low, high, integer, label) {
    const value = raw[key] === undefined ? fallback : raw[key];
    if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high || (integer && !Number.isInteger(value))) {
      fail((label || key) + '必須是 ' + low + ' 到 ' + high + (integer ? ' 的整數。' : ' 的有限數值。'));
    }
    return value;
  }

  function boolean(raw, key, fallback, label) {
    if (raw[key] === undefined) return fallback;
    if (typeof raw[key] !== 'boolean') fail((label || key) + '必須是布林值。');
    return raw[key];
  }

  function text(raw, key, fallback, maxLength, label) {
    const value = raw[key] === undefined ? fallback : raw[key];
    if (typeof value !== 'string' || !value.trim() || value.length > maxLength) fail((label || key) + '必須是 1 到 ' + maxLength + ' 字的文字。');
    return value.trim();
  }

  function enumValue(raw, key, fallback, options, label) {
    const value = raw[key] === undefined ? fallback : raw[key];
    if (!options.includes(value)) fail((label || key) + '不支援此設定：' + value);
    return value;
  }

  function color(value, label) {
    if (typeof value !== 'string' || !/^#[0-9a-f]{6}$/i.test(value)) fail(label + '必須是六碼 HEX 色碼，例如 #ffffff。');
    return value.toLowerCase();
  }

  function curve(raw, fallback, maxValue, label) {
    const points = raw === undefined ? fallback : raw;
    return CurveMath.normalize(points, maxValue, label);
  }

  function colorGradient(raw) {
    if (raw === undefined || raw === null) return null;
    if (!Array.isArray(raw) || raw.length < 2 || raw.length > 32) fail('顏色漸層必須有 2 到 32 個控制點。');
    let previous = -1;
    const points = raw.map(point => {
      if (!point || typeof point !== 'object') fail('顏色漸層控制點格式不正確。');
      const t = number(point, 't', undefined, 0, 1, false, '顏色漸層時間');
      if (t <= previous) fail('顏色漸層時間必須嚴格遞增。');
      previous = t;
      return {t, color: color(point.color, '顏色漸層色碼')};
    });
    if (points[0].t !== 0 || points[points.length - 1].t !== 1) fail('顏色漸層必須包含 t=0 與 t=1 的端點。');
    return points;
  }

  // Only embedded PNGs are accepted. Inspect the IHDR instead of trusting saved dimensions.
  function image(raw, label) {
    if (raw === undefined || raw === null) return null;
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) fail(label + '素材格式不正確。');
    const width = number(raw, 'width', undefined, 1, 2048, true, label + '寬度');
    const height = number(raw, 'height', undefined, 1, 2048, true, label + '高度');
    const data = raw.dataUrl;
    if (raw.mime !== 'image/png' || typeof data !== 'string' || !data.startsWith('data:image/png;base64,')) fail(label + '僅接受內嵌 PNG，不能使用外部網址。');
    const base64 = data.slice(22);
    // Repeating four-character regexp groups can exhaust V8's regexp stack on
    // large but valid PNGs. A single character-class scan stays linear in size.
    if (base64.length > 4 * 1024 * 1024 * 4 / 3 + 4 || base64.length < 44 || base64.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(base64)) fail(label + 'PNG 編碼無效，或素材超過 4 MiB。');
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0;
    const tail = alphabet.indexOf(base64[base64.length - padding - 1]);
    if (base64.length / 4 * 3 - padding > 4 * 1024 * 1024 ||
        (padding === 2 && (tail & 15) !== 0) || (padding === 1 && (tail & 3) !== 0)) fail(label + 'PNG 編碼無效，或素材超過 4 MiB。');
    const bytes = [];
    for (let i = 0; i < 44; i += 4) {
      const word = (alphabet.indexOf(base64[i]) << 18) | (alphabet.indexOf(base64[i + 1]) << 12) | (alphabet.indexOf(base64[i + 2]) << 6) | alphabet.indexOf(base64[i + 3]);
      bytes.push((word >>> 16) & 255, (word >>> 8) & 255, word & 255);
    }
    const signature = [137, 80, 78, 71, 13, 10, 26, 10];
    if (!signature.every((v, i) => bytes[i] === v) || String.fromCharCode.apply(null, bytes.slice(12, 16)) !== 'IHDR') fail(label + '不是有效的 PNG 素材。');
    const u32 = offset => ((bytes[offset] * 0x1000000) + (bytes[offset + 1] << 16) + (bytes[offset + 2] << 8) + bytes[offset + 3]) >>> 0;
    if (u32(16) !== width || u32(20) !== height) fail(label + '尺寸與 PNG 檔案內容不一致。');
    return {name: text(raw, 'name', 'image.png', 160, label + '檔名'), mime: 'image/png', width, height, dataUrl: data};
  }

  function normalizeProject(raw) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) fail('專案格式不正確。');
    if (raw.format !== 'particle-studio' || raw.schemaVersion !== 1) fail('這不是 Particle Studio 第 1 版專案，請載入 .particle.json 專案檔。');
    const result = createProject();
    result.spineVersion = spineProfile(raw.spineVersion).version;
    result.name = text(raw, 'name', result.name, 120, '專案名稱');
    result.fps = number(raw, 'fps', 30, 10, 60, true, '烘焙 FPS');
    result.duration = round(number(raw, 'duration', 3, 0.05, 30, false, '動畫長度'));
    result.flow = normalizeFlow(raw.flow, result.duration);
    result.seed = number(raw, 'seed', 42, 0, 0xffffffff, true, '隨機種子');
    result.loop = boolean(raw, 'loop', true, '循環設定');
    if (!Array.isArray(raw.emitters) || raw.emitters.length < 1 || raw.emitters.length > 8) fail('專案必須包含 1 到 8 個發射器。');
    const ids = new Set();
    result.emitters = raw.emitters.map((source, emitterIndex) => {
      if (!source || typeof source !== 'object' || Array.isArray(source)) fail('發射器格式不正確。');
      const id = text(source, 'id', 'emitter' + (emitterIndex + 1), 48, '發射器 ID');
      if (!/^[a-zA-Z0-9_-]+$/.test(id) || ids.has(id)) fail('發射器 ID 必須唯一，且只含英文字母、數字、底線或減號。');
      ids.add(id);
      const e = createEmitter(id, text(source, 'name', '發射器 ' + (emitterIndex + 1), 80, '發射器名稱'));
      e.enabled = boolean(source, 'enabled', true, '發射器啟用');
      e.alignDirection = boolean(source, 'alignDirection', false, '方向對齊');
      e.shape = enumValue(source, 'shape', e.shape, ['point', 'direction', 'line', 'circle', 'ring', 'box'], '發射形狀');
      // Keep this optional in createEmitter so legacy callers that change only
      // shape still derive the matching historical emission location.
      e.emitFrom = enumValue(source, 'emitFrom', e.shape === 'ring' ? 'edge' : 'area', ['area', 'edge'], '發射位置');
      e.blend = enumValue(source, 'blend', e.blend, ['additive', 'normal'], '混合模式');
      e.motionCurve = enumValue(source, 'motionCurve', e.motionCurve, ['linear', 'easeOut', 'easeIn', 'easeInOut'], '運動曲線');
      const ranges = {
        x: [-4000, 4000], y: [-4000, 4000], width: [0, 2000], height: [0, 2000],
        lineLength: [0, 2000], lineRotation: [-3600, 3600], arcAngle: [1, 360], arcRotation: [-3600, 3600],
        angle: [-3600, 3600], spread: [0, 360], count: [1, 400], emissionDuration: [0, 30],
        life: [0.05, 10], lifeRandom: [0, 8], speed: [0, 4000], speedRandom: [0, 4000],
        gravity: [-6000, 6000], wind: [-3000, 3000], windAngle: [-3600, 3600],
        size: [0.1, 1000], sizeRandom: [0, 1000], rotation: [-36000, 36000],
        spin: [-3600, 3600], spinRandom: [0, 3600]
      };
      Object.keys(ranges).forEach(key => { e[key] = number(source, key, e[key], ranges[key][0], ranges[key][1], key === 'count', '發射器「' + e.name + '」的 ' + key); });
      // Older files described wind by strength and angle. Store its equivalent
      // horizontal wind and downward gravity so editing either signed axis
      // keeps the other axis and the original trajectory intact.
      if (e.windAngle !== 0) {
        const angle = e.windAngle * DEG;
        const horizontalWind = Math.cos(angle) * e.wind;
        const downwardGravity = e.gravity - Math.sin(angle) * e.wind;
        if (Math.abs(downwardGravity) > 6000) fail('發射器「' + e.name + '」的上下外力換算後超過 ±6000 px/秒²。');
        e.wind = Math.abs(horizontalWind) < 1e-10 ? 0 : horizontalWind;
        e.gravity = Math.abs(downwardGravity) < 1e-10 ? 0 : downwardGravity;
        e.windAngle = 0;
      }
      e.colorStart = color(source.colorStart === undefined ? e.colorStart : source.colorStart, '起始色');
      e.colorEnd = color(source.colorEnd === undefined ? e.colorEnd : source.colorEnd, '結束色');
      e.sizeCurve = curve(source.sizeCurve, e.sizeCurve, 4, '尺寸曲線');
      e.alphaCurve = curve(source.alphaCurve, e.alphaCurve, 1, '透明度曲線');
      e.speedCurve = source.speedCurve === undefined || source.speedCurve === null ? null : curve(source.speedCurve, null, 4, '速度曲線');
      e.inactiveSpeedCurve = source.inactiveSpeedCurve === undefined || source.inactiveSpeedCurve === null ? null : curve(source.inactiveSpeedCurve, null, 4, '停用的速度曲線');
      e.colorGradient = colorGradient(source.colorGradient);
      e.image = image(source.image, '發射器「' + e.name + '」');
      return e;
    });
    const bg = raw.background === undefined ? result.background : raw.background;
    if (!bg || typeof bg !== 'object' || Array.isArray(bg)) fail('背景設定格式不正確。');
    result.background = {
      color: color(bg.color === undefined ? '#111827' : bg.color, '背景色'), image: image(bg.image, '背景'),
      x: number(bg, 'x', 0, -4000, 4000, false, '背景 X'),
      y: number(bg, 'y', 0, -4000, 4000, false, '背景 Y'),
      scale: number(bg, 'scale', 1, 0.01, 20, false, '背景縮放')
    };
    const totalImages = result.emitters.reduce((sum, e) => sum + (e.image ? e.image.dataUrl.length : 0), 0) + (result.background.image ? result.background.image.dataUrl.length : 0);
    if (totalImages > 16 * 1024 * 1024) fail('內嵌素材總量超過 16 MiB，請縮小圖片後重試。');
    return result;
  }

  function seedHash(value) {
    let hash = 2166136261;
    for (let i = 0; i < value.length; i++) hash = Math.imul(hash ^ value.charCodeAt(i), 16777619);
    return hash >>> 0;
  }

  function random(seed) {
    let state = seed >>> 0;
    return function () {
      state += 0x6d2b79f5;
      let value = Math.imul(state ^ (state >>> 15), 1 | state);
      value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
  }

  function rgb(hex) { return [1, 3, 5].map(start => parseInt(hex.slice(start, start + 2), 16) / 255); }
  function evalCurve(points, t) {
    if (t <= 0) return points[0].v;
    for (let i = 1; i < points.length; i++) {
      if (t <= points[i].t) {
        const a = points[i - 1], b = points[i];
        return a.v + (b.v - a.v) * (t - a.t) / (b.t - a.t);
      }
    }
    return points[points.length - 1].v;
  }

  function evalGradient(points, t) {
    if (t <= 0) return points[0].color.slice();
    for (let i = 1; i < points.length; i++) {
      if (t <= points[i].t) {
        const a = points[i - 1], b = points[i], progress = (t - a.t) / (b.t - a.t);
        return a.color.map((channel, c) => channel + (b.color[c] - channel) * progress);
      }
    }
    return points[points.length - 1].color.slice();
  }

  function curveProgress(points, age, life) {
    // Authored nodes are exported on a microsecond grid. Resolve a node's
    // quantized timestamp to the node itself so floating remainders cannot
    // leave stepped curves on the previous value until the next frame.
    for (const point of points) if (Math.abs(age - point.t * life) <= 0.0000005 + EPS) return point.t;
    return age / life;
  }

  function ease(t, mode) {
    if (mode === 'easeIn') return t * t;
    if (mode === 'easeOut') return 1 - (1 - t) * (1 - t);
    if (mode === 'easeInOut') return t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t);
    return t;
  }

  // Arc angles are actual world polar directions (0 right, 90 up), centered on
  // arcRotation. Partial noncircular arcs use an inverse perimeter-distance table.
  // Full rings retain the original seeded parameter-angle mapping for old projects.
  function ringSampler(e) {
    const rx = e.width / 2, ry = e.height / 2, span = e.arcAngle * DEG;
    const full = e.arcAngle === 360;
    if (full || rx === ry) {
      const start = full ? 0 : (e.arcRotation - e.arcAngle / 2) * DEG;
      return ratio => {
        const angle = start + ratio * (full ? TAU : span);
        return {x: Math.cos(angle) * rx, y: Math.sin(angle) * ry};
      };
    }
    function parameterAngle(worldAngle) {
      // A collapsed ellipse retains a finite, line-shaped parameterization.
      if (rx === 0 || ry === 0) return worldAngle;
      const angle = Math.atan2(rx * Math.sin(worldAngle), ry * Math.cos(worldAngle));
      return angle + TAU * Math.round((worldAngle - angle) / TAU);
    }
    const start = full ? 0 : parameterAngle((e.arcRotation - e.arcAngle / 2) * DEG);
    const end = full ? TAU : parameterAngle((e.arcRotation + e.arcAngle / 2) * DEG);
    const steps = Math.max(32, Math.ceil((end - start) / TAU * 2048));
    const increment = (end - start) / steps;
    const lengths = new Float64Array(steps + 1);
    let previousX = rx * Math.cos(start), previousY = ry * Math.sin(start);
    for (let i = 1; i <= steps; i++) {
      const angle = start + i * increment, x = rx * Math.cos(angle), y = ry * Math.sin(angle);
      lengths[i] = lengths[i - 1] + Math.hypot(x - previousX, y - previousY);
      previousX = x; previousY = y;
    }
    const total = lengths[steps];
    return ratio => {
      if (total === 0) return {x: 0, y: 0};
      const distance = ratio * total;
      let low = 0, high = steps;
      while (low < high) {
        const middle = (low + high) >>> 1;
        if (lengths[middle] < distance) low = middle + 1;
        else high = middle;
      }
      const index = Math.max(1, low);
      const interval = lengths[index] - lengths[index - 1];
      const fraction = interval ? (distance - lengths[index - 1]) / interval : 0;
      const angle = start + (index - 1 + fraction) * increment;
      return {x: rx * Math.cos(angle), y: ry * Math.sin(angle)};
    };
  }

  // Ellipse sectors have a constant area Jacobian in parameter angle and
  // squared radius. World polar arc endpoints must be converted before sampling;
  // choosing the existing perimeter sampler would bias a noncircular sector.
  function ringAreaSampler(e) {
    const rx = e.width / 2, ry = e.height / 2;
    if (rx === 0 || ry === 0) {
      const extent = rx || ry;
      if (!extent) return () => ({x: 0, y: 0});
      const positiveAngle = rx ? 0 : 90;
      const allowed = [1, -1].filter(sign => {
        if (e.arcAngle === 360) return true;
        const angle = positiveAngle + (sign < 0 ? 180 : 0);
        const difference = mod(angle - e.arcRotation + 180, 360) - 180;
        return Math.abs(difference) <= e.arcAngle / 2 + EPS;
      });
      return (angleRatio, radiusRatio) => {
        if (!allowed.length) return {x: 0, y: 0};
        const sign = allowed[Math.min(allowed.length - 1, Math.floor(angleRatio * allowed.length))];
        const distance = sign * extent * radiusRatio;
        return rx ? {x: distance, y: 0} : {x: 0, y: distance};
      };
    }
    function parameterAngle(worldAngle) {
      const angle = Math.atan2(rx * Math.sin(worldAngle), ry * Math.cos(worldAngle));
      return angle + TAU * Math.round((worldAngle - angle) / TAU);
    }
    const full = e.arcAngle === 360;
    const start = full ? 0 : parameterAngle((e.arcRotation - e.arcAngle / 2) * DEG);
    const end = full ? TAU : parameterAngle((e.arcRotation + e.arcAngle / 2) * DEG);
    return (angleRatio, radiusRatio) => {
      const angle = start + angleRatio * (end - start), radius = Math.sqrt(radiusRatio);
      return {x: rx * Math.cos(angle) * radius, y: ry * Math.sin(angle) * radius};
    };
  }

  function boxEdgePoint(e, edgeRatio, positionRatio) {
    const width = e.width, height = e.height;
    const distance = edgeRatio * 2 * (width + height);
    if (distance < width) return {x: (positionRatio - 0.5) * width, y: -height / 2};
    if (distance < width + height) return {x: width / 2, y: (positionRatio - 0.5) * height};
    if (distance < 2 * width + height) return {x: (positionRatio - 0.5) * width, y: height / 2};
    return {x: -width / 2, y: (positionRatio - 0.5) * height};
  }

  function bake(raw) {
    const project = normalizeProject(raw);
    const particles = [];
    let generatedParticles = 0, maxPoolCycles = 1, longLived = false;
    const warnings = [];
    project.emitters.forEach(e => {
      if (!e.enabled) return;
      const rand = random((project.seed ^ seedHash(e.id)) >>> 0);
      const signed = amplitude => (rand() * 2 - 1) * amplitude;
      const sampleRing = e.shape === 'ring' ? (e.emitFrom === 'area' ? ringAreaSampler(e) : ringSampler(e)) : null;
      // Ring historically consumes one shape draw. Its new area radius uses
      // a separate stream so switching location never reshuffles life or motion.
      const ringRadiusRand = e.shape === 'ring' && e.emitFrom === 'area'
        ? random((project.seed ^ seedHash(e.id + ':ring-area-radius')) >>> 0) : null;
      const lifecycle = {
        size: CurveMath.compile(e.sizeCurve, 4), alpha: CurveMath.compile(e.alphaCurve, 1),
        speed: e.speedCurve ? CurveMath.compile(e.speedCurve, 4) : null,
        sizeLinear: e.sizeCurve.every(point => !point.curve || point.curve === 'linear'),
        alphaLinear: e.alphaCurve.every(point => !point.curve || point.curve === 'linear'),
        gradient: e.colorGradient ? e.colorGradient.map(point => ({t: point.t, color: rgb(point.color)})) : null
      };
      let index = 0, clipped = false;
      for (let sourceIndex = 0; sourceIndex < e.count; sourceIndex++) {
        // Use the same microsecond grid as JSON keys so birth/death attachment events
        // cannot slip to the following video frame after decimal quantization.
        const life = round(clamp(e.life + signed(e.lifeRandom), 0.05, 16));
        const speed = Math.max(0, e.speed + signed(e.speedRandom));
        const size = Math.max(0.1, e.size + signed(e.sizeRandom));
        const angle = (e.angle + signed(e.spread / 2)) * DEG;
        const spin = e.spin + signed(e.spinRandom);
        let sx = 0, sy = 0;
        if (e.shape === 'box') {
          if (e.emitFrom === 'edge') {
            const point = boxEdgePoint(e, rand(), rand()); sx = point.x; sy = point.y;
          } else { sx = signed(e.width / 2); sy = signed(e.height / 2); }
        }
        else if (e.shape === 'ring') {
          const point = ringRadiusRand ? sampleRing(rand(), ringRadiusRand()) : sampleRing(rand()); sx = point.x; sy = point.y;
        } else if (e.shape === 'circle') {
          const polar = rand() * TAU, areaRadius = Math.sqrt(rand());
          const radius = e.emitFrom === 'edge' ? 1 : areaRadius;
          sx = Math.cos(polar) * e.width / 2 * radius; sy = Math.sin(polar) * e.height / 2 * radius;
        } else if (e.shape === 'line') {
          const distance = signed(e.lineLength / 2);
          sx = Math.cos(e.lineRotation * DEG) * distance; sy = Math.sin(e.lineRotation * DEG) * distance;
        } else if (e.shape === 'direction') {
          const distance = signed(e.width / 2);
          sx = -Math.sin(e.angle * DEG) * distance; sy = Math.cos(e.angle * DEG) * distance;
        }
        const birth = round(sourceIndex / e.count * Math.min(e.emissionDuration, project.duration));
        clipped = clipped || (birth + life > project.duration);
        const cycles = project.loop ? Math.max(1, Math.ceil((life - EPS) / project.duration)) : 1;
        maxPoolCycles = Math.max(maxPoolCycles, cycles);
        longLived = longLived || (project.loop && life > project.duration);
        generatedParticles++;
        for (let cycleIndex = 0; cycleIndex < cycles; cycleIndex++) {
          particles.push({emitterId: e.id, index: index++, sourceIndex, cycleIndex,
            birth, life, size, spin, sx, sy, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
            ax: e.wind, ay: -e.gravity,
            direction: angle / DEG, emitter: e, lifecycle, startColor: rgb(e.colorStart), endColor: rgb(e.colorEnd)});
        }
        if (particles.length > MAX_POOL) fail('循環粒子池超過 ' + MAX_POOL + ' 個。請減少粒子數、縮短壽命，或增加動畫長度。');
      }
      if (e.emissionDuration > project.duration) warnings.push('「' + e.name + '」發射時間超過動畫長度；本次烘焙採用 ' + project.duration + ' 秒。');
      if (!project.loop && clipped) warnings.push('「' + e.name + '」部分粒子會在動畫結尾截斷。');
      if (e.alphaCurve[e.alphaCurve.length - 1].v !== 0) warnings.push('「' + e.name + '」透明度曲線尾值不為 0；粒子壽命結束時會立即隱藏。');
    });
    if (!particles.length) warnings.push('所有發射器都已停用，輸出動畫只包含 root。');
    if (longLived) warnings.push('壽命超過循環週期的粒子使用分段粒子池；循環畫面連續，部分骨骼在交接點交換角色。動畫混合與中斷尚未驗證。');
    const enabledEmitters = project.emitters.filter(e => e.enabled).length;
    return freezeDeep({project, particles, duration: project.duration, fps: project.fps, loop: project.loop,
      stats: {particles: particles.length, generatedParticles, bones: particles.length + enabledEmitters + 1,
        slots: particles.length, enabledEmitters, poolCycles: maxPoolCycles, fps: project.fps,
        duration: project.duration, warnings}});
  }

  function particleAge(baked, particle, time) {
    if (baked.loop) {
      let phase = mod(time - particle.birth, baked.duration);
      // Arithmetic residues at exact schedule boundaries must resolve to the next cycle.
      if (Math.abs(phase - baked.duration) < EPS || Math.abs(phase) < EPS) phase = 0;
      return phase + particle.cycleIndex * baked.duration;
    }
    return time - particle.birth;
  }

  function bakeFlow(raw) {
    const project = normalizeProject(raw), flow = project.flow;
    const basis = bake(Object.assign({}, project, {duration: flow.loop.duration, loop: true}));
    const phases = {};
    ['in', 'loop', 'out'].forEach(kind => {
      const duration = flow[kind].duration;
      const particles = kind === 'out' ? basis.particles.map(particle => Object.assign({}, particle, {birth: -particleAge(basis, particle, 0)})) : basis.particles;
      const flowPhase = kind === 'in' ? {kind, basis, offset: -duration} : {kind};
      phases[kind] = {project, particles, duration, fps: project.fps, loop: kind === 'loop', flowPhase,
        stats: Object.assign({}, basis.stats, {duration, phase: kind})};
    });
    const stats = Object.assign({}, basis.stats, {duration: round(flow.in.duration + flow.loop.duration + flow.out.duration),
      phaseDurations: {in: flow.in.duration, loop: flow.loop.duration, out: flow.out.duration}});
    return freezeDeep({project, phases, stats});
  }

  function stateAt(baked, particle, time) {
    const e = particle.emitter;
    const flow = baked.flowPhase;
    const age = flow && flow.kind === 'in' ? particleAge(flow.basis, particle, mod(time + flow.offset, flow.basis.duration)) : particleAge(baked, particle, time);
    const alive = age >= -EPS && age < particle.life - EPS && !(flow && flow.kind === 'out' && time >= baked.duration - EPS);
    const evaluatedAge = clamp(age, 0, particle.life);
    const u = evaluatedAge / particle.life;
    const speedCurve = particle.lifecycle.speed;
    const speedU = speedCurve ? curveProgress(e.speedCurve, evaluatedAge, particle.life) : u;
    const travel = speedCurve ? particle.life * speedCurve.integral(speedU) : ease(u, e.motionCurve) * particle.life;
    // Explicit velocity curves only reshape initial motion. Gravity/wind retain
    // their physical age clock; null keeps legacy eased-position behavior intact.
    const forceTime = speedCurve ? evaluatedAge : travel;
    const speedMultiplier = speedCurve ? speedCurve.sample(speedU) : 1;
    const sizeU = curveProgress(e.sizeCurve, evaluatedAge, particle.life), alphaU = curveProgress(e.alphaCurve, evaluatedAge, particle.life);
    const scaleCurve = particle.lifecycle.sizeLinear ? evalCurve(e.sizeCurve, sizeU) : particle.lifecycle.size.sample(sizeU);
    const maxDimension = e.image ? Math.max(e.image.width, e.image.height) : 64;
    const scale = particle.size / maxDimension * scaleCurve;
    const width = (e.image ? e.image.width : 64) * scale;
    const height = (e.image ? e.image.height : 64) * scale;
    let rotation = e.rotation + particle.spin * evaluatedAge;
    if (e.alignDirection) {
      const vx = particle.vx * speedMultiplier + particle.ax * forceTime, vy = particle.vy * speedMultiplier + particle.ay * forceTime;
      const angle = Math.abs(vx) + Math.abs(vy) < EPS ? particle.direction : Math.atan2(vy, vx) / DEG;
      rotation += particle.direction + mod(angle - particle.direction + 180, 360) - 180;
    }
    return {emitterId: particle.emitterId, index: particle.index,
      x: e.x + particle.sx + particle.vx * travel + particle.ax * forceTime * forceTime / 2,
      y: e.y + particle.sy + particle.vy * travel + particle.ay * forceTime * forceTime / 2,
      scale, width, height, rotation,
      color: particle.lifecycle.gradient ? evalGradient(particle.lifecycle.gradient, curveProgress(e.colorGradient, evaluatedAge, particle.life)) : particle.startColor.map((channel, i) => channel + (particle.endColor[i] - channel) * u),
      alpha: alive ? (particle.lifecycle.alphaLinear ? evalCurve(e.alphaCurve, alphaU) : particle.lifecycle.alpha.sample(alphaU)) *
        (flow && flow.kind === 'in' ? clamp(time / baked.duration, 0, 1) : flow && flow.kind === 'out' ? clamp(1 - time / baked.duration, 0, 1) : 1) : 0, blend: e.blend, image: e.image,
      alive};
  }

  function sample(baked, time) {
    if (typeof time !== 'number' || !Number.isFinite(time)) fail('預覽時間必須是有限數值。');
    const t = baked.loop ? mod(time, baked.duration) : clamp(time, 0, baked.duration);
    return baked.particles.map(particle => stateAt(baked, particle, t));
  }

  function sampledTimeline(baked, particle) {
    const duration = baked.duration;
    const times = new Map();
    function add(time, mandatory, stepped) {
      if (time < -EPS || time > duration + EPS) return;
      const t = round(clamp(time, 0, duration));
      const current = times.get(t) || {time: t, mandatory: false, stepped: false};
      current.mandatory = current.mandatory || !!mandatory;
      current.stepped = current.stepped || !!stepped;
      times.set(t, current);
    }
    add(0, true); add(duration, true);
    for (let frame = 1; frame < Math.ceil(duration * baked.fps); frame++) add(frame / baked.fps, false);
    if (baked.flowPhase && baked.flowPhase.kind === 'in') {
      const basis = baked.flowPhase.basis, basisKeys = sampledTimeline(basis, particle);
      const cycles = Math.ceil(duration / basis.duration) + 1;
      for (let cycle = -cycles; cycle <= 0; cycle++) {
        basisKeys.forEach(key => add(duration + cycle * basis.duration + key.time, key.mandatory, key.stepped));
      }
      return Array.from(times.values()).sort((a, b) => a.time - b.time).map(key => ({time: key.time, mandatory: key.mandatory, stepped: key.stepped,
        state: stateAt(baked, particle, key.time)}));
    }
    function event(phase, reset, mandatory) {
      let time = particle.birth + phase;
      if (baked.loop) time = mod(time, duration);
      add(time, mandatory !== false);
      if (reset) {
        const before = time <= EPS && baked.loop ? duration - RESET_EPS : time - RESET_EPS;
        add(before, true, true);
        if (time <= EPS && baked.loop) add(duration, true);
      }
    }
    function lifetimeEvent(t, reset, mandatory) {
      const age = t * particle.life - (baked.loop ? particle.cycleIndex * duration : 0);
      if (!baked.loop || (age >= 0 && age <= duration)) event(age, reset, mandatory);
    }
    const scalarCurves = [particle.emitter.sizeCurve, particle.emitter.alphaCurve];
    if (particle.emitter.speedCurve) scalarCurves.push(particle.emitter.speedCurve);
    if (baked.loop) {
      event(0, true);
      const death = particle.life - particle.cycleIndex * duration;
      if (death >= 0 && death <= duration) event(death, true);
    } else {
      event(0, true); event(particle.life, true);
    }
    scalarCurves.forEach(points => points.forEach((point, index) => lifetimeEvent(point.t, index > 0 && points[index - 1].curve === 'stepped')));
    if (particle.emitter.colorGradient) particle.emitter.colorGradient.forEach(point => lifetimeEvent(point.t, false));
    [particle.lifecycle.size, particle.lifecycle.alpha, particle.lifecycle.speed].forEach(compiled => {
      if (compiled) compiled.sampleTimes.forEach(t => lifetimeEvent(t, false, false));
    });
    return Array.from(times.values()).sort((a, b) => a.time - b.time).map(key => ({
      time: key.time, mandatory: key.mandatory, stepped: key.stepped,
      state: stateAt(baked, particle, key.time)
    }));
  }

  // Error-bounded piecewise linear reduction. Event/stepped boundaries are never removed.
  function reduceTimeline(keys, channels, tolerance) {
    if (keys.length <= 2) return keys;
    const keep = new Set([0, keys.length - 1]);
    keys.forEach((key, i) => { if (key.mandatory || key.stepped) keep.add(i); if (i && keys[i - 1].stepped) keep.add(i); });
    const anchors = Array.from(keep).sort((a, b) => a - b);
    function split(first, last) {
      if (last - first <= 1 || keys[first].stepped) return;
      let greatest = 1, candidate = -1;
      const a = keys[first], b = keys[last], av = channels(a.state), bv = channels(b.state);
      for (let i = first + 1; i < last; i++) {
        const u = (keys[i].time - a.time) / (b.time - a.time);
        const values = channels(keys[i].state);
        let error = 0;
        for (let c = 0; c < values.length; c++) error = Math.max(error, Math.abs(values[c] - (av[c] + (bv[c] - av[c]) * u)) / tolerance[c]);
        if (error > greatest) { greatest = error; candidate = i; }
      }
      if (candidate !== -1) { keep.add(candidate); split(first, candidate); split(candidate, last); }
    }
    for (let i = 1; i < anchors.length; i++) split(anchors[i - 1], anchors[i]);
    return Array.from(keep).sort((a, b) => a - b).map(i => keys[i]);
  }

  function keyframe(key, values) {
    const result = key.time ? {time: key.time} : {};
    Object.keys(values).forEach(channel => { result[channel] = typeof values[channel] === 'number' ? round(values[channel]) : values[channel]; });
    if (key.stepped) result.curve = 'stepped';
    return result;
  }

  function rgba(state) {
    return state.color.concat(state.alpha).map(value => Math.round(clamp(value, 0, 1) * 255).toString(16).padStart(2, '0')).join('');
  }

  function exportSpine(baked, targetVersion) {
    const profile = spineProfile(targetVersion === undefined ? baked.project.spineVersion : targetVersion);
    const json = {
      skeleton: {spine: profile.version, images: './images/', fps: baked.fps},
      bones: [{name: 'root'}], slots: [], skins: [{name: 'default', attachments: {}}],
      animations: {effect: {bones: {}, slots: {}}}
    };
    const images = [], attachments = json.skins[0].attachments;
    let keyframes = 0, denseKeyframes = 0;
    const enabled = baked.project.emitters.filter(e => e.enabled);
    enabled.forEach(e => json.bones.push({name: 'em_' + e.id, parent: 'root', x: e.x, y: e.y}));
    // The first emitter in the editor is the front layer; Spine draws the final slot last.
    enabled.slice().reverse().forEach(e => {
      const imageName = e.image ? 'emitter_' + e.id + '.png' : 'particle.png';
      const path = imageName.slice(0, -4);
      if (!images.some(item => item.name === imageName)) images.push({name: imageName,
        width: e.image ? e.image.width : 64, height: e.image ? e.image.height : 64,
        dataUrl: e.image ? e.image.dataUrl : null});
      baked.particles.filter(particle => particle.emitterId === e.id).forEach(particle => {
        const boneName = 'em_' + e.id + '_p' + particle.index, slotName = boneName + '_slot';
        const initial = stateAt(baked, particle, 0);
        json.bones.push({name: boneName, parent: 'em_' + e.id});
        json.slots.push({name: slotName, bone: boneName, color: rgba(initial),
          attachment: initial.alive ? 'particle' : undefined, blend: e.blend});
        attachments[slotName] = {particle: {type: 'region', path, width: e.image ? e.image.width : 64, height: e.image ? e.image.height : 64}};
        const dense = sampledTimeline(baked, particle);
        denseKeyframes += dense.length * 4;
        const translate = reduceTimeline(dense, s => [s.x, s.y], [0.2, 0.2]).map(key => keyframe(key, {x: key.state.x - e.x, y: key.state.y - e.y}));
        let rotationKeys = reduceTimeline(dense, s => [s.rotation], [0.25]);
        if (profile.family === '3.8') {
          // 3.8 interpolates the shortest angle between keys. Keep each visible
          // rotation segment below 180 degrees so whole turns cannot disappear.
          const guarded = [], denseTimes = new Set(dense.map(key => key.time));
          rotationKeys.forEach((key, index) => {
            guarded.push(key);
            const next = rotationKeys[index + 1];
            if (!next || key.stepped) return;
            const segments = Math.ceil(Math.abs(next.state.rotation - key.state.rotation) / 120);
            for (let step = 1; step < segments; step++) {
              const at = round(key.time + (next.time - key.time) * step / segments);
              if (at <= guarded[guarded.length - 1].time || at >= next.time) continue;
              guarded.push({time: at, state: stateAt(baked, particle, at)});
              if (!denseTimes.has(at)) { denseTimes.add(at); denseKeyframes++; }
            }
          });
          rotationKeys = guarded;
        }
        const rotate = rotationKeys.map(key => keyframe(key, {[profile.rotationKey]: key.state.rotation}));
        const scale = reduceTimeline(dense, s => [s.scale], [0.002]).map(key => keyframe(key, {x: key.state.scale, y: key.state.scale}));
        const colors = reduceTimeline(dense, s => s.color.concat(s.alpha), [1 / 255, 1 / 255, 1 / 255, 0.004]).map(key => keyframe(key, {color: rgba(key.state)}));
        const switches = [];
        let previous;
        dense.forEach(key => {
          const visible = key.state.alive;
          if (previous === undefined || previous !== visible || key.time === baked.duration) {
            switches.push(keyframe({time: key.time}, {name: visible ? 'particle' : null})); previous = visible;
          }
        });
        json.animations.effect.bones[boneName] = {translate, rotate, scale};
        json.animations.effect.slots[slotName] = {[profile.colorTimeline]: colors, attachment: switches};
        denseKeyframes += switches.length;
        keyframes += translate.length + rotate.length + scale.length + colors.length + switches.length;
      });
    });
    if (!baked.particles.length) {
      json.animations.effect.bones.root = {translate: [{x: 0, y: 0}, {time: baked.duration, x: 0, y: 0}]};
      keyframes = denseKeyframes = 2;
    }
    const stats = Object.assign({}, baked.stats, {keyframes, denseKeyframes,
      keyReduction: denseKeyframes ? round(1 - keyframes / denseKeyframes) : 0,
      jsonBytes: 0, imageCount: images.length, resetEpsilon: RESET_EPS,
      reductionTolerance: {position: 0.2, rotation: 0.25, scale: 0.002, alpha: 0.004, color: 1 / 255}});
    stats.jsonBytes = typeof TextEncoder === 'function' ? new TextEncoder().encode(JSON.stringify(json)).length : JSON.stringify(json).length;
    return {json, images, stats};
  }

  function exportFlow(flowBaked, targetVersion) {
    if (!flowBaked || !flowBaked.phases || !flowBaked.project) fail('請先烘焙 In / Loop / Out 三段動畫。');
    const flow = normalizeFlow(flowBaked.project.flow, flowBaked.project.duration), exported = {}, descriptors = {};
    ['in', 'loop', 'out'].forEach(kind => {
      const phase = flowBaked.phases[kind];
      if (!phase || phase.duration !== flow[kind].duration || phase.loop !== (kind === 'loop')) fail('三段動畫烘焙資料與專案設定不一致，請重新烘焙。');
      descriptors[kind] = {animationName: flow[kind].name, duration: phase.duration, loop: phase.loop};
    });
    // Count timestamp metadata without evaluating positions, curves, or tiled
    // In states. The estimate is deliberately conservative where tiled Loop
    // timestamps overlap the In FPS grid; it is not an exact output-key count.
    function timelineCount(phase, particle) {
      const period = phase.duration, times = new Set();
      function add(at) { if (at >= -EPS && at <= period + EPS) times.add(round(clamp(at, 0, period))); }
      add(0); add(period);
      for (let frame = 1; frame < Math.ceil(period * phase.fps); frame++) add(frame / phase.fps);
      function event(age, reset) {
        let at = particle.birth + age;
        if (phase.loop) at = mod(at, period);
        add(at);
        if (reset) add(at <= EPS && phase.loop ? period - RESET_EPS : at - RESET_EPS);
      }
      function lifetimeEvent(t, reset) {
        const age = t * particle.life - (phase.loop ? particle.cycleIndex * period : 0);
        if (!phase.loop || (age >= 0 && age <= period)) event(age, reset);
      }
      event(0, true);
      if (phase.loop) {
        const death = particle.life - particle.cycleIndex * period;
        if (death >= 0 && death <= period) event(death, true);
      } else event(particle.life, true);
      const curves = [particle.emitter.sizeCurve, particle.emitter.alphaCurve];
      if (particle.emitter.speedCurve) curves.push(particle.emitter.speedCurve);
      curves.forEach(points => points.forEach((point, index) => lifetimeEvent(point.t, index > 0 && points[index - 1].curve === 'stepped')));
      if (particle.emitter.colorGradient) particle.emitter.colorGradient.forEach(point => lifetimeEvent(point.t, false));
      [particle.lifecycle.size, particle.lifecycle.alpha, particle.lifecycle.speed].forEach(compiled => {
        if (compiled) compiled.sampleTimes.forEach(t => lifetimeEvent(t, false));
      });
      return times.size;
    }
    const loopPhase = flowBaked.phases.loop, outPhase = flowBaked.phases.out;
    const repeats = Math.ceil(flow.in.duration / loopPhase.duration) + 1;
    const inGrid = Math.ceil(flow.in.duration * loopPhase.fps) + 1, sampleLimit = 2000000;
    let estimatedSamples = 0;
    for (let index = 0; index < loopPhase.particles.length; index++) {
      const loopKeys = timelineCount(loopPhase, loopPhase.particles[index]);
      estimatedSamples += inGrid + loopKeys * repeats + loopKeys + timelineCount(outPhase, outPhase.particles[index]);
      if (estimatedSamples > sampleLimit) fail('三段動畫匯出取樣成本估算超過 200 萬，可能使介面暫停。請減少粒子數、縮短 In，或增加 Loop 長度，再重新匯出。');
    }
    ['in', 'loop', 'out'].forEach(kind => { exported[kind] = exportSpine(flowBaked.phases[kind], targetVersion); });
    const json = Object.assign({}, exported.loop.json, {animations: Object.create(null)});
    json.slots.forEach(slot => { slot.attachment = null; slot.color = 'ffffff00'; });
    ['in', 'loop', 'out'].forEach(kind => { Object.defineProperty(json.animations, flow[kind].name, {
      value: exported[kind].json.animations.effect, enumerable: true, writable: true, configurable: true}); });
    const keyframes = ['in', 'loop', 'out'].reduce((sum, kind) => sum + exported[kind].stats.keyframes, 0);
    const denseKeyframes = ['in', 'loop', 'out'].reduce((sum, kind) => sum + exported[kind].stats.denseKeyframes, 0);
    const warnings = Array.from(new Set(['in', 'loop', 'out'].flatMap(kind => exported[kind].stats.warnings || [])));
    const stats = Object.assign({}, flowBaked.stats, {keyframes, denseKeyframes, keyReduction: denseKeyframes ? round(1 - keyframes / denseKeyframes) : 0,
      imageCount: exported.loop.images.length, resetEpsilon: RESET_EPS, reductionTolerance: exported.loop.stats.reductionTolerance,
      warnings, jsonBytes: typeof TextEncoder === 'function' ? new TextEncoder().encode(JSON.stringify(json)).length : JSON.stringify(json).length});
    return {json, images: exported.loop.images, stats, manifest: {phases: descriptors, transition: 'loop-boundary'}};
  }

  return {createProject, createEmitter, normalizeProject, normalizeFlow, bake, bakeFlow, sample, exportSpine, exportFlow, spineProfile, SPINE_TARGETS};
});
