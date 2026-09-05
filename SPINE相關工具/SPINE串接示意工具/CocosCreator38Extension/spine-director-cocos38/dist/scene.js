'use strict';

const path = require('path');
module.paths.push(path.join(Editor.App.path, 'node_modules'));

const previewOriginals = new Map();
const previewTracks = new Map();
const nativeOriginals = new Map();
const nativeClipStates = new Map();

function findCanvasNode(root, Canvas) {
    if (!root) return null;
    if (root.getComponent && root.getComponent(Canvas)) return root;
    for (const child of root.children || []) {
        const found = findCanvasNode(child, Canvas);
        if (found) return found;
    }
    return null;
}

function findNodeByUuid(root, uuid) {
    if (!root) return null;
    if (root.uuid === uuid) return root;
    for (const child of root.children || []) {
        const found = findNodeByUuid(child, uuid);
        if (found) return found;
    }
    return null;
}

function findSpineNode(root, Skeleton) {
    if (!root) return null;
    const component = root.getComponent && root.getComponent(Skeleton);
    if (component) return { node: root, skeleton: component };
    for (const child of root.children || []) {
        const found = findSpineNode(child, Skeleton);
        if (found) return found;
    }
    return null;
}

function getComponent(node, ComponentType) {
    return ComponentType && node && node.getComponent ? node.getComponent(ComponentType) : null;
}

function describeSpineNode(node, skeleton) {
    const data = skeleton && skeleton.skeletonData;
    const color = skeleton && skeleton.color;
    return {
        nodeUuid: node.uuid,
        nodeName: node.name,
        assetUuid: data ? (data.uuid || data._uuid || '') : '',
        transform: {
            x: Number(node.position.x) || 0,
            y: -(Number(node.position.y) || 0),
            rotation: -(Number(node.eulerAngles.z) || 0),
            scaleX: Math.abs(Number(node.scale.x)) || 1,
            scaleY: Math.abs(Number(node.scale.y)) || 1,
            flipX: Number(node.scale.x) < 0,
            alpha: color ? color.a / 255 : 1,
            visible: node.active !== false,
            skin: skeleton._skinName || skeleton.defaultSkin || null
        }
    };
}

function capturePreviewOriginal(node, skeleton) {
    if (previewOriginals.has(node.uuid)) return;
    const color = skeleton.color;
    previewOriginals.set(node.uuid, {
        position: { x: node.position.x, y: node.position.y, z: node.position.z },
        rotation: { x: node.eulerAngles.x, y: node.eulerAngles.y, z: node.eulerAngles.z },
        scale: { x: node.scale.x, y: node.scale.y, z: node.scale.z },
        active: node.active,
        color: color ? { r: color.r, g: color.g, b: color.b, a: color.a } : null,
        timeScale: skeleton.timeScale,
        cacheMode: skeleton.defaultCacheMode,
        animation: skeleton.animation || '',
        loop: !!skeleton.loop
    });
}

function restorePreviewInternal() {
    const { director, sp, Color, v3 } = require('cc');
    const scene = director.getScene();
    if (!scene) {
        previewOriginals.clear();
        previewTracks.clear();
        return { ok: false, restored: 0 };
    }

    let restored = 0;
    for (const [uuid, original] of previewOriginals) {
        const node = findNodeByUuid(scene, uuid);
        if (!node) continue;
        const skeleton = node.getComponent(sp.Skeleton);
        node.active = original.active;
        node.setPosition(v3(original.position.x, original.position.y, original.position.z));
        node.setRotationFromEuler(original.rotation.x, original.rotation.y, original.rotation.z);
        node.setScale(v3(original.scale.x, original.scale.y, original.scale.z));
        if (skeleton) {
            skeleton.timeScale = original.timeScale;
            skeleton.setAnimationCacheMode(original.cacheMode);
            if (original.color) {
                skeleton.color = new Color(
                    original.color.r,
                    original.color.g,
                    original.color.b,
                    original.color.a
                );
            }
            skeleton.clearTracks();
            if (original.animation) skeleton.setAnimation(0, original.animation, original.loop);
        }
        restored += 1;
    }
    previewOriginals.clear();
    previewTracks.clear();
    return { ok: true, restored };
}

