'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const Core = require('../core');
const PathMath = require('../path-math');
const Preview = require('../preview');
const Storage = require('../storage');
const Zip = require('../zip');
const {png} = require('./path-outline-examples');
const ROOT = path.resolve(__dirname, '..'), STEM = 'path-facing';

// A geometric, right-facing texture makes the authored tangent visible. Four
// samples per axis keep the small arrow readable at ordinary preview scales.
function arrowImage() {
  const width = 64, height = 32, rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    let coverage = 0;
    for (let yy = 0; yy < 4; yy++) for (let xx = 0; xx < 4; xx++) {
      const px = x + (xx + .5) / 4, py = y + (yy + .5) / 4;
      const shaft = px >= 5 && px <= 36 && py >= 11 && py <= 21;
      const head = px >= 34 && px <= 60 && Math.abs(py - 16) <= (60 - px) * 13 / 26;
      if (shaft || head) coverage++;
    }
    if (coverage) rgba.set([255, 255, 255, Math.round(coverage / 16 * 255)], (y * width + x) * 4);
  }
  const bytes = png(width, height, rgba);
  return {bytes, image: {name: 'path-arrow.png', mime: 'image/png', width, height,
    dataUrl: 'data:image/png;base64,' + bytes.toString('base64')}};
}

function example() {
  const project = Core.createProject(), {image} = arrowImage();
  Object.assign(project, {name: '沿路徑轉向 · 箭頭示範', duration: 4, fps: 30, loop: true,
    bakeQuality: 'standard', seed: 42});
  project.flow.enabled = false;
  project.emitters = [
    {id: 'facing_ellipse', name: '橢圓 · 沿路徑轉向', kind: 'ellipse', x: -185, count: 8,
      width: 260, height: 180, color: '#8af3cf', reverse: false},
    {id: 'facing_reverse', name: 'S 型 · 反向轉向', kind: 's', x: 185, count: 6,
      width: 260, height: 150, color: '#ffcb72', reverse: true}
  ].map(shape => Object.assign(Core.createEmitter(shape.id, shape.name), {
    image: {...image}, shape: 'point', x: shape.x, y: 0,
    count: shape.count, emissionDuration: 4, life: 4, lifeRandom: 0,
    speed: 0, speedRandom: 0, gravity: 0, wind: 0, spread: 0,
    size: 28, sizeRandom: 0, rotation: 0, spin: 0, spinRandom: 0,
    alignDirection: true, blend: 'normal', colorStart: shape.color, colorEnd: shape.color,
    sizeCurve: [{t: 0, v: 1}, {t: 1, v: 1}],
    alphaCurve: [{t: 0, v: 0}, {t: .025, v: 1}, {t: .975, v: 1}, {t: 1, v: 0}],
    path: {...PathMath.defaults(), ...PathMath.preset(shape.kind, shape.width, shape.height),
      enabled: true, mode: 'lifetime', offsets: false, reverse: shape.reverse}
  }));
  return Core.normalizeProject(project);
}

function angleError(a, b) {
  const radians = (a - b) * Math.PI / 180;
  return Math.abs(Math.atan2(Math.sin(radians), Math.cos(radians))) * 180 / Math.PI;
}

function verifyFacing(project, baked) {
  assert.equal(baked.particles.length, 14, 'The orientation example stays lightweight');
  assert(project.emitters.every(emitter => emitter.alignDirection && emitter.rotation === 0 &&
    emitter.spin === 0 && emitter.spinRandom === 0 && emitter.image.name === 'path-arrow.png'));
  const orbit = baked.particles.find(particle => particle.emitterId === 'facing_ellipse');
  assert.equal(orbit.lifecycle.path.totalTurn, 360, 'The orbit retains a whole turn');
  const reverse = baked.particles.find(particle => particle.emitterId === 'facing_reverse');
  assert(reverse.lifecycle.path.sample(0).x > reverse.lifecycle.path.sample(1).x,
    'The second route really travels from right to left');
  let samples = 0;
  for (const time of [.173, .731, 1.583, 2.719, 3.819]) {
    const previous = Core.sample(baked, time - .0001), current = Core.sample(baked, time), next = Core.sample(baked, time + .0001);
    current.forEach((state, i) => {
      if (state.alpha < .99) return;
      const dx = next[i].x - previous[i].x, dy = next[i].y - previous[i].y;
      assert(Math.hypot(dx, dy) > 0, 'Arrow must travel along its route');
      assert(angleError(state.rotation, Math.atan2(dy, dx) * 180 / Math.PI) < .02,
        'The right-facing arrow points along independently measured displacement');
      samples++;
    });
  }
  assert(samples >= 60, 'Both routes were checked at distinct particle ages');
}

