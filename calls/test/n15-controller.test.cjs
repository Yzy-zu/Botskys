// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { LiveController } = require('../service/live-controller.cjs');
const { GroupDirector } = require('../service/group-director.cjs');

test('N15: a new group intervention clears bridge playback and fences queued Live PCM', async t => {
  const calls = [], bridgeQueue = [];
  let callbacks, child, browserEpoch = 0, releaseFirst, enteredFirst;
  const firstGate = new Promise(resolve => { releaseFirst = resolve; });
  const firstEntered = new Promise(resolve => { enteredFirst = resolve; });
  const driver = {
    startLive: async () => {},
    stopLive: async () => {},
    liveAudio: async (_nativeId, _sessionId, data, epoch) => {
      if (epoch === 0 && bridgeQueue.length === 0) {
        bridgeQueue.push(Buffer.from(data)); // already scheduled in the browser bridge
        enteredFirst();
        await firstGate;
      }
      if (epoch !== browserEpoch) return { discarded: true };
      if (!bridgeQueue.some(item => item === data)) bridgeQueue.push(Buffer.from(data));
      calls.push(['audio', epoch]);
      return { accepted: true };
    },
    clearLive: async (_nativeId, _sessionId, epoch) => {
      browserEpoch = epoch;
      bridgeQueue.length = 0; // AudioBridge.clearLive stops scheduled WebAudio sources
      calls.push(['clear', epoch]);
      return { cleared: true };
    },
  };
  const controller = new LiveController({
    driver,
    runtime: { env: () => ({}) },
    getKeys: async () => ['fixture-key'],
    makeSession: options => {
      callbacks = options;
      const voiceGate = new GroupDirector({ callId: 'n15-call', sessionId: 'n15-session' });
      voiceGate.begin();
      voiceGate.current.allowed = true;
      return {
        voiceGate,
        stats: { inputBytes: 0, outputBytes: 0, inputEnds: 0 },
        connect: async () => {}, close() {}, greet() {}, silence() {},
        isOutputCurrent: token => voiceGate.isCurrent(token),
        outputCompleted: (token, at) => voiceGate.playbackEnded(token, at),
      };
    },
    capture: () => {
      child = new EventEmitter();
      child.stdout = new PassThrough(); child.stderr = new PassThrough();
      child.exitCode = null; child.signalCode = null;
      child.kill = signal => { child.signalCode = signal; child.emit('exit', null, signal); };
      return child;
    },
  });
  t.after(() => controller.stop('n15-call'));

  const record = { id: 'n15-call', nativeId: 'native-call', groupId: 'group@g.us', liveInterruption: true };
  await controller.prepare(record);
  await controller.start(record);
  const session = controller.active.session;
  const oldTurn = session.voiceGate.token();

  callbacks.onAudio(Buffer.alloc(2400, 1), oldTurn);
  await firstEntered;
  callbacks.onAudio(Buffer.alloc(2400, 2), oldTurn); // queued behind the in-flight bridge send
  callbacks.onInterrupted();
  await controller.active.clearing;
  releaseFirst();
  await controller.active.output;

  assert.deepEqual(calls.filter(([kind]) => kind === 'clear'), [['clear', 1]]);
  assert.deepEqual(calls.filter(([kind]) => kind === 'audio'), []);
  assert.equal(bridgeQueue.length, 0, 'scheduled PCM from the retired intervention was removed');
  assert.equal(controller.active.epoch, 1);

  const nextTurn = session.voiceGate.begin();
  nextTurn.allowed = true;
  const currentToken = session.voiceGate.token();
  callbacks.onAudio(Buffer.alloc(2400, 3), currentToken);
  await controller.active.output;
  assert.deepEqual(calls.filter(([kind]) => kind === 'audio'), [['audio', 1]]);
  assert.equal(bridgeQueue.length, 1, 'PCM for the next intervention reaches the bridge');
});

test('N15: suspending a group aborts pending turn tools before the director retires that turn', async t => {
  const calls = [];
  let child, signal, toolTurn;
  const controller = new LiveController({
    driver: { startLive: async () => {}, stopLive: async () => {}, liveActivity: async () => {} },
    runtime: { env: () => ({}) }, getKeys: async () => ['fixture-key'],
    makeSession: () => {
      const voiceGate = new GroupDirector({ callId: 'suspend-call', sessionId: 'suspend-session' });
      voiceGate.begin();
      const current = voiceGate.current;
      const tool = new AbortController(); signal = tool.signal; toolTurn = current;
      return {
        voiceGate, stats: {}, connect: async () => {}, close() {}, greet() {}, silence() {},
        cancelToolCallsForTurn(turn) { calls.push(['cancel', turn]); if (turn === current) tool.abort(); },
      };
    },
    capture: () => {
      child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      child.exitCode = null; child.signalCode = null;
      child.kill = signalName => { child.signalCode = signalName; child.emit('exit', null, signalName); };
      return child;
    },
  });
  t.after(() => controller.stop('suspend-call'));
  const record = { id: 'suspend-call', nativeId: 'native', groupId: 'group@g.us' };
  await controller.prepare(record); await controller.start(record);
  await controller.suspend(record);

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'cancel');
  assert.equal(calls[0][1], toolTurn, 'cancellation receives the exact turn before silence advances it');
  assert.equal(signal.aborted, true);
  assert.equal(controller.active.session.voiceGate.reconnecting, true);
});

test('N15: suspension does not invoke group turn cancellation for a private Live session', async t => {
  let child, cancellationCalls = 0;
  const controller = new LiveController({
    driver: { startLive: async () => {}, stopLive: async () => {} },
    runtime: { env: () => ({}) }, getKeys: async () => ['fixture-key'],
    makeSession: () => ({ stats: {}, connect: async () => {}, close() {}, greet() {}, silence() {},
      cancelToolCallsForTurn() { cancellationCalls++; } }),
    capture: () => {
      child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      child.exitCode = null; child.signalCode = null;
      child.kill = signalName => { child.signalCode = signalName; child.emit('exit', null, signalName); };
      return child;
    },
  });
  t.after(() => controller.stop('private-suspend'));
  const record = { id: 'private-suspend', nativeId: 'native' };
  await controller.prepare(record); await controller.start(record); await controller.suspend(record);
  assert.equal(cancellationCalls, 0);
});
