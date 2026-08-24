'use strict';

const path = require('path');
const { pathToFileURL } = require('url');
const packageJSON = require('../../../package.json');

module.exports = Editor.Panel.define({
    template: `
        <div id="app">
            <div id="toolbar">
                <span class="version">Creator 3.8 / Spine 3.8</span>
                <span id="status">就緒</span>
                <button id="create-node" disabled>建立播放節點</button>
            </div>
            <iframe id="tool" allow="clipboard-write"></iframe>
        </div>
    `,
    style: `
        :host { display: block; width: 100%; height: 100%; }
        #app { display: flex; flex-direction: column; width: 100%; height: 100%; background: #1e1e1e; }
        #toolbar { height: 34px; flex: 0 0 34px; display: flex; align-items: center; gap: 10px; padding: 0 10px; border-bottom: 1px solid #3c3c3c; color: #ddd; font: 12px sans-serif; }
        #toolbar .version { color: #6dd58c; font-weight: 700; }
        #status { flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: #aaa; }
        #status.error { color: #ff7b72; }
        #status.success { color: #6dd58c; }
        button { border: 1px solid #555; border-radius: 3px; background: #3a3a3a; color: #eee; padding: 4px 10px; cursor: pointer; }
        button:hover:not(:disabled) { background: #4a4a4a; }
        button:disabled { opacity: .45; cursor: default; }
        iframe { flex: 1; width: 100%; border: 0; background: #111; }
    `,
    $: {
        tool: '#tool',
        status: '#status',
        createNode: '#create-node'
    },
    methods: {
        setStatus(message, kind) {
            this.$.status.textContent = message;
            this.$.status.className = kind || '';
        },
        sendToTool(message) {
            if (this.$.tool.contentWindow) {
                this.$.tool.contentWindow.postMessage(message, '*');
            }
        }
    },
    ready() {
        this.lastExport = null;
        this.onToolMessage = async (event) => {
            const message = event.data;
            if (!message || message.source !== 'spine-director-cocos38') return;

            if (message.type === 'export-project') {
                this.setStatus('正在寫入 Cocos 專案素材…');
                this.$.createNode.disabled = true;
                try {
                    const result = await Editor.Message.request(packageJSON.name, 'export-project', message.payload);
                    this.lastExport = result;
                    this.setStatus(`輸出完成：${result.assetUrl}`, 'success');
                    this.$.createNode.disabled = false;
                    this.sendToTool({
                        source: 'spine-director-cocos38-host',
                        type: 'export-result',
                        ok: true,
                        result
                    });
                } catch (error) {
                    const detail = error && error.message ? error.message : String(error);
                    this.setStatus(`輸出失敗：${detail}`, 'error');
                    this.sendToTool({
                        source: 'spine-director-cocos38-host',
                        type: 'export-result',
                        ok: false,
                        error: detail
                    });
                }
            }
        };
        window.addEventListener('message', this.onToolMessage);

        this.$.createNode.addEventListener('click', async () => {
            if (!this.lastExport) return;
            this.setStatus('正在目前場景建立播放節點…');
            try {
                const result = await Editor.Message.request(packageJSON.name, 'create-player-node', {
                    className: this.lastExport.className,
                    projectSlug: this.lastExport.projectSlug,
                    nodeName: this.lastExport.projectSlug
                });
                this.setStatus(result.message || '播放節點已建立，請儲存場景。', 'success');
            } catch (error) {
                const detail = error && error.message ? error.message : String(error);
                this.setStatus(`建立失敗：${detail}`, 'error');
            }
        });

        const toolPath = path.join(__dirname, '..', '..', '..', 'static', 'SpinePlayTest-Cocos38.html');
        this.$.tool.src = `${pathToFileURL(toolPath).href}?v=3.8&cocos=1`;
    },
    close() {
        if (this.onToolMessage) {
            window.removeEventListener('message', this.onToolMessage);
        }
    }
});
