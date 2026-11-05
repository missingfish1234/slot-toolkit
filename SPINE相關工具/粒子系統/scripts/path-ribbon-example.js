'use strict';
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const Core = require('../core'), PathMath = require('../path-math'), Storage = require('../storage');
const {png} = require('./path-outline-examples');
const ROOT = path.resolve(__dirname, '..');

function smoothStep(value) {
  const t = Math.max(0, Math.min(1, value));
  return t * t * (3 - 2 * t);
}

function ribbonImage() {
  const width = 48, height = 112;
  const pixels = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    const along = (y + .5) / height;
    const tipFade = smoothStep(Math.min(along, 1 - along) * 12);
    const radius = .8 + .2 * Math.sin(Math.PI * along);
    for (let x = 0; x < width; x++) {
      const across = Math.abs(2 * (x + .5) / width - 1) / radius;
      const distanceSquared = across * across;
      const core = Math.exp(-32 * distanceSquared);
      const glow = Math.exp(-5 * distanceSquared);
      const edgeFade = 1 - smoothStep((across - .72) / .28);
      const alpha = tipFade * edgeFade * Math.min(1, .87 * core + .5 * glow);
      pixels.set([24 + 210 * core, 136 + 110 * core, 255, 255 * alpha], (y * width + x) * 4);
    }
  }
  const bytes = png(width, height, pixels);
  return {name: 'path-ribbon-blue.png', mime: 'image/png', width, height,
    dataUrl: 'data:image/png;base64,' + bytes.toString('base64')};
}

function example() {
  const p = Core.createProject();
  Object.assign(p, {name: '整條路徑光帶', duration: 3, fps: 30, loop: false, bakeQuality: 'fine',
    background: {color: '#0b111c', image: null, x: 0, y: 0, scale: 1}});
  p.flow.enabled = false;
  const e = Core.createEmitter('path_ribbon', '整條路徑光帶');
  Object.assign(e, {image: ribbonImage(), x: 0, y: 0, shape: 'point', count: 1,
    startDelay: 0, emissionDuration: 0, life: 2.5, lifeRandom: 0, size: 72, sizeRandom: 0,
    speed: 0, speedRandom: 0, gravity: 0, wind: 0, spread: 0, rotation: 0, spin: 0, spinRandom: 0,
    alignDirection: true, blend: 'additive', colorStart: '#ffffff', colorEnd: '#ffffff',
    sizeCurve: [{t: 0, v: 1}, {t: 1, v: 1}],
    alphaCurve: [{t: 0, v: 0}, {t: .08, v: 1}, {t: .9, v: 1}, {t: 1, v: 0}],
    path: {...PathMath.defaults(), ...PathMath.preset('s', 420, 130), enabled: true, mode: 'lifetime', offsets: false},
    trail: {enabled: true, mode: 'stretch', duration: .4, samples: 8, segments: 32, opacity: 1,
      width: 1, taper: 0, coverage: 'path', showHead: false, axis: 'y', flipTexture: false}});
  p.emitters = [e];
  return Core.normalizeProject(p);
}