function componentCapabilities(node, cc) {
    const skeleton = getComponent(node, cc.sp && cc.sp.Skeleton);
    const particle2d = getComponent(node, cc.ParticleSystem2D);
    const particle3d = getComponent(node, cc.ParticleSystem);
    const animation = getComponent(node, cc.Animation);
    const runtimeData = skeleton && skeleton.skeletonData && skeleton.skeletonData.getRuntimeData
        ? skeleton.skeletonData.getRuntimeData(true)
        : null;
    const spineAnimations = runtimeData && Array.isArray(runtimeData.animations)
        ? runtimeData.animations.map((item) => ({
            name: item.name,
            duration: Number(item.duration) || 0
        }))
        : [];
    const animationClips = animation
        ? (animation.clips || []).filter(Boolean).map((clip) => ({
            name: clip.name,
            duration: Number(clip.duration) || 0
        }))
        : [];
    return {
        spine: !!skeleton,
        particle2d: !!particle2d,
        particle3d: !!particle3d,
        animation: !!animation,
        spineAnimations,
        animationClips
    };
}

function getSceneNodePath(node) {
    const names = [];
    let current = node;
    while (current && current.parent) {
        names.unshift(current.name);
        current = current.parent;
    }
    return names.join('/');
}

function describeTimelineTransform(node, cc) {
    const opacity = getComponent(node, cc.UIOpacity);
    return {
        x: Number(node.position.x) || 0,
        y: Number(node.position.y) || 0,
        z: Number(node.position.z) || 0,
        rx: Number(node.eulerAngles.x) || 0,
        ry: Number(node.eulerAngles.y) || 0,
        rz: Number(node.eulerAngles.z) || 0,
        sx: Number(node.scale.x) || 0,
        sy: Number(node.scale.y) || 0,
        sz: Number(node.scale.z) || 0,
        active: node.active !== false,
        opacity: opacity ? Number(opacity.opacity) : 255
    };
}

function describeTimelineNode(node, cc) {
    return {
        nodeUuid: node.uuid,
        nodeName: node.name,
        nodePath: getSceneNodePath(node),
        transform: describeTimelineTransform(node, cc),
        capabilities: componentCapabilities(node, cc)
    };
}

function captureNativeOriginal(node, cc) {
    if (nativeOriginals.has(node.uuid)) return;
    const skeleton = getComponent(node, cc.sp && cc.sp.Skeleton);
    const particle2d = getComponent(node, cc.ParticleSystem2D);
    const particle3d = getComponent(node, cc.ParticleSystem);
    const animation = getComponent(node, cc.Animation);
    const opacity = getComponent(node, cc.UIOpacity);
    nativeOriginals.set(node.uuid, {
        transform: describeTimelineNode(node, cc).transform,
        spine: skeleton ? {
            enabled: skeleton.enabled !== false,
            timeScale: skeleton.timeScale,
            paused: !!skeleton.paused,
            cacheMode: skeleton.defaultCacheMode,
            animation: skeleton.animation || '',
            loop: !!skeleton.loop
        } : null,
        particle2d: particle2d ? {
            stopped: !!particle2d._stopped,
            enabled: particle2d.enabled !== false
        } : null,
        particle3d: particle3d ? {
            playing: !!particle3d.isPlaying,
            paused: !!particle3d.isPaused
        } : null,
        animation: animation ? {
            playing: (animation.clips || []).filter(Boolean)
                .map((clip) => animation.getState(clip.name))
                .filter((state) => state && state.isPlaying)
                .map((state) => state.name)
        } : null,
        hadOpacity: !!opacity
    });
}

