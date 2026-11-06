const PRESET_BINDINGS = Object.freeze({
  neutral: 'neutral', relaxed: 'relaxed', happy: 'happy', angry: 'angry',
  sad: 'sad', surprised: 'surprised', wink: 'blinkLeft', laugh: 'happy'
});

function expressionList(manager) {
  return manager?.expressions || [];
}

function activeInScene(mesh, scene) {
  if (!mesh || mesh.isMesh !== true || mesh.visible === false) return false;
  if (!scene) return !!mesh.parent;
  for (let node = mesh; node; node = node.parent) {
    if (node.visible === false) return false;
    if (node === scene) return true;
  }
  return false;
}

function realBindings(expression, scene) {
  return (expression?.binds || []).filter(bind => {
    if (Array.isArray(bind?.primitives) && Number.isInteger(bind.index) && Number.isFinite(bind.weight) && bind.weight > 0) {
      return bind.primitives.some(mesh => activeInScene(mesh, scene) && Number.isFinite(mesh.morphTargetInfluences?.[bind.index]));
    }
    return false;
  });
}

export function findExpression(manager, requestedName) {
  if (typeof requestedName !== 'string') return null;
  const key = requestedName.toLowerCase();
  return expressionList(manager).find(item => item.expressionName?.toLowerCase() === key) || null;
}

export function expressionCapabilities(manager, scene) {
  const byName = new Map(expressionList(manager).map(item => [item.expressionName?.toLowerCase(), item]));
  return Object.entries(PRESET_BINDINGS).map(([name, target]) => {
    const expression = byName.get(target.toLowerCase());
    const binds = realBindings(expression, scene);
    const resetOnly = name === 'neutral';
    return { name, expression: expression?.expressionName || null, supported: resetOnly || binds.length > 0,
      mode: resetOnly ? 'reset' : 'expression',
      bindCount: binds.length, bindTypes: [...new Set(binds.map(bind => Array.isArray(bind.primitives) ? 'morph' : 'material'))] };
  });
}

export function resolveSupportedExpression(manager, requestedName, scene) {
  const capability = expressionCapabilities(manager, scene).find(item => item.name === requestedName?.toLowerCase());
  if (!capability?.supported) throw Error('AVATAR_EXPRESSION_UNSUPPORTED');
  return { expression: capability.expression ? findExpression(manager, capability.expression) : null, capability };
}

export function resetExpressions(manager) {
  if (manager?.resetValues) manager.resetValues();
  else for (const expression of expressionList(manager)) manager?.setValue(expression.expressionName, 0);
}

export function appliedExpressionEvidence(expression, capability, weight, scene) {
  const outputValue = Number(expression?.outputWeight ?? expression?.weight ?? 0);
  const binds = realBindings(expression, scene).map(bind => {
    if (Array.isArray(bind.primitives)) {
      const meshes = bind.primitives.filter(mesh => activeInScene(mesh, scene) && Number.isFinite(mesh.morphTargetInfluences?.[bind.index]));
      return { type: 'morph', index: bind.index, weight: bind.weight,
        influence: Math.max(...meshes.map(mesh => Number(mesh.morphTargetInfluences[bind.index]))) };
    }
  });
  return { requested: capability.name, resolved: expression.expressionName, weight,
    value: outputValue, bindCount: binds.length, applied: binds.some(bind => bind.influence > 0), binds };
}

export function resetExpressionEvidence(capability, previousExpressionName, manager) {
  const cleared = previousExpressionName && (manager?.getValue?.(previousExpressionName) ?? 0) === 0
    ? [{ expression: previousExpressionName, value: 0 }] : [];
  return { requested: 'neutral', resolved: capability.expression, weight: 0, value: 0,
    bindCount: 0, applied: true, reset: true, cleared, binds: [] };
}
