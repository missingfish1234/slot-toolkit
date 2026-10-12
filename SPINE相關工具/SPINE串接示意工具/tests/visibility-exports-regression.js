'use strict';
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const exportsAPI = require('../scripts/visibility-exports.js');
const date = seconds => new Date(seconds * 1000);
const char = {
    id: 'hero', name: '虎王', type: 'spine', baseVisible: false,
    baseX: 10, baseY: 20, baseRot: 5, scaleX: 1.2, scaleY: 1.3, baseAlpha: 0.5,
    animTracks: ['hero_anim', 'hero_anim_1'],
    tracks: { anim: 'hero_anim', move: 'hero_move', scale: 'hero_scale', rotate: 'hero_rotate', alpha: 'hero_alpha', visibility: 'hero_visibility' }
};
const switchAt = (time, visible, group = 'hero_visibility') => ({ group, start: date(time), end: date(time + 0.01), visibilityEnabled: visible, type: 'point' });
const items = [
    switchAt(8, true), switchAt(1, true), switchAt(4, false), switchAt(4, true), switchAt(6, false), switchAt(100, false, 'other_visibility'),
    { group: 'hero_anim', start: date(0), end: date(3), content: 'idle (loop)', loop: true },
    { group: 'hero_anim_1', start: date(2.5), end: date(9), content: 'roar', loop: false, mixDuration: 0.4 },
    { group: 'hero_move', start: date(2), end: date(3), motStartX: 10, motStartY: 20, motEndX: 50, motEndY: 60, easing: 'quadIn' },
    { group: 'hero_scale', start: date(3), end: date(4), motStartS: 1, motEndS: 2 },
    { group: 'hero_rotate', start: date(4), end: date(5), motStartR: 5, motEndR: 30 },
    { group: 'hero_alpha', start: date(5), end: date(6), motStartA: 0.5, motEndA: 1 }
];
assert.deepEqual(exportsAPI.getVisibilitySwitches(char, items), [
    { startTime: 1, visible: true }, { startTime: 4, visible: true }, { startTime: 6, visible: false }, { startTime: 8, visible: true }
]);
const data = exportsAPI.buildSequence(char, items);
assert.equal(data.initialVisible, false);
assert.equal(data.totalDuration, 9, 'animation duration must include its end');
assert.equal(data.animations[1].track, 1);
assert.equal(data.animations[1].mixTime, 0.4);
assert.equal(data.transforms.find(item => item.type === 'rotate').endR, 30);
assert.equal(exportsAPI.buildSequence({ ...char, baseVisible: undefined }, []).initialVisible, true, 'legacy scenes begin visible');
assert.equal(exportsAPI.buildSequence(char, [switchAt(12, false)]).totalDuration, 12, 'point marker width is not duration');
const events = exportsAPI.getVisibilityEvents(char, [switchAt(0, true), switchAt(0, false), switchAt(1, true)]);
assert.deepEqual(events, [{ startTime: 0, visible: false }, { startTime: 1, visible: true }], 'last switch at t=0 replaces initial event');

const native = exportsAPI.buildNativeCocosAnim(char, items, 'TigerSequence');
assert.equal(native[0]._name, 'TigerSequence');
assert.equal(native[0]._duration, 9);
assert.deepEqual(native[0]._events.filter(item => item.func === 'setSpineVisible').map(item => [item.frame, item.params[0]]), [[0, false], [1, true], [4, true], [6, false], [8, true]]);
assert.equal(native[0]._events.filter(item => item.func === 'playSpineAnim').length, 1, 'native export retains primary animation track');
assert.equal(native[0]._tracks.length, 4);
for (const reference of native[0]._tracks) {
    const track = native[reference.__id__];
    for (const ref of track._channels || [track._channel]) {
        const curve = native[native[ref.__id__]._curve.__id__];
        assert.equal(curve.__type__, 'cc.RealCurve');
        assert.equal(curve._times.length, curve._values.length);
    }
}
const position = native[native[0]._tracks[0].__id__];
const yCurve = native[native[position._channels[1].__id__]._curve.__id__];
assert.deepEqual(yCurve._values.map(item => item.value), [-20, -20, -60], 'Cocos coordinate conversion remains intact');
assert.equal(exportsAPI.buildNativeCocosAnim(char, [], 'Empty')[0]._duration, 1);
assert.equal(exportsAPI.buildNativeCocosAnim(char, [switchAt(0, true)], 'Start')[0]._events.filter(item => item.func === 'setSpineVisible').length, 1);

