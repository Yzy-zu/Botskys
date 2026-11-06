// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Journal } = require('../service/journal.cjs');
const { CallManager } = require('../service/manager.cjs');
const { LiveController } = require('../service/live-controller.cjs');

class TestClock {
  constructor() { this.time = 1_000_000; this.next = 0; this.tasks = new Map(); }
  now = () => this.time;
  setTimeout = (fn, ms) => { const id = ++this.next; this.tasks.set(id, { at: this.time + ms, fn }); return id; };
  clearTimeout = id => this.tasks.delete(id);
  async advance(ms) {
    const target = this.time + ms;
    for (;;) {
      const next = [...this.tasks].sort((a, b) => a[1].at - b[1].at)[0];
      if (!next || next[1].at > target) break;
      this.time = next[1].at; this.tasks.delete(next[0]); next[1].fn();
      await new Promise(resolve => setImmediate(resolve));
    }
    this.time = target;
  }
}

class CallDriver {
  constructor() {
    this.call = null; this.calls = []; this.closeCount = 0; this.ends = 0; this.disarms = 0;
    this.failNextLiveStart = null;
  }
  async start() { this.calls.push(['browser_start']); }
  async close() { this.closeCount++; this.call = null; }
  async snapshot() { return this.call ? { ...this.call } : { active: false }; }
  async dial(target) {
    this.calls.push(['dial', target.id]);
    this.call = { id: 'native-n12a', active: true, outgoing: true, connected: false,
      isGroup: true, groupId: target.id, audience: { known: true, connectedHumans: 0, source: 'fixture' } };
    return { ...this.call };
  }
  async startLive(nativeId, sessionId, epoch) {
    this.calls.push(['start_live', nativeId, sessionId, epoch]);
    if (this.failNextLiveStart) { const error = this.failNextLiveStart; this.failNextLiveStart = null; throw error; }
  }
  async stopLive(nativeId, sessionId) { this.calls.push(['stop_live', nativeId, sessionId]); }
  async liveAudio(nativeId, sessionId, data, epoch) {
    this.calls.push(['live_audio', nativeId, sessionId, data.length, epoch]); return { accepted: true };
  }
  async volume() {}
  async end(nativeId) {
    if (this.call && this.call.id !== nativeId) throw Object.assign(new Error('CALL_CHANGED'), { code: 'CALL_CHANGED' });
    this.ends++; this.call = null;
  }
  async disarmAudio() { this.disarms++; return { released: true }; }
}

function createCapture() {
  const child = new EventEmitter();
  child.stdout = new PassThrough(); child.stderr = new PassThrough();
  child.exitCode = null; child.signalCode = null;
  child.kill = signal => { child.signalCode = signal; child.emit('exit', null, signal); };
  return child;
}

async function fixture(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zhana-n12a-continuity-'));
  const clock = new TestClock(), journal = new Journal(path.join(dir, 'journal.json'));
  const driver = new CallDriver(), captures = [], sessions = [], logs = [];
  const live = new LiveController({ driver, runtime: { env: () => ({ PULSE_SERVER: 'unix:/fixture.sock' }) },
    getKeys: async () => ['fixture-key'], now: clock.now, wait: async () => {},
    capture: () => { const child = createCapture(); captures.push(child); return child; },
    makeSession: options => {
      const session = { options, stats: { inputBytes: 0, outputBytes: 0, inputEnds: 0 },
        async connect() {}, close() { this.closed = true; }, greet(value) { this.greetings = (this.greetings || 0) + 1; this.greeting = value; },
        audio(frame) { this.stats.inputBytes += frame.length; }, endAudio() { this.stats.inputEnds++; } };
      sessions.push(session); return session;
    } });
  const manager = new CallManager({ driver, journal, clock, group: { id: 'lab@g.us', name: 'Botsky Lab' },
    audiencePolicy: { emptyGraceMs: 5000, unavailableGraceMs: 15000 }, log: (event, fields) => logs.push([event, fields]) });
  manager.liveController = live;
  await manager.boot();
  t.after(async () => { await manager.stop(); await fs.rm(dir, { recursive: true, force: true }); });
  return { clock, driver, captures, sessions, manager, live, logs };
}

async function drain(manager) {
  for (let i = 0; i < 12; i++) {
    const queue = manager.queue, writes = manager.journal.writes;
    await queue; await writes; await new Promise(resolve => setImmediate(resolve));
    if (queue === manager.queue && writes === manager.journal.writes) return;
  }
  throw new Error('Call manager did not settle');
}

async function startGroupCall(f) {
  const result = await f.manager.startCall({ key: 'n12a-continuity-fixture', targetJid: 'lab@g.us', live: true, maxSeconds: 600 });
  await drain(f.manager);
  f.driver.call.connected = true;
  f.driver.call.audience = { known: true, connectedHumans: 2, source: 'fixture' };
  await f.manager.serial(() => f.manager.poll());
  await drain(f.manager);
  assert.equal(f.manager.active.id, result.call.id);
  assert.equal(f.sessions.length, 1);
  assert.equal(f.captures.length, 1);
  return result.call.id;
}

async function audience(f, value) {
  f.driver.call.audience = value;
  await f.manager.serial(() => f.manager.poll());
  await drain(f.manager);
}

function speechFrame() {
  const frame = Buffer.alloc(1920);
  for (let offset = 0; offset < frame.length; offset += 2) frame.writeInt16LE(10000, offset);
  return frame;
}

