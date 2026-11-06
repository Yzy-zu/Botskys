// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { GroupVoiceGate } = require('../service/group-voice-gate.cjs');

test('Only the Live semantic decision with current speech opens voice; arbitrary addresses need no name list', async () => {
  const gate = new GroupVoiceGate({ waitMs: 5 });
  gate.transcript('¿Puedo probarme esto?');
  assert.deepEqual(await gate.authorize(false, gate.current), { allowVoice: false });
  gate.begin(); gate.transcript('Ayer Zhana nos contó una historia.');
  assert.deepEqual(await gate.authorize(false, gate.current), { allowVoice: false });
  gate.begin(); gate.transcript('Pequeña compañera virtual, ¿nos ayudas a elegir?');
  assert.deepEqual(await gate.authorize(true, gate.current), { allowVoice: true });
  gate.begin(); assert.equal(gate.allowed, false);
});

test('Late split transcription can authorize only its current intervention; superseded or aborted decisions stay closed', async () => {
  const gate = new GroupVoiceGate({ waitMs: 30 });
  const first = gate.current;
  const authorization = gate.authorize(true, first);
  gate.transcript('Oye, '); assert.equal(gate.allowed, false);
  gate.transcript('Zhana, ayúdanos.');
  assert.deepEqual(await authorization, { allowVoice: true });
  gate.begin();
  assert.deepEqual(await gate.authorize(true, first), { allowVoice: false });
  const pending = gate.authorize(true, gate.current);
  gate.begin(); gate.transcript('Zhana, hola.');
  assert.deepEqual(await pending, { allowVoice: false });
  assert.equal(gate.allowed, false);
  const controller = new AbortController(); controller.abort();
  assert.deepEqual(await gate.authorize(true, gate.current, controller.signal), { allowVoice: false });
});

test('The initial greeting is authorized and ends without leaving voice open', () => {
  const gate = new GroupVoiceGate();
  gate.begin({ greeting: true }); assert.equal(gate.allowed, true);
  gate.end(); assert.equal(gate.allowed, false);
});
