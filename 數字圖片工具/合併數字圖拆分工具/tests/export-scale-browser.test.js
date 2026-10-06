'use strict';
// Exercises the real HTML tool in a fresh headless Chrome profile. Downloads
// are intercepted in the page, so no user browser profile or downloads folder is used.
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {spawn} = require('child_process');
const {pathToFileURL} = require('url');

const browserPath = process.argv[2] || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'split-export-scale-'));
const proc = spawn(browserPath, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'
], {windowsHide: true, stdio: 'ignore'});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let connection;
let browserClosed = false;

async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0;
  const waiters = new Map();
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    const waiter = waiters.get(message.id);
    if (!waiter) return;
    waiters.delete(message.id);
    message.error ? waiter.reject(Error(message.error.message)) : waiter.resolve(message.result);
  };
  return {
    close: () => socket.close(),
    send: (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++sequence;
      waiters.set(id, {resolve, reject});
      socket.send(JSON.stringify({id, method, params}));
      setTimeout(() => {
        if (waiters.delete(id)) reject(Error('CDP timeout: ' + method));
      }, 15000).unref();
    })
  };
}

async function evaluate(expression) {
  const response = await connection.send('Runtime.evaluate', {
    expression, awaitPromise: true, returnByValue: true
  });
  if (response.exceptionDetails) {
    throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
  }
  return response.result.value;
}

