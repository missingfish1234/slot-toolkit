'use strict';
const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../makefont.html'),'utf8');
const code=html.slice(html.indexOf('function packAndDraw()'),html.indexOf('function renderPreview()'));
const config={padding:2,maxWidth:1024,powerOfTwo:true,fontSize:72,lineHeight:80,exportScale:1,trim:true,keepYBounds:true,unifiedTop:true,groupCenter:true,cocosBaselineFix:true,cocosKeepLineHeight:true,lockInfoSize:true,autoSafeLineHeight:true,monospaceNum:true,cocosFixedDigitCell:true,yOffsetAdjust:0};
const c={state:{config:{...config},glyphs:[]},els:{mainCanvas:{},mainCtx:{clearRect(){},drawImage(){}},atlasSizeDisplay:{},metricStatus:{style:{}},importStatus:{}},calculateRawTrim:img=>img.bounds,isDigit:code=>code>=48&&code<=57};
vm.createContext(c);vm.runInContext(code,c);
const fixture=()=>Array.from('0123456789.,').map((char,i)=>({char,charCode:char.codePointAt(0),width:172,height:374,img:{bounds:{x:0,y:i>=10?225:84+i%5,w:90+i,h:i>=10?79:220-i%3}}}));
function ink(g){const ratio=g.exDrawH/g.computedTrim.h;const top=c.getExportYOffset(g,c.getMetricLineHeight(c.state.config.exportScale),c.state.config.exportScale)+(g.rawTrim.y-g.computedTrim.y)*ratio;return {top,bottom:top+g.rawTrim.h*ratio};}
let cases=0;
for(const scale of [1,.67,.75,2])for(const trim of [false,true])for(const keepYBounds of [false,true])for(const unifiedTop of [false,true])for(const lockInfoSize of [false,true])for(const cocosKeepLineHeight of [false,true]){
 Object.assign(c.state.config,config,{exportScale:scale,trim,keepYBounds,unifiedTop,lockInfoSize,cocosKeepLineHeight});c.state.glyphs=fixture();assert(c.packAndDraw(),c.state.packError+JSON.stringify(c.state.config));
 const digits=c.state.glyphs.slice(0,10).map(ink);const center=(Math.min(...digits.map(g=>g.top))+Math.max(...digits.map(g=>g.bottom)))/2;
 assert(Math.abs(center-c.getExportFontSize(scale)/2)<=.51,JSON.stringify(c.state.config));
 assert(ink(c.state.glyphs[10]).top>digits[0].top,'Punctuation keeps its lower baseline');
 const geometry=JSON.stringify(c.state.glyphs.map(g=>[g.rect,g.exW,g.exOffX,g.exDrawW,g.exDrawH]));
 const g=c.state.glyphs[1],base=c.getExportYOffset(g,80,scale);g.customY=7;c.state.config.yOffsetAdjust=-3;assert(Math.abs(c.getExportYOffset(g,80,scale)-base-4*scale)<=1);
 c.state.config.cocosBaselineFix=false;assert(c.packAndDraw());assert.strictEqual(JSON.stringify(c.state.glyphs.map(g=>[g.rect,g.exW,g.exOffX,g.exDrawW,g.exDrawH])),geometry,'No glyph/atlas geometry or horizontal changes');
 assert.strictEqual(c.getExportYOffset(g,80,scale),g.exOffY,'Non-Cocos output remains legacy');
 c.state.config.cocosBaselineFix=true;c.state.config.groupCenter=false;assert(c.packAndDraw());assert.strictEqual(c.getExportYOffset(g,80,scale),g.exOffY,'Explicitly disabled group centering is respected');cases++;
}
// Reproduce the 374px transparent-cell regression, including at scale 1.
c.state.config={...config};c.state.glyphs=fixture();assert(c.packAndDraw());
assert(c.getExportYOffset(c.state.glyphs[1],374,1)<-150,'Negative compensation is required, never clamp to zero');
// Fonts without digits use letters; punctuation-only and empty art stay finite.
for(const chars of ['AB','.,','']){c.state.glyphs=fixture().slice(0,chars.length).map((g,i)=>({...g,char:chars[i],charCode:chars.codePointAt(i)}));assert.notStrictEqual(c.packAndDraw(),false);if(chars)assert(Number.isFinite(c.state.cocosInkCenter));}
console.log(`Vertical centering passed: ${cases} combinations; transparent bounds, scale 1/.67/.75/2, lock size, trim/keep-Y, punctuation, manual offsets and unchanged geometry`);
