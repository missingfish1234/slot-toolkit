'use strict';
const assert = require('assert/strict'), fs = require('fs'), path = require('path'), vm = require('vm');
const tool = path.resolve(__dirname, '..');
const standalone = fs.readFileSync(path.join(tool, 'SpinePlayTest.html'), 'utf8');
const atlas = fs.readFileSync(path.join(tool, '..', 'SPINE合圖工具', 'spine_atlas_merge.html'), 'utf8');
for (const html of [standalone, atlas]) for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) if (match[1].trim()) new vm.Script(match[1]);
let receivedAtlas;
const spineScope = { PIXI: { spine: {
    TextureAtlas: class { constructor(text, loader) { receivedAtlas=text; loader('page.png',()=>{}); } },
    AtlasAttachmentLoader: class {}, SkeletonJson: class { readSkeletonData(data) { return data; } }, Spine: class {}
}, BaseTexture: { from: x=>x }, utils: { TextureCache: {} } } };
vm.createContext(spineScope);
vm.runInContext(standalone.slice(standalone.indexOf('    function buildSpineObject('),standalone.indexOf('    async function createSpine(')),spineScope);
const assets={atlas:'page.png\nsize: 32,32', images:{'page.png':'data:image/png;base64,x'}, skeleton:{bones:[]}};
spineScope.buildSpineObject(null,null,null,false,assets);
assert.equal(receivedAtlas,assets.atlas);
assert.throws(()=>spineScope.buildSpineObject(null,null,null,false,{...assets,atlas:null}),/Atlas/);
assert.throws(()=>spineScope.buildSpineObject(null,null,null,false,{...assets,images:{}}),/page.png/);
const scope={}; vm.createContext(scope);
vm.runInContext(atlas.slice(atlas.indexOf('  function normalizePath('),atlas.indexOf('  async function addFiles(')),scope);
const compact=scope.parseAtlas('page.png\nsize: 128,128\nr\nbounds: 16,20,32,40\noffsets: 3,4,64,80\nindex: 2\ncustom: 9,8\n','compact.atlas').regions[0];
assert.equal(JSON.stringify([compact.xy,compact.size,compact.orig,compact.offset,compact.extra]),'[[16,20],[32,40],[64,80],[3,4],{"custom":"9,8"}]');
const legacy=scope.parseAtlas('page.png\nsize: 128,128\nr\nxy: 16,20\nsize: 32,40\norig: 64,80\noffset: 3,4\n','legacy.atlas').regions[0];
assert.equal(JSON.stringify(legacy.size),'[32,40]');
assert.throws(()=>scope.parseAtlas('p.png\nr\nbounds: 0,0,0,0\n','bad.atlas'),/尺寸/);
assert.throws(()=>scope.parseAtlas('p.png\nr\nsize: 2,3\nrotate: 270\n','bad.atlas'),/旋轉/);
scope.$=()=>({checked:true}); scope.cropRegionToCanvas=()=>({width:1,height:1,getContext:()=>({getImageData:()=>({data:Uint8Array.from([1,2,3,4])})})}); scope.canvasHash=()=> 'same';
vm.runInContext(atlas.slice(atlas.indexOf('  function prepareUniqueRegions('),atlas.indexOf('  function packShelfAtWidth(')),scope);
const a={...legacy,index:-1,atlasFileName:'a'}, b={...legacy,index:-1,atlasFileName:'b'};
scope.state={parsedAtlases:[{regions:[a]},{regions:[b]}]}; assert.equal(scope.prepareUniqueRegions().unique.length,1);
b.offset=[99,4]; assert.throws(()=>scope.prepareUniqueRegions(),/資料不同/);
b.index=2; assert.equal(scope.prepareUniqueRegions().unique.length,2);
console.log('Spine assets: JS syntax, atlas restoration/missing input, compact/legacy parsing, invalid bounds/rotation, complete-metadata dedup: PASS');
