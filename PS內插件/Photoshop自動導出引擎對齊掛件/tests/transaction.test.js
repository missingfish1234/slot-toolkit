'use strict';
const assert=require('assert');
const {beginExport,publishExport,safeDocumentName,documentSourceId}=require('../source/export-transaction');
class Entry {
    constructor(name,parent,isFolder=false){this.name=name;this.parent=parent;this.isFolder=isFolder;this.contents='';if(isFolder)this.children=new Map();}
    get nativePath(){return this.parent?this.parent.nativePath+'/'+this.name:this.name;}
    async getEntries(){return [...this.children.values()];}
    async createFolder(name){if(this.children.has(name))throw Error('exists');const value=new Entry(name,this,true);this.children.set(name,value);return value;}
    async createFile(name,{overwrite=false}={}){if(this.children.has(name)&&!overwrite)throw Error('exists');const value=new Entry(name,this);this.children.set(name,value);return value;}
    async write(value){this.contents=value;}
    async read(){return this.contents;}
    async copyTo(folder,options){const copy=await folder.createFile(this.name,options);copy.contents=this.contents;return copy;}
    async moveTo(folder,{newName,overwrite=false}={}){
        const name=newName||this.name;
        if(folder.failNextStageMove&&this.name.startsWith('_psd_stage_')){folder.failNextStageMove=false;throw Error('simulated storage failure');}
        if(folder.children.has(name)&&!overwrite)throw Error('exists');
        this.parent.children.delete(this.name);this.name=name;this.parent=folder;folder.children.set(name,this);
    }
}
async function put(folder,name,value){const file=await folder.createFile(name);await file.write(value);return file;}
const sourceId=title=>documentSourceId({path:'D:/project/'+title},'test');
async function publish(root,title,nonce,value){const tx=await beginExport(root,title,sourceId(title),nonce);await put(tx.stage,'image.png',value);return {tx,result:await publishExport(tx,async()=>{})};}
(async()=>{
    const root=new Entry('output',null,true);
    const legacy=await root.createFolder('engine');await put(legacy,'other-project.txt','legacy');
    const a=await publish(root,'A.psd','one','A1');
    const b=await publish(root,'B.psd','two','B1');
    assert.strictEqual(root.children.get('A_Export').children.get('image.png').contents,'A1');
    assert.strictEqual(root.children.get('B_Export').children.get('image.png').contents,'B1');
    assert.strictEqual(legacy.children.get('other-project.txt').contents,'legacy');
    await put(a.result.folder,'artist-preset.json','user settings');
    const next=await publish(root,'A.psd','three','A2');
    assert.strictEqual(next.result.folder.children.get('artist-preset.json').contents,'user settings');
    assert.strictEqual(root.children.get(next.result.backupName).children.get('image.png').contents,'A1');
    assert.strictEqual(root.children.get('B_Export').children.get('image.png').contents,'B1');
    const invalid=await beginExport(root,'A.psd',sourceId('A.psd'),'invalid');await put(invalid.stage,'image.png','bad');
    await assert.rejects(()=>publishExport(invalid,async()=>{throw Error('validation failed')}),/validation failed/);
    assert.strictEqual(root.children.get('A_Export').children.get('image.png').contents,'A2');
    const failMove=await beginExport(root,'A.psd',sourceId('A.psd'),'failed-move');await put(failMove.stage,'image.png','A3');root.failNextStageMove=true;
    await assert.rejects(()=>publishExport(failMove,async()=>{}),/舊版已保留/);
    assert.strictEqual(root.children.get('A_Export').children.get('image.png').contents,'A2');
    assert(root.children.has(failMove.stageName),'failed staging retained for recovery');
    const conflict=await beginExport(root,'A.psd',sourceId('A.psd'),'conflict');await put(conflict.stage,'artist-preset.json','overwrite');
    await assert.rejects(()=>publishExport(conflict,async()=>{}),/自訂檔案/);
    assert.strictEqual(root.children.get('A_Export').children.get('artist-preset.json').contents,'user settings');
    const unknown=await root.createFolder('C_Export');await put(unknown,'user.txt','protected');
    await assert.rejects(()=>beginExport(root,'C.psd',sourceId('C.psd'),'unowned'),/沒有工具產物清單/);
    assert.strictEqual(unknown.children.get('user.txt').contents,'protected');
    await assert.rejects(()=>beginExport(root,'A.psd',documentSourceId({path:'D:/another-project/A.psd'},'test'),'same-basename'),/不同或無法辨識的來源 PSD/);
    assert.strictEqual(root.children.get('A_Export').children.get('image.png').contents,'A2','same basename from another folder cannot replace output');
    const race=await beginExport(root,'A.psd',sourceId('A.psd'),'race');await put(race.stage,'image.png','A4');
    const manifestFile=root.children.get('A_Export').children.get('.psd-export-manifest.json');
    const originalManifest=manifestFile.contents;
    const manifest=JSON.parse(originalManifest);manifest.sourceId='path:d:/someone-else/a.psd';manifestFile.contents=JSON.stringify(manifest);
    await assert.rejects(()=>publishExport(race,async()=>{}),/不同或無法辨識的來源 PSD/);
    assert.strictEqual(root.children.get('A_Export').children.get('image.png').contents,'A2','ownership checked again at publication');
    delete manifest.sourceId;manifestFile.contents=JSON.stringify(manifest);
    await assert.rejects(()=>beginExport(root,'A.psd',sourceId('A.psd'),'legacy-identity'),/不同或無法辨識的來源 PSD/);
    manifestFile.contents=originalManifest;
    assert.strictEqual(documentSourceId({path:'D:\\PROJECT\\A.psd'},'test'),sourceId('A.psd'));
    assert.notStrictEqual(documentSourceId({path:'',id:7},'session-a'),documentSourceId({path:'',id:7},'session-b'));
    assert.notStrictEqual(documentSourceId({path:'',id:7},'session-a'),documentSourceId({path:'',id:8},'session-a'));
    assert.throws(()=>documentSourceId({path:''},'session-a'),/無法辨識來源 PSD/);
    await assert.rejects(()=>beginExport(root,'D.psd',''),/缺少來源 PSD/);
    assert.strictEqual(safeDocumentName('CON.psd'),'PSD_CON');
    console.log('PS transaction: A/B isolation, legacy/user preservation, backup, validation failure, rename rollback, same-basename source identity, ownership race and unsaved-session isolation passed');
})().catch(error=>{console.error(error);process.exitCode=1});