function verify(project, baked) {
  const e = project.emitters[0];
  assert.equal(project.emitters.length, 1); assert.equal(e.count, 1);
  assert.equal(project.duration, 3); assert.equal(project.loop, false);
  assert.equal(e.trail.coverage, 'path'); assert.equal(e.trail.showHead, false);
  assert.equal(e.trail.axis, 'y'); assert.equal(e.trail.flipTexture, false);
  assert.equal(e.colorStart, '#ffffff'); assert.equal(e.colorEnd, '#ffffff');
  assert.deepEqual(e.image, ribbonImage(), 'The sample uses the generated texture');
  const route = PathMath.compile(e.path), start = route.sample(0), end = route.sample(1);
  for (const time of [.25, 1.2]) {
    const states = Core.sample(baked, time);
    const visible = states.filter(state => state.alpha > .001);
    assert.equal(visible.length, 1, 'A single continuous ribbon is visible, without a separate head sprite');
    const ribbon = visible[0];
    assert(ribbon.isTrail && ribbon.type === 'mesh');
    const vertices = ribbon.vertices, rows = e.trail.segments + 1;
    const center = row => ({x: (vertices[row * 2] + vertices[(rows * 2 - 1 - row) * 2]) / 2,
      y: (vertices[row * 2 + 1] + vertices[(rows * 2 - 1 - row) * 2 + 1]) / 2});
    const a = center(0), b = center(rows - 1);
    assert(Math.hypot(a.x - start.x, a.y - start.y) < 1e-6, 'The ribbon starts at the beginning of the path');
    assert(Math.hypot(b.x - end.x, b.y - end.y) < 1e-6, 'The ribbon reaches the end of the path before the head travels there');
    assert(Math.abs(b.x - a.x) >= 419, 'The full 420px S path is covered');
  }
  assert(Core.sample(baked, 2.95).every(state => state.alpha === 0), 'The ribbon fades before the non-looping project ends');
}

function writeExample(project, check, filename, time) {
  check(project, Core.bake(project));
  const saved = Storage.serialize(project, null, {mode: 'live', time, zoom: 1.15, panX: 0, panY: 0});
  assert.deepEqual(Storage.parse(saved, Core).project, project, 'Saving preserves the editable example and its generated PNG');
  fs.writeFileSync(path.join(ROOT, 'examples', filename), saved, 'utf8');
}

function main() {
  writeExample(example(), verify, 'path-ribbon.particle.json', 1.2);
  process.stdout.write('Built a continuous S-path ribbon with a generated blue texture\n');
}

function examplePulse() {
  const p = example(), e = p.emitters[0];
  Object.assign(p, {name: '光帶先長再短', duration: 2.6});
  Object.assign(e, {id: 'path_ribbon_length', name: '光帶先長再短', life: 2,
    alphaCurve: [{t: 0, v: 1}, {t: 1, v: 1}]});
  e.trail.lengthCurve = [{t: 0, v: .15}, {t: .4, v: 1}, {t: 1, v: .05}];
  return Core.normalizeProject(p);
}

function verifyPulse(project, baked) {
  const e = project.emitters[0], route = PathMath.compile(e.path), start = route.sample(0);
  assert.equal(e.life, 2); assert.equal(e.count, 1); assert.equal(project.loop, false);
  assert.deepEqual(e.trail.lengthCurve, [{t: 0, v: .15}, {t: .4, v: 1}, {t: 1, v: .05}]);
  assert.deepEqual(e.image, ribbonImage(), 'The length animation uses the generated texture');
  let previousWidth = null;
  for (const [time, fraction] of [[0, .15], [.8, 1], [2, .05]]) {
    const visible = Core.sample(baked, time).filter(state => state.alpha > .001);
    assert.equal(visible.length, 1, 'Only the length-animated ribbon is visible');
    const ribbon = visible[0], rows = e.trail.segments + 1, vertices = ribbon.vertices;
    assert(ribbon.isTrail && ribbon.type === 'mesh');
    const center = row => ({x: (vertices[row * 2] + vertices[(rows * 2 - 1 - row) * 2]) / 2,
      y: (vertices[row * 2 + 1] + vertices[(rows * 2 - 1 - row) * 2 + 1]) / 2});
    const a = center(0), b = center(rows - 1), end = route.sample(fraction);
    assert(Math.hypot(a.x - start.x, a.y - start.y) < 1e-3, 'The ribbon grows and shrinks from the same path origin');
    assert(Math.hypot(b.x - end.x, b.y - end.y) < 1e-3, 'The length curve controls the covered fraction of the path');
    const width = Math.hypot(vertices[0] - vertices[vertices.length - 2], vertices[1] - vertices[vertices.length - 1]);
    if (previousWidth !== null) assert(Math.abs(width - previousWidth) < 1e-6, 'Changing length preserves ribbon width');
    previousWidth = width;
    const verticalUVs = ribbon.uvs.filter((_, index) => index % 2);
    assert.equal(Math.min(...verticalUVs), 0); assert.equal(Math.max(...verticalUVs), 1);
  }
  assert(Core.sample(baked, 2.5).every(state => state.alpha === 0), 'The short ribbon finishes fading before the project ends');
}

