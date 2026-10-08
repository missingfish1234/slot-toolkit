(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleSpineAssetsUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function selectedPath(file, directory) {
    const relative = directory ? file.webkitRelativePath : file.name;
    if (typeof relative !== 'string' || !relative || relative.includes('\\') || relative.startsWith('/') || /[:\u0000-\u001f]/.test(relative)) throw new Error('素材檔案的相對路徑無效。');
    const parts = relative.split('/');
    if (parts.some(part => !part || part === '.' || part === '..')) throw new Error('素材檔案不可使用空目錄、. 或 .. 路徑。');
    if (directory) {
      if (parts.length < 2) throw new Error('資料夾素材缺少相對路徑，請重新選擇原 Images 資料夾。');
      // The browser includes exactly one selected-folder name at the front.
      // Keep all nested directories below it, since Spine attachment paths use them.
      parts.shift();
    }
    return parts.join('/');
  }
  function mount({Merge, getSession, setSession, onChange, notify, imageLoader, document: doc = document}) {
    const $ = id => doc.getElementById(id);
    const ui = Object.fromEntries(['spineAssetsFields', 'spineLoadImages', 'spineImagesFile', 'spineLoadImagesFolder', 'spineImagesFolder',
      'spineLoadAtlas', 'spineAtlasFile', 'spineClearAssets', 'spineAssetsInfo', 'spineAssetsPreviewInfo'].map(id => [id, $(id)]));
    let busy = false, status = null, statusSource = null;
    function refresh() {
      const session = getSession(), assets = session && session.assets;
      ui.spineAssetsFields.hidden = !session;
      for (const key of ['spineLoadImages', 'spineLoadImagesFolder', 'spineLoadAtlas']) ui[key].disabled = !session || busy;
      ui.spineClearAssets.disabled = !session || !assets || busy;
      if (statusSource !== (session && session.json)) { statusSource = session && session.json; status = null; }
      if (!session) { ui.spineAssetsInfo.textContent = '請先載入原骨架 JSON。'; ui.spineAssetsPreviewInfo.textContent = ''; return; }
      const images = assets ? assets.images : [], atlas = assets && assets.atlas;
      ui.spineAssetsInfo.textContent = images.length ? '已載入 ' + images.length + ' 張原骨架圖片' + (atlas ? ' · 圖集 ' + atlas.name : ' · 使用原始圖片') :
        atlas ? '已載入圖集 ' + atlas.name + '；請再選擇圖集 PNG 頁面。' : '尚未載入角色圖片；預覽會顯示骨架與粒子。';
      ui.spineAssetsPreviewInfo.textContent = status && status.message ? status.message :
        '圖片與 Atlas 只供本機預覽，會隨粒子專案保存；輸出追加包保留原素材目錄，不重複打包角色素材。';
    }
    function setPreviewInfo(info) {
      statusSource = getSession() && getSession().json;
      status = typeof info === 'string' ? {message: info} : info;
      refresh();
    }
    function currentSource(base) {
      const current = getSession();
      if (!current || current.json !== base.json) throw new Error('載入素材期間原骨架已更換；請為目前骨架重新選擇素材。');
      return current;
    }
    function commit(base, assets, message) {
      const current = currentSource(base), next = {...current, assets: Merge.normalizeAssets(assets)};
      setSession(next); status = null; onChange(); refresh(); notify(message);
    }
    async function loadImages(event, directory) {
      const files = Array.from(event.target.files || []); if (!files.length || busy) return;
      const base = getSession(); if (!base) { notify('請先載入原骨架 JSON。', true); return; }
      busy = true; refresh();
      try {
        if (typeof imageLoader !== 'function') throw new Error('圖片載入器尚未初始化，請重新開啟工具。');
        const prior = base.assets || {images: []}, paths = new Set(prior.images.map(image => image.path)), selected = [];
        let total = 0, ignored = 0;
        for (const file of files) {
          if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
            if (directory) { ignored++; continue; }
            throw new Error('請選擇 PNG、JPEG 或 WebP 圖片。');
          }
          if (!Number.isFinite(file.size) || file.size < 0 || file.size > 4 * 1024 * 1024) throw new Error('圖片「' + file.name + '」超過 4 MiB，請先縮小素材。');
          total += file.size;
          if (total > 16 * 1024 * 1024) throw new Error('這批圖片超過 16 MiB，請縮小素材或分批載入。');
          const path = selectedPath(file, directory);
          if (paths.has(path)) throw new Error('圖片路徑重複：「' + path + '」。請清除舊素材後重新載入，或選擇正確的 Images 資料夾。');
          paths.add(path); selected.push({file, path});
        }
        if (!selected.length) throw new Error('這個資料夾沒有可載入的 PNG、JPEG 或 WebP 圖片。');
        const images = prior.images.slice();
        for (const {file, path} of selected) {
          const image = await imageLoader(file); currentSource(base);
          images.push({...image, path});
        }
        commit(base, {...prior, images}, '已載入 ' + selected.length + ' 張原骨架圖片' + (ignored ? '，略過 ' + ignored + ' 個非圖片檔案。' : '。'));
      } catch (error) { notify(error.message, true); }
      finally { busy = false; event.target.value = ''; refresh(); }
    }
    async function loadAtlas(event) {
      const file = event.target.files && event.target.files[0]; if (!file || busy) return;
      const base = getSession(); if (!base) { notify('請先載入原骨架 JSON。', true); return; }
      busy = true; refresh();
      try {
        if (!/\.atlas$/i.test(file.name)) throw new Error('請選擇 Spine 的 .atlas 純文字圖集。');
        if (!Number.isFinite(file.size) || file.size > 256 * 1024) throw new Error('Atlas 超過 256 KiB，請縮小圖集資料。');
        const text = await file.text();
        commit(base, {...(base.assets || {images: []}), atlas: {name: file.name, text}}, '已載入圖集「' + file.name + '」；請確認圖集 PNG 頁面也已載入。');
      } catch (error) { notify(error.message, true); }
      finally { busy = false; event.target.value = ''; refresh(); }
    }
    ui.spineLoadImages.addEventListener('click', () => ui.spineImagesFile.click());
    ui.spineLoadImagesFolder.addEventListener('click', () => ui.spineImagesFolder.click());
    ui.spineLoadAtlas.addEventListener('click', () => ui.spineAtlasFile.click());
    ui.spineImagesFile.addEventListener('change', event => loadImages(event, false));
    ui.spineImagesFolder.addEventListener('change', event => loadImages(event, true));
    ui.spineAtlasFile.addEventListener('change', loadAtlas);
    ui.spineClearAssets.addEventListener('click', () => {
      const current = getSession(); if (!current || busy) return;
      const next = {...current}; delete next.assets; setSession(next); status = null; onChange(); refresh(); notify('已清除原骨架預覽素材；可重新載入圖片與圖集。');
    });
    refresh(); return {refresh, setPreviewInfo};
  }
  return {mount, selectedPath};
});
