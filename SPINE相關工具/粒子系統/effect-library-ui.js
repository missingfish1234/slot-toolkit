(function (root, factory) {
  'use strict';
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleEffectLibraryUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  const shapes = {point: '點', direction: '方向', line: '線', circle: '圓', ring: '環', box: '矩形', outline: '物件輪廓'};
  function mount(options) {
    options = options || {};
    const doc = options.document || root.document, Library = options.Library || root.ParticleEffectLibrary;
    if (!doc || !Library || typeof options.getEmitter !== 'function' || typeof options.onApply !== 'function') throw new Error('我的效果工具尚未完整載入。');
    const win = doc.defaultView || root, getEmitter = options.getEmitter, getGeneration = options.getGeneration || getEmitter;
    const dialog = doc.getElementById('effectLibraryDialog'), opener = doc.getElementById('effectLibraryButton');
    if (!dialog || !opener) throw new Error('缺少我的效果畫面。');
    const store = options.store || Library.createStore();
    dialog.setAttribute('aria-labelledby', 'effectLibraryTitle');
    const builtins = Array.isArray(options.builtins) ? options.builtins : [];
    dialog.innerHTML = '<div class="dialog-heading"><div><span class="eyebrow">EFFECTS</span><h2 id="effectLibraryTitle">效果庫</h2></div>' +
      '<button id="effectLibraryClose" type="button" class="icon-button" aria-label="關閉效果庫">×</button></div>' +
      '<div class="effect-library-body"><p class="hint">選一個效果，按「新增為新圖層」或直接雙擊；「套用至目前發射器」會保留目前的名稱、位置與掛接。</p>' +
      (builtins.length ? '<div class="effect-library-group-title">內建效果</div><div id="effectLibraryBuiltins" class="effect-library-list effect-library-builtins" role="group" aria-label="內建效果"></div>' : '') +
      '<div class="effect-library-group-title">我的效果</div>' +
      '<div class="effect-library-save"><label for="effectLibraryName">效果名稱</label><div class="effect-library-save-row"><input id="effectLibraryName" maxlength="80" placeholder="例如：金色環繞光" autocomplete="off">' +
      '<button id="effectLibrarySave" type="button">儲存目前發射器</button></div><p id="effectLibraryTarget" class="hint"></p></div>' +
      '<div class="effect-library-tools"><strong id="effectLibraryCount">已儲存 0 組</strong><div>' +
      '<button id="effectLibraryImport" type="button" class="subtle">匯入效果庫</button> <button id="effectLibraryExport" type="button" class="subtle">匯出效果庫</button>' +
      '<input id="effectLibraryFile" type="file" accept=".json,application/json" hidden></div></div>' +
      '<div id="effectLibraryList" class="effect-library-list" role="group" aria-label="已儲存效果"></div>' +
      '<div id="effectLibrarySelected" class="effect-library-selection" hidden><strong id="effectLibrarySelectedName"></strong><p id="effectLibrarySelectedInfo" class="hint"></p></div>' +
      '<p id="effectLibraryStatus" class="hint" role="status" aria-live="polite"></p></div>' +
      '<div class="dialog-footer effect-library-footer"><div><button id="effectLibraryDelete" type="button" class="subtle">刪除選取效果</button> ' +
      '<button id="effectLibraryRestore" type="button" class="subtle" hidden>復原刪除</button></div><div class="effect-library-actions"><button id="effectLibraryApply" type="button" class="quiet-button">套用至目前發射器</button>' +
      '<button id="effectLibraryAdd" type="button" class="primary-button">新增為新圖層</button></div></div>';
    const ui = Object.fromEntries(['effectLibraryName', 'effectLibrarySave', 'effectLibraryTarget', 'effectLibraryCount', 'effectLibraryList',
      'effectLibraryApply', 'effectLibraryDelete', 'effectLibraryRestore', 'effectLibraryImport', 'effectLibraryFile', 'effectLibraryExport',
      'effectLibraryClose', 'effectLibraryStatus', 'effectLibrarySelected', 'effectLibrarySelectedName', 'effectLibrarySelectedInfo', 'effectLibraryAdd', 'effectLibraryBuiltins'].map(id => [id, doc.getElementById(id)]));
    let templates = [], selectedId = null, deleted = null, busy = false, loaded = false, priorEmitter = null, fileToken = 0;
    const selected = () => templates.find(item => item.id === selectedId) || null;
    const builtinChoice = () => builtins.find(item => 'builtin:' + item.id === selectedId) || null;
    const addBlocked = () => typeof options.addBlockedReason === 'function' ? options.addBlockedReason() : '';
    function markSelection() {
      dialog.querySelectorAll('[data-template-id]').forEach(node => node.setAttribute('aria-pressed', String(node.dataset.templateId === selectedId)));
    }
    function addSelected() {
      if (busy) return;
      const template = selected(), builtin = builtinChoice(), reason = addBlocked();
      if (!template && !builtin) return;
      if (reason) { status(reason, true); return; }
      try {
        if (typeof options.onAdd !== 'function') throw new Error('目前無法新增圖層。');
        options.onAdd(builtin ? {builtin: builtin.id} : {template});
        refresh(); status('已新增「' + (builtin ? builtin.name : template.name) + '」為新圖層。可繼續新增，或關閉視窗調整。');
      } catch (error) { status(error.message, true); }
    }
    function renderBuiltins() {
      if (!ui.effectLibraryBuiltins) return;
      ui.effectLibraryBuiltins.replaceChildren();
      builtins.forEach(item => {
        const button = doc.createElement('button'); button.type = 'button'; button.className = 'effect-library-item';
        button.dataset.templateId = 'builtin:' + item.id; button.setAttribute('aria-pressed', String(selectedId === 'builtin:' + item.id));
        const art = doc.createElement('span'); art.className = 'effect-library-thumb';
        if (item.gradient) art.style.background = item.gradient;
        if (item.image) { const bitmap = doc.createElement('img'); bitmap.src = item.image; bitmap.alt = ''; art.append(bitmap); }
        else { const symbol = doc.createElement('span'); symbol.textContent = item.symbol || '✦'; art.append(symbol); }
        const info = doc.createElement('span'); info.className = 'effect-library-item-info';
        const name = doc.createElement('strong'), description = doc.createElement('span');
        name.textContent = item.name; description.textContent = item.description || '';
        info.append(name, description); button.append(art, info);
        button.addEventListener('click', () => { if (busy) return; selectedId = 'builtin:' + item.id; markSelection(); status('已選取內建「' + item.name + '」。雙擊或按「新增為新圖層」加入。'); controls(); });
        button.addEventListener('dblclick', () => { selectedId = 'builtin:' + item.id; markSelection(); addSelected(); });
        ui.effectLibraryBuiltins.append(button);
      });
    }
    function status(message, error) {
      ui.effectLibraryStatus.textContent = message;
      ui.effectLibraryStatus.classList.toggle('is-error', !!error);
      if (error && typeof options.notify === 'function') options.notify(message);
    }
    function controls() {
      const current = getEmitter(), choice = selected(), builtin = builtinChoice();
      ui.effectLibrarySave.disabled = busy || !loaded || !current;
      ui.effectLibraryApply.disabled = busy || !loaded || !current || !(choice || builtin);
      ui.effectLibraryAdd.disabled = busy || !loaded || !(choice || builtin) || !!addBlocked();
      ui.effectLibraryAdd.title = addBlocked() || '把選取的效果加成新的發射器圖層（雙擊卡片也可以）';
      ui.effectLibraryDelete.disabled = busy || !loaded || !choice;
      ui.effectLibraryImport.disabled = busy || !loaded;
      ui.effectLibraryExport.disabled = busy || !loaded || !templates.length;
      ui.effectLibraryRestore.hidden = !deleted;
      ui.effectLibraryRestore.disabled = busy || !loaded || !deleted;
      ui.effectLibraryName.disabled = busy || !current;
      ui.effectLibrarySelected.hidden = !choice && !builtin;
      if (builtin && !choice) { ui.effectLibrarySelectedName.textContent = builtin.name; ui.effectLibrarySelectedInfo.textContent = (builtin.description || '') + '。新增後可自由調整。'; }
      if (choice) {
        ui.effectLibrarySelectedName.textContent = choice.name;
        const e = choice.emitter;
        ui.effectLibrarySelectedInfo.textContent = (shapes[e.shape] || e.shape) + ' · ' + e.count + ' 顆 · 壽命 ' + e.life + ' 秒' +
          (e.path && e.path.enabled ? ' · 路徑移動' : '') + (e.sequence && e.sequence.enabled ? (e.sequence.mode === 'random' ? ' · ' + e.sequence.frames.length + ' 張隨機圖' : ' · ' + e.sequence.frames.length + ' 張連續圖 · ' + e.sequence.fps + ' FPS') : e.image ? ' · 自訂 PNG' : '') +
          (e.randomSeed !== undefined ? ' · 種子 ' + e.randomSeed : '') + '。套用後仍可編輯。';
      }
      ui.effectLibraryCount.textContent = '已儲存 ' + templates.length + ' / ' + Library.MAX_ITEMS + ' 組';
    }
    function renderList() {
      ui.effectLibraryList.replaceChildren();
      if (!templates.length) {
        const message = doc.createElement('p'); message.className = 'effect-library-empty';
        message.textContent = '還沒有儲存效果。把目前調好的發射器存下來，下次就能直接使用。';
        ui.effectLibraryList.append(message);
      }
      templates.forEach(template => {
        const button = doc.createElement('button'); button.type = 'button'; button.className = 'effect-library-item';
        button.dataset.templateId = template.id; button.setAttribute('aria-pressed', String(template.id === selectedId));
        const e = template.emitter, art = doc.createElement('span'); art.className = 'effect-library-thumb';
        const points = e.colorGradient || [{t: 0, color: e.colorStart}, {t: 1, color: e.colorEnd}];
        art.style.background = 'linear-gradient(135deg,' + points.map(p => p.color + ' ' + p.t * 100 + '%').join(',') + ')';
        const image = e.sequence && e.sequence.enabled ? e.sequence.frames[0] : e.image || e.outline && e.outline.image;
        if (image) {
          const bitmap = doc.createElement('img'); bitmap.src = image.dataUrl; bitmap.alt = ''; bitmap.loading = 'lazy'; art.append(bitmap);
        } else { const symbol = doc.createElement('span'); symbol.textContent = {point: '✦', direction: '↗', line: '━', circle: '●', ring: '◯', box: '▧', outline: '⬡'}[e.shape] || '✦'; art.append(symbol); }
        const info = doc.createElement('span'); info.className = 'effect-library-item-info';
        const name = doc.createElement('strong'), description = doc.createElement('span'); name.textContent = template.name;
        description.textContent = (shapes[e.shape] || e.shape) + ' · ' + e.count + ' 顆' + (e.path && e.path.enabled ? ' · 路徑' : '') + (e.sequence && e.sequence.enabled ? (e.sequence.mode === 'random' ? ' · 隨機圖 ' + e.sequence.frames.length + ' 張' : ' · 連續圖 ' + e.sequence.fps + ' FPS') : '');
        info.append(name, description); button.append(art, info);
        button.addEventListener('click', () => {
          if (busy) return;
          selectedId = template.id; markSelection();
          status('已選取「' + template.name + '」。雙擊或按「新增為新圖層」加入，或套用至目前發射器。'); controls();
        });
        button.addEventListener('dblclick', () => { selectedId = template.id; markSelection(); addSelected(); });
        ui.effectLibraryList.append(button);
      });
      controls();
    }
    function refresh() {
      const emitter = getEmitter();
      if (emitter !== priorEmitter) { priorEmitter = emitter; ui.effectLibraryName.value = emitter ? emitter.name : ''; }
      ui.effectLibraryTarget.textContent = emitter ? '目前：' + emitter.name + '。套用保留名稱、位置與掛接骨頭；其他發射器與動畫設定維持原值。' : '請先選取發射器。';
      controls();
    }
    async function run(task, success) {
      if (busy) return null;
      busy = true; controls();
      try { const result = await task(); if (success) success(result); return result; }
      catch (error) { status(error.message || '效果庫操作失敗，請重試。', true); return null; }
      finally { busy = false; refresh(); }
    }
    async function open() {
      refresh();
      if (!dialog.open) dialog.showModal();
      return run(() => store.list(), result => {
        templates = result; loaded = true;
        if (!selected() && !builtinChoice()) selectedId = builtins.length ? 'builtin:' + builtins[0].id : null;
        renderBuiltins(); renderList();
        status(store.backend === 'localstorage' ? '效果庫已載入。目前使用瀏覽器備用儲存，建議定期匯出備份。' : '先選取效果，再按套用。效果庫與目前專案分開保存。');
      });
    }
    function close() { fileToken++; if (dialog.open) dialog.close(); }
    opener.addEventListener('click', () => { open(); });
    ui.effectLibraryClose.addEventListener('click', close);
    dialog.addEventListener('cancel', () => { fileToken++; });
    ui.effectLibrarySave.addEventListener('click', () => {
      if (busy || ui.effectLibrarySave.disabled) return;
      let template;
      try { template = Library.createTemplate(getEmitter(), ui.effectLibraryName.value); }
      catch (error) { status(error.message, true); return; }
      run(() => store.save(template), result => {
        templates = result.library.templates; selectedId = result.template.id; renderList();
        status('已儲存「' + result.template.name + '」。重新開啟工具後仍可使用。');
      });
    });
    ui.effectLibraryApply.addEventListener('click', () => {
      if (busy || ui.effectLibraryApply.disabled) return;
      const template = selected(), builtin = builtinChoice(), emitter = getEmitter(), generation = getGeneration();
      try {
        if (!(template || builtin) || !emitter || emitter !== getEmitter() || generation !== getGeneration()) throw new Error('目前發射器已改變，請重新選取後套用。');
        if (builtin) { if (typeof options.onApplyBuiltin !== 'function') throw new Error('目前無法套用內建效果。'); options.onApplyBuiltin(builtin.id); }
        else options.onApply(template);
        refresh(); status('已套用「' + (builtin ? builtin.name : template.name) + '」。可繼續調整，或使用復原回到套用前。');
      } catch (error) { status(error.message, true); }
    });
    ui.effectLibraryAdd.addEventListener('click', addSelected);
    ui.effectLibraryDelete.addEventListener('click', () => {
      const template = selected(); if (!template || busy || ui.effectLibraryDelete.disabled) return;
      run(() => store.remove(template.id), result => {
        deleted = {template: result.template, index: result.index}; templates = result.library.templates; selectedId = null; renderList();
        status('已刪除「' + result.template.name + '」。可按「復原刪除」取回；目前專案不受影響。');
      });
    });
    ui.effectLibraryRestore.addEventListener('click', () => {
      if (!deleted || busy) return;
      run(() => store.restore(deleted), result => {
        templates = result.library.templates; selectedId = result.template.id; deleted = null; renderList(); status('已復原「' + result.template.name + '」。');
      });
    });
    ui.effectLibraryImport.addEventListener('click', () => { if (!busy) ui.effectLibraryFile.click(); });
    ui.effectLibraryFile.addEventListener('change', () => {
      const file = ui.effectLibraryFile.files && ui.effectLibraryFile.files[0]; ui.effectLibraryFile.value = '';
      if (!file || busy) return;
      const token = ++fileToken, generation = getGeneration();
      run(async () => {
        if (file.size > Library.MAX_BYTES) throw new Error('效果庫超過 48 MiB，請縮小素材後重試。');
        const text = await file.text();
        if (token !== fileToken || generation !== getGeneration() || !dialog.open) return null;
        return store.importLibrary(text);
      }, result => {
        if (!result || token !== fileToken || generation !== getGeneration()) return;
        templates = result.library.templates; if (!selected() && !builtinChoice()) selectedId = null; renderList();
        status('已匯入 ' + result.added + ' 組效果' + (result.skipped ? '，略過 ' + result.skipped + ' 組重複內容' : '') + '。尚未套用至目前發射器。');
      });
    });
    ui.effectLibraryExport.addEventListener('click', () => {
      if (busy || ui.effectLibraryExport.disabled) return;
      run(() => store.exportLibrary(), text => {
        const url = win.URL.createObjectURL(new win.Blob([text], {type: 'application/json;charset=utf-8'}));
        const link = doc.createElement('a'); link.href = url; link.download = '我的效果.fx-library.json'; doc.body.append(link); link.click(); link.remove();
        win.setTimeout(() => win.URL.revokeObjectURL(url), 1000); status('效果庫已匯出，可備份或匯入另一台電腦。');
      });
    });
    refresh(); return {refresh, open, close};
  }
  return {mount};
});
