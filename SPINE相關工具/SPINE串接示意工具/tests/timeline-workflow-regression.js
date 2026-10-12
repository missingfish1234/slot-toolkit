'use strict';

// Exercise the application functions directly. DOM, rendering, downloads and
// timers are isolated so timeline behavior is deterministic and needs no browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const htmlPath = path.resolve(__dirname, '..', 'SpinePlayTest.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const inlineScript = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)]
    .map(match => match[1]).find(script => script.includes('function syncSpineToTime'));
assert.ok(inlineScript, 'application script is present');

class DataSet {
    constructor(items = []) { this.rows = new Map(); this.listeners = []; this.nextId = 1; this.add(items); }
    get length() { return this.rows.size; }
    add(items) {
        const ids = (Array.isArray(items) ? items : [items]).map(item => {
            const copy = { ...item };
            if (copy.id === undefined) copy.id = `generated_${this.nextId++}`;
            if (this.rows.has(copy.id)) throw new Error(`duplicate ID: ${copy.id}`);
            this.rows.set(copy.id, copy);
            return copy.id;
        });
        if (ids.length) this.emit();
        return ids;
    }
    get(query) {
        if (typeof query === 'string' || typeof query === 'number') {
            const row = this.rows.get(query); return row ? { ...row } : null;
        }
        const rows = [...this.rows.values()].map(row => ({ ...row }));
        if (Array.isArray(query)) return query.map(id => this.get(id)).filter(Boolean);
        return query && query.filter ? rows.filter(query.filter) : rows;
    }
    update(items) {
        return (Array.isArray(items) ? items : [items]).map(item => {
            if (!this.rows.has(item.id)) return this.add(item)[0];
            this.rows.set(item.id, { ...this.rows.get(item.id), ...item }); this.emit(); return item.id;
        });
    }
    remove(ids) {
        for (const value of Array.isArray(ids) ? ids : [ids]) this.rows.delete(typeof value === 'object' ? value.id : value);
        this.emit();
    }
    clear() { this.rows.clear(); this.emit(); }
    on(event, listener) { this.listeners.push(listener); }
    emit() { for (const listener of this.listeners) listener('*'); }
}

function element() {
    const classes = new Set();
    return {
        value: '', checked: false, disabled: false, innerHTML: '', innerText: '', textContent: '',
        style: {}, dataset: {}, children: [], options: [],
        classList: { add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value), toggle: value => classes.has(value) ? classes.delete(value) : classes.add(value) },
        appendChild(child) { this.children.push(child); this.options.push(child); return child; },
        addEventListener() {}, setAttribute() {}, removeAttribute() {}, click() {},
        closest() { return null; }, querySelectorAll() { return []; },
    };
}

function makeSpine(assets = { fixture: true }) {
    const entries = new Map();
    return {
        assets, x: 0, y: 0, angle: 0, visible: true, alpha: 1, zIndex: 0, destroyed: false,
        scale: { x: 1, y: 1, set(x, y = x) { this.x = x; this.y = y; } },
        state: {
            setAnimation(track, name) { const entry = { animation: { name, duration: 1 }, trackTime: 0, mixDuration: 0 }; entries.set(track, entry); return entry; },
            getCurrent(track) { return entries.get(track); }, setEmptyAnimation(track) { entries.delete(track); },
        },
        skeleton: { skin: { name: 'default' }, data: { findSkin: () => ({}) }, setToSetupPose() {}, setSkinByName(name) { this.skin = { name }; }, setSlotsToSetupPose() {} },
        update() {}, on() { return this; }, destroy() { this.destroyed = true; },
    };
}

