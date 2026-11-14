/* Sample version-matched official 3.8/4.0/4.2 JSON or native binary. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const [input, output, sampleFile, requestedFamily] = process.argv.slice(2);
assert(input && output, 'Usage: node sample_runtime_v13.cjs skeleton.json|skel output.json [progresses.json]');
const file = path.resolve(input), folder = path.dirname(file);
const family = requestedFamily || JSON.parse(fs.readFileSync(file, 'utf8')).skeleton.spine.split('.').slice(0, 2).join('.');
const runtimeRoot = path.resolve(__dirname, '..', '..', 'artifacts', 'spine-turn-build', 'compat-runtimes');
const runtimes = {
  '3.8': path.join(runtimeRoot, 'spine38-core.js'),
  '4.0': path.join(runtimeRoot, 'node_modules', 'spine40', 'dist', 'iife', 'spine-core.js'),
  '4.2': path.join(runtimeRoot, 'node_modules', 'spine42', 'dist', 'iife', 'spine-core.js'),
};
const runtime = runtimes[family];
assert(runtime && fs.existsSync(runtime), 'Version-matched official runtime not available.');
const context = { console, Float32Array, Uint16Array, Uint8Array, ArrayBuffer, Math };
vm.createContext(context);
vm.runInContext(fs.readFileSync(runtime, 'utf8'), context);
const spine = context.spine;
const descriptor = [file.replace(/\.(json|skel)$/i, '.atlas'), ...fs.readdirSync(folder)
  .filter(n => n.endsWith('.atlas')).map(n => path.join(folder, n))].find(p => fs.existsSync(p));
function texture(name) {
  const png = fs.readFileSync(path.join(folder, name));
  const width = png.readUInt32BE(16), height = png.readUInt32BE(20);
  return { getImage: () => ({ width, height }), setFilters() {}, setWraps() {} };
}
const atlas = family === '3.8'
  ? new spine.TextureAtlas(fs.readFileSync(descriptor, 'utf8'), texture)
  : new spine.TextureAtlas(fs.readFileSync(descriptor, 'utf8'));
if (family !== '3.8') for (const page of atlas.pages) {
  const resource = texture(page.name);
  assert.equal(resource.getImage().width, page.width); assert.equal(resource.getImage().height, page.height);
  page.setTexture(resource);
}
const loader = new spine.AtlasAttachmentLoader(atlas);
const data = /\.skel$/i.test(file)
  ? new spine.SkeletonBinary(loader).readSkeletonData(new Uint8Array(fs.readFileSync(file)))
  : new spine.SkeletonJson(loader).readSkeletonData(JSON.parse(fs.readFileSync(file, 'utf8')));
const skeleton = new spine.Skeleton(data);
assert(String(data.version).startsWith(family + '.'), 'Wrong-family skeleton data was loaded.');
if (process.argv[6]) {
  const timelines = {};
  for (const animation of data.animations) {
    timelines[animation.name] = animation.timelines.filter(t => t instanceof spine.DeformTimeline)
      .map(t => ({ slot: data.slots[t.slotIndex].name, attachment: t.attachment.name,
        frames: Array.from(t.frames), frameVertices: (t.frameVertices || t.vertices).map(v => Array.from(v)) }));
  }
  fs.writeFileSync(process.argv[6], JSON.stringify(timelines));
}
const progresses = sampleFile ? JSON.parse(fs.readFileSync(sampleFile, 'utf8'))
  : Array.from({ length: 241 }, (_, i) => i / 240);
const result = { atlas_pages: atlas.pages.map(p => ({name:p.name,width:p.width,height:p.height})), atlas_regions: atlas.regions.map(r => ({name:r.name,page:r.page.name,x:r.x,y:r.y,width:r.width,height:r.height,degrees:r.degrees || (r.rotate ? 90 : 0)})), runtime: 'official Spine family ' + family, data_version: data.version,
  authoring_fps: data.fps, animations: {} };
for (const animation of data.animations.filter(a => a.name === 'rotate_loop')) {
  result.animations[animation.name] = { duration: animation.duration, poses: [] };
  for (const progress of progresses) {
    skeleton.setToSetupPose();
    animation.apply(skeleton, -1, animation.duration * progress, false, [], 1,
      spine.MixBlend.replace, spine.MixDirection.mixIn);
    if (spine.Physics) skeleton.updateWorldTransform(spine.Physics.update);
    else skeleton.updateWorldTransform();
    const bones = {};
    for (const bone of skeleton.bones) {
      bones[bone.data.name] = { x: bone.x, y: bone.y, scale_x: bone.scaleX, scale_y: bone.scaleY,
        world_x: bone.worldX, world_y: bone.worldY, a: bone.a, b: bone.b, c: bone.c, d: bone.d };
      for (const value of Object.values(bones[bone.data.name])) assert(Number.isFinite(value));
    }
    const geometry = {};
    for (const slot of skeleton.drawOrder) {
      const attachment = slot.getAttachment();
      if (!attachment) continue;
      assert(attachment instanceof spine.MeshAttachment);
      const vertices = new Float32Array(attachment.worldVerticesLength);
      attachment.computeWorldVertices(slot, 0, vertices.length, vertices, 0, 2);
      assert(Array.from(vertices).every(Number.isFinite));
      geometry[slot.data.name] = { name: attachment.name, path: attachment.path,
        vertices: Array.from(vertices), uvs: Array.from(attachment.regionUVs),
        triangles: Array.from(attachment.triangles), atlas_uvs: Array.from(attachment.uvs), atlas_page: atlas.findRegion(attachment.path).page.name,
        color: [slot.color.r, slot.color.g, slot.color.b, slot.color.a],
        blend_mode: slot.data.blendMode };
    }
    result.animations[animation.name].poses.push({ progress, bones, geometry });
  }
}
fs.writeFileSync(output, JSON.stringify(result));
process.stdout.write(JSON.stringify({ output, animations: Object.keys(result.animations),
  samplesPerClip: progresses.length }) + '\n');
