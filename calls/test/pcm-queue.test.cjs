'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {PcmQueue} = require('../pcm-queue.cjs');
test('PCM real conserva muestras, copia entrada y aísla llamada/sesión/epoch', () => {
  const queue = new PcmQueue('call-lab', 'session-lab');
  const pcm = Buffer.alloc(480); for (let i = 0; i < 240; i++) pcm.writeInt16LE(i % 2 ? 12000 : -12000, i * 2);
  const packet = {callId: 'call-lab', sessionId: 'session-lab', epoch: 0, sequence: 0, pcm};
  assert.deepEqual(queue.push({...packet, callId: 'foreign'}), {discarded: true});
  assert.deepEqual(queue.push(packet), {accepted: true}); pcm.fill(0);
  assert.deepEqual(queue.push(packet), {discarded: true});
  const frame = queue.take(); assert.equal(frame.sampleRate, 24000); assert.equal(frame.pcm.readInt16LE(2), 12000);
  assert.equal(frame.pcm.readInt16LE(0), -12000); assert.equal(queue.take(), null);
  assert.equal(queue.clear(1), true); assert.deepEqual(queue.push({...packet, sequence: 1}), {discarded: true});
  assert.equal(queue.clear(1), false); queue.close(); assert.equal(queue.take(), null);
});
test('presión acotada y drenaje no pierden ni aceptan paquetes extra', () => {
  const queue = new PcmQueue('call', 'session'); const pcm = Buffer.alloc(96000, 1);
  const packet = {callId: 'call', sessionId: 'session', epoch: 0, pcm};
  for (let sequence = 0; sequence < 5; sequence++) assert.equal(queue.push({...packet, sequence}).accepted, true);
  assert.deepEqual(queue.push({...packet, sequence: 5}), {retryAfterMs: 250});
  assert.equal(queue.bytes, 480000); assert.equal(queue.take(48000).pcm.length, 96000);
  assert.equal(queue.push({...packet, sequence: 5}).accepted, true);
  assert.throws(() => queue.push({...packet, sequence: 6, pcm: Buffer.alloc(3)}), /PCM_FORMAT/);
  queue.close(); assert.equal(queue.bytes, 0); assert.deepEqual(queue.push({...packet, sequence: 6}), {discarded: true});
});
