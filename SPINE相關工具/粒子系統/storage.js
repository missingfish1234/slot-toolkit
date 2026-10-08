(function (root, factory) {
  'use strict';
  const Merge = typeof module === 'object' && module.exports ? require('./spine-merge.js') : root.ParticleSpineMerge;
  var api = factory(root, Merge);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleStorage = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root, Merge) {
  'use strict';

  const FORMAT = 'particle-studio-project';
  const MAX_BYTES = 48 * 1024 * 1024;
  const DATABASE_NAME = 'particle-studio-local';
  const STORE_NAME = 'drafts';
  const DRAFT_KEY = 'last';
  const FALLBACK_KEY = 'particle-studio-draft-v1';
  let databasePromise = null;
  let lastSavedAt = 0;
  const isObject = value => !!value && typeof value === 'object' && !Array.isArray(value);
  const finite = (value, fallback) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  // Count UTF-8 bytes without allocating another copy of a potentially large project.
  function checkTextSize(text) {
    if (text.length > MAX_BYTES) throw new Error('專案檔超過 48 MiB，請縮小內嵌素材後重試。');
    let bytes = 0;
    for (let i = 0; i < text.length; i++) {
      const code = text.charCodeAt(i);
      if (code < 0x80) bytes++;
      else if (code < 0x800) bytes += 2;
      else if (code >= 0xd800 && code <= 0xdbff && i + 1 < text.length && text.charCodeAt(i + 1) >= 0xdc00 && text.charCodeAt(i + 1) <= 0xdfff) {
        bytes += 4;
        i++;
      } else bytes += 3;
      if (bytes > MAX_BYTES) throw new Error('專案檔超過 48 MiB，請縮小內嵌素材後重試。');
    }
  }

  function projectIdentity(project, label) {
    if (!isObject(project) || project.format !== 'particle-studio' || project.schemaVersion !== 1) {
      throw new Error((label || '專案') + '必須是 Particle Studio 第 1 版專案。');
    }
  }

  function normalizeView(raw, project, bakedProject, integration) {
    const source = isObject(raw) ? raw : {};
    const mode = source.mode === 'baked' && bakedProject ? 'baked' : 'live';
    const current = mode === 'baked' ? bakedProject : project;
    const flow = current.flow && current.flow.enabled ? current.flow : null;
    const phase = ['in', 'loop', 'out'].includes(source.phase) ? source.phase : 'loop';
    let duration = finite(flow && flow[phase] ? flow[phase].duration : current.duration, 3);
    if (source.previewAttached !== false && integration && integration.settings.enabled !== false) {
      const target = flow ? (integration.settings.flowTargets || {})[phase] : integration.settings;
      if (target) {
        const original = Merge.inspect(integration.json).animations.find(a => a.name === target.animationName);
        duration = Math.max(original ? original.duration : 0, finite(target.startTime, 0) + duration);
      }
    }
    const result = {
      time: clamp(finite(source.time, 0), 0, Math.max(0, duration)),
      mode,
      zoom: clamp(finite(source.zoom, 1), 0.25, 2),
      panX: finite(source.panX, 0),
      panY: finite(source.panY, 0)
    };
    if (flow) result.phase = phase;
    if (typeof source.previewAttached === 'boolean') result.previewAttached = source.previewAttached;
    if (typeof source.showBones === 'boolean') result.showBones = source.showBones;
    if (typeof source.skinName === 'string') result.skinName = source.skinName.slice(0, 1024);
    return result;
  }

  function serialize(project, bakedProject, view, integration) {
    projectIdentity(project);
    const baked = bakedProject === undefined || bakedProject === null ? null : bakedProject;
    if (baked) projectIdentity(baked, '烘焙專案');
    let text;
    try {
      const session = integration !== undefined && integration !== null ? Merge.normalizeSession(integration) : null;
      const data = {format: FORMAT, schemaVersion: 1, project, bakedProject: baked,
        view: normalizeView(view, project, baked, session)};
      if (session) data.integration = session;
      text = JSON.stringify(data, null, 2);
    } catch (_) {
      throw new Error('專案含有無法儲存的資料，請檢查專案內容。');
    }
    checkTextSize(text);
    return text;
  }

  function parse(text, Core) {
    if (typeof text !== 'string') throw new Error('請提供 JSON 格式的專案文字。');
    checkTextSize(text);
    if (!Core || typeof Core.normalizeProject !== 'function') throw new Error('粒子核心尚未載入，無法開啟專案。');
    let raw;
    try { raw = JSON.parse(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text); }
    catch (_) { throw new Error('專案 JSON 格式不正確，請確認檔案完整。'); }
    if (!isObject(raw)) throw new Error('專案內容必須是 Particle Studio 專案物件。');
    if (raw.skeleton || (Array.isArray(raw.bones) && raw.animations)) {
      throw new Error('這是 Spine 動畫輸出，無法作為粒子編輯專案開啟。請載入 Particle Studio 專案檔。');
    }
    if (raw.format !== FORMAT && raw.format !== 'particle-studio') {
      throw new Error('不支援此專案格式。第三方粒子參數不能直接開啟，請使用 Particle Studio 專案檔。');
    }
    if (raw.schemaVersion !== 1) throw new Error('不支援此 Particle Studio 專案版本，目前僅支援 schemaVersion 1。');
    const wrapper = raw.format === FORMAT;
    const project = Core.normalizeProject(wrapper ? raw.project : raw);
    let bakedProject = null;
    if (wrapper && raw.bakedProject !== undefined && raw.bakedProject !== null) {
      try { bakedProject = Core.normalizeProject(raw.bakedProject); }
      catch (error) { throw new Error('儲存的烘焙專案無效：' + error.message); }
    }
    const parsed = {project, bakedProject, view: normalizeView(wrapper ? raw.view : null, project, bakedProject)};
    if (wrapper && raw.integration !== undefined && raw.integration !== null) {
      try { parsed.integration = Merge.normalizeSession(raw.integration); }
      catch (error) { throw new Error('儲存的 Spine 掛接設定無效：' + error.message); }
    }
    parsed.view = normalizeView(wrapper ? raw.view : null, project, bakedProject, parsed.integration);
    return parsed;
  }

  function openDatabase() {
    if (databasePromise) return databasePromise;
    databasePromise = new Promise((resolve, reject) => {
      let request, timer, settled = false;
      function finish(error, db) {
        if (settled) { if (db) db.close(); return; }
        settled = true;
        if (timer !== undefined) root.clearTimeout(timer);
        if (error) reject(error);
        else {
          db.onversionchange = function () { db.close(); databasePromise = null; };
          resolve(db);
        }
      }
      try {
        if (!root.indexedDB) { finish(new Error('IndexedDB 不可用')); return; }
        request = root.indexedDB.open(DATABASE_NAME, 1);
        request.onupgradeneeded = function () {
          try {
            if (!request.result.objectStoreNames.contains(STORE_NAME)) request.result.createObjectStore(STORE_NAME);
          } catch (error) {
            if (request.transaction) request.transaction.abort();
            finish(error);
          }
        };
        request.onsuccess = function () { finish(null, request.result); };
        request.onerror = function () { finish(request.error || new Error('IndexedDB 無法開啟')); };
        request.onblocked = function () { finish(new Error('IndexedDB 被其他視窗占用')); };
        // Some restricted browser contexts leave the open request pending indefinitely.
        timer = root.setTimeout(function () { finish(new Error('IndexedDB 開啟逾時')); }, 2500);
      } catch (error) { finish(error); }
    });
    return databasePromise;
  }

  function writeDatabase(db, record) {
    return new Promise((resolve, reject) => {
      let transaction;
      try {
        transaction = db.transaction(STORE_NAME, 'readwrite');
        const request = transaction.objectStore(STORE_NAME).put(record, DRAFT_KEY);
        request.onerror = function () { reject(request.error || new Error('草稿寫入失敗')); };
        transaction.oncomplete = function () { resolve(); };
        transaction.onerror = function () { reject(transaction.error || new Error('草稿交易失敗')); };
        transaction.onabort = function () { reject(transaction.error || new Error('草稿交易中止')); };
      } catch (error) {
        if (transaction) { try { transaction.abort(); } catch (_) {} }
        reject(error);
      }
    });
  }

  function readDatabase(db) {
    return new Promise((resolve, reject) => {
      let result = null;
      try {
        const transaction = db.transaction(STORE_NAME, 'readonly');
        const request = transaction.objectStore(STORE_NAME).get(DRAFT_KEY);
        request.onsuccess = function () { result = request.result === undefined ? null : request.result; };
        request.onerror = function () { reject(request.error || new Error('草稿讀取失敗')); };
        transaction.oncomplete = function () { resolve(result); };
        transaction.onerror = function () { reject(transaction.error || new Error('草稿讀取交易失敗')); };
        transaction.onabort = function () { reject(transaction.error || new Error('草稿讀取交易中止')); };
      } catch (error) { reject(error); }
    });
  }

  function draftRecord(raw) {
    if (!isObject(raw)) return null;
    if (raw.storageVersion === 1 && isObject(raw.payload)) return {savedAt: finite(raw.savedAt, 0), payload: raw.payload};
    // Read drafts saved by the initial implementation without storage metadata.
    if (raw.format === FORMAT || raw.format === 'particle-studio') return {savedAt: 0, payload: raw};
    return null;
  }

  async function saveDraft(payload) {
    // Store a detached JSON value so later edits cannot alter a pending draft.
    let copy;
    try {
      if (!isObject(payload)) throw new Error('Invalid draft');
      const text = JSON.stringify(payload);
      checkTextSize(text);
      copy = JSON.parse(text);
    } catch (_) { throw new Error('本機草稿無法保存，請儲存專案檔'); }
    lastSavedAt = Math.max(Date.now(), lastSavedAt + 1);
    const record = {storageVersion: 1, savedAt: lastSavedAt, payload: copy};
    try {
      await writeDatabase(await openDatabase(), record);
      return {backend: 'indexeddb'};
    } catch (_) {
      try {
        if (!root.localStorage) throw new Error('LocalStorage 不可用');
        root.localStorage.setItem(FALLBACK_KEY, JSON.stringify(record));
        return {backend: 'localstorage'};
      } catch (_) { throw new Error('本機草稿無法保存，請儲存專案檔'); }
    }
  }

  async function loadDraft() {
    let primary = null, fallback = null;
    try { primary = draftRecord(await readDatabase(await openDatabase())); } catch (_) {}
    try {
      if (root.localStorage) {
        const text = root.localStorage.getItem(FALLBACK_KEY);
        if (text !== null) { checkTextSize(text); fallback = draftRecord(JSON.parse(text)); }
      }
    } catch (_) {}
    const record = !primary ? fallback : fallback && fallback.savedAt > primary.savedAt ? fallback : primary;
    if (!record) return null;
    lastSavedAt = Math.max(lastSavedAt, record.savedAt);
    return record.payload;
  }

  return {serialize, parse, saveDraft, loadDraft};
});
