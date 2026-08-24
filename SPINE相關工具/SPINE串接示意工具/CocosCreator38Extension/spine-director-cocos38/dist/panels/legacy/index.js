'use strict';

const path = require('path');
const { pathToFileURL } = require('url');
const packageJSON = require('../../../package.json');

module.exports = Editor.Panel.define({
    template: `
        <div id="app">
            <div id="toolbar">
                <span class="version">Creator 3.8 / Spine 3.8</span>
                <button id="import-asset" title="先在資源管理器選取 .skel、.json 或 .atlas">載入專案 Spine</button>
                <button id="bind-node" title="先在階層管理器選取含 sp.Skeleton 的節點">綁定 Scene 節點</button>
                <button id="restore-preview" title="還原開始預覽前的 Scene 狀態">還原 Scene</button>
                <span id="status">就緒</span>
                <button id="create-node" disabled>建立播放節點</button>
            </div>
            <iframe id="tool" allow="clipboard-write"></iframe>
        </div>
    `,
    style: `
        :host { display: block; width: 100%; height: 100%; }
        #app { display: flex; flex-direction: column; width: 100%; height: 100%; background: #1e1e1e; }
        #toolbar { min-height: 34px; flex: 0 0 auto; display: flex; align-items: center; gap: 7px; padding: 4px 10px; border-bottom: 1px solid #3c3c3c; color: #ddd; font: 12px sans-serif; }
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
        importAsset: '#import-asset',
        bindNode: '#bind-node',
        restorePreview: '#restore-preview',
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
        this.previewBusy = false;
        this.pendingPreview = null;
        this.requestSpineImport = async (messageName, loadingMessage) => {
            this.setStatus(loadingMessage);
            this.$.importAsset.disabled = true;
            this.$.bindNode.disabled = true;
            try {
                const result = await Editor.Message.request(packageJSON.name, messageName);
                const items = Array.isArray(result.items) ? result.items : [result];
                const names = items.map(item => item.bundle && item.bundle.name).filter(Boolean);
                const warning = result.errors && result.errors.length ? `；${result.errors.length} 個項目略過` : '';
                this.setStatus(`已載入 ${items.length} 組：${names.join(', ')}${warning}`, 'success');
                this.sendToTool({
                    source: 'spine-director-cocos38-host',
                    type: 'import-cocos-spines',
                    payload: items
                });
            } catch (error) {
                const detail = error && error.message ? error.message : String(error);
                this.setStatus(`載入失敗：${detail}`, 'error');
            } finally {
                this.$.importAsset.disabled = false;
                this.$.bindNode.disabled = false;
            }
        };
        this.flushScenePreview = async () => {
            if (this.previewBusy || !this.pendingPreview) return;
            this.previewBusy = true;
            try {
                while (this.pendingPreview) {
                    const payload = this.pendingPreview;
                    this.pendingPreview = null;
                    await Editor.Message.request(packageJSON.name, 'preview-scene', payload);
                }
            } catch (error) {
                const detail = error && error.message ? error.message : String(error);
                this.setStatus(`Scene 預覽失敗：${detail}`, 'error');
                this.pendingPreview = null;
            } finally {
                this.previewBusy = false;
            }
        };
        this.onToolMessage = async (event) => {
            const message = event.data;
            if (!message || message.source !== 'spine-director-cocos38') return;

            if (message.type === 'scene-preview') {
                this.pendingPreview = message.payload;
                void this.flushScenePreview();
            } else if (message.type === 'export-project') {
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

        this.$.importAsset.addEventListener('click', () => {
            void this.requestSpineImport('import-selected-spine', '正在讀取資源管理器選取的 Spine…');
        });
        this.$.bindNode.addEventListener('click', () => {
            void this.requestSpineImport('bind-selected-spine-node', '正在讀取階層管理器選取的 Spine 節點…');
        });
        this.$.restorePreview.addEventListener('click', async () => {
            try {
                const result = await Editor.Message.request(packageJSON.name, 'restore-scene-preview');
                this.setStatus(`已還原 ${result.restored || 0} 個 Scene 節點`, 'success');
            } catch (error) {
                const detail = error && error.message ? error.message : String(error);
                this.setStatus(`還原失敗：${detail}`, 'error');
            }
        });

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
        void Editor.Message.request(packageJSON.name, 'restore-scene-preview').catch(() => {});
    }
});
