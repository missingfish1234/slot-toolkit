'use strict';
const fs = require('node:fs');
const path = require('node:path');
const Core = require('../core.js');
const Presets = require('../look-presets.js');
const Storage = require('../storage.js');
const Zip = require('../zip.js');
const root = path.resolve(__dirname, '..');
function main() {
  const project = Core.createProject(); project.name = '配色與生命曲線預設'; project.flow.enabled = true;
  const bytes = fs.readFileSync(path.join(root, 'examples/images/particle.png'));
  const image = {name: 'particle.png', mime: 'image/png', width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20), dataUrl: 'data:image/png;base64,' + bytes.toString('base64')};
  const combinations = [
    ['gold', '金光 · 彈出與淡入淡出', 'fade-in-out', 'pop', 'launch'],
    ['ice', '冰藍 · 呼吸與雙重閃爍', 'pulse', 'breathe', 'pulse'],
    ['mint', '翡翠 · 放大後收束', 'delayed-fade', 'swell-fade', 'accelerate'],
    ['violet', '紫光 · 縮小與柔和淡出', 'fade-out', 'shrink', 'brake']
  ];
  project.emitters = combinations.map(([color, name, alpha, size, speed], index) => {
    const emitter = Core.createEmitter('preset_' + color, name);
    Object.assign(emitter, {image, x: -300 + index * 200, y: 0, shape: 'ring', width: 90, height: 90, emitFrom: 'edge', directionMode: 'radial', count: 16, life: 1.8, lifeRandom: .2, size: 15, sizeRandom: 3, speed: 34, speedRandom: 6, gravity: 0, wind: 0});
    for (const [kind, id] of Object.entries({color, alpha, size, speed})) Presets.apply(emitter, kind, id);
    return emitter;
  });
  const normalized = Core.normalizeProject(project);
  const saved = Storage.serialize(normalized, null, {mode: 'live', phase: 'loop', time: .8, zoom: .65, panX: 0, panY: 0});
  fs.writeFileSync(path.join(root, 'examples/lifetime-presets.particle.json'), saved);
  const baked = Core.bakeFlow(normalized);
  for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
    const output = Core.exportFlow(baked, version), family = Core.spineProfile(version).family;
    const entries = [{name: 'lifetime-presets.json', data: JSON.stringify(output.json)}, {name: 'lifetime-presets.particle.json', data: saved},
      {name: '動畫段落.json', data: JSON.stringify(output.manifest, null, 2)},
      {name: '配色曲線示範.txt', data: '配色與生命曲線預設示範 · Spine ' + version + '\n\n四個發射器分別搭配金色、冰藍、翡翠與紫色，並組合不同透明度、尺寸和速度預設。\n在外觀與運動面板先選預設、按套用，再拖曳節點與貝茲微調。修改後請重新烘焙。\nSpine JSON 搭配 images 匯入；先播放 IN、循環 LOOP，再於循環邊界接 OUT。\n'}];
    output.images.forEach(asset => entries.push({name: 'images/' + asset.name, data: Zip.decodeDataUrl(asset.dataUrl)}));
    fs.writeFileSync(path.join(root, 'examples/lifetime-presets_spine' + family + '.zip'), Zip.create(entries));
  }
  process.stdout.write('Built lifetime presets project + 3 Spine export examples\n');
}
if (require.main === module) main();
module.exports = {main};
