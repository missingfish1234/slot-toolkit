'use strict';

const assert = require('assert');
const fs = require('fs');

global.Editor = { Panel: { define(definition) { return definition; } } };
const panel = require('../dist/panels/default');

assert.ok(panel.template.includes('滾分 QA 測試工具'));
assert.strictEqual(typeof panel.ready, 'function');
assert.strictEqual(typeof panel.close, 'function');
for (const [name, selector] of Object.entries(panel.$)) {
    assert.ok(panel.template.includes(`id="${selector.slice(1)}"`), `missing template node for ${name}`);
}
for (const method of ['bindSelection', 'startRoll', 'startStress', 'stopRun', 'copyReport']) {
    assert.strictEqual(typeof panel.methods[method], 'function', `missing panel method ${method}`);
}

const panelSource = fs.readFileSync(require.resolve('../dist/panels/default'), 'utf8');
assert.ok(panelSource.includes('const MAX_SCENE_FPS = 15;'), 'Scene FPS cap is missing');
assert.ok(panelSource.includes('text: metrics.text ?? text'), 'monitor must use Scene-confirmed text');
assert.ok(panelSource.includes('await this.apply(formatValue(start, this.options())'), 'roll must prime Scene before timing');

const manifest = require('../package.json');
const methods = manifest.contributions.messages;
for (const message of ['bind-selection', 'inspect-target', 'apply-text', 'restore-preview', 'copy-report']) {
    assert.ok(methods[message], `missing manifest message ${message}`);
}

console.log('rolling-score-tester panel manifest tests passed');
