// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { FeatureControls } = require('../service/feature-controls.cjs');
const { reportSnapshot, Operations } = require('../service/operations.cjs');

async function controls(t, base) {
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'botsky-controls-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
 const args={file:path.join(dir,'features.json'),base};const store=new FeatureControls(args);await store.init();return {dir,args,store};
}
test('PM11: feature rollback persists, composes concurrent edits and cannot enable environment-disabled functions', async t => {
 const {args,store}=await controls(t,{incoming:false});
 await Promise.all([store.update({outgoing:false}),store.update({agenda:false})]);
 const restarted=new FeatureControls(args);await restarted.init();
 assert.equal(restarted.value.outgoing,false);assert.equal(restarted.value.agenda,false);assert.equal(restarted.value.live,true);
 await assert.rejects(restarted.update({incoming:true}),{code:'FEATURE_NOT_CONFIGURED'});
 for(const patch of [{live:'false'},{targetJid:'other'},[],{}])await assert.rejects(restarted.update(patch),{code:'INVALID_FEATURE_CONTROLS'});
 assert.equal((await fs.stat(args.file)).mode&0o777,0o600);
});
test('PM11: failed persistence does not publish feature changes and corrupt controls fail closed', async t => {
 const {dir,args,store}=await controls(t);
 store.file=dir;await assert.rejects(store.update({outgoing:false}));assert.equal(store.value.outgoing,true);
 await fs.writeFile(args.file,'{"version":1,"overrides":{"outgoing":"false"}}');
 await assert.rejects(new FeatureControls(args).init(),{code:'FEATURE_CONTROLS_INVALID'});
});
function manager() {
 return {state:'ready',featureEnabled:()=>true,journal:{records:[
  {id:'private-call-id',key:'private-key',targetJid:'525511112222@s.whatsapp.net',groupName:'SECRET GROUP',sourceReceipt:{messageKey:{id:'secret-message'}},state:'ended',reason:'remote_or_native_end',requestedAt:1000,startedAt:1200,connectedAt:2000,endedAt:5000,usage:{inputAudioSeconds:60,modelOutputAudioSeconds:20,bridgeAcceptedAudioSeconds:18,firstAudioLatencyMs:100}},
  {state:'failed',reason:'AIzaSecretKeyWithoutSpaces',requestedAt:1000}
 ]},active:null,observed:null,lastSuccessfulPollAt:6000,audioRuntime:{armed:false,liveTracks:0},
 agenda:{ready:true,policy:{enabled:true},rows:[{status:'pending',targetJid:'secret-destination'}],reservedKeys:{'secret-key':true}},clock:{now:()=>6000}};
}
test('PM11: report exposes aggregate measurements and never identifiers, content or arbitrary error strings', () => {
 const report=reportSnapshot({manager:manager(),now:6000});const serialized=JSON.stringify(report);
 assert.equal(report.ready,true);assert.equal(report.history.calls,2);assert.equal(report.history.reasons.OTHER,1);
 assert.equal(report.health.idleMediaReleased,true);assert.equal(report.latencies.dial.medianMs,200);
 assert.equal(report.usage.inputAudioSeconds,60);assert.equal(report.usage.billingCost,null);
 assert.doesNotMatch(serialized,/private-call-id|private-key|525511112222|SECRET GROUP|secret-message|AIza|secret-destination|secret-key/);
});
test('PM11: detects stale observation, idle audio and low disk without attempting repair or making a call', () => {
 const m=manager();m.audioRuntime.armed=true;m.lastSuccessfulPollAt=1;
 const report=reportSnapshot({manager:m,now:20000,storage:{availableBytes:1}});
 assert.deepEqual(report.health.warnings,['IDLE_MEDIA_PRESENT','OBSERVATION_DELAYED','LOW_DISK_SPACE']);
 m.agenda.ready=false;assert.equal(reportSnapshot({manager:m,now:20000}).ready,false);
});
test('PM11: resource observation counts audio files and temporary jobs without reading or deleting their content', async t => {
 const {dir}=await controls(t);const audioDir=path.join(dir,'audio');await fs.mkdir(path.join(audioDir,'tmp'),{recursive:true});
 const file=path.join(audioDir,'a'.repeat(64)+'.wav');await fs.writeFile(file,'private audio content');
 await fs.mkdir(path.join(audioDir,'tmp/job-private'));
 const operations=new Operations({manager:manager(),privateDir:dir,runtime:{records:[]},audioStore:{dir:audioDir,jobs:new Set(),busy:false}});
 const report=await operations.report();assert.equal(report.storage.audioFiles,1);assert.equal(report.storage.tempJobs,1);
 assert.ok(report.resources.rssBytes>0);assert.equal(await fs.readFile(file,'utf8'),'private audio content');
 assert.doesNotMatch(JSON.stringify(report),/private audio content|job-private/);
});

test('LIVE-2C: live renewal evidence is a numeric aggregate without session or key identifiers',()=>{
 const m=manager();m.active={state:'connected',requestedAt:1000,live:true};
 m.liveController={status:()=>({renewals:2,inputSeconds:1,outputSeconds:3,bridgeAcceptedSeconds:3,receivedSpeechFrames:4,resumeHandle:'private-resume-token',key:'private-key'})};
 const report=reportSnapshot({manager:m,now:6000});assert.equal(report.current.liveUsage.connectionRenewals,2);
 assert.doesNotMatch(JSON.stringify(report),/private-resume-token|private-key/);
});
