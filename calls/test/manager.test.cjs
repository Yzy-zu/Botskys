// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Journal } = require('../service/journal.cjs');
const { CallManager } = require('../service/manager.cjs');
const { ServiceError } = require('../service/common.cjs');
const { createIncomingPolicy } = require('../service/incoming-policy.cjs');
const { createCallDestinationPolicy } = require('../policy/callDestinations');

class Clock {
  constructor() { this.time = 1000000; this.next = 0; this.tasks = new Map(); }
  now = () => this.time;
  setTimeout = (fn, ms) => { const id = ++this.next; this.tasks.set(id, { at: this.time + ms, fn }); return id; };
  clearTimeout = id => this.tasks.delete(id);
  async advance(ms) {
    this.time += ms;
    for (const [id, task] of [...this.tasks].sort((a, b) => a[1].at - b[1].at)) {
      if (task.at <= this.time && this.tasks.delete(id)) task.fn();
    }
    await new Promise(resolve => setImmediate(resolve));
  }
}

class Driver {
  constructor() { this.dials = 0; this.starts = 0; this.ends = 0; this.closes = 0; this.call = null; this.plays = []; this.disarmed = []; this.targets = []; }
  async start() { this.starts++; if (this.startError) throw this.startError; }
  async completeLink() { return !!this.linked; }
  async close() { this.closes++; this.call = null; this.releaseDial?.(); }
  async abort() { return this.close(); }
  async snapshot() { return this.call ? { ...this.call, audience: this.call.audience ?? { known: true, connectedHumans: 1, source: 'native_connected_peer' } } : { active: false }; }
  async dial(group, { cancelled }) {
    if (cancelled()) throw new ServiceError('CANCELLED', 'cancelled');
    this.dials++;
    this.targets.push(group);
    if (this.dialError) throw this.dialError;
    if (this.hangDial) await new Promise((_, reject) => { this.releaseDial = () => { const e = new Error('browser closed'); e.dispatched = true; reject(e); }; });
    this.call = { id: `native-${this.dials}`, active: true, outgoing: true, connected: false,
      isGroup: group.kind === 'group', groupId: group.kind === 'group' ? group.id : null };
    return this.call;
  }
  async end(id) {
    if (this.call && this.call.id !== id) throw new ServiceError('CALL_CHANGED', 'different call');
    this.ends++; this.call = null;
  }
  async disarmAudio(token) { this.disarmed.push(token); }
  async playAudio(id, playbackId, data, volume) {
    if (this.call?.id !== id || !this.call.connected) throw new ServiceError('AUDIO_CALL_CHANGED', 'changed');
    if (this.playError) throw this.playError;
    this.plays.push({ id, playbackId, volume });
    this.call.audio = { playback: { id: playbackId, state: 'playing' }, microphoneStreams: 1 };
  }
  async stopAudio(id) {
    if (this.call && this.call.id !== id) throw new ServiceError('AUDIO_CALL_CHANGED', 'changed');
    if (this.call?.audio?.playback) this.call.audio.playback.state = 'stopped';
  }
  async pauseAudio(nativeId, id, offset) {
    this.call.audio.playback = { ...this.call.audio.playback, id, state: 'paused', positionSeconds: offset };
  }
  async resumeAudio(nativeId, id, offset) {
    this.call.audio.playback = { ...this.call.audio.playback, id, state: 'playing', positionSeconds: offset };
  }
  async volume(id, volume) {
    if (this.call?.id !== id) throw new ServiceError('AUDIO_CALL_CHANGED', 'changed');
    this.call.audio.playback.volume = volume;
  }
}

async function fixture(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-calls-test-'));
  const journal = new Journal(path.join(dir, 'journal.json'));
  const driver = new Driver(), clock = new Clock();
  const manager = new CallManager({ driver, journal, clock, group: { id: 'lab@g.us', name: 'Botsky Lab' } });
  const asset = { id: 'a'.repeat(64), durationSeconds: 1.4 };
  manager.audioStore = {
    get: async id => { if (!['tone', asset.id].includes(id)) throw new ServiceError('AUDIO_NOT_FOUND', 'missing', 404); return asset; },
    read: async id => ({ asset: await manager.audioStore.get(id), data: Buffer.from('wave-fixture') }),
  };
  await manager.boot();
  t.after(async () => { await manager.stop(); await fs.rm(dir, { recursive: true, force: true }); });
  return { dir, journal, driver, clock, manager };
}

async function drain(manager) {
  for (let i = 0; i < 10; i++) {
    const queue = manager.queue, writes = manager.journal.writes;
    await queue; await writes;
    await new Promise(resolve => setImmediate(resolve));
    if (queue === manager.queue && writes === manager.journal.writes) return;
  }
  throw new Error('Manager did not settle');
}

test('Private outbound calls stop on remote hangup, never redial a retry and restart narration for a fresh request', async t => {
  const { manager, driver } = await fixture(t);
  const owner = '525511112222@s.whatsapp.net';
  manager.destinationPolicy = createCallDestinationPolicy({ lab: manager.group, env: { BOTSKY_OWNER_NUMBER: owner } });
  const options = { key: 'pm04-private-first', targetJid: owner, origin: { chatId: owner, requesterId: owner }, audioId: 'tone', durationFromAnswer: true };
  const first = await manager.startCall(options); await drain(manager);
  assert.equal(driver.targets[0].kind, 'private');
  assert.equal(driver.targets[0].id, owner);
  assert.equal(manager.active.groupId, null);
  assert.equal(driver.plays.length, 0);
  driver.call.connected = true; await manager.serial(() => manager.poll());
  assert.equal(driver.plays.length, 1);
  driver.call = null; await manager.serial(() => manager.poll());
  assert.equal(manager.getCall(first.call.id).state, 'ended');
  assert.ok(driver.disarmed.includes(first.call.id));
  assert.equal((await manager.startCall(options)).replayed, true);
  assert.equal(driver.dials, 1);
  await manager.startCall({ ...options, key: 'pm04-private-second' }); await drain(manager);
  driver.call.connected = true; await manager.serial(() => manager.poll());
  assert.equal(driver.dials, 2);
  assert.equal(driver.plays.length, 2);
  assert.notEqual(driver.plays[0].playbackId, driver.plays[1].playbackId);
});

test('Service authorization rejects disabled private targets and cross-chat orders from groups before reservation or dialing', async t => {
  const { manager, driver, journal } = await fixture(t);
  const owner = '525511112222@s.whatsapp.net', other = '525533334444@s.whatsapp.net';
  manager.destinationPolicy = createCallDestinationPolicy({ lab: manager.group, env: { BOTSKY_OWNER_NUMBER: owner } });
  await assert.rejects(manager.startCall({ key: 'pm04-disabled-peer', targetJid: other }), { code: 'DESTINATION_NOT_ENABLED' });
  await assert.rejects(manager.startCall({ key: 'pm04-forged-owner', targetJid: owner, origin: { chatId: other, requesterId: owner } }), { code: 'CALL_IDENTITY_UNKNOWN' });
  await assert.rejects(manager.startCall({ key: 'pm04-owner-in-group', targetJid: owner, origin: { chatId: '120363000000001@g.us', requesterId: owner } }), { code: 'CALL_DESTINATION_DENIED' });
  assert.equal(driver.dials, 0);
  assert.equal(journal.records.length, 0);
});

test('A private rejection before dispatch acknowledgement closes its journal entry and never recovers or redials', async t => {
  const { manager, driver } = await fixture(t);
  const owner = '525511112222@s.whatsapp.net';
  manager.destinationPolicy = createCallDestinationPolicy({ lab: manager.group, env: { BOTSKY_OWNER_NUMBER: owner } });
  driver.dial = async () => { driver.dials++; return { id: 'rejected-immediately', active: false, outgoing: true, state: 'REJECTED' }; };
  const options = { key: 'pm04-rejected-private', targetJid: owner };
  const result = await manager.startCall(options); await drain(manager);
  assert.equal(manager.getCall(result.call.id).reason, 'remote_rejected');
  assert.equal(manager.state, 'ready');
  assert.equal(driver.ends, 0);
  assert.ok(driver.disarmed.includes(result.call.id));
  assert.equal((await manager.startCall(options)).replayed, true);
  assert.equal(driver.dials, 1);
});

test('Group audience keeps a single playback through initiator departure, late join and an empty grace period', async t => {
  const { manager, driver, clock } = await fixture(t);
  const { call } = await manager.startCall({ key: 'audience-group-playback', audioId: 'tone', durationFromAnswer: true });
  await drain(manager);
  driver.call.connected = true;
  const observe = async count => {
    driver.call.audience = { known: true, connectedHumans: count, source: 'native_connected_participants' };
    await manager.serial(() => manager.poll()); await drain(manager);
  };
  await observe(0);
  clock.time += 6000; await observe(0);
  assert.equal(driver.plays.length, 0);
  assert.equal(manager.active.connectedAt, undefined); // Transport alone is not an answer.
  await observe(2);
  assert.equal(driver.plays.length, 1);
  const deadline = manager.active.expiresAt;
  await observe(1); // The initiator has left; one human remains.
  assert.equal(driver.ends, 0);
  await observe(2); // A late arrival must not restart the narration or deadline.
  assert.equal(driver.plays.length, 1);
  assert.equal(manager.active.expiresAt, deadline);
  await observe(0);
  clock.time += 4000; await observe(1); // Rejoin cancels the empty countdown.
  clock.time += 2000; await observe(1);
  assert.equal(driver.ends, 0);
  await observe(0);
  clock.time += 4999; await observe(0);
  assert.equal(driver.ends, 0);
  clock.time += 1; await observe(0);
  assert.equal(manager.getCall(call.id).reason, 'audience_empty');
  assert.equal(driver.ends, 1);
  assert.equal(driver.plays.length, 1);
  assert.equal(manager.active, null);
});

test('The requested group and the observed native representation are recorded separately', async t => {
  const { manager, driver } = await fixture(t);
  await manager.startCall({ key: 'pm04-native-representation' }); await drain(manager);
  assert.equal(manager.active.destinationKind, 'group');
  assert.deepEqual(manager.active.nativeRepresentation, { kind: 'group', groupContextMatches: true });
  driver.call.isGroup = false; driver.call.groupId = null; driver.call.connected = true;
  await manager.serial(() => manager.poll());
  assert.equal(manager.active.destinationKind, 'group');
  assert.deepEqual(manager.active.nativeRepresentation, { kind: 'private', groupContextMatches: false });
});

