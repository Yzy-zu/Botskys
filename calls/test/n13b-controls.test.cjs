// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { CallManager } = require('../service/manager.cjs');
const { AVATAR_TOOLS } = require('../service/avatar-tools.cjs');

function fixture() {
  const driver = { avatarControl: async (_nativeId, options) => ({
    gestureCapabilities: ['wave', 'nod', 'shake_head', 'hand_to_chest'].map(name => ({ name, supported: true, bones: [] })),
    blushCapabilities: [{ name: 'soft', supported: true, mode: 'procedural-overlay' }],
    ...(options.action === 'gesture' ? { appliedGesture: { requested: options.name, applied: true, weight: 1, bones: [{ bone: 'rightHand', axis: 'y', delta: 0.1, value: 0.1 }] } } : {}),
    ...(options.action === 'blush' ? { appliedBlush: { requested: options.name, applied: true, weight: 1, cheeks: [{ position: 'left', opacity: 0.2 }] } } : {})
  }) };
  const manager = new CallManager({ driver, journal: {}, group: { id: 'lab@g.us' } });
  manager.active = { id: 'owned', nativeId: 'native-owned', state: 'connected', live: true, video: true };
  return { manager, driver };
}

test('N13b exposes the bounded gesture and blush controls and requires applied frame evidence', async () => {
  const { manager, driver } = fixture();
  const declaration = AVATAR_TOOLS[0].functionDeclarations[0];
  assert.deepEqual(declaration.parameters.properties.action.enum, ['background', 'expression', 'gesture', 'blush']);
  assert.equal((await manager.avatarCommand({ callId: 'owned', action: 'gesture', name: 'wave' })).success, true);
  assert.equal((await manager.avatarCommand({ callId: 'owned', action: 'blush', name: 'soft', duration: 15 })).success, true);
  driver.avatarControl = async () => ({ capabilities: { gestures: ['wave'] } });
  assert.equal((await manager.avatarCommand({ callId: 'owned', action: 'gesture', name: 'wave' })).success, false);
  driver.avatarControl = async () => ({ appliedBlush: { requested: 'soft', applied: true, weight: 1, cheeks: [{ position: 'left', opacity: 0.2 }] } });
  assert.equal((await manager.avatarCommand({ callId: 'owned', action: 'blush', name: 'soft' })).success, true);
});

test('N13b validates action names and timed-control duration before dispatch', async () => {
  const { manager, driver } = fixture(); let dispatched = 0;
  driver.avatarControl = async () => { dispatched++; return {}; };
  for (const request of [
    { action: 'gesture', name: 'jump' }, { action: 'blush', name: 'strong' },
    { action: 'blush', name: 'soft', duration: 0 }, { action: 'gesture', name: 'wave', duration: 16 }
  ]) assert.equal((await manager.avatarCommand({ callId: 'owned', ...request })).success, false);
  assert.equal(dispatched, 0);
});
