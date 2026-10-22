'use strict';
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const Core = require('../core');
const PathMath = require('../path-math');
const ContourMath = require('../contour-math');
const Storage = require('../storage');
const Zip = require('../zip');
const root = path.resolve(__dirname, '..');
const editorVersion = require('../package.json').version.replace(/\.0$/, '');
function png(width, height, rgba) {
  const chunk = (name, data) => { const tag = Buffer.from(name), length = Buffer.alloc(4), crc = Buffer.alloc(4); length.writeUInt32BE(data.length); crc.writeUInt32BE(Zip.crc32(Buffer.concat([tag, data]))); return Buffer.concat([length, tag, data, crc]); };
  const header = Buffer.alloc(13); header.writeUInt32BE(width); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 6;
  const rows = Buffer.alloc(height * (width * 4 + 1));
  for (let y = 0; y < height; y++) Buffer.from(rgba.buffer, rgba.byteOffset + y * width * 4, width * 4).copy(rows, y * (width * 4 + 1) + 1);
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(rows)), chunk('IEND', Buffer.alloc(0))]);
}
function objectImage() {
  const width = 160, height = 160, data = new Uint8ClampedArray(width * height * 4);
  const polygon = Array.from({length: 10}, (_, i) => { const angle = -Math.PI / 2 + i * Math.PI / 5, radius = i % 2 ? 37 : 70; return {x: 80 + Math.cos(angle) * radius, y: 80 + Math.sin(angle) * radius}; });
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) { const a = polygon[i], b = polygon[j]; if ((a.y > y + .5) !== (b.y > y + .5) && x + .5 < (b.x - a.x) * (y + .5 - a.y) / (b.y - a.y) + a.x) inside = !inside; }
    if (inside && Math.hypot(x + .5 - 80, y + .5 - 80) > 13) { const at = (y * width + x) * 4; data.set([43, 81, 89, 255], at); }
  }
  const bytes = png(width, height, data), image = {name: 'outline-object.png', mime: 'image/png', width, height, dataUrl: 'data:image/png;base64,' + bytes.toString('base64')};
  const outline = ContourMath.scan({width, height, data, sourceName: image.name}); outline.image = image;
  return {bytes, outline};
}
function examples() {
  const orbit = Core.createProject(); orbit.name = '沿路徑 · 矩形與橢圓'; orbit.duration = 3;
  orbit.flow = {enabled: true, in: {name: 'in', duration: 1}, loop: {name: 'loop', duration: 3}, out: {name: 'out', duration: 1}};
  const box = orbit.emitters[0]; Object.assign(box, {name: '矩形光串', count: 36, emissionDuration: 3, life: 3, lifeRandom: 0, size: 11, sizeRandom: 2,
    colorStart: '#a2fff0', colorEnd: '#4dbaad', path: {...PathMath.defaults(), ...PathMath.preset('rectangle', 440, 240), enabled: true}});
  const circle = Core.createEmitter('circlePath', '橢圓 · 反向'); Object.assign(circle, {count: 22, emissionDuration: 3, life: 3, lifeRandom: 0, size: 8, sizeRandom: 0,
    colorStart: '#ffd1a7', colorEnd: '#ff9852', path: {...PathMath.defaults(), ...PathMath.preset('ellipse', 320, 160), enabled: true, reverse: true}});
  orbit.emitters.push(circle);
  const {bytes, outline} = objectImage(), contour = Core.createProject(); contour.name = '物件輪廓 · 五角星與內孔'; contour.duration = 2;
  Object.assign(contour.emitters[0], {name: 'PNG 邊界發射', shape: 'outline', emitFrom: 'edge', outline: {...outline, includeHoles: true}, width: 320, height: 320,
    count: 120, emissionDuration: 2, life: 2, lifeRandom: 0, speed: 0, speedRandom: 0, size: 9, sizeRandom: 2, colorStart: '#abfff0', colorEnd: '#64ddc2'});
  const follow = Core.createProject(); follow.name = '沿物件外型 · 五角星光串'; follow.duration = 3;
  follow.flow = {enabled: true, in: {name: 'in', duration: 1}, loop: {name: 'loop', duration: 3}, out: {name: 'out', duration: 1}};
  Object.assign(follow.emitters[0], {name: '沿 PNG 外型移動', shape: 'point', outline, width: 320, height: 320,
    count: 24, emissionDuration: 3, life: 3, lifeRandom: 0, size: 9, sizeRandom: 0, spin: 0, spinRandom: 0,
    colorStart: '#b3ffec', colorEnd: '#53baa5', alignDirection: true,
    path: {...PathMath.defaults(), ...ContourMath.toPath(outline, 320, 320), enabled: true}});
  return {projects: [['motion-path', orbit], ['object-outline', contour], ['outline-motion', follow]], bytes};
}
function main() {
  const {projects, bytes} = examples(); fs.writeFileSync(path.join(root, 'examples/images/outline-object.png'), bytes);
  for (const [stem, project] of projects) {
    const flow = project.flow && project.flow.enabled ? Core.bakeFlow(project) : null, baked = flow ? flow.phases.loop : Core.bake(project);
    const saved = Storage.serialize(project, baked.project, {mode: 'baked', time: .8, zoom: 1, panX: 0, panY: 0, ...(flow ? {phase: 'loop'} : {})});
    fs.writeFileSync(path.join(root, 'examples', stem + '.particle.json'), saved);
    for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
      const output = flow ? Core.exportFlow(flow, version) : Core.exportSpine(baked, version);
      const guide = project.name + '\n\n用粒子工作室 v' + editorVersion + ' 開啟 ' + stem + '.particle.json。\nSpine ' + version + ' 使用 Import Data 載入 ' + stem + '.json，Images 指向 images/。\n' + (flow ? '先播放 in，再循環 loop，於 loop 完整結束後播放 out。\n' : '播放 effect；請勾選循環。\n') + '路徑／物件輪廓已烘焙為骨骼關鍵幀，無須遊戲端額外控制。輪廓參考 PNG 僅用於工具預覽，不包含在 Spine 粒子貼圖中。\n';
      const entries = [{name: stem + '.json', data: JSON.stringify(output.json)}, {name: stem + '.particle.json', data: saved}, {name: '匯入說明.txt', data: guide}];
      if (flow) entries.push({name: '動畫段落.json', data: JSON.stringify(output.manifest, null, 2)});
      for (const image of output.images) entries.push({name: 'images/' + image.name, data: image.dataUrl ? Zip.decodeDataUrl(image.dataUrl) : fs.readFileSync(path.join(root, 'assets/particle.png'))});
      fs.writeFileSync(path.join(root, 'examples', stem + '_spine' + Core.spineProfile(version).family + '.zip'), Zip.create(entries));
    }
    process.stdout.write('Built ' + stem + ' project + 3 Spine export examples\n');
  }
}
if (require.main === module) main();
module.exports = {examples, objectImage, png, main};
