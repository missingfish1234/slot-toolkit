'use strict';

// A dependency-free, deterministic build. The editable source files stay separate.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const workspace = path.resolve(__dirname, '..');
const scripts = ['curve-math.js', 'core.js', 'zip.js', 'spine-merge.js', 'storage.js', 'preview.js', 'scrub.js', 'curve-editor.js', 'gradient-editor.js', 'spine-attachment-ui.js', 'flow-playback.js',
  'spine-runtimes.js', 'spine-runtime-preview.js', 'spine-canvas-renderer.js', 'attachment-preview.js', 'spine-assets-ui.js', 'app.js'];
const output = path.join(workspace, 'dist', 'Particle-Studio.html');

function attribute(tag, name) {
  const expression = new RegExp('(?:^|\\s)' + name + '\\s*=\\s*(?:"([^"]*)"|\'([^\']*)\'|([^\\s"\'=<>`]+))', 'i');
  const match = expression.exec(tag);
  return match ? match[1] !== undefined ? match[1] : match[2] !== undefined ? match[2] : match[3] : null;
}

function localName(reference) {
  return reference && reference.replace(/^\.\//, '');
}

function build() {
  const required = ['index.html', 'styles.css'].concat(scripts);
  const missing = required.filter(name => !fs.existsSync(path.join(workspace, name)));
  if (missing.length) {
    throw new Error('建置缺少必要檔案：' + missing.join('、') + '。請完成這些檔案後重新建置；不會產生缺少功能的 HTML。');
  }
  const sources = Object.fromEntries(required.map(name => [name, fs.readFileSync(path.join(workspace, name), 'utf8')]));
  // Catch accidental source syntax errors before replacing the previous build.
  scripts.forEach(name => new vm.Script(sources[name], {filename: name}));

  let html = sources['index.html'];
  let stylesheetCount = 0;
  const includedScripts = [];
  html = html.replace(/<link\b[^>]*>/gi, tag => {
    const href = attribute(tag, 'href');
    if (href === null) return tag;
    const rel = attribute(tag, 'rel');
    if (rel && rel.toLowerCase() === 'stylesheet' && localName(href) === 'styles.css') {
      stylesheetCount++;
      // HTML raw-text parsing recognizes closing tags even inside CSS strings/comments.
      return '<style data-bundle="styles.css">\n' + sources['styles.css'].replace(/<\/style/gi, '<\\/style') + '\n</style>';
    }
    throw new Error('離線建置不支援此外部或未內嵌的 link 資源：' + href);
  });
  html = html.replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, tag => {
    const openTag = /^<script\b[^>]*>/i.exec(tag)[0];
    const src = attribute(openTag, 'src');
    if (src === null) return tag;
    const name = localName(src);
    if (!scripts.includes(name)) throw new Error('離線建置不支援此外部或未知的 script：' + src);
    const type = attribute(openTag, 'type');
    if (type && !['text/javascript', 'application/javascript'].includes(type.toLowerCase())) {
      throw new Error(name + ' 必須使用傳統 script，不能使用 module 或其他 script 類型。');
    }
    if (/\s(?:async|defer)\b/i.test(openTag)) throw new Error(name + ' 的 async/defer 載入方式無法安全轉成單一離線檔。');
    includedScripts.push(name);
    // Keep JS string values unchanged while preventing a literal HTML closing tag.
    return '<script data-bundle="' + name + '">\n' + sources[name].replace(/<\/script/gi, '<\\/script') + '\n</script>';
  });
  if (stylesheetCount !== 1) throw new Error('index.html 必須且只能載入一次 styles.css。');
  if (includedScripts.join('|') !== scripts.join('|')) {
    throw new Error('index.html 必須依序且各載入一次：' + scripts.join(' → ') + '。');
  }
  if (/<script\b[^>]*\bsrc\s*=/i.test(html) || /<link\b[^>]*\bhref\s*=/i.test(html)) {
    throw new Error('離線建置檢查失敗：HTML 仍含未內嵌的 script 或 link 資源。');
  }
  const cssUrls = Array.from(sources['styles.css'].matchAll(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))\s*\)/gi));
  const externalCssUrl = cssUrls.some(match => !/^(?:data:|#)/i.test((match[1] || match[2] || match[3] || '').trim()));
  if (/@import\b/i.test(sources['styles.css']) || externalCssUrl) {
    throw new Error('離線建置檢查失敗：樣式仍引用外部或本機資源。請將資源內嵌後重試。');
  }
  const inlineScripts = Array.from(html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi));
  if (inlineScripts.length !== scripts.length) throw new Error('離線建置檢查失敗：內嵌 script 數量不正確。');
  inlineScripts.forEach((match, index) => new vm.Script(match[1], {filename: 'inline:' + scripts[index]}));

  fs.mkdirSync(path.dirname(output), {recursive: true});
  fs.writeFileSync(output, html, 'utf8');
  process.stdout.write('已建立 dist/Particle-Studio.html（' + Math.ceil(Buffer.byteLength(html, 'utf8') / 1024) + ' KiB）\n');
  process.stdout.write('樣式與 ' + scripts.length + ' 個程式檔已內嵌，可直接開啟，不需要伺服器或網路。\n');
}

try { build(); }
catch (error) {
  process.stderr.write('建置失敗：' + error.message + '\n');
  process.exitCode = 1;
}
