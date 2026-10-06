'use strict';
// Reconstruct source cells from a supplied FNT/PNG in memory. Never edit them.
const fs=require('fs'),path=require('path'),assert=require('assert');
const checkEngine=require('./cocos-engine-check');
module.exports=async function({evaluate,screenshot},creatorRoot,fontPath){
 const fnt=fs.readFileSync(fontPath,'utf8');
 const page=fnt.match(/^page id=0 file="([^"]+)"/m)[1];
 const png=fs.readFileSync(path.join(path.dirname(fontPath),page)).toString('base64');
 const glyphs=fnt.split('\n').filter(line=>line.startsWith('char id=')).map(line=>Object.fromEntries([...line.matchAll(/(\w+)=(-?\d+)/g)].map(m=>[m[1],Number(m[2])])));
 const original=checkEngine(fnt,creatorRoot,{quiet:true,samples:[{text:'123',lineHeight:40}]});
 await evaluate(`(async()=>{
  clearAll();const atlas=new Image();atlas.src='data:image/png;base64,${png}';await atlas.decode();
  window.centeringSource=${JSON.stringify(glyphs)}.map(a=>{const img=document.createElement('canvas');img.width=a.width;img.height=a.height;img.getContext('2d').drawImage(atlas,a.x,a.y,a.width,a.height,0,0,a.width,a.height);return {char:String.fromCodePoint(a.id),charCode:a.id,img,width:a.width,height:a.height};});
  Object.assign(state.config,{fontSize:72,lineHeight:80,trim:true,unifiedTop:true,groupCenter:true,keepYBounds:true,cocosBaselineFix:true,cocosKeepLineHeight:true,lockInfoSize:true,autoSafeLineHeight:true,monospaceNum:true,cocosFixedDigitCell:true,opticalFitNum:false,yOffsetAdjust:0,previewText:'123'});
  HTMLAnchorElement.prototype.click=function(){window.downloadURL=this.href};
 })()`);
 const results=await evaluate(`(async()=>{
  const results=[];
  for(const scale of [1,.67,.75])for(const trimMode of ['keepY','tight','none'])for(const lock of [true,false]){
   state.glyphs=centeringSource.map(g=>({...g}));Object.assign(state.config,{exportScale:scale,trim:trimMode!=='none',keepYBounds:trimMode==='keepY',lockInfoSize:lock,cocosBaselineFix:true});
   if(!packAndDraw())throw Error(state.packError);renderPreview();
   const geometry=state.glyphs.map(g=>[g.exW,g.exOffX,g.exDrawW,g.exDrawH,g.rect.x,g.rect.y]);
   const alpha={};for(const g of state.glyphs){const a=els.mainCtx.getImageData(g.rect.x,g.rect.y,g.exDrawW,g.exDrawH).data;let top=g.exDrawH,bottom=0;for(let y=0;y<g.exDrawH;y++)for(let x=0;x<g.exDrawW;x++)if(a[(y*g.exDrawW+x)*4+3]){top=Math.min(top,y);bottom=Math.max(bottom,y+1);}alpha[g.char]={top,bottom};}
   const originalDraw=els.previewCtx.drawImage.bind(els.previewCtx);const previewCenters=[];
   els.previewCtx.drawImage=function(...args){if(args.length===9){const g=state.glyphs.find(g=>g.img===args[0]);if(g)previewCenters.push({char:g.char,center:args[6]+((g.rawTrim.y-g.computedTrim.y)+g.rawTrim.h/2)*(g.exDrawH/g.computedTrim.h)-els.previewCanvas.height/2});}return originalDraw(...args);};
   renderPreview();els.previewCtx.drawImage=originalDraw;
   await exportZip();const zip=await JSZip.loadAsync(await(await fetch(window.downloadURL)).arrayBuffer());const out=await zip.file('myFont.fnt').async('string');
   state.config.cocosBaselineFix=false;packAndDraw();const unchanged=JSON.stringify(geometry)===JSON.stringify(state.glyphs.map(g=>[g.exW,g.exOffX,g.exDrawW,g.exDrawH,g.rect.x,g.rect.y]));
   results.push({scale,trimMode,lock,fnt:out,alpha,previewCenters,unchanged});
  }
  state.glyphs=centeringSource.map(g=>({...g}));Object.assign(state.config,{exportScale:1,trim:true,keepYBounds:true,lockInfoSize:true,cocosBaselineFix:true});packAndDraw();renderPreview();updateUIFromState();
  return results;
 })()`);
 let worstCenter=0;
 for(const result of results){
  assert(result.unchanged,'Vertical fix must not change glyph scale, widths or atlas rectangles');
  const output=checkEngine(result.fnt,creatorRoot,{quiet:true,samples:[{text:'0123456789',lineHeight:40},{text:'0123456789',lineHeight:160},{text:'0123456789',fontSize:36},{text:'123',lineHeight:40}]});
  for(const s of output.samples.slice(0,3)){
   const tops=s.quads.map(q=>q.positionY-result.alpha[q.char].top*s.scale);
   const bottoms=s.quads.map(q=>q.positionY-result.alpha[q.char].bottom*s.scale);
   const center=(Math.max(...tops)+Math.min(...bottoms))/2;
   // Raster resampling + integer FNT offsets can differ by about one atlas pixel.
   assert(Math.abs(center)<=1.5*s.scale,JSON.stringify({scale:result.scale,trim:result.trimMode,lock:result.lock,center}));
   worstCenter=Math.max(worstCenter,Math.abs(center));
  }
  const s=output.samples[3];
  for(const p of result.previewCenters){const q=s.quads.find(q=>q.char===p.char),a=result.alpha[p.char];const engineCenter=q.positionY-(a.top+a.bottom)/2*s.scale;assert(Math.abs(engineCenter+p.center*s.scale)<=1.5*s.scale,'Preview and engine vertical positions must agree');}
 }
 await evaluate('changeSimZoom(-.5);changeZoom(-.65)');
 await screenshot('cocos-centering-fixed-preview');
 console.log(JSON.stringify({test:'Cocos 3.8.6 alpha-centering',cases:results.length,worstCenterInLabelUnits:worstCenter,original123Width:original.samples[0].width,originalQuadTop:original.samples[0].quads[0].positionY,sourceUnchanged:fs.readFileSync(fontPath,'utf8')===fnt,sceneGPU:false}));
};
