'use strict';
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const Core = require('../core'), Curve = require('../curve-math'), PathMath = require('../path-math');
const Storage = require('../storage'), Preview = require('../preview'), Zip = require('../zip');
const {png} = require('./path-outline-examples');
const ROOT = path.resolve(__dirname, '..'), STEM = 'size-axes';

// Deliberately non-square art makes unequal scaling obvious without relying on
// downloaded images or requiring a separate asset-loading step.
function shapeImage(kind = 'bar') {
  const width = 80, height = 36, rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    let inside;
    if (kind === 'arrow') inside = (x >= 5 && x <= 45 && y >= 12 && y < 24) || (x >= 38 && x <= 75 && Math.abs(y - 18) <= (75 - x) * .43);
    else inside = x >= 6 && x < 74 && y >= 8 && y < 28 && (x >= 12 && x < 68 || Math.abs(y - 18) < 4);
    if (inside) rgba.set([255, 255, 255, 255], (y * width + x) * 4);
  }
  const bytes = png(width, height, rgba);
  return {bytes, image: {name: 'size-' + kind + '.png', mime: 'image/png', width, height, dataUrl: 'data:image/png;base64,' + bytes.toString('base64')}};
}
function curves() {
  return {
    sizeCurveX: [{t: 0, v: .55, curve: 'bezier', out: {x: .25, y: .55}},
      {t: .24, v: 1.8, in: {x: .7, y: 1.8}, curve: 'bezier', out: {x: .3, y: 1.8}},
      {t: .64, v: .42, in: {x: .7, y: .42}, curve: 'bezier', out: {x: .3, y: .42}}, {t: 1, v: 1, in: {x: .7, y: 1}}],
    sizeCurveY: [{t: 0, v: 1.5, curve: 'bezier', out: {x: .3, y: 1.5}},
      {t: .32, v: .5, in: {x: .7, y: .5}, curve: 'bezier', out: {x: .3, y: .5}},
      {t: .7, v: 1.75, in: {x: .7, y: 1.75}, curve: 'bezier', out: {x: .3, y: 1.75}}, {t: 1, v: 1, in: {x: .7, y: 1}}]
  };
}
function example() {
  const p = Core.createProject(); Object.assign(p, {name: '分軸縮放 · 拉伸與壓扁', duration: 3, fps: 30, loop: true, bakeQuality: 'fine'}); p.flow.enabled = false;
  p.emitters = [
    {id: 'squash_bar', name: '綠色 · X 拉長／Y 壓扁', x: -210, kind: 'bar', rotation: 0, color: '#8af3cf'},
    {id: 'stretch_bar', name: '金色 · 旋轉後沿各自軸變形', x: 0, kind: 'bar', rotation: 35, color: '#ffcb72'},
    {id: 'facing_arrow', name: '紫色 · 沿路徑轉向＋分軸變形', x: 210, kind: 'arrow', rotation: 0, color: '#c6a0ff'}
  ].map((s, index) => {
    const e = Core.createEmitter(s.id, s.name);
    Object.assign(e, {image: shapeImage(s.kind).image, shape: 'point', x: s.x, y: 0, count: index === 2 ? 3 : 1,
      emissionDuration: index === 2 ? 2.8 : 0, life: 3, lifeRandom: 0, speed: 0, speedRandom: 0, spread: 0,
      gravity: 0, wind: 0, size: index === 2 ? 47 : 80, sizeRandom: 0, rotation: s.rotation, spin: 0, spinRandom: 0,
      alignDirection: index === 2, blend: 'normal', colorStart: s.color, colorEnd: s.color,
      alphaCurve: [{t: 0, v: 0}, {t: .025, v: 1}, {t: .975, v: 1}, {t: 1, v: 0}],
      sizeCurve: [{t: 0, v: .5}, {t: .35, v: 1.1}, {t: 1, v: .5}], separateSizeAxes: true, ...curves()});
    if (index === 1) [e.sizeCurveX, e.sizeCurveY] = [e.sizeCurveY, e.sizeCurveX];
    if (index === 2) e.path = {...PathMath.defaults(), ...PathMath.preset('ellipse', 155, 120), enabled: true, mode: 'lifetime', offsets: false};
    return e;
  });
  return Core.normalizeProject(p);
}
function verify(p, baked) {
  assert.equal(baked.particles.length, 5, 'The example stays lightweight');
  assert(p.emitters.every(e => e.separateSizeAxes && e.image.width !== e.image.height));
  const states = Core.sample(baked, .9), first = states.find(s => s.emitterId === 'squash_bar');
  const e = p.emitters[0], x = Curve.compile(e.sizeCurveX, 4).sample(.3), y = Curve.compile(e.sizeCurveY, 4).sample(.3);
  assert(Math.abs(first.width - e.image.width * x) < 1e-8 && Math.abs(first.height - e.image.height * y) < 1e-8, 'Each dimension follows its own Bezier curve');
  assert(first.width / e.image.width > first.height / e.image.height * 2, 'The initial preview has an obvious squash/stretch silhouette');
}
function guide(version) {
  return '分軸縮放 · 拉伸與壓扁\n\n開啟 ' + STEM + '.particle.json，預覽 3 秒循環；所有素材已內嵌。\n' +
    '「外觀」→「生命期間的曲線」→開啟「分別調整 X／Y」，可獨立編輯兩條尺寸倍率曲線。\n' +
    '綠色長條先橫向拉長，再轉為直向拉伸；金色長條旋轉 35°，兩條曲線與綠色互換；紫色箭頭同時沿橢圓轉向與變形。\n' +
    '曲線以貼圖本身的 X／Y 軸為準，會跟著粒子旋轉。預設共用倍率；切回共用時，會恢復原本保留的共用曲線。\n' +
    '每條曲線都能套用預設、拖曳節點、調整貝茲控制柄；按 Ctrl 可單獨調整一邊。\n' +
    '示範只使用 5 個粒子，貼圖為自製非正方形幾何圖；請重新烘焙後匯出自己的調整。\n\n' +
    'Spine ' + version + '：用 Import Data 匯入 ' + STEM + '.json，Images 指向 images/，循環播放 effect。\n' +
    '位移、轉向與 X／Y 尺寸皆已轉換為骨骼關鍵幀，保留 PNG 原檔名。\n';
}
function main() {
  const p = example(), baked = Core.bake(p); verify(p, baked);
  const saved = Storage.serialize(p, baked.project, {mode: 'live', time: .9, zoom: 1.1, panX: 0, panY: 0});
  assert.deepEqual(Storage.parse(saved, Core).project, p, 'Both authored axis curves survive save/load');
  for (const kind of ['bar', 'arrow']) fs.writeFileSync(path.join(ROOT, 'examples/images/size-' + kind + '.png'), shapeImage(kind).bytes);
  fs.writeFileSync(path.join(ROOT, 'examples/' + STEM + '.particle.json'), saved);
  for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
    const out = Core.exportSpine(baked, version), replay = Preview.compile(out, baked);
    const track = out.json.animations.effect.bones.em_squash_bar_p0.scale;
    assert(track.some(k => Math.abs(k.x - k.y) > .8), 'Distinct X/Y scale keys exported for ' + version);
    for (const time of [.173, .713, 1.211, 1.917, 2.719]) for (const state of Core.sample(baked, time).filter(s => s.alpha > .1)) {
      const got = replay.sample(time).find(s => s.slotName === 'em_' + state.emitterId + '_p' + state.index + '_slot');
      assert(got && Math.abs(got.width - state.width) < .22 && Math.abs(got.height - state.height) < .22, 'Three-version playback retains squash/stretch dimensions');
    }
    const entries = [{name: STEM + '.json', data: JSON.stringify(out.json)}, {name: STEM + '.particle.json', data: saved}, {name: '匯入說明.txt', data: guide(version)}];
    for (const im of out.images) entries.push({name: 'images/' + im.name, data: Zip.decodeDataUrl(im.dataUrl)});
    const bytes = Buffer.from(Zip.create(entries)); assert.equal(bytes.readUInt32LE(0), 0x04034b50);
    fs.writeFileSync(path.join(ROOT, 'examples/' + STEM + '_spine' + Core.spineProfile(version).family + '.zip'), bytes);
  }
  process.stdout.write('Built X/Y Bezier squash/stretch with 5 non-square particles + 3 Spine exports\n');
}
if (require.main === module) main();
module.exports = {example, shapeImage, curves, main};