// Execute the original exporter, rather than reimplementing its schema in the
// test. Existing fields must survive unchanged after adding visibility events.
const html = fs.readFileSync(path.join(__dirname, '../SpinePlayTest.html'), 'utf8');
const oldStart = html.indexOf('    function exportNativeCocosAnim() {');
const oldEnd = html.indexOf('    function exportCodeSnippet()', oldStart);
assert.ok(oldStart >= 0 && oldEnd > oldStart);
const originalNativeSource = html.slice(oldStart, oldEnd);
function originalNative(fixtureChar, fixtureItems) {
    let downloaded;
    const originalScope = {
        selectedCharId: fixtureChar.id, characters: [fixtureChar],
        getGroupClips: group => fixtureItems.filter(item => item.group === group),
        alert: () => {}, prompt: () => 'NativeParity',
        document: { createElement: () => ({ click() { downloaded = JSON.parse(decodeURIComponent(this.href.split(',')[1])); } }) }
    };
    vm.createContext(originalScope);
    vm.runInContext(originalNativeSource + '\nexportNativeCocosAnim();', originalScope);
    downloaded[0]._hash = 0;
    return downloaded;
}
let nativeParityCases = 0;
function assertNativeParity(fixtureChar, fixtureItems) {
    const original = originalNative(fixtureChar, fixtureItems);
    const rebuilt = JSON.parse(JSON.stringify(exportsAPI.buildNativeCocosAnim(fixtureChar, fixtureItems, 'NativeParity')));
    rebuilt[0]._hash = 0;
    rebuilt[0]._events = rebuilt[0]._events.filter(item => item.func !== 'setSpineVisible');
    const switches = exportsAPI.getVisibilitySwitches(fixtureChar, fixtureItems);
    if (switches.length) original[0]._duration = Math.max(original[0]._duration, ...switches.map(item => item.startTime));
    assert.deepEqual(rebuilt, original, 'all legacy native serialized fields, references, paths, values and times must match');
    nativeParityCases++;
}
const transformGroups = ['hero_move', 'hero_scale', 'hero_rotate', 'hero_alpha'];
for (let mask = 0; mask < 16; mask++) {
    for (const startAtZero of [false, true]) {
        const fixtureItems = items.filter(item => item.group.startsWith('hero_anim') || transformGroups.some((group, index) => mask & (1 << index) && item.group === group));
        const clips = fixtureItems.map(item => ({ ...item, start: startAtZero ? date(0) : item.start }));
        assertNativeParity(char, clips);
    }
}
assertNativeParity(char, []);
assertNativeParity(char, items);
assertNativeParity(char, [...items, switchAt(12, false)]);
assertNativeParity(char, [...items, ...items.filter(item => transformGroups.includes(item.group)).map(item => ({ ...item, start: date(1.333), end: date(1.333) }))]);
assertNativeParity({ ...char, baseX: '12', baseRot: undefined, scaleX: undefined, baseAlpha: undefined }, items.map(item => item.group === 'hero_anim' ? { ...item, loop: null } : item));
assertNativeParity(char, items.map(item => transformGroups.includes(item.group) ? { ...item, start: date(20), end: date(19) } : item));