test('Unknown audience is distinct from empty, clears its countdown, and closes after a bounded loss of telemetry', async t => {
  const { manager, driver, clock } = await fixture(t);
  const { call } = await manager.startCall({ key: 'audience-telemetry-loss', audioId: 'tone' });
  await drain(manager); driver.call.connected = true;
  const observe = async (known, count) => {
    driver.call.audience = { known, connectedHumans: count, source: known ? 'native_connected_participants' : 'unavailable' };
    await manager.serial(() => manager.poll()); await drain(manager);
  };
  await observe(true, 1);
  await observe(true, 0);
  clock.time += 4000; await observe(false, null);
  clock.time += 5000; await observe(false, null);
  assert.equal(driver.ends, 0); // Missing data cannot finish the old empty countdown.
  await observe(true, 1);
  clock.time += 15000; await observe(false, null);
  assert.equal(driver.ends, 0); // A new loss starts a new countdown.
  clock.time += 14999; await observe(false, null);
  assert.equal(driver.ends, 0);
  clock.time += 1; await observe(false, null);
  assert.equal(manager.getCall(call.id).reason, 'audience_unavailable');
  assert.equal(driver.ends, 1);
});

test('Live starts only with an audience and is stopped and disarmed when the last human leaves', async t => {
  const { manager, driver, clock } = await fixture(t);
  const events = [];
  manager.liveController = { prepare: async () => {}, start: async r => events.push(['start', r.id]), suspend: async r => events.push(['suspend', r.id]), stop: async id => events.push(['stop', id]) };
  const { call } = await manager.startCall({ key: 'audience-live-lifecycle', live: true, durationFromAnswer: true });
  assert.equal(manager.active.liveInterruption, true);
  await drain(manager); driver.call.connected = true;
  driver.call.audience = { known: true, connectedHumans: 0, source: 'native_connected_lonely' };
  await manager.serial(() => manager.poll());
  assert.equal(events.length, 0);
  driver.call.audience.connectedHumans = 1;
  await manager.serial(() => manager.poll());
  await manager.serial(() => manager.poll());
  assert.equal(events.filter(e => e[0] === 'start').length, 1);
  driver.call.audience.connectedHumans = 0;
  await manager.serial(() => manager.poll());
  clock.time += 5000; await manager.serial(() => manager.poll()); await drain(manager);
  assert.equal(manager.getCall(call.id).reason, 'audience_empty');
  assert.ok(events.some(e => e[0] === 'stop' && e[1] === call.id));
  assert.ok(driver.disarmed.includes(call.id));
});

function incomingFixture(manager, driver) {
  const events = [];
  manager.incomingPolicy = createIncomingPolicy({ CALLS_AUTOANSWER_OWNER: 'true', ALLOWED_NUMBERS_ADMIN: '5215512345678' });
  manager.liveController = { prepare: async record => events.push(['prepare', record.id]), start: async record => events.push(['start', record.id]), stop: async id => events.push(['stop', id]), status: () => null };
  driver.call = { id: 'incoming-native', active: true, outgoing: false, state: 3, connected: false, peerJid: '525512345678@s.whatsapp.net' };
  driver.answer = async (snapshot, options) => { assert.equal(options.cancelled(), false); events.push(['accept', snapshot.id]); driver.call.connected = true; driver.call.state = 6; return driver.call; };
  return events;
}

test('An owned incoming voice call is journaled, accepted once and receives Live after connecting', async t => {
  const { manager, driver } = await fixture(t);
  const events = incomingFixture(manager, driver);
  await manager.serial(() => manager.poll());
  assert.equal(manager.active.direction, 'incoming'); assert.equal(manager.active.state, 'connected');
  assert.equal(manager.active.liveInterruption, undefined);
  assert.equal(driver.dials, 0); assert.deepEqual(events.map(e => e[0]), ['prepare', 'accept']);
  assert.equal(manager.publicCall(manager.active).incomingPeer, undefined);
  await manager.serial(() => manager.poll());
  assert.equal(events.filter(e => e[0] === 'start').length, 1);
  driver.call = null; await manager.serial(() => manager.poll());
  assert.equal(manager.active, null); assert.equal(events.at(-1)[0], 'stop');
  driver.call = { id: 'incoming-native', active: true, outgoing: false, state: 3, peerJid: '525512345678@s.whatsapp.net' };
  await manager.serial(() => manager.poll());
  assert.equal(events.filter(e => e[0] === 'accept').length, 1);
});

test('A private call becoming natively lonely stops Live immediately without the group grace', async t => {
  const { manager, driver, clock } = await fixture(t);
  const events = incomingFixture(manager, driver);
  await manager.serial(() => manager.poll());
  await manager.serial(() => manager.poll());
  const id = manager.active.id, now = clock.now();
  driver.call.audience = { known: true, connectedHumans: 0, source: 'native_connected_lonely' };
  await manager.serial(() => manager.poll()); await drain(manager);
  assert.equal(manager.getCall(id).reason, 'remote_left');
  assert.equal(manager.getCall(id).endedAt, now);
  assert.equal(events.at(-1)[0], 'stop');
  assert.equal(driver.ends, 1);
});

test('Owned incoming video reserves video Live, accepts once and cleans up on remote hangup', async t => {
  const { manager, driver, clock } = await fixture(t);
  const events = incomingFixture(manager, driver);
  driver.call.isVideo = true;
  manager.liveController.prepare = async record => {
    assert.equal(record.video, true); assert.equal(record.live, true);
    assert.equal(record.expiresAt - clock.now(), 45000);
    events.push(['prepare', record.id]);
  };
  await manager.serial(() => manager.poll());
  const id = manager.active.id;
  assert.equal(manager.active.direction, 'incoming'); assert.equal(manager.active.video, true);
  assert.equal(manager.active.maxSeconds, null); assert.equal(manager.active.expiresAt, null);
  await manager.serial(() => manager.poll());
  assert.equal(events.filter(e => e[0] === 'start').length, 1);
  assert.equal(driver.dials, 0);
  driver.call = null; await manager.serial(() => manager.poll());
  assert.equal(manager.active, null); assert.ok(driver.disarmed.includes(id));
  assert.equal(events.filter(e => e[0] === 'accept').length, 1);
});

test('Incoming callers outside policy and missing durable storage cannot trigger acceptance', async t => {
  const { manager, driver, journal } = await fixture(t);
  const events = incomingFixture(manager, driver);
  driver.call.peerJid = '999999999999@s.whatsapp.net'; await manager.serial(() => manager.poll());
  assert.equal(events.length, 0);
  driver.call.peerJid = '525512345678@s.whatsapp.net'; journal.save = async () => { throw Error('disk full'); };
  await manager.serial(() => manager.poll());
  assert.equal(events.length, 0); assert.equal(manager.active, null);
});

test('Incoming Live provider failure or a changed call cannot lead to answering another caller', async t => {
  const { manager, driver } = await fixture(t);
  const events = incomingFixture(manager, driver);
  manager.liveController.prepare = async () => { throw new ServiceError('LIVE_NO_KEY', 'test'); };
  await manager.serial(() => manager.poll());
  assert.equal(events.some(e => e[0] === 'accept'), false); assert.equal(driver.ends, 0);
  driver.call.id = 'incoming-next'; manager.liveController.prepare = async () => {};
  driver.answer = async () => { throw new ServiceError('CALL_CHANGED', 'changed'); };
  await manager.serial(() => manager.poll());
  assert.equal(driver.ends, 0); assert.equal(manager.active, null);
});

test('Live prepares before dialing, captures only after answer and stops on remote hangup', async t => {
  const { manager, driver } = await fixture(t);
  const events = [];
  manager.liveController = { prepare: async record => { assert.equal(driver.dials, 0); events.push(['prepare', record.id]); },
    start: async record => events.push(['start', record.id]), stop: async id => events.push(['stop', id]), status: () => null };
  const result = await manager.startCall({ key: 'live-call-test', live: true, maxSeconds: 300, durationFromAnswer: true });
  await drain(manager); assert.deepEqual(events.map(e => e[0]), ['prepare']);
  await assert.rejects(manager.startCall({ key: 'live-call-test', live: false, maxSeconds: 300, durationFromAnswer: true }), { code: 'KEY_CONFLICT' });
  driver.call.connected = true; await manager.serial(() => manager.poll()); await manager.serial(() => manager.poll());
  assert.equal(events.filter(e => e[0] === 'start').length, 1);
  assert.equal(driver.plays.length, 0);
  await assert.rejects(manager.playAudio({ key: 'not-while-live', audioId: 'tone' }), { code: 'LIVE_AUDIO_EXCLUSIVE' });
  driver.call = null; await manager.serial(() => manager.poll());
  assert.equal(events.at(-1)[0], 'stop');
  assert.equal(manager.getCall(result.call.id).state, 'ended');
});

test('A Live preparation failure cannot dial, and Live cannot mix with a prepared narration', async t => {
  const { manager, driver } = await fixture(t);
  manager.liveController = { prepare: async () => { throw new ServiceError('LIVE_NO_KEY', 'test'); }, stop: async () => {}, status: () => null };
  await assert.rejects(manager.startCall({ key: 'mixed-live-audio', live: true, audioId: 'tone' }), { code: 'INVALID_LIVE_POLICY' });
  const started = await manager.startCall({ key: 'failed-live-test', live: true }); await drain(manager);
  assert.equal(driver.dials, 0);
  assert.equal(manager.getCall(started.call.id).reason, 'LIVE_NO_KEY');
});

test('Narration gets its full budget after answer and hangs up when the audio ends', async t => {
  const { manager, driver, clock } = await fixture(t);
  const started = await manager.startCall({ key: 'ten-minute-narration', maxSeconds: 625, audioId: 'tone', durationFromAnswer: true, endAfterAudio: true });
  await drain(manager);
  await clock.advance(30000); await drain(manager);
  assert.equal(driver.plays.length, 0);
  driver.call.connected = true; await manager.serial(() => manager.poll());
  assert.equal(manager.active.expiresAt, clock.now() + 625000);
  assert.equal(driver.plays.length, 1);
  await clock.advance(60000); await drain(manager);
  assert.equal(manager.active.state, 'connected');
  driver.call.audio.playback.state = 'ended';
  await manager.serial(() => manager.poll()); await drain(manager);
  assert.equal(manager.active, null);
  assert.equal(manager.getCall(started.call.id).reason, 'audio_completed');
  assert.equal(driver.ends, 1);
});

test('An unanswered narration has a short ringing timeout and never emits audio', async t => {
  const { manager, driver, clock } = await fixture(t);
  const started = await manager.startCall({ key: 'unanswered-long-story', maxSeconds: 625, audioId: 'tone', durationFromAnswer: true, endAfterAudio: true });
  await drain(manager); await clock.advance(45001); await drain(manager);
  assert.equal(manager.getCall(started.call.id).reason, 'answer_timeout');
  assert.equal(driver.plays.length, 0);
});

