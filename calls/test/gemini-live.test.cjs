// Port técnico de Zhana; fixtures locales sin navegador ni proveedor.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { WebSocket, WebSocketServer } = require('ws');
const { GeminiLive, LIVE_SYSTEM } = require('../service/gemini-live.cjs');

test('Live protocol authenticates server-side and exchanges PCM without exposing transcripts', async t => {
  const server = new WebSocketServer({ port: 0, host: '127.0.0.1' });
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => { for (const client of server.clients) client.terminate(); server.close(); });
  const received = []; let auth, outputs = 0, turns = 0;
  server.on('connection', (ws, request) => {
    auth = request.headers['x-goog-api-key'];
    ws.on('message', data => {
      const m = JSON.parse(data); received.push(m);
      if (m.setup) ws.send(JSON.stringify({ setupComplete: {} }));
      if (m.clientContent) {
        ws.send(JSON.stringify({ serverContent: { inputTranscription: { text: 'private fixture' }, modelTurn: { parts: [{ inlineData: { mimeType: 'audio/pcm;rate=24000', data: Buffer.alloc(2400).toString('base64') } }] }, turnComplete: true } }));
      }
    });
  });
  const Socket = function(_url, options) { return new WebSocket(`ws://127.0.0.1:${server.address().port}`, options); };
  let complete;
  const done = new Promise(resolve => { complete = resolve; });
  const activity = [];
  const live = new GeminiLive({model:'models/fixture-live', key: 'fixture-secret', Socket, onActivity: state => activity.push(state), onAudio: b => { outputs += b.length; }, onTurn: () => { turns++; complete(); } });
  t.after(() => live.close());
  await live.connect(); live.audio(Buffer.alloc(1920)); live.greet(); await done;
  assert.equal(auth, 'fixture-secret'); assert.equal(outputs, 2400); assert.equal(turns, 1);
  assert.ok(activity.includes('thinking')); assert.ok(activity.includes('speaking')); assert.equal(activity.at(-1), 'listening');
  assert.equal(received[0].setup.generationConfig.speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName, 'Aoede');
  assert.match(received[0].setup.systemInstruction.parts[0].text, /español claro/);
  assert.equal(received[0].setup.realtimeInputConfig.activityHandling, 'NO_INTERRUPTION');
  assert.equal(received[1].realtimeInput.audio.mimeType, 'audio/pcm;rate=16000');
  assert.equal(JSON.stringify(live.stats).includes('private fixture'), false);
  assert.equal(received[0].setup.tools, undefined);
  assert.match(LIVE_SYSTEM, /nunca decides comandos de chat/);
});

test('Group interruption is opt-in and discards audio bundled with the provider interruption', async t => {
  const { EventEmitter } = require('node:events');
  let socket;
  class Socket extends EventEmitter {
    constructor() { super(); this.readyState = WebSocket.OPEN; this.bufferedAmount = 0; this.sent = []; socket = this; queueMicrotask(() => this.emit('open')); }
    send(raw) { const message = JSON.parse(raw); this.sent.push(message); if (message.setup) queueMicrotask(() => this.emit('message', Buffer.from('{"setupComplete":{}}'))); }
    close() { this.readyState = WebSocket.CLOSED; }
    terminate() {}
  }
  let interrupted = 0, bytes = 0;
  const live = new GeminiLive({model:'models/fixture-live', key: 'fixture-secret', Socket, interruptOnSpeech: true,
    onInterrupted: () => { interrupted++; }, onAudio: data => { bytes += data.length; } });
  t.after(() => live.close());
  await live.connect();
  assert.equal(socket.sent[0].setup.realtimeInputConfig.activityHandling, 'START_OF_ACTIVITY_INTERRUPTS');
  const audio = { modelTurn: { parts: [{ inlineData: { mimeType: 'audio/pcm;rate=24000', data: Buffer.alloc(2400).toString('base64') } }] } };
  socket.emit('message', Buffer.from(JSON.stringify({ serverContent: audio })));
  assert.equal(bytes, 2400);
  socket.emit('message', Buffer.from(JSON.stringify({ serverContent: { ...audio, interrupted: true } })));
  assert.equal(interrupted, 1);
  assert.equal(bytes, 2400);
  assert.equal(live.activityState, 'listening');
});