function restoreNativeInternal() {
    const cc = require('cc');
    const scene = cc.director.getScene();
    if (!scene) {
        nativeOriginals.clear();
        nativeClipStates.clear();
        return { ok: false, restored: 0 };
    }
    let restored = 0;
    for (const [uuid, original] of nativeOriginals) {
        const node = findNodeByUuid(scene, uuid);
        if (!node) continue;
        const state = original.transform;
        node.active = state.active;
        node.setPosition(cc.v3(state.x, state.y, state.z));
        node.setRotationFromEuler(state.rx, state.ry, state.rz);
        node.setScale(cc.v3(state.sx, state.sy, state.sz));
        const opacity = getComponent(node, cc.UIOpacity);
        if (opacity) opacity.opacity = state.opacity;

        const skeleton = getComponent(node, cc.sp && cc.sp.Skeleton);
        if (skeleton && original.spine) {
            skeleton.enabled = true;
            skeleton.clearTracks();
            skeleton.timeScale = original.spine.timeScale;
            skeleton.paused = original.spine.paused;
            skeleton.setAnimationCacheMode(original.spine.cacheMode);
            if (original.spine.animation) {
                skeleton.setAnimation(0, original.spine.animation, original.spine.loop);
            } else {
                skeleton.setToSetupPose();
                skeleton.updateAnimation(0);
            }
            skeleton.enabled = original.spine.enabled;
            if (typeof skeleton._markForUpdateRenderData === 'function') {
                skeleton._markForUpdateRenderData();
            }
        }
        const particle2d = getComponent(node, cc.ParticleSystem2D);
        if (particle2d && original.particle2d) {
            particle2d.enabled = true;
            particle2d.resetSystem();
            if (original.particle2d.stopped) particle2d.stopSystem();
            particle2d.enabled = original.particle2d.enabled;
            if (typeof particle2d._markForUpdateRenderData === 'function') {
                particle2d._markForUpdateRenderData();
            }
        }
        const particle3d = getComponent(node, cc.ParticleSystem);
        if (particle3d && original.particle3d) {
            particle3d.stop();
            if (original.particle3d.playing || original.particle3d.paused) {
                particle3d.play();
                if (original.particle3d.paused) particle3d.pause();
            }
        }
        const animation = getComponent(node, cc.Animation);
        if (animation && original.animation) {
            animation.stop();
            for (const name of original.animation.playing) animation.play(name);
        }
        restored += 1;
    }
    nativeOriginals.clear();
    nativeClipStates.clear();
    return { ok: true, restored };
}

function applySpineClip(node, skeleton, clip, cc, owned) {
    const stateKey = `${node.uuid}:spine`;
    if (!clip) {
        if (owned) {
            if (nativeClipStates.get(stateKey) !== 'off') {
                skeleton.enabled = true;
                skeleton.clearTrack(0);
                skeleton.setToSetupPose();
                skeleton.updateAnimation(0);
            }
            skeleton.enabled = false;
            nativeClipStates.set(stateKey, 'off');
            if (typeof skeleton._markForUpdateRenderData === 'function') {
                skeleton._markForUpdateRenderData();
            }
        } else if (nativeClipStates.has(stateKey)) {
            const original = nativeOriginals.get(node.uuid);
            skeleton.enabled = original && original.spine
                ? original.spine.enabled
                : true;
            skeleton.clearTrack(0);
            skeleton.setToSetupPose();
            skeleton.updateAnimation(0);
            nativeClipStates.delete(stateKey);
        }
        return;
    }
    skeleton.enabled = true;
    const signature = `${clip.id}|${clip.animation}|${!!clip.loop}`;
    skeleton.setAnimationCacheMode(cc.sp.Skeleton.AnimationCacheMode.REALTIME);
    skeleton.paused = false;
    skeleton.timeScale = 1;
    skeleton.clearTrack(0);
    skeleton.setToSetupPose();
    const entry = skeleton.setAnimation(0, clip.animation, !!clip.loop);
    if (!entry) {
        nativeClipStates.delete(stateKey);
        skeleton.timeScale = 0;
        return;
    }
    const targetTime = Math.max(0, Number(clip.localTime) || 0);
    entry.trackTime = targetTime;
    const animationState = skeleton.getState && skeleton.getState();
    const runtimeSkeleton = skeleton._skeleton;
    if (animationState && runtimeSkeleton && typeof animationState.apply === 'function') {
        animationState.update(0);
        animationState.apply(runtimeSkeleton);
        if (typeof runtimeSkeleton.updateWorldTransform === 'function') {
            runtimeSkeleton.updateWorldTransform();
        }
        if (typeof skeleton._markForUpdateRenderData === 'function') {
            skeleton._markForUpdateRenderData();
        }
    } else {
        entry.trackTime = 0;
        skeleton.updateAnimation(targetTime);
    }
    skeleton.timeScale = 0;
    nativeClipStates.set(stateKey, signature);
}