function harness() {
    const nodes = new Map();
    const storage = new Map();
    const timers = new Map();
    const blobs = [];
    let timerId = 0;
    const fixtureData = { animations: [{ name: 'idle', duration: 1 }, { name: 'win', duration: 0.5 }], skins: [{ name: 'default' }] };
    const sandbox = {
        console, Date, Math, Map, Set, Blob, URLSearchParams, DataSet, makeSpine, fixtureData,
        window: { location: { search: '', href: 'file:///SpinePlayTest.html' }, addEventListener() {} },
        document: { getElementById(id) { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); }, createElement: element, querySelectorAll: () => [], body: element() },
        localStorage: { setItem: (key, value) => storage.set(key, value), getItem: key => storage.get(key), removeItem: key => storage.delete(key) },
        URL: { createObjectURL(blob) { blobs.push(blob); return 'blob:fixture'; }, revokeObjectURL() {} },
        vis: { DataSet },
        setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; },
        clearTimeout(id) { timers.delete(id); }, requestAnimationFrame() {},
        alert(message) { throw new Error(`unexpected alert: ${message}`); }, confirm: () => true, prompt: () => 'fixture-project',
    };
    const context = vm.createContext(sandbox);
    vm.runInContext(inlineScript.replace(/^\s*bootstrap\(\);\s*$/m, ''), context, { filename: htmlPath });
    const run = source => vm.runInContext(source, context);
    run(`
        timelineData = new vis.DataSet(); timelineGroups = new vis.DataSet();
        timelineData.on('*', markTimelineCacheDirty);
        timeline = { selection: [], setSelection(ids) { this.selection = [...ids]; }, getSelection() { return [...this.selection]; }, setCustomTime() {}, getWindow() { return { start: new Date(0), end: new Date(5000) }; }, setWindow() {}, focus() {}, redraw() {} };
        worldContainer = { children: [], addChild(obj) { this.children.push(obj); }, sortChildren() {}, removeChild() {} };
        renderInspector = () => {}; renderSceneList = () => {}; drawDebugHelpers = () => {};
        if (typeof renderQuickComposer === 'function') renderQuickComposer = () => {};
        buildSpineObject = (raw, atlas, textures, binary, assets) => ({ spine: makeSpine(assets), spineData: fixtureData });
    `);
    return {
        run, storage, blobs, nodes,
        flushTimers() { const work = [...timers.values()]; timers.clear(); work.forEach(fn => fn()); },
        addCharacter(id = 'A', config = {}) {
            sandbox.characterConfig = { id, name: id, type: 'spine', x: 0, y: 0, scaleX: 1, scaleY: 1, rotation: 0, alpha: 1, order: 0, assets: { fixture: true }, ...config };
            run(`finalizeCharacterCreation(makeSpine(characterConfig.assets), characterConfig.name, characterConfig.id, characterConfig, 'spine', fixtureData);`);
            const char = run(`getCharacterById(${JSON.stringify(id)})`);
            // Composer choices originate from user interaction during a session.
            if (config.preferredAnimation !== undefined) char.preferredAnimation = config.preferredAnimation;
            if (config.preferredAnimTrack !== undefined) char.preferredAnimTrack = config.preferredAnimTrack;
            // Restored fixture groups intentionally resemble a real legacy project.
            const groups = [id, ...char.animTracks, ...Object.values(char.tracks)];
            for (const group of new Set(groups)) if (!run(`timelineGroups.get(${JSON.stringify(group)})`)) run(`timelineGroups.add({ id: ${JSON.stringify(group)}, content: 'fixture', nestedGroups: [] });`);
            return char;
        },
        addClip(id, group, start, end, extras = {}) {
            sandbox.fixtureClip = { id, group, content: 'idle (1.00s)', className: 'track-anim', start: new Date(start), end: new Date(end), ...extras };
            run('timelineData.add(fixtureClip);');
        },
        clips(group) { return run('timelineData.get()').filter(item => item.group === group).sort((a, b) => a.start - b.start); },
    };
}

const tests = [];
function test(name, body) { tests.push({ name, body }); }
function visibility(h, id, time) { return h.run(`getVisibilityAtTime(getCharacterById(${JSON.stringify(id)}), ${time})`); }
function bounds(items) { return items.map(item => [item.start.valueOf(), item.end.valueOf()]); }