function guide(version) {
  return '沿路徑轉向 · 箭頭示範\n\n' +
    '用粒子工作室開啟 ' + STEM + '.particle.json，即可播放 4 秒循環。所有 PNG 已內嵌，無須另載素材。\n' +
    '左側綠色箭頭沿橢圓移動，右側金色箭頭沿 S 型由右往左移動；箭頭會跟隨彎曲方向轉向。\n' +
    '選取發射器，在「運動」→「沿路徑移動」取消／勾選「沿路徑方向轉向」，即可比較固定朝向與跟隨轉向。\n' +
    '本例的原始箭頭朝右，因此「轉向偏移」為 0°。若自己的貼圖原本朝上，可改為 −90° 校正。\n' +
    '要完全跟隨路徑，請將旋轉速度與旋轉隨機設為 0；本例已完成設定。\n' +
    '可在路徑編輯視窗切換「反向前進」，箭頭會跟隨新的移動方向。修改後請重新烘焙、匯出。\n\n' +
    'Spine ' + version + '：使用 Import Data 載入 ' + STEM + '.json，Images 指向 images/，循環播放 effect。\n' +
    '位移與朝向皆已烘焙為骨骼關鍵幀；箭頭貼圖保留 path-arrow.png 原檔名，分層資料夾用於避免同名衝突。\n';
}

function main() {
  const project = example(), baked = Core.bake(project);
  verifyFacing(project, baked);
  const saved = Storage.serialize(project, baked.project, {mode: 'live', time: 1.13, zoom: 1, panX: 0, panY: 0});
  assert.deepEqual(Storage.parse(saved, Core).project, project, 'Embedded arrows and orientation settings survive save/load');
  fs.writeFileSync(path.join(ROOT, 'examples/images/path-arrow.png'), arrowImage().bytes);
  fs.writeFileSync(path.join(ROOT, 'examples', STEM + '.particle.json'), saved);
  for (const version of ['3.8.99', '4.0.56', '4.2.43']) {
    const output = Core.exportSpine(baked, version), replay = Preview.compile(output, baked), family = Core.spineProfile(version).family;
    assert.equal(output.json.skeleton.spine, version);
    assert(output.images.every(image => path.posix.basename(image.name) === 'path-arrow.png'), 'Original arrow filenames are retained');
    const track = output.json.animations.effect.bones.em_facing_ellipse_p0.rotate;
    const angles = track.map(key => key.angle === undefined ? key.value : key.angle);
    assert(Math.max(...angles) - Math.min(...angles) > 350, 'Whole-turn rotation is present in ' + version);
    for (const time of [.173, .731, 1.583, 2.719, 3.819]) {
      const expected = Core.sample(baked, time).filter(state => state.alive && state.alpha > .1), actual = replay.sample(time);
      assert.equal(actual.length, baked.particles.length, 'Every arrow has an exported attachment');
      for (const state of expected) {
        const slot = 'em_' + state.emitterId + '_p' + state.index + '_slot', found = actual.find(candidate => candidate.slotName === slot);
        assert(found && angleError(found.rotation, state.rotation) < .8, 'Three-version playback keeps forward and reverse headings');
        assert(Math.hypot(found.x - state.x, found.y - state.y) < .5, 'Heading does not disturb exported route position');
      }
    }
    const entries = [{name: STEM + '.json', data: JSON.stringify(output.json)},
      {name: STEM + '.particle.json', data: saved}, {name: '匯入說明.txt', data: guide(version)}];
    for (const image of output.images) entries.push({name: 'images/' + image.name, data: Zip.decodeDataUrl(image.dataUrl)});
    const bytes = Buffer.from(Zip.create(entries));
    assert.equal(bytes.readUInt32LE(0), 0x04034b50);
    assert.equal(bytes.readUInt32LE(bytes.length - 22), 0x06054b50);
    assert.equal(bytes.readUInt16LE(bytes.length - 12), entries.length);
    fs.writeFileSync(path.join(ROOT, 'examples', STEM + '_spine' + family + '.zip'), bytes);
  }
  process.stdout.write('Built two visible arrow routes (14 particles, forward ellipse + reverse S) + 3 Spine exports\n');
}

if (require.main === module) main();
module.exports = {example, arrowImage, main};
