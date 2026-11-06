// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const { build } = require('esbuild');

const bundle = build({ entryPoints: [path.join(__dirname, '../service/avatar-client.mjs')], bundle: true,
  format: 'iife', platform: 'browser', write: false, logLevel: 'silent', define: { AVATAR_WORKER_SOURCE: '"fixture-only"' } });

async function fixture() {
  const workers = [], timers = new Map(); let next = 0, time = 0;
  const canvas = { getContext: () => ({ putImageData() {} }) };
  class Worker {
    constructor() { workers.push(this); this.messages = []; }
    postMessage(message) { this.messages.push(message); }
    terminate() { this.terminated = true; }
    emit(data) { this.onmessage({ data }); }
    frame(background = 'night') { this.emit({ type: 'frame', rgba: new Uint8ClampedArray(4), status: { ready: true, frames: 1, background, expression: 'happy' } }); }
    fail() { this.onerror({ preventDefault() {} }); }
  }
  const addTimer = (fn, ms, interval) => { const id = ++next; timers.set(id, { fn, at: time + ms, interval }); return id; };
  const context = { window: {}, document: { createElement: () => canvas }, Worker,
    Blob: class {}, ImageData: class {}, URL: { createObjectURL: () => 'blob:fixture', revokeObjectURL() {} },
    performance: { now: () => time }, setTimeout: (fn, ms) => addTimer(fn, ms, 0), clearTimeout: id => timers.delete(id),
    setInterval: (fn, ms) => addTimer(fn, ms, ms), clearInterval: id => timers.delete(id) };
  vm.runInNewContext((await bundle).outputFiles[0].text, context);
  context.window.__botskyAvatar.prepare('model-for-this-call');
  const avatar = context.window.__botskyAvatar.create();
  function advance(ms) {
    const end = time + ms;
    for (;;) {
      const next = [...timers].sort((a, b) => a[1].at - b[1].at)[0];
      if (!next || next[1].at > end) break;
      const [id, task] = next; time = task.at;
      if (task.interval) task.at += task.interval; else timers.delete(id);
      task.fn();
    }
    time = end;
  }
  return { avatar, workers, canvas, timers, advance, api: context.window.__botskyAvatar };
}

test('N12b renderer replaces one crashed worker in the same canvas and fences late frames and controls', async () => {
  const f = await fixture(), original = f.workers[0];
  original.frame(); await f.avatar.ready;
  const pending = f.avatar.control({ action: 'background', name: 'sunset' });
  const rejected = assert.rejects(pending, /AVATAR_STOPPED/);
  f.api.prepare('different-model-for-a-future-call');
  original.fail(); await rejected;
  assert.equal(original.terminated, true);
  assert.equal(f.avatar.status().recovering, true);
  const replacement = f.workers[1];
  assert.equal(replacement.messages[0].base64, 'model-for-this-call');
  const lateMessages = original.messages.length;
  original.frame('sunset');
  assert.equal(original.messages.length, lateMessages);
  assert.equal(f.avatar.draw(), false);
  replacement.frame('neon');
  assert.equal(f.avatar.canvas, f.canvas);
  assert.equal(f.avatar.draw(), true);
  assert.equal(f.avatar.status().recoveries, 1);
  const restore = replacement.messages.filter(message => message.type === 'control');
  assert.equal(restore.length, 1);
  assert.equal(restore[0].options.action, 'background');
  assert.equal(restore[0].options.name, 'night');
  f.avatar.stop(); assert.equal(f.timers.size, 0);
});

test('N12b renderer stops retrying after the one recovery and exposes failure without losing the canvas', async () => {
  const f = await fixture();
  f.workers[0].frame(); await f.avatar.ready;
  const width = f.canvas.width;
  f.workers[0].fail(); f.workers[1].frame(); f.workers[1].fail();
  assert.equal(f.avatar.status().failed, true);
  assert.equal(f.avatar.status().worker, false);
  assert.equal(f.avatar.draw(), false);
  assert.equal(f.canvas.width, width);
  f.advance(60000);
  assert.equal(f.workers.length, 2);
  assert.ok(f.workers.every(worker => worker.terminated));
  assert.equal(f.timers.size, 0);
  f.avatar.stop();
});

test('N12b renderer watchdog bounds a silent worker and its stalled replacement', async () => {
  const f = await fixture();
  f.workers[0].frame(); await f.avatar.ready;
  f.advance(4999); assert.equal(f.workers.length, 1);
  f.advance(1); assert.equal(f.workers.length, 2);
  assert.equal(f.avatar.status().recovering, true);
  f.advance(15000);
  assert.equal(f.avatar.status().failed, true);
  assert.equal(f.timers.size, 0);
  f.avatar.stop();
});

test('N12b renderer hangup during recovery cannot resurrect a worker or frame', async () => {
  const f = await fixture();
  f.workers[0].frame(); await f.avatar.ready;
  f.workers[0].fail(); f.avatar.stop();
  f.workers[1].frame(); f.workers[1].fail(); f.advance(60000);
  assert.equal(f.workers.length, 2);
  assert.equal(f.avatar.draw(), false);
  assert.equal(f.canvas.width, 0);
  assert.equal(f.timers.size, 0);
});

test('N12b renderer failure before any frame rejects preparation after the bounded attempt', async () => {
  const f = await fixture();
  const rejected = assert.rejects(f.avatar.ready, /AVATAR_UNAVAILABLE/);
  f.workers[0].fail(); f.workers[1].fail(); await rejected;
  assert.equal(f.avatar.status().failed, true);
  assert.equal(f.timers.size, 0);
  f.avatar.stop();
});
