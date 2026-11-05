(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleSpineFolder = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  // Opens an exported Spine project folder (skeleton JSON + images/ or atlas) in
  // one step and, when the browser grants write access, writes the merged result
  // back next to the original with a timestamped backup. The pure planning
  // functions run in Node tests; the handle helpers only run in the browser.
  const SKIP_DIRS = new Set(['_particle_backup', '.git', 'node_modules', '__macosx', '.particle-spine-bridge']);
  const MAX_ENTRIES = 6000;
  const IMAGE = /\.(png|jpe?g|webp)$/i;
  const BACKUP_DIR = '_particle_backup';
  const SPINE_EXPORT_PREFIX = '匯入Spine_';
  const PROJECT_EXPORT_PREFIX = '粒子編輯專案_';
  const PROJECT_SUFFIX = '.particle.json';

  function fail(message) { throw new Error(message); }
  function normalize(path) {
    if (typeof path !== 'string') return null;
    const parts = [];
    for (const part of path.replace(/\\/g, '/').split('/')) {
      if (!part || part === '.') continue;
      if (part === '..') { if (!parts.length) return null; parts.pop(); continue; }
      parts.push(part);
    }
    return parts.join('/');
  }
  const join = (...parts) => normalize(parts.filter(part => part !== '' && part !== null && part !== undefined).join('/'));
  function dirname(path) { const index = path.lastIndexOf('/'); return index < 0 ? '' : path.slice(0, index); }
  function basename(path) { return path.slice(path.lastIndexOf('/') + 1); }
  function stemOf(path) { return basename(path).replace(/\.json$/i, ''); }
  function exportJsonNames(stem) {
    return {spine: SPINE_EXPORT_PREFIX + stem + '.json', project: PROJECT_EXPORT_PREFIX + stem + PROJECT_SUFFIX};
  }
  function within(path, dir) { return !dir || path.startsWith(dir + '/'); }
  function relative(path, dir) { return dir ? path.slice(dir.length + 1) : path; }
  function skipped(path) { return dirname(path).split('/').some(part => SKIP_DIRS.has(part.toLowerCase())); }
  function ownArtifact(name) {
    return /\.particle(?:-receipt)?\.json$/i.test(name) || /^(效果更新記錄|追加清單)\.json$/.test(name) || /\.fx-library\.json$/i.test(name);
  }

  // Candidate skeleton JSON files: everything JSON except files this tool writes.
  function skeletonCandidates(entries) {
    return entries.filter(entry => /\.json$/i.test(entry.path) && !ownArtifact(basename(entry.path)) && !skipped(entry.path))
      .sort((a, b) => a.path.split('/').length - b.path.split('/').length || a.path.localeCompare(b.path));
  }
  function isSkeleton(json) { return !!json && typeof json === 'object' && !!json.skeleton && Array.isArray(json.bones); }

  function imageEntriesUnder(entries, dir, exclude) {
    return entries.filter(entry => IMAGE.test(entry.path) && within(entry.path, dir) && !skipped(entry.path) &&
      !(exclude && within(entry.path, exclude)));
  }
  // Spine writes skeleton.images relative to the JSON file. Absolute editor
  // paths (C:\..., /Users/...) cannot be reached from a dropped folder, so we
  // fall back to an images/ folder next to the JSON, then the JSON folder.
  function resolveImagesRoot(entries, jsonPath, json) {
    const dir = dirname(jsonPath), raw = json && json.skeleton && typeof json.skeleton.images === 'string' ? json.skeleton.images.trim() : '';
    const candidates = [];
    if (raw && !/^([a-z]:|\/|\\\\)/i.test(raw)) { const value = join(dir, raw); if (value !== null) candidates.push({root: value, source: 'json'}); }
    candidates.push({root: join(dir, 'images'), source: 'images'}, {root: join(dir, 'Images'), source: 'images'}, {root: dir, source: 'json-dir'});
    for (const candidate of candidates) {
      if (candidate.root === null) continue;
      const direct = candidate.root === dir ? entries.filter(entry => IMAGE.test(entry.path) && dirname(entry.path) === dir) : imageEntriesUnder(entries, candidate.root);
      if (direct.length) return candidate;
    }
    return {root: raw && !/^([a-z]:|\/|\\\\)/i.test(raw) ? join(dir, raw) || dir : join(dir, 'images'), source: 'missing'};
  }
  // Where Spine itself will look for images: the JSON's relative Images path.
  function declaredImagesRoot(jsonPath, json, fallback) {
    const raw = json && json.skeleton && typeof json.skeleton.images === 'string' ? json.skeleton.images.trim() : '';
    if (!raw || /^([a-z]:|\/|\\\\)/i.test(raw)) return fallback;
    const value = join(dirname(jsonPath), raw);
    return value === null ? fallback : value;
  }
  function atlasPages(text) {
    const pages = []; let expectPage = true;
    for (const raw of String(text).replace(/^\uFEFF/, '').split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) { expectPage = true; continue; }
      if (expectPage) { if (!line.includes(':')) pages.push(line); expectPage = false; }
    }
    return pages;
  }
  function findAtlas(entries, jsonPath) {
    const dir = dirname(jsonPath), stem = stemOf(jsonPath).toLowerCase();
    const near = entries.filter(entry => /\.atlas(\.txt)?$/i.test(entry.path) && dirname(entry.path) === dir);
    return near.find(entry => basename(entry.path).toLowerCase().replace(/\.atlas(\.txt)?$/, '') === stem) || (near.length === 1 ? near[0] : null);
  }
  function findSidecar(entries, jsonPath, suffix) {
    const wanted = join(dirname(jsonPath), stemOf(jsonPath) + suffix);
    return entries.find(entry => entry.path === wanted) || null;
  }
  function findParticleProject(entries, jsonPath) {
    const sameStem = findSidecar(entries, jsonPath, PROJECT_SUFFIX);
    const stem = stemOf(jsonPath);
    if (sameStem || !stem.startsWith(SPINE_EXPORT_PREFIX)) return sameStem;
    const names = exportJsonNames(stem.slice(SPINE_EXPORT_PREFIX.length));
    const wanted = join(dirname(jsonPath), names.project);
    return entries.find(entry => entry.path === wanted) || null;
  }
  function planLoad(entries, jsonPath, json, options = {}) {
    const imagesRoot = resolveImagesRoot(entries, jsonPath, json);
    const exclude = options.excludeImageDir ? join(imagesRoot.root, options.excludeImageDir) : null;
    const images = imageEntriesUnder(entries, imagesRoot.root, exclude).map(entry => ({entry, path: relative(entry.path, imagesRoot.root)}));
    const atlas = findAtlas(entries, jsonPath);
    return {jsonPath, jsonDir: dirname(jsonPath), stem: stemOf(jsonPath), imagesRoot: imagesRoot.root, imagesSource: imagesRoot.source, images, atlas,
      receipt: findSidecar(entries, jsonPath, '.particle-receipt.json'), project: findParticleProject(entries, jsonPath)};
  }
  function atlasPageEntries(entries, atlasPath, text) {
    const dir = dirname(atlasPath), found = [], missing = [];
    atlasPages(text).forEach(name => {
      const path = join(dir, name), entry = path && entries.find(item => item.path === path);
      if (entry) found.push({entry, path: name}); else missing.push(name);
    });
    return {found, missing};
  }

  function stamp(date = new Date()) {
    const pad = value => String(value).padStart(2, '0');
    return date.getFullYear() + pad(date.getMonth() + 1) + pad(date.getDate()) + '-' + pad(date.getHours()) + pad(date.getMinutes()) + pad(date.getSeconds());
  }
  // Everything the write-back touches, so the caller can show it and back it up.
  // images are names relative to the images root ("group/spark.png").
  function planWrite({jsonPath, imagesRoot, images, imageDirectory, existing, time}) {
    if (typeof jsonPath !== 'string' || !normalize(jsonPath)) fail('原骨架 JSON 路徑無效。');
    const dir = dirname(jsonPath), stem = stemOf(jsonPath), root = imagesRoot === null || imagesRoot === undefined ? join(dir, 'images') : imagesRoot;
    const writes = [{path: jsonPath, kind: 'json'}, {path: join(dir, stem + '.particle-receipt.json'), kind: 'receipt'}, {path: join(dir, stem + PROJECT_SUFFIX), kind: 'project'}];
    const imagePaths = new Set();
    (images || []).forEach(name => {
      const path = join(root, name);
      if (!path || !within(path, root)) fail('新增圖片路徑無效：' + name);
      imagePaths.add(path); writes.push({path, kind: 'image'});
    });
    const present = new Set(existing || []);
    const groupDir = imageDirectory ? join(root, imageDirectory) : null;
    const removes = groupDir ? Array.from(present).filter(path => within(path, groupDir) && IMAGE.test(path) && !imagePaths.has(path)) : [];
    const backupDir = BACKUP_DIR + '/' + stamp(time);
    const backups = writes.filter(item => present.has(item.path)).map(item => item.path).concat(removes)
      .map(path => ({from: path, to: backupDir + '/' + path}));
    return {backupDir, writes, removes, backups, imagesRoot: root};
  }

  // ---- Browser helpers ----
  async function collectFromDirectory(handle, prefix = '', list = []) {
    for await (const [name, child] of handle.entries()) {
      if (list.length >= MAX_ENTRIES) fail('資料夾內檔案超過 ' + MAX_ENTRIES + ' 個，請選擇只包含此骨架的匯出資料夾。');
      const path = prefix ? prefix + '/' + name : name;
      if (child.kind === 'directory') { if (!SKIP_DIRS.has(name.toLowerCase())) await collectFromDirectory(child, path, list); }
      else list.push({path, handle: child, getFile: () => child.getFile()});
    }
    return list;
  }
  function entryFile(entry) { return new Promise((resolve, reject) => entry.file(resolve, reject)); }
  async function collectFromEntry(entry, prefix, list) {
    if (list.length >= MAX_ENTRIES) fail('資料夾內檔案超過 ' + MAX_ENTRIES + ' 個，請選擇只包含此骨架的匯出資料夾。');
    const path = prefix ? prefix + '/' + entry.name : entry.name;
    if (entry.isFile) { const file = await entryFile(entry); list.push({path, getFile: async () => file}); return; }
    if (!entry.isDirectory || SKIP_DIRS.has(entry.name.toLowerCase())) return;
    const reader = entry.createReader();
    for (;;) {
      const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length) break;
      for (const child of batch) await collectFromEntry(child, path, list);
    }
  }
  // A dropped folder: prefer a writable handle (Chrome/Edge), else read-only entries.
  async function fromDataTransfer(items) {
    const list = Array.from(items || []).filter(item => item.kind === 'file');
    const folders = [];
    for (const item of list) {
      const entry = typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null;
      if (entry && entry.isDirectory) folders.push({item, entry});
    }
    if (folders.length !== 1) return null;
    const {item, entry} = folders[0];
    let handle = null;
    if (typeof item.getAsFileSystemHandle === 'function') { try { handle = await item.getAsFileSystemHandle(); } catch (_) { handle = null; } }
    if (handle && handle.kind === 'directory') return {name: handle.name, handle, entries: await collectFromDirectory(handle)};
    const entries = [];
    const reader = entry.createReader();
    for (;;) {
      const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length) break;
      for (const child of batch) await collectFromEntry(child, '', entries);
    }
    return {name: entry.name, handle: null, entries};
  }
  function fromFileList(files) {
    const list = Array.from(files || []);
    if (!list.length) return null;
    const first = list[0].webkitRelativePath || '';
    const name = first.includes('/') ? first.split('/')[0] : '';
    const entries = list.map(file => {
      const raw = file.webkitRelativePath || file.name;
      return {path: name && raw.startsWith(name + '/') ? raw.slice(name.length + 1) : raw, getFile: async () => file};
    }).filter(entry => !skipped(entry.path));
    return {name: name || 'files', handle: null, entries};
  }
  async function walkTo(directory, parts, create) {
    let current = directory;
    for (const part of parts) current = await current.getDirectoryHandle(part, {create});
    return current;
  }
  async function fileHandle(directory, path, create) {
    const parts = path.split('/'), name = parts.pop();
    return (await walkTo(directory, parts, create)).getFileHandle(name, {create});
  }
  async function readText(directory, path) {
    try { return await (await (await fileHandle(directory, path, false)).getFile()).text(); } catch (_) { return null; }
  }
  async function fileSignature(directory, path) {
    try { const file = await (await fileHandle(directory, path, false)).getFile(); return file.size + ':' + file.lastModified; } catch (_) { return null; }
  }
  async function writeFile(directory, path, data) {
    const handle = await fileHandle(directory, path, true), writable = await handle.createWritable();
    try { await writable.write(data); } finally { await writable.close(); }
  }
  async function copyFile(directory, from, to) {
    const source = await (await fileHandle(directory, from, false)).getFile();
    await writeFile(directory, to, await source.arrayBuffer());
  }
  async function removeFile(directory, path) {
    const parts = path.split('/'), name = parts.pop();
    await (await walkTo(directory, parts, false)).removeEntry(name);
  }
  async function ensureWritable(handle) {
    if (!handle || typeof handle.queryPermission !== 'function') return false;
    const options = {mode: 'readwrite'};
    if (await handle.queryPermission(options) === 'granted') return true;
    return await handle.requestPermission(options) === 'granted';
  }
  // data: Map(path -> string | Uint8Array). Backups first, then writes, then
  // stale group images; a failure before writing leaves the original intact.
  async function executeWrite(directory, plan, data) {
    for (const backup of plan.backups) await copyFile(directory, backup.from, backup.to);
    for (const item of plan.writes) {
      if (!data.has(item.path)) fail('缺少要寫入的資料：' + item.path);
      await writeFile(directory, item.path, data.get(item.path));
    }
    for (const path of plan.removes) await removeFile(directory, path);
    return {written: plan.writes.length, backedUp: plan.backups.length, removed: plan.removes.length};
  }
  const supportsWrite = () => typeof globalThis.showDirectoryPicker === 'function';

  return {normalize, join, dirname, declaredImagesRoot, basename, stemOf, exportJsonNames, ownArtifact, isSkeleton, skeletonCandidates, resolveImagesRoot, atlasPages, findAtlas,
    planLoad, atlasPageEntries, planWrite, stamp, BACKUP_DIR,
    collectFromDirectory, fromDataTransfer, fromFileList, readText, fileSignature, writeFile, executeWrite, ensureWritable, supportsWrite};
});