test('Audio policy is part of idempotency and audio failure closes a narration call', async t => {
  const { manager, driver } = await fixture(t);
  const options = { key: 'narration-audio-failure', audioId: 'tone', endAfterAudio: true, durationFromAnswer: true };
  const started = await manager.startCall(options); await drain(manager);
  await assert.rejects(manager.startCall({ ...options, endAfterAudio: false }), { code: 'KEY_CONFLICT' });
  driver.call.connected = true; driver.playError = new ServiceError('AUDIO_PLAY_FAILED', 'test');
  await manager.serial(() => manager.poll()); await drain(manager);
  assert.equal(manager.getCall(started.call.id).reason, 'audio_failed');
  assert.equal(driver.ends, 1);
});

test('Concurrent retries persist one reservation and dispatch one call', async t => {
  const { manager, driver, journal } = await fixture(t);
  const results = await Promise.all(Array.from({ length: 12 }, () => manager.startCall({ key: 'same-request' })));
  await drain(manager);
  assert.equal(new Set(results.map(r => r.call.id)).size, 1);
  assert.equal(results.filter(r => !r.replayed).length, 1);
  assert.equal(driver.dials, 1); assert.equal(journal.records.length, 1);
  const stored = JSON.parse(await fs.readFile(journal.file, 'utf8'));
  assert.equal(stored.records[0].nativeId, 'native-1');
  assert.equal(manager.status().activeCall.nativeId, undefined);
  assert.equal(manager.status().activeCall.key, undefined);
  await assert.rejects(manager.startCall({ key: 'same-request', maxSeconds: 20 }), { code: 'KEY_CONFLICT' });
  await assert.rejects(manager.startCall({ key: 'other-request' }), { code: 'CALL_BUSY' });
  assert.equal(driver.dials, 1);
});

test('Other groups, invalid duration and invalid keys cannot dispatch', async t => {
  const { manager, driver } = await fixture(t);
  await assert.rejects(manager.startCall({ key: 'a-valid-key', groupId: 'friends@g.us' }), { code: 'DESTINATION_NOT_ENABLED' });
  for (const maxSeconds of [0, 4, 961, 3.5, '30']) await assert.rejects(manager.startCall({ key: 'a-valid-key', maxSeconds }), { code: 'INVALID_DURATION' });
  await assert.rejects(manager.startCall({ key: 'short' }), { code: 'INVALID_KEY' });
  assert.equal(driver.dials, 0);
});

test('Remote hangup clears ownership and old deadline cannot end the next call', async t => {
  const { manager, driver, clock } = await fixture(t);
  const first = await manager.startCall({ key: 'first-request', maxSeconds: 5 });
  await drain(manager);
  driver.call.connected = true; await manager.serial(() => manager.poll());
  assert.equal(manager.status().activeCall.state, 'connected');
  driver.call = null; await manager.serial(() => manager.poll());
  assert.equal(manager.getCall(first.call.id).reason, 'remote_or_native_end');
  assert.equal((await manager.endCall(first.call.id)).alreadyEnded, true);
  await manager.startCall({ key: 'second-request', maxSeconds: 60 });
  await drain(manager); await clock.advance(5001); await drain(manager);
  assert.equal(driver.ends, 0);
  assert.equal(manager.status().activeCall.state, 'dialing');
});

test('A deadline ends an unanswered owned call', async t => {
  const { manager, driver, clock } = await fixture(t);
  const started = await manager.startCall({ key: 'deadline-request', maxSeconds: 5 });
  await drain(manager); await clock.advance(5000); await drain(manager);
  assert.equal(driver.ends, 1); assert.equal(manager.status().activeCall, null);
  assert.equal(manager.getCall(started.call.id).reason, 'duration_limit');
});

test('A changed native call is never terminated as the owned call', async t => {
  const { manager, driver } = await fixture(t);
  const started = await manager.startCall({ key: 'changed-request' });
  await drain(manager);
  driver.call = { id: 'incoming-unrelated', active: true, connected: false, outgoing: false };
  await manager.endCall(started.call.id);
  assert.equal(driver.ends, 0); assert.equal(driver.call.id, 'incoming-unrelated');
  assert.equal(manager.getCall(started.call.id).state, 'interrupted');
});

test('Browser loss interrupts the journal and recovery never redials', async t => {
  const { manager, driver, clock } = await fixture(t);
  const started = await manager.startCall({ key: 'loss-request' });
  await drain(manager); await manager.lost('browser_crashed');
  assert.equal(manager.getCall(started.call.id).state, 'interrupted');
  await clock.advance(2000); await drain(manager);
  assert.equal(driver.dials, 1); assert.equal(driver.starts, 2);
  assert.equal(manager.state, 'ready');
  const replay = await manager.startCall({ key: 'loss-request' });
  assert.equal(replay.replayed, true); assert.equal(replay.call.state, 'interrupted');
});

test('An ambiguous dispatch closes the browser and is not retried', async t => {
  const { manager, driver, clock } = await fixture(t);
  const error = new ServiceError('DIAL_UNCONFIRMED', 'uncertain'); error.dispatched = true;
  driver.dialError = error;
  const result = await manager.startCall({ key: 'uncertain-request' });
  await drain(manager);
  assert.equal(manager.getCall(result.call.id).state, 'interrupted');
  assert.equal(manager.state, 'recovering');
  delete driver.dialError; await clock.advance(2000); await drain(manager);
  assert.equal(driver.dials, 1);
  assert.equal((await manager.startCall({ key: 'uncertain-request' })).replayed, true);
});

test('Emergency watchdog closes a hung dial independently of its command queue', async t => {
  const { manager, driver, clock } = await fixture(t);
  driver.hangDial = true;
  await manager.startCall({ key: 'hung-request', maxSeconds: 5 });
  await new Promise(resolve => setImmediate(resolve));
  await clock.advance(5000); await manager.journal.writes;
  await clock.advance(5000); await drain(manager);
  assert.equal(manager.status().activeCall, null);
  assert.ok(driver.closes >= 2);
  assert.equal(driver.dials, 1);
});

test('Restart restores idempotency and marks an unfinished reservation interrupted', async t => {
  const { manager, driver, journal, clock } = await fixture(t);
  const first = await manager.startCall({ key: 'persisted-request' });
  await drain(manager);
  // Simulate process loss, preserving the real on-disk journal.
  manager.stopping = true;
  for (const name of [...manager.timers.keys()]) manager.clearTimer(name);
  manager.active = null; await driver.close();
  const driver2 = new Driver(), journal2 = new Journal(journal.file);
  const restored = new CallManager({ driver: driver2, journal: journal2, clock, group: manager.group });
  t.after(() => restored.stop());
  await restored.boot();
  const replay = await restored.startCall({ key: 'persisted-request' });
  assert.equal(replay.replayed, true); assert.equal(replay.call.id, first.call.id);
  assert.equal(replay.call.state, 'interrupted'); assert.equal(driver2.dials, 0);
});

test('A corrupt journal fails closed instead of silently forgetting request keys', async t => {
  const { journal } = await fixture(t);
  await fs.writeFile(journal.file, '{broken');
  await assert.rejects(new Journal(journal.file).load(), { code: 'JOURNAL_INVALID' });
});

test('Shutdown terminates an owned call and prevents future calls', async t => {
  const { manager, driver } = await fixture(t);
  await manager.startCall({ key: 'shutdown-request' }); await drain(manager);
  await assert.rejects(manager.restartBrowser(), { code: 'CALL_BUSY' });
  await manager.stop();
  assert.equal(driver.ends, 1); assert.equal(manager.state, 'stopped');
  await assert.rejects(manager.startCall({ key: 'after-shutdown' }), { code: 'STOPPING' });
});

test('A failed durable reservation cannot dispatch a call', async t => {
  const { manager, driver, journal } = await fixture(t);
  journal.save = async () => { throw new Error('disk full'); };
  await assert.rejects(manager.startCall({ key: 'storage-request' }), /disk full/);
  assert.equal(driver.dials, 0); assert.equal(manager.active, null);
});

test('A new incoming call observed during dispatch is preserved', async t => {
  const { manager, driver } = await fixture(t);
  const error = new ServiceError('CALL_CHANGED', 'incoming call'); error.dispatched = true;
  driver.dialError = error;
  await manager.startCall({ key: 'incoming-request' }); await drain(manager);
  assert.equal(driver.closes, 1); // initial boot only
  assert.equal(manager.state, 'ready');
  assert.equal(manager.status().lastCall.state, 'interrupted');
});

test('Linking is polled in the same browser without rotating the QR session', async t => {
  const { manager, driver, clock } = await fixture(t);
  await manager.driver.close(); manager.state = 'recovering';
  driver.startError = new ServiceError('NEEDS_LINK', 'link required', 503);
  await manager.recover();
  assert.equal(manager.state, 'needs_link');
  const starts = driver.starts;
  await clock.advance(2000); await drain(manager);
  assert.equal(driver.starts, starts); assert.equal(manager.state, 'needs_link');
  driver.linked = true;
  await clock.advance(2000); await drain(manager);
  assert.equal(manager.state, 'ready'); assert.equal(driver.starts, starts);
  assert.equal(driver.dials, 0);
});

test('Autoplay waits for answer, executes once, supports volume and preserves call idempotency', async t => {
  const { manager, driver } = await fixture(t);
  const started = await manager.startCall({ key: 'audio-call-request', audioId: 'tone', volume: 0.6 });
  await drain(manager); await manager.serial(() => manager.poll());
  assert.equal(driver.plays.length, 0);
  driver.call.connected = true;
  await manager.serial(() => manager.poll()); await manager.serial(() => manager.poll());
  assert.equal(driver.plays.length, 1); assert.equal(driver.plays[0].volume, 0.6);
  assert.equal(manager.status().activeCall.audioRequests, undefined);
  await manager.setVolume({ volume: 0.3 });
  const retry = await manager.startCall({ key: 'audio-call-request', audioId: 'tone', volume: 0.6 });
  assert.equal(retry.replayed, true); assert.equal(retry.call.id, started.call.id);
  assert.equal(driver.dials, 1);
  await assert.rejects(manager.startCall({ key: 'audio-call-request', audioId: 'tone', volume: 0.5 }), { code: 'KEY_CONFLICT' });
});

