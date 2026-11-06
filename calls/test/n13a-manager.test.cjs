// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { CallManager } = require('../service/manager.cjs');

function fixture() {
  const driver = {};
  const manager = new CallManager({ driver, journal: {}, group: { id: 'lab@g.us' } });
  manager.active = { id: 'owned', nativeId: 'native-owned', state: 'connected', live: true, video: true };
  return { manager, driver };
}

test('N13a manager requires applied expression evidence and rejects a late result from another call', async () => {
  const { manager, driver } = fixture();
  driver.avatarControl = async () => ({ expression: 'happy' });
  assert.equal((await manager.avatarCommand({ callId: 'owned', action: 'expression', name: 'happy' })).success, false);
  driver.avatarControl = async () => ({ appliedExpression: { requested: 'happy', applied: true } });
  assert.equal((await manager.avatarCommand({ callId: 'owned', action: 'expression', name: 'happy' })).success, true);
  driver.avatarControl = async () => {
    manager.active = { id: 'successor', nativeId: 'native-successor', state: 'connected', live: true, video: true };
    return { appliedExpression: { requested: 'happy', applied: true } };
  };
  assert.equal((await manager.avatarCommand({ callId: 'owned', action: 'expression', name: 'happy' })).success, false);
});

test('N13a abort forwards the exact visual control ID and cannot report a cancelled gesture as success', async () => {
  const { manager, driver } = fixture(), controller = new AbortController();
  let begin, rejectControl, command;
  const entered = new Promise(resolve => { begin = resolve; });
  driver.avatarControl = async (nativeId, options) => {
    command = { nativeId, controlId: options.controlId }; begin();
    return new Promise((_, reject) => { rejectControl = reject; });
  };
  driver.cancelAvatarControl = async (nativeId, controlId) => {
    assert.deepEqual({ nativeId, controlId }, command);
    rejectControl(Error('AVATAR_CONTROL_CANCELLED'));
  };
  const work = manager.avatarCommand({ callId: 'owned', action: 'expression', name: 'happy', signal: controller.signal });
  await entered; controller.abort();
  assert.equal((await work).success, false);
  assert.equal(command.nativeId, 'native-owned');
});
