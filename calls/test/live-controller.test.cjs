// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { LiveController } = require('../service/live-controller.cjs');

function fixture() {
  const calls = [], errors = []; let callbacks, child;
  const driver = { startLive: async (...args) => calls.push(['start', ...args]), liveAudio: async (...args) => calls.push(['output', ...args]), stopLive: async (...args) => calls.push(['stop', ...args]), clearLive: async (...args) => calls.push(['clear', ...args]) };
  const controller = new LiveController({ driver, runtime: { env: () => ({ PULSE_SERVER: 'unix:/fixture-only.sock' }) }, getKeys: async () => ['fake'],
    onFailure: (...args) => errors.push(args), makeSession: options => {
      callbacks = options;
      return { stats: { inputBytes: 0, outputBytes: 0, inputEnds: 0 }, connect: async () => {}, close: () => calls.push(['close']), greet: options => calls.push(['greet', options]), silence: () => calls.push(['silence']), audio(frame) { this.stats.inputBytes += frame.length; }, endAudio() { this.stats.inputEnds++; } };
    }, capture: (program, args, options) => {
      calls.push(['capture', program, args, options]);
      child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.exitCode = null;
      child.signalCode = null;
      child.kill = signal => { calls.push(['kill', signal]); child.signalCode = signal; child.emit('exit', null, signal); };
      return child;
    } });
  return { controller, calls, errors, callbacks: () => callbacks, child: () => child };
}

test('Live waits for answer before capturing, uses the dedicated monitor and stops on hangup', async () => {
  const f = fixture(), record = { id: 'owned-call', nativeId: 'native' };
  await f.controller.prepare(record);
  assert.equal(f.calls.some(c => c[0] === 'capture'), false);
  await f.controller.start(record);
  const capture = f.calls.find(c => c[0] === 'capture');
  assert.ok(capture[2].includes('--device=botsky_calls.monitor'));
  assert.equal(capture[3].env.PULSE_SERVER, 'unix:/fixture-only.sock');
  const frame = Buffer.alloc(1920); for (let i = 0; i < frame.length; i += 2) frame.writeInt16LE(4000, i);
  f.child().stdout.write(frame);
  assert.ok(f.controller.status().peakInput > 0.1);
  assert.equal(f.controller.status().receivedSpeechFrames, 1);
  f.child().stdout.write(Buffer.alloc(1920 * 12));
  assert.equal(f.controller.status().completedInputTurns, 1);
  const sentBytes = f.controller.active.session.stats.inputBytes;
  f.child().stdout.write(Buffer.alloc(1920 * 50));
  assert.equal(f.controller.active.session.stats.inputBytes, sentBytes);
  f.callbacks().onAudio(Buffer.alloc(2400)); await f.controller.active.output;
  assert.equal(f.calls.filter(c => c[0] === 'output').length, 1);
  await f.controller.stop(record.id);
  f.callbacks().onAudio(Buffer.alloc(2400));
  assert.equal(f.controller.status(), null); assert.equal(f.child().exitCode, null); assert.equal(f.child().signalCode, 'SIGTERM');
  assert.equal(f.calls.filter(c => c[0] === 'output').length, 1);
});

test('A failure in credentials releases the reservation and unrelated calls cannot stop Live', async () => {
  const f = fixture(); f.controller.getKeys = async () => { throw Error('unavailable'); };
  await assert.rejects(f.controller.prepare({ id: 'a' }), /unavailable/);
  assert.equal(f.controller.active, null);
  f.controller.getKeys = async () => ['fake'];
  await f.controller.prepare({ id: 'b' });
  await f.controller.stop('different-call'); assert.equal(f.controller.active.callId, 'b');
  await f.controller.stop('b');
});

test('H4: a bridge failure keeps its origin even when its code starts with LIVE', async () => {
  const f = fixture(), record = { id: 'owned-call', nativeId: 'native' };
  await f.controller.prepare(record); await f.controller.start(record);
  await f.controller.suspend(record);
  f.controller.driver.startLive = async () => { const error = new Error('synthetic bridge timeout'); error.code = 'LIVE_START_TIMEOUT'; throw error; };
  await assert.rejects(f.controller.resume(record), { code: 'LIVE_START_TIMEOUT', callFailureSource: 'browser' });
  assert.equal(f.controller.active.suspended, true);
  await f.controller.stop(record.id);
});

