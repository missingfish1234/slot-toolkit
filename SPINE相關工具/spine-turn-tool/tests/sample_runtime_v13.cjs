/* Sample official Spine 4.0 world transforms from JSON or native binary. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const [input, output, sampleFile] = process.argv.slice(2);
assert(input && output, 'Usage: node sample_runtime_v13.cjs skeleton.json|skel output.json [progresses.json]');
const runtime = path.join(__dirname, '..', 'vendor', 'spine-core.js');
const fallback = 'E:/SPINE測試/ghost_spine_4.0.56/tools/node_modules/@esotericsoftware/spine-core/dist/iife/spine-core.js';
const context = { console, Float32Array, Uint16Array, Uint8Array, ArrayBuffer, Math };
vm.createContext(context);
vm.runInContext(fs.readFileSync(fs.existsSync(runtime) ? runtime : fallback, 'utf8'), context);
const spine = context.spine;
const file = path.resolve(input), folder = path.dirname(file);
const descriptor = [file.replace(/\.(json|skel)$/i, '.atlas'), ...fs.readdirSync(folder)
  .filter(n => n.endsWith('.atlas')).map(n => path.join(folder, n))].find(p => fs.existsSync(p));
const atlas = new spine.TextureAtlas(fs.readFileSync(descriptor, 'utf8'));
for (const page of atlas.pages) {
  const png = fs.readFileSync(path.join(folder, page.name));
  const width = png.readUInt32BE(16), height = png.readUInt32BE(20);
  assert.equal(width, page.width); assert.equal(height, page.height);
  page.setTexture({ getImage: () => ({ width, height }), setFilters() {}, setWraps() {} });
}
const loader = new spine.AtlasAttachmentLoader(atlas);
const data = /\.skel$/i.test(file)
  ? new spine.SkeletonBinary(loader).readSkeletonData(new Uint8Array(fs.readFileSync(file)))
  : new spine.SkeletonJson(loader).readSkeletonData(JSON.parse(fs.readFileSync(file, 'utf8')));
const skeleton = new spine.Skeleton(data);
const progresses = sampleFile ? JSON.parse(fs.readFileSync(sampleFile, 'utf8'))
  : Array.from({ length: 241 }, (_, i) => i / 240);
const result = { runtime: 'official Spine 4.0.31', animations: {} };
for (const animation of data.animations) {
  result.animations[animation.name] = { duration: animation.duration, poses: [] };
  for (const progress of progresses) {
    skeleton.setToSetupPose();
    animation.apply(skeleton, -1, animation.duration * progress, false, [], 1,
      spine.MixBlend.replace, spine.MixDirection.mixIn);
    skeleton.updateWorldTransform();
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
        triangles: Array.from(attachment.triangles),
        color: [slot.color.r, slot.color.g, slot.color.b, slot.color.a] };
    }
    result.animations[animation.name].poses.push({ progress, bones, geometry });
  }
}
fs.writeFileSync(output, JSON.stringify(result));
process.stdout.write(JSON.stringify({ output, animations: Object.keys(result.animations),
  samplesPerClip: progresses.length }) + '\n');
