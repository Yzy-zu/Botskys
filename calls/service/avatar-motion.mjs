import { Quaternion, Vector3 } from 'three';
// Original procedural gestures: no external animation assets or model edits.
const definitions = {
  wave: ['rightUpperArm', 'rightLowerArm', 'rightHand'],
  nod: ['head'], shake_head: ['head'],
  hand_to_chest: ['head', 'rightUpperArm', 'rightLowerArm', 'rightHand', 'chest']
};
export function motionCapabilities(humanoid) {
  return Object.entries(definitions).map(([name, bones]) => ({ name,
    supported: bones.every(bone => !!humanoid?.getNormalizedBoneNode(bone)), bones }));
}
export function createMotionLayer(humanoid) {
  const nodes = new Map();
  for (const name of new Set(Object.values(definitions).flat())) {
    const node = humanoid?.getNormalizedBoneNode(name);
    if (node) nodes.set(name, node);
  }
  // Captured after the base arm pose; reset each frame before idle and gestures.
  const base = new Map([...nodes].map(([name, node]) => [name, node.rotation.clone()]));
  // Fit this rig once in normalized humanoid space, rather than assuming
  // elbow axes from one model. No IK work is needed in the frame loop.
  const chestPose = new Map();
  let chestTarget = null;
  if (['head', 'rightHand', 'rightUpperArm', 'rightLowerArm'].every(name => nodes.get(name)?.getWorldPosition)) {
    const hand = nodes.get('rightHand'), head = nodes.get('head');
    const target = head.getWorldPosition(new Vector3()).add(new Vector3(-0.035, -0.20, 0.14));
    chestTarget = target.toArray();
    for (let pass = 0; pass < 16; pass++) {
      for (const name of ['rightLowerArm', 'rightUpperArm']) {
        const joint = nodes.get(name); if (!joint) continue;
        joint.updateWorldMatrix(true, true);
        const origin = joint.getWorldPosition(new Vector3());
        const inverseParent = joint.parent.getWorldQuaternion(new Quaternion()).invert();
        const from = hand.getWorldPosition(new Vector3()).sub(origin).applyQuaternion(inverseParent).normalize();
        const to = target.clone().sub(origin).applyQuaternion(inverseParent).normalize();
        joint.quaternion.premultiply(new Quaternion().setFromUnitVectors(from, to));
      }
    }
    if (hand.getWorldPosition(new Vector3()).distanceTo(target) < 0.04) {
      for (const name of ['rightUpperArm', 'rightLowerArm']) chestPose.set(name, nodes.get(name).quaternion.clone());
    }
    for (const [name, node] of nodes) node.rotation.copy(base.get(name));
    head.updateWorldMatrix(true, true);
  }
  const capabilities = () => motionCapabilities(humanoid).map(item => ({ ...item, supported: item.supported && (item.name !== 'hand_to_chest' || chestPose.size > 0) }));
  let active = null, evidence = null, outgoing = null, lastApplied = [];
  const smooth = x => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  return {
    capabilities,
    start(name, duration, now) {
      if (!definitions[name]) throw Error('AVATAR_GESTURE_INVALID');
      if (!capabilities().find(item => item.name === name)?.supported) throw Error('AVATAR_GESTURE_UNSUPPORTED');
      outgoing = active && now < active.end && lastApplied.length ? { changes: lastApplied, start: now } : null;
      active = { name, start: now, end: now + duration * 1000 }; evidence = null;
    },
    reset() { for (const [name, node] of nodes) node.rotation.copy(base.get(name)); },
    apply(now) {
      evidence = null;
      const composed = [];
      if (outgoing) {
        const fade = 1 - smooth((now - outgoing.start) / 320);
        if (fade <= 0) outgoing = null;
        else for (const change of outgoing.changes) {
          const delta = change.delta * fade;
          nodes.get(change.bone).rotation[change.axis] += delta;
          composed.push({ bone: change.bone, axis: change.axis, delta });
        }
      }
      lastApplied = composed;
      if (!active) return;
      if (now >= active.end) { active = null; return; }
      const time = Math.max(0, (now - active.start) / 1000);
      const remaining = (active.end - now) / 1000;
      // A small first-frame anticipation is visible and can be acknowledged.
      const weight = Math.min(smooth((time + 0.06) / 0.32), smooth(remaining / 0.4));
      const changes = [];
      const add = (name, axis, amount) => {
        const node = nodes.get(name), delta = amount * weight;
        node.rotation[axis] += delta;
        changes.push({ bone: name, axis, delta, value: node.rotation[axis] });
      };
      if (active.name === 'nod') add('head', 'x', 0.16 * Math.sin(time * 5 + 0.45));
      if (active.name === 'shake_head') add('head', 'y', 0.22 * Math.sin(time * 5 + 0.45));
      if (active.name === 'wave') {
        add('rightUpperArm', 'z', 0.8); add('rightUpperArm', 'x', -0.25);
        add('rightLowerArm', 'z', 1.9); add('rightHand', 'z', 0.3 * Math.sin(time * 7 + 0.5));
      }
      if (active.name === 'hand_to_chest') {
        if (chestPose.size) {
          for (const [name, pose] of chestPose) {
            const node = nodes.get(name), before = node.rotation.clone();
            node.quaternion.slerp(pose, weight);
            for (const axis of ['x', 'y', 'z']) changes.push({ bone: name, axis, delta: node.rotation[axis] - before[axis], value: node.rotation[axis] });
          }
        }
        add('rightHand', 'x', -0.15); add('chest', 'z', -0.025);
      }
      for (const change of changes) {
        const previous = lastApplied.find(item => item.bone === change.bone && item.axis === change.axis);
        if (previous) previous.delta += change.delta;
        else lastApplied.push({ bone: change.bone, axis: change.axis, delta: change.delta });
      }
      evidence = { ...(active.name === 'hand_to_chest' && chestTarget ? { target: chestTarget } : {}), transitioning: !!outgoing, requested: active.name, applied: changes.some(item => Math.abs(item.delta) > 0.0001), weight, bones: changes };
    },
    status: () => ({ gesture: active?.name || null, appliedGesture: evidence })
  };
}
