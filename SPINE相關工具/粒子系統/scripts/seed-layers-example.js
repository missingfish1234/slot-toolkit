'use strict';
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const Core = require('../core'), Storage = require('../storage'), Zip = require('../zip');
const ROOT = path.resolve(__dirname, '..'), STEM = 'seed-layers';
function example() {
  const p = Core.createProject(), bytes = fs.readFileSync(path.join(ROOT, 'examples/images/particle.png'));
  Object.assign(p, {name: '隨機種子 · 同物件三層變化', duration: 2.4, fps: 30, seed: 42,
    flow: {enabled: true, in: {name: 'in', duration: 1}, loop: {name: 'loop', duration: 2.4}, out: {name: 'out', duration: 2}}});
  const basis = Core.createEmitter('seed_back', '第 1 層 · 種子 137');
  Object.assign(basis, {x: 0, y: -35, shape: 'ring', emitFrom: 'area', width: 250, height: 140,
    count: 12, emissionDuration: 2.4, life: 1.8, lifeRandom: .5, speed: 32, speedRandom: 24, angle: 90, spread: 80,
    size: 20, sizeRandom: 11, rotation: 0, spin: 0, spinRandom: 30, colorStart: '#fff5cf', colorEnd: '#ffb445',
    image: {name: 'particle.png', mime: 'image/png', width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20), dataUrl: 'data:image/png;base64,' + bytes.toString('base64')},
    alphaCurve: [{t: 0, v: 0}, {t: .14, v: .9}, {t: .72, v: .7}, {t: 1, v: 0}],
    sizeCurve: [{t: 0, v: .4}, {t: .3, v: 1}, {t: 1, v: .2}]});
  p.emitters = [137, 2718, 9142].map((randomSeed, i) => ({...JSON.parse(JSON.stringify(basis)),
    id: ['seed_back', 'seed_middle', 'seed_front'][i], name: '第 ' + (i + 1) + ' 層 · 種子 ' + randomSeed, randomSeed}));
  return Core.normalizeProject(p);
}
function guide(version) {
  return '隨機種子分層示範\n\n開啟 ' + STEM + '.particle.json。\n三組發射器的位置、範圍、數量、顏色、速度與尺寸設定完全一致，只更改各自的隨機種子。\n' +
    '種子分別為 137、2718、9142，因此初始位置與原有隨機範圍內的速度／尺寸／壽命變化會不同，形成疊加層次。\n' +
    '在「發射」頁籤的「隨機變化」可選擇「自訂此發射器」，輸入種子或按「換一組」。\n' +
    '複製後會保留自訂種子；相同參數與種子可重現相同粒子表演。選擇「跟隨專案」則依上方專案種子自動分組。\n' +
    '種子只改變已啟用的隨機變化；如果發射位置、方向、速度、尺寸、壽命皆固定，改變種子可能沒有差異。\n\n' +
    'Spine ' + version + '：使用 Import Data 載入 ' + STEM + '.json，Images 指向 images/。\n' +
    '依序播放 in（1 秒）、loop（2.4 秒，可循環）、out（2 秒）。\n';
}
function main() {
  const p = example(), flow = Core.bakeFlow(p), saved = Storage.serialize(p, flow.phases.loop.project,
    {mode: 'live', phase: 'loop', time: .81, zoom: 1.6, panX: 0, panY: 0});
  assert.deepEqual(Storage.parse(saved, Core).project.emitters.map(e => e.randomSeed), [137, 2718, 9142]);
  fs.writeFileSync(path.join(ROOT, 'examples', STEM + '.particle.json'), saved);
  for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
    const output = Core.exportFlow(flow, version), entries = [{name: STEM + '.json', data: JSON.stringify(output.json)},
      {name: STEM + '.particle.json', data: saved}, {name: '動畫段落.json', data: JSON.stringify(output.manifest, null, 2)}, {name: '匯入說明.txt', data: guide(version)}];
    for (const image of output.images) entries.push({name: 'images/' + image.name, data: Zip.decodeDataUrl(image.dataUrl)});
    fs.writeFileSync(path.join(ROOT, 'examples', STEM + '_spine' + Core.spineProfile(version).family + '.zip'), Zip.create(entries));
  }
  process.stdout.write('Built three copied emitter layers with independent seeds 137 / 2718 / 9142 + 3 Spine exports\n');
}
if (require.main === module) main();
module.exports = {example, main};
