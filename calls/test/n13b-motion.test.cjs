// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
async function fixture(missing) {
  const { createMotionLayer } = await import('../service/avatar-motion.mjs');
  const { Euler } = await import('three');
  const nodes = new Map(['head', 'chest', 'rightUpperArm', 'rightLowerArm', 'rightHand'].filter(name => name !== missing).map(name => [name, { rotation: new Euler(0, 0, name === 'rightUpperArm' ? -1.15 : 0) }]));
  return { layer: createMotionLayer({ getNormalizedBoneNode: name => nodes.get(name) }), nodes };
}
test('N13b gesture layer preserves base, overrides idle and returns without accumulated rotations', async () => {
  const { layer, nodes } = await fixture();
  layer.start('wave', 2, 0);
  for (let time = 0; time <= 2000; time += 50) {
    layer.reset(); nodes.get('head').rotation.x = 0.02;
    layer.apply(time);
    if (time === 500) {
      assert.ok(nodes.get('rightUpperArm').rotation.z > -0.5);
      assert.equal(layer.status().appliedGesture.applied, true);
    }
  }
  assert.equal(layer.status().gesture, null);
  assert.equal(nodes.get('rightUpperArm').rotation.z, -1.15);
  assert.equal(nodes.get('head').rotation.x, 0.02);
});
test('N13b missing hand withdraws gestures that depend on it', async () => {
  const { layer } = await fixture('rightHand');
  assert.equal(layer.capabilities().find(item => item.name === 'wave').supported, false);
  assert.throws(() => layer.start('wave', 2, 0), /UNSUPPORTED/);
  layer.start('nod', 2, 0); layer.reset(); layer.apply(0);
  assert.equal(layer.status().appliedGesture.applied, true);
});
test('N13b replacement fades the old gesture and resets all touched bones', async () => {
  const { layer, nodes } = await fixture();
  layer.start('wave', 2, 0); layer.apply(500);
  layer.start('shake_head', 1, 500); layer.reset(); layer.apply(500);
  assert.ok(nodes.get('rightUpperArm').rotation.z > -0.5, 'old gesture fades instead of snapping');
  assert.equal(layer.status().appliedGesture.transitioning, true);
  layer.reset(); layer.apply(900);
  assert.equal(nodes.get('rightUpperArm').rotation.z, -1.15);
  assert.equal(layer.status().gesture, 'shake_head');
  assert.throws(() => layer.start('arbitrary', 2, 0), /INVALID/);
});

test('N13b chest gesture is unavailable when this rig cannot fit a chest target', async () => {
  const { layer } = await fixture();
  assert.equal(layer.capabilities().find(item => item.name === 'hand_to_chest').supported, false);
  assert.throws(() => layer.start('hand_to_chest', 2, 0), /UNSUPPORTED/);
});