function applyAnimationClip(node, animation, clip) {
    const stateKey = `${node.uuid}:animation`;
    if (!clip) {
        if (nativeClipStates.has(stateKey)) {
            animation.stop();
            nativeClipStates.delete(stateKey);
        }
        return;
    }
    const signature = `${clip.id}|${clip.animation}`;
    if (nativeClipStates.get(stateKey) !== signature) {
        animation.play(clip.animation);
        nativeClipStates.set(stateKey, signature);
    }
    const state = animation.getState(clip.animation);
    if (state) {
        state.setTime(Math.max(0, Number(clip.localTime) || 0));
        state.sample();
        state.pause();
    }
}

function applyParticle2DClip(node, particle, clip, playing) {
    const stateKey = `${node.uuid}:particle2d`;
    if (!clip) {
        if (nativeClipStates.get(stateKey) !== 'off' || particle.enabled !== false) {
            particle.enabled = true;
            particle.resetSystem();
            particle.stopSystem();
            const renderData = particle._simulator && particle._simulator.renderData;
            if (renderData) {
                if (typeof renderData.reset === 'function') renderData.reset();
                if (typeof renderData.resize === 'function') renderData.resize(0, 0);
                if (typeof renderData.setRenderDrawInfoAttributes === 'function') {
                    renderData.setRenderDrawInfoAttributes();
                }
            }
            particle.enabled = false;
            if (typeof particle._markForUpdateRenderData === 'function') {
                particle._markForUpdateRenderData();
            }
        }
        nativeClipStates.set(stateKey, 'off');
        return;
    }
    const signature = `${clip.id}|${playing ? 'play' : 'scrub'}`;
    if (nativeClipStates.get(stateKey) !== signature || !playing) {
        particle.enabled = true;
        if (typeof particle._flushAssembler === 'function') {
            particle._flushAssembler();
        }
        particle.resetSystem();
        nativeClipStates.set(stateKey, signature);
        if (!playing && particle._simulator && typeof particle._simulator.step === 'function') {
            let remaining = Math.max(0, Number(clip.localTime) || 0);
            while (remaining > 0) {
                const step = Math.min(1 / 30, remaining);
                particle._simulator.step(step);
                remaining -= step;
            }
            particle._simulator.active = false;
            particle._simulator.finished = true;
            particle._stopped = false;
            if (typeof particle._markForUpdateRenderData === 'function') {
                particle._markForUpdateRenderData();
            }
        }
    }
}

function applyParticle3DClip(node, particle, clip, playing) {
    const stateKey = `${node.uuid}:particle3d`;
    if (!clip) {
        if (nativeClipStates.has(stateKey)) {
            particle.stop();
            nativeClipStates.delete(stateKey);
        }
        return;
    }
    const signature = clip.id;
    if (nativeClipStates.get(stateKey) !== signature || !playing) {
        particle.stop();
        particle.play();
        if (!playing) particle.pause();
        nativeClipStates.set(stateKey, signature);
    }
}

exports.load = function load() {};
exports.unload = function unload() {
    restorePreviewInternal();
    restoreNativeInternal();
};