test('N12a keeps one Live session for 2→1→2 and suspends/resumes it through 0→1 within audience grace', async t => {
  const f = await fixture(t), callId = await startGroupCall(f);
  const session = f.sessions[0], child = f.captures[0], greetings = session.greetings;
  await audience(f, { known: true, connectedHumans: 1, source: 'fixture' });
  assert.equal(f.live.active.session, session); assert.equal(f.live.active.child, child);
  assert.equal(f.live.active.suspended, undefined); assert.equal(session.greetings, greetings);
  await audience(f, { known: true, connectedHumans: 2, source: 'fixture' });
  assert.equal(f.driver.calls.filter(call => call[0] === 'start_live').length, 1);
  assert.equal(f.driver.calls.filter(call => call[0] === 'stop_live').length, 0);

  await audience(f, { known: true, connectedHumans: 0, source: 'fixture' });
  assert.equal(f.manager.active.id, callId); assert.equal(f.manager.active.audiencePaused, true);
  assert.equal(f.live.active.session, session); assert.equal(f.live.active.child, child);
  assert.equal(f.live.active.suspended, true);
  const inputBytes = session.stats.inputBytes, outputCount = f.driver.calls.filter(call => call[0] === 'live_audio').length;
  child.stdout.write(speechFrame());
  session.options.onAudio(Buffer.alloc(2400));
  await f.live.active.output;
  assert.equal(session.stats.inputBytes, inputBytes);
  assert.equal(f.driver.calls.filter(call => call[0] === 'live_audio').length, outputCount);

  await audience(f, { known: true, connectedHumans: 1, source: 'fixture' });
  assert.equal(f.manager.active.id, callId); assert.equal(f.manager.active.audiencePaused, false);
  assert.equal(f.live.active.session, session); assert.equal(f.live.active.child, child);
  assert.equal(f.live.active.suspended, false);
  assert.equal(session.greetings, greetings); assert.equal(f.captures.length, 1);
  assert.equal(f.driver.calls.filter(call => call[0] === 'start_live').length, 2);
  assert.equal(f.driver.calls.filter(call => call[0] === 'stop_live').length, 1);
  session.options.onAudio(Buffer.alloc(2400)); await f.live.active.output;
  assert.equal(f.driver.calls.filter(call => call[0] === 'live_audio').length, outputCount + 1);
});

test('N12a ends and cleans Live after sustained empty audience without a late reappearance', async t => {
  const f = await fixture(t), callId = await startGroupCall(f), session = f.sessions[0], child = f.captures[0];
  await audience(f, { known: true, connectedHumans: 0, source: 'fixture' });
  assert.equal(f.manager.active.id, callId); assert.equal(f.live.active.suspended, true);
  f.clock.time += 5001;
  await f.manager.serial(() => f.manager.poll());
  await drain(f.manager);
  assert.equal(f.manager.active, null);
  assert.equal(f.manager.getCall(callId).reason, 'audience_empty');
  assert.equal(f.live.active, null); assert.equal(session.closed, true);
  assert.equal(child.signalCode, 'SIGTERM');
  assert.equal(f.driver.ends, 1); assert.equal(f.driver.disarms, 1);
  const starts = f.driver.calls.filter(call => call[0] === 'start_live').length;
  f.driver.call = { id: 'native-late-reappearance', active: true, outgoing: true, connected: true, isGroup: true, groupId: 'lab@g.us',
    audience: { known: true, connectedHumans: 1, source: 'fixture' } };
  await f.manager.serial(() => f.manager.poll()); await drain(f.manager);
  assert.equal(f.manager.active, null); assert.equal(f.live.active, null);
  assert.equal(f.driver.calls.filter(call => call[0] === 'start_live').length, starts);
  assert.equal(f.sessions.length, 1); assert.equal(f.captures.length, 1);
});

test('N12a browser failure rebinding Live enters bounded H4 recovery without closing the call', async t => {
  const f = await fixture(t), callId = await startGroupCall(f);
  const session = f.sessions[0], child = f.captures[0];
  await audience(f, { known: true, connectedHumans: 0, source: 'fixture' });
  const timeout = Object.assign(new Error('fixture bridge timeout'), { code: 'LIVE_START_TIMEOUT' });
  f.driver.failNextLiveStart = timeout;
  f.driver.call.audience = { known: true, connectedHumans: 1, source: 'fixture' };

  await f.clock.advance(1000);
  await drain(f.manager);
  for (let i = 0; i < 10 && f.manager.active?.recovery?.phase !== 'waiting'; i++) {
    await new Promise(resolve => setImmediate(resolve)); await drain(f.manager);
  }

  assert.equal(timeout.callFailureSource, 'browser');
  assert.equal(f.manager.active.id, callId);
  assert.equal(f.manager.state, 'recovering_call');
  assert.equal(f.manager.active.recovery.attempts, 1);
  assert.equal(f.manager.active.recovery.phase, 'waiting');
  assert.equal(f.driver.ends, 0); assert.equal(f.driver.disarms, 0);
  assert.equal(f.driver.closeCount, 1); // Only the initial boot close.
  assert.equal(f.live.active.session, session); assert.equal(f.live.active.child, child);
  assert.equal(f.sessions.length, 1); assert.equal(f.captures.length, 1);
});