test('PM05B: Live preserves the same Gemini session through suspend/rebind and drops stale output', async () => {
  const f = fixture(), record = { id: 'owned-call', nativeId: 'native-1' };
  await f.controller.prepare(record); await f.controller.start(record);
  const session = f.controller.active.session;
  f.callbacks().onAudio(Buffer.alloc(2400));
  await f.controller.suspend(record); await f.controller.active.output;
  assert.equal(f.calls.filter(c => c[0] === 'output').length, 0);
  const before = session.stats.inputBytes;
  f.child().stdout.write(Buffer.alloc(1920 * 3, 10));
  f.callbacks().onAudio(Buffer.alloc(2400));
  assert.equal(session.stats.inputBytes, before);
  record.nativeId = 'native-2'; await f.controller.resume(record);
  assert.equal(f.controller.active.session, session);
  f.callbacks().onAudio(Buffer.alloc(2400)); await f.controller.active.output;
  assert.equal(f.calls.filter(c => c[0] === 'output').length, 1);
  assert.equal(f.calls.find(c => c[0] === 'output')[1], 'native-2');
  assert.equal(f.calls.filter(c => c[0] === 'capture').length, 1);
  assert.equal(f.calls.filter(c => c[0] === 'greet').length, 1);
  await f.controller.stop(record.id);
});

test('PM05C: a late Live start after suspend cannot create a capture or duplicate the greeting', async () => {
  const f = fixture(), record = { id: 'owned-call', nativeId: 'native' };
  let release, entered;
  const reached = new Promise(resolve => { entered = resolve; }); const gate = new Promise(resolve => { release = resolve; });
  const originalStart = f.controller.driver.startLive;
  f.controller.driver.startLive = async (...args) => { entered(); await gate; return originalStart(...args); };
  await f.controller.prepare(record);
  const start = f.controller.start(record); await reached;
  await f.controller.suspend(record); release(); await start;
  assert.equal(f.calls.some(c => c[0] === 'capture'), false); assert.equal(f.calls.some(c => c[0] === 'greet'), false);
  f.controller.driver.startLive = originalStart; await f.controller.resume(record);
  assert.equal(f.calls.filter(c => c[0] === 'capture').length, 1); assert.equal(f.calls.filter(c => c[0] === 'greet').length, 1);
  await f.controller.stop(record.id);
});


test('LIVE-1: long native responses exceed the old queue cap without failing or using a TTS provider', async () => {
 const f=fixture(),record={id:'long-response',nativeId:'native'};await f.controller.prepare(record);await f.controller.start(record);
 for(let i=0;i<80;i++)f.callbacks().onAudio(Buffer.alloc(24000));
 await f.controller.active.output;
 assert.equal(f.errors.length,0);assert.equal(f.calls.filter(call=>call[0]==='output').length,80);
 assert.equal(f.controller.status().bridgeAcceptedSeconds,40);await f.controller.stop(record.id);
});

test('LIVE-1: explicit silence fences pending and in-flight chunks, keeps capture alive and accepts the next reply', async () => {
 const f=fixture(),record={id:'silence-response',nativeId:'native'};await f.controller.prepare(record);await f.controller.start(record);
 let entered,release;const reached=new Promise(r=>{entered=r;}),gate=new Promise(r=>{release=r;});const delivered=[];let browserEpoch=0;
 f.controller.driver.liveAudio=async(id,session,data,epoch)=>{entered();await gate;if(epoch!==browserEpoch)return {discarded:true};delivered.push(epoch);return {accepted:true};};
 f.controller.driver.clearLive=async(id,session,epoch)=>{browserEpoch=epoch;};
 f.callbacks().onAudio(Buffer.alloc(2400));f.callbacks().onAudio(Buffer.alloc(2400));await reached;
 const child=f.child();await f.controller.silence(record);release();await f.controller.active.output;
 assert.equal(delivered.length,0);assert.equal(child.exitCode,null);assert.equal(f.controller.status().state,'listening');assert.equal(f.calls.filter(c=>c[0]==='silence').length,1);
 f.callbacks().onAudio(Buffer.alloc(2400));await f.controller.active.output;assert.deepEqual(delivered,[1]);assert.equal(f.errors.length,0);
 await assert.rejects(f.controller.silence({id:'someone-else'}),{code:'LIVE_NOT_READY'});
 await f.controller.stop(record.id);
});

