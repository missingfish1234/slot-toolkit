'use strict';
const path = require('node:path');
const ts = require(process.env.COCOS_TYPESCRIPT || 'C:/ProgramData/cocos/editors/Creator/3.8.6/resources/app.asar.unpacked/node_modules/typescript');
const root = path.resolve(__dirname, '../..');
const engine = process.env.COCOS_ENGINE_ROOT || 'C:/ProgramData/cocos/editors/Creator/3.8.6/resources/resources/3d/engine';
const files = [
    'Sharder/COCOS/一般圖片掃光/SweepLightController.ts',
    'Sharder/COCOS/漸層遮罩/SoftMaskDirectMaterialDriver.ts',
    'SPINE相關工具/SPINE串接示意工具/CocosCreator38Extension/spine-director-cocos38/static/runtime/CocosTimelinePlayer.ts',
    'SPINE相關工具/SPINE串接示意工具/CocosCreator38Extension/spine-director-cocos38/static/runtime/SpineDirectorPlayer.ts',
].map(file => path.join(root, file));
files.push(path.join(engine, 'bin/.declarations/cc.d.ts'), path.join(__dirname, 'cc-env.d.ts'));
const program = ts.createProgram(files, {noEmit:true, skipLibCheck:true, experimentalDecorators:true, target:ts.ScriptTarget.ES2020, module:ts.ModuleKind.ESNext, moduleResolution:ts.ModuleResolutionKind.NodeJs, types:[]});
const diagnostics = ts.getPreEmitDiagnostics(program);
if (diagnostics.length) console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics, {getCanonicalFileName:x=>x, getCurrentDirectory:()=>__dirname, getNewLine:()=> '\n'}));
console.log(`Installed Cocos declarations: ${diagnostics.length} diagnostics; TypeScript ${ts.version}`);
process.exitCode = diagnostics.length ? 1 : 0;
