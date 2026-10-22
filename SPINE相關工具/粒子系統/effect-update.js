(function (root, factory) {
  'use strict';
  const merge = typeof module === 'object' && module.exports ? require('./spine-merge.js') : root.ParticleSpineMerge;
  const api = factory(merge);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleEffectUpdate = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (Merge) {
  'use strict';

  const FORMAT = 'particle-studio-effect-update', PHASES = ['in', 'loop', 'out'];
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
  const copy = value => JSON.parse(JSON.stringify(value));
  const put = (target, key, value) => Object.defineProperty(target, key, {value, enumerable: true, writable: true, configurable: true});
  const fail = value => { throw new Error('無法更新原效果：' + value); };
  function checkJson(value) {
    const visiting = new Set(); let nodes = 0;
    function visit(item, depth) {
      if (++nodes > 2000000 || depth > 100) fail('更新記錄太大或巢狀過深。');
      if (typeof item === 'number' && !Number.isFinite(item)) fail('更新記錄含非有限數值。');
      if (item === null || ['string', 'number', 'boolean', 'undefined'].includes(typeof item)) return;
      if ((!object(item) && !Array.isArray(item)) || visiting.has(item)) fail('更新記錄必須是完整 JSON。');
      visiting.add(item); Object.keys(item).forEach(key => visit(item[key], depth + 1)); visiting.delete(item);
    }
    visit(value, 0);
  }
  function name(value, label) {
    if (typeof value !== 'string' || !value.trim() || value.length > 1024 || /[\u0000-\u001f]/.test(value)) fail(label + '名稱無效。');
    return value;
  }
  function checkSize(value) {
    const text = JSON.stringify(value); let bytes = 0;
    for (const character of text) {
      const point = character.codePointAt(0); bytes += point <= 0x7f ? 1 : point <= 0x7ff ? 2 : point <= 0xffff ? 3 : 4;
      if (bytes > 8 * 1024 * 1024) fail('效果更新記錄超過 8 MiB。');
    }
  }
  function mapping(value, namespace, label, empty) {
    if (!object(value) || Object.keys(value).length > 50000 || (!empty && !Object.keys(value).length)) fail(label + '對應記錄不完整。');
    const result = {}, names = new Set();
    Object.keys(value).forEach(source => {
      name(source, label); const mapped = name(value[source], label);
      if (mapped !== namespace + '__' + source || names.has(mapped)) fail(label + '對應記錄與效果群組不符。');
      names.add(mapped); put(result, source, mapped);
    });
    return result;
  }
  function targets(manifest) {
    if (manifest.phases !== undefined) {
      if (!object(manifest.phases) || PHASES.some(phase => !object(manifest.phases[phase]))) fail('IN／LOOP／OUT 動畫記錄不完整。');
      const names = PHASES.map(phase => name(manifest.phases[phase].animationName, '動畫'));
      if (new Set(names).size !== 3) fail('IN／LOOP／OUT 動畫記錄重複。');
      return names;
    }
    return [name(manifest.animationName, '動畫')];
  }
  function particleAliases(entries) {
    const keys = Object.keys(entries).sort();
    return (keys.length === 1 && keys[0] === 'particle') ||
      (keys.length > 0 && keys.length <= 120 && keys.every((key, index) => key === 'particle_f' + String(index + 1).padStart(4, '0')));
  }
  function assetPaths(value, namespace, boneMap) {
    if (!object(value) || Object.keys(value).length > 50000) fail('圖片路徑對應記錄不完整。');
    const result = {};
    Object.keys(value).forEach(emitter => {
      if (!emitter.startsWith('em_') || !own(boneMap, emitter) || !object(value[emitter]) || !particleAliases(value[emitter])) fail('圖片路徑指定未登記的發射器或不完整連續圖。');
      const entries = {};
      Object.keys(value[emitter]).forEach(alias => {
        const path = name(value[emitter][alias], '圖片路徑');
        if (!path.startsWith(namespace + '/') || path.includes('\\') || /[:\u0000-\u001f]/.test(path) || path.split('/').some(part => !part || part === '.' || part === '..')) fail('圖片路徑必須位於記錄中的效果子目錄。');
        put(entries, alias, path);
      });
      put(result, emitter, entries);
    });
    return result;
  }
  function normalize(raw) {
    checkJson(raw);
    if (!object(raw)) fail('請載入本工具輸出的「效果更新記錄.json」或「追加清單.json」。');
    checkSize(raw);
    const rich = own(raw, 'format');
    if (rich && (raw.format !== FORMAT || ![1, 2].includes(raw.version))) fail('更新記錄格式或版本不支援。');
    const wrapper = object(raw.manifest), manifest = copy(wrapper ? raw.manifest : raw);
    const namespace = manifest.namespace;
    // Auto-allocated suffixes can extend the normal 48-character requested prefix.
    if (typeof namespace !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(namespace)) fail('效果群組名稱無效。');
    manifest.boneMap = mapping(manifest.boneMap, namespace, '骨骼', false);
    manifest.slotMap = mapping(manifest.slotMap, namespace, '插槽', true);
    if (!own(manifest.boneMap, 'root')) fail('缺少本工具的粒子根骨骼記錄。');
    if (!object(manifest.attachmentMap)) fail('附件對應記錄不完整。');
    const attachmentMap = {};
    if (Object.keys(manifest.attachmentMap).length !== Object.keys(manifest.slotMap).length) fail('附件與插槽對應數量不同。');
    Object.keys(manifest.attachmentMap).forEach(slot => {
      if (!own(manifest.slotMap, slot)) fail('附件指定未登記的粒子插槽。');
      const entries = mapping(manifest.attachmentMap[slot], namespace, '附件', false);
      if (!particleAliases(entries)) fail('附件不是本工具產生的粒子 region 或完整連續圖。');
      put(attachmentMap, slot, entries);
    });
    manifest.attachmentMap = attachmentMap;
    const hasAssetPaths = own(manifest, 'assetPathMap');
    if (rich && ((raw.version === 2 && !hasAssetPaths) || (raw.version === 1 && hasAssetPaths))) fail('圖片路徑記錄與更新格式版本不符。');
    if (hasAssetPaths) manifest.assetPathMap = assetPaths(manifest.assetPathMap, namespace, manifest.boneMap);
    if (manifest.imageDirectory !== namespace) fail('圖片目錄與效果群組不同。');
    name(manifest.parentBone, '父骨骼');
    if (manifest.emitterParents !== undefined && !object(manifest.emitterParents)) fail('發射器父骨骼記錄無效。');
    const names = targets(manifest);
    if (typeof manifest.targetVersion !== 'string' || !/^(3\.8|4\.0|4\.2)\.\d+$/.test(manifest.targetVersion)) fail('更新記錄缺少 Spine 版本。');
    const result = rich ? copy(raw) : {format: FORMAT, version: hasAssetPaths ? 2 : 1, manifest, legacy: true};
    result.manifest = manifest;
    if (rich && raw.legacy !== true) {
      if (!object(result.ownership) || !object(result.baseline)) fail('更新記錄缺少所有權或原始圖層資料。');
      ['bones', 'slots', 'animations'].forEach(key => {
        if (!Array.isArray(result.ownership[key]) || result.ownership[key].length > 50000) fail('更新記錄的 ' + key + ' 無效。');
      });
      if (result.ownership.bones.length !== Object.keys(manifest.boneMap).length || result.ownership.slots.length !== Object.keys(manifest.slotMap).length) fail('效果所有權數量與對應表不同。');
      if (result.ownership.animations.length !== names.length || result.ownership.animations.some(item => !object(item) || !names.includes(item.name)) || new Set(result.ownership.animations.map(item => item.name)).size !== names.length) fail('動畫所有權與對應表不同。');
      result.ownership.animations.forEach(item => {
        if (['created', 'hadBones', 'hadSlots'].some(key => typeof item[key] !== 'boolean')) fail('動畫所有權旗標無效。');
      });
      if (['defaultSkinCreated', 'defaultAttachmentsCreated', 'hadSkins', 'hadSlots', 'hadAnimations'].some(key => typeof result.ownership[key] !== 'boolean')) fail('原始結構所有權旗標無效。');
      if (!Array.isArray(result.baseline.slotOrder) || result.baseline.slotOrder.length > 50000 || new Set(result.baseline.slotOrder).size !== result.baseline.slotOrder.length) fail('原始插槽順序無效。');
      result.baseline.slotOrder.forEach(value => name(value, '原始插槽'));
      if (!object(result.baseline.drawOrders)) fail('原始圖層動畫記錄無效。');
      Object.keys(result.baseline.drawOrders).forEach(animation => {
        name(animation, '原始動畫'); const timelines = result.baseline.drawOrders[animation];
        if (!object(timelines) || Object.keys(timelines).some(key => !['drawOrder', 'draworder'].includes(key))) fail('原始圖層動畫記錄格式無效。');
        Object.values(timelines).forEach(frames => {
          if (!Array.isArray(frames)) fail('原始圖層動畫記錄格式無效。');
          frames.forEach(frame => { if (!object(frame)) fail('原始圖層關鍵幀無效。'); Merge.decodeOrder(result.baseline.slotOrder, frame.offsets); });
        });
      });
    }
    return result;
  }
  function boneIndexMap(json, owned) {
    const map = []; let next = 0;
    json.bones.forEach((bone, index) => { map[index] = owned.has(bone.name) ? -1 : next++; });
    return map;
  }
  function weightedVertices(attachment, boneCount, visitor) {
    const vertices = attachment.vertices;
    if (vertices === undefined) return;
    if (!Array.isArray(vertices)) fail('原附件頂點格式無效。');
    const type = attachment.type || 'region';
    const count = type === 'mesh' ? Array.isArray(attachment.uvs) ? attachment.uvs.length / 2 : NaN : ['path', 'clipping', 'boundingbox'].includes(type) ? attachment.vertexCount : undefined;
    if (count === undefined) return;
    if (!Number.isInteger(count) || count < 0) fail('原附件頂點數量無效。');
    if (vertices.length === count * 2) return;
    let offset = 0;
    for (let vertex = 0; vertex < count; vertex++) {
      const influences = vertices[offset++];
      if (!Number.isInteger(influences) || influences < 0 || influences > boneCount || offset + influences * 4 > vertices.length) fail('原加權附件的骨骼索引格式無效。');
      for (let influence = 0; influence < influences; influence++, offset += 4) {
        const index = vertices[offset];
        if (!Number.isInteger(index) || index < 0 || index >= boneCount) fail('原加權附件指定不存在的骨骼索引。');
        visitor(index, offset);
      }
    }
    if (offset !== vertices.length) fail('原加權附件頂點資料長度不符。');
  }
  function eachAttachment(json, callback) {
    (json.skins || []).forEach(skin => Object.keys(skin.attachments || {}).forEach(slot => Object.keys(skin.attachments[slot]).forEach(key => callback(skin.attachments[slot][key], skin, slot, key))));
  }
  function validate(json, receipt) {
    const info = Merge.inspect(json), manifest = receipt.manifest;
    if (info.version.split('.').slice(0, 2).join('.') !== manifest.targetVersion.split('.').slice(0, 2).join('.')) fail('更新記錄與載入骨架的 Spine 主版本不同。');
    const bones = new Map(json.bones.map(bone => [bone.name, bone])), slots = new Map((json.slots || []).map(slot => [slot.name, slot]));
    const ownedBones = new Set(Object.values(manifest.boneMap)), ownedSlots = new Set(Object.values(manifest.slotMap));
    const sourceForBone = new Map(Object.entries(manifest.boneMap).map(([source, mapped]) => [mapped, source]));
    const emitterSources = new Set(), particleSources = new Set();
    if (ownedBones.has(manifest.parentBone) || !bones.has(manifest.parentBone)) fail('原父骨骼不存在或被錯誤登記為粒子。');
    const root = bones.get(manifest.boneMap.root);
    if (!root || root.parent !== manifest.parentBone) fail('粒子根骨骼與記錄的掛接關係不同。');
    Object.keys(manifest.boneMap).forEach(source => {
      const bone = bones.get(manifest.boneMap[source]);
      if (!bone) fail('找不到記錄中的粒子骨骼：' + manifest.boneMap[source]);
      if (source === 'root') return;
      if (!source.startsWith('em_')) fail('對應表包含本工具之外的骨骼。');
      const parentSource = sourceForBone.get(bone.parent);
      if (parentSource === 'root' || own(manifest.emitterParents || {}, source)) {
        const expected = own(manifest.emitterParents || {}, source) ? manifest.emitterParents[source] : manifest.boneMap.root;
        if (bone.parent !== expected || (expected !== manifest.boneMap.root && (ownedBones.has(expected) || !bones.has(expected)))) fail('發射器掛接關係與記錄不同：' + bone.name);
        emitterSources.add(source);
      } else {
        if (typeof parentSource !== 'string' || !parentSource.startsWith('em_') || !source.startsWith(parentSource + '_p') || !/^(0|[1-9]\d*)$/.test(source.slice((parentSource + '_p').length))) fail('粒子骨骼父子關係不符合本工具記錄：' + bone.name);
        particleSources.add(source);
      }
    });
    Object.keys(manifest.emitterParents || {}).forEach(source => { if (!emitterSources.has(source)) fail('掛接記錄指定未登記的發射器。'); });
    particleSources.forEach(source => {
      if (!emitterSources.has(sourceForBone.get(bones.get(manifest.boneMap[source]).parent))) fail('粒子父骨骼不是發射器。');
      if (!own(manifest.slotMap, source + '_slot')) fail('粒子骨骼缺少相符的插槽記錄。');
    });
    Object.keys(manifest.slotMap).forEach(source => {
      const sourceBone = source.slice(0, -5), slot = slots.get(manifest.slotMap[source]);
      if (!source.endsWith('_slot') || !particleSources.has(sourceBone) || !slot || slot.bone !== manifest.boneMap[sourceBone]) fail('粒子插槽與骨骼記錄不符：' + manifest.slotMap[source]);
      const expectedAttachments = Object.values(manifest.attachmentMap[source]);
      if (slot.attachment !== undefined && slot.attachment !== null && !expectedAttachments.includes(slot.attachment)) fail('粒子插槽改用了記錄之外的附件：' + slot.name);
    });
    if (own(manifest, 'assetPathMap')) {
      const usedEmitters = new Set();
      Object.keys(manifest.slotMap).forEach(source => {
        const particle = bones.get(manifest.boneMap[source.slice(0, -5)]), emitter = sourceForBone.get(particle.parent);
        if (!own(manifest.assetPathMap, emitter) || !same(Object.keys(manifest.assetPathMap[emitter]).sort(), Object.keys(manifest.attachmentMap[source]).sort())) fail('圖片路徑與發射器粒子附件對應不完整。');
        usedEmitters.add(emitter);
      });
      if (Object.keys(manifest.assetPathMap).length !== usedEmitters.size || Object.keys(manifest.assetPathMap).some(emitter => !usedEmitters.has(emitter))) fail('圖片路徑記錄混入未使用的發射器。');
    }
    const targetNames = targets(manifest), targetSet = new Set(targetNames);
    targetNames.forEach(animation => { if (!own(json.animations || {}, animation)) fail('找不到記錄中的粒子動畫：' + animation); });
    if (!receipt.legacy) {
      ['bones', 'slots'].forEach(group => {
        const source = group === 'bones' ? bones : slots, owned = group === 'bones' ? ownedBones : ownedSlots, relation = group === 'bones' ? 'parent' : 'bone', seen = new Set();
        receipt.ownership[group].forEach(item => {
          if (!object(item) || !owned.has(item.name) || seen.has(item.name) || source.get(item.name)[relation] !== item[relation]) fail('效果所有權的 ' + group + ' 掛接關係不符。');
          seen.add(item.name);
        });
      });
      if (receipt.baseline.slotOrder.some(slot => ownedSlots.has(slot))) fail('原始插槽記錄混入了此次粒子。');
    }
    const refFail = (kind, key) => fail(kind + '「' + key + '」仍參照這組粒子；請先解除該參照再更新。');
    bones.forEach(bone => { if (!ownedBones.has(bone.name) && ownedBones.has(bone.parent)) refFail('外部骨骼', bone.name); });
    slots.forEach(slot => { if (!ownedSlots.has(slot.name) && ownedBones.has(slot.bone)) refFail('外部插槽', slot.name); });
    ['ik', 'transform', 'path', 'physics'].forEach(group => (json[group] || []).forEach(constraint => {
      if ((constraint.bones || []).some(bone => ownedBones.has(bone)) || ownedBones.has(constraint.bone) || (group === 'path' ? ownedSlots : ownedBones).has(constraint.target)) refFail('外部約束', constraint.name || group);
    }));
    (json.skins || []).forEach(skin => { if ((skin.bones || []).some(bone => ownedBones.has(bone))) refFail('皮膚骨骼清單', skin.name); });
    let attachments = 0; const foundSlots = new Set(), foundAttachments = new Set();
    const attachmentSources = new Map(Object.entries(manifest.slotMap).map(([source, mapped]) => [mapped,
      new Map(Object.entries(manifest.attachmentMap[source]).map(([original, renamed]) => [renamed, original]))]));
    const expectedAttachmentCount = Object.values(manifest.attachmentMap).reduce((sum, entries) => sum + Object.keys(entries).length, 0);
    eachAttachment(json, (attachment, skin, slot, key) => {
      if (ownedSlots.has(slot)) {
        const particle = slots.get(slot).bone, emitterSource = sourceForBone.get(bones.get(particle).parent), emitterId = emitterSource.slice(3);
        const original = attachmentSources.get(slot).get(key);
        const paths = own(manifest, 'assetPathMap') ? [manifest.assetPathMap[emitterSource][original]] : original === 'particle' ?
          [manifest.namespace + '/particle', manifest.namespace + '/emitter_' + emitterId] :
          [manifest.namespace + '/emitter_' + emitterId + '_' + (original || '').slice('particle_'.length)];
        const identity = JSON.stringify([slot, key]);
        if (skin.name !== 'default' || !original || foundAttachments.has(identity) || !object(attachment) || !['region', undefined].includes(attachment.type) || !paths.includes(attachment.path) || (attachment.name !== undefined && attachment.name !== key)) fail('粒子附件已變更結構、路徑或新增其他皮膚；請保留原效果並新增一組。');
        foundAttachments.add(identity);
        attachments++; foundSlots.add(slot); return;
      }
      if (attachment && ownedSlots.has(attachment.end)) refFail('外部裁切附件', key);
      if (attachment && ownedSlots.has(attachment.slot)) refFail('外部連結附件', key);
      if (attachment) weightedVertices(attachment, json.bones.length, index => { if (ownedBones.has(json.bones[index].name)) refFail('外部加權附件', key); });
    });
    if (foundSlots.size !== ownedSlots.size || attachments !== expectedAttachmentCount) fail('粒子附件缺漏或重複，不能確認可更新的完整效果。');
    Object.keys(json.animations || {}).forEach(animationName => {
      const animation = json.animations[animationName];
      ['bones', 'slots'].forEach(group => Object.keys(animation[group] || {}).forEach(key => {
        if ((group === 'bones' ? ownedBones : ownedSlots).has(key) && !targetSet.has(animationName)) refFail('其他動畫', animationName);
      }));
      ['deform', 'attachments'].forEach(group => Object.keys(animation[group] || {}).forEach(skin => Object.keys(animation[group][skin] || {}).forEach(slot => {
        if (ownedSlots.has(slot)) refFail('外部附件動畫', animationName);
      })));
    });
    return {ownedBones, ownedSlots, targetNames, summary: {namespace: manifest.namespace, removedBones: ownedBones.size, removedSlots: ownedSlots.size, removedAttachments: attachments, animations: targetNames.slice(), legacy: receipt.legacy === true}};
  }
  function inspectReceipt(raw, json) {
    const receipt = normalize(raw), {summary} = validate(json, receipt);
    return {receipt, summary};
  }
  function same(value, other) { return JSON.stringify(value) === JSON.stringify(other); }
  function withoutOffsets(frame) { const result = copy(frame); delete result.offsets; return result; }
  function remove(json, raw) {
    const receipt = normalize(raw), state = validate(json, receipt), result = copy(json);
    const originalOrder = (json.slots || []).map(slot => slot.name), cleanOrder = originalOrder.filter(slot => !state.ownedSlots.has(slot));
    const indices = boneIndexMap(json, state.ownedBones);
    result.bones = result.bones.filter(bone => !state.ownedBones.has(bone.name));
    if (own(result, 'slots')) result.slots = result.slots.filter(slot => !state.ownedSlots.has(slot.name));
    (result.skins || []).forEach(skin => Object.keys(skin.attachments || {}).forEach(slot => {
      if (state.ownedSlots.has(slot)) delete skin.attachments[slot];
    }));
    eachAttachment(result, attachment => { if (attachment) weightedVertices(attachment, json.bones.length, (index, offset) => { attachment.vertices[offset] = indices[index]; }); });
    Object.keys(result.animations || {}).forEach(animationName => {
      const animation = result.animations[animationName];
      ['bones', 'slots'].forEach(group => Object.keys(animation[group] || {}).forEach(key => {
        if ((group === 'bones' ? state.ownedBones : state.ownedSlots).has(key)) delete animation[group][key];
      }));
      ['drawOrder', 'draworder'].forEach(property => {
        if (!own(animation, property)) return;
        animation[property].forEach((frame, index) => {
          const clean = Merge.decodeOrder(originalOrder, frame.offsets).filter(slot => !state.ownedSlots.has(slot));
          const baseline = !receipt.legacy && own(receipt.baseline.drawOrders, animationName) && receipt.baseline.drawOrders[animationName][property];
          const old = baseline && baseline[index];
          if (old && same(cleanOrder, receipt.baseline.slotOrder) && same(withoutOffsets(frame), withoutOffsets(old)) && same(clean, Merge.decodeOrder(receipt.baseline.slotOrder, old.offsets))) {
            if (own(old, 'offsets')) frame.offsets = copy(old.offsets); else delete frame.offsets;
          } else {
            const metadata = (frame.offsets || []).filter(change => !state.ownedSlots.has(change.slot));
            const offsets = Merge.encodeOrder(cleanOrder, clean, metadata);
            if (offsets.length || own(frame, 'offsets')) frame.offsets = offsets; else delete frame.offsets;
          }
        });
      });
    });
    if (!receipt.legacy) {
      receipt.ownership.animations.forEach(item => {
        const animation = result.animations[item.name];
        if (!item.hadBones && object(animation.bones) && !Object.keys(animation.bones).length) delete animation.bones;
        if (!item.hadSlots && object(animation.slots) && !Object.keys(animation.slots).length) delete animation.slots;
        if (item.created && !Object.keys(animation).length) delete result.animations[item.name];
      });
      const skin = (result.skins || []).find(skin => skin.name === 'default');
      if (skin && receipt.ownership.defaultAttachmentsCreated && !Object.keys(skin.attachments || {}).length) delete skin.attachments;
      if (skin && receipt.ownership.defaultSkinCreated && Object.keys(skin).every(key => key === 'name' || (key === 'attachments' && !Object.keys(skin.attachments).length))) result.skins = result.skins.filter(item => item !== skin);
      ['skins', 'slots', 'animations'].forEach(key => {
        const flag = 'had' + key[0].toUpperCase() + key.slice(1);
        if (!receipt.ownership[flag] && result[key] && !Object.keys(result[key]).length) delete result[key];
      });
    }
    Merge.inspect(result);
    return {json: result, receipt, summary: state.summary};
  }
  function createReceipt(base, merged, settings) {
    Merge.inspect(base);
    if (!object(merged) || !object(merged.json) || !object(merged.manifest)) fail('請先完成粒子追加再產生更新記錄。');
    const manifest = copy(merged.manifest), normalized = normalize(manifest), ownedBones = new Set(Object.values(manifest.boneMap)), ownedSlots = new Set(Object.values(manifest.slotMap));
    const baseline = {slotOrder: (base.slots || []).map(slot => slot.name), drawOrders: {}};
    Object.keys(base.animations || {}).forEach(name => {
      const timelines = {};
      ['drawOrder', 'draworder'].forEach(property => { if (own(base.animations[name], property)) timelines[property] = copy(base.animations[name][property]); });
      if (Object.keys(timelines).length) put(baseline.drawOrders, name, timelines);
    });
    const defaultSkin = (base.skins || []).find(skin => skin.name === 'default');
    const receipt = {format: FORMAT, version: own(manifest, 'assetPathMap') ? 2 : 1, manifest, ownership: {
      bones: merged.json.bones.filter(bone => ownedBones.has(bone.name)).map(bone => ({name: bone.name, parent: bone.parent})),
      slots: (merged.json.slots || []).filter(slot => ownedSlots.has(slot.name)).map(slot => ({name: slot.name, bone: slot.bone})),
      animations: targets(manifest).map(name => ({name, created: !own(base.animations || {}, name), hadBones: own(base.animations || {}, name) && own(base.animations[name], 'bones'), hadSlots: own(base.animations || {}, name) && own(base.animations[name], 'slots')})),
      defaultSkinCreated: !defaultSkin, defaultAttachmentsCreated: !defaultSkin || !own(defaultSkin, 'attachments'), hadSkins: own(base, 'skins'), hadSlots: own(base, 'slots'), hadAnimations: own(base, 'animations')
    }, baseline};
    if (settings !== undefined) { checkJson(settings); if (!object(settings)) fail('掛接設定必須是物件。'); receipt.settings = copy(settings); }
    // Validate the generated receipt against the actual result before saving it.
    validate(merged.json, normalize(receipt));
    if (normalized.legacy !== true) fail('更新記錄建立失敗。');
    return receipt;
  }
  return {inspectReceipt, remove, createReceipt};
});