test('legacy projects remain initially visible and receive a visibility track', () => {
    const h = harness(); const char = h.addCharacter();
    assert.equal(char.baseVisible, true);
    assert.equal(char.tracks.visibility, 'A_visibility');
    assert.equal(visibility(h, 'A', 0), true);
    assert.equal(visibility(h, 'A', 5000), true);
    h.run('syncSpineToTime(5000);'); assert.equal(char.spine.visible, true);
});

test('restoring old project JSON adds the visibility track to the character group', () => {
    const h = harness();
    h.run(`restoreProjectData({
        characters: [{ id: 'legacy', name: 'legacy', type: 'spine', x: 0, y: 0, rotation: 0, scaleX: 1, scaleY: 1, order: 0, assets: { fixture: true }, animTracks: ['legacy_anim'] }],
        timeline: [], groups: [{ id: 'legacy', content: 'legacy', nestedGroups: ['legacy_anim'] }, { id: 'legacy_anim', content: 'T0' }]
    });`);
    assert.equal(visibility(h, 'legacy', 0), true);
    assert.ok(h.run("timelineGroups.get('legacy_visibility')"));
    assert.ok(h.run("timelineGroups.get('legacy').nestedGroups.includes('legacy_visibility')"));
});

test('visibility events use exact boundaries and produce deterministic forward and reverse seeks', () => {
    const h = harness(); const char = h.addCharacter('A', { baseVisible: false });
    h.addClip('on', char.tracks.visibility, 1000, 1010, { type: 'point', className: 'track-visibility', visibilityEnabled: true });
    h.addClip('off', char.tracks.visibility, 3000, 3010, { type: 'point', className: 'track-visibility', visibilityEnabled: false });
    for (const [time, expected] of [[0, false], [999, false], [1000, true], [1010, true], [2999, true], [3000, false], [5000, false], [1500, true], [500, false], [3000, false]]) {
        assert.equal(visibility(h, 'A', time), expected, `visibility at ${time} ms`);
        h.run(`syncSpineToTime(${time});`); assert.equal(char.spine.visible, expected, `render visibility at ${time} ms`);
    }
});

test('adding an opposite switch at the same time replaces the existing event', () => {
    const h = harness(); const char = h.addCharacter();
    h.run("selectCharacter('A'); currentTime = 1250; addVisibilitySwitch(false);");
    const first = h.clips(char.tracks.visibility); assert.equal(first.length, 1); assert.equal(first[0].type, 'point');
    assert.deepEqual(bounds(first), [[1250, 1260]]); assert.equal(visibility(h, 'A', 1250), false);
    h.run('addVisibilitySwitch(true);');
    const replaced = h.clips(char.tracks.visibility); assert.equal(replaced.length, 1); assert.equal(visibility(h, 'A', 1250), true);
});

test('deleting visibility switches falls back to the earlier event and then the initial state', () => {
    const h = harness(); const char = h.addCharacter('A', { baseVisible: false });
    h.run("selectCharacter('A'); currentTime = 1000; addVisibilitySwitch(true); currentTime = 3000; addVisibilitySwitch(false);");
    assert.equal(visibility(h, 'A', 3000), false);
    h.run('deleteSelectedClip();');
    assert.equal(visibility(h, 'A', 3000), true); assert.equal(char.spine.visible, true);
    const onId = h.clips(char.tracks.visibility)[0].id;
    h.run(`selectedClipId = ${JSON.stringify(onId)}; timeline.setSelection([selectedClipId]); deleteSelectedClip();`);
    assert.equal(visibility(h, 'A', 3000), false); assert.equal(char.spine.visible, false);
});

