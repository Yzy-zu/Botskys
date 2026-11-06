'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { startConfigured } = require('../main.cjs');
const owner = '525511112222@s.whatsapp.net';
const account = '525544445555@s.whatsapp.net';
function options(root) {
  return {projectRoot:root,token:'a'.repeat(64),port:0,executable:'/synthetic/browser',allowBrowserLaunch:true,agendaTimers:false,
    live:{key:'single-synthetic-key',model:'explicit-synthetic-model'},
    document:{version:1,instance:'synthetic',account,epoch:1,owner,actors:[owner],privateChats:[owner],groups:[],
      features:{agenda:false,incoming:false,live:true,outgoing:true},schedule:{timeZone:'America/Mexico_City',startHour:8,endHour:23}}};
}
function factories(events) {
  return {assets:async()=>null,
    runtime:privateDir=>({privateDir,env:()=>({}),async start(){events.push('runtime-start');},async stop(){events.push('runtime-stop');}}),
    driver:({privateDir})=>({privateDir,async verifyAccount(expected){events.push('verify');return expected===account;},
      async start(){events.push('browser-start');},async close(){events.push('browser-close');},async snapshot(){return {active:false};}})};
}
test('configured composition starts own runtime before verified driver and releases both on close',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'botsky-config-start-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const events=[], service=await startConfigured(options(root),factories(events));
  t.after(()=>service.close());
  assert.ok(events.indexOf('runtime-start')<events.indexOf('browser-start'));
  assert.ok(events.includes('verify'));
  assert.equal(service.manager.state,'ready');
  let response=await fetch(service.url+'/v1/status',{headers:{Authorization:'Bearer '+'a'.repeat(64)}});
  assert.equal((await response.json()).policyRevision,service.policy.revision);
  response=await fetch(service.url+'/v1/qr',{headers:{Authorization:'Bearer '+'a'.repeat(64)}});
  assert.equal(response.status,403);
  await service.close();
  assert.ok(events.includes('runtime-stop'));
  await assert.rejects(fs.access(path.join(root,'private/calls/service.lock')),{code:'ENOENT'});
});
test('unauthorized browser and multi-key Live are rejected before runtime or storage',async()=>{
  let touched=false;
  const f={runtime(){touched=true;throw Error('unexpected');}};
  const opts=options('/does-not-exist/botsky');
  opts.allowBrowserLaunch=false;
  await assert.rejects(()=>startConfigured(opts,f),/BROWSER_NOT_AUTHORIZED/);
  opts.allowBrowserLaunch=true;opts.live.keys=['forbidden-pool'];
  await assert.rejects(()=>startConfigured(opts,f),/CALLS_EXPLICIT_LIVE_REQUIRED/);
  assert.equal(touched,false);
});
test('runtime startup failure closes owned resources and releases lock',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'botsky-config-fail-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const events=[], f=factories(events), original=f.runtime;
  f.runtime=dir=>({...original(dir),async start(){events.push('runtime-start');throw Error('synthetic runtime failure');}});
  await assert.rejects(()=>startConfigured(options(root),f),/synthetic runtime failure/);
  assert.ok(events.includes('runtime-stop'));
  assert.ok(!events.includes('browser-start'));
  await assert.rejects(fs.access(path.join(root,'private/calls/service.lock')),{code:'ENOENT'});
});
test('real CLI rejects disabled browser and oversized pipe without touching a profile',async t=>{
  const {spawnSync}=require('node:child_process');
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'botsky-main-pipe-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const o=options(path.join(root,'not-created'));o.allowBrowserLaunch=false;
  for(const input of [JSON.stringify(o),Buffer.alloc(70000,32)]){
    const result=spawnSync(process.execPath,[path.join(__dirname,'../main.cjs'),'--run'],{input,timeout:10000});
    assert.equal(result.status,1);assert.equal(String(result.stdout),'');
    assert.match(String(result.stderr),/CALLS_STARTUP_FAILED/);
  }
  await assert.rejects(fs.access(o.projectRoot),{code:'ENOENT'});
});
