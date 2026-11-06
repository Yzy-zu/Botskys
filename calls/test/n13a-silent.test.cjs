// Port técnico de Zhana; fixtures locales sin navegador ni proveedor.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { WebSocket } = require('ws');
const { GeminiLive } = require('../service/gemini-live.cjs');
const { AVATAR_TOOLS } = require('../service/avatar-tools.cjs');

async function fixture(t, onToolCall = async () => ({ success: true }), { groupVoice = true, tools = AVATAR_TOOLS } = {}) {
  let socket;
  class Socket extends EventEmitter {
    constructor() {
      super(); this.readyState = WebSocket.OPEN; this.bufferedAmount = 0; this.sent = [];
      socket = this; queueMicrotask(() => this.emit('open'));
    }
    send(raw) {
      const message = JSON.parse(raw); this.sent.push(message);
      if (message.setup) queueMicrotask(() => this.emit('message', Buffer.from('{"setupComplete":{}}')));
    }
    close() { this.readyState = WebSocket.CLOSED; }
    terminate() {}
  }
  let audioBytes = 0;
  const live = new GeminiLive({model:'models/fixture-live', key: 'fixture', Socket, groupVoice, tools,
    onAudio: data => { audioBytes += data.length; }, onToolCall });
  t.after(() => live.close());
  await live.connect();
  const wait = async predicate => {
    for (let i = 0; i < 100; i++) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 5));
    }
    assert.fail('Live event timed out');
  };
  return { live, get socket() { return socket; }, get audioBytes() { return audioBytes; }, wait,
    emit: message => socket.emit('message', Buffer.from(JSON.stringify(message))) };
}

test('N13a avatar actions use SILENT scheduling and never open group voice or undeclared tools', async t => {
  const calls = [];
  const f = await fixture(t, async (args, info) => { calls.push({ args, name: info.name }); return { success: true }; });
  const declarations = f.socket.sent[0].setup.tools.flatMap(tool => tool.functionDeclarations);
  const avatarTool = declarations.find(tool => tool.name === 'controlar_avatar');
  assert.equal(avatarTool.behavior, 'NON_BLOCKING');

  f.emit({ toolCall: { functionCalls: [{ id: 'avatar-1', name: 'controlar_avatar', args: { action: 'expression', name: 'happy', duration: 3 } }] } });
  await f.wait(() => f.socket.sent.some(message => message.toolResponse));
  const response = f.socket.sent.find(message => message.toolResponse).toolResponse.functionResponses[0];
  assert.deepEqual({ scheduling: response.scheduling, willContinue: response.willContinue }, { scheduling: 'SILENT', willContinue: false });
  assert.equal(response.response.success, true);
  assert.equal(f.live.voiceGate.allowed, false);

  f.emit({ serverContent: { modelTurn: { parts: [{ inlineData: { mimeType: 'audio/pcm', data: Buffer.alloc(2400).toString('base64') } }] } } });
  assert.equal(f.audioBytes, 0, 'a visual gesture must not authorize PCM');

  f.emit({ toolCall: { functionCalls: [{ id: 'unknown-1', name: 'controlar_clips', args: { action: 'play' } }] } });
  await f.wait(() => f.socket.sent.filter(message => message.toolResponse).length === 2);
  const unknown = f.socket.sent.at(-1).toolResponse.functionResponses[0];
  assert.equal(unknown.response.success, false);
  assert.equal(unknown.response.message, 'Herramienta no disponible.');
  assert.deepEqual(calls, [{ args: { action: 'expression', name: 'happy', duration: 3 }, name: 'controlar_avatar' }]);
});

test('N13a pending avatar work is aborted and suppressed when its group generation is superseded', async t => {
  let entered, release, signal;
  const started = new Promise(resolve => { entered = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  const f = await fixture(t, async (_args, info) => { signal = info.signal; entered(); await pending; return { success: true }; });
  f.emit({ toolCall: { functionCalls: [{ id: 'avatar-old-turn', name: 'controlar_avatar', args: { action: 'expression', name: 'surprised' } }] } });
  await started;
  f.live.audio(Buffer.alloc(640));
  assert.equal(signal.aborted, true);
  release();
  await f.wait(() => f.live.toolControllers.size === 0);
  assert.equal(f.socket.sent.filter(message => message.toolResponse).length, 0);
  assert.equal(f.live.voiceGate.allowed, false);
});

test('N13a toolCallCancellation aborts pending avatar work without a late result', async t => {
  let entered, release, signal;
  const started = new Promise(resolve => { entered = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  const f = await fixture(t, async (_args, info) => { signal = info.signal; entered(); await pending; return { success: true }; });
  f.emit({ toolCall: { functionCalls: [{ id: 'avatar-cancel', name: 'controlar_avatar', args: { action: 'expression', name: 'wink' } }] } });
  await started;
  f.emit({ toolCallCancellation: { ids: ['avatar-cancel'] } });
  assert.equal(signal.aborted, true);
  release();
  await f.wait(() => f.live.toolControllers.size === 0);
  assert.equal(f.socket.sent.filter(message => message.toolResponse).length, 0);
});

test('N13a call closure aborts pending avatar work without a late result', async t => {
  let entered, release, signal;
  const started = new Promise(resolve => { entered = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  const f = await fixture(t, async (_args, info) => { signal = info.signal; entered(); await pending; return { success: true }; });
  f.emit({ toolCall: { functionCalls: [{ id: 'avatar-close', name: 'controlar_avatar', args: { action: 'background', name: 'night' } }] } });
  await started;
  f.live.close();
  assert.equal(signal.aborted, true);
  release();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.socket.sent.filter(message => message.toolResponse).length, 0);
});

test('N13a new private input cancels only the pending avatar control', async t => {
  const toolEntered = new Map(), toolSignals = new Map(), finish = new Map();
  const entered = name => new Promise(resolve => toolEntered.set(name, resolve));
  const waitForFinish = name => new Promise(resolve => finish.set(name, resolve));
  const tools = [...AVATAR_TOOLS, { functionDeclarations: [{ name: 'controlar_privada', behavior: 'BLOCKING', parameters: { type: 'OBJECT', properties: {} } }] }];
  const f = await fixture(t, async (_args, info) => {
    toolSignals.set(info.name, info.signal);
    toolEntered.get(info.name)();
    await waitForFinish(info.name);
    return { success: true };
  }, { groupVoice: false, tools });
  const avatarStarted = entered('controlar_avatar'), otherStarted = entered('controlar_privada');
  f.emit({ toolCall: { functionCalls: [{ id: 'private-avatar', name: 'controlar_avatar', args: { action: 'expression', name: 'happy' } }] } });
  f.emit({ toolCall: { functionCalls: [{ id: 'private-other', name: 'controlar_privada', args: {} }] } });
  await Promise.all([avatarStarted, otherStarted]);

  f.live.audio(Buffer.alloc(640));
  assert.equal(toolSignals.get('controlar_avatar').aborted, true);
  assert.equal(toolSignals.get('controlar_privada').aborted, false);
  finish.get('controlar_avatar')(); finish.get('controlar_privada')();
  await f.wait(() => f.live.toolControllers.size === 0);
  const responses = f.socket.sent.flatMap(message => message.toolResponse?.functionResponses || []);
  assert.deepEqual(responses.map(response => response.id), ['private-other']);
});
