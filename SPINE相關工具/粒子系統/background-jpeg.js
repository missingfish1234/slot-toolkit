(function (root, factory) {
  'use strict';
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleBackgroundJPEG = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  const MAX_INPUT_BYTES = 32 * 1024 * 1024;
  const MAX_OUTPUT_BYTES = 4 * 1024 * 1024;
  const MAX_SIDE = 8192, MAX_PIXELS = 16 * 1024 * 1024;
  const DEFAULT_QUALITY = .88;
  const fail = message => { throw new Error(message); };
  function environment(options) {
    const env = options.env || {};
    return {document: env.document || options.document || root.document,
      FileReader: env.FileReader || options.FileReader || root.FileReader,
      Image: env.Image || options.Image || root.Image};
  }
  function settings(options) {
    const quality = options.quality === undefined ? DEFAULT_QUALITY : options.quality;
    if (typeof quality !== 'number' || !Number.isFinite(quality) || quality < .3 || quality > 1) fail('JPG 品質請設為 0.3–1。');
    const background = options.background === undefined ? '#ffffff' : options.background;
    if (typeof background !== 'string' || !/^#(?:[\da-f]{3}|[\da-f]{6})$/i.test(background)) fail('JPG 底色請使用不透明色碼，例如 #ffffff。');
    return {quality, background};
  }
  function dimensions(image) {
    const width = image && (image.naturalWidth || image.width), height = image && (image.naturalHeight || image.height);
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) fail('背景圖片沒有有效尺寸，請重新載入 PNG、JPG 或 WebP。');
    if (width > MAX_SIDE || height > MAX_SIDE) fail('背景圖片單邊不能超過 8192 px，請先裁切或縮小原圖後重新載入。');
    if (width * height > MAX_PIXELS) fail('背景圖片不能超過 16 Mi 像素，請先裁切或縮小原圖後重新載入。');
    return {width, height};
  }
  function filename(name) {
    const base = String(name || 'background').split(/[\\/]/).pop().replace(/\.[^.]*$/, '') || 'background';
    return base + '.jpg';
  }
  function encodedBytes(dataUrl) {
    const match = typeof dataUrl === 'string' && /^data:image\/jpeg;base64,([A-Za-z0-9+/]+={0,2})$/.exec(dataUrl);
    if (!match || match[1].length % 4 !== 0) fail('瀏覽器無法產生 JPG，請改用新版 Chrome 或 Edge 重試。');
    const body = match[1], padding = body.endsWith('==') ? 2 : body.endsWith('=') ? 1 : 0;
    return body.length / 4 * 3 - padding;
  }
  // The decoded source is drawn at its original dimensions. Only JPEG quality
  // changes to meet the size limit; this helper never resizes or writes a file.
  function convert(image, options = {}) {
    const config = settings(options), size = dimensions(image), env = environment(options);
    if (!env.document || typeof env.document.createElement !== 'function') fail('瀏覽器無法建立背景圖片，請改用新版 Chrome 或 Edge。');
    const canvas = env.document.createElement('canvas');
    canvas.width = size.width; canvas.height = size.height;
    const context = canvas.getContext('2d');
    if (!context) fail('記憶體不足，無法轉換背景圖片；請關閉其他分頁後重試。');
    context.fillStyle = config.background;
    context.fillRect(0, 0, size.width, size.height);
    context.drawImage(image, 0, 0, size.width, size.height);
    let quality = config.quality;
    const minimum = Math.min(.4, quality);
    while (true) {
      let dataUrl;
      try { dataUrl = canvas.toDataURL('image/jpeg', quality); }
      catch (_) { fail('背景無法轉成 JPG，請重新載入本機 PNG、JPG 或 WebP 圖片後重試。'); }
      const bytes = encodedBytes(dataUrl);
      if (bytes <= MAX_OUTPUT_BYTES) return {name: filename(options.name), mime: 'image/jpeg',
        width: size.width, height: size.height, dataUrl, sourceWidth: size.width, sourceHeight: size.height,
        quality, bytes, originalBytes: options.originalBytes === undefined ? 0 : options.originalBytes};
      if (quality <= minimum) fail('這張背景在原解析度、降低 JPG 品質後仍超過 4 MiB。請先裁切或縮小圖片後重試；原圖與解析度皆未更動。');
      quality = Math.max(minimum, Math.round((quality - .1) * 1000) / 1000);
    }
  }
  function readFile(file, Reader) {
    if (typeof Reader !== 'function') return Promise.reject(new Error('瀏覽器無法讀取背景檔案，請改用新版 Chrome 或 Edge。'));
    return new Promise((resolve, reject) => {
      const reader = new Reader();
      reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('背景檔案讀取失敗，請重新選擇圖片。'));
      reader.onerror = () => reject(new Error('背景檔案讀取失敗，請重新選擇圖片。'));
      reader.onabort = () => reject(new Error('背景檔案讀取已取消，請重新選擇圖片。'));
      try { reader.readAsDataURL(file); } catch (_) { reject(new Error('背景檔案讀取失敗，請重新選擇圖片。')); }
    });
  }
  function decode(dataUrl, ImageType) {
    if (typeof ImageType !== 'function') return Promise.reject(new Error('瀏覽器無法解碼背景圖片，請改用新版 Chrome 或 Edge。'));
    return new Promise((resolve, reject) => {
      const image = new ImageType(), invalid = () => reject(new Error('背景圖片無法解碼，請重新匯出 PNG、JPG 或 WebP 後載入。'));
      image.onerror = invalid;
      image.onload = () => {
        try {
          Promise.resolve(typeof image.decode === 'function' ? image.decode() : undefined).then(() => resolve(image), invalid);
        } catch (_) { invalid(); }
      };
      try { image.src = dataUrl; } catch (_) { invalid(); }
    });
  }
  async function load(file, options = {}) {
    settings(options);
    if (!file || typeof file.size !== 'number' || !Number.isFinite(file.size) || file.size <= 0) fail('請選擇有效的 PNG、JPG 或 WebP 背景圖片。');
    if (file.size > MAX_INPUT_BYTES) fail('背景來源檔不能超過 32 MiB，請先壓縮或裁切後重新載入。');
    const mime = String(file.type || '').toLowerCase();
    if (mime ? !['image/png', 'image/jpeg', 'image/webp'].includes(mime) : !/\.(?:png|jpe?g|webp)$/i.test(file.name || '')) fail('背景轉 JPG 僅支援 PNG、JPG 或 WebP 圖片。');
    const env = environment(options), dataUrl = await readFile(file, env.FileReader), image = await decode(dataUrl, env.Image);
    return convert(image, {...options, name: file.name, originalBytes: file.size});
  }
  return {load, convert, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, MAX_SIDE, MAX_PIXELS, DEFAULT_QUALITY};
});
