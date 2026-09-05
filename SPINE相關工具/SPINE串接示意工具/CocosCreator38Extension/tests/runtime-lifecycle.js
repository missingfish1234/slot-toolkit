'use strict';
const assert=require('assert/strict'),fs=require('fs'),path=require('path'),vm=require('vm');
let ts;
for(const candidate of [process.env.COCOS_TYPESCRIPT,'typescript','C:/ProgramData/cocos/editors/Creator/3.8.6/resources/app.asar.unpacked/node_modules/typescript']) {
    if(!candidate)continue;
    try{ts=require(candidate);break;}catch{}
}
if(!ts)throw Error('Lifecycle tests need TypeScript; npm install --no-save typescript or set COCOS_TYPESCRIPT to its installed module.');
const root=fs.existsSync(path.join(__dirname,'..','dist'))?path.join(__dirname,'..'):path.join(__dirname,'..','spine-director-cocos38');
const source=fs.readFileSync(path.join(root,'static/runtime/CocosTimelinePlayer.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText;
let pending=[],scene={};
class Component{constructor(){this.isValid=true;this.enabledInHierarchy=true;}}
const cc={Component,director:{getScene:()=>scene},resources:{load:(_p,_t,cb)=>pending.push(cb)},_decorator:{ccclass:()=>c=>c,property:(...args)=>args.length>=2?undefined:()=>{}},sp:{Skeleton:class{}},Animation:class{},ParticleSystem:class{},ParticleSystem2D:class{},UIOpacity:class{},JsonAsset:class{},v3:()=>({})};
const scope={exports:{},require:()=>cc,console};vm.createContext(scope);vm.runInContext(compiled,scope);
const Player=Object.values(scope.exports).find(x=>typeof x==='function');
const asset={json:{schema:'cocos-native-timeline@1',tracks:[],duration:1}};
async function fixture(action){
    pending=[];scene={};const p=new Player();p.configPath='test';let touched=0;p.bindSceneNodes=()=>touched++;p.seek=()=>touched++;p.play=()=>touched++;
    const loading=p.loadTimeline();action(p);pending[0](null,asset);await loading;assert.equal(touched,0);return p;
}
(async()=>{
    await fixture(p=>{p.onDestroy();p.isValid=false;});
    await fixture(p=>{p.onDisable();p.enabledInHierarchy=false;});
    await fixture(()=>{scene={};});
    pending=[];const p=new Player();p.configPath='test';let touched=0;p.bindSceneNodes=()=>touched++;p.seek=()=>touched++;p.play=()=>touched++;
    const old=p.loadTimeline();p.onDisable();p.onEnable();const next=pending[1];pending[0](null,asset);await old;assert.equal(p.loading,true);assert.equal(touched,0);next(null,asset);await new Promise(r=>setImmediate(r));assert.equal(touched,3);assert.equal(p.loading,false);
    console.log('Timeline runtime lifecycle: destroyed/disabled/scene-change/stale-vs-new-load PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
