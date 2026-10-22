(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleLookPresets = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

  // Curve handle X is segment progress; Y is the absolute multiplier/alpha.
  // Flat tangents at authored points make the joins smooth and editable.
  function smooth(values) {
    return values.map((value, index) => {
      const point = {t: value[0], v: value[1]};
      if (index > 0) point.in = {x: 2 / 3, y: point.v};
      if (index + 1 < values.length) {
        point.curve = 'bezier';
        point.out = {x: 1 / 3, y: point.v};
      }
      return point;
    });
  }
  const steady = value => [{t: 0, v: value}, {t: 1, v: value}];
  const gradient = values => values.map(value => ({t: value[0], color: value[1]}));
  const item = (id, label, description, points) => ({id, label, description, points});
  function freeze(value) {
    Object.keys(value).forEach(key => {
      if (value[key] && typeof value[key] === 'object') freeze(value[key]);
    });
    return Object.freeze(value);
  }
  const catalog = freeze({
    color: [
      item('gold', '金色光芒', '暖白 → 金黃 → 橙金，適合金幣、獎勵與亮點。',
        gradient([[0, '#fff8dc'], [.3, '#ffe58a'], [.7, '#ffc13b'], [1, '#e87918']])),
      item('fire', '火焰暖光', '亮黃 → 橙紅 → 暗紅，適合火花與爆發。',
        gradient([[0, '#fff2b0'], [.25, '#ffb83d'], [.65, '#f34b23'], [1, '#841d36']])),
      item('ice', '冰藍閃光', '白 → 冰藍 → 藍紫，適合冰霜與冷光。',
        gradient([[0, '#f1fcff'], [.35, '#8be7ff'], [.75, '#4b99ff'], [1, '#6065d9']])),
      item('mint', '翡翠綠光', '淡黃綠 → 薄荷綠 → 深青綠，適合能量與環繞光。',
        gradient([[0, '#edffc0'], [.35, '#8bf5af'], [.7, '#2dd9ad'], [1, '#109e9c']])),
      item('violet', '紫色魔法', '淡粉 → 紫羅蘭 → 藍紫，適合魔法與稀有獎勵。',
        gradient([[0, '#ffe2fa'], [.3, '#efa1ff'], [.65, '#b95aff'], [1, '#6555dc']])),
      item('rainbow', '彩虹流光', '粉紅 → 金黃 → 綠 → 藍 → 紫，適合彩色慶祝效果。',
        gradient([[0, '#ff7eaf'], [.25, '#ffe17a'], [.5, '#8be7ae'], [.75, '#75caff'], [1, '#b586ff']])),
      item('white', '純白原色', '全程白色乘色，保留粒子 PNG 的原始色彩。',
        gradient([[0, '#ffffff'], [1, '#ffffff']]))
    ],
    alpha: [
      item('steady', '保持透明度', '全程不透明；粒子壽命結束時隱藏。', steady(1)),
      item('fade-out', '柔和淡出', '出生時可見，沿生命週期平滑淡出。', smooth([[0, 1], [1, 0]])),
      item('fade-in-out', '淡入淡出', '先柔和淡入，保持亮度，再淡出。', smooth([[0, 0], [.18, 1], [.72, 1], [1, 0]])),
      item('flash', '短促閃光', '快速亮起並提前淡出，適合火花與閃爍。', smooth([[0, 0], [.08, 1], [.45, 0], [1, 0]])),
      item('delayed-fade', '停留後淡出', '保持可見到生命週期後段，再柔和淡出。', smooth([[0, 1], [.7, 1], [1, 0]])),
      item('pulse', '雙重閃爍', '兩次亮度高峰，出生與死亡時透明。', smooth([[0, 0], [.2, 1], [.48, .18], [.7, 1], [1, 0]]))
    ],
    size: [
      item('steady', '固定大小', '全程 1 倍大小。', steady(1)),
      item('grow', '逐漸放大', '由 0.2 倍平滑放大到 1.4 倍。', smooth([[0, .2], [1, 1.4]])),
      item('shrink', '逐漸縮小', '由 1 倍平滑縮小到 0。', smooth([[0, 1], [1, 0]])),
      item('pop', '彈出回穩', '快速放大到 1.35 倍，再回到 1 倍。', smooth([[0, 0], [.2, 1.35], [.45, 1], [1, 1]])),
      item('breathe', '呼吸縮放', '由 0.75 倍放大到 1.25 倍，再回到 0.75 倍。', smooth([[0, .75], [.5, 1.25], [1, .75]])),
      item('swell-fade', '放大後收束', '由小放大到 1.4 倍，最後縮小消失。', smooth([[0, .15], [.55, 1.4], [1, 0]]))
    ],
    speed: [
      item('constant', '等速移動', '全程 1 倍初始速度，啟用速度曲線。', steady(1)),
      item('accelerate', '逐漸加速', '由 0.2 倍平滑加速到 2 倍。', smooth([[0, .2], [1, 2]])),
      item('decelerate', '逐漸減速', '由 2 倍平滑減速到 0.2 倍。', smooth([[0, 2], [1, .2]])),
      item('launch', '衝出後緩行', '以 2.4 倍速度衝出，前段減速後保持 0.3 倍。', smooth([[0, 2.4], [.35, .3], [1, .3]])),
      item('brake', '緩速煞停', '前半段保持 1 倍速度，後半段減速到 0。', smooth([[0, 1], [.5, 1], [1, 0]])),
      item('pulse', '節奏變速', '在 0.4 倍與 1.6 倍間形成兩次加速。', smooth([[0, .4], [.22, 1.6], [.5, .4], [.76, 1.6], [1, .4]]))
    ]
  });
  const fields = Object.freeze({alpha: 'alphaCurve', size: 'sizeCurve', sizeX: 'sizeCurveX', sizeY: 'sizeCurveY', speed: 'speedCurve'});
  function entries(kind) {
    if (kind === 'sizeX' || kind === 'sizeY') return catalog.size;
    if (typeof kind !== 'string' || !own(catalog, kind)) throw new Error('不支援的生命週期預設類型。');
    return catalog[kind];
  }
  function list(kind) { return clone(entries(kind)); }
  function get(kind, id) {
    const preset = entries(kind).find(entry => entry.id === id);
    return preset ? clone(preset) : null;
  }
  function same(a, b) {
    if (a === b) return true;
    if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every(key => own(b, key) && same(a[key], b[key]));
  }
  function apply(emitter, kind, id) {
    if (!emitter || typeof emitter !== 'object' || Array.isArray(emitter)) throw new Error('套用預設需要有效的發射器。');
    const preset = get(kind, id);
    if (!preset) throw new Error('找不到生命週期預設：' + id);
    const points = preset.points;
    if (kind === 'color') {
      if (same(emitter.colorGradient, points)) return false;
      emitter.colorGradient = points;
    } else {
      const field = fields[kind];
      if (same(emitter[field], points) && (kind !== 'speed' || emitter.inactiveSpeedCurve == null)) return false;
      emitter[field] = points;
      if (kind === 'speed') emitter.inactiveSpeedCurve = null;
    }
    return true;
  }
  return {list, get, apply};
});
