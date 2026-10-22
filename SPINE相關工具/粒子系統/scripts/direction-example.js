'use strict';
const fs = require('node:fs');
const path = require('node:path');
const Core = require('../core');
const Storage = require('../storage');
const Zip = require('../zip');
const {objectImage} = require('./path-outline-examples');
const root = path.resolve(__dirname, '..');
function main() {
  const project = Core.createProject(); project.name = '方向示範 · 中心與輪廓向外'; project.duration = 3;
  project.flow = {enabled: true, in: {name: 'in', duration: .6}, loop: {name: 'loop', duration: 3}, out: {name: 'out', duration: .7}};
  const circle = Core.createEmitter('radialCircle', '圓形 · 中心向外'), outline = Core.createEmitter('normalOutline', 'PNG · 輪廓法線'), box = Core.createEmitter('normalBox', '矩形 · 四邊向外');
  for (const e of [circle, outline, box]) Object.assign(e, {count: 30, emissionDuration: 3, life: 1.5, lifeRandom: 0, speed: 55, speedRandom: 0, size: 8, sizeRandom: 2, spread: 360, directionSpread: 0, spin: 0, spinRandom: 0, width: 130, height: 130, emitFrom: 'edge'});
  Object.assign(circle, {x: -260, shape: 'circle', directionMode: 'radial', colorStart: '#9ee9ff', colorEnd: '#41a6e8'});
  Object.assign(outline, {shape: 'outline', directionMode: 'normal', outline: {...objectImage().outline, includeHoles: true}, colorStart: '#abfff0', colorEnd: '#64ddc2'});
  Object.assign(box, {x: 260, shape: 'box', directionMode: 'normal', colorStart: '#ffe3a2', colorEnd: '#f1a74b'});
  project.emitters = [circle, outline, box];
  const flow = Core.bakeFlow(project), saved = Storage.serialize(project, flow.phases.loop.project, {mode: 'baked', phase: 'loop', time: .8, zoom: 1, panX: 0, panY: 0}), stem = 'emission-directions';
  fs.writeFileSync(path.join(root, 'examples', stem + '.particle.json'), saved);
  for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
    const exported = Core.exportFlow(flow, version), guide = project.name + '\n\nParticle Studio v1.11 使用「開啟」載入 ' + stem + '.particle.json。\n左側圓形從中心向外，中間 PNG 沿輪廓法線向透明區發射，右側矩形沿四邊垂直向外。\n可切換發射方向比較；原散射角360°保留，新模式使用獨立方向散射0°。\n\nSpine ' + version + ' 使用 Import Data 載入 ' + stem + '.json，Images 指向 images/。先播放 in，再循環 loop，於完整一輪結束後播放 out。\nPNG 參考物件不含於 Spine 粒子素材。\n';
    const entries = [{name: stem + '.json', data: JSON.stringify(exported.json)}, {name: stem + '.particle.json', data: saved}, {name: '匯入說明.txt', data: guide}, {name: '動畫段落.json', data: JSON.stringify(exported.manifest, null, 2)}];
    for (const image of exported.images) entries.push({name: 'images/' + image.name, data: image.dataUrl ? Zip.decodeDataUrl(image.dataUrl) : fs.readFileSync(path.join(root, 'assets/particle.png'))});
    fs.writeFileSync(path.join(root, 'examples', stem + '_spine' + Core.spineProfile(version).family + '.zip'), Zip.create(entries));
  }
  process.stdout.write('Built emission-directions project + 3 Spine export examples\n');
}
if (require.main === module) main();
module.exports = {main};
