// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const { ClipCommands } = require('../service/clip-commands.cjs');
function fixture() {
  const assets = [{ id: 'a', label: 'Gato feliz', aliases: ['michi'], createdAt: 1 }, { id: 'b', label: 'Gato enojado', createdAt: 2 }];
  const played = [], controls = [], record = { id: 'call-1', nativeId: 'native-1' };
  const manager = { active: record, clipStore: { list: async () => assets }, clipCall: id => { if (!manager.active || (id && manager.active.id !== id) || record.endRequested) throw Error('closed'); return record; },
    serial: fn => fn(), driver: { snapshot: async () => ({ id: 'native-1', audio: { video: { clip: { volume: 0.1 } } } }) },
    playClip: async ({ clipId }) => { played.push(clipId); record.clip = { clipId }; return { clip: { clipId, state: 'playing' } }; },
    controlClip: async data => { controls.push(data); return { clip: { state: data.action, volume: data.volume } }; } };
  const commands = new ClipCommands(manager);
  return { commands, manager, record, played, controls };
}
test('V4 names, aliases and scoped choices never play ambiguous or missing clips', async () => {
  const f = fixture(), execute = (request, scope = 'voice') => f.commands.execute({ callId: 'call-1', scope, request });
  assert.equal((await execute({ action: 'play', query: 'gato' })).needs_clarification, true); assert.equal(f.played.length, 0);
  assert.equal((await execute({ action: 'play', selection: 2 }, 'other-user')).success, false);
  assert.equal((await execute({ action: 'play', selection: 2 })).success, true); assert.deepEqual(f.played, ['b']);
  assert.equal((await execute({ action: 'play', query: 'MICHI' })).success, true); assert.equal(f.played.at(-1), 'a');
  assert.equal((await execute({ action: 'play', query: 'un clip inexistente' })).success, false); assert.equal(f.played.length, 2);
});
test('V4 next/replay, real relative volume, idempotency and call changes preserve intent', async () => {
  const f = fixture();
  const command = { callId: 'call-1', key: 'once', request: { action: 'play', query: 'michi' } };
  await Promise.all([f.commands.execute(command), f.commands.execute(command)]); assert.equal(f.played.length, 1);
  await f.commands.execute({ request: { action: 'next' } }); assert.equal(f.played.at(-1), 'b');
  await f.commands.execute({ request: { action: 'replay' } }); assert.equal(f.played.at(-1), 'b');
  await f.commands.execute({ request: { action: 'volume', adjustment: -0.2 } }); assert.equal(f.controls.at(-1).volume, 0);
  f.manager.active = { id: 'call-2' };
  assert.equal((await f.commands.execute(command)).success, false); assert.equal(f.played.length, 3);
});

test('V5 volume changed after a clip ends is rounded, saved for the next clip and applied on replay', async () => {
  const f = fixture(), appliedVolumes = [];
  f.record.clipVolume = 0.2;
  f.record.clip = { clipId: 'a', label: 'Gato feliz' };
  f.manager.driver.snapshot = async () => ({ id: 'native-1', audio: { video: { clip: { state: 'ended', volume: 0.2 } } } });
  f.manager.controlClip = async ({ volume }) => {
    f.record.clipVolume = volume;
    return { clip: { state: 'ended', volume } };
  };
  f.manager.playClip = async ({ clipId, volume }) => {
    appliedVolumes.push(volume); f.record.clip = { clipId };
    return { clip: { clipId, state: 'playing', volume } };
  };
  const adjusted = await f.commands.execute({ request: { action: 'volume', adjustment: 0.1 } });
  assert.equal(adjusted.success, true);
  assert.equal(adjusted.clip.volume, 0.3);
  assert.equal(adjusted.message, 'Volumen del siguiente clip: 30%.');
  await f.commands.execute({ request: { action: 'play', query: 'michi' } });
  assert.deepEqual(appliedVolumes, [0.3]);
});

test('N12b a later stop invalidates queued play commands before they reach the manager', async () => {
  const f = fixture(); let release;
  f.commands.queue = new Promise(resolve => { release = resolve; });
  const play = f.commands.execute({ callId: 'call-1', request: { action: 'play', query: 'michi' } });
  const stopped = await f.commands.execute({ callId: 'call-1', request: { action: 'stop' } });
  assert.equal(stopped.success, true);
  release();
  assert.equal((await play).success, false);
  assert.equal(f.played.length, 0);
});
