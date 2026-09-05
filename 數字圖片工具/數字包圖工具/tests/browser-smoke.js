'use strict';
// Runs the three real HTML tools in a fresh headless Chromium profile.
// No user browser profile, downloads directory, or engine project is used.
const assert=require('assert'),fs=require('fs'),os=require('os'),path=require('path'),{spawn}=require('child_process'),{pathToFileURL}=require('url');
const browserPath=process.argv[2]||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'toolkit-numbers-browser-'));
const proc=spawn(browserPath,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let lastConnection, browserClosed=false;
async function connect(url){const socket=new WebSocket(url);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let sequence=0;const waiters=new Map();socket.onmessage=event=>{const msg=JSON.parse(event.data);const promise=waiters.get(msg.id);if(promise){waiters.delete(msg.id);msg.error?promise.reject(Error(msg.error.message)):promise.resolve(msg.result)}};return {close:()=>socket.close(),send:(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;waiters.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(waiters.delete(id))reject(Error('CDP timeout: '+method))},15000).unref()})};}
async function evaluate(c,expression){const result=await c.send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;}
(async()=>{
 let port;for(let i=0;i<100;i++){const file=path.join(profile,'DevToolsActivePort');if(fs.existsSync(file)){port=fs.readFileSync(file,'utf8').split('\n')[0];break;}await delay(100)}if(!port)throw Error('Headless Chromium did not start');
 const numbers=path.resolve(__dirname,'..','..');
 async function page(file){const target=await(await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(pathToFileURL(file).href)}`,{method:'PUT'})).json();const c=lastConnection=await connect(target.webSocketDebuggerUrl);for(let i=0;i<100;i++){if(await evaluate(c,'document.readyState')==='complete')return c;await delay(50)}throw Error('HTML load timeout');}
 let c=await page(path.join(numbers,'合併數字圖拆分工具','split_glyph_tool_dragdrop_v5.html'));
 const split=await evaluate(c,`(async()=>{
   srcCanvas.width=200;srcCanvas.height=24;srcCtx.clearRect(0,0,200,24);srcCtx.fillStyle='white';for(let i=0;i<6;i++)srcCtx.fillRect(3+i*30,3,12,16);srcImg=srcCanvas;
   $('chars').value='01.,xX';$('gapMerge').value='0';$('minRun').value='1';split();
   if(results.length!==6)throw Error(err.textContent);
   window.showSaveFilePicker=undefined;HTMLAnchorElement.prototype.click=function(){window.downloadURL=this.href};await downloadZip();
   const zip=await JSZip.loadAsync(await (await fetch(window.downloadURL)).arrayBuffer());const files=Object.keys(zip.files);
   const glyphs=JSON.parse(await zip.file('glyph-map.json').async('string')).glyphs;
   $('chars').value='001';split();if(results.length||!$('zipBtn').disabled)throw Error('duplicate export enabled');
   return {files,glyphs};
 })()`);
 assert(split.files.includes('dot.png'));assert(split.files.includes('comma.png'));assert(split.files.includes('u0078.png'));assert(split.files.includes('X.png'));c.close();
 c=await page(path.join(numbers,'數字包圖工具','makefont.html'));
 const packed=await evaluate(c,`(async()=>{
   state.config.monospaceNum=true;state.config.cocosFixedDigitCell=true;state.config.powerOfTwo=true;
   state.glyphs=Array.from('0123456789.,').map((char,i)=>{const img=document.createElement('canvas');img.width=i===1?12:40;img.height=30;img.getContext('2d').fillRect(0,0,img.width,img.height);return {char,charCode:char.codePointAt(0),img,width:img.width,height:img.height}});
   if(!packAndDraw())throw Error(state.packError);renderPreview();HTMLAnchorElement.prototype.click=function(){window.downloadURL=this.href};await exportZip();
   const zip=await JSZip.loadAsync(await (await fetch(window.downloadURL)).arrayBuffer());const fnt=await zip.file('myFont.fnt').async('string');const png=await zip.file('myFont.png').async('uint8array');
   return {fnt,pngMagic:Array.from(png.slice(0,8)),mapping:${JSON.stringify(split.glyphs)}.map(g=>[g.char,guessCharFromFileName({name:g.file})])};
 })()`);
 assert.match(packed.fnt,/char id=46 /);assert.match(packed.fnt,/char id=44 /);assert.deepStrictEqual(packed.pngMagic,[137,80,78,71,13,10,26,10]);for(const [a,b]of packed.mapping)assert.strictEqual(a,b);
 if(process.argv[3]) require('./cocos-engine-check')(packed.fnt,process.argv[3]);
 if(process.argv[4]) {
   const sourceFolder=path.resolve(process.argv[4]);
   const inputs=fs.readdirSync(sourceFolder).filter(name=>/\.png$/i.test(name)).map(name=>({name,data:fs.readFileSync(path.join(sourceFolder,name)).toString('base64')}));
   assert(inputs.length,'source fixture folder contains no PNG');
   const actualFonts=await evaluate(c,`(async()=>{
     clearAll();const inputs=${JSON.stringify(inputs)};
     const files=inputs.map(input=>new File([Uint8Array.from(atob(input.data),c=>c.charCodeAt(0))],input.name,{type:'image/png'}));
     await processFiles(files);if(state.glyphs.length!==inputs.length)throw Error('source glyph count mismatch');
     const result=[];for(const scale of [1,0.67,0.75]){state.config.exportScale=scale;if(!packAndDraw())throw Error(state.packError);await exportZip();const zip=await JSZip.loadAsync(await(await fetch(window.downloadURL)).arrayBuffer());result.push({scale,fnt:await zip.file('myFont.fnt').async('string')})}return result;
   })()`);
   for(const fixture of actualFonts){if(process.argv[3])require('./cocos-engine-check')(fixture.fnt,process.argv[3]);console.log('Actual input PNG fixture passed: '+sourceFolder+'; '+inputs.length+' glyphs; scale='+fixture.scale)}
 }
 c.close();
 c=await page(path.join(numbers,'圖片中心點快速對位工具','slot_symbol_center_align_tool.html'));
 const centered=await evaluate(c,`(async()=>{
   const input=document.createElement('canvas');input.width=10;input.height=10;input.getContext('2d').fillRect(0,0,10,10);const bounds=detectBounds(input,8);
   const output=renderCentered({bounds,sourceCanvas:input,width:10,height:10,name:'數字.png'},0,{alignMode:'bottomCenter',padding:0,offsetX:0,offsetY:0,prefix:''},10,10);
   const data=output.canvas.getContext('2d').getImageData(0,0,10,10).data;let opaque=0;for(let i=3;i<data.length;i+=4)if(data[i]===255)opaque++;
   const blob=await new Promise(r=>output.canvas.toBlob(r));const zip=createSimpleZip([{name:'數字.png',data:new Uint8Array(await blob.arrayBuffer())}]);return {opaque,offset:output.drawY,zipFlag:new DataView(await zip.arrayBuffer()).getUint16(6,true),preview:previewDimensions(400,100,1)};
 })()`);
 assert.strictEqual(centered.opaque,100);assert.strictEqual(centered.offset,0);assert.strictEqual(centered.zipFlag,2048);assert.deepStrictEqual(centered.preview,{width:180,height:45});
 console.log('REAL CHROMIUM PASSED: split PNG/ZIP → filename/codepoint roundtrip → real BMFont PNG/FNT ZIP; center 100/100 opaque pixels, aspect ratio and Unicode ZIP');
 await c.send('Browser.close');browserClosed=true;c.close();
})().catch(error=>{console.error(error);process.exitCode=1}).finally(async()=>{
 if(lastConnection&&!browserClosed){try{await lastConnection.send('Browser.close')}catch(_){}}
 if(lastConnection)lastConnection.close();for(let i=0;i<30&&proc.exitCode===null;i++)await delay(100);if(proc.exitCode===null)proc.kill();await delay(300);
 const resolved=path.resolve(profile),base=path.resolve(os.tmpdir())+path.sep;
 if(resolved.startsWith(base)&&path.basename(resolved).startsWith('toolkit-numbers-browser-')){try{fs.rmSync(resolved,{recursive:true,force:true})}catch(_){console.log('Temporary browser profile retained (locked): '+resolved)}}
});
