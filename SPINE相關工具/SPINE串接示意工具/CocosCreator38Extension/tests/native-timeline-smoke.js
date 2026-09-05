'use strict';

const assert = require('assert');
const Module = require('module');
const fs = require('fs');
const path = require('path');

class Skeleton {}
class ParticleSystem2D {}
class ParticleSystem {}
class Animation {}
class UIOpacity {}

class MockNode {
    constructor(uuid, name) {
        this.uuid = uuid;
        this.name = name;
        this.children = [];
        this.active = true;
        this.position = { x: 10, y: 20, z: 0 };
        this.eulerAngles = { x: 0, y: 0, z: 5 };
        this.scale = { x: 1, y: 1, z: 1 };
        this.components = new Map();
    }
    getComponent(type) { return this.components.get(type) || null; }
    setPosition(value) { this.position = { ...value }; }
    setRotationFromEuler(x, y, z) { this.eulerAngles = { x, y, z }; }
    setScale(value) { this.scale = { ...value }; }
}

const root = new MockNode('root', 'Scene');
const target = new MockNode('node-1', 'Boom');
const particleTarget = new MockNode('node-2', 'Particle2D');
root.children.push(target, particleTarget);

const skeleton = {
    enabled: true,
    skeletonData: {
        getRuntimeData: () => ({ animations: [{ name: 'idle', duration: 2 }] })
    },
    timeScale: 1,
    defaultCacheMode: 0,
    animation: '',
    loop: false,
    appliedTime: -1,
    renderDirty: false,
    worldUpdated: false,
    _skeleton: {
        updateWorldTransform() { skeleton.worldUpdated = true; }
    },
    setAnimationCacheMode(value) { this.defaultCacheMode = value; },
    setAnimation(index, name, loop) {
        this.animation = name;
        this.loop = loop;
        this.entry = { trackTime: 0 };
        return this.entry;
    },
    getState() {
        return {
            getCurrent: () => this.entry,
            update() {},
            apply: () => { this.appliedTime = this.entry ? this.entry.trackTime : -1; }
        };
    },
    clearTrack() { this.entry = null; },
    clearTracks() { this.entry = null; },
    setToSetupPose() {},
    _markForUpdateRenderData() { this.renderDirty = true; },
    updateAnimation(deltaTime) {
        if (this.entry) this.entry.trackTime += Number(deltaTime) || 0;
    }
};
const opacity = { opacity: 255 };
target.components.set(Skeleton, skeleton);
target.components.set(UIOpacity, opacity);

const particle2d = {
    enabled: true,
    _stopped: false,
    flushed: false,
    renderDirty: false,
    resetCount: 0,
    stopCount: 0,
    _simulator: {
        active: true,
        finished: false,
        renderData: null,
        elapsed: 0,
        step(deltaTime) {
            if (!this.renderData) return;
            this.elapsed += deltaTime;
        }
    },
    _flushAssembler() {
        this.flushed = true;
        this._simulator.renderData = {};
    },
    resetSystem() {
        this.resetCount += 1;
        this._stopped = false;
        this._simulator.active = true;
        this._simulator.finished = false;
        this._simulator.elapsed = 0;
    },
    stopSystem() {
        this.stopCount += 1;
        this._stopped = true;
        this._simulator.active = false;
    },
    _markForUpdateRenderData() { this.renderDirty = true; }
};
particleTarget.components.set(ParticleSystem2D, particle2d);

const cc = {
    director: { getScene: () => root },
    sp: {
        Skeleton,
        Skeleton: Object.assign(Skeleton, { AnimationCacheMode: { REALTIME: 0 } })
    },
    ParticleSystem2D,
    ParticleSystem,
    Animation,
    UIOpacity,
    v3: (x, y, z) => ({ x, y, z })
};

const originalLoad = Module._load;
Module._load = function patchedLoad(request, parent, isMain) {
    if (request === 'cc') return cc;
    return originalLoad.call(this, request, parent, isMain);
};
global.Editor = { App: { path: process.cwd() } };

const extensionRoot = fs.existsSync(path.join(__dirname, '..', 'dist')) ? path.join(__dirname, '..') : path.join(__dirname, '..', 'spine-director-cocos38');
const sceneExtension = require(path.join(extensionRoot, 'dist', 'scene.js'));
const described = sceneExtension.methods.describeTimelineNodes(['node-1']);
assert.equal(described.length, 1);
assert.equal(described[0].capabilities.spine, true);
assert.equal(described[0].capabilities.spineAnimations[0].name, 'idle');

const preview = sceneExtension.methods.applyNativeTimeline({
    time: 1,
    playing: false,
    states: [{
        nodeUuid: 'node-1',
        ownedTypes: ['spine'],
        transform: {
            x: 100, y: 200, z: 0,
            rx: 0, ry: 0, rz: 45,
            sx: 2, sy: 2, sz: 1,
            active: true, opacity: 128
        },
        clips: [{
            id: 'clip-1',
            type: 'spine',
            animation: 'idle',
            loop: false,
            localTime: 1
        }]
    }]
});
assert.equal(preview.updated, 1);
assert.equal(target.position.x, 100);
assert.equal(target.eulerAngles.z, 45);
assert.equal(skeleton.animation, 'idle');
assert.equal(skeleton.entry.trackTime, 1);
assert.equal(skeleton.appliedTime, 1);
assert.equal(skeleton.worldUpdated, true);
assert.equal(skeleton.renderDirty, true);
assert.equal(opacity.opacity, 128);

