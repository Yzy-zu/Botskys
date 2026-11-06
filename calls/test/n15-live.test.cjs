// Port técnico de Zhana; fixtures locales sin navegador ni proveedor.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { WebSocket } = require('ws');
const { GeminiLive } = require('../service/gemini-live.cjs');
const { AVATAR_TOOLS } = require('../service/avatar-tools.cjs');
async function fixture(t, onToolCall) {
  let socket, cuts=0, bytes=0; const completed=[];
  class Socket extends EventEmitter {
    constructor() { super(); socket=this; this.readyState=WebSocket.OPEN; this.bufferedAmount=0; this.sent=[]; queueMicrotask(()=>this.emit('open')); }
    send(raw) { const data=JSON.parse(raw); this.sent.push(data); if(data.setup) queueMicrotask(()=>this.emit('message',Buffer.from('{"setupComplete":{}}'))); }
    close() { this.readyState=WebSocket.CLOSED; } terminate() {}
  }
  const live=new GeminiLive({model:'models/fixture-live',key:'fixture',Socket,groupVoice:true,interruptOnSpeech:true,tools:AVATAR_TOOLS,onToolCall,
    onInterrupted:()=>cuts++,onAudio:data=>bytes+=data.length,onGenerationComplete:token=>completed.push(token)});
  await live.connect(); t.after(()=>live.close());
  return { live, socket, completed, get cuts(){return cuts;},get bytes(){return bytes;},emit:data=>socket.emit('message',Buffer.from(JSON.stringify({serverContent:data}))) };
}
const audio={modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm;rate=24000',data:Buffer.alloc(2400).toString('base64')}}]}};
async function authorize(f,id='auth') {
  f.emit({inputTranscription:{text:'Botsky, responde'}});
  await f.live.handleToolCalls([{id,name:'autorizar_turno',args:{addressed:true}}]);
}
test('N15 fresh group input cuts admitted playback once; late provider interruption cannot erase the new answer',async t=>{
  const f=await fixture(t); await authorize(f); f.emit(audio); assert.equal(f.bytes,2400);
  const old=f.live.voiceGate.token(); f.live.audio(Buffer.alloc(1920));
  assert.equal(f.cuts,1); assert.equal(f.live.isOutputCurrent(old),false); f.emit(audio); assert.equal(f.bytes,2400);
  f.live.endAudio(); await authorize(f,'new'); f.emit(audio); assert.equal(f.bytes,4800);
  f.emit({interrupted:true,generationComplete:true}); assert.equal(f.cuts,1); assert.equal(f.live.voiceGate.allowed,true);
  assert.equal(f.live.responding,true); f.emit({turnComplete:true});
  assert.equal(f.live.voiceGate.allowed,true); assert.equal(f.completed.length,0);
  f.emit(audio); assert.equal(f.bytes,7200);
  f.emit({generationComplete:true,turnComplete:true}); assert.equal(f.live.voiceGate.allowed,false); assert.equal(f.completed.length,1);
});
test('N15 provider-only interruption revokes turn/tools and does not permit late PCM',async t=>{
  let entered,release,signal; const started=new Promise(r=>entered=r),pending=new Promise(r=>release=r);
  const f=await fixture(t,async(_args,info)=>{ signal=info.signal; entered(); await pending; return {success:true}; });
  await authorize(f); f.emit(audio);
  const tool=f.live.handleToolCalls([{id:'pending',name:'controlar_avatar',args:{action:'gesture',name:'wave'}}]); await started;
  f.emit({interrupted:true}); assert.equal(signal.aborted,true); assert.equal(f.live.voiceGate.allowed,false);
  f.emit(audio); assert.equal(f.bytes,2400); release(); await tool;
  assert.equal(f.socket.sent.some(x=>x.toolResponse?.functionResponses[0].id==='pending'),false);
});
test('N15 final turnComplete observes drain even without generationComplete and opens the spoken question',async t=>{
  const f=await fixture(t); await authorize(f);
  await f.live.handleToolCalls([{id:'question',name:'dejar_pregunta',args:{question:'¿Cuál prefieres?'}}]);
  f.emit({outputTranscription:{text:'¿Cuál prefieres?'}}); f.emit(audio); f.emit({turnComplete:true});
  assert.equal(f.completed.length,1); assert.equal(f.live.voiceGate.pendingQuestion,null);
  f.live.outputCompleted(f.completed[0],Date.now()); assert.ok(f.live.voiceGate.pendingQuestion);
  f.emit({generationComplete:true}); // no second playback watcher for the same generation
  assert.equal(f.completed.length,1);
});
test('N15 explicit silence aborts pending visual work and keeps the gate closed',async t=>{
  let entered,release,signal; const started=new Promise(r=>entered=r),pending=new Promise(r=>release=r);
  const f=await fixture(t,async(_args,info)=>{signal=info.signal;entered();await pending;return {success:true};});
  const tool=f.live.handleToolCalls([{id:'visual',name:'controlar_avatar',args:{action:'blush',name:'soft'}}]); await started;
  f.live.silence(); assert.equal(signal.aborted,true); assert.equal(f.live.voiceGate.allowed,false);
  release();await tool;f.emit(audio);assert.equal(f.bytes,0);
});