test('switching from A to B clears A clip selection and restores B animation track', () => {
    const h = harness(); const a = h.addCharacter('A'); const b = h.addCharacter('B', { animTracks: ['B_anim', 'B_anim_1'], preferredAnimation: 'win', preferredAnimTrack: 'B_anim_1' });
    h.addClip('A_clip', a.animTracks[0], 0, 1000);
    h.run("selectedCharId = 'A'; selectedClipId = 'A_clip'; selectedTrackId = 'A_anim'; timeline.setSelection(['A_clip']); selectCharacter('B');");
    assert.equal(h.run('selectedCharId'), 'B'); assert.equal(h.run('selectedClipId'), null);
    assert.deepEqual(Array.from(h.run('timeline.getSelection()')), []);
    assert.equal(h.run('selectedTrackId'), b.preferredAnimTrack);
    assert.equal(b.preferredAnimation, 'win');
});

test('selecting a clip preserves that clip while synchronizing its character', () => {
    const h = harness(); const a = h.addCharacter('A'); h.addCharacter('B');
    h.addClip('A_clip', a.animTracks[0], 0, 1000);
    h.run("selectedCharId = 'B'; selectedClipId = 'A_clip'; timeline.setSelection(['A_clip']); selectCharacter('A', false); selectTrack('A_anim');");
    assert.equal(h.run('selectedCharId'), 'A'); assert.equal(h.run('selectedClipId'), 'A_clip');
    assert.deepEqual(Array.from(h.run('timeline.getSelection()')), ['A_clip']);
});

test('append respects the selected character sub-track and existing tail', () => {
    const h = harness(); const a = h.addCharacter('A', { animTracks: ['A_anim', 'A_anim_1'] });
    h.addClip('base', a.animTracks[0], 0, 9000); h.addClip('sub', a.animTracks[1], 1000, 2000);
    h.run("selectCharacter('A'); selectTrack('A_anim_1'); currentTime = 250; addAnimClip('A', 'win', null, 'append');");
    assert.deepEqual(bounds(h.clips(a.animTracks[1])), [[1000, 2000], [2000, 2500]]);
    assert.deepEqual(bounds(h.clips(a.animTracks[0])), [[0, 9000]]);
});

test('playhead insertion moves a crossing clip intact and pushes later clips without overlap', () => {
    const h = harness(); const a = h.addCharacter(); const group = a.animTracks[0];
    h.addClip('crossing', group, 0, 1000); h.addClip('next', group, 1000, 2000); h.addClip('gap', group, 5000, 6000);
    h.run("selectCharacter('A'); currentTime = 500; addAnimClip('A', 'win', null, 'playhead');");
    assert.deepEqual(bounds(h.clips(group)), [[500, 1000], [1000, 2000], [2000, 3000], [5000, 6000]]);
    const crossing = h.run("timelineData.get('crossing')"); assert.equal(crossing.end - crossing.start, 1000);
    const next = h.run("timelineData.get('next')"); assert.equal(next.end - next.start, 1000);
});

test('playhead insertion into an empty gap does not shift unrelated clips', () => {
    const h = harness(); const a = h.addCharacter(); const group = a.animTracks[0];
    h.addClip('before', group, 0, 1000); h.addClip('after', group, 3000, 4000);
    h.run("selectCharacter('A'); currentTime = 1500; addAnimClip('A', 'win', null, 'playhead');");
    assert.deepEqual(bounds(h.clips(group)), [[0, 1000], [1500, 2000], [3000, 4000]]);
});

test('adding a new animation track makes it the next animation destination', () => {
    const h = harness(); const a = h.addCharacter();
    h.run("selectCharacter('A'); addExtraAnimTrack(); currentTime = 250; addAnimClip('A', 'win', null, 'playhead');");
    assert.equal(a.animTracks.length, 2); assert.equal(h.run('selectedTrackId'), a.animTracks[1]);
    assert.deepEqual(bounds(h.clips(a.animTracks[1])), [[250, 750]]);
});

