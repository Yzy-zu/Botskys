// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { GroupDirector } = require('../service/group-director.cjs');

test('Director ties queued output to its call and input generation, including after provider turn completion', async () => {
  const director = new GroupDirector({ callId: 'call-a', sessionId: 'session-a' });
  assert.equal(director.snapshot().state, 'listening');
  director.transcript('Zhana, hola.');
  await director.authorize(true, director.current);
  director.speaking(); const first = director.token();
  assert.equal(director.snapshot().state, 'responding');
  director.end();
  assert.equal(director.allowed, false);
  assert.equal(director.snapshot().state, 'waiting_addressed');
  assert.equal(director.isCurrent(first), true); // Previously admitted audio may drain.
  assert.deepEqual(await director.authorize(true, director.current), { allowVoice: false });
  director.begin();
  assert.equal(director.isCurrent(first), false);
  const second = director.token();
  const other = new GroupDirector({ callId: 'call-b', sessionId: 'session-b' });
  assert.equal(other.isCurrent(second), false);
  director.setReconnecting(true);
  assert.equal(director.snapshot().state, 'reconnecting');
  assert.deepEqual(await director.authorize(true, director.current), { allowVoice: false });
  director.setReconnecting(false); director.interrupted();
  assert.equal(director.snapshot().state, 'listening');
  director.close(); director.begin({ greeting: true }); director.interrupted();
  assert.equal(director.snapshot().state, 'ended');
  assert.equal(director.isCurrent(second), false);
  assert.equal(director.allowed, false);
  assert.equal(JSON.stringify(director.snapshot()).includes('Zhana, hola'), false);
});

test('A delayed authorization cannot move the director after a newer intervention or end', async () => {
  const director = new GroupDirector({ waitMs: 100 });
  const old = director.current;
  const pending = director.authorize(true, old);
  director.begin(); director.transcript('Zhana, ayúdanos.');
  assert.deepEqual(await pending, { allowVoice: false });
  assert.equal(director.snapshot().state, 'listening');
  assert.equal(director.allowed, false);
  const closing = new GroupDirector({ waitMs: 100 });
  const late = closing.authorize(true, closing.current);
  closing.close();
  assert.deepEqual(await late, { allowVoice: false });
  assert.equal(closing.snapshot().state, 'ended');
  const finished = new GroupDirector({ waitMs: 100 });
  const lateFinish = finished.authorize(true, finished.current);
  finished.transcript('Zhana, hola.'); finished.end();
  assert.deepEqual(await lateFinish, { allowVoice: false });
  assert.equal(finished.allowed, false);
});
