'use strict';

// Verify that makefont.html works when it is the only file sent to a colleague.
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {spawn} = require('child_process');
const {pathToFileURL} = require('url');

const source = path.resolve(__dirname, '..', 'makefont.html');
const browserPath = process.argv[2] || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const temporaryPrefix = 'bmfont-standalone-';
const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), temporaryPrefix));
const standaloneHtml = path.join(temporaryRoot, 'makefont.html');
const profile = path.join(temporaryRoot, 'chrome-profile');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let browserProcess, socket, connection, browserClosed = false;

async function connect(url) {
    socket = new WebSocket(url);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let nextId = 0;
    const pending = new Map();
    socket.onmessage = event => {
        const message = JSON.parse(event.data);
        const request = pending.get(message.id);
        if (!request) return;
        pending.delete(message.id);
        clearTimeout(request.timer);
        message.error ? request.reject(Error(message.error.message)) : request.resolve(message.result);
    };
    return {
        send(method, params = {}) {
            return new Promise((resolve, reject) => {
                const id = ++nextId;
                const timer = setTimeout(() => {
                    pending.delete(id);
                    reject(Error('CDP timeout: ' + method));
                }, 15000);
                pending.set(id, {resolve, reject, timer});
                socket.send(JSON.stringify({id, method, params}));
            });
        }
    };
}

async function evaluate(expression) {
    const result = await connection.send('Runtime.evaluate', {
        expression, awaitPromise: true, returnByValue: true
    });
    if (result.exceptionDetails) {
        throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result.value;
}

async function waitForPort() {
    const activePort = path.join(profile, 'DevToolsActivePort');
    for (let attempt = 0; attempt < 100; attempt++) {
        if (fs.existsSync(activePort)) return fs.readFileSync(activePort, 'utf8').split('\n')[0];
        if (browserProcess.exitCode !== null) throw Error('Chromium exited before opening DevTools');
        await delay(100);
    }
    throw Error('Chromium did not open DevTools');
}

async function main() {
    assert(fs.existsSync(browserPath), 'Chrome/Edge executable not found: ' + browserPath);
    fs.copyFileSync(source, standaloneHtml);
    assert.deepStrictEqual(fs.readdirSync(temporaryRoot), ['makefont.html']);
    assert(!fs.existsSync(path.join(temporaryRoot, 'vendor')));

    browserProcess = spawn(browserPath, [
        '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'
    ], {windowsHide: true, stdio: 'ignore'});
    browserProcess.on('error', () => {});
    const port = await waitForPort();
    const url = pathToFileURL(standaloneHtml).href;
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {method: 'PUT'})).json();
    connection = await connect(target.webSocketDebuggerUrl);
    for (let attempt = 0; attempt < 100; attempt++) {
        if (await evaluate(`location.href===${JSON.stringify(url)} && document.readyState==='complete'`)) break;
        if (attempt === 99) throw Error('Standalone HTML did not finish loading');
        await delay(50);
    }

    const output = await evaluate(`(async () => {
        if (typeof JSZip !== 'function') throw Error('JSZip is unavailable without vendor');
        state.config.fontName = 'standaloneTest';
        state.glyphs = ['0', '1', '.'].map((char, index) => {
            const img = document.createElement('canvas');
            img.width = 16 + index * 4;
            img.height = 24;
            img.getContext('2d').fillRect(1, 1, img.width - 2, 22);
            return {char, charCode: char.codePointAt(0), img, width: img.width, height: img.height};
        });
        if (!packAndDraw()) throw Error(state.packError);
        HTMLAnchorElement.prototype.click = function () {
            window.downloadURL = this.href;
            window.downloadName = this.download;
        };
        URL.revokeObjectURL = () => {};
        await exportZip();
        if (!window.downloadURL) throw Error('Export did not trigger a download');
        const archive = await JSZip.loadAsync(await (await fetch(window.downloadURL)).arrayBuffer());
        const names = Object.keys(archive.files).sort();
        const fnt = await archive.file('standaloneTest.fnt')?.async('string');
        const png = await archive.file('standaloneTest.png')?.async('uint8array');
        return {
            version: JSZip.version,
            downloadName: window.downloadName,
            names,
            fnt,
            pngSignature: png && Array.from(png.slice(0, 8))
        };
    })()`);

    assert.strictEqual(output.version, '3.10.1');
    assert.strictEqual(output.downloadName, 'standaloneTest.zip');
    assert.deepStrictEqual(output.names, ['standaloneTest.fnt', 'standaloneTest.png']);
    assert.match(output.fnt, /page id=0 file="standaloneTest\.png"/);
    assert.match(output.fnt, /chars count=3\n/);
    for (const code of [46, 48, 49]) assert.match(output.fnt, new RegExp(`char id=${code} `));
    assert.deepStrictEqual(output.pngSignature, [137, 80, 78, 71, 13, 10, 26, 10]);
    console.log('Standalone HTML passed: JSZip 3.10.1, atlas packing, PNG/FNT ZIP export');
    await connection.send('Browser.close');
    browserClosed = true;
}

main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
    if (connection && !browserClosed) {
        try { await connection.send('Browser.close'); } catch (_) {}
    }
    if (socket) socket.close();
    if (browserProcess) {
        for (let attempt = 0; attempt < 30 && browserProcess.exitCode === null; attempt++) await delay(100);
        if (browserProcess.exitCode === null) browserProcess.kill();
        await delay(300);
    }
    const resolved = path.resolve(temporaryRoot);
    if (path.dirname(resolved) === path.resolve(os.tmpdir()) && path.basename(resolved).startsWith(temporaryPrefix)) {
        try { fs.rmSync(resolved, {recursive: true, force: true}); }
        catch (_) { console.warn('Temporary browser files could not be removed: ' + resolved); }
    }
});
