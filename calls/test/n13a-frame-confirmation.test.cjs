// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture() {
  const output = [], timers = new Map(), applied = []; let nextTimer = 0, frames = 0;
  const avatar = { ready: Promise.resolve(), draw: () => { frames++; return true; }, readPixels: () => new Uint8ClampedArray(16),
    status: () => ({ frames, expression: applied.at(-1) }), control: options => { applied.push(options.name); }, stop() {} };
  const context = { AVATAR_WIDTH: 2, AVATAR_HEIGHT: 2, AVATAR_FPS: 20, AVATAR_FRAME_MS: 50,
    __botskyAvatarRenderer: { prepare() {}, create: () => avatar }, onmessage: null,
    performance: { now: () => 0 }, postMessage: message => output.push(message),
    setTimeout: fn => { const id = ++nextTimer; timers.set(id, fn); return id; }, clearTimeout: id => timers.delete(id) };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../service/avatar-worker.mjs'), 'utf8').replace(/^import .*;$/gm, ''), context);
  return { output, applied, send: data => context.onmessage({ data }),
    tick() { const next = timers.entries().next().value; assert.ok(next); timers.delete(next[0]); next[1](); } };
}

test('N13a worker confirms an expression only after the compositor acknowledges its own frame', async () => {
  const f = fixture(); await f.send({ type: 'init', base64: 'fixture' });
  const first = f.output[0];
  await f.send({ type: 'control', id: 7, options: { name: 'happy' } });
  assert.deepEqual(f.applied, []);
  await f.send({ type: 'ack', frameId: 999 });
  assert.deepEqual(f.applied, []);
  await f.send({ type: 'ack', frameId: first.frameId }); f.tick();
  assert.deepEqual(f.applied, ['happy']);
  assert.equal(f.output.some(message => message.type === 'control'), false);
  const changed = f.output.at(-1);
  assert.equal(changed.status.expression, 'happy');
  await f.send({ type: 'ack', frameId: first.frameId });
  assert.equal(f.output.some(message => message.type === 'control'), false);
  await f.send({ type: 'ack', frameId: changed.frameId });
  assert.equal(f.output.at(-1).type, 'control');
  assert.equal(f.output.at(-1).id, 7);
  assert.equal(f.output.at(-1).status.frames, changed.status.frames);
});

test('N13a a cancelled queued expression is never applied and a cancelled in-flight frame is never confirmed', async () => {
  const f = fixture(); await f.send({ type: 'init', base64: 'fixture' });
  await f.send({ type: 'control', id: 1, options: { name: 'sad' } });
  await f.send({ type: 'cancel-control', id: 1 });
  await f.send({ type: 'ack', frameId: f.output[0].frameId }); f.tick();
  assert.deepEqual(f.applied, []);
  await f.send({ type: 'control', id: 2, options: { name: 'happy' } });
  await f.send({ type: 'ack', frameId: f.output.at(-1).frameId }); f.tick();
  assert.deepEqual(f.applied, ['happy']);
  await f.send({ type: 'cancel-control', id: 2 });
  await f.send({ type: 'ack', frameId: f.output.at(-1).frameId });
  assert.equal(f.output.some(message => message.type === 'control'), false);
});
