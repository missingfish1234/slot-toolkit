(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleSpineMerge = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const MAX_NODES = 2000000, MAX_ITEMS = 50000, MAX_TIME = 86400;
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
  const fail = message => { throw new Error(message); };
  // Spine names are arbitrary strings, including names inherited by Object.prototype.
  const put = (target, key, value) => Object.defineProperty(target, key, {value, enumerable: true, configurable: true, writable: true});
  const get = (target, key, fallback) => object(target) && own(target, key) ? target[key] : fallback;
  const copy = value => JSON.parse(JSON.stringify(value));
  const roundedTime = value => Math.round(value * 1000000) / 1000000;
  const FLOW_PHASES = ['in', 'loop', 'out'];
  function versionProfile(version) {
    if (typeof version !== 'string' || !/^(3\.8|4\.0|4\.2)\.\d+$/.test(version)) fail('追加功能支援 Spine 3.8.x、4.0.x、4.2.x JSON；請使用原版本匯出，無法直接修改版本號轉換角色骨架。');
    if (version === '3.8.75') fail('Spine 官方 runtime 不支援 3.8.75 JSON；請在 Spine 3.8.99 重新匯出原骨架，勿只修改版本號。');
    const minor = version.split('.').slice(0, 2).join('.');
    return {minor, colorChannel: minor === '3.8' ? 'color' : 'rgba', normalizedCurves: minor === '3.8'};
  }
  function name(value, label) {
    if (typeof value !== 'string' || !value.trim() || value.length > 1024 || /[\u0000-\u001f]/.test(value)) fail(label + '名稱無效。');
    return value;
  }
  function time(value, fallback, label, positive) {
    if (value === undefined) return fallback;
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > MAX_TIME || (positive && !value)) fail(label + '必須是 ' + (positive ? '大於 0' : '不小於 0') + ' 的有限秒數（上限 86400 秒）。');
    return value;
  }
  function checkJson(value) {
    const seen = new Set(); let nodes = 0;
    function visit(item, depth) {
      if (++nodes > MAX_NODES || depth > 100) fail('Spine JSON 結構過大或巢狀過深。');
      if (typeof item === 'number' && !Number.isFinite(item)) fail('Spine JSON 含非有限數值。');
      if (item === undefined || item === null || typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') return;
      if (!object(item) && !Array.isArray(item)) fail('Spine 資料必須是完整 JSON。');
      if (seen.has(item)) fail('Spine JSON 不可包含循環引用。');
      seen.add(item);
      Object.keys(item).forEach(key => visit(item[key], depth + 1));
      seen.delete(item);
    }
    visit(value, 0);
  }
  function namedList(list, label, required) {
    if (list === undefined && !required) return new Map();
    if (!Array.isArray(list) || (required && !list.length) || list.length > MAX_ITEMS) fail(label + '格式或數量無效。');
    const names = new Map();
    list.forEach((item, index) => {
      if (!object(item)) fail(label + '項目必須是物件。');
      const key = name(item.name, label);
      if (names.has(key)) fail(label + '名稱重複：' + key);
      names.set(key, {item, index});
    });
    return names;
  }
  function animationDuration(animation, label) {
    if (!object(animation)) fail('Spine 動畫格式無效：' + label);
    let duration = 0;
    function visit(value) {
      if (Array.isArray(value)) {
        let previous = -1;
        value.forEach(key => {
          if (object(key)) {
            const at = time(key.time, 0, '動畫 ' + label + ' 關鍵幀時間');
            if (at < previous) fail('動畫 ' + label + ' 的關鍵幀時間未依序排列。');
            previous = at; duration = Math.max(duration, at);
          }
        });
      } else if (object(value)) Object.keys(value).forEach(key => visit(value[key]));
    }
    ['bones', 'slots', 'ik', 'transform', 'path', 'physics', 'attachments', 'deform', 'events', 'drawOrder', 'draworder'].forEach(key => {
      if (own(animation, key)) visit(animation[key]);
    });
    return duration;
  }
  function structure(json) {
    if (!object(json) || !object(json.skeleton)) fail('請匯入包含 skeleton 的 Spine JSON；.spine 或 .skel 二進位檔需先在 Spine 匯出 JSON。');
    checkJson(json);
    const version = json.skeleton.spine;
    versionProfile(version);
    const bones = namedList(json.bones, '骨骼', true), slots = namedList(json.slots, '插槽', false);
    bones.forEach(({item}) => {
      if (own(item, 'parent')) {
        name(item.parent, '父骨骼');
        if (!bones.has(item.parent)) fail('找不到父骨骼：' + item.parent);
      }
    });
    const visited = new Set();
    function parents(key) {
      if (visited.has(key)) return;
      const visiting = new Set(), chain = [];
      while (!visited.has(key)) {
        if (visiting.has(key)) fail('Spine 骨骼父子關係存在循環：' + key);
        visiting.add(key); chain.push(key); const bone = bones.get(key).item;
        if (!own(bone, 'parent')) break;
        key = bone.parent;
      }
      chain.forEach(item => visited.add(item));
    }
    bones.forEach((entry, key) => parents(key));
    bones.forEach(({item, index}) => {
      if (own(item, 'parent') && bones.get(item.parent).index >= index) fail('Spine 骨骼必須依父骨骼在前、子骨骼在後排序：' + item.name);
    });
    slots.forEach(({item}) => { if (!bones.has(item.bone)) fail('插槽 ' + item.name + ' 指定不存在的骨骼：' + item.bone); });
    const skins = namedList(json.skins, '皮膚', false);
    skins.forEach(({item}) => {
      if (item.attachments !== undefined && !object(item.attachments)) fail('Spine 皮膚附件格式無效。');
      Object.keys(item.attachments || {}).forEach(key => {
        if (!slots.has(key)) fail('皮膚指定不存在的插槽：' + key);
        if (!object(item.attachments[key])) fail('Spine 插槽附件格式無效：' + key);
      });
    });
    if (json.animations !== undefined && !object(json.animations)) fail('Spine 動畫格式無效。');
    const animations = Object.keys(json.animations || {}).map(key => {
      name(key, '動畫'); const animation = json.animations[key];
      if (!object(animation)) fail('Spine 動畫格式無效：' + key);
      ['bones', 'slots'].forEach(group => {
        if (animation[group] !== undefined && !object(animation[group])) fail('動畫 ' + key + ' 的 ' + group + ' 格式無效。');
        Object.keys(animation[group] || {}).forEach(target => {
          if (!(group === 'bones' ? bones : slots).has(target)) fail('動畫 ' + key + ' 指定不存在的 ' + group + '：' + target);
        });
      });
      return {name: key, duration: animationDuration(animation, key)};
    });
    return {version, bones, slots, skins, animations};
  }
  function inspect(json) {
    const state = structure(json);
    // Validate offsets against the source setup order even before a merge is requested.
    Object.keys(json.animations || {}).forEach(key => {
      ['drawOrder', 'draworder'].forEach(property => {
        const keys = json.animations[key][property];
        if (keys !== undefined) {
          if (!Array.isArray(keys)) fail('Spine drawOrder 必須是關鍵幀陣列。');
          keys.forEach(frame => { if (!object(frame)) fail('Spine drawOrder 關鍵幀格式無效。'); decodeOrder(Array.from(state.slots.keys()), frame.offsets); });
        }
      });
    });
    return {version: state.version, imagesPath: typeof json.skeleton.images === 'string' ? json.skeleton.images : './images/',
      bones: Array.from(state.bones.values(), entry => copy(entry.item)),
      slots: Array.from(state.slots.values(), entry => copy(entry.item)), animations: state.animations,
      skins: Array.from(state.skins.keys()), boneCount: state.bones.size, slotCount: state.slots.size};
  }
  function prefixName(value) {
    if (value === undefined || value === '') return 'particle_fx';
    if (typeof value !== 'string') fail('粒子前綴必須是文字。');
    const result = value.trim();
    if (!/^[A-Za-z0-9_-]{1,48}$/.test(result) || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(result)) fail('粒子前綴限 1～48 個英文字母、數字、底線或連字號，且不可使用系統保留檔名。');
    return result;
  }
  function optionsFor(json, options, durationFallback) {
    const info = inspect(json), settings = object(options) ? options : {};
    const boneNames = new Set(info.bones.map(bone => bone.name)), slotNames = new Set(info.slots.map(slot => slot.name));
    const parentBone = settings.parentBone === undefined || settings.parentBone === '' ? info.bones[0].name : name(settings.parentBone, '父骨骼');
    if (!boneNames.has(parentBone)) fail('找不到要掛接的父骨骼：' + parentBone);
    const emitterParents = {};
    if (settings.emitterParents !== undefined && !object(settings.emitterParents)) fail('發射器掛接設定格式無效。');
    Object.keys(settings.emitterParents || {}).forEach(key => {
      name(key, '發射器骨骼'); const parent = name(settings.emitterParents[key], '父骨骼');
      if (!boneNames.has(parent)) fail('找不到發射器要掛接的父骨骼：' + parent);
      put(emitterParents, key, parent);
    });
    const animationName = name(settings.animationName === undefined || settings.animationName === '' ? 'particle_fx' : settings.animationName, '動畫');
    const drawOrder = settings.drawOrder === undefined ? 'front' : settings.drawOrder;
    if (!['front', 'back', 'after'].includes(drawOrder)) fail('粒子圖層位置必須是 front、back 或 after。');
    const afterSlot = typeof settings.afterSlot === 'string' ? settings.afterSlot : '';
    if (drawOrder === 'after' && !slotNames.has(afterSlot)) fail('找不到要放在其後的插槽：' + afterSlot);
    const startTime = time(settings.startTime, 0, '粒子開始時間');
    if (startTime > 600) fail('粒子開始時間不可超過 600 秒。');
    if (settings.enabled !== undefined && typeof settings.enabled !== 'boolean') fail('Spine 追加啟用設定必須為布林值。');
    const animationMode = settings.animationMode === undefined ? info.animations.some(item => item.name === animationName) ? 'existing' : 'new' : settings.animationMode;
    if (!['existing', 'new'].includes(animationMode)) fail('Spine 追加動畫模式必須為 existing 或 new。');
    const result = {enabled: settings.enabled === undefined ? true : settings.enabled, parentBone, emitterParents, animationName, animationMode, startTime,
      duration: time(settings.duration, durationFallback, '粒子長度', true), drawOrder, afterSlot, prefix: prefixName(settings.prefix)};
    if (settings.flowTargets !== undefined) result.flowTargets = normalizeFlowTargets(settings.flowTargets, info);
    return result;
  }
  function normalizeFlowTargets(raw, info) {
    if (!object(raw) || FLOW_PHASES.some(phase => !object(raw[phase]))) fail('三段動畫掛接設定必須包含 IN、LOOP、OUT。');
    const targets = {}, used = new Set();
    FLOW_PHASES.forEach(phase => {
      const value = raw[phase], animationName = name(value.animationName, phase.toUpperCase() + ' 動畫');
      const animationMode = value.animationMode === undefined ? info.animations.some(item => item.name === animationName) ? 'existing' : 'new' : value.animationMode;
      if (!['existing', 'new'].includes(animationMode)) fail(phase.toUpperCase() + ' 動畫方式必須為 existing 或 new。');
      if (used.has(animationName)) fail('IN、LOOP、OUT 必須選擇三個不同的目標動畫，避免覆蓋同一段粒子軌。');
      used.add(animationName);
      const startTime = time(value.startTime, 0, phase.toUpperCase() + ' 開始時間');
      if (startTime > 600) fail(phase.toUpperCase() + ' 開始時間不可超過 600 秒。');
      targets[phase] = {animationName, animationMode, startTime};
    });
    return targets;
  }
  function normalizeSession(session) {
    if (session === null || session === undefined) return null;
    if (!object(session)) fail('Spine 追加專案格式無效。');
    const json = copyAfterCheck(session.json), settings = optionsFor(json, session.settings, undefined);
    if (settings.duration === undefined) delete settings.duration;
    const result = {fileName: typeof session.fileName === 'string' && session.fileName.trim() ? session.fileName.split(/[\\/]/).pop().slice(0, 255) : 'skeleton.json', json, settings};
    if (session.assets !== undefined && session.assets !== null) result.assets = normalizeAssets(session.assets);
    return result;
  }
  function utf8Length(value) {
    let bytes = 0;
    for (const character of value) bytes += character.codePointAt(0) <= 0x7f ? 1 : character.codePointAt(0) <= 0x7ff ? 2 : character.codePointAt(0) <= 0xffff ? 3 : 4;
    return bytes;
  }
  function normalizeAssetImage(raw) {
    if (!object(raw)) fail('原骨架圖片素材格式無效。');
    const path = imagePath(raw.path), label = '原骨架圖片「' + path + '」';
    const width = raw.width, height = raw.height;
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 2048 || height > 2048) fail(label + '尺寸必須是 1 到 2048 像素。');
    const data = raw.dataUrl;
    if (raw.mime !== 'image/png' || typeof data !== 'string' || !data.startsWith('data:image/png;base64,')) fail(label + '僅接受內嵌 PNG，不能使用外部網址。');
    const base64 = data.slice(22), max = 4 * 1024 * 1024;
    if (base64.length > max * 4 / 3 + 4 || base64.length < 44 || base64.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(base64)) fail(label + 'PNG 編碼無效，或素材超過 4 MiB。');
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/', padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0;
    const tail = alphabet.indexOf(base64[base64.length - padding - 1]);
    if (base64.length / 4 * 3 - padding > max || (padding === 2 && (tail & 15) !== 0) || (padding === 1 && (tail & 3) !== 0)) fail(label + 'PNG 編碼無效，或素材超過 4 MiB。');
    const bytes = [];
    for (let index = 0; index < 44; index += 4) {
      const word = (alphabet.indexOf(base64[index]) << 18) | (alphabet.indexOf(base64[index + 1]) << 12) | (alphabet.indexOf(base64[index + 2]) << 6) | alphabet.indexOf(base64[index + 3]);
      bytes.push((word >>> 16) & 255, (word >>> 8) & 255, word & 255);
    }
    if (![137, 80, 78, 71, 13, 10, 26, 10].every((value, index) => bytes[index] === value) || String.fromCharCode.apply(null, bytes.slice(12, 16)) !== 'IHDR') fail(label + '不是有效的 PNG 素材。');
    const u32 = offset => ((bytes[offset] * 0x1000000) + (bytes[offset + 1] << 16) + (bytes[offset + 2] << 8) + bytes[offset + 3]) >>> 0;
    if (u32(16) !== width || u32(20) !== height) fail(label + '尺寸與 PNG 檔案內容不一致。');
    const displayName = raw.name === undefined ? path.split('/').pop() : raw.name;
    if (typeof displayName !== 'string' || !displayName.trim() || displayName.length > 160 || /[\u0000-\u001f]/.test(displayName)) fail(label + '檔名無效。');
    return {path, name: displayName, mime: 'image/png', width, height, dataUrl: data};
  }
  function normalizeAssets(raw) {
    if (!object(raw)) fail('原骨架預覽素材格式無效。');
    const list = raw.images === undefined ? [] : raw.images;
    if (!Array.isArray(list) || list.length > 2000) fail('原骨架預覽圖片必須是陣列，且不可超過 2000 張。');
    const paths = new Set(), result = {images: []}; let bytes = 0;
    list.forEach(value => {
      const image = normalizeAssetImage(value);
      if (paths.has(image.path)) fail('原骨架圖片路徑重複：' + image.path + '；請保留每個相對路徑的一份素材。');
      paths.add(image.path); bytes += image.dataUrl.length; result.images.push(image);
    });
    if (raw.atlas !== undefined && raw.atlas !== null) {
      if (!object(raw.atlas) || typeof raw.atlas.text !== 'string' || !raw.atlas.text.trim() || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(raw.atlas.text)) fail('Atlas 必須是有效的純文字資源。');
      const atlasName = raw.atlas.name === undefined ? 'skeleton.atlas' : raw.atlas.name;
      if (typeof atlasName !== 'string' || !atlasName.trim() || atlasName.length > 255 || /[\\/\u0000-\u001f]/.test(atlasName)) fail('Atlas 檔名無效。');
      const text = raw.atlas.text.replace(/^\uFEFF/, ''), length = utf8Length(text);
      if (length > 256 * 1024) fail('Atlas 純文字超過 256 KiB，請縮小圖集資料。');
      result.atlas = {name: atlasName, text}; bytes += length;
    }
    if (bytes > 16 * 1024 * 1024) fail('原骨架內嵌預覽素材總量超過 16 MiB，請縮小圖片後重試。');
    return result;
  }
  function copyAfterCheck(value) { checkJson(value); return copy(value); }

  // All supported Spine versions use offsets relative to setup indices.
  function decodeOrder(setup, offsets) {
    if (offsets === undefined) return setup.slice();
    if (!Array.isArray(offsets) || offsets.length > setup.length) fail('Spine drawOrder offsets 格式無效。');
    const index = new Map(setup.map((key, i) => [key, i])), order = Array(setup.length).fill(null), unchanged = [];
    let original = 0;
    offsets.forEach(change => {
      if (!object(change) || !index.has(change.slot) || !Number.isInteger(change.offset)) fail('Spine drawOrder offset 指定的插槽或偏移值無效。');
      const slotIndex = index.get(change.slot);
      if (slotIndex < original) fail('Spine drawOrder offsets 必須依原插槽順序排列，且不可重複。');
      while (original < slotIndex) unchanged.push(original++);
      const destination = original + change.offset;
      if (destination < 0 || destination >= setup.length || order[destination] !== null) fail('Spine drawOrder offset 超出範圍或重複目的位置。');
      order[destination] = original++;
    });
    while (original < setup.length) unchanged.push(original++);
    for (let i = order.length - 1; i >= 0; i--) if (order[i] === null) order[i] = unchanged.pop();
    return order.map(i => setup[i]);
  }
  function insertBlock(order, extra, settings) {
    const result = order.slice();
    const at = settings.drawOrder === 'back' ? 0 : settings.drawOrder === 'front' ? result.length : result.indexOf(settings.afterSlot) + 1;
    result.splice(at, 0, ...extra); return result;
  }
  function encodeOrder(setup, order, originalOffsets) {
    const positions = new Map(order.map((key, index) => [key, index]));
    const metadata = new Map((originalOffsets || []).map(offset => [offset.slot, offset]));
    const offsets = [];
    setup.forEach((key, index) => {
      const offset = positions.get(key) - index;
      if (offset || metadata.has(key)) {
        const changed = metadata.has(key) ? copy(metadata.get(key)) : {};
        changed.slot = key; changed.offset = offset; offsets.push(changed);
      }
    });
    return offsets;
  }
  function imagePath(value) {
    if (typeof value !== 'string' || !value || value.length > 1024 || value.includes('\\') || value.startsWith('/') || /[:\u0000-\u001f]/.test(value) || value.split('/').some(part => !part || part === '.' || part === '..')) fail('粒子圖片路徑必須是安全的相對路徑。');
    return value;
  }
  function resourcePaths(json) {
    const paths = new Set();
    (json.skins || []).forEach(skin => Object.keys(skin.attachments || {}).forEach(slot => {
      Object.keys(skin.attachments[slot]).forEach(key => {
        const attachment = skin.attachments[slot][key];
        if (object(attachment)) paths.add(typeof attachment.path === 'string' ? attachment.path : typeof attachment.name === 'string' ? attachment.name : key);
      });
    }));
    return paths;
  }
  function allocateNamespace(base, source, images, requested) {
    const bones = new Set(base.bones.map(item => item.name)), slots = new Set((base.slots || []).map(item => item.name)), paths = resourcePaths(base);
    function collides(namespace) {
      if (source.bones.some(item => bones.has(namespace + '__' + item.name)) || (source.slots || []).some(item => slots.has(namespace + '__' + item.name))) return true;
      for (const path of paths) if (path === namespace || path.startsWith(namespace + '/')) return true;
      return images.some(image => paths.has(namespace + '/' + image.name.replace(/\.[^/.]+$/, '')));
    }
    let result = requested, suffix = 2;
    while (collides(result)) { if (suffix > 100000) fail('無法產生唯一的粒子前綴。'); result = requested + '_' + suffix++; }
    return result;
  }
  function shiftedKeys(keys, settings, label, profile) {
    if (!Array.isArray(keys)) fail('粒子動畫軌格式無效：' + label);
    return keys.filter(key => time(key.time, 0, '粒子關鍵幀時間') <= settings.duration).map(key => {
      const result = copy(key), at = roundedTime((key.time || 0) + settings.startTime);
      if (at) result.time = at; else delete result.time;
      if (Array.isArray(result.curve)) {
        if (result.curve.length % 4 || result.curve.some(value => typeof value !== 'number' || !Number.isFinite(value))) fail('粒子貝茲曲線格式無效。');
        // 3.8 stores normalized (0..1) control points; 4.x stores absolute
        // timeline time/value pairs. Only absolute control times move with keys.
        if (!profile.normalizedCurves) for (let i = 0; i < result.curve.length; i += 2) result.curve[i] = roundedTime(result.curve[i] + settings.startTime);
      }
      return result;
    });
  }
  function rgbaAt(keys, at, fallback) {
    let left = null, right = null;
    for (const key of keys) {
      if ((key.time || 0) <= at) left = key;
      else { right = key; break; }
    }
    if (!left) return fallback;
    if (!right || left.curve === 'stepped') return left.color;
    const u = (at - (left.time || 0)) / ((right.time || 0) - (left.time || 0));
    return [0, 2, 4, 6].map(index => {
      const a = parseInt(left.color.slice(index, index + 2), 16), b = parseInt(right.color.slice(index, index + 2), 16);
      return Math.round(a + (b - a) * u).toString(16).padStart(2, '0');
    }).join('');
  }
  function hideSlot(track, settings, setupColor, attachmentMap, profile, preserveEnd) {
    const end = roundedTime(settings.startTime + settings.duration);
    const attachment = shiftedKeys(track.attachment || [], settings, 'attachment', profile);
    attachment.forEach(key => {
      if (key.name !== undefined && key.name !== null) {
        if (!own(attachmentMap, key.name)) fail('粒子 attachment 動畫指定不存在的附件：' + key.name);
        key.name = attachmentMap[key.name];
      }
    });
    const rgba = shiftedKeys(track[profile.colorChannel] || [], settings, profile.colorChannel, profile);
    rgba.forEach(key => {
      if (typeof key.color !== 'string' || !/^[0-9a-f]{8}$/i.test(key.color)) fail('粒子 RGBA 關鍵幀色碼格式無效。');
      if (key.curve !== undefined && key.curve !== 'stepped') fail('粒子追加的 RGBA 曲線必須先烘焙為 linear 或 stepped 關鍵幀。');
    });
    const transparent = (typeof setupColor === 'string' && /^[0-9a-f]{8}$/i.test(setupColor) ? setupColor.slice(0, 6) : 'ffffff') + '00';
    const beforeEnd = roundedTime(end - Math.min(0.0001, settings.duration / 2));
    // Read the original curve before replacing its endpoint. Replacing an alive
    // endpoint with transparent would otherwise fade the whole preceding span.
    const tailColor = rgbaAt(rgba, beforeEnd, transparent);
    if (settings.startTime > 0) {
      attachment.unshift({name: null}); rgba.unshift({color: transparent, curve: 'stepped'});
    }
    if (preserveEnd) {
      track.attachment = attachment; track[profile.colorChannel] = rgba;
      return;
    }
    // Replace the looping emitter's endpoint pose with an exact, one-shot stop.
    while (attachment.length && (attachment[attachment.length - 1].time || 0) >= end) attachment.pop();
    while (rgba.length && (rgba[rgba.length - 1].time || 0) > beforeEnd) rgba.pop();
    if (rgba.length && (rgba[rgba.length - 1].time || 0) === beforeEnd) {
      // A pre-existing reset/birth/death key at the cutoff retains its own value.
      rgba[rgba.length - 1].curve = 'stepped';
    } else rgba.push({time: beforeEnd, color: tailColor, curve: 'stepped'});
    attachment.push({time: end, name: null}); rgba.push({time: end, color: transparent});
    track.attachment = attachment; track[profile.colorChannel] = rgba;
  }
  function mergeBundle(baseJson, exported, options, isFlow) {
    const baseInfo = inspect(baseJson);
    if (!object(exported) || !object(exported.json) || !Array.isArray(exported.images)) fail('請先烘焙粒子，再追加至 Spine 專案。');
    const sourceInfo = inspect(exported.json), source = exported.json;
    const profile = versionProfile(sourceInfo.version), targetProfile = versionProfile(baseInfo.version);
    if (profile.minor !== targetProfile.minor) fail('粒子與原骨架版本不同：粒子 Spine ' + sourceInfo.version + '、原骨架 Spine ' + baseInfo.version + '。請重新輸出與原骨架相同版本的粒子；不可只修改骨架版本號。');
    const animationNames = sourceInfo.animations.map(item => item.name);
    if (animationNames.length !== (isFlow ? 3 : 1)) fail(isFlow ? '三段粒子匯出必須包含 IN、LOOP、OUT 三段動畫。' : '粒子匯出必須包含一段動畫。');
    animationNames.forEach(animationName => {
      const sourceAnimation = source.animations[animationName];
      if (Object.keys(sourceAnimation).some(key => !['bones', 'slots'].includes(key)) || ['ik', 'transform', 'path', 'physics'].some(key => own(source, key))) fail('粒子追加僅支援烘焙後的骨骼與插槽動畫。');
      Object.values(sourceAnimation.slots || {}).forEach(track => {
        if (own(track, profile.colorChannel === 'color' ? 'rgba' : 'color')) fail('粒子插槽顏色軌與 Spine ' + sourceInfo.version + ' 格式不符；請使用對應版本重新烘焙輸出。');
      });
    });
    const roots = source.bones.filter(bone => !own(bone, 'parent'));
    if (roots.length !== 1) fail('粒子匯出必須有唯一的根骨骼。');
    const settings = optionsFor(baseJson, options, exported.stats && exported.stats.duration !== undefined ? exported.stats.duration : sourceInfo.animations[0].duration);
    const segments = isFlow ? flowSegments(baseJson, exported, settings, sourceInfo) : [{phase: null, sourceAnimationName: animationNames[0], ...settings, loop: false}];
    segments.forEach(segment => {
      if (segment.duration === undefined || !segment.duration) fail('粒子烘焙長度必須大於 0 秒。');
      if (segment.startTime + segment.duration > MAX_TIME) fail('粒子追加結束時間不可超過 86400 秒。');
    });
    const sourceBones = new Map(source.bones.map(bone => [bone.name, bone]));
    Object.keys(settings.emitterParents).forEach(key => {
      if (!sourceBones.has(key) || sourceBones.get(key).parent !== roots[0].name) fail('發射器掛接設定指定不存在的發射器骨骼：' + key);
    });
    const images = exported.images.map(image => {
      if (!object(image)) fail('粒子圖片格式無效。');
      imagePath(image.name); return copy(image);
    });
    if (new Set(images.map(image => image.name)).size !== images.length) fail('粒子圖片名稱重複。');
    const namespace = allocateNamespace(baseJson, source, images, settings.prefix), result = copy(baseJson);
    const boneMap = {}, slotMap = {}, attachmentMap = {};
    source.bones.forEach(bone => put(boneMap, bone.name, namespace + '__' + bone.name));
    (source.slots || []).forEach(slot => put(slotMap, slot.name, namespace + '__' + slot.name));
    source.bones.forEach(bone => {
      const added = copy(bone); added.name = boneMap[bone.name];
      added.parent = bone.name === roots[0].name ? settings.parentBone : own(settings.emitterParents, bone.name) ? settings.emitterParents[bone.name] : boneMap[bone.parent];
      result.bones.push(added);
    });
    const extraSlots = (source.slots || []).map(slot => {
      const added = copy(slot); added.name = slotMap[slot.name]; added.bone = boneMap[slot.bone];
      added.attachment = null;
      added.color = (typeof slot.color === 'string' && /^[0-9a-f]{8}$/i.test(slot.color) ? slot.color.slice(0, 6) : 'ffffff') + '00';
      return added;
    });
    const originalOrder = (baseJson.slots || []).map(slot => slot.name), extraOrder = extraSlots.map(slot => slot.name);
    const newOrder = insertBlock(originalOrder, extraOrder, settings), slotObjects = new Map([...(result.slots || []), ...extraSlots].map(slot => [slot.name, slot]));
    result.slots = newOrder.map(key => slotObjects.get(key));
    if (!result.skins) result.skins = [];
    let defaultSkin = result.skins.find(skin => skin.name === 'default');
    if (!defaultSkin) { defaultSkin = {name: 'default', attachments: {}}; result.skins.push(defaultSkin); }
    if (!defaultSkin.attachments) defaultSkin.attachments = {};
    const imageNames = new Map(images.map(image => [image.name.replace(/\.[^/.]+$/, ''), image.name]));
    (source.skins || []).forEach(skin => Object.keys(skin.attachments || {}).forEach(slot => {
      const targetSlot = slotMap[slot];
      if (!own(defaultSkin.attachments, targetSlot)) put(defaultSkin.attachments, targetSlot, {});
      if (!own(attachmentMap, slot)) put(attachmentMap, slot, {});
      Object.keys(skin.attachments[slot]).forEach(key => {
        const attachment = copy(skin.attachments[slot][key]);
        if (!object(attachment) || (attachment.type !== undefined && attachment.type !== 'region')) fail('粒子追加僅支援 region 附件。');
        const path = imagePath(attachment.path === undefined ? key : attachment.path);
        if (!imageNames.has(path)) fail('粒子附件找不到圖片：' + path);
        const mapped = namespace + '__' + key;
        if (own(defaultSkin.attachments[targetSlot], mapped)) fail('粒子皮膚具有重複的附件。');
        attachment.path = namespace + '/' + path;
        if (typeof attachment.name === 'string') attachment.name = mapped;
        put(defaultSkin.attachments[targetSlot], mapped, attachment); put(attachmentMap[slot], key, mapped);
      });
    }));
    images.forEach(image => { image.name = namespace + '/' + image.name; });
    if (!result.animations) result.animations = {};
    // Remap every old draw-order timeline. Original weighted meshes retain their
    // bone indices, since original bones are never reordered or inserted before them.
    Object.keys(result.animations).forEach(key => {
      ['drawOrder', 'draworder'].forEach(property => {
        if (!own(result.animations[key], property)) return;
        result.animations[key][property].forEach(frame => {
          const old = decodeOrder(originalOrder, frame.offsets), order = insertBlock(old, extraOrder, settings);
          const offsets = encodeOrder(newOrder, order, frame.offsets);
          if (offsets.length || own(frame, 'offsets')) frame.offsets = offsets;
        });
      });
    });
    const segmentStats = [];
    segments.forEach(segment => {
      const existed = own(result.animations, segment.animationName);
      if (!existed) put(result.animations, segment.animationName, {});
      const animation = result.animations[segment.animationName], sourceAnimation = source.animations[segment.sourceAnimationName];
      ['bones', 'slots'].forEach(group => {
        if (!own(animation, group)) put(animation, group, {});
        Object.keys(sourceAnimation[group] || {}).forEach(key => {
          const mapped = group === 'bones' ? boneMap[key] : slotMap[key], track = copy(sourceAnimation[group][key]);
          Object.keys(track).forEach(channel => {
            if (group !== 'slots' || ![profile.colorChannel, 'attachment'].includes(channel)) track[channel] = shiftedKeys(track[channel], segment, group + '.' + channel, profile);
          });
          if (group === 'slots') {
            const sourceSlot = source.slots.find(slot => slot.name === key);
            hideSlot(track, segment, sourceSlot.color, get(attachmentMap, key, {}), profile, isFlow && segment.phase !== 'out');
          }
          if (own(animation[group], mapped)) fail('粒子動畫命名發生衝突：' + mapped);
          put(animation[group], mapped, track);
        });
      });
      segmentStats.push({phase: segment.phase, animationName: segment.animationName, animationCreated: !existed,
        startTime: segment.startTime, endTime: roundedTime(segment.startTime + segment.duration), duration: segment.duration, loop: segment.loop});
    });
    const warnings = [];
    if (baseInfo.version !== sourceInfo.version) warnings.push('原專案版本為 ' + baseInfo.version + '，已保留版本；請在對應的 Spine ' + targetProfile.minor + ' 編輯器確認後再匯出。');
    warnings.push('輸出只包含新增粒子圖片，原專案圖片、atlas 與音效需保留；請把新增子目錄放入原 Images 路徑。');
    const hasClipping = (baseJson.skins || []).some(skin => Object.keys(skin.attachments || {}).some(slot =>
      Object.keys(skin.attachments[slot]).some(key => skin.attachments[slot][key] && skin.attachments[slot][key].type === 'clipping')));
    if (hasClipping) warnings.push('原專案包含 clipping；請在 Spine 確認粒子圖層是否位於裁切範圍內。');
    const manifest = {namespace, boneMap, slotMap, attachmentMap, imageDirectory: namespace, parentBone: settings.parentBone,
      emitterParents: copy(settings.emitterParents), animationName: settings.animationName, startTime: settings.startTime,
      endTime: roundedTime(settings.startTime + settings.duration), drawOrder: settings.drawOrder, afterSlot: settings.afterSlot,
      sourceVersion: sourceInfo.version, targetVersion: baseInfo.version, originalImagesPath: baseInfo.imagesPath};
    const stats = {addedBones: source.bones.length, addedSlots: extraSlots.length, addedImages: images.length,
      boneCount: result.bones.length, slotCount: result.slots.length, animationName: settings.animationName,
      animationCreated: segmentStats[0].animationCreated, startTime: settings.startTime, endTime: manifest.endTime, namespace};
    if (isFlow) {
      manifest.phases = {}; stats.phases = {};
      segments.forEach((segment, index) => {
        manifest.phases[segment.phase] = {sourceAnimationName: segment.sourceAnimationName, animationName: segment.animationName,
          animationMode: segment.animationMode, startTime: segment.startTime, duration: segment.duration,
          endTime: segmentStats[index].endTime, loop: segment.loop};
        stats.phases[segment.phase] = segmentStats[index];
      });
      manifest.transition = 'loop-boundary';
      delete manifest.animationName; delete manifest.startTime; delete manifest.endTime;
      delete stats.animationName; delete stats.animationCreated; delete stats.startTime; delete stats.endTime;
      warnings.push('IN → LOOP → OUT 共用同一組粒子骨骼；請在 LOOP 完整循環的邊界切換到 OUT，並以 0 混合時間播放三段動畫。');
    }
    return {json: result, images, stats, warnings, manifest};
  }
  function flowSegments(baseJson, exported, settings, sourceInfo) {
    const phases = exported.manifest && exported.manifest.phases;
    if (!object(phases) || FLOW_PHASES.some(phase => !object(phases[phase]))) fail('三段粒子匯出缺少 IN、LOOP、OUT 的長度與動畫資料。');
    const originalNames = new Set(sourceInfo.animations.map(item => item.name)), usedSources = new Set();
    const targets = settings.flowTargets || normalizeFlowTargets(Object.fromEntries(FLOW_PHASES.map(phase => {
      const animationName = phases[phase].animationName;
      return [phase, {animationName, animationMode: own(baseJson.animations || {}, animationName) ? 'existing' : 'new', startTime: 0}];
    })), inspect(baseJson));
    return FLOW_PHASES.map(phase => {
      const source = phases[phase], sourceAnimationName = name(source.animationName, phase.toUpperCase() + ' 來源動畫');
      if (!originalNames.has(sourceAnimationName) || usedSources.has(sourceAnimationName)) fail('IN、LOOP、OUT 必須對應三段不同且存在的粒子動畫。');
      usedSources.add(sourceAnimationName);
      const duration = time(source.duration, undefined, phase.toUpperCase() + ' 長度', true);
      if (duration === undefined || source.loop !== (phase === 'loop')) fail('三段粒子匯出的長度或 LOOP 循環設定無效。');
      const keyedDuration = sourceInfo.animations.find(animation => animation.name === sourceAnimationName).duration;
      if (Math.abs(keyedDuration - duration) > .000001) fail(phase.toUpperCase() + ' 粒子動畫長度與階段設定不同，請重新烘焙三段動畫。');
      const target = targets[phase], existed = own(baseJson.animations || {}, target.animationName);
      if (target.animationMode === 'existing' && !existed) fail(phase.toUpperCase() + ' 目標動畫不存在：' + target.animationName);
      if (target.animationMode === 'new' && existed) fail(phase.toUpperCase() + ' 新動畫名稱已存在，請改選追加至原動畫或使用其他名稱。');
      if (phase === 'loop') {
        if (target.startTime !== 0) fail('LOOP 必須從 0 秒開始，完整動畫重播才能維持連續循環。');
        const originalDuration = existed ? animationDuration(baseJson.animations[target.animationName], target.animationName) : 0;
        if (originalDuration > duration + .000001) fail('原 LOOP 動畫長度 ' + originalDuration.toFixed(2) + ' 秒超過粒子 LOOP 的 ' + duration.toFixed(2) + ' 秒；請增加 LOOP 長度或選擇新增動畫，避免循環接縫中斷。');
      }
      return {phase, sourceAnimationName, duration, loop: phase === 'loop', ...target};
    });
  }
  function merge(baseJson, exported, options) { return mergeBundle(baseJson, exported, options, false); }
  function mergeFlow(baseJson, exported, options) { return mergeBundle(baseJson, exported, options, true); }
  return {inspect, normalizeSession, normalizeAssets, merge, mergeFlow};
});
