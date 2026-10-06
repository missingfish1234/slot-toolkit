'use strict';
// Real, isolated Chromium: exercise the review dialog, PNG decoding and export.
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {spawn} = require('child_process');
const {pathToFileURL} = require('url');
const root = path.resolve(__dirname, '..');
const browser = process.argv[2] || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const artifacts = process.argv[3] && path.resolve(process.argv[3]);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'bmfont-import-'));
const proc = spawn(browser, ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'], {windowsHide:true,stdio:'ignore'});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket, connection, closed = false;
async function connect(url) {
    socket = new WebSocket(url);
    await new Promise((resolve,reject) => {socket.onopen=resolve;socket.onerror=reject;});
    let id = 0; const waiters = new Map();
    socket.onmessage = event => {const msg=JSON.parse(event.data),p=waiters.get(msg.id);if(p){waiters.delete(msg.id);clearTimeout(p.timer);msg.error?p.reject(Error(msg.error.message)):p.resolve(msg.result);}};
    return {send(method,params={}){return new Promise((resolve,reject)=>{const key=++id;const timer=setTimeout(()=>{waiters.delete(key);reject(Error('CDP timeout: '+method));},15000);waiters.set(key,{resolve,reject,timer});socket.send(JSON.stringify({id:key,method,params}));});}};
}
async function evaluate(expression) {
    const result = await connection.send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
}
async function until(expression) {
    for(let i=0;i<100;i++){if(await evaluate(expression))return;await delay(30);}
    throw Error('Condition timed out: '+expression);
}
async function start(inputs) {
    await evaluate(`window.importRun=processFiles(${JSON.stringify(inputs)}.map((f,i)=>{
        let bytes;
        if(f.data!==undefined)bytes=Uint8Array.from(atob(f.data),c=>c.charCodeAt(0));
        else {const canvas=document.createElement('canvas');canvas.width=f.width||16+i;canvas.height=24;canvas.getContext('2d').fillRect(1,1,canvas.width-2,22);bytes=Uint8Array.from(atob(canvas.toDataURL().split(',')[1]),c=>c.charCodeAt(0));}
        return new File([bytes],f.name,{type:'image/png'});
    }));true`);
    await until('!!document.querySelector(".import-dialog[open]")');
}
async function confirm() {
    assert.strictEqual(await evaluate('document.querySelector(".import-confirm").disabled'),false);
    await evaluate('document.querySelector(".import-confirm").click();window.importRun');
    assert.strictEqual(await evaluate('importBusy'),false);
}
async function cancel() {
    await evaluate('document.querySelector(".import-cancel").click();window.importRun');
}
async function mappings() {return evaluate('Object.fromEntries(state.glyphs.map(g=>[g.sourceName,g.char]))');}
async function setChar(filename,char) {
    await evaluate(`{const r=[...document.querySelectorAll('.import-row')].find(r=>r.querySelector('.import-filename').textContent===${JSON.stringify(filename)});const input=r.querySelector('.import-char');input.value=${JSON.stringify(char)};input.dispatchEvent(new Event('input',{bubbles:true}));}`);
}
async function screenshot(name) {
    if(!artifacts)return;
    fs.mkdirSync(artifacts,{recursive:true});
    const result=await connection.send('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(artifacts,name+'.png'),Buffer.from(result.data,'base64'));
}
(async()=>{
    let port;
    for(let i=0;i<100;i++){const active=path.join(profile,'DevToolsActivePort');if(fs.existsSync(active)){port=fs.readFileSync(active,'utf8').split('\n')[0];break;}await delay(50);}
    assert(port,'Chromium started');
    const target=await(await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(pathToFileURL(path.join(root,'makefont.html')).href)}`,{method:'PUT'})).json();
    connection=await connect(target.webSocketDebuggerUrl);
    await connection.send('Emulation.setDeviceMetricsOverride',{width:1200,height:900,deviceScaleFactor:1,mobile:false});
    await until(`location.href===${JSON.stringify(pathToFileURL(path.join(root,'makefont.html')).href)} && document.readyState==='complete'`);
    await start(['bU.png','kU.png','xU.png','dot.png','comma.png','u1f600.png'].map(name=>({name})));
    assert.strictEqual(await evaluate('state.glyphs.length'),0,'No mutation before confirmation');
    await screenshot('suffix-review');
    await confirm();
    assert.deepStrictEqual(await mappings(),{'bU.png':'B','comma.png':',','dot.png':'.','kU.png':'K','u1f600.png':'😀','xU.png':'X'});
    const before=await mappings();
    await evaluate('state.glyphs.find(g=>g.char==="B").customX=7');
    await start([{name:'bU.png',width:52}]);
    assert(await evaluate('document.querySelector(".import-confirm").disabled'));
    await cancel(); assert.deepStrictEqual(await mappings(),before);
    assert.strictEqual(await evaluate('state.glyphs.find(g=>g.char==="B").width'),16);
    await start([{name:'bU.png',width:52}]);
    await evaluate('document.querySelector(".import-replace input").click()');
    await confirm(); assert.strictEqual(await evaluate('state.glyphs.length'),6);
    assert.strictEqual(await evaluate('state.glyphs.find(g=>g.char==="B").width'),52);
    assert.strictEqual(await evaluate('state.glyphs.find(g=>g.char==="B").customX'),7);
    assert.match(await evaluate('els.importStatus.textContent'),/經確認取代 1/);
    await start([{name:'WIN.png'}]);
    await evaluate('processFiles([new File([],"unexpected.png",{type:"image/png"})])');
    assert.strictEqual(await evaluate('document.querySelectorAll(".import-row").length'),1,'Overlapping imports cannot replace the pending review');
    assert(await evaluate('document.querySelector(".import-confirm").disabled'));
    await setChar('WIN.png','WIN'); assert(await evaluate('document.querySelector(".import-confirm").disabled'));
    await setChar('WIN.png','W'); await confirm();
    await start([{name:'bad.png',data:'bm90IGEgcG5n'},{name:'Q.png'}]);
    assert.match(await evaluate('document.querySelector(".import-summary").textContent'),/1 張解碼失敗/);
    await confirm(); assert.strictEqual((await mappings())['Q.png'],'Q');
    await start([{name:'A.png'}]);
    await connection.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await connection.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await until('!document.querySelector(".import-dialog")');
    assert.strictEqual((await mappings())['A.png'],undefined);
    await evaluate('clearAll()');
    await start([{name:'2.png'},{name:'X.png'},{name:'X2.png'}]);
    assert(await evaluate('document.querySelector(".import-confirm").disabled'));
    await screenshot('duplicate-review');
    await setChar('X2.png','x'); await confirm();
    assert.deepStrictEqual(await mappings(),{'2.png':'2','X.png':'X','X2.png':'x'});
    await evaluate('clearAll()');
    await start([{name:'X.png'},{name:'char_X.png'}]);
    assert(await evaluate('document.querySelector(".import-confirm").disabled'));
    await evaluate('document.querySelectorAll(".import-include")[1].click()');
    await confirm(); assert.strictEqual(await evaluate('state.glyphs.length'),1);
    for(const folder of ['測試用','測試2組','測試3組/數字','NUM_X-1']) {
        const dir=path.join(root,folder); if(!fs.existsSync(dir))continue;
        const files=fs.readdirSync(dir).filter(name=>/\.png$/i.test(name)).map(name=>({name,data:fs.readFileSync(path.join(dir,name)).toString('base64')}));
        await evaluate('clearAll()'); await start(files);
        if(folder==='測試2組'){assert(await evaluate('document.querySelector(".import-confirm").disabled'));await setChar('X2.png','x');}
        if(folder==='測試用') {
            await evaluate(`document.querySelector('.import-rows').scrollTop=document.querySelector('.import-rows').scrollHeight`);
            await screenshot('actual-letter-suffixes');
            await connection.send('Emulation.setDeviceMetricsOverride',{width:600,height:600,deviceScaleFactor:1,mobile:false});
            assert(await evaluate(`(()=>{const d=document.querySelector('.import-dialog').getBoundingClientRect();return d.width<=innerWidth&&d.height<=innerHeight;})()`));
            assert(await evaluate(`(()=>{const rows=document.querySelector('.import-rows');return rows.scrollWidth<=rows.clientWidth+1;})()`),'Narrow dialog must not clip character inputs horizontally');
            await screenshot('narrow-review');
            await connection.send('Emulation.setDeviceMetricsOverride',{width:1200,height:900,deviceScaleFactor:1,mobile:false});
        }
        await screenshot(folder==='測試用'?'actual-letter-review':'actual-'+folder.replaceAll('/','-'));
        await confirm(); const result=await mappings(); assert.strictEqual(Object.keys(result).length,files.length,folder);
        if(folder==='測試用'){for(const f of files.filter(f=>/^[a-z]U\.png$/.test(f.name)))assert.strictEqual(result[f.name],f.name[0].toUpperCase());}
        if(folder==='測試2組')assert.strictEqual(result['2.png'],'2');
        if(folder==='測試3組/數字')assert.strictEqual(result['X_a.png'],'X');
        const exports=await evaluate(`(async()=>{
            HTMLAnchorElement.prototype.click=function(){window.downloadURL=this.href};
            state.config.monospaceNum=true;state.config.cocosFixedDigitCell=true;
            const result=[];for(const scale of [1,.67,.75]){state.config.exportScale=scale;await exportZip();const zip=await JSZip.loadAsync(await(await fetch(window.downloadURL)).arrayBuffer());result.push({scale,fnt:await zip.file('myFont.fnt').async('string'),png:Array.from((await zip.file('myFont.png').async('uint8array')).slice(0,8))});}return result;
        })()`);
        for(const output of exports){assert.match(output.fnt,new RegExp('chars count='+files.length+'\\n'));assert.deepStrictEqual(output.png,[137,80,78,71,13,10,26,10]);const codes=[...output.fnt.matchAll(/char id=(\d+) /g)].map(m=>Number(m[1]));assert.strictEqual(new Set(codes).size,files.length);for(const char of Object.values(result))assert(codes.includes(char.codePointAt(0)));}
        console.log('PASS actual PNG review + FNT/PNG export, 3 scales: '+folder+' ('+files.length+' glyphs)');
    }
    console.log('PASS: review, case-sensitive mapping, batch conflicts, explicit replacement, unknown/multichar input, corrupt PNG, skip, cancel/Escape');
    if(process.argv[4] && process.argv[5])await require('./centering-browser-check')({evaluate,screenshot},process.argv[4],path.resolve(process.argv[5]));
    await connection.send('Browser.close');closed=true;
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
    if(connection&&!closed){try{await connection.send('Browser.close');}catch(_){}}
    if(socket)socket.close();
    for(let i=0;i<30&&proc.exitCode===null;i++)await delay(100);
    if(proc.exitCode===null)proc.kill();
    await delay(200);
    const resolved=path.resolve(profile);
    if(resolved.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(resolved).startsWith('bmfont-import-')){
        try{fs.rmSync(resolved,{recursive:true,force:true});}catch(_){console.log('Temporary profile retained (locked): '+resolved);}
    }
});
