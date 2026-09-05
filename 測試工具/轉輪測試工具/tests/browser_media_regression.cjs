'use strict';
// Set PLAYWRIGHT_MODULE and CHROME_PATH if these are not installed conventionally.
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
const playwright=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../../..');
async function run(){
 const browser=await playwright.chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  const page=await browser.newPage({viewport:{width:1500,height:1000}}), errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await page.route('https://**/*',route=>route.abort());
  await page.goto('about:blank');
  const clip=Buffer.from(await page.evaluate(async()=>{
   const c=document.createElement('canvas');c.width=64;c.height=64;const ctx=c.getContext('2d'),stream=c.captureStream(15),parts=[];
   const recorder=new MediaRecorder(stream,{mimeType:'video/webm'});
   const blob=await new Promise(resolve=>{recorder.ondataavailable=e=>parts.push(e.data);recorder.onstop=()=>resolve(new Blob(parts,{type:'video/webm'}));recorder.start();let frame=0;const timer=setInterval(()=>{ctx.fillStyle=frame%2?'#ff2222':'#2222ff';ctx.fillRect(0,0,64,64);if(++frame===20){clearInterval(timer);recorder.stop();stream.getTracks().forEach(t=>t.stop());}},67)});
   return [...new Uint8Array(await blob.arrayBuffer())];
  }));
  const goto=rel=>page.goto(pathToFileURL(path.join(root,rel)).href);
  await goto('測試工具/影片處理工具/Webm轉錄工具/TG_WebM_Converter.html');
  await page.locator('#videoUpload').setInputFiles({name:'fixture.webm',mimeType:'video/webm',buffer:clip});
  await page.waitForFunction(()=>document.getElementById('recordBtn').disabled===false);
  assert.equal(await page.evaluate(()=>Number.isFinite(v.duration)&&v.duration>0),true);
  await page.evaluate(()=>{document.getElementById('endT').value='0.6';});
  await page.locator('#recordBtn').click();
  await page.waitForFunction(()=>document.getElementById('downloadLink').style.display==='block',null,{timeout:10000});
  assert.equal(await page.locator('#recordBtn').isDisabled(),false);
  console.log('PASS real Chromium WebM record / finish / UI restoration');
  await page.locator('#endT').fill('999');await page.locator('#recordBtn').click();
  assert.match(await page.locator('#warningText').innerText(),/影片長度/);assert.equal(await page.locator('#recordBtn').isDisabled(),false);
  await page.evaluate(()=>document.getElementById('endT').value=String(v.duration*.9));await page.locator('#recordBtn').click();
  await page.waitForFunction(()=>recording&&cancelRecording!==null);await page.evaluate(()=>cancelRecordBtn.click());
  await page.waitForFunction(()=>!recording);assert.match(await page.locator('#warningText').innerText(),/取消/);
  console.log('PASS WebM invalid end / cancellation');
  await goto('測試工具/影片處理工具/影片導出連續圖跟去背工具/video_sequence_bgremover_tool.html');
  await page.locator('#file').setInputFiles({name:'fixture.webm',mimeType:'video/webm',buffer:clip});
  await page.waitForFunction(()=>video.videoWidth>0&&video.readyState>=2&&Number.isFinite(video.duration));
  await page.evaluate(()=>{document.getElementById('start').value='0';document.getElementById('end').value='0.5';document.getElementById('count').value='2';});
  await page.locator('#exportSeq').click();await page.waitForFunction(()=>document.getElementById('status').textContent.includes('完成：'),null,{timeout:10000});
  assert.equal(await page.locator('.thumb').count(),2);assert.equal(await page.locator('#exportSeq').isDisabled(),false);
  await page.locator('#clearThumbs').click();assert.equal(await page.locator('.thumb').count(),0);
  await page.locator('#outW').fill('4096');await page.locator('#outH').fill('4096');await page.locator('#count').fill('300');await page.locator('#exportSeq').click();assert.match(await page.locator('#status').innerText(),/512 MiB/);
  console.log('PASS real frame extraction / thumbnails cleanup / budget guard');
  await goto('測試工具/大轉盤測試工具/wheel_tester.html');
  const before=await page.locator('#wheelImage').getAttribute('src');await page.locator('[data-tab="tab-system"]').click();await page.locator('#segments').fill('8');await page.locator('#segments').dispatchEvent('change');assert.notEqual(await page.locator('#wheelImage').getAttribute('src'),before);
  await goto('測試工具/滾分測試工具/ScoreRollTest.html');await page.getByText('停止滾分',{exact:true}).click();
  assert.equal(errors.length,0,errors.join('\n'));console.log('PASS wheel / score pages; zero uncaught page errors');
  if(process.env.MEDIA_REPORT_PATH)fs.writeFileSync(process.env.MEDIA_REPORT_PATH,JSON.stringify({passed:true,browser:'isolated headless Chromium',fixture:'generated 64x64 WebM; no user assets',checks:['real WebM recording and final UI','invalid end rejected','record cancel','PNG frame extraction with local JSZip','thumbnail cleanup','512 MiB export guard','default wheel segment redraw','score page stop'],uncaughtPageErrors:errors},null,2));
 }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
