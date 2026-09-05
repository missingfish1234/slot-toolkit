'use strict';

// Exercise real panel methods with a deterministic asynchronous Scene bridge.
// No Creator process, project assets or saved timelines are modified by this test.
const assert = require('assert/strict');
const path = require('path');
const base = { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0, sx: 1, sy: 1, sz: 1, active: true, opacity: 255 };
const fields = Object.keys(base);
const transform = (value) => Object.fromEntries(fields.map((key) => [key, value[key]]));
let bridge;
global.Editor = {
    Panel: { define: (panel) => panel },
    Message: { request: (...args) => bridge(...args) }
};
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
const extensionRoot = require('fs').existsSync(path.join(__dirname, '..', 'dist')) ? path.join(__dirname, '..') : path.join(__dirname, '..', 'spine-director-cocos38');
const definition = require(path.join(extensionRoot, 'dist', 'panels', 'default', 'index.js'));
const settle = () => new Promise((resolve) => setImmediate(resolve));
const gate = () => {
    let release;
    const promise = new Promise((resolve) => { release = resolve; });
    return { promise, release };
};

function fixture(keys = [], count = 1) {
    const scene = new Map();
    const calls = [];
    const hooks = {};
    const tracks = Array.from({ length: count }, (_, index) => ({
        id: `t${index}`, nodeUuid: `n${index}`, nodeName: `Node${index}`,
        initialTransform: { ...base }, clips: [], capabilities: {},
        transformKeys: keys.map((key, i) => ({ ...base, id: `key${index}-${i}`, ...key }))
    }));
    for (const track of tracks) scene.set(track.nodeUuid, { ...base });
    bridge = async (_pkg, method, payload) => {
        calls.push(method);
        if (method === 'timeline-inspect-nodes') {
            const nodes = payload.map((nodeUuid) => ({ nodeUuid, transform: { ...scene.get(nodeUuid) } }));
            if (hooks.inspect) await hooks.inspect();
            return nodes;
        }
        if (method === 'timeline-preview') {
            if (hooks.preview) await hooks.preview();
            for (const state of payload.states) scene.set(state.nodeUuid, transform(state.transform));
            if (hooks.applied) hooks.applied(scene);
            return {
                ok: true,
                transforms: payload.states.map((state) => ({ nodeUuid: state.nodeUuid, transform: { ...scene.get(state.nodeUuid) } }))
            };
        }
        if (method === 'timeline-restore') {
            if (hooks.restore) await hooks.restore();
            for (const uuid of scene.keys()) scene.set(uuid, { ...base });
            return { restored: scene.size };
        }
        throw new Error(`Unexpected message: ${method}`);
    };
    const panel = Object.assign({}, definition.methods, {
        project: { fps: 30, duration: 5, autoDuration: false, tracks },
        currentTime: 0, playing: false, recording: true, scrubbing: false,
        recordPolling: false, recordTimer: 0, recordSession: 1, sceneRevision: 0,
        restoringScene: false, panelClosed: false, previewTask: null,
        previewBusy: false, pendingPreview: null,
        recordSnapshot: new Map(tracks.map((track) => [track.nodeUuid, { ...base }])),
        $: { playhead: { style: {} }, time: {}, play: {}, record: { classList: { toggle() {}, remove() {} } } },
        render() { this.renderCount = (this.renderCount || 0) + 1; },
        setStatus(text) { this.status = text; }, scheduleRecordPoll() {}, pixelsPerSecond: () => 100
    });
    return { panel, tracks, scene, calls, hooks };
}

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test('manual first Key followed by seek does not create phantom Keys', async () => {
    const { panel, tracks, scene } = fixture();
    scene.get('n0').x = 100;
    await panel.captureSingleTrack(tracks[0]);
    await settle();
    for (const time of [0.5, 1, 2]) {
        panel.seek(time); await settle(); await panel.pollRecording(); await settle();
    }
    assert.deepEqual(tracks[0].transformKeys.map((key) => [key.time, key.x]), [[0, 100]]);
});