test('Stop/replay does not repeat a playback after a retry or a remote hangup', async t => {
  const { manager, driver } = await fixture(t);
  const started = await manager.startCall({ key: 'audio-manual-call' }); await drain(manager);
  driver.call.connected = true; await manager.serial(() => manager.poll());
  const first = await manager.playAudio({ key: 'first-playback', audioId: 'tone' });
  await assert.rejects(manager.playAudio({ key: 'other-playback', audioId: 'tone' }), { code: 'AUDIO_BUSY' });
  await manager.setVolume({ volume: 0.2 });
  const retry = await manager.playAudio({ key: 'first-playback', audioId: 'tone' });
  assert.equal(retry.replayed, true); assert.equal(retry.playback.id, first.playback.id);
  assert.equal(driver.plays.length, 1);
  await manager.stopAudio(); assert.equal((await manager.stopAudio()).alreadyStopped, true);
  await manager.playAudio({ key: 'second-playback', audioId: 'tone' });
  driver.call = null; await manager.serial(() => manager.poll());
  assert.equal(manager.getCall(started.call.id).playback.state, 'stopped');
  const afterHangup = await manager.playAudio({ callId: started.call.id, key: 'second-playback', audioId: 'tone' });
  assert.equal(afterHangup.replayed, true); assert.equal(driver.plays.length, 2);
  await assert.rejects(manager.playAudio({ callId: started.call.id, key: 'new-after-hangup', audioId: 'tone' }), { code: 'CALL_NOT_CONNECTED' });
  assert.ok(driver.disarmed.includes(started.call.id));
});

test('Unknown audio and invalid volume fail before dialing; disconnected audio never plays', async t => {
  const { manager, driver } = await fixture(t);
  await assert.rejects(manager.startCall({ key: 'bad-audio-call', audioId: 'missing' }), { code: 'AUDIO_NOT_FOUND' });
  await assert.rejects(manager.startCall({ key: 'bad-volume-call', volume: 2 }), { code: 'INVALID_VOLUME' });
  assert.equal(driver.dials, 0);
  await manager.startCall({ key: 'not-answered-call' }); await drain(manager);
  await assert.rejects(manager.playAudio({ key: 'before-answer', audioId: 'tone' }), { code: 'CALL_NOT_CONNECTED' });
  assert.equal(driver.plays.length, 0);
});

test('Uncertain audio commands are recorded and cannot be automatically replayed', async t => {
  const { manager, driver } = await fixture(t);
  await manager.startCall({ key: 'uncertain-audio-call' }); await drain(manager);
  driver.call.connected = true; await manager.serial(() => manager.poll());
  driver.playError = new ServiceError('AUDIO_PLAY_TIMEOUT', 'uncertain', 503);
  await assert.rejects(manager.playAudio({ key: 'uncertain-playback', audioId: 'tone' }), { code: 'AUDIO_PLAY_TIMEOUT' });
  const retry = await manager.playAudio({ key: 'uncertain-playback', audioId: 'tone' });
  assert.equal(retry.replayed, true); assert.equal(retry.playback.state, 'interrupted');
  assert.equal(driver.plays.length, 0);
});

test('A failed playback reservation emits no audio and does not leave a phantom busy player', async t => {
  const { manager, driver, journal } = await fixture(t);
  await manager.startCall({ key: 'audio-storage-call' }); await drain(manager);
  driver.call.connected = true; await manager.serial(() => manager.poll());
  const save = journal.save.bind(journal);
  journal.save = async () => { throw new Error('disk full'); };
  await assert.rejects(manager.playAudio({ key: 'audio-storage-key', audioId: 'tone' }), /disk full/);
  assert.equal(driver.plays.length, 0); assert.equal(manager.active.playback, undefined);
  journal.save = save;
  await manager.playAudio({ key: 'audio-storage-key', audioId: 'tone' });
  assert.equal(driver.plays.length, 1);
});

test('PM05A: cancelled offer key survives restart and blocks a delayed start', async t => {
  const { manager, journal, driver } = await fixture(t);
  const key = 'cancel-before-offer';
  await manager.cancelKey(key);
  const restored = new Journal(journal.file); await restored.load();
  assert.equal(Object.hasOwn(restored.cancelledKeys, key), true);
  await assert.rejects(manager.startCall({ key }), { code: 'CANCELLED' });
  assert.equal(driver.dials, 0);
});

