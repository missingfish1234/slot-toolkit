'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../../..');
const read=rel=>fs.readFileSync(path.join(root,rel),'utf8');
const slice=(src,start,end)=>{const a=src.indexOf(start),b=src.indexOf(end,a);assert.ok(a>=0&&b>a,start);return src.slice(a,b)};
const context=x=>vm.createContext(x);
async function run(){
 const score=read('測試工具/滾分測試工具/ScoreRollTest.html');
 let pending=new Map(),next=0,draws=0;
 const element=()=>({style:{},insertAdjacentElement(){}});
 const s=context({animState:{frameId:null},performance:{now:()=>0},draw:()=>draws++,requestAnimationFrame:f=>{pending.set(++next,f);return next},cancelAnimationFrame:id=>pending.delete(id),document:{getElementById:()=>({...element(),value:'linear'}),createElement:element},window:{addEventListener(){}},Easings:{linear:t=>t}});
 vm.runInContext(slice(score,'function startAnimation(','function draw('),s);
 s.startAnimation(0,100,1000);s.startAnimation(0,200,1000);assert.equal(pending.size,1);
 const batch=[...pending.values()];pending.clear();batch.forEach(f=>f(500));assert.equal(s.animState.currentVal,100);assert.equal(pending.size,1);
 s.stopAnimation();assert.equal(pending.size,0);assert.equal(s.animState.isRunning,false);console.log('PASS score restart / stop / value');

 const seq=read('測試工具/影片處理工具/影片導出連續圖跟去背工具/video_sequence_bgremover_tool.html');
 let pixel;const vals={mode:{value:'alphaOnly'},keyColor:{value:'#00ff00'},tol:{value:80},soft:{value:35},contrast:{value:1},premultiply:{checked:false},erode:{value:0},feather:{value:0}};
 const a=context({canvas:{width:1,height:1},ctx:{getImageData:()=>({data:pixel}),putImageData(){}},$:id=>vals[id],hexToRgb:()=>({r:0,g:255,b:0}),clamp:(v,l,h)=>Math.max(l,Math.min(h,v))});
 vm.runInContext(slice(seq,'function processCanvas(','function refineAlpha('),a);
 for(const alpha of [0,1,64,128,254,255]){pixel=new Uint8ClampedArray([100,100,100,alpha]);a.processCanvas();assert.equal(pixel[3],alpha)}
 console.log('PASS neutral Alpha at 6 boundary/intermediate values');

 const slot=read('測試工具/轉輪測試工具/slot_test.html');
 const data=m=>'data:application/octet-stream;base64,'+Buffer.from(m).toString('base64');
 const original={id:'hero',name:'hero.png',url:data('png'),isSpine:true,spineData:{jsonName:'hero.skel',atlasName:'hero.atlas',rawDataURIs:{'hero.skel':data('skeleton'),'hero.atlas':data('atlas'),'page1.png':data('page1'),'page2.png':data('page2')}}};
 const p=context({settings:{images:[original]},projectData:{assets:{},modes:{base:{},fg:{}}},blobToBase64:async url=>url,base64ToBlobUrl:x=>'restored:'+x,atob:x=>Buffer.from(x,'base64').toString('binary')});
 vm.runInContext(slice(slot,'async function packSpineData(','        async function blobToBase64('),p);
 const body=slot.match(/const _packData = async \(cfg\) => \{([\s\S]*?)\n            \};/)[1];vm.runInContext('async function pack(cfg){'+body+'}',p);
 const packed=await p.pack({schemaVersion:3});p.validateProjectPack(packed);
 const symbol=packed.pack.symbols[0],restored=p.restoreSpineData(symbol);assert.equal(symbol.isSpine,true);assert.equal(restored.jsonName,'hero.skel');assert.equal(Object.keys(restored.rawDataURIs).length,4);assert.equal(restored.rawDataURIs['page2.png'],'restored:'+data('page2'));
 assert.throws(()=>p.validateProjectPack({schemaVersion:99}));delete symbol.spineData.resources['hero.atlas'];assert.throws(()=>p.validateProjectPack(packed));console.log('PASS Spine multi-page pack / restore / missing-resource / future schema');

 const wheel=read('測試工具/大轉盤測試工具/wheel_tester.html');let arcs=0,handler;
 const w=context({els:{segments:{value:12,addEventListener:(ev,f)=>handler=f},wheelImage:{src:''},showSegmentSeams:{checked:false},wheelStatus:{},useSegments:{checked:false}},ctx:{wheelImages:[]},document:{createElement:()=>({getContext:()=>({beginPath(){},moveTo(){},arc(){arcs++},fill(){},stroke(){}}),toDataURL:()=>String(arcs)})},drawOverlay(){},drawSeamLines(){},resetPool(){}});
 vm.runInContext(slice(wheel,'function createDefaultWheel(','    // Curve Editor'),w);vm.runInContext(slice(wheel,"els.segments.addEventListener('change'","els.noRepeatMode.addEventListener('change'"),w);
 w.createDefaultWheel();arcs=0;w.els.segments.value=8;handler();assert.equal(arcs,8);w.ctx.usingDefaultWheel=false;arcs=0;handler();assert.equal(arcs,0);console.log('PASS generated wheel changes; uploaded wheel preserved');

 const webm=read('測試工具/影片處理工具/Webm轉錄工具/TG_WebM_Converter.html');
 const fields={startT:{value:0},endT:{value:5},cW:{value:512},cH:{value:256},cX:{value:0},cY:{value:0}};
 const r=context({document:{getElementById:id=>fields[id]},v:{duration:2,videoWidth:512},platformTarget:{value:'telegram'},outEdgeNum:{value:512},currentRecordFps:30});
 vm.runInContext(slice(webm,'function recordingParameters()','        function seekRecordingStart('),r);assert.throws(()=>r.recordingParameters());fields.endT.value=2;assert.equal(r.recordingParameters().outW,512);fields.endT.value=0;assert.throws(()=>r.recordingParameters());fields.endT.value=2;fields.cW.value=0;assert.throws(()=>r.recordingParameters());console.log('PASS WebM time bounds / dimensions');
 for(const src of [score,seq,slot,wheel,webm])for(const m of src.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);console.log('PASS 5 HTML syntax checks');
}
run().catch(e=>{console.error(e);process.exitCode=1});
