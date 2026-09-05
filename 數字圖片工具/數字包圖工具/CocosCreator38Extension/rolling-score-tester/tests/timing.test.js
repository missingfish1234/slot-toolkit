'use strict';
const assert = require('assert');
global.Editor = { Panel: { define: value => value }, Message: { request: null } };
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
const definition = require('../dist/panels/default');
const metrics = text => ({ text, fontName:'Numbers', fontUuid:'font-1', fontSize:20, actualFontSize:20, scaleRatio:1, lineHeight:20, spacingX:0, overflow:'NONE', renderWidth:40, renderHeight:20 });
function makePanel() {
    const panel = {...definition.methods, $:{}, target:metrics('READY'), samples:[], runId:1, pendingRequests:0, requestBusy:false, requestChain:Promise.resolve(), running:true, paused:false, mode:'roll', startedAt:0, lastSentAt:900, labels:[]};
    for (const name of Object.keys(definition.$)) panel.$[name] = {value:'',checked:false,disabled:false,textContent:''};
    Object.assign(panel.$.startValue,{value:'0'});Object.assign(panel.$.endValue,{value:'100'});Object.assign(panel.$.duration,{value:'1'});Object.assign(panel.$.fps,{value:'15'});Object.assign(panel.$.easing,{value:'linear'});
    return panel;
}
async function flush() { for(let i=0;i<8;i++) await Promise.resolve(); }
(async () => {
    const requests=[];
    Editor.Message.request=(pkg, method,payload)=>new Promise(resolve=>requests.push({method,payload,resolve}));
    let panel=makePanel();
    const preceding=panel.apply('90','roll',.9);await flush();
    const ending=panel.tickRoll(1000);await flush();
    assert.strictEqual(requests.length,1);assert.strictEqual(panel.running,true,'completion must wait for terminal confirmation');
    requests[0].resolve(metrics('90'));await preceding;await flush();
    assert.strictEqual(requests.length,2);assert.strictEqual(requests[1].payload.text,'100');
    requests[1].resolve(metrics('100'));await ending;
    assert.strictEqual(panel.running,false);assert.strictEqual(panel.$.preview.textContent,'100');

    const calls=[];let pending;
    Editor.Message.request=async(pkg,method,payload)=>{
        calls.push(method);
        if(method==='apply-text') return new Promise(resolve=>{pending=resolve});
        return metrics('READY');
    };
    panel=makePanel();const stale=panel.apply('OLD','roll',.5);await flush();
    const stopped=panel.stopRun(true);await flush();assert.deepStrictEqual(calls,['apply-text']);
    pending(metrics('OLD'));await stale;await stopped;
    assert.deepStrictEqual(calls,['apply-text','restore-preview','inspect-target']);
    assert.strictEqual(panel.samples.length,0,'cancelled run cannot append stale samples');
    assert.strictEqual(panel.$.preview.textContent,'READY');

    panel=makePanel();panel.samples=[{...metrics('9,999'),renderWidth:90},{...metrics('9.99K'),renderWidth:95}];panel.updateSummary();
    assert.strictEqual(panel.summary.sameLengthWidthDrift.length,0,'different formats must not be compared');
    panel.samples.push({...metrics('1,111'),renderWidth:95});panel.updateSummary();assert.strictEqual(panel.summary.sameLengthWidthDrift.length,1);
    Editor.Message.request=async()=>({...metrics('555'),fontUuid:'font-2',fontName:'New font'});
    await panel.apply('555','roll',.5);assert.strictEqual(panel.samples.length,1);assert.strictEqual(panel.target.fontUuid,'font-2');

    panel=makePanel();panel.mode='stress';panel.stressIndex=-1;panel.nextStressAt=0;
    let stressResolve;Editor.Message.request=(pkg,method,payload)=>new Promise(resolve=>{stressResolve=()=>resolve(metrics(payload.text))});
    const firstCase=panel.tickStress(100000);await flush();assert.strictEqual(panel.stressIndex,0,'slow clock must not skip cases');
    stressResolve();await firstCase;assert.strictEqual(panel.samples[0].text,'44444');
    const nextCase=panel.tickStress(panel.nextStressAt);await flush();assert.strictEqual(panel.stressIndex,1);stressResolve();await nextCase;assert.strictEqual(panel.samples[1].text,'41414');
    console.log('Cocos timing: terminal ACK, stop/restore ordering, stale run, format groups, font changes and sequential stress passed');
})().catch(error=>{console.error(error);process.exitCode=1});
