// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { CallManager } = require('../service/manager.cjs');
const { ClipCommands } = require('../service/clip-commands.cjs');

function fixture() {
  let release, entered;
  const gate = new Promise(resolve => { release = resolve; });
  const reached = new Promise(resolve => { entered = resolve; });
  let media = { state: 'resuming', volume: 0.5 };
  const stops = [];
  const record = { id: 'owned-call', nativeId: 'native-owned', state: 'connected', video: true, live: true };
  const driver = {
    async playClip() { entered(); await gate; return { ...media }; },
    async controlClip(id, action, volume) {
      if (id !== record.nativeId) throw Error('foreign call');
      if (action === 'resume') { media.state = 'resuming'; entered(); await gate; }
      else if (action === 'pause') media.state = 'paused';
      else if (action === 'stop') { stops.push(id); media.state = 'stopped'; }
      else if (action === 'volume') media.volume = volume;
      return { ...media };
    },
    async snapshot() { return { id: record.nativeId, audio: { video: { clip: media } } }; },
  };
  const journal = { records: [record], cancelledKeys: {}, save: async () => {} };
  const manager = new CallManager({ driver, journal, group: { id: 'lab@g.us' } });
  manager.active = record; manager.state = 'ready';
  manager.clipStore = { list: async () => [{ id: 'fixture-clip', label: 'Colores', createdAt: 1 }],
    read: async () => ({ asset: { id: 'fixture-clip', label: 'Colores' }, data: Buffer.from('fixture-only') }) };
  return { manager, record, driver, reached, release, stops, setMedia: value => { media = value; } };
}

test('N12b pause and stop reach a pending clip load before the browser queue is released', async () => {
  const f = fixture();
  const play = f.manager.playClip({ callId: f.record.id, clipId: 'fixture-clip', key: 'n12b-pending-play' });
  await f.reached;
  const paused = await f.manager.controlClip({ callId: f.record.id, action: 'pause' });
  assert.equal(paused.clip.state, 'paused');
  const stopped = await f.manager.controlClip({ callId: f.record.id, action: 'stop' });
  assert.equal(stopped.clip.state, 'stopped');
  await assert.rejects(f.manager.controlClip({ callId: 'foreign-call', action: 'pause' }), { code: 'CLIP_CALL_REQUIRED' });
  f.release(); await play;
  assert.equal(f.manager.pendingClip, null);
});

test('N12b a manual pause can supersede a pending resume without waiting for play()', async () => {
  const f = fixture();
  const resume = f.manager.controlClip({ callId: f.record.id, action: 'resume' });
  await f.reached;
  assert.equal((await f.manager.controlClip({ callId: f.record.id, action: 'pause' })).clip.state, 'paused');
  f.release();
  assert.equal((await resume).clip.state, 'paused');
  assert.equal(f.manager.pendingClip, null);
});

test('N12b abort during pending clip load rejects promptly and stops late completion', async () => {
  const f = fixture(), controller = new AbortController();
  const play = f.manager.playClip({ callId: f.record.id, clipId: 'fixture-clip', key: 'n12b-abort-load', signal: controller.signal });
  await f.reached;
  controller.abort();
  await assert.rejects(play, { code: 'CANCELLED' });
  assert.equal(f.manager.pendingClip, null);
  assert.deepEqual(f.stops, ['native-owned']);
  const drain = f.manager.clipOperationDrain?.promise;
  f.release();
  await drain;
  assert.deepEqual(f.stops, ['native-owned', 'native-owned']);
  assert.equal(f.record.clip, undefined);
  assert.equal(f.record.clipRequests[0].state, 'failed');
});

test('N12b abort during pending resume rejects promptly and stops late completion', async () => {
  const f = fixture(), controller = new AbortController();
  const resume = f.manager.controlClip({ callId: f.record.id, action: 'resume', signal: controller.signal });
  await f.reached;
  controller.abort();
  await assert.rejects(resume, { code: 'CANCELLED' });
  assert.equal(f.manager.pendingClip, null);
  assert.deepEqual(f.stops, ['native-owned']);
  const drain = f.manager.clipOperationDrain?.promise;
  f.release();
  await drain;
  assert.deepEqual(f.stops, ['native-owned', 'native-owned']);
});

test('N12b late aborted completion cannot stop a successor call', async () => {
  const f = fixture(), controller = new AbortController();
  const play = f.manager.playClip({ callId: f.record.id, clipId: 'fixture-clip', key: 'n12b-abort-successor', signal: controller.signal });
  await f.reached;
  controller.abort();
  await assert.rejects(play, { code: 'CANCELLED' });
  f.manager.active = { id: 'successor-call', nativeId: 'native-successor', state: 'connected', video: true, live: true };
  f.release();
  await f.manager.clipOperationDrain?.promise;
  assert.deepEqual(f.stops, ['native-owned']);
});

test('N12b spoken pause bypasses a pending clip command while preserving call identity', async () => {
  const f = fixture(), commands = new ClipCommands(f.manager);
  const play = commands.execute({ callId: f.record.id, key: 'play-once', request: { action: 'play', query: 'Colores' } });
  await f.reached;
  const paused = await commands.execute({ callId: f.record.id, key: 'pause-once', request: { action: 'pause' } });
  assert.equal(paused.success, true);
  assert.equal(paused.clip.state, 'paused');
  assert.equal((await commands.execute({ callId: 'foreign-call', request: { action: 'stop' } })).success, false);
  f.release(); await play;
});

test('N12b resume of an ended clip asks before replaying and sends no playback command', async () => {
  const f = fixture(), commands = new ClipCommands(f.manager);
  f.setMedia({ state: 'ended', volume: 0.4 });
  f.driver.controlClip = async () => { throw Error('must not resume ended clip'); };
  f.manager.playClip = async () => { throw Error('must not replay implicitly'); };
  const result = await commands.execute({ callId: f.record.id, request: { action: 'resume' } });
  assert.equal(result.success, false);
  assert.equal(result.needs_clarification, true);
  assert.equal(result.question, 'Ya terminó. ¿Lo repito?');
});
