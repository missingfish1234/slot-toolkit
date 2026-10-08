(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleZip = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const crcTable = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let value = i;
    for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);
    crcTable[i] = value >>> 0;
  }
  function crc32(bytes) {
    let crc = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) crc = crcTable[(crc ^ bytes[i]) & 255] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }
  function create(entries) {
    if (!Array.isArray(entries) || entries.length > 1000) throw new Error('ZIP 檔案項目過多。');
    const encoder = new TextEncoder();
    const names = new Set();
    const files = entries.map(entry => {
      const name = String(entry.name).replace(/\\/g, '/');
      if (!name || name.startsWith('/') || name.includes(':') || name.split('/').some(part => part === '..' || part === '.') || names.has(name)) throw new Error('ZIP 檔名無效或重複。');
      names.add(name);
      const filename = encoder.encode(name);
      const data = typeof entry.data === 'string' ? encoder.encode(entry.data) : new Uint8Array(entry.data);
      if (filename.length > 65535) throw new Error('ZIP 檔名過長。');
      return {filename, data, crc: crc32(data), offset: 0};
    });
    const dataSize = files.reduce((sum, f) => sum + 30 + f.filename.length + f.data.length, 0);
    const directorySize = files.reduce((sum, f) => sum + 46 + f.filename.length, 0);
    const total = dataSize + directorySize + 22;
    if (total > 96 * 1024 * 1024) throw new Error('輸出超過 96 MB，請減少粒子或素材尺寸。');
    const bytes = new Uint8Array(total);
    const view = new DataView(bytes.buffer);
    let position = 0;
    const now = new Date();
    const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | Math.floor(now.getSeconds() / 2);
    const dosDate = ((Math.max(1980, now.getFullYear()) - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
    const u16 = value => { view.setUint16(position, value, true); position += 2; };
    const u32 = value => { view.setUint32(position, value, true); position += 4; };
    const append = value => { bytes.set(value, position); position += value.length; };
    for (const file of files) {
      file.offset = position;
      u32(0x04034b50); u16(20); u16(0x0800); u16(0); u16(dosTime); u16(dosDate);
      u32(file.crc); u32(file.data.length); u32(file.data.length); u16(file.filename.length); u16(0);
      append(file.filename); append(file.data);
    }
    for (const file of files) {
      u32(0x02014b50); u16(20); u16(20); u16(0x0800); u16(0); u16(dosTime); u16(dosDate);
      u32(file.crc); u32(file.data.length); u32(file.data.length); u16(file.filename.length); u16(0); u16(0); u16(0); u16(0); u32(0); u32(file.offset);
      append(file.filename);
    }
    u32(0x06054b50); u16(0); u16(0); u16(files.length); u16(files.length); u32(directorySize); u32(dataSize); u16(0);
    return bytes;
  }
  function decodeDataUrl(dataUrl) {
    if (typeof dataUrl !== 'string' || !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(dataUrl)) throw new Error('素材必須是內嵌 PNG。');
    const binary = typeof atob === 'function' ? atob(dataUrl.slice(dataUrl.indexOf(',') + 1)) : Buffer.from(dataUrl.slice(dataUrl.indexOf(',') + 1), 'base64').toString('binary');
    return Uint8Array.from(binary, char => char.charCodeAt(0));
  }
  return {create, crc32, decodeDataUrl};
});