exports.methods = {
    describeTimelineNodes(nodeUuids) {
        const cc = require('cc');
        const scene = cc.director.getScene();
        if (!scene) throw new Error('目前沒有開啟的 Scene。');
        const results = [];
        for (const uuid of nodeUuids || []) {
            const node = findNodeByUuid(scene, uuid);
            if (node) results.push(describeTimelineNode(node, cc));
        }
        return results;
    },

    applyNativeTimeline(payload) {
        const cc = require('cc');
        const scene = cc.director.getScene();
        if (!scene || !payload || !Array.isArray(payload.states)) {
            return { ok: false, updated: 0 };
        }
        let updated = 0;
        const appliedNodes = [];
        for (const item of payload.states) {
            const node = findNodeByUuid(scene, item.nodeUuid);
            if (!node) continue;
            captureNativeOriginal(node, cc);
            const transform = item.transform || {};
            node.active = transform.active !== false;
            node.setPosition(cc.v3(
                Number(transform.x) || 0,
                Number(transform.y) || 0,
                Number(transform.z) || 0
            ));
            node.setRotationFromEuler(
                Number(transform.rx) || 0,
                Number(transform.ry) || 0,
                Number(transform.rz) || 0
            );
            node.setScale(cc.v3(
                Number.isFinite(Number(transform.sx)) ? Number(transform.sx) : 1,
                Number.isFinite(Number(transform.sy)) ? Number(transform.sy) : 1,
                Number.isFinite(Number(transform.sz)) ? Number(transform.sz) : 1
            ));
            const opacity = getComponent(node, cc.UIOpacity);
            if (opacity && Number.isFinite(Number(transform.opacity))) {
                opacity.opacity = Math.max(0, Math.min(255, Number(transform.opacity)));
            }

            const clips = item.clips || [];
            const skeleton = getComponent(node, cc.sp && cc.sp.Skeleton);
            if (skeleton) applySpineClip(
                node,
                skeleton,
                clips.find((clip) => clip.type === 'spine'),
                cc,
                Array.isArray(item.ownedTypes) && item.ownedTypes.includes('spine')
            );
            const animation = getComponent(node, cc.Animation);
            if (animation) applyAnimationClip(node, animation, clips.find((clip) => clip.type === 'animation'));
            const particle2d = getComponent(node, cc.ParticleSystem2D);
            if (particle2d) applyParticle2DClip(
                node,
                particle2d,
                clips.find((clip) => clip.type === 'particle2d'),
                !!payload.playing
            );
            const particle3d = getComponent(node, cc.ParticleSystem);
            if (particle3d) applyParticle3DClip(
                node,
                particle3d,
                clips.find((clip) => clip.type === 'particle3d'),
                !!payload.playing
            );
            updated += 1;
            appliedNodes.push(node);
        }
        const transforms = appliedNodes.map((node) => ({
            nodeUuid: node.uuid, transform: describeTimelineTransform(node, cc)
        }));
        return { ok: true, updated, time: Number(payload.time) || 0, transforms };
    },

    restoreNativeTimeline() {
        return restoreNativeInternal();
    },

    inspectSelectedSpine(nodeUuids) {
        const { director, sp } = require('cc');
        const scene = director.getScene();
        if (!scene) throw new Error('目前沒有開啟的場景。');
        for (const uuid of nodeUuids || []) {
            const selected = findNodeByUuid(scene, uuid);
            const found = findSpineNode(selected, sp.Skeleton);
            if (found && found.skeleton.skeletonData) {
                return describeSpineNode(found.node, found.skeleton);
            }
        }
        return null;
    },

    async ensurePreviewNode(options) {
        const { assetManager, director, Node, Canvas, sp } = require('cc');
        const scene = director.getScene();
        if (!scene) throw new Error('目前沒有開啟的場景。');
        if (!options || !options.assetUuid) throw new Error('缺少 Spine SkeletonData UUID。');

        const skeletonData = await new Promise((resolve, reject) => {
            assetManager.loadAny(options.assetUuid, (error, asset) => {
                if (error || !asset) reject(error || new Error('SkeletonData 載入失敗。'));
                else resolve(asset);
            });
        });

        const parent = findCanvasNode(scene, Canvas) || scene;
        const node = new Node(`[SpineDirector] ${options.name || 'Spine'}`);
        parent.addChild(node);
        if (options.position) {
            node.setPosition(
                Number(options.position.x) || 0,
                Number(options.position.y) || 0,
                0
            );
        }
        const skeleton = node.addComponent(sp.Skeleton);
        skeleton.skeletonData = skeletonData;
        return describeSpineNode(node, skeleton);
    },

    applyPreview(payload) {
        const { director, sp, Color, v3 } = require('cc');
        const scene = director.getScene();
        if (!scene || !payload || !Array.isArray(payload.characters)) {
            return { ok: false, updated: 0 };
        }

        let updated = 0;
        for (const state of payload.characters) {
            if (!state || !state.nodeUuid) continue;
            const node = findNodeByUuid(scene, state.nodeUuid);
            if (!node) continue;
            const skeleton = node.getComponent(sp.Skeleton);
            if (!skeleton || !skeleton.skeletonData) continue;

            capturePreviewOriginal(node, skeleton);
            skeleton.setAnimationCacheMode(sp.Skeleton.AnimationCacheMode.REALTIME);
            skeleton.timeScale = 0;

            node.active = state.visible !== false;
            node.setPosition(v3(
                Number(state.x) || 0,
                -(Number(state.y) || 0),
                node.position.z
            ));
            node.setRotationFromEuler(
                node.eulerAngles.x,
                node.eulerAngles.y,
                -(Number(state.rotation) || 0)
            );
            node.setScale(v3(
                Number.isFinite(Number(state.scaleX)) ? Number(state.scaleX) : 1,
                Number.isFinite(Number(state.scaleY)) ? Number(state.scaleY) : 1,
                node.scale.z
            ));

            const currentColor = skeleton.color;
            const numericAlpha = Number(state.alpha);
            const alpha = Math.round(Math.max(0, Math.min(1, Number.isFinite(numericAlpha) ? numericAlpha : 1)) * 255);
            skeleton.color = new Color(currentColor.r, currentColor.g, currentColor.b, alpha);

            const trackMap = previewTracks.get(node.uuid) || new Map();
            const activeTrackIndexes = new Set();
            for (const animation of state.animations || []) {
                const trackIndex = Number(animation.track) || 0;
                activeTrackIndexes.add(trackIndex);
                const signature = `${animation.name}|${!!animation.loop}`;
                let entry = skeleton.getState() && skeleton.getState().getCurrent(trackIndex);
                if (trackMap.get(trackIndex) !== signature || !entry) {
                    entry = skeleton.setAnimation(trackIndex, animation.name, !!animation.loop);
                    trackMap.set(trackIndex, signature);
                }
                if (entry) {
                    entry.trackTime = Math.max(0, Number(animation.time) || 0);
                    entry.mixDuration = Math.max(0, Number(animation.mixDuration) || 0);
                }
            }

            for (const trackIndex of [...trackMap.keys()]) {
                if (activeTrackIndexes.has(trackIndex)) continue;
                skeleton.clearTrack(trackIndex);
                trackMap.delete(trackIndex);
            }
            previewTracks.set(node.uuid, trackMap);
            skeleton.setToSetupPose();
            skeleton.updateAnimation(0);
            updated += 1;
        }
        return { ok: true, updated, time: Number(payload.time) || 0 };
    },

    restorePreview() {
        return restorePreviewInternal();
    },

    createPlayerNode(options) {
        const { director, Node, Canvas } = require('cc');
        const scene = director.getScene();
        if (!scene) {
            throw new Error('目前沒有開啟的場景。');
        }

        const parent = findCanvasNode(scene, Canvas);
        if (!parent) {
            throw new Error('場景中找不到 Canvas；請先建立 Canvas，再建立播放節點。');
        }

        const nodeName = options.nodeName || options.projectSlug || 'SpineDirector';
        const node = new Node(nodeName);
        parent.addChild(node);

        const component = node.addComponent(options.className);
        if (!component) {
            node.destroy();
            throw new Error(`找不到元件 ${options.className}。請等待 Creator 完成腳本編譯後再試一次。`);
        }

        return {
            ok: true,
            nodeName,
            uuid: node.uuid,
            message: '播放節點已建立在 Canvas 下；請儲存場景。'
        };
    }
};
