'use strict';
const fs = require('node:fs');
const path = require('node:path');
const Core = require('../core.js');
const Storage = require('../storage.js');
const Library = require('../effect-library.js');
const root = path.resolve(__dirname, '..');
function main() {
  const presets = Storage.parse(fs.readFileSync(path.join(root, 'examples/lifetime-presets.particle.json'), 'utf8'), Core).project.emitters;
  const pathProject = Storage.parse(fs.readFileSync(path.join(root, 'examples/motion-path.particle.json'), 'utf8'), Core).project;
  const outlineProject = Storage.parse(fs.readFileSync(path.join(root, 'examples/outline-motion.particle.json'), 'utf8'), Core).project;
  const choices = [...presets.map(e => [e, e.name]), [pathProject.emitters.find(e => e.path && e.path.enabled), '流動邊框 · 路徑移動'],
    [outlineProject.emitters.find(e => e.path && e.path.enabled), '沿物件外型環繞']];
  const templates = choices.map(([emitter, name], index) => {
    if (!emitter) throw new Error('效果庫範例缺少路徑發射器。');
    const template = Library.createTemplate(emitter, name, {now: () => 0}); template.id = 'fx_example_' + (index + 1); return template;
  });
  const payload = {format: Library.FORMAT, schemaVersion: 1, templates};
  const text = Library.serialize(payload); Library.parse(text);
  fs.writeFileSync(path.join(root, 'examples/常用效果.fx-library.json'), text);
  fs.writeFileSync(path.join(root, 'examples/我的效果庫使用說明.txt'), '我的效果庫示範\n\n1. 按左側「我的效果庫」→「匯入效果庫」，選取常用效果.fx-library.json。\n2. 選一組效果後，按「套用至目前發射器」。配色、曲線、PNG、路徑與輪廓都可繼續編輯。\n3. 套用保留目前發射器的名稱、位置、啟用狀態與掛接骨骼；也可一步復原。\n4. 把自己調好的發射器命名後儲存，下次可直接使用。\n\n效果庫獨立保存在目前瀏覽器；粒子專案保存目前使用的效果參數，效果庫請另外匯出備份。更換資料夾、瀏覽器、電腦或版本前，先匯出效果庫，再於新環境匯入。\n', 'utf8');
  process.stdout.write('Built personal effects library with ' + templates.length + ' editable templates\n');
}
if (require.main === module) main();
module.exports = {main};
