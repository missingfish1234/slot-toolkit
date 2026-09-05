'use strict';
// Executes the installed Creator's original TextProcessing / FontAtlas source.
// Canvas pool and numeric value objects are host stubs; no editor Scene/GPU is claimed.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
module.exports=function checkEngineFont(fnt,creatorRoot){
 const ts=require(path.join(creatorRoot,'resources/app.asar.unpacked/node_modules/typescript'));
 const engine=path.join(creatorRoot,'resources/resources/3d/engine');
 class Vec2{constructor(x=0,y=0){this.x=x;this.y=y}clone(){return new Vec2(this.x,this.y)}set(x=0,y=0){this.x=x;this.y=y;return this}}Vec2.ZERO=new Vec2();
 class Size{constructor(width=0,height=0){this.width=width;this.height=height}clone(){return new Size(this.width,this.height)}set(w=0,h=0){this.width=w;this.height=h;return this}}Size.ZERO=new Size();
 class Rect{constructor(x=0,y=0,width=0,height=0){Object.assign(this,{x,y,width,height})}set(x=0,y=0,w=0,h=0){Object.assign(this,{x,y,width:w,height:h})}}
 class Color{constructor(r=255,g=255,b=255,a=255){Object.assign(this,{r,g,b,a})}clone(){return new Color(this.r,this.g,this.b,this.a)}set(other){if(other)Object.assign(this,other)}}Color.WHITE=new Color();Color.BLACK=new Color(0,0,0);
 const core={Vec2,Size,Rect,Color,cclegacy:{},js:{mixin:Object.assign,Pool:class{_get(){return null}put(){}}}};
 const labels={Overflow:{NONE:0,CLAMP:1,SHRINK:2,RESIZE_HEIGHT:3},HorizontalTextAlignment:{LEFT:0,CENTER:1,RIGHT:2},VerticalTextAlignment:{TOP:0,CENTER:1,BOTTOM:2}};
 const shared={shareLabelInfo:{margin:0,hash:'',fontAtlas:null},CanvasPool:{getInstance:()=>({get:()=>({canvas:{},context:{}}),put(){}})}};
 function compile(source,dependencies={}){const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;const module={exports:{}};vm.runInNewContext(output,{exports:module.exports,module,require:key=>{if(key in dependencies)return dependencies[key];if(key==='internal:constants')return {ANDROID:false,JSB:false,RUNTIME_BASED:false};if(key.endsWith('/core'))return core;if(key.endsWith('/platform'))return {logID(){},warnID(){}};if(key==='pal/minigame')return {};if(key.endsWith('/utilities'))return {};if(key.endsWith('/assets'))return {};if(key.endsWith('/asset-enum'))return {};if(key.endsWith('/label'))return labels;if(key==='./font-utils')return shared;throw Error('Unexpected engine dependency '+key)},console});return module.exports;}
 const textUtils=compile(fs.readFileSync(path.join(engine,'cocos/2d/utils/text-utils.ts'),'utf8'));
 const bitmapSource=fs.readFileSync(path.join(engine,'cocos/2d/assets/bitmap-font.ts'),'utf8');
 const ast=ts.createSourceFile('bitmap-font.ts',bitmapSource,ts.ScriptTarget.Latest,true);
 const selected=ast.statements.filter(node=>ts.isClassDeclaration(node)&&['FontAtlas','FontLetterDefinition'].includes(node.name?.text)).map(node=>node.getText(ast)).join('\n');
 const bitmap=compile("const {getSymbolCodeAt}=require('./text-utils');const js={mixin:Object.assign};\n"+selected,{'./text-utils':textUtils});
 const {TextStyle}=compile(fs.readFileSync(path.join(engine,'cocos/2d/assembler/label/text-style.ts'),'utf8'));
 const {TextLayout}=compile(fs.readFileSync(path.join(engine,'cocos/2d/assembler/label/text-layout.ts'),'utf8'));
 const {TextOutputLayoutData,TextOutputRenderData}=compile(fs.readFileSync(path.join(engine,'cocos/2d/assembler/label/text-output-data.ts'),'utf8'));
 const processingSource=fs.readFileSync(path.join(engine,'cocos/2d/assembler/label/text-processing.ts'),'utf8');
 const {TextProcessing}=compile(processingSource,{'../../utils/text-utils':textUtils,'../../assets/bitmap-font':bitmap});
 const atlas=new bitmap.FontAtlas(null),getAttrs=line=>Object.fromEntries([...line.matchAll(/(\w+)=(-?[\d.]+)/g)].map(m=>[m[1],Number(m[2])]));
 let fontSize=0,lineHeight=0;
 for(const line of fnt.split('\n')){const a=getAttrs(line);if(line.startsWith('info '))fontSize=a.size;if(line.startsWith('common '))lineHeight=a.lineHeight;if(line.startsWith('char ')){const g=new bitmap.FontLetterDefinition();Object.assign(g,{u:a.x,v:a.y,w:a.width,h:a.height,offsetX:a.xoffset,offsetY:a.yoffset,xAdvance:a.xadvance,valid:true});atlas.addLetterDefinitions(String(a.id),g)}}
 shared.shareLabelInfo.fontAtlas=atlas;
 const proc=TextProcessing.instance;
 function sample(text,overflow,width=200){const style=new TextStyle(),layout=new TextLayout(),data=new TextOutputLayoutData(),render=new TextOutputRenderData();Object.assign(style,{fontSize:20,actualFontSize:20,originFontSize:fontSize,fntConfig:{fontSize,kerningDict:{}}});Object.assign(layout,{overFlow:overflow,wrapping:false,lineHeight,horizontalAlign:1});data.nodeContentSize.set(width,100);proc.processingString(true,style,layout,data,text);const quads=[];proc.generateRenderInfo(true,style,layout,data,render,text,(_s,_l,_r,_offset,_texture,rect)=>quads.push({x:rect.x,y:rect.y,width:rect.width,height:rect.height}));return {width:data.nodeContentSize.width,fontSize:style.actualFontSize,quads};}
 const widths=new Set();for(let i=0;i<120;i++){const result=sample(String(100000+i),0);widths.add(result.width);assert.strictEqual(result.fontSize,20);assert.strictEqual(result.quads.length,6)}assert.strictEqual(widths.size,1,'Cocos NONE layout must stay fixed for same digit count');
 const one=sample('111111',0),eight=sample('888888',0);assert.strictEqual(one.width,eight.width);assert.notDeepStrictEqual(one.quads,eight.quads,'Cocos must select new atlas rectangles');
 const shrunk=sample('888888',2,30);assert(shrunk.fontSize<20,'narrow SHRINK fixture must actually shrink');
 console.log(`INSTALLED COCOS CORE PASSED: ${creatorRoot}; 120 changing strings, stable NONE width=${one.width}, current UV rectangles and SHRINK=${shrunk.fontSize}; host math/canvas stubs, no Scene/GPU.`);
 return {engineWidth:one.width,shrinkSize:shrunk.fontSize};
};