test('Group interruption clears scheduled and queued audio while preserving the Live capture', async () => {
 const f=fixture(),record={id:'group-interrupt',nativeId:'native',groupId:'group@g.us',liveInterruption:true};
 await f.controller.prepare(record);await f.controller.start(record);
 assert.equal(f.callbacks().interruptOnSpeech,true);
 let entered,release;const reached=new Promise(resolve=>{entered=resolve;}),gate=new Promise(resolve=>{release=resolve;});
 let browserEpoch=0;const delivered=[];
 f.controller.driver.liveAudio=async(_native,_session,_data,epoch)=>{
   if(epoch===0){entered();await gate;}
   if(epoch!==browserEpoch)return {discarded:true};
   delivered.push(epoch);return {accepted:true};
 };
 f.controller.driver.clearLive=async(_native,_session,epoch)=>{browserEpoch=epoch;};
 f.callbacks().onAudio(Buffer.alloc(2400));f.callbacks().onAudio(Buffer.alloc(2400));await reached;
 f.callbacks().onInterrupted();await f.controller.active.clearing;release();await f.controller.active.output;
 assert.deepEqual(delivered,[]);
 assert.equal(f.controller.active.epoch,1);
 assert.equal(f.child().exitCode,null);
 f.callbacks().onAudio(Buffer.alloc(2400));await f.controller.active.output;
 assert.deepEqual(delivered,[1]);assert.equal(f.errors.length,0);
 await f.controller.stop(record.id);
 const privateCall=fixture(),privateRecord={id:'private',nativeId:'native',liveInterruption:true};
 await privateCall.controller.prepare(privateRecord);
 assert.equal(privateCall.callbacks().interruptOnSpeech,false);
 await privateCall.controller.stop(privateRecord.id);
});

test('LIVE-1: playback backpressure waits locally and cancellation discards the remaining response', async () => {
 const f=fixture(),record={id:'paced-response',nativeId:'native'};await f.controller.prepare(record);await f.controller.start(record);
 let waits=0,sends=0;f.controller.driver.liveAudio=async()=>++sends===1?{retryAfterMs:200}:{accepted:true};
 f.controller.wait=async()=>{waits++;};f.callbacks().onAudio(Buffer.alloc(2400));await f.controller.active.output;
 assert.equal(waits,1);assert.equal(sends,2);assert.equal(f.controller.status().bridgeAcceptedSeconds,0.05);
 let entered,release;const reached=new Promise(r=>{entered=r;}),gate=new Promise(r=>{release=r;});
 f.controller.driver.liveAudio=async()=>({retryAfterMs:200});f.controller.wait=async()=>{entered();await gate;};
 f.callbacks().onAudio(Buffer.alloc(2400));await reached;const active=f.controller.active;await f.controller.stop(record.id);release();await active.output;
 assert.equal(f.errors.length,0);assert.equal(f.controller.active,null);
});

test('Group director fences delayed PCM when the input changes without relying on provider interruption', async t => {
 const { GeminiLive } = require('../service/gemini-live.cjs');
 const f=fixture();let socket;
 class Socket extends EventEmitter {
  constructor(){super();this.readyState=1;this.bufferedAmount=0;socket=this;queueMicrotask(()=>this.emit('open'));}
  send(raw){if(JSON.parse(raw).setup)queueMicrotask(()=>this.emit('message',Buffer.from('{"setupComplete":{}}')));}
  close(){this.readyState=3;}terminate(){}
 }
 f.controller.makeSession=options=>new GeminiLive({...options,Socket,model:'models/fixture-live'});
 const record={id:'director-call',nativeId:'native',groupId:'group@g.us',liveInterruption:true};
 await f.controller.prepare(record);await f.controller.start(record);t.after(()=>f.controller.stop());
 const s=f.controller.active,session=s.session;
 const emit=content=>socket.emit('message',Buffer.from(JSON.stringify({serverContent:content})));
 emit({turnComplete:true});session.audio(Buffer.alloc(1920));session.endAudio();
 emit({inputTranscription:{text:'Zhana, hola.'}});
 await session.handleToolCalls([{id:'grant',name:'autorizar_turno',args:{addressed:true}}]);
 let release,entered;const gate=new Promise(r=>{release=r;}),reached=new Promise(r=>{entered=r;});let sent=0;
 f.controller.driver.liveAudio=async()=>{sent++;return {retryAfterMs:20};};
 f.controller.wait=async()=>{entered();await gate;};
 emit({modelTurn:{parts:[{inlineData:{mimeType:'audio/pcm',data:Buffer.alloc(2400).toString('base64')}}]}});
 await reached;
 session.audio(Buffer.alloc(1920));release();await s.output;
 assert.equal(sent,1);assert.equal(s.bridgeAcceptedBytes||0,0);
 assert.equal(f.controller.status().groupDirector.allowVoice,false);
 assert.equal(f.controller.status().groupDirector.callId,record.id);
 await f.controller.stop(record.id);
 assert.equal(session.voiceGate.snapshot().state,'ended');
 assert.equal(f.errors.length,0);
});

