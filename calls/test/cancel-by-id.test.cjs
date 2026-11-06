// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../service/http.cjs');
const { CallManager } = require('../service/manager.cjs');

test('Cancel by old call ID never ends a later call and retains identity without exposing keys', async t => {
  const old = { id: 'old-call', key: 'old-key-123', state: 'ended', origin: { chatId: 'chat', requesterId: 'person' }, targetJid: 'chat' };
  const active = { id: 'new-call', key: 'new-key-123', state: 'connected' };
  const manager = { active, state: 'ready', clock: { now: () => 1 }, journal: {
    records: [old, active], cancelledKeys: {}, byId(id) { return this.records.find(r => r.id === id); }, byKey(key) { return this.records.find(r => r.key === key); }, save: async () => {} },
    serial: async fn => fn(), requestEnd: () => assert.fail('must not end successor'),
    publicCall: CallManager.prototype.publicCall, cancelKey: CallManager.prototype.cancelKey,
    status() { return { activeCall: this.publicCall(this.active), lastCall: this.publicCall(old) }; } };
  const server = createServer({ manager, driver: {}, audioStore: {}, token: 'token', policyRevision: 'a'.repeat(64), policyCurrent: () => false });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => { server.closeAllConnections(); server.close(); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (route, options = {}) => fetch(base + route, { ...options, headers: { Authorization: 'Bearer token', 'Content-Type': 'application/json', ...options.headers } });
  const result = await request('/v1/calls/cancel-by-id', { method: 'POST', body: JSON.stringify({ callId: old.id }) });
  assert.equal(result.status, 200); assert.deepEqual(await result.json(), { cancelled: true });
  assert.equal(manager.active, active); assert.ok(Object.hasOwn(manager.journal.cancelledKeys, old.key));
  assert.ok(!Object.hasOwn(manager.journal.cancelledKeys, active.key));
  const status = await (await request('/v1/status')).json();
  assert.deepEqual(status.lastCall.origin, old.origin); assert.equal(status.lastCall.targetJid, old.targetJid); assert.ok(!('key' in status.lastCall));
  const byKey = await (await request('/v1/calls/by-key?key=old-key-123')).json();
  assert.equal(byKey.call.id, old.id); assert.ok(!('key' in byKey.call));
  const byId = await (await request('/v1/calls/by-id?callId=old-call')).json();
  assert.equal(byId.key, old.key); assert.deepEqual(byId.call.origin, old.origin); assert.ok(!('key' in byId.call));
  assert.equal((await fetch(base + '/v1/calls/by-id?callId=old-call')).status, 401);
  assert.equal((await request('/v1/calls/by-id?callId=missing')).status, 404);
  active.state = 'starting';
  assert.equal((await (await request('/v1/status')).json()).activeCall.state, 'starting');
  active.state = 'connected'; // The remote call connected after the status read.
  const skip = await request('/v1/calls/cancel-by-id', {method:'POST', body:JSON.stringify({callId:active.id,onlyPreparing:true})});
  assert.deepEqual(await skip.json(), {cancelled:false,skipped:true});
  assert.ok(!Object.hasOwn(manager.journal.cancelledKeys, active.key));
  active.state = 'starting'; active.connectedAt = 1;
  const retrySkip = await request('/v1/calls/cancel-by-id', {method:'POST', body:JSON.stringify({callId:active.id,onlyPreparing:true})});
  assert.deepEqual(await retrySkip.json(), {cancelled:false,skipped:true});
  assert.ok(!Object.hasOwn(manager.journal.cancelledKeys, active.key));
  const preparing = {id:'preparing-call', key:'preparing-key', state:'starting'};
  manager.journal.records.push(preparing);
  const cancelled = await request('/v1/calls/cancel-by-id', {method:'POST',body:JSON.stringify({callId:preparing.id,onlyPreparing:true})});
  assert.deepEqual(await cancelled.json(), {cancelled:true});
  assert.ok(Object.hasOwn(manager.journal.cancelledKeys, preparing.key));
  const malformed = await request('/v1/calls/cancel-by-id', {method:'POST',body:JSON.stringify({callId:active.id,onlyPreparing:'true'})});
  assert.equal(malformed.status, 400);
  const missing = await request('/v1/calls/cancel-by-id', { method:'POST', body:JSON.stringify({callId:'unknown'}) });
  assert.equal(missing.status, 404); assert.equal(manager.active, active);
});
