'use strict';

const path = require('path');
module.paths.push(path.join(Editor.App.path, 'node_modules'));

function findCanvasNode(root, Canvas) {
    if (!root) return null;
    if (root.getComponent && root.getComponent(Canvas)) return root;
    for (const child of root.children || []) {
        const found = findCanvasNode(child, Canvas);
        if (found) return found;
    }
    return null;
}

exports.load = function load() {};
exports.unload = function unload() {};

exports.methods = {
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
