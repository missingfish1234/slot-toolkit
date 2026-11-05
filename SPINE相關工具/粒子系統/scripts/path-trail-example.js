'use strict';
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const Core = require('../core'), PathMath = require('../path-math'), Storage = require('../storage');
const {png} = require('./path-outline-examples');
const {arrowImage} = require('./path-facing-example');
const ROOT = path.resolve(__dirname, '..');

function ribbonImage() {
  const width = 128, height = 32, pixels = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const edge = Math.max(0, 1 - Math.abs(y + .5 - height / 2) / (height / 2));
    const cap = Math.min(1, (x + .5) / 8, (width - x - .5) / 8);
    pixels.set([255, 255, 255, Math.round(Math.pow(edge, 1.3) * cap * 255)], (y * width + x) * 4);
  }
  const bytes = png(width, height, pixels);
  return {name: 'path-ribbon.png', mime: 'image/png', width, height, dataUrl: 'data:image/png;base64,' + bytes.toString('base64')};
}

function example(mode) {
  assert(['stretch', 'afterimage'].includes(mode));
  const p = Core.createProject();
  Object.assign(p, {name: mode === 'stretch' ? '沿路徑拉伸 · 彎曲光帶' : '殘影拖尾 · 箭頭淡出',
    duration: 3, fps: 30, loop: false, bakeQuality: 'fine'});
  p.flow.enabled = false;
  const e = Core.createEmitter('path_trail_' + mode, mode === 'stretch' ? '彎曲光帶' : '箭頭殘影');
  Object.assign(e, {image: mode === 'stretch' ? ribbonImage() : arrowImage().image,
    x: 0, y: 0, shape: 'point', count: 1, startDelay: .2, emissionDuration: 0,
    life: 1.8, lifeRandom: 0, size: mode === 'stretch' ? 40 : 34, sizeRandom: 0,
    speed: 0, speedRandom: 0, gravity: 0, wind: 0, spread: 0,
    rotation: 0, spin: 0, spinRandom: 0, alignDirection: true,
    blend: mode === 'stretch' ? 'additive' : 'normal',
    colorStart: mode === 'stretch' ? '#a5fff1' : '#e2c4ff',
    colorEnd: mode === 'stretch' ? '#45b8ff' : '#a78bfa',
    sizeCurve: [{t: 0, v: 1}, {t: 1, v: 1}],
    alphaCurve: [{t: 0, v: 0}, {t: .04, v: 1}, {t: .88, v: 1}, {t: 1, v: 0}],
    path: {...PathMath.defaults(), ...PathMath.preset('s', 440, 180), enabled: true, mode: 'lifetime', offsets: false},
    trail: {enabled: true, mode, duration: .65, samples: 12, segments: 24, opacity: .75, width: 1.2, taper: .85}});
  p.emitters = [e];
  return Core.normalizeProject(p);
}

function verify(project, baked) {
  const trail = project.emitters[0].trail;
  assert(trail && trail.enabled, 'The current Core must preserve trail settings before examples are generated');
  assert.equal(project.duration, 3); assert.equal(project.loop, false);
  assert.equal(project.emitters[0].count, 1, 'Examples stay lightweight');
  assert(Core.sample(baked, 1.25).some(state => state.alpha > .1), 'The moving effect is visible');
  assert(Core.sample(baked, 2.3).some(state => state.alpha > .001), 'The tail remains visible after the head dies at 2 seconds');
  assert(Core.sample(baked, 2.8).every(state => state.alpha === 0), 'The complete tail fades before the project ends');
}

function main() {
  for (const mode of ['stretch', 'afterimage']) {
    const project = example(mode), baked = Core.bake(project); verify(project, baked);
    const saved = Storage.serialize(project, null, {mode: 'live', time: 1.25, zoom: 1.15, panX: 0, panY: 0});
    assert.deepEqual(Storage.parse(saved, Core).project, project, 'Project save/load preserves the editable route and tail');
    fs.writeFileSync(path.join(ROOT, 'examples/path-trail-' + mode + '.particle.json'), saved, 'utf8');
  }
  process.stdout.write('Built two lightweight S-path trail projects with visible post-life fade\n');
}
if (require.main === module) main();
module.exports = {example, ribbonImage, verify, main};
