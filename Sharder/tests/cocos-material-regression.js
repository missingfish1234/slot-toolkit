'use strict';
// Run with Node; uses the installed Creator compiler or COCOS_TYPESCRIPT.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const candidates = [process.env.COCOS_TYPESCRIPT, 'typescript', 'C:/ProgramData/cocos/editors/Creator/3.8.6/resources/app.asar.unpacked/node_modules/typescript'].filter(Boolean);
let ts;
for (const candidate of candidates) { try { ts = require(candidate); break; } catch (_) {} }
if (!ts) throw new Error('Set COCOS_TYPESCRIPT to a TypeScript module path.');
class Material {
    constructor() { this.writes = []; }
    setProperty(name, value) { this.writes.push({name, value: typeof value === 'number' ? value : {...value}}); }
}
class Sprite {
    constructor(material) { this.isValid = true; this.customMaterial = material; }
    set customMaterial(value) { if (this._material !== value) this._instance = null; this._material = value; }
    get customMaterial() { return this._material; }
    getMaterialInstance() { return this._instance || (this._instance = new Material()); }
}
class Component { constructor() { this.enabledInHierarchy = true; } getComponent() { return this.sprite; } }
class Vec4 { constructor(...values) { this.set(...values); } set(x,y,z,w) { Object.assign(this,{x,y,z,w}); } }
const identity = () => value => value;
const cc = {Component, Sprite, Material, Vec4, Enum: value => value, math:{lerp:(a,b,t)=>a+(b-a)*t}, _decorator:{ccclass:identity, property:()=>()=>{}, requireComponent:identity, executeInEditMode:identity}};
function load(relative, exported) {
    const file = path.join(__dirname, '..', relative);
    const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText;
    const exports = {};
    vm.runInNewContext(output, {exports, console, require:name => name === 'cc' ? cc : name === 'cc/env' ? {EDITOR:true} : require(name)}, {filename:file});
    return exports[exported];
}
const SoftMask = load('COCOS/漸層遮罩/SoftMaskDirectMaterialDriver.ts','SoftMaskDirectMaterialDriver');
const shared = new Material();
const originalA = new Material(); const originalB = new Material();
const a = new SoftMask(); const b = new SoftMask();
const spriteA = new Sprite(originalA); const spriteB = new Sprite(originalB);
a.targetSprite=spriteA; b.targetSprite=spriteB; a.targetMaterial=b.targetMaterial=shared;
a.progress=.2; b.progress=.8; a.apply(); b.apply();
assert.equal(shared.writes.length,0,'default independent drivers changed shared asset');
assert.equal(spriteA.getMaterialInstance().writes.at(-1).value.x,.2);
assert.equal(spriteB.getMaterialInstance().writes.at(-1).value.x,.8);
for(let i=0;i<1000;i++)a.lateUpdate();
assert.equal(spriteA.getMaterialInstance().writes.length,1,'unchanged parameters uploaded every frame');
a.applyEveryFrame=false; a.previewInEditor=false; a.onValidate();
assert.equal(spriteA.customMaterial,originalA,'preview disabled did not restore material');
a.previewInEditor=true; a.apply(); a.targetMaterial=null; a.apply();
assert.equal(spriteA.customMaterial,originalA,'removed target material left old binding');
a.targetMaterial=shared; a.apply(); a.targetSprite=null; a.apply();
assert.equal(spriteA.customMaterial,originalA,'removed target sprite left old binding');
a.targetSprite=spriteA; a.apply(); a.independentMaterial=false; a.apply();
assert.equal(shared.writes.length,1,'explicit shared mode did not update source');
const external = new Material(); spriteA.customMaterial=external; a.onDisable();
assert.equal(spriteA.customMaterial,external,'disable overwrote an external material change');
b.onDisable(); assert.equal(spriteB.customMaterial,originalB);
const Sweep = load('COCOS/一般圖片掃光/SweepLightController.ts','SweepLightController');
const source = new Material(); const one = new Sweep(); const two = new Sweep();
one.sprite=new Sprite(source); two.sprite=new Sprite(source);
one.onEnable(); two.onEnable(); one.duration=0; one.update(.5);
assert.equal(source.writes.length,0,'Sweep changed shared asset');
assert(one.sprite.getMaterialInstance().writes.every(x=>Number.isFinite(x.value)),'zero duration emitted nonfinite progress');
assert.notEqual(one.sprite.getMaterialInstance(),two.sprite.getMaterialInstance());
one.onDisable(); assert.equal(one._material,null);
console.log('Cocos material lifecycle PASS: independent/shared modes, unchanged upload cache, preview toggle, removed targets, external reassignment, zero duration.');
