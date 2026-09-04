'use strict';

const packageJSON = require('../package.json');
let lastNodeUuids = [];

function selectedNodes() {
    try {
        const selected = Editor.Selection.getSelected('node') || [];
        if (selected.length) lastNodeUuids = selected.filter(Boolean);
    } catch (_) {}
    return lastNodeUuids;
}

function runScene(method, args = []) {
    return Editor.Message.request('scene', 'execute-scene-script', {
        name: packageJSON.name,
        method,
        args
    });
}

exports.load = function load() {
    selectedNodes();
};

exports.unload = function unload() {
    void runScene('restorePreview').catch(() => {});
};

exports.methods = {
    openPanel() {
        Editor.Panel.open(packageJSON.name);
    },

    onSelectionSelect(type, value) {
        if (type !== 'node') return;
        const values = Array.isArray(value) ? value : [value];
        const clean = values.filter((item) => typeof item === 'string' && item);
        if (clean.length) lastNodeUuids = clean;
    },

    async bindSelection() {
        const uuids = selectedNodes();
        if (!uuids.length) throw new Error('請先在 Hierarchy 選取含有 Label 的節點。');
        return runScene('findLabels', [uuids]);
    },

    async inspectTarget(target) {
        return runScene('inspectTarget', [target]);
    },

    async applyText(payload) {
        return runScene('applyText', [payload]);
    },

    async restorePreview() {
        return runScene('restorePreview');
    },

    copyReport(report) {
        const text = JSON.stringify(report, null, 2);
        try {
            require('electron').clipboard.writeText(text);
            return { ok: true, length: text.length };
        } catch (error) {
            throw new Error(`無法複製報告：${error.message || error}`);
        }
    }
};
