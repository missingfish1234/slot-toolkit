'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'makefont.html'), 'utf8');
function section(from, until) { return html.slice(html.indexOf(from), html.indexOf(until, html.indexOf(from) + from.length)); }
const guess = vm.runInNewContext(section('function guessCharFromFileName(', 'function getDuplicateCharCodes(') + ';guessCharFromFileName');
for (const [name, char] of [['dot.png', '.'], ['comma.png', ','], ['u0078.png', 'x'], ['X.png', 'X'], ['u1f600.png', '😀'], ['NUM_X-1.png', 'X'], ['num_0.png', '0']]) assert.strictEqual(guess({name}), char);
for (const name of ['bU.png','kU.png','X2.png','X_a.png','WIN.png','Font_Win.png','ud800.png','u110000.png','u000a.png']) assert.strictEqual(guess({name}), '', name+' must not silently map to a trailing character');
for (const [name,char] of [['NUM_..png','.'],['NUM_,.png',','],['digit-8.png','8'],['A.png','A'],['a.png','a'],['-.png','-'],['space.png',' ']]) assert.strictEqual(guess({name}),char);
const importAPI = vm.runInNewContext(section('function guessCharFromFileName(', 'function getDuplicateCharCodes(') + ';({suggestImportChar,validateImportRows,isValidGlyphChar})');
assert.strictEqual(importAPI.suggestImportChar({name:'bU.png'}).char,'B');
assert.strictEqual(importAPI.suggestImportChar({name:'xU.png'}).char,'X');
assert.strictEqual(importAPI.suggestImportChar({name:'X2.png'}).char,'X');
assert.strictEqual(importAPI.suggestImportChar({name:'X_a.png'}).char,'X');
const row=char=>({char,include:true,replace:false});
assert(importAPI.validateImportRows([row('X'),row('X')],[]).every(Boolean));
assert(importAPI.validateImportRows([row('X')],[{charCode:88}])[0]);
assert.strictEqual(importAPI.validateImportRows([{...row('X'),replace:true}],[{charCode:88}])[0],'');
assert(importAPI.validateImportRows([row('WIN')],[])[0]);
assert(!importAPI.validateImportRows([row('X'),row('x'),row('😀')],[]).some(Boolean));
assert(!importAPI.validateImportRows([row('X'),{...row('X'),include:false}],[]).some(Boolean));
let scans = 0;
const context = {
    state: { glyphs: [], config: {padding:2, fontSize:72, lineHeight:80, exportScale:1, trim:true, maxWidth:512, unifiedTop:true, monospaceNum:true, cocosFixedDigitCell:true, autoSafeLineHeight:true}, glyphOffsets:{} },
    els: {mainCanvas:{}, mainCtx:{clearRect(){},drawImage(){}}, atlasSizeDisplay:{}, metricStatus:{style:{}}, importStatus:{}},
    calculateRawTrim(img) { scans++; return {x:0,y:0,w:img.w,h:img.h}; }, isDigit: code => code >=48 && code<=57
};
vm.createContext(context);
vm.runInContext(section('function packAndDraw()', 'function getMetricLineHeight('), context);
const glyph = (char,w,h=20) => ({char,charCode:char.codePointAt(0),width:w,height:h,img:{w,h}});
context.state.glyphs = [glyph('1',12),glyph('8',40)];
assert(context.packAndDraw());
assert.strictEqual(scans,2);
context.packAndDraw();
assert.strictEqual(scans,2,'repacking must reuse alpha trim');
for(const scale of [1,.67,.75]) {
    context.state.config.exportScale=scale; assert(context.packAndDraw());
    const [one,eight]=context.state.glyphs;
    assert.strictEqual(one.exW,eight.exW);
    for(const g of [one,eight]) assert.strictEqual(g.exOffX+g.exDrawW,g.exW,'fixed cell right edge');
}
context.state.glyphs[0].img={w:10,h:20};context.packAndDraw();assert.strictEqual(scans,3,'new image invalidates cached trim');
context.state.config.exportScale=1;
context.state.config.powerOfTwo=true;
context.state.glyphs=[glyph('8',4100)];
assert.strictEqual(context.packAndDraw(),false);
assert.match(context.state.packError,/4096/);
assert.strictEqual(context.els.mainCanvas.width,0,'failed pack cannot export stale atlas');
context.state.glyphs=[glyph('8',20)];context.state.config.exportScale=0;assert.strictEqual(context.packAndDraw(),false);
context.state.config.exportScale=1;context.state.glyphs[0].customX='invalid';assert.strictEqual(context.packAndDraw(),false);assert.match(context.state.packError,/偏移無效/);
for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
console.log('BMFont regression: aliases, Unicode, cached trim, fixed-cell scales, oversized/invalid input passed');
