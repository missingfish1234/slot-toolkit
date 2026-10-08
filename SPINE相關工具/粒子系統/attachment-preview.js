(function (root, factory) {
  'use strict';
  const node = typeof module === 'object' && module.exports;
  const api = factory(node ? require('./core.js') : root.ParticleCore,
    node ? require('./preview.js') : root.ParticlePreview,
    node ? require('./spine-merge.js') : root.ParticleSpineMerge,
    node ? require('./spine-runtime-preview.js') : root.ParticleSpineRuntimePreview);
  if (node) module.exports = api;
  root.ParticleAttachmentPreview = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (Core, Preview, Merge, Runtime) {
  'use strict';
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const mod = (value, duration) => ((value % duration) + duration) % duration;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  function point(matrix, value) { return {x: matrix.x + matrix.a * value.x + matrix.b * value.y, y: matrix.y + matrix.c * value.x + matrix.d * value.y}; }
  function inverseDelta(matrix, value) {
    const det = matrix.a * matrix.d - matrix.b * matrix.c;
    if (!Number.isFinite(det) || Math.abs(det) < 1e-10) return null;
    return {x: (matrix.d * value.x - matrix.b * value.y) / det, y: (-matrix.c * value.x + matrix.a * value.y) / det};
  }
  function resolveTimeline(session, localBake, phase) {
    if (!session || session.settings.enabled === false) throw new Error('請先載入並啟用原骨架。');
    const flow = ['in', 'loop', 'out'].includes(phase), settings = session.settings;
    const target = flow ? settings.flowTargets && settings.flowTargets[phase] : settings;
    if (!target) throw new Error('請先設定 ' + String(phase).toUpperCase() + ' 的目標動畫。');
    const info = Merge.inspect(session.json), animationName = target.animationName;
    if (typeof animationName !== 'string' || !animationName.trim()) throw new Error('請設定預覽的目標動畫名稱。');
    const animationMode = target.animationMode || (own(session.json.animations || {}, animationName) ? 'existing' : 'new');
    const original = info.animations.find(item => item.name === animationName);
    if (animationMode === 'existing' && !original) throw new Error('找不到原動畫：' + animationName);
    if (animationMode === 'new' && original) throw new Error('新動畫名稱已存在，請改名或選擇追加原動畫。');
    const startTime = target.startTime || 0, fxDuration = localBake.duration;
    if (!Number.isFinite(startTime) || startTime < 0 || startTime > 600) throw new Error('預覽開始時間必須是 0–600 秒。');
    if (flow && phase === 'loop' && (startTime !== 0 || original && original.duration > fxDuration + 1e-6)) throw new Error('原 LOOP 長度不能超過粒子 LOOP，且必須從 0 秒開始；請調整掛接設定。');
    return {phase: flow ? phase : null, animationName, animationMode, rigAnimationName: original ? animationName : null,
      startTime, endTime: Math.round((startTime + fxDuration) * 1e6) / 1e6, fxDuration,
      duration: Math.max(original ? original.duration : 0, startTime + fxDuration), loop: flow ? phase === 'loop' : localBake.loop,
      holdsEnd: flow && phase === 'in'};
  }
  function transform(state, parent, fallback) {
    const image = state.image || fallback, angle = state.rotation * Math.PI / 180;
    const width = image ? image.width : 64, height = image ? image.height : 64;
    const local = state.matrix || {a: Math.cos(angle) * state.width / width, b: -Math.sin(angle) * state.height / height,
      c: Math.sin(angle) * state.width / width, d: Math.cos(angle) * state.height / height, x: state.x, y: state.y};
    const matrix = {a: parent.a * local.a + parent.b * local.c, b: parent.a * local.b + parent.b * local.d,
      c: parent.c * local.a + parent.d * local.c, d: parent.c * local.b + parent.d * local.d,
      ...point(parent, local)};
    const vertices = [];
    [[-width / 2, -height / 2], [-width / 2, height / 2], [width / 2, height / 2], [width / 2, -height / 2]].forEach(([x, y]) => {
      const value = point(matrix, {x, y}); vertices.push(value.x, value.y);
    });
    return {...state, type: 'region', image, matrix, x: matrix.x, y: matrix.y,
      width: width * Math.hypot(matrix.a, matrix.c), height: height * Math.hypot(matrix.b, matrix.d),
      rotation: Math.atan2(matrix.c, matrix.a) * 180 / Math.PI, vertices, uvs: [0, 1, 0, 0, 1, 0, 1, 1], triangles: [0, 1, 2, 2, 3, 0], isParticle: true};
  }
  function compile(options) {
    const session = options.session, localBake = options.localBake, phase = options.phase;
    const timeline = resolveTimeline(session, localBake, phase);
    const rig = Runtime.compile({json: session.json}, {animationName: timeline.rigAnimationName,
      duration: timeline.duration, loop: timeline.loop, assets: session.assets, skinName: options.skinName || undefined});
    const emitters = localBake.project.emitters, emitterOrder = emitters.slice().reverse().map(e => e.id);
    const settings = session.settings, parentFor = id => (settings.emitterParents || {})['em_' + id] || settings.parentBone;
    let reader = null, emitterBySlot = new Map();
    if (options.baked && options.exported) {
      const output = options.exported;
      const name = phase ? output.manifest.phases[phase].animationName : 'effect';
      const single = {json: {...output.json, animations: {effect: output.json.animations[name]}}, images: output.images};
      reader = Preview.compile(single, localBake, options.fallbackImage);
      const parentByBone = new Map(output.json.bones.map(bone => [bone.name, bone.parent]));
      const idByBone = new Map(emitters.map(e => ['em_' + e.id, e.id]));
      output.json.slots.forEach(slot => emitterBySlot.set(slot.name, idByBone.get(parentByBone.get(slot.bone))));
    }
    function clock(time) {
      if (!Number.isFinite(time)) throw new Error('預覽時間必須是有限數值。');
      return timeline.loop ? mod(time, timeline.duration) : clamp(time, 0, timeline.duration);
    }
    function localTime(time) {
      const at = clock(time);
      if (at < timeline.startTime || (!timeline.holdsEnd && at >= timeline.endTime)) return null;
      return clamp(at - timeline.startTime, 0, timeline.fxDuration);
    }
    function emitterFrame(id, time) {
      const bone = rig.getBone(parentFor(id), clock(time));
      return bone && bone.active ? {parentBone: bone.name, matrix: bone.matrix, active: true,
        draggable: inverseDelta(bone.matrix, {x: 1, y: 0}) !== null} : null;
    }
    function sample(time) {
      const at = clock(time), original = rig.sample(at).map(item => ({...item, isParticle: false}));
      const local = localTime(time), particles = [];
      if (local !== null) {
        const states = reader ? reader.sample(local) : Core.sample(localBake, local);
        for (let state of states) {
          if (state.alpha <= 0 || state.alive === false) continue;
          const id = state.emitterId || emitterBySlot.get(state.slotName), frame = emitterFrame(id, at);
          if (!frame) continue;
          if (!reader && options.getProject) {
            const current = options.getProject().emitters.find(e => e.id === id), old = emitters.find(e => e.id === id);
            if (!current || !current.enabled || !old) continue;
            const dx = current.x - old.x, dy = current.y - old.y;
            state = {...state, x: state.x + dx, y: state.y + dy};
            if (state.matrix) state.matrix = {...state.matrix, x: state.matrix.x + dx, y: state.matrix.y + dy};
          }
          const transformed = transform(state, frame.matrix, options.fallbackImage);
          transformed.emitterId = id; transformed.slotName = state.slotName || 'em_' + id + '_p' + state.index + '_slot';
          particles.push(transformed);
        }
        particles.sort((a, b) => emitterOrder.indexOf(a.emitterId) - emitterOrder.indexOf(b.emitterId));
      }
      const order = rig.slotOrder(at), after = settings.drawOrder === 'after' ? settings.afterSlot : settings.drawOrder === 'front' ? order[order.length - 1] : null;
      const clips = after ? rig.clipsAfterSlot(after, at) : [];
      particles.forEach(item => { item.clipPolygons = clips; });
      if (settings.drawOrder === 'back') return particles.concat(original);
      if (settings.drawOrder !== 'after') return original.concat(particles);
      const grouped = new Map(); original.forEach(item => { if (!grouped.has(item.slotName)) grouped.set(item.slotName, []); grouped.get(item.slotName).push(item); });
      const result = [];
      order.forEach(name => { result.push(...(grouped.get(name) || [])); if (name === settings.afterSlot) result.push(...particles); });
      return result;
    }
    return {timeline, metadata: rig.metadata, rig, sample, localTime, emitterFrame,
      bones(time) { return rig.bones(clock(time)); },
      emitterPoint(id, value, time) { const frame = emitterFrame(id, time); return frame ? point(frame.matrix, value) : null; }};
  }
  return {compile, resolveTimeline, point, inverseDelta, transform};
});
