'use strict';
// Original vector-like raster frames generated locally; no borrowed artwork.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const Core = require('../core'), Storage = require('../storage'), Zip = require('../zip');
const {png} = require('./path-outline-examples');
const ROOT = path.resolve(__dirname, '..'), STEM = 'sequence-particles';

function frameImage(index, count = 8) {
  const width = 72, height = 72, rgba = new Uint8ClampedArray(width * height * 4), phase = index / count;
  const radius = 10 + phase * 22;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const dx = x + .5 - width / 2, dy = y + .5 - height / 2, r = Math.hypot(dx, dy), angle = Math.atan2(dy, dx);
    const ring = Math.exp(-Math.pow((r - radius) / (2.5 + phase * 1.2), 2));
    const rays = Math.pow(Math.max(0, Math.cos(angle * 8 - phase * 2.2)), 10) * Math.exp(-Math.pow((r - radius + 6) / 9, 2));
    const center = Math.exp(-r * r / 25) * (1 - phase);
    const alpha = Math.min(1, ring * (1 - phase * .7) + rays * .65 + center);
    const at = (y * width + x) * 4;
    rgba.set([Math.round(100 + 140 * center), Math.round(225 + 30 * center), 255, Math.round(alpha * 255)], at);
  }
  const bytes = png(width, height, rgba);
  return {name: 'energy_' + String(index + 1).padStart(2, '0') + '.png', mime: 'image/png', width, height,
    dataUrl: 'data:image/png;base64,' + bytes.toString('base64')};
}
function example() {
  const p = Core.createProject();
  Object.assign(p, {name: '連續圖 · 循環與播完停格', duration: 2, fps: 30, seed: 7417,
    flow: {enabled: true, in: {name: 'in', duration: .8}, loop: {name: 'loop', duration: 2}, out: {name: 'out', duration: 1}}});
  const frames = Array.from({length: 8}, (_, i) => frameImage(i));
  p.emitters = ['loop', 'once'].map((mode, index) => {
    const e = Core.createEmitter('sequence_' + mode, index ? '播完停格 · 24 FPS' : '循環播放 · 12 FPS');
    Object.assign(e, {x: index ? 115 : -115, y: 0, shape: 'point', count: 8, emissionDuration: 2,
      life: 1.3, lifeRandom: 0, speed: 22, speedRandom: 0, angle: 90, spread: 90,
      size: 82, sizeRandom: 5, spin: 0, spinRandom: 0, gravity: 0, wind: 0,
      colorStart: index ? '#ffd491' : '#a6ffff', colorEnd: index ? '#ff883b' : '#41b0ff',
      alphaCurve: [{t: 0, v: 0}, {t: .08, v: 1}, {t: .82, v: 1}, {t: 1, v: 0}],
      sizeCurve: [{t: 0, v: .7}, {t: .22, v: 1}, {t: 1, v: .8}],
      sequence: {enabled: true, fps: index ? 24 : 12, mode, frames: frames.map(frame => ({...frame}))}});
    return e;
  });
  return Core.normalizeProject(p);
}
function guide(version) {
  return '連續圖粒子示範\n\n用粒子工作室 v' + require('../package.json').version.replace(/\.0$/, '') +
    ' 開啟 ' + STEM + '.particle.json。\n左側 8 張圖以 12 FPS 循環；右側以 24 FPS 播完後停在最後一張。\n' +
    '於「外觀」的「粒子貼圖」選擇「連續圖」，可調整連續圖 FPS 與播放方式。每顆粒子出生後，從第 1 張開始播放。\n' +
    '專案內已包含全部 PNG。連續圖 FPS 控制換圖速度；上方專案 FPS 控制骨骼動態烘焙頻率，兩者可分開調整。\n\n' +
    'Spine ' + version + '：使用 Import Data 載入 ' + STEM + '.json，Images 指向 images/。\n' +
    '依序播放 in（0.8 秒）、loop（2 秒，可循環）、out（1 秒）。\n' +
    '輸出採一般 Region Attachment 與插槽附件換圖關鍵幀，可用於 Spine 3.8、4.0、4.2。\n';
}
function main() {
  const p = example(), flow = Core.bakeFlow(p), saved = Storage.serialize(p, flow.phases.loop.project,
    {mode: 'baked', phase: 'loop', time: .55, zoom: 1.2, panX: 0, panY: 0});
  assert.equal(Storage.parse(saved, Core).project.emitters[0].sequence.frames.length, 8);
  fs.writeFileSync(path.join(ROOT, 'examples', STEM + '.particle.json'), saved);
  for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
    const output = Core.exportFlow(flow, version);
    assert.equal(output.images.length, 16, '每組發射器都輸出完整的 8 張連續圖');
    const entries = [{name: STEM + '.json', data: JSON.stringify(output.json)}, {name: STEM + '.particle.json', data: saved},
      {name: '動畫段落.json', data: JSON.stringify(output.manifest, null, 2)}, {name: '匯入說明.txt', data: guide(version)}];
    for (const image of output.images) entries.push({name: 'images/' + image.name, data: Zip.decodeDataUrl(image.dataUrl)});
    fs.writeFileSync(path.join(ROOT, 'examples', STEM + '_spine' + Core.spineProfile(version).family + '.zip'), Zip.create(entries));
  }
  process.stdout.write('Built embedded 8-frame particle sequence example (12 / 24 FPS) + 3 Spine exports\n');
}
if (require.main === module) main();
module.exports = {frameImage, example, main};