const spineOutsidePreview = sceneExtension.methods.applyNativeTimeline({
    time: 2,
    playing: false,
    states: [{
        nodeUuid: 'node-1',
        ownedTypes: ['spine'],
        transform: {
            x: 100, y: 200, z: 0,
            rx: 0, ry: 0, rz: 45,
            sx: 2, sy: 2, sz: 1,
            active: true, opacity: 128
        },
        clips: []
    }]
});
assert.equal(spineOutsidePreview.updated, 1);
assert.equal(skeleton.enabled, false);

const particlePreview = sceneExtension.methods.applyNativeTimeline({
    time: 0,
    playing: false,
    states: [{
        nodeUuid: 'node-2',
        transform: {
            x: 0, y: 0, z: 0,
            rx: 0, ry: 0, rz: 0,
            sx: 1, sy: 1, sz: 1,
            active: true, opacity: 255
        },
        clips: []
    }]
});
assert.equal(particlePreview.updated, 1);
assert.equal(particle2d.enabled, false);
assert.equal(particle2d._stopped, true);

const particleInsidePreview = sceneExtension.methods.applyNativeTimeline({
    time: 0.5,
    playing: false,
    states: [{
        nodeUuid: 'node-2',
        transform: {
            x: 0, y: 0, z: 0,
            rx: 0, ry: 0, rz: 0,
            sx: 1, sy: 1, sz: 1,
            active: true, opacity: 255
        },
        clips: [{
            id: 'particle-clip-1',
            type: 'particle2d',
            localTime: 0.5
        }]
    }]
});
assert.equal(particleInsidePreview.updated, 1);
assert.equal(particle2d.enabled, true);
assert.equal(particle2d.flushed, true);
assert.ok(particle2d._simulator.elapsed > 0.49);
assert.equal(particle2d._simulator.finished, true);
assert.equal(particle2d._stopped, false);
assert.equal(particle2d.renderDirty, true);

sceneExtension.methods.applyNativeTimeline({
    time: 1.5,
    playing: false,
    states: [{
        nodeUuid: 'node-2',
        transform: {
            x: 0, y: 0, z: 0,
            rx: 0, ry: 0, rz: 0,
            sx: 1, sy: 1, sz: 1,
            active: true, opacity: 255
        },
        clips: []
    }]
});
assert.equal(particle2d._stopped, true);
assert.equal(particle2d.enabled, false);
assert.ok(particle2d.resetCount >= 2);

const restored = sceneExtension.methods.restoreNativeTimeline();
assert.equal(preview.transforms.length, 1);
assert.equal(preview.transforms[0].nodeUuid, 'node-1');
assert.equal(preview.transforms[0].transform.x, 100);
assert.equal(preview.transforms[0].transform.rz, 45);
assert.equal(preview.transforms[0].transform.opacity, 128);
assert.equal(restored.restored, 2);
assert.equal(target.position.x, 10);
assert.equal(target.eulerAngles.z, 5);
assert.equal(opacity.opacity, 255);
assert.equal(skeleton.enabled, true);
assert.equal(particle2d._stopped, false);
assert.equal(particle2d.enabled, true);

Module._load = originalLoad;

const panelSource = fs.readFileSync(path.join(extensionRoot, 'dist', 'panels', 'default', 'index.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(extensionRoot, 'dist', 'main.js'), 'utf8');
const runtimeSource = fs.readFileSync(path.join(extensionRoot, 'static', 'runtime', 'CocosTimelinePlayer.ts'), 'utf8');
const extensionPackage = JSON.parse(fs.readFileSync(path.join(extensionRoot, 'package.json'), 'utf8'));
assert.match(panelSource, /<ui-drag-area id="workspace" droppable="cc\.Node">/);
assert.match(panelSource, /Editor\.UI\.DragArea\.currentDragInfo/);
assert.match(panelSource, /timeline-peek-selection/);
assert.match(panelSource, /id="auto-duration"/);
assert.match(panelSource, /updateAutoDuration\(\)/);
assert.match(panelSource, /id="new-project"/);
assert.match(panelSource, /createNewProject\(\)/);
assert.match(panelSource, /ownedTypes:/);
assert.match(panelSource, /MIN_TIMELINE_ZOOM = 0\.1/);
assert.match(panelSource, /const visibleDuration = Math\.max\(this\.project\.duration, width \/ pps\)/);
assert.equal(extensionPackage.version, '0.13.2');
assert.ok(fs.existsSync(path.join(extensionRoot, 'static', 'runtime', 'CocosTimelinePlayer.ts')));
assert.match(mainSource, /'Game',\s*'Animation',\s*'Timeline'/);
assert.match(mainSource, /const outputRoot = path\.join\(timelineRoot, 'resources'\)/);
assert.match(mainSource, /const timelineRoot = path\.join\(timelineBaseRoot, timelineName\)/);
assert.match(mainSource, /db:\/\/assets\/Game\/Animation\/Timeline\/\$\{timelineName\}\/resources/);
assert.match(runtimeSource, /@ccclass\('CocosTimelinePlayerGameAnimation'\)/);
assert.ok(extensionPackage.contributions.messages['timeline-peek-selection']);
assert.ok(extensionPackage.contributions.messages.delete);
assert.ok(extensionPackage.contributions.shortcuts.some((item) => item.win === 'delete'));

console.log('native timeline scene bridge: OK');