test('Live rejects a provider setup error without leaking the error body or key', async t => {
  const server = new WebSocketServer({ port: 0, host: '127.0.0.1' });
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => { for (const client of server.clients) client.terminate(); server.close(); });
  server.on('connection', ws => ws.on('message', () => ws.send(JSON.stringify({ error: { message: 'sensitive details' } }))));
  const Socket = function(_url, options) { return new WebSocket(`ws://127.0.0.1:${server.address().port}`, options); };
  const live = new GeminiLive({model:'models/fixture-live', key: 'fixture-secret', Socket, onAudio: () => {} });
  t.after(() => live.close());
  await assert.rejects(live.connect(), error => error.code === 'LIVE_PROVIDER_ERROR' && !error.message.includes('sensitive'));
});

test('Group PCM stays closed until a current named intervention is semantically authorized and resets for the next input', async t => {
 const {EventEmitter}=require('node:events');let socket;
 class Socket extends EventEmitter {
  constructor(){super();this.readyState=WebSocket.OPEN;this.bufferedAmount=0;this.sent=[];socket=this;queueMicrotask(()=>this.emit('open'));}
  send(raw){const m=JSON.parse(raw);this.sent.push(m);if(m.setup)queueMicrotask(()=>this.emit('message',Buffer.from('{"setupComplete":{}}')));}
  close(){this.readyState=WebSocket.CLOSED;}terminate(){}
 }
 let bytes=0;const live=new GeminiLive({model:'models/fixture-live',key:'fake',Socket,groupVoice:true,onAudio:b=>{bytes+=b.length;}});
 t.after(()=>live.close());await live.connect();
 assert.equal(socket.sent[0].setup.tools.at(-1).functionDeclarations[0].name,'autorizar_turno');
 const emit=m=>socket.emit('message',Buffer.from(JSON.stringify(m)));
 const audio={serverContent:{modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm;rate=24000',data:Buffer.alloc(2400).toString('base64')}}]}}};
 live.audio(Buffer.alloc(1280));live.endAudio();emit(audio);assert.equal(bytes,0);
 const decision=live.handleToolCalls([{id:'first',name:'autorizar_turno',args:{addressed:true}}]);
 emit({serverContent:{inputTranscription:{text:'Botsky, ayúdanos.'}}});await decision;
 emit(audio);assert.equal(bytes,2400);
 live.audio(Buffer.alloc(1280));live.endAudio();emit(audio);assert.equal(bytes,2400);
 emit({serverContent:{inputTranscription:{text:'Ayer Botsky nos contó algo.'}}});
 await live.handleToolCalls([{id:'incidental',name:'autorizar_turno',args:{addressed:false}}]);
 emit(audio);assert.equal(bytes,2400);
 await live.handleToolCalls([{id:'first',name:'autorizar_turno',args:{addressed:true}}]);
 assert.equal(socket.sent.at(-1).toolResponse.functionResponses[0].response.allowVoice,false);
 emit(audio);assert.equal(bytes,2400); // A duplicate old decision cannot reopen this intervention.
 live.greet();emit(audio);assert.equal(bytes,4800);
 emit({serverContent:{turnComplete:true}});emit(audio);assert.equal(bytes,4800);
});

test('LIVE-1: native setup uses natural-length answers and explicit silence drops late audio until the next voice turn', async t => {
 const {EventEmitter}=require('node:events');let socket;
 class Socket extends EventEmitter {
  constructor(){super();this.readyState=WebSocket.OPEN;this.bufferedAmount=0;this.sent=[];socket=this;queueMicrotask(()=>this.emit('open'));}
  send(data){const item=JSON.parse(data);this.sent.push(item);if(item.setup)queueMicrotask(()=>this.emit('message',Buffer.from(JSON.stringify({setupComplete:{}}))));}
  close(){this.readyState=WebSocket.CLOSED;}terminate(){}
 }
 let bytes=0;const live=new GeminiLive({model:'models/fixture-live',key:'fake',Socket,onAudio:data=>{bytes+=data.length;}});t.after(()=>live.close());await live.connect();
 assert.equal(socket.sent[0].setup.generationConfig.maxOutputTokens,undefined);
 assert.doesNotMatch(socket.sent[0].setup.systemInstruction.parts[0].text,/UNA frase breve|No hagas monólogos en esta prueba/);
 const emit=content=>socket.emit('message',Buffer.from(JSON.stringify({serverContent:content})));
 const audio={modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm;rate=24000',data:Buffer.alloc(2400).toString('base64')}}]}};
 live.greet({liveRequest:'Hablen sobre fútbol'});assert.match(socket.sent.at(-1).clientContent.turns[0].parts[0].text,/Hablen sobre fútbol/);
 emit(audio);assert.equal(bytes,2400);live.silence();assert.equal(socket.sent.at(-1).clientContent.turnComplete,false);
 emit(audio);emit({turnComplete:true,interactionStatus:'IN_PROGRESS'});emit(audio);assert.equal(bytes,2400);
 emit({turnComplete:true,interactionStatus:'IDLE'});emit(audio);assert.equal(bytes,2400);
 live.audio(Buffer.alloc(1920));live.endAudio();emit(audio);assert.equal(bytes,4800);
});

test('LIVE-1: silence received while idle does not wait forever for a nonexistent old turn',async t=>{
 const {EventEmitter}=require('node:events');let socket;
 class Socket extends EventEmitter {
  constructor(){super();this.readyState=WebSocket.OPEN;this.bufferedAmount=0;socket=this;queueMicrotask(()=>this.emit('open'));}
  send(data){if(JSON.parse(data).setup)queueMicrotask(()=>this.emit('message',Buffer.from('{"setupComplete":{}}')));}
  close(){this.readyState=WebSocket.CLOSED;}terminate(){}
 }
 let heard=0;const live=new GeminiLive({model:'models/fixture-live',key:'fake',Socket,onAudio:()=>heard++});t.after(()=>live.close());await live.connect();
 live.silence();live.audio(Buffer.alloc(1920));
 socket.emit('message',Buffer.from(JSON.stringify({serverContent:{modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm',data:Buffer.alloc(2400).toString('base64')}}]}}})));
 assert.equal(heard,1);
});

async function renewalFixture(t, { holdResume = false } = {}) {
 const server=new WebSocketServer({port:0,host:'127.0.0.1'});await new Promise(r=>server.once('listening',r));
 const sockets=[],messages=[],failures=[],audio=[];
 server.on('connection',(ws,req)=>{
  const index=sockets.push(ws)-1;messages[index]=[];ws.auth=req.headers['x-goog-api-key'];
  ws.on('message',raw=>{const data=JSON.parse(raw);messages[index].push(data);if(data.setup&&(!index||!holdResume))ws.send('{"setupComplete":{}}');});
 });
 const Socket=function(_url,options){return new WebSocket(`ws://127.0.0.1:${server.address().port}`,options);};
 const live=new GeminiLive({model:'models/fixture-live',key:'fixture-private-key',Socket,onAudio:b=>audio.push(b),onFailure:e=>failures.push(e)});
 t.after(()=>{live.close();for(const socket of server.clients)socket.terminate();server.close();});
 await live.connect();
 const until=async predicate=>{for(let i=0;i<200;i++){if(predicate())return;await new Promise(r=>setTimeout(r,5));}assert.fail('Live transition did not complete');};
 const send=(index,message)=>sockets[index].send(JSON.stringify(message));
 return {live,sockets,messages,failures,audio,until,send};
}

test('LIVE-2: GoAway waits for a safe checkpoint, resumes the same session and flushes input once',async t=>{
 const f=await renewalFixture(t,{holdResume:true}),{live}=f;
 const activity=[];live.onActivity=state=>activity.push(state);
 live.greet({liveRequest:'Platiquen sobre astronomía'});await f.until(()=>f.messages[0].length===2);
 f.send(0,{sessionResumptionUpdate:{resumable:false,newHandle:''},goAway:{timeLeft:'15s'}});
 await f.until(()=>!!live.renewal);live.audio(Buffer.alloc(1920));live.endAudio();
 assert.equal(f.sockets.length,1);assert.equal(f.messages[0].length,2);
 f.send(0,{serverContent:{turnComplete:true,interactionStatus:'IDLE'},sessionResumptionUpdate:{resumable:true,newHandle:'opaque-checkpoint'}});
 await f.until(()=>f.messages[1]?.[0]?.setup);assert.deepEqual(f.messages[1][0].setup.sessionResumption,{handle:'opaque-checkpoint'});
 assert.equal(activity.at(-1),'reconnecting');
 assert.equal(f.sockets[1].auth,'fixture-private-key');assert.equal(f.messages[1].length,1);
 // Events from the retired socket cannot mutate the successor or replay audio.
 const retired=live.connectionGeneration-1;assert.ok(retired>=1);
 f.send(1,{setupComplete:{}});await f.until(()=>live.stats.renewals===1&&f.messages[1].length===3);
 assert.equal(activity.at(-1),'thinking');
 assert.equal(f.messages[1][1].realtimeInput.audio.mimeType,'audio/pcm;rate=16000');
 assert.equal(f.messages[1][2].realtimeInput.audioStreamEnd,true);
 assert.equal(f.messages.flat().filter(m=>m.clientContent).length,1);assert.equal(live.stats.inputBytes,1920);
 assert.equal(live.stats.connections,2);assert.equal(f.failures.length,0);assert.equal(live.closed,false);
 f.send(1,{serverContent:{modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm;rate=24000',data:Buffer.alloc(2400).toString('base64')}}]}}});
 await f.until(()=>f.audio.length===1);assert.equal(live.stats.outputBytes,2400);
});

test('LIVE-2: an unavailable checkpoint closes cleanly instead of starting a context-free session',async t=>{
 const f=await renewalFixture(t);f.live.greet();f.send(0,{goAway:{timeLeft:'1s'}});
 await f.until(()=>f.failures.length===1);assert.equal(f.failures[0].code,'LIVE_RESUMPTION_UNAVAILABLE');
 assert.equal(f.live.closed,true);assert.equal(f.sockets.length,1);assert.equal(JSON.stringify(f.failures).includes('fixture-private-key'),false);
});

test('LIVE-2: hanging up during resumption cancels setup and cannot resurrect the session',async t=>{
 const f=await renewalFixture(t,{holdResume:true});
 f.send(0,{sessionResumptionUpdate:{resumable:true,newHandle:'private-handle'},goAway:{timeLeft:'15s'}});
 await f.until(()=>f.messages[1]?.[0]?.setup);f.live.audio(Buffer.alloc(1920));f.live.close();
 await new Promise(r=>setTimeout(r,20));assert.equal(f.live.ready,false);assert.equal(f.live.renewal,null);
 assert.equal(f.live.resumeHandle,null);assert.equal(f.failures.length,0);assert.equal(f.messages[1].length,1);
});

test('LIVE-2: unexpected transport loss resumes only a checkpoint covering all sent input',async t=>{
 const f=await renewalFixture(t);
 f.send(0,{sessionResumptionUpdate:{resumable:true,newHandle:'safe-handle'}});await f.until(()=>f.live.resumable);
 f.sockets[0].close();await f.until(()=>f.live.stats.renewals===1);
 assert.equal(f.messages[1][0].setup.sessionResumption.handle,'safe-handle');
 f.live.audio(Buffer.alloc(1920));await f.until(()=>f.messages[1].length===2);
 f.sockets[1].close();await f.until(()=>f.failures.length===1);assert.equal(f.sockets.length,2);
 assert.equal(f.live.closed,true);assert.equal(f.failures[0].code,'LIVE_SOCKET_CLOSED');
});

test('LIVE-2: repeated renewal notices are bounded and do not create parallel successors',async t=>{
 const f=await renewalFixture(t);
 for(let i=0;i<2;i++){
  f.send(i,{sessionResumptionUpdate:{resumable:true,newHandle:'handle-'+i},goAway:{timeLeft:'15s'}});
  await f.until(()=>f.live.stats.renewals===i+1);
 }
 f.send(2,{sessionResumptionUpdate:{resumable:true,newHandle:'handle-2'},goAway:{timeLeft:'15s'}});
 await f.until(()=>f.failures.length===1);assert.equal(f.failures[0].code,'LIVE_RENEWAL_LIMIT');assert.equal(f.sockets.length,3);
});

test('LIVE-2: silence during renewal stays queued and listening continues on the successor',async t=>{
 const f=await renewalFixture(t,{holdResume:true});
 f.send(0,{sessionResumptionUpdate:{resumable:true,newHandle:'safe'},goAway:{timeLeft:'15s'}});
 await f.until(()=>f.messages[1]?.[0]?.setup);f.live.silence();f.live.audio(Buffer.alloc(1920));f.live.endAudio();
 f.send(1,{setupComplete:{}});await f.until(()=>f.messages[1].length===4);
 assert.equal(f.messages[1][1].clientContent.turnComplete,false);assert.ok(f.messages[1][2].realtimeInput.audio);
 assert.equal(f.messages[1][3].realtimeInput.audioStreamEnd,true);assert.equal(f.live.outputMuted,false);assert.equal(f.failures.length,0);
});

test('LIVE-2: an early checkpoint cannot discard pending generation, but completed queued audio can cross renewal',async t=>{
 const f=await renewalFixture(t);f.live.greet();
 f.send(0,{sessionResumptionUpdate:{resumable:true,newHandle:'too-early'},goAway:{timeLeft:'15s'}});
 await f.until(()=>!!f.live.renewal);assert.equal(f.sockets.length,1);
 f.send(0,{serverContent:{modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm',data:Buffer.alloc(2400).toString('base64')}}]},generationComplete:true},sessionResumptionUpdate:{resumable:true,newHandle:'after-generation'}});
 await f.until(()=>f.live.stats.renewals===1);
 assert.equal(f.messages[1][0].setup.sessionResumption.handle,'after-generation');assert.equal(f.audio.length,1);assert.equal(f.failures.length,0);
});

test('LIVE-2: a retained provider handle is usable after generation without requiring a redundant token update',async t=>{
 const f=await renewalFixture(t);f.send(0,{sessionResumptionUpdate:{resumable:true,newHandle:'initial-session-handle'}});
 await f.until(()=>f.live.resumable);f.live.greet();f.send(0,{goAway:{timeLeft:'15s'}});
 await f.until(()=>!!f.live.renewal);assert.equal(f.sockets.length,1);
 f.send(0,{serverContent:{generationComplete:true}});await f.until(()=>f.live.stats.renewals===1);
 assert.equal(f.messages[1][0].setup.sessionResumption.handle,'initial-session-handle');assert.equal(f.failures.length,0);
});

test('LIVE-2: rejected resumption closes and releases buffered input without retrying or losing context silently',async t=>{
 const f=await renewalFixture(t,{holdResume:true});
 f.send(0,{sessionResumptionUpdate:{resumable:true,newHandle:'expired-handle'},goAway:{timeLeft:'15s'}});
 await f.until(()=>f.messages[1]?.[0]?.setup);f.live.audio(Buffer.alloc(1920));
 f.send(1,{error:{message:'sensitive fixture-provider-body'}});await f.until(()=>f.failures.length===1);
 assert.equal(f.failures[0].code,'LIVE_RESUMPTION_FAILED');assert.equal(f.live.closed,true);assert.equal(f.live.renewal,null);
 assert.equal(f.sockets.length,2);assert.equal(f.messages[1].length,1);assert.equal(JSON.stringify(f.failures).includes('sensitive'),false);
});

test('LIVE-2: excessive input while waiting to renew is bounded and shuts down once',async t=>{
 const f=await renewalFixture(t);f.live.greet();f.send(0,{goAway:{timeLeft:'15s'}});await f.until(()=>!!f.live.renewal);
 for(let i=0;i<2000&&!f.live.closed;i++)f.live.audio(Buffer.alloc(1920));
 assert.equal(f.live.closed,true);assert.equal(f.failures.length,1);assert.equal(f.failures[0].code,'LIVE_RENEWAL_INPUT_BACKLOG');
 assert.equal(f.live.renewal,null);assert.equal(f.sockets.length,1);
});

test('LIVE-2C: JSON setup errors expose only classified codes, not provider messages or key IDs',async t=>{
 for(const [error,expected]of [[{code:429,status:'RESOURCE_EXHAUSTED',message:'private-key quota'},'LIVE_QUOTA_EXCEEDED'],[{code:400,details:[{reason:'API_KEY_INVALID',metadata:{key:'private-key'}}]},'LIVE_KEY_REJECTED'],[{code:400,message:'unknown field'},'LIVE_REQUEST_INVALID'],[{code:503},'LIVE_PROVIDER_UNAVAILABLE']]){
  const server=new WebSocketServer({port:0,host:'127.0.0.1'});await new Promise(r=>server.once('listening',r));
  server.on('connection',ws=>ws.on('message',()=>ws.send(JSON.stringify({error}))));
  const Socket=function(_url,options){return new WebSocket(`ws://127.0.0.1:${server.address().port}`,options);};
  const live=new GeminiLive({model:'models/fixture-live',key:'private-key',Socket,onAudio:()=>{}});
  try{await assert.rejects(live.connect(),e=>e.code===expected&&!JSON.stringify(e).includes('private-key'));}
  finally{live.close();for(const socket of server.clients)socket.terminate();server.close();}
 }
});

test('LIVE-2C: handshake HTTP rejection is classified and the response is drained',async t=>{
 const http=require('node:http');const server=http.createServer((_request,response)=>{response.writeHead(429);response.end('private-provider-body');});
 server.on('upgrade',(_request,socket)=>socket.end('HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>server.close());
 const Socket=function(_url,options){return new WebSocket(`ws://127.0.0.1:${server.address().port}`,options);};
 const live=new GeminiLive({model:'models/fixture-live',key:'fixture-private-key',Socket,onAudio:()=>{}});t.after(()=>live.close());
 await assert.rejects(live.connect(),e=>e.code==='LIVE_QUOTA_EXCEEDED'&&!JSON.stringify(e).includes('private'));
});

test('LIVE-2C: WebSocket setup rejection distinguishes key problems from invalid configuration',async t=>{
 for(const [reason,expected]of [['API key not valid. private-key','LIVE_KEY_REJECTED'],['Quota exceeded private-project','LIVE_QUOTA_EXCEEDED'],['Unknown field badConfig','LIVE_REQUEST_INVALID']]){
  const server=new WebSocketServer({port:0,host:'127.0.0.1'});await new Promise(r=>server.once('listening',r));
  server.on('connection',ws=>ws.on('message',()=>ws.close(1007,reason)));
  const Socket=function(_url,options){return new WebSocket(`ws://127.0.0.1:${server.address().port}`,options);};
  const live=new GeminiLive({model:'models/fixture-live',key:'private-key',Socket,onAudio:()=>{}});
  try{await assert.rejects(live.connect(),e=>e.code===expected&&!JSON.stringify(e).includes('private'));}
  finally{live.close();for(const socket of server.clients)socket.terminate();server.close();}
 }
});