test('record two poses with a seek in between and keep exactly two Keys', async () => {
    const { panel, tracks, scene } = fixture();
    panel.recording = false;
    await panel.toggleRecording();
    scene.get('n0').x = 100;
    await panel.pollRecording(); await settle();
    for (const time of [0.5, 1, 1.5, 2]) {
        panel.seek(time); await settle(); await panel.pollRecording(); await settle();
    }
    scene.get('n0').x = 200;
    await panel.pollRecording(); await settle();
    for (const time of [1.5, 1, 0.5, 0]) {
        panel.seek(time); await settle(); await panel.pollRecording(); await settle();
    }
    assert.deepEqual(tracks[0].transformKeys.map((key) => [key.time, key.x]), [[0, 100], [2, 200]]);
});

test('scrubbing an interpolated segment preserves exactly the two endpoint Keys', async () => {
    const { panel, tracks } = fixture([{ time: 0, x: 0 }, { time: 2, x: 200 }]);
    for (const time of [0.5, 1, 1.5, 0.5, 2]) {
        panel.seek(time); await settle(); await panel.pollRecording(); await settle();
    }
    assert.equal(tracks[0].transformKeys.length, 2);
});

test('movement at a stationary playhead creates one Key then updates it', async () => {
    const { panel, tracks, scene } = fixture([{ time: 0 }]);
    panel.seek(2); await settle();
    for (const x of [10, 20, 30]) {
        scene.get('n0').x = x;
        await panel.pollRecording(); await settle();
    }
    assert.deepEqual(tracks[0].transformKeys.map((key) => [key.time, key.x]), [[0, 0], [2, 30]]);
});

test('same snapped frame updates one Key even with an unsnapped playhead', async () => {
    const { panel, tracks, scene } = fixture();
    panel.currentTime = 0.051;
    for (const x of [10, 20]) {
        scene.get('n0').x = x;
        await panel.captureSingleTrack(tracks[0]); await settle();
    }
    assert.equal(tracks[0].transformKeys.length, 1);
    assert.equal(tracks[0].transformKeys[0].time, 0.0667);
    assert.equal(tracks[0].transformKeys[0].x, 20);
});

test('stale automatic inspection cannot write into a new time', async () => {
    const { panel, tracks, scene, hooks } = fixture([{ time: 0 }]);
    const delayed = gate(); hooks.inspect = () => delayed.promise;
    scene.get('n0').x = 80;
    const poll = panel.pollRecording();
    panel.seek(1); await settle();
    delayed.release(); await poll;
    assert.equal(tracks[0].transformKeys.length, 1);
});

test('A to B to A seek invalidates old inspection even at identical final time', async () => {
    const { panel, tracks, scene, hooks } = fixture([{ time: 0 }]);
    const delayed = gate(); hooks.inspect = () => delayed.promise;
    scene.get('n0').x = 80;
    const poll = panel.pollRecording();
    panel.seek(1); panel.seek(0); await settle();
    delayed.release(); await poll;
    assert.equal(tracks[0].transformKeys[0].x, 0);
    assert.equal(tracks[0].transformKeys.length, 1);
});

test('stale manual capture is cancelled rather than stamped with the new time', async () => {
    const { panel, tracks, scene, hooks } = fixture();
    const delayed = gate(); hooks.inspect = () => delayed.promise;
    scene.get('n0').x = 80;
    const capture = panel.captureSingleTrack(tracks[0]); await settle();
    panel.seek(1); await settle();
    delayed.release(); await capture;
    assert.equal(tracks[0].transformKeys.length, 0);
});

test('recording waits for the latest queued preview to finish', async () => {
    const { panel, tracks, calls, hooks } = fixture([{ time: 0 }, { time: 2, x: 200 }]);
    const delayed = gate(); hooks.preview = () => delayed.promise;
    panel.seek(0.5); panel.seek(1.5);
    await panel.pollRecording();
    assert.ok(!calls.includes('timeline-inspect-nodes'));
    delayed.release(); await settle(); await panel.pollRecording();
    assert.equal(tracks[0].transformKeys.length, 2);
    assert.equal(panel.recordSnapshot.get('n0').x, 150);
});

test('Scene applied transform, not requested transform, becomes baseline', async () => {
    const { panel, tracks, hooks } = fixture([{ time: 0 }, { time: 2, x: 200 }]);
    hooks.applied = (scene) => { scene.get('n0').rz = -180; };
    panel.seek(1); await settle(); await panel.pollRecording();
    assert.equal(tracks[0].transformKeys.length, 2);
    assert.equal(panel.recordSnapshot.get('n0').rz, -180);
});