test('Pending question waits for queued output and browser playback before starting its window', async t => {
 const { GroupDirector } = require('../service/group-director.cjs');
 const f=fixture(),record={id:'pending-playback',nativeId:'native',groupId:'group@g.us'};
 await f.controller.prepare(record);await f.controller.start(record);t.after(()=>f.controller.stop());
 const session=f.controller.active.session,director=new GroupDirector({now:()=>100000});
 session.voiceGate=director;session.isOutputCurrent=token=>director.isCurrent(token);session.outputCompleted=(token,at)=>director.playbackEnded(token,at);
 director.begin({greeting:true});director.speaking();director.proposeQuestion('¿Qué prefieren?',director.current);director.outputText('¿Qué prefieren?');director.generationFinished();
 const token=director.token();director.end();
 let polls=0;
 f.controller.driver.livePlayback=async()=>++polls===1?{playing:true,endedAt:null}:{playing:false,endedAt:99500};
 f.controller.wait=async()=>{assert.equal(director.pendingQuestion,null);};
 f.callbacks().onGenerationComplete(token);await f.controller.active.playbackWatch;
 assert.equal(polls,2);assert.equal(director.pendingQuestion.openedAt,99500);assert.equal(director.pendingQuestion.expiresAt,129500);
});

test('LIVE-1: only the explicit initial request is passed to the native greeting', async () => {
 const f=fixture(),record={id:'topic-call',nativeId:'native',liveRequest:'Llama a Pepino para hablar de fútbol'};
 await f.controller.prepare(record);await f.controller.start(record);
 assert.equal(f.calls.find(c=>c[0]==='greet')[1].liveRequest,record.liveRequest);await f.controller.stop(record.id);
});

test('LIVE-1: a new reply received during the browser clear waits instead of losing its first words',async()=>{
 const f=fixture(),record={id:'clear-race',nativeId:'native'};await f.controller.prepare(record);await f.controller.start(record);
 let release;const gate=new Promise(resolve=>{release=resolve;});f.controller.driver.clearLive=async()=>gate;
 const clearing=f.controller.silence(record);f.callbacks().onAudio(Buffer.alloc(2400));
 await Promise.resolve();assert.equal(f.calls.filter(c=>c[0]==='output').length,0);
 release();await clearing;await f.controller.active.output;assert.equal(f.calls.filter(c=>c[0]==='output').length,1);
 await f.controller.stop(record.id);
});

test('LIVE-2: provider renewal preserves the native call, capture and original greeting',async t=>{
 const {GeminiLive}=require('../service/gemini-live.cjs');
 const f=fixture(),sockets=[];
 class Socket extends EventEmitter{
  constructor(){super();this.readyState=1;this.bufferedAmount=0;this.sent=[];sockets.push(this);queueMicrotask(()=>this.emit('open'));}
  send(raw){const data=JSON.parse(raw);this.sent.push(data);if(data.setup)queueMicrotask(()=>this.emit('message',Buffer.from('{"setupComplete":{}}')));}
  close(){this.readyState=3;this.emit('close');}terminate(){}
 }
 f.controller.makeSession=options=>new GeminiLive({...options,Socket,model:'models/fixture-live'});
 const record={id:'same-call',nativeId:'same-native',liveRequest:'Conversen de astronomía'};
 await f.controller.prepare(record);await f.controller.start(record);t.after(()=>f.controller.stop(record.id));
 const child=f.child(),session=f.controller.active.session;
 sockets[0].emit('message',Buffer.from(JSON.stringify({serverContent:{turnComplete:true,interactionStatus:'IDLE'},sessionResumptionUpdate:{resumable:true,newHandle:'private-checkpoint'},goAway:{timeLeft:'15s'}})));
 for(let i=0;i<20&&session.stats.renewals!==1;i++)await new Promise(r=>setImmediate(r));
 assert.equal(session.stats.renewals,1);assert.equal(f.controller.active.session,session);assert.equal(f.child(),child);
 assert.equal(f.calls.filter(c=>c[0]==='start').length,1);assert.equal(f.calls.filter(c=>c[0]==='capture').length,1);
 assert.equal(f.calls.filter(c=>c[0]==='stop').length,0);assert.equal(sockets.flatMap(s=>s.sent).filter(m=>m.clientContent).length,1);
 assert.equal(f.controller.status().renewals,1);assert.equal(f.errors.length,0);
});
