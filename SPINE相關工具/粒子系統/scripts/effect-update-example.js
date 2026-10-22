'use strict';
// A self-contained editable demonstration: its canonical Spine source still
// includes the prior FX, while replace preview uses the verified clean base.
const fs = require('node:fs');
const path = require('node:path');
const Core = require('../core.js');
const Merge = require('../spine-merge.js');
const Update = require('../effect-update.js');
const Storage = require('../storage.js');
const root = path.resolve(__dirname, '..');
function main() {
  const source = JSON.parse(fs.readFileSync(path.join(root, 'tests/attachment-preview-fixtures/4.0.56/flow/project.particle.json'), 'utf8'));
  const parsed = Storage.parse(JSON.stringify(source), Core), session = parsed.integration;
  const texture = session.assets.images[0];
  parsed.project.emitters.forEach(emitter => { emitter.image = {name: 'particle.png', mime: 'image/png', width: texture.width, height: texture.height, dataUrl: texture.dataUrl}; });
  const baked = Core.bakeFlow(parsed.project), exported = Core.exportFlow(baked, session.json.skeleton.spine);
  const result = Merge.mergeFlow(session.json, exported, session.settings);
  const receipt = Update.createReceipt(session.json, result, session.settings);
  const project = Core.normalizeProject({...parsed.project, name: '更新既有粒子示範', bakeQuality: 'compact'});
  const settings = {...session.settings, prefix: receipt.manifest.namespace};
  const assets = Merge.normalizeAssets({...session.assets, images: [...session.assets.images, ...result.images.map(image => ({...image, path: image.name, mime: 'image/png'}))]});
  const integration = {...session, assets, fileName: 'spine-with-particles.json', json: result.json, settings, update: {mode: 'replace', receipt}};
  const folder = path.join(root, 'examples/effect-update'); fs.mkdirSync(folder, {recursive: true});
  fs.writeFileSync(path.join(folder, 'spine-with-particles.json'), JSON.stringify(result.json, null, 2));
  fs.writeFileSync(path.join(folder, '效果更新記錄.json'), JSON.stringify(receipt, null, 2));
  fs.writeFileSync(path.join(folder, 'effect-update.particle.json'), Storage.serialize(project, null, {mode: 'live', time: .4, phase: 'loop', zoom: .8, previewAttached: true, showBones: true}, integration));
  fs.writeFileSync(path.join(folder, '更新示範說明.txt'), '效果更新示範 · Spine 4.0.56\n\n1. 開啟 effect-update.particle.json，已包含原骨架、角色參考圖與更新記錄。\n2. 掛接設定 → 更新已追加的粒子效果，切換追加新效果 / 更新此效果比較預覽。\n3. 調整粒子參數；烘焙檢查切換精細、標準、精簡，試烘焙後比較實際 KEY 與 JSON 大小。\n4. 使用更新此效果輸出，不會累積第二組粒子。\n\nspine-with-particles.json 是包含原粒子的來源；對應的效果更新記錄.json 可再載入練習更新流程。請保留自己的原 Spine 工程，輸出另存新版本。\n', 'utf8');
}
if (require.main === module) main();
module.exports = {main};