test('holding the ruler drag and normal playback both suspend recording', async () => {
    const { panel, tracks, scene, calls } = fixture([{ time: 0 }]);
    scene.get('n0').x = 70;
    panel.scrubbing = true; await panel.pollRecording();
    panel.scrubbing = false; panel.playing = true; await panel.pollRecording();
    assert.ok(!calls.includes('timeline-inspect-nodes'));
    panel.playing = false; panel.queuePreview(); await settle(); await panel.pollRecording();
    assert.equal(tracks[0].transformKeys.length, 1);
});

test('automatic playback end and pause do not record preview movement', async () => {
    const { panel, tracks } = fixture([{ time: 0 }, { time: 2, x: 200 }]);
    panel.playing = true; panel.playStartTime = 0;
    panel.playStartClock = performance.now() - 6000;
    panel.playFrame(); await settle(); await panel.pollRecording();
    assert.equal(panel.playing, false);
    assert.equal(tracks[0].transformKeys.length, 2);
    panel.playing = true; panel.startPlayback(); await settle(); await panel.pollRecording();
    assert.equal(tracks[0].transformKeys.length, 2);
});

test('simultaneous edits of two nodes are committed before one shared preview', async () => {
    const { panel, tracks, scene, calls } = fixture([{ time: 0 }], 2);
    panel.seek(2); await settle(); calls.length = 0;
    scene.get('n0').x = 11; scene.get('n1').x = 22;
    await panel.pollRecording(); await settle();
    assert.equal(tracks[0].transformKeys[1].x, 11);
    assert.equal(tracks[1].transformKeys[1].x, 22);
    assert.equal(scene.get('n1').x, 22);
    assert.equal(calls.filter((name) => name === 'timeline-preview').length, 1);
});

test('turning recording off discards an in-flight sample', async () => {
    const { panel, tracks, scene, hooks } = fixture([{ time: 0 }]);
    const delayed = gate(); hooks.inspect = () => delayed.promise;
    scene.get('n0').x = 90;
    const poll = panel.pollRecording();
    await panel.toggleRecording(); delayed.release(); await poll;
    assert.equal(tracks[0].transformKeys[0].x, 0);
});

test('late recording initialization does not overwrite a newer session', async () => {
    const { panel, scene, hooks } = fixture();
    panel.recording = false;
    const delayed = gate(); hooks.inspect = () => delayed.promise;
    const oldStart = panel.toggleRecording(); await settle();
    await panel.toggleRecording();
    hooks.inspect = null; scene.get('n0').x = 55;
    await panel.toggleRecording(); delayed.release(); await oldStart;
    assert.equal(panel.recording, true);
    assert.equal(panel.recordSnapshot.get('n0').x, 55);
});

test('restoring Scene waits for preview and does not record the restored pose', async () => {
    const { panel, tracks, calls, hooks } = fixture([{ time: 0 }, { time: 2, x: 200 }]);
    const delayed = gate(); hooks.preview = () => delayed.promise;
    panel.seek(1);
    const stopping = panel.stopPlayback(); await settle();
    await panel.pollRecording();
    assert.ok(!calls.includes('timeline-restore'));
    delayed.release(); await stopping; await panel.pollRecording();
    assert.equal(tracks[0].transformKeys.length, 2);
    assert.equal(panel.recordSnapshot.get('n0').x, 0);
});

test('failed preview rebaselines without generating a Key', async () => {
    const { panel, tracks, scene, hooks } = fixture([{ time: 0 }]);
    hooks.preview = () => { throw new Error('test failure'); };
    panel.seek(1); await settle();
    scene.get('n0').x = 99;
    await panel.pollRecording();
    assert.equal(tracks[0].transformKeys.length, 1);
    assert.equal(panel.recordSnapshot.get('n0').x, 99);
});

test('a newly added track can record its first real edit', async () => {
    const { panel, scene } = fixture();
    panel.mergeNodeDescriptions([{ nodeUuid: 'new', nodeName: 'New', transform: { ...base }, capabilities: {} }]);
    scene.set('new', { ...base, x: 40 });
    await panel.pollRecording(); await settle();
    const track = panel.project.tracks.find((item) => item.nodeUuid === 'new');
    assert.equal(track.transformKeys.length, 1);
    assert.equal(track.transformKeys[0].x, 40);
});

(async () => {
    for (const { name, fn } of tests) {
        await fn();
        await settle();
        console.log(`PASS ${name}`);
    }
    console.log(`Timeline recording: ${tests.length}/${tests.length} passed`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
