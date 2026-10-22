'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const Core = require('../core.js');
const PathMath = require('../path-math.js');
const Storage = require('../storage.js');
const Zip = require('../zip.js');
const root = path.resolve(__dirname, '..');
const stem = 'bezier-paths';
const editorVersion = require('../package.json').version.replace(/\.0$/, '');

function example() {
  const project = Core.createProject();
  Object.assign(project, {name: '少量節點 · 貝茲移動路徑', duration: 3, bakeQuality: 'standard',
    flow: {enabled: true, in: {name: 'in', duration: 1}, loop: {name: 'loop', duration: 3}, out: {name: 'out', duration: 1}}});
  const bytes = fs.readFileSync(path.join(root, 'examples/images/particle.png'));
  const image = {name: 'particle.png', mime: 'image/png', width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20),
    dataUrl: 'data:image/png;base64,' + bytes.toString('base64')};
  const shapes = [
    {id: 'ellipse', label: '橢圓 · 4 個節點', count: 4, x: -190, y: 110, color: '#ffd56a', end: '#ff975c'},
    {id: 'figure8', label: '8 字型 · 8 個節點', count: 8, x: 190, y: 110, color: '#8de6ff', end: '#48a3ff'},
    {id: 's', label: 'S 型 · 5 個節點', count: 5, x: -190, y: -110, color: '#9dffd9', end: '#44c6ac'},
    {id: 'spiral', label: '螺旋 · 9 個節點', count: 9, x: 190, y: -110, color: '#e0adff', end: '#aa66ef'}
  ];
  project.emitters = shapes.map((shape, index) => {
    const emitter = Core.createEmitter('bezier_' + shape.id, shape.label);
    Object.assign(emitter, {image: {...image}, x: shape.x, y: shape.y, shape: 'point', count: 16, emissionDuration: 3,
      life: 3, lifeRandom: 0, speed: 0, speedRandom: 0, gravity: 0, wind: 0,
      size: 8, sizeRandom: 0, spin: 0, spinRandom: 0, alignDirection: true,
      colorStart: shape.color, colorEnd: shape.end,
      sizeCurve: [{t: 0, v: .75}, {t: .16, v: 1}, {t: 1, v: .75}],
      alphaCurve: [{t: 0, v: 0}, {t: .08, v: 1}, {t: .88, v: 1}, {t: 1, v: 0}],
      path: {...PathMath.defaults(), ...PathMath.preset(shape.id, index === 3 ? 200 : 220, 140),
        enabled: true, mode: 'lifetime', offsets: false}});
    assert.equal(emitter.path.points.length, shape.count, shape.label);
    assert.ok(emitter.path.points.some(point => point.in || point.out), '曲線包含貝茲控制柄');
    return emitter;
  });
  return Core.normalizeProject(project);
}

function guide(version) {
  return '少量節點 · 貝茲移動路徑示範\n\n' +
    '用粒子工作室 v' + editorVersion + ' 開啟 ' + stem + '.particle.json，即可預覽四種曲線的粒子動畫。\n' +
    '左上：橢圓 4 點；右上：8 字型 8 點；左下：S 型 5 點；右下：兩圈螺旋 9 點。\n' +
    '選擇發射器，於「運動」面板開啟「編輯移動路徑」。拖曳節點調整位置，拖曳藍色控制柄調整曲線。\n' +
    '中間節點預設平衡兩側控制柄；按住 Ctrl 可單獨調整一側。8 字型中央重疊的節點可用「選取節點」分別選取。\n' +
    '舊折線路徑不會自動變更；需要減少點數時，可在路徑編輯視窗按「精簡為貝茲」。\n' +
    '所有 PNG 都已內嵌於粒子專案，不需要另外載入素材。修改後請重新烘焙、匯出。\n\n' +
    'Spine ' + version + '：以 Import Data 載入 ' + stem + '.json，Images 指向 images/。\n' +
    '先播放 in（1 秒），接 loop（3 秒，可循環），在完整 Loop 結束後接 out（1 秒）。\n' +
    '路徑與粒子朝向已烘焙成骨骼關鍵幀，遊戲端不需要另外計算移動路徑。\n';
}

function main() {
  const project = example(), flow = Core.bakeFlow(project);
  const saved = Storage.serialize(project, flow.phases.loop.project,
    {mode: 'baked', phase: 'loop', time: .8, zoom: .8, panX: 0, panY: 0});
  const parsed = Storage.parse(saved, Core);
  assert.deepEqual(parsed.project.emitters.map(emitter => emitter.path.points.length), [4, 8, 5, 9]);
  assert.ok(parsed.project.emitters.every(emitter => /^data:image\/png;base64,/.test(emitter.image.dataUrl)));
  fs.writeFileSync(path.join(root, 'examples', stem + '.particle.json'), saved);
  for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
    const output = Core.exportFlow(flow, version), family = Core.spineProfile(version).family;
    assert.equal(output.json.skeleton.spine, version);
    assert.deepEqual(Object.keys(output.json.animations), ['in', 'loop', 'out']);
    assert.ok(Object.values(output.json.animations).every(animation => Object.keys(animation.bones || {}).length > 0));
    const entries = [{name: stem + '.json', data: JSON.stringify(output.json)},
      {name: stem + '.particle.json', data: saved},
      {name: '動畫段落.json', data: JSON.stringify(output.manifest, null, 2)},
      {name: '匯入說明.txt', data: guide(version)}];
    for (const asset of output.images) {
      assert.ok(asset.dataUrl, '輸出素材必須使用內嵌 PNG');
      entries.push({name: 'images/' + asset.name, data: Zip.decodeDataUrl(asset.dataUrl)});
    }
    assert.ok(entries.some(entry => entry.name.startsWith('images/')));
    const zip = Zip.create(entries), outputPath = path.join(root, 'examples', stem + '_spine' + family + '.zip');
    fs.writeFileSync(outputPath, zip);
    const bytes = fs.readFileSync(outputPath);
    assert.equal(bytes.readUInt32LE(0), 0x04034b50);
    assert.equal(bytes.readUInt32LE(bytes.length - 22), 0x06054b50);
    assert.equal(bytes.readUInt16LE(bytes.length - 12), entries.length);
  }
  process.stdout.write('Built sparse Bezier project (4 / 8 / 5 / 9 anchors) + 3 Spine export examples\n');
}
if (require.main === module) main();
module.exports = {example, main};