(async () => {
  let port;
  for (let i = 0; i < 100; i++) {
    const activePort = path.join(profile, 'DevToolsActivePort');
    if (fs.existsSync(activePort)) {
      port = fs.readFileSync(activePort, 'utf8').split('\n')[0];
      break;
    }
    await delay(100);
  }
  if (!port) throw Error('Headless Chrome did not start: ' + browserPath);

  const file = path.resolve(__dirname, '..', 'split_glyph_tool_dragdrop_v5.html');
  const url = pathToFileURL(file).href;
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {method: 'PUT'})).json();
  connection = await connect(target.webSocketDebuggerUrl);
  for (let i = 0; i < 100; i++) {
    if (await evaluate(`location.href === ${JSON.stringify(url)} && document.readyState === 'complete'`)) break;
    if (i === 99) throw Error('HTML load timeout');
    await delay(50);
  }

  const result = await evaluate(`(async () => {
    const must = (condition, message) => { if (!condition) throw Error(message); };
    const scaleInput = $('outputScale');
    must(scaleInput && scaleInput.type === 'number', 'Missing outputScale number input');
    must(scaleInput.value === '100', 'Default output scale must be 100%');
    must(typeof JSZip !== 'undefined', 'Offline JSZip did not load');

    srcCanvas.width = 80;
    srcCanvas.height = 24;
    srcCtx.clearRect(0, 0, 80, 24);
    srcCtx.fillStyle = '#ffffff';
    srcCtx.fillRect(3, 3, 12, 16);
    srcCtx.fillRect(40, 3, 10, 16);
    srcImg = srcCanvas;
    $('chars').value = '0萬';
    $('maskMode').value = 'alpha';
    $('gapMerge').value = '0';
    $('minRun').value = '1';
    $('heightMode').value = 'source';

    window.showSaveFilePicker = undefined;
    const captures = [];
    HTMLAnchorElement.prototype.click = function () {
      captures.push({name: this.download, bytes: fetch(this.href).then(response => response.arrayBuffer())});
    };
    async function takeDownload(expectedName) {
      for (let i = 0; i < 200 && captures.length === 0; i++) {
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      must(captures.length > 0, 'Download was not triggered: ' + expectedName);
      const capture = captures.shift();
      must(capture.name === expectedName, 'Wrong download filename: ' + capture.name);
      return capture.bytes;
    }
    async function readPng(bytes) {
      const bitmap = await createImageBitmap(new Blob([bytes], {type: 'image/png'}));
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext('2d', {willReadFrequently: true});
      context.drawImage(bitmap, 0, 0);
      bitmap.close();
      return {width: canvas.width, height: canvas.height,
        pixels: context.getImageData(0, 0, canvas.width, canvas.height).data};
    }
    const alpha = (image, x, y) => image.pixels[(y * image.width + x) * 4 + 3];
    const expectedOriginal = [{char: '0', name: '0.png', width: 16, opaque: 192},
      {char: '萬', name: 'u842c.png', width: 12, opaque: 160}];
    const summaries = [];

    for (const percent of [100, 50, 67.5, 150]) {
      scaleInput.value = String(percent);
      scaleInput.dispatchEvent(new Event('change', {bubbles: true}));
      must(!err.textContent, percent + '% split error: ' + err.textContent);
      must(results.length === 2, percent + '% should produce two glyphs');
      const zipBtn = $('zipBtn');
      must(!zipBtn.disabled, percent + '% ZIP should be enabled');

      const singleImages = [];
      for (let i = 0; i < expectedOriginal.length; i++) {
        const expected = expectedOriginal[i];
        const width = Math.max(1, Math.round(expected.width * percent / 100));
        const height = Math.max(1, Math.round(24 * percent / 100));
        must(results[i].char === expected.char && results[i].name + '.png' === expected.name,
          percent + '% glyph order or filename changed');
        must(results[i].canvas.width === width && results[i].canvas.height === height,
          percent + '% result canvas dimensions wrong for ' + expected.char);

        const button = document.querySelectorAll('#out .tile button')[i];
        must(!!button, 'Single PNG download button missing for ' + expected.char);
        button.click();
        const image = await readPng(await takeDownload(expected.name));
        must(image.width === width && image.height === height,
          percent + '% single PNG dimensions wrong for ' + expected.char);
        must(alpha(image, 0, 0) === 0, percent + '% transparent corner lost');
        must(alpha(image, Math.floor(width / 2), Math.floor(height / 2)) === 255,
          percent + '% solid center pixel lost for ' + expected.char);
        if (percent === 100) {
          let opaque = 0;
          for (let p = 3; p < image.pixels.length; p += 4) if (image.pixels[p] === 255) opaque++;
          must(opaque === expected.opaque, '100% changed source pixels for ' + expected.char);
        }
        if (percent === 50) {
          must(alpha(image, Math.floor(width / 2), height - 1) === 0,
            '50% content was cropped instead of scaled for ' + expected.char);
          if (i === 0) must(alpha(image, width - 1, Math.floor(height / 2)) === 0,
            '50% digit width was cropped instead of scaled');
        }
        if (percent === 150) {
          must(alpha(image, Math.floor(width * 0.75), Math.floor(height / 2)) === 255 &&
            alpha(image, Math.floor(width / 2), 25) === 255,
            '150% content did not grow in both axes for ' + expected.char);
        }
        singleImages.push(image);
      }

      await downloadZip();
      const zip = await JSZip.loadAsync(await takeDownload('split_glyphs.zip'));
      const names = Object.keys(zip.files).sort();
      must(JSON.stringify(names) === JSON.stringify(['0.png', 'glyph-map.json', 'u842c.png']),
        percent + '% ZIP entries changed: ' + names.join(','));
      const glyphs = JSON.parse(await zip.file('glyph-map.json').async('string')).glyphs;
      must(glyphs.length === 2 && glyphs[0].file === '0.png' && glyphs[0].char === '0' && glyphs[0].codePoint === 48 &&
        glyphs[1].file === 'u842c.png' && glyphs[1].char === '萬' && glyphs[1].codePoint === 0x842c,
        percent + '% glyph-map Unicode mapping changed');
      for (let i = 0; i < expectedOriginal.length; i++) {
        const zipImage = await readPng(await zip.file(expectedOriginal[i].name).async('uint8array'));
        const single = singleImages[i];
        must(zipImage.width === single.width && zipImage.height === single.height,
          percent + '% ZIP/PNG dimensions differ for ' + expectedOriginal[i].char);
        must(zipImage.pixels.length === single.pixels.length &&
          zipImage.pixels.every((value, index) => value === single.pixels[index]),
          percent + '% ZIP/PNG pixels differ for ' + expectedOriginal[i].char);
      }
      summaries.push(percent + '%');
    }

    for (const value of ['0', '-1', '401', '']) {
      scaleInput.value = value;
      scaleInput.dispatchEvent(new Event('change', {bubbles: true}));
      must(results.length === 0 && $('zipBtn').disabled && !!err.textContent,
        'Invalid scale ' + JSON.stringify(value) + ' did not block split/export');
      const before = captures.length;
      await downloadZip();
      must(captures.length === before, 'Invalid scale triggered a ZIP download');
    }
    return {scales: summaries, invalidScales: 4};
  })()`);

  assert.deepStrictEqual(result, {scales: ['100%', '50%', '67.5%', '150%'], invalidScales: 4});
  console.log('REAL CHROME PASSED: 100/50/67.5/150% single PNG and ZIP pixels, Unicode map, invalid scale blocking');
  await connection.send('Browser.close');
  browserClosed = true;
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (connection && !browserClosed) { try { await connection.send('Browser.close'); } catch (_) {} }
  if (connection) connection.close();
  for (let i = 0; i < 30 && proc.exitCode === null; i++) await delay(100);
  if (proc.exitCode === null) proc.kill();
  await delay(300);
  const resolved = path.resolve(profile);
  const base = path.resolve(os.tmpdir()) + path.sep;
  if (resolved.startsWith(base) && path.basename(resolved).startsWith('split-export-scale-')) {
    try { fs.rmSync(resolved, {recursive: true, force: true}); }
    catch (_) { console.log('Temporary Chrome profile retained (locked): ' + resolved); }
  }
});