function mainPulse() {
  writeExample(examplePulse(), verifyPulse, 'path-ribbon-length.particle.json', .8);
  process.stdout.write('Built an S-path ribbon that grows from 15% to 100% then shrinks to 5%\n');
}

function exampleComet() {
  const p = example(), e = p.emitters[0];
  Object.assign(p, {name: '彗星撞擊', duration: 1});
  Object.assign(e, {id: 'path_comet_impact', name: '彗星撞擊', life: .65, size: 52,
    alphaCurve: [{t: 0, v: 1}, {t: .98, v: 1}, {t: 1, v: 0}],
    path: {...PathMath.defaults(), ...PathMath.preset('s', 360, 120), enabled: true, mode: 'lifetime', offsets: false}});
  Object.assign(e.trail, {coverage: 'history', showHead: true, duration: .2, taper: .8,
    moveDuration: .5, lengthDuration: .65,
    lengthCurve: [{t: 0, v: .15}, {t: .5 / .65, v: 2.5}, {t: 1, v: 0}]});
  return Core.normalizeProject(p);
}

function verifyComet(project, baked) {
  const e = project.emitters[0], end = PathMath.compile(e.path).sample(1);
  assert.equal(e.life, .65); assert.equal(e.count, 1); assert.equal(project.duration, 1); assert.equal(project.loop, false);
  assert.equal(e.trail.moveDuration, .5); assert.equal(e.trail.lengthDuration, .65);
  assert.equal(e.trail.showHead, true); assert.equal(e.trail.coverage, 'history');
  assert.deepEqual(e.image, ribbonImage(), 'The comet uses the generated texture');
  const ribbonLength = ribbon => {
    const vertices = ribbon.vertices, rows = vertices.length / 4;
    let previous = null, length = 0;
    for (let row = 0; row < rows; row++) {
      const point = {x: (vertices[row * 2] + vertices[(rows * 2 - 1 - row) * 2]) / 2,
        y: (vertices[row * 2 + 1] + vertices[(rows * 2 - 1 - row) * 2 + 1]) / 2};
      if (previous) length += Math.hypot(point.x - previous.x, point.y - previous.y);
      previous = point;
    }
    return length;
  };
  const lengths = [];
  for (const time of [.5, .6]) {
    const visible = Core.sample(baked, time).filter(state => state.alpha > .001);
    const heads = visible.filter(state => !state.isTrail), tails = visible.filter(state => state.isTrail);
    assert.equal(heads.length, 1); assert.equal(tails.length, 1);
    assert(Math.hypot(heads[0].x - end.x, heads[0].y - end.y) < 1e-6,
      'The head reaches the path end at .5 seconds and stays there while its tail shrinks');
    lengths.push(ribbonLength(tails[0]));
  }
  assert(lengths[0] > 300, 'The comet leaves a long tail by the moment it arrives');
  assert(lengths[1] < lengths[0] * .5, 'The tail keeps shrinking after the head stops');
  for (const time of [.65, .9]) assert(Core.sample(baked, time).every(state => state.alpha === 0),
    'The tail and head are both invisible when shrink completion is reached');
}

function mainComet() {
  writeExample(exampleComet(), verifyComet, 'path-comet-impact.particle.json', .5);
  process.stdout.write('Built a comet that arrives at .5s and finishes shrinking at .65s\n');
}
if (require.main === module) {
  main();
  mainPulse();
  mainComet();
}
module.exports = {example, ribbonImage, verify, main, examplePulse, verifyPulse, mainPulse, exampleComet, verifyComet, mainComet};