test('autosave and project download preserve initial visibility, switches and composer memories', async () => {
    const h = harness(); const a = h.addCharacter('A', { baseVisible: false, preferredAnimation: 'win', preferredAnimTrack: 'A_anim' });
    h.addClip('on', a.tracks.visibility, 1500, 1510, { type: 'point', className: 'track-visibility', visibilityEnabled: true });
    h.run('autoSaveToLocal();');
    const auto = JSON.parse(h.storage.get('spineDirectorAutoSave'));
    assert.equal(auto.characters[0].baseVisible, false); assert.equal(auto.characters[0].preferredAnimation, 'win');
    assert.equal(auto.characters[0].preferredAnimTrack, 'A_anim'); assert.equal(auto.timeline[0].visibilityEnabled, true);
    await h.run('enhancedSaveProject();');
    const saved = JSON.parse(await h.blobs.at(-1).text());
    assert.equal(saved.characters[0].baseVisible, false); assert.equal(saved.characters[0].preferredAnimation, 'win');
    assert.equal(saved.characters[0].preferredAnimTrack, 'A_anim'); assert.equal(saved.timeline[0].visibilityEnabled, true);
    h.run(`restoreProjectData(${JSON.stringify(saved)});`);
    assert.equal(visibility(h, 'A', 0), false); assert.equal(visibility(h, 'A', 1500), true);
    assert.equal(h.run("getCharacterById('A').preferredAnimation"), 'win');
});

test('copying a character with tracks copies visibility and all animation sub-tracks', async () => {
    const h = harness(); const a = h.addCharacter('A', { baseVisible: false, animTracks: ['A_anim', 'A_anim_1'], preferredAnimation: 'win', preferredAnimTrack: 'A_anim_1' });
    h.addClip('on', a.tracks.visibility, 1000, 1010, { type: 'point', className: 'track-visibility', visibilityEnabled: true });
    h.addClip('base', a.animTracks[0], 1000, 2000); h.addClip('sub', a.animTracks[1], 1250, 1750);
    await h.run("selectCharacter('A'); duplicateWithDialog();"); h.flushTimers();
    const copy = h.run('characters[characters.length - 1]');
    assert.notEqual(copy.id, a.id); assert.equal(copy.baseVisible, false); assert.equal(copy.animTracks.length, 2);
    assert.equal(visibility(h, copy.id, 0), false); assert.equal(visibility(h, copy.id, 1000), true);
    assert.deepEqual(bounds(h.clips(copy.animTracks[0])), [[1000, 2000]]);
    assert.deepEqual(bounds(h.clips(copy.animTracks[1])), [[1250, 1750]]);
    assert.equal(copy.preferredAnimation, 'win'); assert.equal(copy.preferredAnimTrack, copy.animTracks[1]);
});

test('undo restores visibility events and initial visibility', () => {
    const h = harness(); const a = h.addCharacter();
    h.run("selectCharacter('A'); recordHistoryCheckpoint('initial'); currentTime = 1000; addVisibilitySwitch(false);"); h.flushTimers();
    assert.equal(visibility(h, 'A', 1000), false);
    h.run('undoLastAction();');
    assert.equal(visibility(h, 'A', 1000), true); assert.equal(h.clips(a.tracks.visibility).length, 0);
    h.run('setInitialVisibility(false);'); h.flushTimers();
    assert.equal(visibility(h, 'A', 0), false);
    h.run('undoLastAction();');
    assert.equal(visibility(h, 'A', 0), true); assert.equal(a.baseVisible, true);
});

(async () => {
    let failures = 0;
    for (const { name, body } of tests) {
        try { await body(); console.log(`PASS ${name}`); }
        catch (error) { failures++; console.error(`FAIL ${name}\n${error.stack}`); }
    }
    console.log(`\n${tests.length - failures}/${tests.length} regression checks passed.`);
    process.exitCode = failures ? 1 : 0;
})();
