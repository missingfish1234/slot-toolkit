'use strict';

const originals = new Map();
let repaintTimer = null;

function findNodeByUuid(root, uuid) {
    if (!root) return null;
    if (root.uuid === uuid) return root;
    for (const child of root.children || []) {
        const found = findNodeByUuid(child, uuid);
        if (found) return found;
    }
    return null;
}

function nodePath(node) {
    const names = [];
    let current = node;
    while (current && current.parent) {
        names.unshift(current.name);
        current = current.parent;
    }
    return names.join('/');
}

function collectLabels(node, Label, output) {
    if (!node) return;
    const label = node.getComponent(Label);
    if (label) output.push(label);
    for (const child of node.children || []) collectLabels(child, Label, output);
}

function overflowName(Label, value) {
    for (const name of ['NONE', 'CLAMP', 'SHRINK', 'RESIZE_HEIGHT']) {
        if (Label.Overflow && Label.Overflow[name] === value) return name;
    }
    return String(value);
}

function repaintScene(scheduleFollowUp = true) {
    try {
        const engine = globalThis.cce && globalThis.cce.Engine;
        if (engine && typeof engine.repaintInEditMode === 'function') {
            engine.repaintInEditMode();
            // Cocos 內建編輯器元件也會延後 repaint，讓同一個 tick 的 assembler/UI 資料先落地。
            // 每次只保留最後一個補繪，避免滾分期間累積 timer。
            if (scheduleFollowUp && typeof setTimeout === 'function') {
                if (repaintTimer !== null && typeof clearTimeout === 'function') clearTimeout(repaintTimer);
                repaintTimer = setTimeout(() => {
                    repaintTimer = null;
                    repaintScene(false);
                }, 50);
            }
            return true;
        }
    } catch (_) {}
    return false;
}

function forceRender(label) {
    try {
        // Cocos 3.8 編輯器模式不一定會像遊戲執行期一樣自動跑完 UI renderer tick。
        // 必須先標 dirty，再立即更新 assembler；舊版會在最後重新標 dirty，
        // 但 Scene 視窗未重繪，造成 Inspector.string 已變而畫面仍停在舊數字。
        if (typeof label._markForUpdateRenderData === 'function') label._markForUpdateRenderData(true);
        else if (typeof label.markForUpdateRenderData === 'function') label.markForUpdateRenderData(true);

        if (typeof label.updateRenderData === 'function') label.updateRenderData(true);
        else if (typeof label._forceUpdateRenderData === 'function') label._forceUpdateRenderData(true);

        // 3.8 已把 updateRenderer 標示為 deprecated，但編輯器預覽仍可用來同步 render flag。
        if (typeof label.updateRenderer === 'function') label.updateRenderer();
    } catch (_) {}
    repaintScene();
}

function renderBounds(label) {
    const data = label.renderData && label.renderData.data;
    if (!Array.isArray(data) || !data.length) return null;
    const points = data.filter((item) => item && Number.isFinite(Number(item.x)) && Number.isFinite(Number(item.y)));
    if (!points.length) return null;
    const xs = points.map((item) => Number(item.x));
    const ys = points.map((item) => Number(item.y));
    return {
        width: Math.max(...xs) - Math.min(...xs),
        height: Math.max(...ys) - Math.min(...ys)
    };
}

function describe(label, Label, UITransform) {
    forceRender(label);
    const transform = label.node.getComponent(UITransform);
    const bounds = renderBounds(label);
    const fontSize = Number(label.fontSize) || 0;
    const actualFontSize = Number(label.actualFontSize ?? label._actualFontSize ?? fontSize) || 0;
    return {
        nodeUuid: label.node.uuid,
        componentUuid: label.uuid,
        name: label.node.name,
        path: nodePath(label.node),
        text: label.string,
        fontName: label.font ? (label.font.name || 'BitmapFont') : (label.fontFamily || 'System Font'),
        bitmapFont: !!label.font,
        fontSize,
        actualFontSize,
        scaleRatio: fontSize > 0 ? actualFontSize / fontSize : 1,
        lineHeight: Number(label.lineHeight) || 0,
        spacingX: Number(label.spacingX) || 0,
        overflow: overflowName(Label, label.overflow),
        wrap: !!label.enableWrapText,
        nodeScaleX: Number(label.node.scale.x) || 0,
        nodeScaleY: Number(label.node.scale.y) || 0,
        boxWidth: transform ? Number(transform.width) || 0 : 0,
        boxHeight: transform ? Number(transform.height) || 0 : 0,
        renderWidth: bounds ? bounds.width : null,
        renderHeight: bounds ? bounds.height : null
    };
}

function resolveLabel(target, cc) {
    const scene = cc.director.getScene();
    if (!scene || !target) return null;
    const node = findNodeByUuid(scene, target.nodeUuid);
    if (!node) return null;
    const labels = [];
    collectLabels(node, cc.Label, labels);
    if (target.componentUuid) {
        const exact = labels.find((item) => item.uuid === target.componentUuid);
        if (exact) return exact;
    }
    return labels[0] || null;
}

function capture(label) {
    if (!originals.has(label.uuid)) {
        originals.set(label.uuid, {
            nodeUuid: label.node.uuid,
            componentUuid: label.uuid,
            text: label.string
        });
    }
}

exports.load = function load() {};
exports.unload = function unload() {
    restoreAll();
    if (repaintTimer !== null && typeof clearTimeout === 'function') {
        clearTimeout(repaintTimer);
        repaintTimer = null;
    }
};

function restoreAll() {
    const cc = require('cc');
    const scene = cc.director.getScene();
    let restored = 0;
    if (scene) {
        for (const state of originals.values()) {
            const label = resolveLabel(state, cc);
            if (!label) continue;
            label.string = state.text;
            forceRender(label);
            restored += 1;
        }
    }
    originals.clear();
    return { ok: true, restored };
}

exports.methods = {
    findLabels(nodeUuids) {
        const cc = require('cc');
        const scene = cc.director.getScene();
        if (!scene) throw new Error('目前沒有開啟的 Scene。');
        const labels = [];
        const seen = new Set();
        for (const uuid of nodeUuids || []) {
            const node = findNodeByUuid(scene, uuid);
            const found = [];
            collectLabels(node, cc.Label, found);
            for (const label of found) {
                if (seen.has(label.uuid)) continue;
                seen.add(label.uuid);
                labels.push(describe(label, cc.Label, cc.UITransform));
            }
        }
        if (!labels.length) throw new Error('選取節點及其子節點找不到 cc.Label。');
        return labels;
    },

    inspectTarget(target) {
        const cc = require('cc');
        const label = resolveLabel(target, cc);
        if (!label) throw new Error('目標 Label 已不存在，請重新綁定。');
        return describe(label, cc.Label, cc.UITransform);
    },

    async applyText(payload) {
        const cc = require('cc');
        const label = resolveLabel(payload && payload.target, cc);
        if (!label) throw new Error('目標 Label 已不存在，請重新綁定。');
        capture(label);
        label.string = String(payload.text ?? '');
        forceRender(label);
        await new Promise((resolve) => setTimeout(resolve, 0));
        forceRender(label);
        return describe(label, cc.Label, cc.UITransform);
    },

    restorePreview() {
        return restoreAll();
    }
};
