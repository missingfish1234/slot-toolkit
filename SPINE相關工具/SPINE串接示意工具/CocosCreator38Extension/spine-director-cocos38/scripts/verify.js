'use strict';
const fs=require('fs'), path=require('path'), cp=require('child_process');
const root=path.resolve(__dirname,'..');
const tests=fs.existsSync(path.join(root,'tests'))?path.join(root,'tests'):path.join(root,'..','tests');
for(const name of ['native-timeline-smoke.js','timeline-recording-regression.js','runtime-lifecycle.js']){
    const result=cp.spawnSync(process.execPath,[path.join(tests,name)],{stdio:'inherit',cwd:root});
    if(result.status!==0) process.exit(result.status || 1);
}
for(const name of ['main.js','scene.js','panels/default/index.js']){
    const result=cp.spawnSync(process.execPath,['--check',path.join(root,'dist',name)],{stdio:'inherit'});
    if(result.status!==0) process.exit(result.status || 1);
}
console.log('Timeline package verification: PASS');
