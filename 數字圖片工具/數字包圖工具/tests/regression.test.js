'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'makefont.html'), 'utf8');
function section(from, until) { return html.slice(html.indexOf(from), html.indexOf(until, html.indexOf(from) + from.length)); }
const guess = vm.runInNewContext(section('function guessCharFromFileName(', 'function getDuplicateCharCodes(') + ';guessCharFromFileName');
for (const [name, char] of [['dot.png', '.'], ['comma.png', ','], ['u0078.png', 'x'], ['X.png', 'X'], ['u1f600.png', '😀'], ['NUM_X-1.png', 'X'], ['num_0.png', '0']]) assert.strictEqual(guess({name}), char);
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
