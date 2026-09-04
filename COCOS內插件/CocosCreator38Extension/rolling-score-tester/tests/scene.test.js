'use strict';

const assert = require('assert');
const Module = require('module');

let repaintCalls = 0;
const originalCce = globalThis.cce;
globalThis.cce = {
    Engine: {
        repaintInEditMode() { repaintCalls += 1; }
    }
};

class Label {}
Label.Overflow = { NONE: 0, CLAMP: 1, SHRINK: 2, RESIZE_HEIGHT: 3 };
class UITransform {}

class MockNode {
    constructor(uuid, name, parent = null) {
        this.uuid = uuid;
        this.name = name;
        this.parent = parent;
        this.children = [];
        this.scale = { x: 1, y: 1 };
        this.components = new Map();
        if (parent) parent.children.push(this);
    }
    getComponent(type) { return this.components.get(type) || null; }
}

const scene = new MockNode('scene', 'Scene');
const canvas = new MockNode('canvas', 'Canvas', scene);
const numberNode = new MockNode('number', 'WinNumber', canvas);
const transform = { width: 720, height: 120 };
const label = {
    uuid: 'label-1', node: numberNode, string: 'READY', font: { name: 'Fixed' },
    fontSize: 72, actualFontSize: 72, lineHeight: 119, spacingX: 0, overflow: 2,
    enableWrapText: false,
    renderData: { data: [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 72 }, { x: 0, y: 72 }] },
    _markForUpdateRenderData() { this.renderData.vertDirty = true; },
    updateRenderData() {
        this.actualFontSize = this.string.length > 6 ? 40 : 72;
        const width = this.string.length * 98;
        this.renderData.data = [{ x: 0, y: 0 }, { x: width, y: 0 }, { x: width, y: 72 }, { x: 0, y: 72 }];
        this.renderData.vertDirty = false;
    }
};
numberNode.components.set(Label, label);
numberNode.components.set(UITransform, transform);

const mockCc = { Label, UITransform, director: { getScene: () => scene } };
const originalLoad = Module._load;
Module._load = function load(request, parent, isMain) {
    if (request === 'cc') return mockCc;
    return originalLoad.call(this, request, parent, isMain);
};

const sceneScript = require('../dist/scene');
const found = sceneScript.methods.findLabels(['canvas']);
assert.strictEqual(found.length, 1);
assert.strictEqual(found[0].path, 'Canvas/WinNumber');
assert.strictEqual(found[0].actualFontSize, 72);

(async () => {
    const repaintBeforeApply = repaintCalls;
    const changed = await sceneScript.methods.applyText({ target: found[0], text: '999,999,999' });
    assert.strictEqual(changed.text, '999,999,999');
    assert.strictEqual(changed.actualFontSize, 40);
    assert.strictEqual(changed.renderWidth, 1078);
    assert.strictEqual(label.string, '999,999,999');
    assert.ok(repaintCalls > repaintBeforeApply, 'applyText should repaint the edit-mode Scene');

    const repaintBeforeRestore = repaintCalls;
    const restored = sceneScript.methods.restorePreview();
    assert.strictEqual(restored.restored, 1);
    assert.strictEqual(label.string, 'READY');
    assert.ok(repaintCalls > repaintBeforeRestore, 'restorePreview should repaint the edit-mode Scene');

    Module._load = originalLoad;
    globalThis.cce = originalCce;
    console.log('rolling-score-tester scene preview tests passed');
})().catch((error) => {
    Module._load = originalLoad;
    globalThis.cce = originalCce;
    console.error(error);
    process.exitCode = 1;
});