const cocos = exportsAPI.buildCodeSnippet(char, items, 'cocos');
new vm.Script(cocos);
assert.match(cocos, /tween\(node\)\.delay\(8\.0\)\.call\(\(\) => \{ visual\.enabled = true;/);
assert.match(cocos, /tween\(node\)\.delay\(2\.0\)\.set\(\{ position: v3\(10\.0, -20\.0, 0\.0\)/);
assert.match(cocos, /tween\(node\)\.delay\(2\.5\).*spine\.setAnimation\(1, "roar", false\)/);
assert.ok(!cocos.includes('node.active'), 'hiding must keep event player active');
assert.ok(cocos.includes('\nconst spine'), 'snippet contains real newlines');
const unity = exportsAPI.buildCodeSnippet(char, items, 'unity');
assert.match(unity, /timeline\.InsertCallback\(8\.0f, \(\) => \{ visualRenderer\.enabled = true;/);
assert.match(unity, /timeline\.Insert\(2\.0f, transform\.DOLocalMove/);
assert.match(unity, /SetEase\(Ease\.InQuad\)/);
assert.match(unity, /timeline\.InsertCallback\(2\.5f,.*SetAnimation\(1, "roar", false\)/);
assert.ok(!unity.includes('SetActive'), 'Unity renderer hiding keeps animator running');
const easingPairs = [
    ['linear', 'Linear', 'linear'], ['easeOutQuad', 'OutQuad', 'quadOut'],
    ['easeInOutQuad', 'InOutQuad', 'quadInOut'], ['easeOutBack', 'OutBack', 'backOut'], ['easeOutElastic', 'OutElastic', 'elasticOut']
];
const uiEasingOptions = html.slice(html.indexOf('<select id="clipEasing"'), html.indexOf('</select>', html.indexOf('<select id="clipEasing"')));
assert.deepEqual(Array.from(uiEasingOptions.matchAll(/value="([^"]+)"/g), match => match[1]), easingPairs.map(pair => pair[0]), 'test every easing currently offered by the UI');
for (const [uiName, unityName, cocosName] of easingPairs) {
    const easingItems = [ { ...items.find(item => item.group === 'hero_move'), easing: uiName } ];
    assert.ok(exportsAPI.buildCodeSnippet(char, easingItems, 'unity').includes('SetEase(Ease.' + unityName + ')'));
    assert.ok(exportsAPI.buildCodeSnippet(char, easingItems, 'cocos').includes('easing: "' + cocosName + '"'));
}
const spriteCode = exportsAPI.buildCodeSnippet({ ...char, type: 'sprite' }, items, 'unity');
assert.ok(!spriteCode.includes('skeletonAnimation'), 'image reference export must not assume a Spine component');
assert.match(exportsAPI.buildCodeSnippet(char, [switchAt(0, true)], 'cocos'), /visual.enabled = true;/, 't=0 switch applies immediately');

// Exercise installed browser exports with lexical editor state and a download target.
const source = fs.readFileSync(path.join(__dirname, '../scripts/visibility-exports.js'), 'utf8');
const downloads = [], scope = {
    window: {}, prompt: () => 'TigerSequence', alert: () => {},
    document: { createElement: () => { const anchor = { click() { downloads.push(this); } }; return anchor; }, querySelector: () => ({ value: 'cocos' }) },
    navigator: { clipboard: { writeText: async () => {} } }
};
vm.createContext(scope);
vm.runInContext('let characters = []; let selectedCharId = null; let timelineData = null;', scope);
scope.editorChar = char; scope.editorItems = items;
vm.runInContext('characters = [editorChar]; selectedCharId = editorChar.id; timelineData = { get: () => editorItems };', scope);
vm.runInContext(source, scope);
scope.exportSequenceJSON(); scope.exportNativeCocosAnim();
assert.equal(downloads[0].download, '虎王_Sequence.json');
assert.equal(JSON.parse(decodeURIComponent(downloads[0].href.split(',')[1])).visibility.length, 4);
assert.equal(downloads[1].download, 'TigerSequence.anim');
assert.equal(JSON.parse(decodeURIComponent(downloads[1].href.split(',')[1]))[0]._events[0].func, 'setSpineVisible');

const hook = fs.readFileSync(path.join(__dirname, '../SpineTimelineHook.ts'), 'utf8');
const hookBody = hook.match(/public setSpineVisible\(visible: boolean = true\) \{([\s\S]*?)\n    \}/)[1];
const setSpineVisible = new Function('visible', hookBody);
const skeleton = { enabled: true }, runtime = { getSpine: () => skeleton, node: { active: true } };
setSpineVisible.call(runtime, false);
assert.equal(skeleton.enabled, false);
assert.equal(runtime.node.active, true);
setSpineVisible.call(runtime, true);
assert.equal(skeleton.enabled, true);
global.Sprite = function Sprite() {};
const sprite = { enabled: true };
setSpineVisible.call({ getSpine: () => null, getComponent: () => sprite }, false);
assert.equal(sprite.enabled, false);
assert.doesNotThrow(() => setSpineVisible.call({ getSpine: () => null, getComponent: () => null }, false));
delete global.Sprite;
console.log('Visibility exports: initial/legacy state, same-time switches, durations, native parity (' + nativeParityCases + ' original-export comparisons), all UI easing values, absolute timing, browser wrappers and Hook: PASS');
