(function (root, factory) {
  'use strict';
  const runtimes = typeof module === 'object' && module.exports ? require('./spine-runtimes.js') : root.ParticleSpineRuntimes;
  const api = factory(runtimes);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleSpineRuntimePreview = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (Runtimes) {
  'use strict';
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const copy = value => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const DEG = Math.PI / 180;
  function fail(message, code) { const error = new Error(message); error.code = code || 'SPINE_PREVIEW_ERROR'; throw error; }
  function finite(value, fallback, label) {
    if (value === undefined) return fallback;
    if (typeof value !== 'number' || !Number.isFinite(value)) fail(label + '必須是有限數值。');
    return value;
  }
  function normalPath(value) {
    return String(value || '').replace(/\\/g, '/').replace(/^(\.\/)+/, '').replace(/\/+/g, '/').replace(/\.(png|jpe?g|webp)$/i, '');
  }
  function matrix(bone) { return {a: bone.a, b: bone.b, c: bone.c, d: bone.d, x: bone.worldX, y: bone.worldY}; }
  function multiply(p, b) {
    return {a: p.a * b.a + p.b * b.c, b: p.a * b.b + p.b * b.d, c: p.c * b.a + p.d * b.c, d: p.c * b.b + p.d * b.d,
      x: p.a * b.x + p.b * b.y + p.x, y: p.c * b.x + p.d * b.y + p.y};
  }
  // Official skins store attachment keys in plain JS dictionaries. Give those
  // keys private safe aliases so arbitrary user names cannot become setters.
  // Bone/slot indices and names stay unchanged, including weighted mesh indices.
  function aliasAttachments(json) {
    const bySlot = new Map(), descriptors = new Map(), aliases = new Map(); let sequence = 0;
    const alias = (slot, name) => {
      if (!bySlot.has(slot)) bySlot.set(slot, new Map());
      const names = bySlot.get(slot);
      if (!names.has(name)) { const key = 'ps_attachment_' + sequence++; names.set(name, key); aliases.set(key, {slot, name}); }
      return names.get(name);
    };
    for (const skin of json.skins || []) for (const slot of Object.keys(skin.attachments || {})) {
      const source = skin.attachments[slot], remapped = {};
      for (const name of Object.keys(source)) {
        const item = source[name], type = item.type || 'region', key = alias(slot, name);
        if (item.sequence && (!Number.isInteger(item.sequence.count) || item.sequence.count < 1 || item.sequence.count > 1000 ||
          item.sequence.digits !== undefined && (!Number.isInteger(item.sequence.digits) || item.sequence.digits < 0 || item.sequence.digits > 16) ||
          item.sequence.setup !== undefined && (!Number.isInteger(item.sequence.setup) || item.sequence.setup < 0 || item.sequence.setup >= item.sequence.count))) {
          fail('Spine 圖片序列數量或檔名位數超出預覽範圍。', 'SEQUENCE_INVALID');
        }
        const originalPath = item.path === undefined ? item.name === undefined ? name : item.name : item.path;
        item.name = key;
        if (['region', 'mesh', 'linkedmesh'].includes(type)) item.path = originalPath;
        descriptors.set(key, {slot, name, path: originalPath, type, width: item.width, height: item.height});
        if (item.parent !== undefined) item.parent = alias(slot, item.parent);
        remapped[key] = item;
      }
      Object.defineProperty(skin.attachments, slot, {value: remapped, enumerable: true, configurable: true, writable: true});
    }
    for (const slot of json.slots || []) if (slot.attachment !== undefined && slot.attachment !== null) slot.attachment = alias(slot.name, slot.attachment);
    for (const animation of Object.values(json.animations || {})) {
      for (const slot of Object.keys(animation.slots || {})) for (const key of animation.slots[slot].attachment || []) {
        if (key.name !== undefined && key.name !== null) key.name = alias(slot, key.name);
      }
      for (const group of ['deform', 'attachments']) for (const skin of Object.keys(animation[group] || {})) {
        for (const slot of Object.keys(animation[group][skin])) {
          const original = animation[group][skin][slot], remapped = {};
          for (const key of Object.keys(original)) remapped[alias(slot, key)] = original[key];
          Object.defineProperty(animation[group][skin], slot, {value: remapped, enumerable: true, configurable: true, writable: true});
        }
      }
    }
    return {descriptors, aliases};
  }
  function compile(exported, options) {
    if (!Runtimes) fail('官方 Spine 預覽核心尚未載入。', 'RUNTIMES_MISSING');
    if (!exported || !exported.json || !exported.json.skeleton) fail('請提供完整 Spine JSON。');
    let json;
    try { json = copy(exported.json); } catch (_) { fail('Spine JSON 含有無法預覽的循環或非 JSON 資料。'); }
    const opts = options || {}, version = json.skeleton.spine, match = typeof version === 'string' && /^(3\.8|4\.0|4\.2)\.\d+$/.exec(version);
    if (!match || !Runtimes[match[1]]) fail('掛接預覽支援 Spine 3.8、4.0、4.2 JSON。', 'VERSION_UNSUPPORTED');
    const family = match[1], runtime = Runtimes[family], modern = family === '4.2';
    if (modern && ((Array.isArray(json.physics) && json.physics.length) || Object.values(json.animations || {}).some(animation => animation.physics && Object.keys(animation.physics).length))) {
      fail('這個 Spine 4.2 專案包含物理約束；目前掛接預覽尚未支援可重現的物理模擬。請在 Spine 檢查物理表演，或使用不含物理約束的預覽資料。', 'PHYSICS_UNSUPPORTED');
    }
    if (!Array.isArray(json.bones) || !Array.isArray(json.slots) || !Array.isArray(json.skins)) fail('Spine JSON 的骨骼、插槽與皮膚資料不完整。');
    const requestedAnimation = opts.animationName === undefined ? Object.keys(json.animations || {})[0] || null : opts.animationName;
    if (requestedAnimation !== null && (typeof requestedAnimation !== 'string' || !own(json.animations || {}, requestedAnimation))) fail('找不到掛接預覽動畫：' + String(requestedAnimation), 'ANIMATION_MISSING');
    const names = aliasAttachments(json), imageEntries = new Map(), flexibleImages = new Set(), missing = new Map(), records = new Map(), atlases = [];
    function register(raw, flexible) {
      if (!raw || typeof raw !== 'object') return;
      const name = raw.path || raw.name; if (typeof name !== 'string' || !name) return;
      const width = finite(raw.width, 0, '圖片寬度'), height = finite(raw.height, 0, '圖片高度');
      const entry = Object.freeze({name: raw.name || raw.path, path: raw.path || raw.name, width, height,
        mime: raw.mime || 'image/png', dataUrl: typeof raw.dataUrl === 'string' && raw.dataUrl ? raw.dataUrl : null});
      const key = normalPath(name); imageEntries.set(key, entry);
      if (flexible) flexibleImages.add(key); else flexibleImages.delete(key);
    }
    (opts.assets && opts.assets.images || []).forEach(raw => register(raw, true)); (exported.images || []).forEach(raw => register(raw, false));
    function lookup(path) {
      const key = normalPath(path); if (imageEntries.has(key)) return imageEntries.get(key);
      const candidates = Array.from(imageEntries, ([name, image]) => ({name, image})).filter(item => flexibleImages.has(item.name) && item.name.endsWith('/' + key));
      if (candidates.length === 1) return candidates[0].image;
      const insensitive = Array.from(imageEntries, ([name, image]) => ({name, image})).filter(item => item.name.toLowerCase() === key.toLowerCase() || flexibleImages.has(item.name) && item.name.toLowerCase().endsWith('/' + key.toLowerCase()));
      return insensitive.length === 1 ? insensitive[0].image : null;
    }
    const atlasInput = opts.assets && opts.assets.atlas, atlasSources = Array.isArray(atlasInput) ? atlasInput : atlasInput ? [atlasInput] : [];
    for (const source of atlasSources) {
      if (!source || typeof source.text !== 'string') fail('Atlas 素材必須包含文字。', 'ATLAS_INVALID');
      const directory = String(source.name || '').replace(/\\/g, '/').replace(/[^/]*$/, ''), pageSizes = new Map();
      let pageName = null, expectingPage = true, readingPage = false;
      for (const line of source.text.split(/\r?\n/)) {
        const text = line.trim();
        if (!text) { expectingPage = true; readingPage = false; continue; }
        if (expectingPage) {
          if (text.includes(':')) continue;
          pageName = text; expectingPage = false; readingPage = true; continue;
        }
        if (readingPage && !text.includes(':')) readingPage = false;
        const size = readingPage && /^size\s*:\s*(\d+)\s*,\s*(\d+)/i.exec(text);
        if (size) pageSizes.set(pageName, {width: Number(size[1]), height: Number(size[2])});
      }
      let atlas;
      try {
        atlas = family === '3.8' ? new runtime.TextureAtlas(source.text, page => {
          const size = pageSizes.get(page), image = lookup(directory + page) || lookup(page);
          return {getImage: () => ({width: size && size.width || image && image.width || 1, height: size && size.height || image && image.height || 1}), setFilters() {}, setWraps() {}, dispose() {}};
        }) : new runtime.TextureAtlas(source.text);
      } catch (error) { fail('Atlas 解析失敗：' + error.message, 'ATLAS_INVALID'); }
      for (const page of atlas.pages) {
        const image = lookup(directory + page.name) || lookup(page.name);
        // Atlas coordinates remain in the declared page space even when the
        // uploaded page was resized. Canvas maps normalized UVs to real pixels.
        const width = page.width || image && image.width || 1, height = page.height || image && image.height || 1;
        page.width = width; page.height = height;
        const texture = {getImage: () => ({width, height}), setFilters() {}, setWraps() {}, dispose() {}};
        if (typeof page.setTexture === 'function') page.setTexture(texture); else page.texture = texture;
        page.previewImage = image && image.dataUrl ? Object.freeze({...image, pma: !!page.pma}) : null;
      }
      for (const region of atlas.regions) {
        const page = region.page, rotated = region.rotate || region.degrees === 90 || region.degrees === 270;
        region.u = region.x / page.width; region.v = region.y / page.height;
        region.u2 = (region.x + (rotated ? region.height : region.width)) / page.width;
        region.v2 = (region.y + (rotated ? region.width : region.height)) / page.height;
      }
      atlases.push(atlas);
    }
    function regionFor(path, alias) {
      const image = lookup(path), descriptor = names.descriptors.get(alias) || {};
      if (image && image.dataUrl) return {region: {width: image.width || descriptor.width || 64, height: image.height || descriptor.height || 64,
        originalWidth: image.width || descriptor.width || 64, originalHeight: image.height || descriptor.height || 64,
        offsetX: 0, offsetY: 0, u: 0, v: 0, u2: 1, v2: 1, degrees: 0, rotate: false}, image, placeholder: false};
      for (const atlas of atlases) {
        const region = atlas.findRegion(path);
        if (region) return {region, image: region.page.previewImage, placeholder: false};
      }
      return {region: {width: descriptor.width || 64, height: descriptor.height || 64, originalWidth: descriptor.width || 64, originalHeight: descriptor.height || 64,
        offsetX: 0, offsetY: 0, u: 0, v: 0, u2: 1, v2: 1, degrees: 0, rotate: false}, image: null, placeholder: true};
    }
    function textured(attachment, path, alias, sequence) {
      let record;
      if (sequence) {
        const sequenceFrames = [];
        for (let i = 0; i < sequence.regions.length; i++) {
          const framePath = sequence.getPath(path, i), frame = regionFor(framePath, alias);
          frame.path = framePath; frame.attachment = attachment; sequenceFrames.push(frame); sequence.regions[i] = frame.region;
        }
        record = sequenceFrames[sequence.setupIndex] || sequenceFrames[0]; record.sequenceFrames = sequenceFrames;
      } else { record = regionFor(path, alias); record.path = path; record.attachment = attachment; }
      if (typeof attachment.setRegion === 'function') attachment.setRegion(record.region); else attachment.region = record.region;
      records.set(attachment, record); return attachment;
    }
    const loader = {
      newRegionAttachment(_skin, alias, path, sequence) { return textured(new runtime.RegionAttachment(alias, path), path, alias, sequence); },
      newMeshAttachment(_skin, alias, path, sequence) { return textured(new runtime.MeshAttachment(alias, path), path, alias, sequence); },
      newBoundingBoxAttachment(_skin, alias) { return new runtime.BoundingBoxAttachment(alias); },
      newPathAttachment(_skin, alias) { return new runtime.PathAttachment(alias); },
      newPointAttachment(_skin, alias) { return new runtime.PointAttachment(alias); },
      newClippingAttachment(_skin, alias) { return new runtime.ClippingAttachment(alias); }
    };
    let data;
    try {
      const parser = new runtime.SkeletonJson(loader);
      if (family === '3.8') {
        const read = parser.readCurve;
        parser.readCurve = function (frame, timeline, index) {
          const safe = copy(frame); Object.defineProperty(safe, 'hasOwnProperty', {value: key => own(frame, key), enumerable: false});
          return read.call(this, safe, timeline, index);
        };
      }
      data = parser.readSkeletonData(json);
    } catch (error) { fail('Spine 骨架解析失敗：' + error.message, 'SPINE_PARSE_ERROR'); }
    for (const [attachment, record] of records) {
      for (const frame of record.sequenceFrames || [record]) {
        if (frame.placeholder) {
          const width = attachment.width || frame.region.width || 64, height = attachment.height || frame.region.height || 64;
          frame.region.width = frame.region.originalWidth = width; frame.region.height = frame.region.originalHeight = height;
        }
        if (!frame.image) {
          if (!missing.has(frame.path)) missing.set(frame.path, {path: frame.path, slots: [], reason: '未提供原圖片或 Atlas 頁面'});
          const descriptor = names.aliases.get(attachment.name);
          if (descriptor && !missing.get(frame.path).slots.includes(descriptor.slot)) missing.get(frame.path).slots.push(descriptor.slot);
        }
      }
      if (attachment instanceof runtime.RegionAttachment) {
        if (modern) attachment.updateRegion(); else attachment.updateOffset();
      } else if (attachment instanceof runtime.MeshAttachment) {
        if (modern) attachment.updateRegion(); else attachment.updateUVs();
      }
    }
    const skeleton = new runtime.Skeleton(data), animation = requestedAnimation === null ? null : data.findAnimation(requestedAnimation);
    if (requestedAnimation !== null && !animation) fail('找不到掛接預覽動畫：' + requestedAnimation, 'ANIMATION_MISSING');
    if (opts.skinName !== undefined && opts.skinName !== null) {
      const skin = data.findSkin(opts.skinName); if (!skin) fail('找不到掛接預覽皮膚：' + opts.skinName, 'SKIN_MISSING'); skeleton.setSkin(skin);
    } else if (data.defaultSkin || data.skins.length) skeleton.setSkin(data.defaultSkin || data.skins[0]);
    const duration = finite(opts.duration, animation && animation.duration || 0, '預覽動畫長度'); if (duration < 0) fail('預覽動畫長度不可小於 0。');
    const loop = opts.loop === true, selected = opts.slotNames === undefined ? null : new Set(opts.slotNames);
    let lastTime = null, cachedSample = null, cachedBones = null, cachedBoneMap = null, cachedSlotOrder = null, cachedClipAfter = null, evaluations = 0;
    const metadata = {family, version, animationName: requestedAnimation, duration, officialAnimationDuration: animation && animation.duration || 0, loop,
      skinName: skeleton.skin ? skeleton.skin.name : null, missingAssets: Array.from(missing.values()),
      skinNames: Array.from(data.skins, skin => skin.name),
      physicsSupported: false, clippingSupported: true, meshSupported: true};
    function update(time) {
      finite(time, 0, '預覽時間');
      if (typeof time !== 'number') fail('預覽時間必須是有限數值。');
      let at = loop && duration > 0 ? time % duration : clamp(time, 0, duration);
      if (at < 0) at += duration;
      if (loop && (Math.abs(at - duration) < 1e-9 || Math.abs(at) < 1e-9)) at = 0;
      if (at === lastTime) return;
      skeleton.setToSetupPose();
      // Our clock uses the complete selected clip duration. Animation.apply's
      // loop is false to avoid accidentally wrapping to a shorter FX duration.
      if (animation) animation.apply(skeleton, -1, at, false, [], 1, runtime.MixBlend.setup, runtime.MixDirection.mixIn);
      if (modern) skeleton.updateWorldTransform(runtime.Physics.none); else skeleton.updateWorldTransform();
      evaluations++; lastTime = at; cachedSample = []; cachedBones = []; cachedBoneMap = new Map();
      cachedSlotOrder = Array.from(skeleton.drawOrder, slot => slot.data.name); cachedClipAfter = new Map();
      for (const bone of skeleton.bones) {
        const item = {name: bone.data.name, parentName: bone.parent ? bone.parent.data.name : null, length: bone.data.length, active: bone.active !== false,
          x: bone.worldX, y: bone.worldY, endX: bone.worldX + bone.a * bone.data.length, endY: bone.worldY + bone.c * bone.data.length,
          rotation: Math.atan2(bone.c, bone.a) / DEG, matrix: matrix(bone)};
        cachedBones.push(item); cachedBoneMap.set(item.name, item);
      }
      let clips = [];
      for (const slot of skeleton.drawOrder) {
        const attachment = slot.getAttachment();
        if (attachment instanceof runtime.ClippingAttachment && slot.bone.active !== false) {
          const vertices = new Array(attachment.worldVerticesLength).fill(0);
          attachment.computeWorldVertices(slot, 0, vertices.length, vertices, 0, 2);
          if (!clips.length) clips = [{vertices, endSlotName: attachment.endSlot ? attachment.endSlot.name : null}];
        } else if (attachment && slot.bone.active !== false && (!selected || selected.has(slot.data.name)) && (attachment instanceof runtime.RegionAttachment || attachment instanceof runtime.MeshAttachment)) {
          let record = records.get(attachment);
          const tint = attachment.color, light = slot.color, global = skeleton.color;
          const color = [clamp(light.r * tint.r * global.r, 0, 1), clamp(light.g * tint.g * global.g, 0, 1), clamp(light.b * tint.b * global.b, 0, 1)];
          const alpha = clamp(light.a * tint.a * global.a, 0, 1);
          const vertices = new Array(attachment instanceof runtime.RegionAttachment ? 8 : attachment.worldVerticesLength).fill(0);
          if (attachment instanceof runtime.RegionAttachment) attachment.computeWorldVertices(modern ? slot : slot.bone, vertices, 0, 2);
          else attachment.computeWorldVertices(slot, 0, vertices.length, vertices, 0, 2);
          if (record && record.sequenceFrames) record = record.sequenceFrames.find(frame => frame.region === attachment.region) || record;
          let local = {a: 1, b: 0, c: 0, d: 1, x: 0, y: 0};
          if (attachment instanceof runtime.RegionAttachment) {
            const r = attachment.rotation * DEG; local = {a: Math.cos(r) * attachment.scaleX, b: -Math.sin(r) * attachment.scaleY,
              c: Math.sin(r) * attachment.scaleX, d: Math.cos(r) * attachment.scaleY, x: attachment.x, y: attachment.y};
          }
          const world = multiply(matrix(slot.bone), local), alias = names.aliases.get(attachment.name);
          const item = {type: attachment instanceof runtime.RegionAttachment ? 'region' : 'mesh', slotName: slot.data.name,
            attachmentName: alias ? alias.name : attachment.name, path: record && record.path,
            x: world.x, y: world.y, rotation: Math.atan2(world.c, world.a) / DEG, color, alpha,
            darkColor: slot.darkColor ? [slot.darkColor.r, slot.darkColor.g, slot.darkColor.b] : null,
            blend: ['normal', 'additive', 'multiply', 'screen'][slot.data.blendMode] || 'normal', image: record && record.image || null,
            matrix: world, vertices, uvs: Array.from(attachment.uvs), triangles: attachment instanceof runtime.RegionAttachment ? [0, 1, 2, 2, 3, 0] : Array.from(attachment.triangles),
            clipPolygons: clips.map(clip => ({vertices: clip.vertices.slice(), endSlotName: clip.endSlotName}))};
          if (item.type === 'region') {
            item.x = (vertices[0] + vertices[2] + vertices[4] + vertices[6]) / 4; item.y = (vertices[1] + vertices[3] + vertices[5] + vertices[7]) / 4;
            item.width = Math.hypot(vertices[4] - vertices[2], vertices[5] - vertices[3]); item.height = Math.hypot(vertices[2] - vertices[0], vertices[3] - vertices[1]);
          } else {
            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            for (let i = 0; i < vertices.length; i += 2) {
              minX = Math.min(minX, vertices[i]); maxX = Math.max(maxX, vertices[i]);
              minY = Math.min(minY, vertices[i + 1]); maxY = Math.max(maxY, vertices[i + 1]);
            }
            item.width = maxX - minX; item.height = maxY - minY;
          }
          cachedSample.push(item);
        }
        if (clips.length && clips[0].endSlotName === slot.data.name) clips = [];
        cachedClipAfter.set(slot.data.name, clips.map(clip => ({vertices: clip.vertices.slice(), endSlotName: clip.endSlotName})));
      }
    }
    return {metadata, missingAssets: metadata.missingAssets,
      sample(time) { update(time); return cachedSample; }, bones(time) { update(time); return cachedBones; },
      getBone(name, time) { update(time); return cachedBoneMap.get(name) || null; },
      boneMapAt(time) { update(time); return new Map(cachedBoneMap); },
      slotOrder(time) { update(time); return cachedSlotOrder; },
      clipsAfterSlot(name, time) { update(time); return cachedClipAfter.get(name) || []; },
      diagnostics() { return {evaluations, lastTime}; }};
  }
  return {compile};
});
