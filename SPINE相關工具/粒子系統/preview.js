(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticlePreview = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const DEG = Math.PI / 180;
  const mod = (value, period) => ((value % period) + period) % period;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const fail = message => { throw new Error(message); };
  const finite = (value, fallback, label) => {
    if (value === undefined) return fallback;
    if (typeof value !== 'number' || !Number.isFinite(value)) fail(label + '必須是有限數值。');
    return value;
  };

  function rgba(value, fallback) {
    if (value === undefined) return fallback.slice();
    if (typeof value !== 'string' || !/^[0-9a-f]{8}$/i.test(value)) fail('Spine RGBA 色碼必須是八碼十六進位文字。');
    return [0, 2, 4, 6].map(offset => parseInt(value.slice(offset, offset + 2), 16) / 255);
  }

  function numericTrack(keys, fields, defaults, colors) {
    if (keys === undefined) return null;
    if (!Array.isArray(keys)) fail('Spine 動畫軌格式不正確。');
    const times = [], values = [], steps = [];
    keys.forEach((key, index) => {
      if (!key || typeof key !== 'object') fail('Spine 關鍵幀格式不正確。');
      const time = finite(key.time, 0, 'Spine 關鍵幀時間');
      if (time < 0 || (index && time <= times[index - 1])) fail('Spine 關鍵幀時間必須嚴格遞增。');
      if (key.curve !== undefined && key.curve !== 'stepped') fail('烘焙預覽僅支援 linear 與 stepped 曲線。');
      times.push(time);
      values.push(colors ? rgba(key.color, defaults) : fields.map((field, channel) => finite(key[field], defaults[channel], 'Spine ' + field)));
      steps.push(key.curve === 'stepped');
    });
    return {times, values, steps, defaults: defaults.slice()};
  }

  function attachmentTrack(keys, setup) {
    if (keys === undefined) return {times: [], values: [], setup};
    if (!Array.isArray(keys)) fail('Spine attachment 動畫軌格式不正確。');
    const times = [], values = [];
    keys.forEach((key, index) => {
      const time = finite(key.time, 0, 'Spine attachment 時間');
      if (time < 0 || (index && time <= times[index - 1])) fail('Spine attachment 時間必須嚴格遞增。');
      if (key.name !== undefined && key.name !== null && typeof key.name !== 'string') fail('Spine attachment 名稱格式不正確。');
      times.push(time); values.push(key.name === undefined ? null : key.name);
    });
    return {times, values, setup};
  }

  function leftIndex(times, time) {
    let low = 0, high = times.length - 1, left = -1;
    while (low <= high) {
      const middle = (low + high) >>> 1;
      if (times[middle] <= time) { left = middle; low = middle + 1; }
      else high = middle - 1;
    }
    return left;
  }

  function read(track, time, defaults) {
    if (!track || !track.times.length) return defaults;
    const index = leftIndex(track.times, time);
    if (index < 0) return defaults;
    const value = track.values[index];
    if (index === track.times.length - 1 || track.steps[index]) return value;
    const next = track.values[index + 1];
    const ratio = (time - track.times[index]) / (track.times[index + 1] - track.times[index]);
    return value.map((channel, i) => channel + (next[i] - channel) * ratio);
  }

  function readAttachment(track, time) {
    const index = leftIndex(track.times, time);
    return index < 0 ? track.setup : track.values[index];
  }

  function multiply(parent, local) {
    return {
      a: parent.a * local.a + parent.b * local.c,
      b: parent.a * local.b + parent.b * local.d,
      c: parent.c * local.a + parent.d * local.c,
      d: parent.c * local.b + parent.d * local.d,
      x: parent.a * local.x + parent.b * local.y + parent.x,
      y: parent.c * local.x + parent.d * local.y + parent.y
    };
  }

  function texture(raw, fallback) {
    if (!raw || !raw.dataUrl) return fallback;
    return Object.freeze({name: raw.name, mime: 'image/png', width: raw.width, height: raw.height, dataUrl: raw.dataUrl});
  }

  function compile(exported, baked, fallbackImage) {
    const json = exported && exported.json;
    if (!json || !json.skeleton || typeof json.skeleton.spine !== 'string' || !/^(3\.8|4\.0|4\.2)\.\d+$/.test(json.skeleton.spine) || !Array.isArray(json.bones) || !Array.isArray(json.slots) || !Array.isArray(json.skins)) fail('烘焙預覽需要 Spine 3.8、4.0 或 4.2 的 JSON。');
    const legacy = json.skeleton.spine.startsWith('3.8.');
    if (json.skeleton.spine === '3.8.75') fail('Spine 官方 runtime 不接受 3.8.75 資料，請使用 3.8.99 重新匯出。');
    if (!baked || !Number.isFinite(baked.duration) || baked.duration <= 0 || typeof baked.loop !== 'boolean') fail('烘焙預覽需要有效的動畫長度與循環設定。');
    const duration = baked.duration, loop = baked.loop;
    const animation = json.animations && (json.animations.effect || Object.values(json.animations)[0]);
    if (!animation) fail('Spine JSON 沒有可預覽的動畫。');
    const white = [1, 1, 1, 1], zero = [0, 0], one = [1, 1], noRotate = [0];
    const boneMap = new Map(), bones = [];
    json.bones.forEach(source => {
      if (!source || typeof source.name !== 'string' || boneMap.has(source.name)) fail('Spine 骨骼名稱必須存在且唯一。');
      if (source.transform !== undefined && source.transform !== 'normal') fail('烘焙預覽僅支援正常繼承的骨骼。');
      if (source.inherit !== undefined && source.inherit.toLowerCase() !== 'normal') fail('烘焙預覽僅支援正常繼承的骨骼。');
      const tracks = animation.bones && animation.bones[source.name] || {};
      const bone = {
        name: source.name, parentName: source.parent, parent: null,
        x: finite(source.x, 0, '骨骼 X'), y: finite(source.y, 0, '骨骼 Y'),
        rotation: finite(source.rotation, 0, '骨骼旋轉'),
        scaleX: finite(source.scaleX, 1, '骨骼 X 縮放'), scaleY: finite(source.scaleY, 1, '骨骼 Y 縮放'),
        shearX: finite(source.shearX, 0, '骨骼 X 剪切'), shearY: finite(source.shearY, 0, '骨骼 Y 剪切'),
        translate: numericTrack(tracks.translate, ['x', 'y'], zero),
        rotate: numericTrack(tracks.rotate, [legacy ? 'angle' : 'value'], noRotate),
        scale: numericTrack(tracks.scale, ['x', 'y'], one),
        world: null, referenceAngle: 0, visiting: false, visited: false
      };
      boneMap.set(bone.name, bone);
    });
    function visit(bone) {
      if (bone.visited) return;
      if (bone.visiting) fail('Spine 骨骼階層不能循環引用。');
      bone.visiting = true;
      if (bone.parentName !== undefined) {
        bone.parent = boneMap.get(bone.parentName);
        if (!bone.parent) fail('找不到 Spine 父骨骼：' + bone.parentName);
        visit(bone.parent);
      }
      bone.visiting = false; bone.visited = true; bones.push(bone);
    }
    boneMap.forEach(visit);
    let fallback = null;
    if (typeof fallbackImage === 'string') fallback = Object.freeze({name: 'particle.png', mime: 'image/png', width: 64, height: 64, dataUrl: fallbackImage});
    else if (fallbackImage) fallback = Object.freeze(Object.assign({}, fallbackImage));
    const imageMap = new Map();
    (exported.images || []).forEach(raw => {
      if (!raw || typeof raw.name !== 'string') fail('Spine 圖片名稱格式不正確。');
      imageMap.set(raw.name.replace(/\.png$/i, ''), texture(raw, fallback));
    });
    const skin = json.skins.find(item => item.name === 'default') || json.skins[0];
    if (!skin || !skin.attachments) fail('Spine JSON 缺少預設 skin 附件。');
    const slots = [], slotNames = new Set();
    json.slots.forEach(source => {
      if (!source || typeof source.name !== 'string' || slotNames.has(source.name)) fail('Spine 插槽名稱必須存在且唯一。');
      slotNames.add(source.name);
      const bone = boneMap.get(source.bone);
      if (!bone) fail('找不到 Spine 插槽的骨骼：' + source.bone);
      const tracks = animation.slots && animation.slots[source.name] || {};
      const regions = new Map();
      Object.entries(skin.attachments[source.name] || {}).forEach(([name, sourceRegion]) => {
        if (sourceRegion.type !== undefined && sourceRegion.type !== 'region') fail('烘焙預覽僅支援 region 圖片附件。');
        const angle = finite(sourceRegion.rotation, 0, '附件旋轉');
        const sx = finite(sourceRegion.scaleX, 1, '附件 X 縮放');
        const sy = finite(sourceRegion.scaleY, 1, '附件 Y 縮放');
        const regionPath = sourceRegion.path || name;
        const image = imageMap.has(regionPath) ? imageMap.get(regionPath) : imageMap.get(regionPath.replace(/\.png$/i, ''));
        if (image === undefined) fail('找不到 Spine 附件圖片：' + regionPath);
        regions.set(name, {
          width: finite(sourceRegion.width, 0, '附件寬度'), height: finite(sourceRegion.height, 0, '附件高度'),
          angle, color: rgba(sourceRegion.color, white), image,
          local: {a: Math.cos(angle * DEG) * sx, b: -Math.sin(angle * DEG) * sy,
            c: Math.sin(angle * DEG) * sx, d: Math.cos(angle * DEG) * sy,
            x: finite(sourceRegion.x, 0, '附件 X'), y: finite(sourceRegion.y, 0, '附件 Y')}
        });
      });
      const attachments = attachmentTrack(tracks.attachment, source.attachment === undefined ? null : source.attachment);
      attachments.values.concat(attachments.setup).forEach(name => {
        if (name !== null && name !== undefined && !regions.has(name)) fail('找不到 Spine attachment：' + name);
      });
      slots.push({name: source.name, bone, regions, attachments,
        rgba: numericTrack(tracks[legacy ? 'color' : 'rgba'], [], white, true), setupColor: rgba(source.color, white),
        blend: source.blend || 'normal'});
    });

    function sample(time) {
      if (typeof time !== 'number' || !Number.isFinite(time)) fail('預覽時間必須是有限數值。');
      const t = loop ? mod(time, duration) : clamp(time, 0, duration);
      bones.forEach(bone => {
        const position = read(bone.translate, t, zero), rotation = bone.rotation + read(bone.rotate, t, noRotate)[0];
        const scale = read(bone.scale, t, one), sx = bone.scaleX * scale[0], sy = bone.scaleY * scale[1];
        const xAngle = (rotation + bone.shearX) * DEG;
        const yAngle = (rotation + 90 + bone.shearY) * DEG;
        const local = {a: Math.cos(xAngle) * sx, b: Math.cos(yAngle) * sy,
          c: Math.sin(xAngle) * sx, d: Math.sin(yAngle) * sy,
          x: bone.x + position[0], y: bone.y + position[1]};
        bone.world = bone.parent ? multiply(bone.parent.world, local) : local;
        bone.referenceAngle = (bone.parent ? bone.parent.referenceAngle : 0) + rotation + bone.shearX;
      });
      const result = [];
      slots.forEach(slot => {
        const name = readAttachment(slot.attachments, t);
        if (name === null || name === undefined) return;
        const region = slot.regions.get(name);
        const color = read(slot.rgba, t, slot.setupColor).map((channel, i) => clamp(channel * region.color[i], 0, 1));
        if (color[3] <= 0) return;
        const matrix = multiply(slot.bone.world, region.local);
        const normalizedAngle = Math.atan2(matrix.c, matrix.a) / DEG;
        const referenceAngle = slot.bone.referenceAngle + region.angle;
        const rotation = normalizedAngle + 360 * Math.round((referenceAngle - normalizedAngle) / 360);
        result.push({x: matrix.x, y: matrix.y,
          width: region.width * Math.hypot(matrix.a, matrix.c), height: region.height * Math.hypot(matrix.b, matrix.d),
          rotation, color: color.slice(0, 3), alpha: color[3], blend: slot.blend, image: region.image,
          slotName: slot.name, attachmentName: name,
          // The scalar sizes/rotation are exact for ParticleCore's uniform-scale
          // exports; this matrix also retains arbitrary affine geometry for later renderers.
          matrix});
      });
      return result;
    }
    return {sample, duration, loop};
  }
  return {compile};
});
