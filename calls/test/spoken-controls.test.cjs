// Port técnico de Zhana; fixtures locales sin navegador ni proveedor.
'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const { SpokenControls, SPOKEN_TOOLS } = require('../service/spoken-controls.cjs');
const { GeminiLive } = require('../service/gemini-live.cjs');
const { EventEmitter } = require('node:events');
const { WebSocket } = require('ws');
function fixture() {
 const record = { id: 'call-a', state: 'connected', volume: 0.7 };
 const session = { stats: { outputTurns: 0, outputBytes: 0 }, requestVoiceChange: voice => ({success:true,pending:true,voice}) };
 const live = { callId:record.id, session, output:Promise.resolve(), nativeId:'native-a', id:'session-a', epoch:0 };
 const ended=[], volumes=[];
 const manager={ active:record, liveController:{active:live}, driver:{livePlayback:async()=>({playing:false,endedAt:1})}, requestEnd:async(r,reason)=>{ended.push([r.id,reason]);}, setVolume:async({callId,volume})=>{volumes.push([callId,volume]);record.volume=volume;} };
 return {record,session,live,manager,ended,volumes,controls:new SpokenControls(manager)};
}
test('spoken controls close only after farewell audio queue and browser playback drain', async()=>{
 const f=fixture(); let release; f.live.output=new Promise(r=>{release=r;});
 assert.equal((await f.controls.execute(f.record,{action:'hangup'})).pending,true);
 f.session.stats.outputTurns++; f.session.stats.outputBytes=2400; f.controls.turnComplete(f.record);
 await new Promise(r=>setImmediate(r)); assert.equal(f.ended.length,0);
 release(); await new Promise(r=>setImmediate(r)); assert.deepEqual(f.ended,[['call-a','spoken_goodbye']]);
});
test('spoken controls reject stale or group sessions and cannot close a later call',async()=>{
 const f=fixture(); const signal=new AbortController();
 await f.controls.execute(f.record,{action:'hangup'},{signal:signal.signal});
 signal.abort(); assert.equal(f.controls.pending.size,0);
 f.record.groupId='group'; assert.equal((await f.controls.execute(f.record,{action:'volume',direction:'up'})).success,false);delete f.record.groupId;
 await f.controls.execute(f.record,{action:'hangup'});f.manager.active={id:'later',state:'connected'};
 await f.controls.finish(f.controls.pending.get(f.record.id));assert.equal(f.ended.length,0);
});
test('keep_call cancels the existing goodbye timer and does not end the call later',async()=>{
 const f=fixture();const controls=new SpokenControls(f.manager,{graceMs:5});
 await controls.execute(f.record,{action:'hangup'});assert.equal(controls.pending.size,1);
 await controls.execute(f.record,{action:'keep_call'});assert.equal(controls.pending.size,0);
 await new Promise(r=>setTimeout(r,20));assert.deepEqual(f.ended,[]);
});
test('volume is bounded, persisted by manager and closed arguments cannot redirect calls',async()=>{
 const f=fixture();await f.controls.execute(f.record,{action:'volume',direction:'up'});assert.ok(Math.abs(f.record.volume-.85)<1e-9);
 await f.controls.execute(f.record,{action:'volume',value:.1});await f.controls.execute(f.record,{action:'volume',direction:'down'});assert.equal(f.record.volume,.1);
 assert.equal((await f.controls.execute(f.record,{action:'volume',value:2})).success,false);
 assert.equal((await f.controls.execute(f.record,{action:'hangup',callId:'later'})).success,false);
 await f.controls.execute(f.record,{action:'hangup'});await f.controls.execute(f.record,{action:'keep_call'});assert.equal(f.controls.pending.size,0);
 assert.equal((await f.controls.execute(f.record,{action:'voice',voice:'Kore'})).pending,true);
 assert.equal((await f.controls.execute(f.record,{action:'voice',voice:'clone'})).success,false);
});
test('Live voice switch resumes with chosen setup, same checkpoint and no implicit fallback',async t=>{
 const sockets=[];let fail;
 class Socket extends EventEmitter { constructor(){ super();this.readyState=WebSocket.OPEN;this.bufferedAmount=0;this.sent=[];sockets.push(this);queueMicrotask(()=>this.emit('open')); } send(raw){ const d=JSON.parse(raw);this.sent.push(d);if(d.setup)queueMicrotask(()=>this.emit('message',Buffer.from('{"setupComplete":{}}'))); } close(){} terminate(){} }
 const live=new GeminiLive({model:'models/fixture-live',key:'fixture',Socket,tools:SPOKEN_TOOLS,onAudio(){},onFailure:e=>{fail=e;},onToolCall:args=>live.requestVoiceChange(args.voice)});t.after(()=>live.close());
 await live.connect();assert.equal(live.requestVoiceChange('Kore').success,false);
 live.resumable=true;live.resumeHandle='checkpoint';
 await live.handleToolCalls([{id:'voice-1',name:'controlar_llamada',args:{action:'voice',voice:'Kore'}}]);
 for(let i=0;i<50&&live.stats.connections!==2;i++)await new Promise(r=>setTimeout(r,2));
 assert.equal(live.stats.connections,2);assert.equal(live.voiceName,'Kore');assert.equal(live.stats.voiceChanges,1);assert.equal(fail,undefined);
 assert.equal(sockets[1].sent[0].setup.sessionResumption.handle,'checkpoint');
 assert.equal(sockets[1].sent[0].setup.generationConfig.speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName,'Kore');
 assert.ok(sockets[0].sent.some(d=>d.toolResponse));
 live.renewalTimes=[Date.now(),Date.now()];assert.equal(live.requestVoiceChange('Zephyr').success,false);assert.equal(sockets.length,2);
});
test('Live de-duplicates volume tool calls and cancellation disarms pending goodbye',async()=>{
 const f=fixture();const live=new GeminiLive({model:'models/fixture-live',key:'fixture',tools:SPOKEN_TOOLS,onAudio(){},onFailure(){},onToolCall:(args,info)=>f.controls.execute(f.record,args,info)});
 f.session=live;f.live.session=live;live.ready=true;live.socket={readyState:WebSocket.OPEN,bufferedAmount:0,send(){},close(){},terminate(){}};
 const call={id:'same',name:'controlar_llamada',args:{action:'volume',direction:'up'}};
 await live.handleToolCalls([call]);await live.handleToolCalls([call]);assert.equal(f.volumes.length,1);
 await live.handleToolCalls([{id:'mixed1',name:'controlar_llamada',args:{action:'volume',direction:'up'}},{id:'mixed2',name:'controlar_llamada',args:{action:'hangup'}}]);assert.equal(f.volumes.length,1);assert.equal(f.controls.pending.size,0);
 await live.handleToolCalls([{id:'bye',name:'controlar_llamada',args:{action:'hangup'}}]);
 live.toolResults.get('bye').controller.abort();assert.equal(f.controls.pending.size,0);live.close();
});

test('H8 volume reports actual endpoints with stable decimal steps',async()=>{
 const f=fixture();
 let result=await f.controls.execute(f.record,{action:'volume',value:.7});assert.equal(result.atLimit,false);
 result=await f.controls.execute(f.record,{action:'volume',direction:'up'});assert.equal(result.volume,.85);assert.equal(result.atLimit,false);
 result=await f.controls.execute(f.record,{action:'volume',direction:'up'});assert.equal(result.volume,1);assert.equal(result.atLimit,true);
 result=await f.controls.execute(f.record,{action:'volume',value:.1});assert.equal(result.atLimit,true);
});
