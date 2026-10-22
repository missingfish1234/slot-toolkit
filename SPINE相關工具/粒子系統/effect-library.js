(function (root, factory) {
  'use strict';
  const Core = typeof module === 'object' && module.exports ? require('./core.js') : root.ParticleCore;
  const api = factory(root, Core);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleEffectLibrary = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root, Core) {
  'use strict';
  const FORMAT = 'particle-studio-fx-library', MAX_ITEMS = 100, MAX_BYTES = 48 * 1024 * 1024, MAX_ITEM_BYTES = 16 * 1024 * 1024;
  const DATABASE_NAME = 'particle-studio-effects', STORE_NAME = 'library', RECORD_KEY = 'current', FALLBACK_KEY = 'particle-studio-effects-v1';
  const ANCHOR_KEYS = ['id', 'name', 'x', 'y', 'enabled'];
  const EFFECT_KEYS = new Set(Object.keys(Core.createEmitter()).filter(key => !ANCHOR_KEYS.includes(key)).concat(['directionMode', 'directionSpread', 'emitFrom', 'path', 'outline', 'sequence', 'randomSeed', 'separateSizeAxes', 'sizeCurveX', 'sizeCurveY', 'startDelay']));
  const clone = value => JSON.parse(JSON.stringify(value));
  const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  let sequence = 0;

  function byteLength(text, limit, label) {
    if (typeof text !== 'string' || text.length > limit) throw new Error(label + '超過大小限制。');
    let bytes = 0;
    for (let i = 0; i < text.length; i++) {
      const c = text.charCodeAt(i);
      if (c < 128) bytes++;
      else if (c < 2048) bytes += 2;
      else if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length && text.charCodeAt(i + 1) >= 0xdc00 && text.charCodeAt(i + 1) <= 0xdfff) { bytes += 4; i++; }
      else bytes += 3;
      if (bytes > limit) throw new Error(label + '超過大小限制。');
    }
    return bytes;
  }

  // Validate before copying. In particular JSON.stringify would otherwise silently
  // erase non-JSON values or invoke arbitrary toJSON methods in a supplied object.
  function safeValue(raw) {
    const seen = new Set(); let nodes = 0;
    function visit(value, depth) {
      if (++nodes > 200000 || depth > 16) throw new Error('效果資料結構過大或過深。');
      if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
      if (typeof value === 'number' && Number.isFinite(value)) return;
      if (typeof value !== 'object' || seen.has(value)) throw new Error('效果資料必須是有限數值與可儲存的 JSON。');
      const prototype = Object.getPrototypeOf(value);
      if (!Array.isArray(value) && prototype !== Object.prototype && prototype !== null) throw new Error('效果資料必須是一般 JSON 物件。');
      seen.add(value);
      for (const key of Object.keys(value)) {
        if (['__proto__', 'prototype', 'constructor', 'toJSON'].includes(key)) throw new Error('效果資料含有不支援的欄位：' + key + '。');
        const descriptor = Object.getOwnPropertyDescriptor(value, key);
        if (!descriptor || descriptor.get || descriptor.set) throw new Error('效果資料不能包含動態欄位。');
        visit(descriptor.value, depth + 1);
      }
      seen.delete(value);
    }
    visit(raw, 0);
  }
  function keysOnly(raw, allowed, label) {
    if (!object(raw)) throw new Error(label + '格式不正確。');
    for (const key of Object.keys(raw)) if (!allowed.includes(key)) throw new Error(label + '含有不支援的欄位「' + key + '」，請使用 .fx-library.json 效果庫。');
  }
  function nameValue(value) {
    if (typeof value !== 'string' || !value.trim() || value.trim().length > 80 || /[\u0000-\u001f\u007f]/.test(value)) throw new Error('效果名稱需為 1 到 80 個字，不能含控制字元。');
    return value.trim();
  }
  function newId(now) {
    const crypto = root.crypto;
    if (crypto && typeof crypto.randomUUID === 'function') return 'fx_' + crypto.randomUUID();
    return 'fx_' + Math.max(0, now).toString(36) + '_' + (++sequence).toString(36) + '_' + Math.random().toString(36).slice(2, 10);
  }
  function effectFrom(emitter) {
    const result = {};
    for (const key of EFFECT_KEYS) if (own(emitter, key)) result[key] = emitter[key];
    return result;
  }
  function normalizedEffect(raw) {
    keysOnly(raw, Array.from(EFFECT_KEYS), '效果參數');
    const project = Core.createProject();
    project.emitters = [Object.assign({id: 'template', name: '效果範本', x: 0, y: 0, enabled: true}, raw)];
    return effectFrom(Core.normalizeProject(project).emitters[0]);
  }
  function templateValue(raw) {
    keysOnly(raw, ['id', 'name', 'createdAt', 'emitter'], '效果範本');
    if (typeof raw.id !== 'string' || !/^fx_[a-zA-Z0-9_-]{1,120}$/.test(raw.id)) throw new Error('效果範本 ID 格式不正確。');
    if (typeof raw.createdAt !== 'number' || !Number.isSafeInteger(raw.createdAt) || raw.createdAt < 0) throw new Error('效果範本儲存時間不正確。');
    byteLength(JSON.stringify(raw), MAX_ITEM_BYTES, '單一效果（最多 16 MiB）');
    return {id: raw.id, name: nameValue(raw.name), createdAt: raw.createdAt, emitter: normalizedEffect(raw.emitter)};
  }
  function createTemplate(emitter, name, options) {
    options = options || {};
    if (!object(emitter)) throw new Error('請先選取要儲存的發射器。');
    safeValue(emitter);
    const project = Core.createProject(); project.emitters = [emitter];
    const normalized = Core.normalizeProject(project).emitters[0];
    const now = typeof options.now === 'function' ? options.now() : Date.now();
    return templateValue({id: newId(now), name: nameValue(name), createdAt: now, emitter: effectFrom(normalized)});
  }
  function normalize(raw) {
    safeValue(raw);
    keysOnly(raw, ['format', 'schemaVersion', 'templates'], '效果庫');
    if (raw.format !== FORMAT || raw.schemaVersion !== 1) throw new Error('請載入 Particle Studio 第 1 版 .fx-library.json 效果庫。');
    if (!Array.isArray(raw.templates) || raw.templates.length > MAX_ITEMS) throw new Error('效果庫最多可保存 100 組效果。');
    byteLength(JSON.stringify(raw), MAX_BYTES, '效果庫（最多 48 MiB）');
    const ids = new Set();
    const templates = raw.templates.map(item => {
      const result = templateValue(item);
      if (ids.has(result.id)) throw new Error('效果庫含有重複的範本 ID。');
      ids.add(result.id); return result;
    });
    const result = {format: FORMAT, schemaVersion: 1, templates};
    byteLength(JSON.stringify(result), MAX_BYTES, '效果庫（最多 48 MiB）');
    return result;
  }
  function parse(text) {
    byteLength(text, MAX_BYTES, '效果庫（最多 48 MiB）');
    let raw;
    try { raw = JSON.parse(text); } catch (_) { throw new Error('效果庫不是有效的 JSON，請選取 .fx-library.json 檔案。'); }
    return normalize(raw);
  }
  function serialize(raw) { return JSON.stringify(normalize(raw)); }
  function empty() { return {format: FORMAT, schemaVersion: 1, templates: []}; }
  function instantiate(template, currentEmitter) {
    safeValue(template);
    const value = templateValue(template);
    if (!object(currentEmitter)) throw new Error('請先選取要套用效果的發射器。');
    const merged = Object.assign({}, value.emitter);
    ANCHOR_KEYS.forEach(key => { merged[key] = currentEmitter[key]; });
    const project = Core.createProject(); project.emitters = [merged];
    return Core.normalizeProject(project).emitters[0];
  }
  function uniqueName(name, templates) {
    if (!templates.some(item => item.name === name)) return name;
    for (let number = 2; ; number++) {
      const suffix = ' (' + number + ')', next = name.slice(0, 80 - suffix.length) + suffix;
      if (!templates.some(item => item.name === next)) return next;
    }
  }
  function signature(item) { return JSON.stringify({name: item.name, emitter: item.emitter}); }
  function mergeLibrary(current, imported, now) {
    const result = clone(current), known = new Set(result.templates.map(signature));
    let added = 0, skipped = 0;
    for (const source of imported.templates) {
      const sameId = result.templates.find(item => item.id === source.id);
      // A collided ID may have been renamed on a previous import. Match its
      // effect payload across the collection so retrying that file is harmless.
      if (known.has(signature(source)) || sameId && result.templates.some(item => JSON.stringify(item.emitter) === JSON.stringify(source.emitter))) { skipped++; continue; }
      const item = clone(source);
      if (sameId) item.id = newId(now());
      item.name = uniqueName(item.name, result.templates);
      result.templates.push(item); known.add(signature(source)); added++;
    }
    return {library: normalize(result), added, skipped};
  }

  function createStore(options) {
    options = options || {};
    const idb = own(options, 'indexedDB') ? options.indexedDB : root.indexedDB;
    let storage;
    try { storage = own(options, 'localStorage') ? options.localStorage : root.localStorage; } catch (_) { storage = null; }
    const now = options.now || Date.now, timerSet = options.setTimeout || root.setTimeout, timerClear = options.clearTimeout || root.clearTimeout;
    const fallback = !idb || typeof idb.open !== 'function';
    let databasePromise = null, queued = Promise.resolve();
    const errorMessage = verb => '我的效果無法' + verb + '本機資料，請檢查瀏覽器儲存空間或匯出效果庫備份後重試。';
    function openDatabase() {
      if (databasePromise) return databasePromise;
      databasePromise = new Promise((resolve, reject) => {
        let request, timer, settled = false;
        const done = (error, db) => {
          if (settled) { if (db) db.close(); return; }
          settled = true; if (timer) timerClear(timer);
          if (error) reject(new Error(errorMessage('開啟')));
          else { db.onversionchange = () => { db.close(); databasePromise = null; }; resolve(db); }
        };
        try {
          request = idb.open(DATABASE_NAME, 1);
          request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains(STORE_NAME)) request.result.createObjectStore(STORE_NAME); };
          request.onerror = () => done(request.error || true);
          request.onblocked = () => done(true);
          request.onsuccess = () => done(null, request.result);
          timer = timerSet(() => done(true), 2500);
        } catch (_) { done(true); }
      }).catch(error => { databasePromise = null; throw error; });
      return databasePromise;
    }
    function fallbackOperation(transform) {
      if (!storage) throw new Error(errorMessage('讀寫'));
      let text;
      try { text = storage.getItem(FALLBACK_KEY); } catch (_) { throw new Error(errorMessage('讀取')); }
      const current = text === null ? empty() : parse(text);
      if (!transform) return current;
      const result = transform(current), next = serialize(result.library);
      try { storage.setItem(FALLBACK_KEY, next); } catch (_) { throw new Error(errorMessage('寫入')); }
      return result;
    }
    function databaseOperation(db, transform) {
      return new Promise((resolve, reject) => {
        let transaction, result, error = null;
        try {
          transaction = db.transaction(STORE_NAME, transform ? 'readwrite' : 'readonly');
          const store = transaction.objectStore(STORE_NAME), request = store.get(RECORD_KEY);
          request.onsuccess = () => {
            try {
              const current = request.result === undefined ? empty() : normalize(request.result);
              result = transform ? transform(current) : current;
              if (transform) {
                const checked = normalize(result.library);
                try { store.put(checked, RECORD_KEY); }
                catch (_) { throw new Error(errorMessage('寫入')); }
              }
            } catch (problem) { error = problem; transaction.abort(); }
          };
          request.onerror = () => { error = new Error(errorMessage('讀取')); };
          transaction.oncomplete = () => resolve(result);
          transaction.onerror = transaction.onabort = () => reject(error || new Error(errorMessage(transform ? '寫入' : '讀取')));
        } catch (problem) { if (transaction) { try { transaction.abort(); } catch (_) {} } reject(error || new Error(errorMessage(transform ? '寫入' : '讀取'))); }
      });
    }
    function operation(transform) {
      // Serialize operations in this window as well as IndexedDB's cross-window
      // read/write transaction. A failed operation never poisons the queue.
      const task = queued.then(async () => fallback ? fallbackOperation(transform) : databaseOperation(await openDatabase(), transform));
      queued = task.catch(() => {}); return task;
    }
    async function save(template) {
      safeValue(template); const detached = templateValue(template);
      return operation(current => {
        const item = clone(detached);
        if (current.templates.some(existing => existing.id === item.id)) item.id = newId(now());
        item.name = uniqueName(item.name, current.templates);
        const library = normalize({...current, templates: current.templates.concat([item])});
        return {library, template: item};
      });
    }
    async function remove(id) {
      if (typeof id !== 'string') throw new Error('請先選取要刪除的效果。');
      return operation(current => {
        const index = current.templates.findIndex(item => item.id === id);
        if (index === -1) throw new Error('這組效果已被移除，請重新選取。');
        const template = clone(current.templates[index]), templates = current.templates.filter(item => item.id !== id);
        return {library: {...current, templates}, template, index};
      });
    }
    async function restore(deleted) {
      if (!object(deleted) || !object(deleted.template)) throw new Error('沒有可復原的效果。');
      safeValue(deleted.template); const template = templateValue(deleted.template), index = Number.isInteger(deleted.index) ? deleted.index : 0;
      return operation(current => {
        const existing = current.templates.find(item => item.id === template.id);
        if (existing && signature(existing) === signature(template)) return {library: current, template: existing};
        const item = clone(template), templates = current.templates.slice();
        if (existing) item.id = newId(now());
        item.name = uniqueName(item.name, templates);
        templates.splice(Math.max(0, Math.min(index, templates.length)), 0, item);
        return {library: normalize({...current, templates}), template: item};
      });
    }
    async function importLibrary(raw) {
      const imported = typeof raw === 'string' ? parse(raw) : normalize(raw);
      return operation(current => mergeLibrary(current, imported, now));
    }
    return {backend: fallback ? 'localstorage' : 'indexeddb',
      list: async () => (await operation()).templates,
      save, remove, restore, importLibrary,
      exportLibrary: async () => serialize(await operation())};
  }

  return {FORMAT, MAX_ITEMS, MAX_BYTES, MAX_ITEM_BYTES, DATABASE_NAME, STORE_NAME, FALLBACK_KEY,
    createTemplate, normalize, parse, serialize, instantiate, createStore};
});
