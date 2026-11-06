// Port técnico de Zhana; fixtures locales sin navegador ni proveedor.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {WebSocket}=require('ws');
const {SpokenControls,SPOKEN_TOOLS}=require('../service/spoken-controls.cjs');
const {GeminiLive}=require('../service/gemini-live.cjs');
const tick=()=>new Promise(r=>setImmediate(r));
function fixture(graceMs=1000){
 const record={id:'original',state:'connected'},session={closed:false,stats:{outputTurns:0,outputBytes:0}};
 const live={callId:record.id,session,output:Promise.resolve(),nativeId:'native',id:'session',epoch:0};
 const ended=[];const manager={active:record,liveController:{active:live},driver:{livePlayback:async()=>({playing:false,endedAt:1})},requestEnd:async r=>ended.push(r.id)};
 return{record,session,live,manager,ended,controls:new SpokenControls(manager,{graceMs})};
}
test('A1 intermediate provider turn cannot close; final audio waits for its output queue',async t=>{
 const f=fixture();let socket;
 class Socket extends EventEmitter{constructor(){super();socket=this;this.readyState=WebSocket.OPEN;this.bufferedAmount=0;queueMicrotask(()=>this.emit('open'));}send(raw){if(JSON.parse(raw).setup)queueMicrotask(()=>this.emit('message',Buffer.from('{"setupComplete":{}}')));}close(){}terminate(){}}
 const live=new GeminiLive({model:'models/fixture-live',key:'fixture',Socket,onAudio(){},onFailure(){},onTurn:()=>f.controls.turnComplete(f.record)});f.live.session=live;t.after(()=>{f.controls.cancel(f.record.id);live.close();});await live.connect();
 await f.controls.execute(f.record,{action:'hangup'});
 const emit=status=>socket.emit('message',Buffer.from(JSON.stringify({serverContent:{modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm',data:Buffer.alloc(2400).toString('base64')}}]},turnComplete:true,interactionStatus:status}})));
 emit('IN_PROGRESS');await tick();assert.equal(f.ended.length,0);
 let release;f.live.output=new Promise(r=>{release=r;});emit('IDLE');await tick();assert.equal(f.ended.length,0);release();await tick();assert.deepEqual(f.ended,['original']);
});
test('A2 expiry closes the exact recovering call even with suspended audio',async()=>{
 const f=fixture(5);await f.controls.execute(f.record,{action:'hangup'});f.record.state='recovering';f.live.suspended=true;
 await new Promise(r=>setTimeout(r,20));assert.deepEqual(f.ended,['original']);assert.equal(f.controls.pending.size,0);
});
test('A2 expiry never closes a replacement call',async()=>{
 const f=fixture(5);await f.controls.execute(f.record,{action:'hangup'});f.manager.active={id:'replacement',state:'connected'};
 await new Promise(r=>setTimeout(r,20));assert.deepEqual(f.ended,[]);
});
test('A3 cancellation before checkpoint keeps voice and flushes buffered input once',async()=>{
 const f=fixture();const sent=[];let connections=0;
 const live=new GeminiLive({model:'models/fixture-live',key:'fixture',tools:SPOKEN_TOOLS,onAudio(){},onFailure(){},onToolCall:(args,info)=>f.controls.execute(f.record,args,info)});f.live.session=live;
 live.ready=true;live.resumable=true;live.resumeHandle='checkpoint';live.responding=true;live.generationDone=false;
 live.socket={readyState:WebSocket.OPEN,bufferedAmount:0,send:raw=>sent.push(JSON.parse(raw)),close(){},terminate(){}};live.openConnection=async()=>{connections++;};
 await live.handleToolCalls([{id:'voice',name:'controlar_llamada',args:{action:'voice',voice:'Kore'}}]);
 live.send({realtimeInput:{audio:{data:'synthetic',mimeType:'audio/pcm;rate=16000'}}});
 live.toolCancelled.add('voice');live.toolResults.get('voice').controller.abort();
 live.responding=false;live.generationDone=true;live.maybeResume();await tick();
 assert.equal(connections,0);assert.equal(live.voiceName,'Aoede');assert.equal(live.pendingVoiceName,null);assert.equal(live.renewal,null);
 assert.equal(sent.filter(d=>d.realtimeInput?.audio).length,1);live.close();
});
test('A3 cancelling voice preserves a renewal requested independently by provider',async()=>{
 const live=new GeminiLive({model:'models/fixture-live',key:'fixture',onAudio(){},onFailure(){}}),abort=new AbortController();
 live.ready=true;live.resumable=true;live.resumeHandle='checkpoint';live.responding=true;live.generationDone=false;
 live.socket={readyState:WebSocket.OPEN,bufferedAmount:0,send(){},close(){},terminate(){}};
 live.requestVoiceChange('Kore',{signal:abort.signal});live.requestRenewal({timeLeft:'10s'});abort.abort();
 assert.equal(live.pendingVoiceName,null);assert.equal(live.voiceName,'Aoede');assert.equal(live.renewal.reason,'provider');live.close();
});

test('H1 aborted playback drain can observe a later recovered turn',async t=>{
 for(const mode of ['discarded','suspended','error']) {
  const f=fixture();t.after(()=>f.controls.cancel(f.record.id));
  await f.controls.execute(f.record,{action:'hangup'});
  f.session.stats.outputTurns=1;f.session.stats.outputBytes=2400;
  f.manager.driver.livePlayback=async()=>{if(mode==='error')throw Error('synthetic');if(mode==='suspended')f.live.suspended=true;return {discarded:true};};
  f.controls.turnComplete(f.record);await tick();
  assert.equal(f.controls.pending.get(f.record.id).draining,false);
  f.live.suspended=false;f.manager.driver.livePlayback=async()=>({playing:false,endedAt:2});
  f.session.stats.outputTurns++;f.controls.turnComplete(f.record);await tick();assert.deepEqual(f.ended,['original']);
 }
});
test('H7 asking for active voice cancels only a deferred switch and preserves provider renewal',()=>{
 for(const provider of [false,true]){
  const live=new GeminiLive({model:'models/fixture-live',key:'fixture',onAudio(){},onFailure(){}});
  live.ready=true;live.resumable=true;live.resumeHandle='checkpoint';live.responding=true;live.generationDone=false;
  live.socket={readyState:WebSocket.OPEN,bufferedAmount:0,send(){},close(){},terminate(){}};
  live.requestVoiceChange('Kore');if(provider)live.requestRenewal({timeLeft:'10s'});
  assert.equal(live.requestVoiceChange('Aoede').unchanged,true);
  assert.equal(live.pendingVoiceName,null);assert.equal(live.voiceName,'Aoede');
  assert.equal(live.renewal?.reason,provider?'provider':undefined);live.close();
 }
});
test('H7 cannot report unchanged while a submitted voice switch is connecting',()=>{
 const live=new GeminiLive({model:'models/fixture-live',key:'fixture',onAudio(){},onFailure(){}});
 live.pendingVoiceChange={started:true};assert.equal(live.requestVoiceChange('Aoede').success,false);live.pendingVoiceChange=null;live.close();
});