test('PM05A: cancellation during preload is visible before native dispatch', async t => {
  const { manager, driver } = await fixture(t);
  let release, entered;
  const reached = new Promise(resolve => { entered = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  driver.dial = async (_, { cancelled }) => { entered(); await gate; assert.equal(cancelled(), true); throw new ServiceError('CANCELLED', 'cancelled'); };
  const result = await manager.startCall({ key: 'cancel-preload' }); await reached;
  const ending = manager.cancelKey('cancel-preload');
  assert.equal(manager.active.endRequested, 'cancelled');
  release(); await ending; await drain(manager);
  assert.equal(manager.getCall(result.call.id).state, 'ended');
  assert.equal(driver.dials, 0);
  await assert.rejects(manager.startCall({ key: 'cancel-preload' }), { code: 'CANCELLED' });
});

test('PM05A: cancelled playback cannot start later and stops only its own audio', async t => {
  const { manager, driver } = await fixture(t);
  const result = await manager.startCall({ key: 'playback-host' }); await drain(manager);
  driver.call.connected = true; await manager.poll();
  await manager.cancelKey('audio-cancelled');
  await assert.rejects(manager.playAudio({ callId: result.call.id, key: 'audio-cancelled', audioId: 'tone' }), { code: 'CANCELLED' });
  await manager.playAudio({ callId: result.call.id, key: 'audio-playing', audioId: 'tone' });
  await manager.cancelKey('audio-playing');
  assert.equal(manager.active.playback.state, 'stopped');
  assert.equal(manager.active.state, 'connected');
  await manager.playAudio({ callId: result.call.id, key: 'audio-successor', audioId: 'tone' });
  await manager.cancelKey('audio-playing');
  assert.equal(manager.active.playback.state, 'playing');
  assert.equal(driver.plays.length, 2);
});

async function recoveryFixture(t) {
  const f = await fixture(t);
  f.driver.pauses = []; f.driver.resumes = [];
  f.driver.pauseAudio = async (nativeId, id, offset) => { f.driver.pauses.push({ nativeId, id, offset }); f.driver.call.audio.playback.state = 'paused'; };
  f.driver.resumeAudio = async (nativeId, id, offset) => { f.driver.resumes.push({ nativeId, id, offset }); f.driver.call.audio.playback.state = 'playing'; };
  const started = await f.manager.startCall({ key: 'recoverable-call', audioId: 'tone', endAfterAudio: true, durationFromAnswer: true });
  await drain(f.manager);
  f.driver.call.connected = true; f.driver.call.state = 6; await f.manager.poll();
  f.driver.call.audio.playback.positionSeconds = 0.5; await f.manager.poll();
  return { ...f, started };
}

test('H4: scheduled poll closes a failed Live session without treating it as browser loss', async t => {
  const f = await fixture(t);
  const live = { callId: null, suspended: false, stopped: false };
  let resumes = 0, suspends = 0;
  f.manager.liveController = {
    active: live,
    prepare: async () => {},
    start: async record => { live.callId = record.id; live.suspended = false; },
    suspend: async () => { suspends++; live.suspended = true; },
    resume: async () => { resumes++; throw new ServiceError('LIVE_OWNER_CHANGED', 'synthetic Live failure'); },
    stop: async () => {},
    status: () => null,
  };
  await f.manager.startCall({ key: 'h4-connected-live', live: true, maxSeconds: 300 });
  await drain(f.manager);
  f.driver.call.connected = true; f.driver.call.state = 6;
  await f.manager.poll();
  const record = f.manager.active;
  assert.equal(record.connectedAt, f.clock.now());
  assert.equal(record.liveStarted, true);
  live.suspended = true;
  const closesBeforePollFailure = f.driver.closes;

  await f.clock.advance(1000); await drain(f.manager);
  assert.equal(resumes, 1);
  assert.equal(suspends, 0);
  assert.equal(f.driver.closes, closesBeforePollFailure);
  assert.equal(f.manager.state, 'ready');
  assert.equal(f.manager.active, null);
  assert.equal(record.reason, 'live_failed');
  assert.deepEqual(record.liveError, { code: 'LIVE_OWNER_CHANGED' });
  assert.equal(record.recovery, undefined);
});

test('PM05B: restores the same native call once and resumes its confirmed audio position without redial', async t => {
  const { manager, driver, clock, journal } = await recoveryFixture(t);
  const originalPlayback = manager.active.playback.id, expiresAt = manager.active.expiresAt;
  driver.call.connected = false; driver.call.state = 'CONNECTION_LOST'; await manager.poll();
  assert.equal(manager.active.state, 'recovering');
  assert.equal(driver.pauses[0].offset, 0.5);
  const saved = new Journal(journal.file); await saved.load(); assert.equal(saved.records.at(-1).recovery.attempts, 1);
  driver.call.connected = true; driver.call.state = 6;
  await clock.advance(1000); await drain(manager);
  assert.equal(manager.active.state, 'connected'); assert.equal(manager.active.recovery.phase, 'recovered');
  assert.equal(driver.dials, 1); assert.equal(driver.resumes[0].offset, 0.5);
  assert.equal(manager.active.playback.id, originalPlayback); assert.equal(manager.active.expiresAt, expiresAt);
  driver.call.connected = false; driver.call.state = 'CONNECTION_LOST'; await manager.poll(); await drain(manager);
  assert.equal(manager.active, null); assert.equal(driver.dials, 1);
});

test('H4: a failed recovery snapshot stays bounded and never invents another offer', async t => {
  const { manager, driver, clock } = await recoveryFixture(t);
  const record = manager.active;
  await manager.lost('synthetic_browser_loss');
  driver.recoverSnapshot = async () => { throw new ServiceError('SNAPSHOT_TIMEOUT', 'synthetic'); };
  await clock.advance(1000); await drain(manager);
  assert.equal(record.recovery.phase, 'waiting');
  assert.equal(record.liveError, undefined);
  assert.equal(driver.dials, 1);
  await clock.advance(12000); await drain(manager);
  assert.equal(record.state, 'interrupted');
  assert.equal(record.reason, 'recovery_timeout');
  assert.equal(manager.active, null);
  assert.equal(driver.dials, 1);
});

test('N12a: an absent audience pauses a recado at its observed position and rejoin resumes it once', async t => {
  const { manager, driver } = await fixture(t);
  await manager.startCall({ key: 'n12a-recado-continuity', audioId: 'tone', durationFromAnswer: true });
  await drain(manager); driver.call.connected = true;
  await manager.poll();
  const record = manager.active, playback = record.playback, expiresAt = record.expiresAt;
  driver.call.audio.playback.positionSeconds = 0.7;
  driver.call.audience = { known: false, connectedHumans: null };
  await manager.poll();
  assert.equal(playback.state, 'paused');
  assert.equal(playback.confirmedPositionSeconds, 0.7);
  driver.call.audience = { known: true, connectedHumans: 0 };
  await manager.poll();
  assert.equal(playback.state, 'paused');
  driver.call.audience.connectedHumans = 1;
  await manager.poll();
  assert.equal(record.playback, playback);
  assert.equal(playback.state, 'playing');
  assert.equal(driver.call.audio.playback.positionSeconds, 0.7);
  assert.equal(record.expiresAt, expiresAt);
  assert.equal(driver.plays.length, 1);
});

test('N12a: a recado ending as audience leaves is completed instead of paused at an invalid offset', async t => {
  const { manager, driver } = await fixture(t);
  await manager.startCall({ key: 'n12a-recado-final-frame', audioId: 'tone', endAfterAudio: true, durationFromAnswer: true });
  await drain(manager); driver.call.connected = true; await manager.poll();
  const record = manager.active;
  driver.pauseAudio = async () => { throw new Error('must not pause an ended recado'); };
  driver.call.audio.playback.positionSeconds = record.playback.durationSeconds;
  driver.call.audience = { known: true, connectedHumans: 0 };
  await manager.serial(() => manager.poll()); await drain(manager);
  assert.equal(record.reason, 'audio_completed');
  assert.equal(record.playback.state, 'ended');
  assert.equal(manager.state, 'ready');
  assert.equal(manager.active, null);
});

test('PM05B: two confirmed native failures permit one guarded redial with the same target and audio checkpoint', async t => {
  const { manager, driver, clock } = await recoveryFixture(t);
  const expiresAt = manager.active.expiresAt, logicalId = manager.active.id;
  const originalDial = driver.dial.bind(driver); let recoveryNativeId;
  driver.dial = (target, options) => { recoveryNativeId = options.recoveryNativeId; return originalDial(target, options); };
  driver.call.active = false; driver.call.connected = false; driver.call.state = 'FAILED';
  await manager.poll(); await clock.advance(1000); await drain(manager);
  assert.equal(driver.dials, 2); assert.equal(recoveryNativeId, 'native-1');
  assert.equal(manager.active.id, logicalId); assert.equal(manager.active.recovery.redialUsed, true);
  assert.equal(manager.active.audioToken, logicalId + '-recovery-1');
  assert.equal(driver.targets[0].id, driver.targets[1].id);
  driver.call.connected = true; driver.call.state = 6; await manager.poll();
  assert.equal(manager.active.state, 'connected');
  assert.equal(manager.active.playback.offsetSeconds, 0.5); assert.equal(driver.plays.length, 2);
  assert.equal(manager.active.expiresAt, expiresAt);
  driver.call.active = false; driver.call.connected = false; driver.call.state = 'FAILED';
  await manager.poll(); await drain(manager);
  assert.equal(driver.dials, 2); assert.equal(manager.active, null);
  assert.equal(driver.disarmed.at(-1), logicalId + '-recovery-1');
});

test('PM05B: remote hangup, rejection, no answer and locally ended FAILED never redial', async t => {
  for (const [state, userEnded] of [[0, false], ['ENDED', false], ['REJECTED', false], ['NOT_ANSWERED', false], ['FAILED', true]]) {
    const { manager, driver, clock } = await recoveryFixture(t);
    driver.call.active = false; driver.call.connected = false; driver.call.state = state; driver.call.userEnded = userEnded;
    await manager.poll(); await clock.advance(15000); await drain(manager);
    assert.equal(manager.active, null, String(state)); assert.equal(driver.dials, 1, String(state));
  }
});

test('PM05B: a temporary browser observation failure reuses the existing page without restarting or redialing', async t => {
  const { manager, driver, clock } = await recoveryFixture(t);
  await manager.lost('SNAPSHOT_TIMEOUT'); assert.equal(manager.state, 'recovering_call');
  await clock.advance(1000); await drain(manager);
  assert.equal(manager.state, 'ready'); assert.equal(manager.active.state, 'connected');
  assert.equal(driver.starts, 1); assert.equal(driver.dials, 1);
});

test('PM05B: unavailable browser and expired recovery window cannot authorize a new offer', async t => {
  const { manager, driver, clock } = await recoveryFixture(t);
  await manager.lost('browser_disconnected');
  driver.snapshot = async () => { throw new ServiceError('BROWSER_LOST', 'lost'); };
  for (let i = 0; i < 12; i++) { await clock.advance(1000); await drain(manager); }
  assert.equal(manager.active, null); assert.equal(driver.dials, 1);
  assert.equal(manager.journal.records.at(-1).recovery.phase, 'failed');
});

test('PM05B: cancelling during recovery prevents a late FAILED snapshot from redialing', async t => {
  const { manager, driver, clock } = await recoveryFixture(t);
  driver.call.state = 'CONNECTION_LOST'; driver.call.connected = false; await manager.poll();
  await manager.cancelKey('recoverable-call');
  await clock.advance(15000); await drain(manager);
  assert.equal(manager.active, null); assert.equal(driver.dials, 1);
});

test('PM05B: restart preserves the spent attempt and interrupts unfinished recovery without dispatch', async t => {
  const { manager, driver, clock, journal } = await recoveryFixture(t);
  driver.call.state = 'CONNECTION_LOST'; driver.call.connected = false; await manager.poll();
  const freshDriver = new Driver();
  const restarted = new CallManager({ driver: freshDriver, journal: new Journal(journal.file), group: manager.group, clock });
  t.after(() => restarted.stop()); await restarted.boot();
  assert.equal(restarted.journal.records.at(-1).recovery.attempts, 1);
  assert.equal(restarted.journal.records.at(-1).recovery.phase, 'failed');
  assert.equal(restarted.journal.records.at(-1).reason, 'service_restart');
  assert.equal(freshDriver.dials, 0); assert.equal(restarted.active, null);
});

test('PM05B: disappearance or another native call during the recovery probe never redials or hangs up that call', async t => {
  for (const different of [false, true]) {
    const { manager, driver, clock } = await recoveryFixture(t);
    driver.call.state = 'CONNECTION_LOST'; driver.call.connected = false; await manager.poll();
    driver.call = different ? { active: true, connected: true, id: 'foreign', outgoing: false } : null;
    await clock.advance(1000); await drain(manager);
    assert.equal(manager.active, null); assert.equal(driver.dials, 1); assert.equal(driver.ends, 0);
  }
});

test('PM05B: a failed connection before answer gets one attempt but an unanswered call does not', async t => {
  const { manager, driver, clock } = await fixture(t);
  await manager.startCall({ key: 'before-answer-failure' }); await drain(manager);
  driver.call.active = false; driver.call.state = 'FAILED'; await manager.poll();
  assert.equal(manager.active.recovery.attempts, 1);
  await clock.advance(1000); await drain(manager); assert.equal(driver.dials, 2);
  driver.call.active = false; driver.call.state = 'NOT_ANSWERED'; await manager.poll();
  await clock.advance(15000); await drain(manager); assert.equal(driver.dials, 2); assert.equal(manager.active, null);
});

test('PM05B: failed persistence cannot authorize a recovery offer', async t => {
  const { manager, driver, journal } = await recoveryFixture(t);
  const original = journal.save.bind(journal);
  journal.save = async () => { throw Error('disk unavailable'); };
  driver.call.active = false; driver.call.state = 'FAILED';
  await assert.rejects(manager.poll(), /disk unavailable/);
  assert.equal(driver.dials, 1); assert.equal(manager.timers.has('call-recovery'), false);
  journal.save = original;
});

test('PM05B: a browser loss followed by FAILED needs two explicit failed observations before redial', async t => {
  const { manager, driver, clock } = await recoveryFixture(t);
  await manager.lost('SNAPSHOT_TIMEOUT');
  driver.call.active = false; driver.call.connected = false; driver.call.state = 'FAILED';
  await clock.advance(1000); await drain(manager); assert.equal(driver.dials, 1);
  await clock.advance(1000); await drain(manager); assert.equal(driver.dials, 2);
});

test('PM05B: a cancellation received during a slow recovery probe invalidates its late FAILED result', async t => {
  const { manager, driver, clock } = await recoveryFixture(t);
  driver.call.state = 'FAILED'; driver.call.active = false; driver.call.connected = false; await manager.poll();
  let entered, release;
  const reached = new Promise(resolve => { entered = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  driver.recoverSnapshot = async () => { entered(); await gate; return { ...driver.call }; };
  await clock.advance(1000); await reached;
  const cancellation = manager.cancelKey('recoverable-call');
  assert.equal(manager.active.endRequested, 'cancelled');
  release(); await cancellation; await drain(manager);
  assert.equal(driver.dials, 1); assert.equal(manager.active, null);
});

test('PM05B: recovery before any answer still gives the requested conversation budget after the first answer', async t => {
  const { manager, driver, clock } = await fixture(t);
  await manager.startCall({ key: 'first-answer-after-recovery', maxSeconds: 300, durationFromAnswer: true }); await drain(manager);
  driver.call.active = false; driver.call.state = 'FAILED'; await manager.poll();
  await clock.advance(1000); await drain(manager);
  driver.call.connected = true; driver.call.state = 6; await manager.poll();
  assert.equal(manager.active.expiresAt, clock.now() + 300000);
});

test('PM05C: reservation stays occupied through cleanup; duplicate finish coalesces cleanup', async t => {
  const { manager, driver } = await fixture(t);
  await manager.startCall({ key: 'closing-reservation' }); await drain(manager);
  const record = manager.active; let release, entered, cleanups = 0;
  const reached = new Promise(resolve => { entered = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  driver.disarmAudio = async () => { cleanups++; entered(); await gate; };
  const closing = manager.finish(record, 'ended', 'remote_or_native_end'); await reached;
  const duplicate = manager.finish(record, 'interrupted', 'late_failure');
  assert.equal(manager.active, record);
  await assert.rejects(manager.startCall({ key: 'while-still-cleaning' }), { code: 'CALL_BUSY' });
  release(); await Promise.all([closing, duplicate]);
  assert.equal(cleanups, 1); assert.equal(manager.active, null);
  assert.equal(record.reason, 'remote_or_native_end');
  await manager.startCall({ key: 'after-cleaning' }); await drain(manager); assert.equal(driver.dials, 2);
});

test('PM05C: late playback result cannot resurrect an ended call or affect its successor', async t => {
  const { manager, driver } = await fixture(t);
  await manager.startCall({ key: 'late-playback-host' }); await drain(manager);
  driver.call.connected = true; await manager.poll(); const record = manager.active;
  let entered, release;
  const reached = new Promise(resolve => { entered = resolve; }); const gate = new Promise(resolve => { release = resolve; });
  driver.playAudio = async () => { entered(); await gate; };
  const playing = manager.serial(() => manager.performPlayback(record, { key: 'late-playback-request', audioId: 'tone' }));
  const rejected = assert.rejects(playing, { code: 'AUDIO_CALL_CHANGED' });
  await reached; await manager.finish(record, 'ended', 'remote_or_native_end');
  const next = await manager.startCall({ key: 'successor-after-close' });
  release(); await rejected; await drain(manager);
  assert.equal(record.playback.state, 'interrupted');
  assert.equal(manager.active.id, next.call.id); assert.equal(manager.active.state, 'dialing');
  assert.equal(driver.dials, 2);
});

async function noticeFixture(t, { failed = true } = {}) {
  const f = await fixture(t), owner = '525511112222@s.whatsapp.net';
  f.manager.destinationPolicy = createCallDestinationPolicy({ lab: f.manager.group, env: { BOTSKY_OWNER_NUMBER: owner } });
  if (failed) f.driver.dialError = new ServiceError('FIXTURE_DIAL_FAILED', 'simulated failure');
  const receipt = { chatId: owner, messageKey: { id: 'source-message', remoteJid: owner, fromMe: false } };
  const result = await f.manager.startCall({ key: 'notice-origin-order', targetJid: f.manager.group.id, origin: { chatId: owner, requesterId: owner }, sourceReceipt: receipt });
  await drain(f.manager); return { ...f, receipt, result };
}

test('PM05C: definitive failure has one durable leased receipt in the original private chat, not the target group', async t => {
  const { manager, journal, receipt, result, driver } = await noticeFixture(t);
  assert.equal(manager.getCall(result.call.id).state, 'failed');
  assert.equal(manager.getCall(result.call.id).sourceReceipt, undefined);
  const claims = await Promise.all([manager.claimFailureNotices(), manager.claimFailureNotices()]);
  assert.equal(claims.flatMap(c => c.notices).length, 1);
  const notice = claims.flatMap(c => c.notices)[0]; assert.equal(notice.chatId, receipt.chatId); assert.deepEqual(notice.messageKey, receipt.messageKey);
  const loaded = new Journal(journal.file); await loaded.load(); assert.equal(loaded.records.at(-1).failureNotice.state, 'claimed');
  await assert.rejects(manager.ackFailureNotice({ callId: result.call.id, lease: 'wrong-lease', delivered: true }), { code: 'NOTICE_LEASE_CHANGED' });
  assert.equal((await manager.beginFailureNotice({ callId: result.call.id, lease: notice.lease })).begun, true);
  await manager.ackFailureNotice({ callId: result.call.id, lease: notice.lease, delivered: true });
  assert.equal((await manager.claimFailureNotices()).notices.length, 0); assert.equal(driver.dials, 1);
});

test('PM05C: failure-reaction retries are bounded and never retry the call', async t => {
  const { manager, clock, driver } = await noticeFixture(t);
  for (let i = 0; i < 3; i++) {
    const [notice] = (await manager.claimFailureNotices()).notices; assert.ok(notice);
    assert.equal((await manager.beginFailureNotice({ callId: notice.callId, lease: notice.lease })).begun, true);
    await manager.ackFailureNotice({ callId: notice.callId, lease: notice.lease, delivered: false });
    await clock.advance(60000); await drain(manager);
  }
  assert.equal((await manager.claimFailureNotices()).notices.length, 0);
  assert.equal(manager.journal.records.at(-1).failureNotice.state, 'abandoned'); assert.equal(driver.dials, 1);
});

test('PM05C: voluntary close, no answer, rejection and an ordinary completed call have no failure reaction', async t => {
  for (const reason of ['requested', 'cancelled', 'remote_or_native_end', 'remote_rejected', 'not_answered', 'audio_completed', 'audience_empty', 'service_shutdown']) {
    const { manager } = await noticeFixture(t, { failed: false });
    await manager.finish(manager.active, 'ended', reason);
    assert.equal((await manager.claimFailureNotices()).notices.length, 0, reason);
  }
});

test('PM05C: an unacknowledged failure receipt survives restart with a lease, without starting any calls', async t => {
  const { manager, journal, clock } = await noticeFixture(t);
  const [first] = (await manager.claimFailureNotices()).notices;
  const driver = new Driver();
  const restarted = new CallManager({ driver, journal: new Journal(journal.file), group: manager.group, clock });
  t.after(() => restarted.stop()); await restarted.boot();
  assert.equal((await restarted.claimFailureNotices()).notices.length, 0);
  await clock.advance(90001); await drain(restarted);
  const [second] = (await restarted.claimFailureNotices()).notices;
  assert.equal(second.callId, first.callId); assert.notEqual(second.lease, first.lease);
  await assert.rejects(restarted.ackFailureNotice({ callId: first.callId, lease: first.lease, delivered: true }), { code: 'NOTICE_LEASE_CHANGED' });
  assert.equal(driver.dials, 0);
});

test('Call notice: begin is a durable one-shot POST permit; restart turns sending into terminal uncertain', async t => {
  const { manager, journal, result } = await noticeFixture(t);
  const [notice] = (await manager.claimFailureNotices()).notices;
  assert.equal(notice.requesterId, '525511112222@s.whatsapp.net');
  assert.equal((await manager.beginFailureNotice({ callId: notice.callId, lease: notice.lease })).begun, true);
  assert.equal((await manager.beginFailureNotice({ callId: notice.callId, lease: notice.lease })).begun, false);

  const restarted = new CallManager({ driver: new Driver(), journal: new Journal(journal.file), group: manager.group });
  t.after(() => restarted.stop()); await restarted.boot();
  assert.equal(restarted.journal.byId(result.call.id).failureNotice.state, 'uncertain');
  assert.equal((await restarted.claimFailureNotices()).notices.length, 0);
  await assert.rejects(restarted.ackFailureNotice({ callId: notice.callId, lease: notice.lease, outcome: 'accepted' }), { code: 'NOTICE_LEASE_CHANGED' });
});

test('Call notice: an expired claim cannot authorize the delayed sender', async t => {
  const { manager, clock, result } = await noticeFixture(t);
  const [oldLease] = (await manager.claimFailureNotices()).notices;
  await clock.advance(90001);
  assert.equal((await manager.beginFailureNotice({ callId: oldLease.callId, lease: oldLease.lease })).begun, false);
  const [newLease] = (await manager.claimFailureNotices()).notices;
  assert.notEqual(newLease.lease, oldLease.lease);
  assert.equal((await manager.beginFailureNotice({ callId: result.call.id, lease: newLease.lease })).begun, true);
  await manager.ackFailureNotice({ callId: result.call.id, lease: newLease.lease, outcome: 'uncertain' });
  assert.equal((await manager.claimFailureNotices()).notices.length, 0);
});

test('PM05C: unconfirmed microphone cleanup closes the owned browser before releasing the reservation', async t => {
  const { manager, driver, clock } = await fixture(t);
  await manager.startCall({ key: 'cleanup-fallback' }); await drain(manager);
  driver.call = null; driver.disarmAudio = async () => ({ released: false });
  await manager.finish(manager.active, 'ended', 'remote_or_native_end');
  assert.equal(manager.active, null); assert.equal(manager.state, 'recovering'); assert.equal(driver.closes, 2);
  await assert.rejects(manager.startCall({ key: 'during-cleanup-recovery' }), { code: 'NOT_READY' });
  driver.disarmAudio = async () => ({ released: true });
  await clock.advance(2000); await drain(manager); assert.equal(manager.state, 'ready');
});

test('PM05C: cleanup never closes a known unrelated call and blocks new automated calls if release is unconfirmed', async t => {
  const { manager, driver, clock } = await fixture(t);
  await manager.startCall({ key: 'foreign-during-cleanup' }); await drain(manager);
  driver.call = { active: true, id: 'foreign', outgoing: false }; driver.disarmAudio = async () => ({ released: false });
  await manager.finish(manager.active, 'interrupted', 'different_call_observed');
  assert.equal(manager.state, 'error'); assert.ok(manager.active); assert.equal(driver.closes, 1);
  await clock.advance(10000); await drain(manager); assert.equal(driver.closes, 1);
  driver.disarmAudio = async () => ({ released: true });
});

test('PM05C: a failed single recovery queues exactly one final failure notice', async t => {
  const { manager, driver, clock } = await noticeFixture(t, { failed: false });
  driver.call.connected = true; await manager.poll();
  driver.call.active = false; driver.call.connected = false; driver.call.state = 'FAILED'; await manager.poll();
  assert.equal((await manager.claimFailureNotices()).notices.length, 0);
  await clock.advance(1000); await drain(manager); assert.equal(driver.dials, 2);
  driver.call.active = false; driver.call.connected = false; driver.call.state = 'FAILED'; await manager.poll(); await drain(manager);
  const first = await manager.claimFailureNotices(), second = await manager.claimFailureNotices();
  assert.equal(first.notices.length, 1); assert.equal(second.notices.length, 0); assert.equal(driver.dials, 2);
});


test('PM05C: failure before any answer still reports a spent recovery once, without a third offer', async t => {
  const { manager, driver, clock } = await noticeFixture(t, { failed: false });
  driver.call.active = false; driver.call.state = 'FAILED'; await manager.poll();
  await clock.advance(1000); await drain(manager);
  driver.call.active = false; driver.call.state = 'FAILED'; await manager.poll(); await drain(manager);
  assert.equal(driver.dials, 2); assert.equal((await manager.claimFailureNotices()).notices.length, 1);
});

test('PM11: disabling outgoing blocks new reservations while preserving current calls and replay receipts', async t => {
 const {manager,driver}=await fixture(t);
 const first=await manager.startCall({key:'feature-current-call'});await drain(manager);
 manager.featureStore={value:{outgoing:false}};
 assert.equal((await manager.startCall({key:'feature-current-call'})).replayed,true);
 await assert.rejects(manager.startCall({key:'feature-blocked-new-call'}),{code:'OUTGOING_DISABLED'});
 assert.equal(manager.active.id,first.call.id);assert.equal(driver.dials,1);assert.equal(driver.ends,0);
});
test('PM11: disabling live or incoming cannot reserve a new Gemini session or answer', async t => {
 const {manager,driver}=await fixture(t);let preparations=0;
 manager.liveController={prepare:async()=>{preparations++;},stop:async()=>{},status:()=>null};
 manager.featureStore={value:{live:false,incoming:false}};
 await assert.rejects(manager.startCall({key:'feature-blocked-live',live:true}),{code:'LIVE_DISABLED'});
 manager.incomingPolicy={allows:()=>true};await manager.receiveIncoming({active:true,id:'incoming-owner',outgoing:false,state:3});
 assert.equal(preparations,0);assert.equal(manager.active,null);assert.equal(driver.dials,0);
});
test('PM11: late outgoing disable during preload invalidates the offer instead of dialing', async t => {
 const {manager,driver}=await fixture(t);let entered,release;
 const reached=new Promise(r=>{entered=r}),gate=new Promise(r=>{release=r});
 manager.featureStore={value:{outgoing:true}};
 driver.dial=async(_, {cancelled})=>{entered();await gate;assert.equal(cancelled(),true);throw new ServiceError('CANCELLED','disabled');};
 const result=await manager.startCall({key:'feature-preload-race'});await reached;manager.featureStore.value.outgoing=false;release();await drain(manager);
 assert.equal(manager.getCall(result.call.id).reason,'FEATURE_DISABLED');assert.equal(driver.dials,0);
});
test('PM11: live usage survives normal hangup as numeric counters without conversation content', async t => {
 const {manager,driver}=await fixture(t);const result=await manager.startCall({key:'feature-usage-counter'});await drain(manager);
 manager.liveController={status:()=>({callId:result.call.id,inputSeconds:3,outputSeconds:4,bridgeAcceptedSeconds:2,firstAudioLatencyMs:150,completedInputTurns:1,outputTurns:1,renewals:2}),stop:async()=>{manager.liveController.status=()=>null;}};
 await manager.endCall(result.call.id);
 assert.deepEqual(manager.getCall(result.call.id).usage,{inputAudioSeconds:3,modelOutputAudioSeconds:4,bridgeAcceptedAudioSeconds:2,firstAudioLatencyMs:150,completedInputTurns:1,outputTurns:1,connectionRenewals:2});
});

test('PM11: unavailable optional usage telemetry cannot prevent hangup or release', async t => {
 const {manager}=await fixture(t);const result=await manager.startCall({key:'unavailable-usage-metric'});await drain(manager);
 manager.liveController={status:()=>{throw Error('telemetry unavailable');},stop:async()=>{}};
 await manager.endCall(result.call.id);assert.equal(manager.active,null);assert.equal(manager.getCall(result.call.id).reason,'requested');
});

test('High audit: a failed close receipt retries persistence without replaying cleanup or the call', async t => {
 const {manager,driver,journal,clock}=await fixture(t);
 await manager.startCall({key:'finish-storage-failure'});await drain(manager);manager.clearTimer('poll');
 const record=manager.active;driver.call=null;let cleanups=0;
 driver.disarmAudio=async()=>{cleanups++;return {released:true};};
 const save=journal.save.bind(journal);journal.save=async()=>{throw Error('disk unavailable');};
 await assert.rejects(manager.finish(record,'ended','remote_or_native_end'),/disk unavailable/);
 const endedAt=record.endedAt;assert.equal(manager.active,record);assert.equal(record.state,'ended');
 await assert.rejects(manager.startCall({key:'still-cleaning-after-error'}),{code:'CALL_BUSY'});
 await clock.advance(1000);await drain(manager);assert.equal(manager.active,record);assert.equal(cleanups,1);assert.equal(driver.dials,1);
 journal.save=save;await clock.advance(1000);await drain(manager);
 assert.equal(manager.active,null);assert.equal(cleanups,1);assert.equal(record.endedAt,endedAt);assert.equal(record.reason,'remote_or_native_end');
 const stored=new Journal(journal.file);await stored.load();assert.equal(stored.byId(record.id).state,'ended');
 await manager.startCall({key:'after-close-storage-recovers'});await drain(manager);assert.equal(driver.dials,2);
});

test('High audit: transient microphone cleanup failure is retried before releasing the reservation', async t => {
 const {manager,driver,clock}=await fixture(t);
 await manager.startCall({key:'finish-cleanup-failure'});await drain(manager);manager.clearTimer('poll');
 const record=manager.active;driver.call=null;let attempts=0;
 driver.disarmAudio=async()=>{if(++attempts===1)throw Error('transient cleanup failure');return {released:true};};
 await assert.rejects(manager.finish(record,'ended','requested'),/transient cleanup/);
 assert.equal(manager.active,record);await clock.advance(1000);await drain(manager);
 assert.equal(manager.active,null);assert.equal(attempts,2);assert.equal(driver.dials,1);assert.equal(record.reason,'requested');
});

test('High audit: cleanup receipt recovery can recover the browser after a fatal storage error', async t => {
 const {manager,driver,journal,clock}=await fixture(t);
 await manager.startCall({key:'fatal-close-storage'});await drain(manager);manager.clearTimer('poll');
 const record=manager.active;driver.call=null;const save=journal.save.bind(journal);
 journal.save=async()=>{throw Error('disk temporarily unavailable');};
 await assert.rejects(manager.finish(record,'ended','remote_or_native_end'));
 await manager.fatal(Error('storage'));assert.equal(manager.state,'error');assert.equal(manager.active,record);
 journal.save=save;await clock.advance(1000);await drain(manager);
 assert.equal(manager.active,null);assert.equal(manager.state,'recovering');
 await clock.advance(2000);await drain(manager);assert.equal(manager.state,'ready');assert.equal(driver.dials,1);
 await manager.startCall({key:'after-fatal-storage-recovers'});await drain(manager);assert.equal(driver.dials,2);
});

test('High audit: a close receipt failure after hangup does not close the browser or repeat hangup', async t => {
 const {manager,driver,journal,clock}=await fixture(t);
 await manager.startCall({key:'hangup-receipt-retry'});await drain(manager);manager.clearTimer('poll');
 const record=manager.active,closes=driver.closes,save=journal.save.bind(journal);let writes=0;
 journal.save=async()=>{if(++writes===2)throw Error('close receipt unavailable');return save();};
 await assert.rejects(manager.requestEnd(record,'requested'),/close receipt unavailable/);
 assert.equal(record.state,'ended');assert.equal(manager.active,record);assert.equal(driver.closes,closes);assert.equal(driver.ends,1);
 await clock.advance(1000);await drain(manager);
 assert.equal(manager.active,null);assert.equal(manager.state,'ready');assert.equal(driver.closes,closes);assert.equal(driver.ends,1);assert.equal(driver.dials,1);
 journal.save=save;
});

test('High audit: a storage failure during unconfirmed cleanup never closes the known foreign call', async t => {
 const {manager,driver,journal,clock}=await fixture(t);
 await manager.startCall({key:'foreign-close-storage'});await drain(manager);manager.clearTimer('poll');
 const record=manager.active,closes=driver.closes,save=journal.save.bind(journal);
 driver.call={active:true,id:'foreign',outgoing:false};driver.disarmAudio=async()=>({released:false});
 journal.save=async()=>{throw Error('disk unavailable');};
 await assert.rejects(manager.finish(record,'interrupted','different_call_observed'));
 await manager.fatal(Error('disk unavailable'));assert.equal(driver.closes,closes);assert.equal(driver.call.id,'foreign');
 journal.save=save;await clock.advance(1000);await drain(manager);
 assert.equal(manager.active,record);assert.equal(manager.state,'error');assert.equal(driver.closes,closes);assert.equal(driver.call.id,'foreign');
 driver.disarmAudio=async()=>({released:true});
});

test('LIVE-1: initial context is private, durable, validated and included in the idempotency fingerprint',async t=>{
 const {manager,driver,journal}=await fixture(t);let context;
 manager.liveController={prepare:async record=>{context=record.liveRequest;},start:async()=>{},stop:async()=>{},status:()=>null};
 const request={key:'live-topic-context',live:true,liveRequest:'Platiquen de astronomía'};
 const result=await manager.startCall(request);await drain(manager);assert.equal(context,request.liveRequest);assert.equal(result.call.liveRequest,undefined);assert.equal(manager.status().activeCall.liveRequest,undefined);
 const loaded=new Journal(journal.file);await loaded.load();assert.equal(loaded.byKey(request.key).liveRequest,request.liveRequest);
 await assert.rejects(manager.startCall({...request,liveRequest:'Otro tema'}),{code:'KEY_CONFLICT'});
 await assert.rejects(manager.startCall({key:'invalid-topic-mode',live:false,liveRequest:'Tema'}),{code:'INVALID_LIVE_REQUEST'});
 await assert.rejects(manager.startCall({key:'invalid-topic-size',live:true,liveRequest:'x'.repeat(8001)}),{code:'INVALID_LIVE_REQUEST'});
 assert.equal(driver.dials,1);
});

test('LIVE-1: silence is scoped to the current connected Live call and does not hang up or alter its volume',async t=>{
 const {manager,driver}=await fixture(t);const silenced=[];
 manager.liveController={prepare:async()=>{},start:async()=>{},silence:async record=>silenced.push(record.id),stop:async()=>{},status:()=>null};
 await manager.startCall({key:'live-silence-control',live:true});await drain(manager);driver.call.connected=true;await manager.poll();
 const record=manager.active,volume=record.volume;const result=await manager.stopAudio(record.id);
 assert.equal(result.live,true);assert.deepEqual(silenced,[record.id]);assert.equal(driver.ends,0);assert.equal(record.volume,volume);assert.equal(manager.active,record);
});

test('LIVE-2: indefinite outgoing Live survives old caps and still stops when the human hangs up', async t => {
 const {manager,driver,clock,journal}=await fixture(t);let stopped=0;
 manager.liveController={prepare:async()=>{},start:async()=>{},stop:async()=>{stopped++;},status:()=>null};
 await manager.startCall({key:'indefinite-live-outgoing',live:true});await drain(manager);
 driver.call.connected=true;await manager.poll();const record=manager.active;
 assert.equal(record.maxSeconds,null);assert.equal(record.expiresAt,null);assert.equal(manager.timers.has('deadline'),false);
 await clock.advance(60*60*1000);await drain(manager);assert.equal(manager.active,record);assert.equal(driver.dials,1);
 const loaded=new Journal(journal.file);await loaded.load();assert.equal(loaded.byId(record.id).maxSeconds,null);
 driver.call=null;await manager.poll();await drain(manager);assert.equal(manager.active,null);assert.ok(stopped>0);
});

test('LIVE-2: explicit Live duration above sixteen minutes closes at the requested time',async t=>{
 const {manager,driver,clock}=await fixture(t);
 manager.liveController={prepare:async()=>{},start:async()=>{},stop:async()=>{},status:()=>null};
 await manager.startCall({key:'long-explicit-live-call',live:true,maxSeconds:3600});await drain(manager);
 driver.call.connected=true;await manager.poll();const record=manager.active;
 await clock.advance(960000);await drain(manager);assert.equal(manager.active,record);
 await clock.advance(3600000-960000);await drain(manager);assert.equal(manager.active,null);assert.equal(record.reason,'duration_limit');
});

test('LIVE-2: incoming Live has no conversation timer but retains the answer deadline',async t=>{
 const {manager,driver,clock}=await fixture(t);
 manager.incomingPolicy={allows:()=>true};manager.liveController={prepare:async()=>{},start:async()=>{},stop:async()=>{},status:()=>null};
 const snapshot={id:'incoming-unlimited',peerJid:'525511112222@s.whatsapp.net'};
 driver.answer=async()=>{driver.call={id:snapshot.id,active:true,connected:true};return {connected:true};};
 await manager.receiveIncoming(snapshot);const record=manager.active;
 assert.equal(record.maxSeconds,null);assert.equal(record.expiresAt,null);assert.equal(manager.timers.has('deadline'),false);
 await clock.advance(60*60*1000);await drain(manager);assert.equal(manager.active,record);assert.equal(driver.dials,0);
});

test('LIVE-2: very long explicit timers are chunked instead of overflowing Node timers',async t=>{
 const {manager,driver,clock}=await fixture(t);
 manager.liveController={prepare:async()=>{},start:async()=>{},stop:async()=>{},status:()=>null};
 await manager.startCall({key:'long-live-chunked-timer',live:true,maxSeconds:3000000});await drain(manager);
 driver.call.connected=true;await manager.poll();const record=manager.active;
 assert.equal(clock.tasks.get(manager.timers.get('deadline')).at-clock.now(),2147483647);
 await clock.advance(2147483647);await drain(manager);assert.equal(manager.active,record);
 await clock.advance(3000000000-2147483647);await drain(manager);assert.equal(manager.active,null);assert.equal(record.reason,'duration_limit');
});

test('LIVE-2: native recovery of unlimited Live keeps an answer timeout without inventing a duration limit',async t=>{
 const {manager,driver,clock}=await fixture(t);
 manager.liveController={prepare:async()=>{},start:async()=>{},suspend:async()=>{},resume:async()=>{},stop:async()=>{},status:()=>null};
 await manager.startCall({key:'unlimited-live-native-recovery',live:true});await drain(manager);
 driver.call.connected=true;await manager.poll();const record=manager.active;
 driver.call.active=false;driver.call.connected=false;driver.call.state='FAILED';await manager.poll();
 await clock.advance(1000);await drain(manager);assert.equal(driver.dials,2);assert.equal(record.expiresAt,null);
 const timeout=clock.tasks.get(manager.timers.get('deadline'));assert.equal(timeout.at-clock.now(),45000);
 driver.call.connected=true;driver.call.state=6;await manager.poll();
 assert.equal(manager.active,record);assert.equal(record.state,'connected');assert.equal(record.expiresAt,null);assert.equal(manager.timers.has('deadline'),false);
});

test('Botsky: a credential pool is rejected before any native offer',async t=>{
 const {LiveController}=require('../service/live-controller.cjs');
 const f=await fixture(t);let attempts=0;
 f.manager.liveController=new LiveController({driver:f.driver,runtime:{},getKeys:async()=>['first','second'],makeSession:()=>{attempts++;throw Error('must not probe');}});
 const result=await f.manager.startCall({key:'pool-is-forbidden-before-dial',live:true});await drain(f.manager);
 assert.equal(attempts,0);assert.equal(f.driver.dials,0);assert.equal(f.manager.active,null);
 assert.equal(f.manager.getCall(result.call.id).reason,'LIVE_NO_KEY');
});

test('LIVE-2C: invalid destinations cannot probe configured keys',async t=>{
 const {LiveController}=require('../service/live-controller.cjs');const f=await fixture(t);let probes=0;
 f.manager.liveController=new LiveController({driver:f.driver,runtime:{},getKeys:async()=>{probes++;return ['key'];}});
 await assert.rejects(f.manager.startCall({key:'invalid-target-before-key',live:true,targetJid:'bad-target'}));assert.equal(probes,0);assert.equal(f.driver.dials,0);
});

test('V1 private video still requires owner Live and remains idempotent', async t => {
  const { manager, driver } = await fixture(t);
  const owner = '525511112222@s.whatsapp.net';
  manager.destinationPolicy = createCallDestinationPolicy({ lab: manager.group, env: { BOTSKY_OWNER_NUMBER: owner } });
  manager.liveController = { prepare: async () => {}, stop: async () => {}, status: () => null };
  const dial = driver.dial.bind(driver);
  driver.dial = async (target, options) => { const result = await dial(target, options); result.isVideo = options.video; return result; };
  const options = { key: 'v1-private-video', targetJid: owner, live: true, video: true };
  await assert.rejects(manager.startCall({ ...options, video: 'true' }), { code: 'INVALID_VIDEO_POLICY' });
  await assert.rejects(manager.startCall({ ...options, live: false }), { code: 'INVALID_VIDEO_POLICY' });
  await assert.rejects(manager.startCall({ ...options, targetJid: manager.group.id, live: false }), { code: 'INVALID_VIDEO_POLICY' });
  const result = await manager.startCall(options); await drain(manager);
  assert.equal(result.call.video, true); assert.equal(driver.call.isVideo, true);
  assert.equal((await manager.startCall(options)).replayed, true);
  await assert.rejects(manager.startCall({ ...options, video: false }), { code: 'KEY_CONFLICT' });
  await manager.requestEnd(manager.active, 'requested');
});

test('V2 Lab video keeps one Live session through 2-1-2 listeners and ends after everyone leaves', async t => {
  const { manager, driver, clock } = await fixture(t);
  let starts = 0, stops = 0;
  manager.liveController = { prepare: async () => {}, start: async () => { starts++; }, suspend: async () => {}, stop: async () => { stops++; }, status: () => null };
  const dial = driver.dial.bind(driver);
  driver.dial = async (target, options) => { const call = await dial(target, options); call.isVideo = options.video; return call; };
  const result = await manager.startCall({ key: 'v2-lab-video-audience', targetJid: manager.group.id, live: true, video: true });
  await drain(manager);
  assert.equal(driver.targets[0].id, manager.group.id); assert.equal(manager.active.video, true);
  driver.call.connected = true;
  for (const count of [2, 1, 2]) {
    driver.call.audience = { known: true, connectedHumans: count, source: 'native_connected_participants' };
    await manager.serial(() => manager.poll());
    assert.equal(manager.active.id, result.call.id); assert.equal(starts, 1); assert.equal(driver.ends, 0);
  }
  driver.call.audience.connectedHumans = 0;
  await manager.serial(() => manager.poll());
  await clock.advance(5001); await drain(manager);
  assert.equal(manager.active, null); assert.equal(manager.getCall(result.call.id).reason, 'audience_empty');
  assert.equal(starts, 1); assert.ok(stops >= 1); assert.ok(driver.disarmed.includes(result.call.id));
});

test('V3 clip requests are scoped to connected video, idempotent and never execute after hangup', async t => {
  const { manager, driver } = await fixture(t);
  const clipId = 'c'.repeat(64), events = [];
  let release, entered;
  manager.clipStore = { read: async () => { if (release) { entered(); await new Promise(r => { release = r; }); } return { asset: { id: clipId, label: 'fixture' }, data: Buffer.from('video') }; } };
  driver.playClip = async (_, id) => { events.push(['play', id]); return { id, clipId, state: 'playing' }; };
  driver.controlClip = async (_, action, volume) => { events.push([action, volume]); return { clipId, state: action }; };
  await assert.rejects(manager.playClip({ clipId, key: 'v3-before-call' }), { code: 'CLIP_CALL_REQUIRED' });
  const result = await manager.startCall({ key: 'v3-call-fixture' }); await drain(manager);
  Object.assign(manager.active, { state: 'connected', video: true, live: true });
  driver.call.connected = true; driver.call.isVideo = true;
  manager.liveController = { stop: async () => {}, status: () => null };
  const request = { clipId, callId: result.call.id, key: 'v3-play-once' };
  assert.equal((await manager.playClip(request)).replayed, false);
  assert.equal((await manager.playClip(request)).replayed, true); assert.equal(events.length, 1);
  await assert.rejects(manager.playClip({ ...request, volume: 0.2 }), { code: 'KEY_CONFLICT' });
  await manager.controlClip({ callId: result.call.id, action: 'pause' });
  await manager.controlClip({ callId: result.call.id, action: 'volume', volume: 0 });
  assert.deepEqual(events.at(-1), ['volume', 0]);
  const loading = new Promise(r => { entered = r; }); release = () => {};
  const late = manager.playClip({ ...request, key: 'v3-late-request' });
  const rejected = assert.rejects(late, { code: 'CLIP_CALL_REQUIRED' });
  await loading;
  const ending = manager.requestEnd(manager.active, 'requested');
  release(); await rejected; await ending;
  assert.equal(events.filter(e => e[0] === 'play').length, 1); assert.equal(manager.active, null);
});

test('V5 avatar commands affect only a connected video call and stop when cancelled', async t => {
  const { manager, driver } = await fixture(t), commands = [];
  driver.avatarControl = async (id, options) => { commands.push({ id, ...options }); return { name: 'Kazumi', background: options.name }; };
  assert.equal((await manager.avatarCommand({ action: 'background', name: 'night' })).success, false);
  await manager.startCall({ key: 'v5-avatar-fixture' }); await drain(manager);
  assert.equal((await manager.avatarCommand({ callId: manager.active.id, action: 'background', name: 'night' })).success, false);
  Object.assign(manager.active, { video: true, live: true, state: 'connected' });
  manager.liveController = { stop: async () => {}, status: () => null };
  assert.equal((await manager.avatarCommand({ callId: 'wrong-call', action: 'background', name: 'night' })).success, false);
  assert.equal((await manager.avatarCommand({ callId: manager.active.id, action: 'background', name: 'night' })).success, true);
  driver.avatarControl = async (id, options) => { commands.push({ id, ...options }); return { name: 'Kazumi', background: 'sunset', deferred: true, requestedBackground: options.name }; };
  const deferred = await manager.avatarCommand({ callId: manager.active.id, action: 'background', name: 'night' });
  assert.equal(deferred.deferred, true);
  assert.match(deferred.message, /termin.*detengas el clip/);
  const controller = new AbortController(); controller.abort();
  assert.equal((await manager.avatarCommand({ callId: manager.active.id, action: 'expression', name: 'happy', signal: controller.signal })).success, false);
  assert.equal(commands.length, 2); assert.equal(commands[0].name, 'night');
});
