// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {
  appliedExpressionEvidence, expressionCapabilities, findExpression,
  resetExpressionEvidence, resetExpressions, resolveSupportedExpression
} = require('../service/avatar-expressions.mjs');

function morphExpression(expressionName, influence = 0, bindWeight = 0.8) {
  const scene = { visible: true, parent: null };
  const mesh = { isMesh: true, visible: true, parent: scene, morphTargetInfluences: [influence] };
  return { expressionName, weight: 0, outputWeight: 0, binds: [{ primitives: [mesh], index: 0, weight: bindWeight }], mesh, scene };
}

function manager(expressions) {
  return {
    expressions,
    resetValues() { for (const expression of expressions) expression.weight = 0; },
    getValue(name) { return expressions.find(item => item.expressionName === name)?.weight ?? null; },
    setValue(name, value) {
      const expression = expressions.find(item => item.expressionName === name);
      if (expression) expression.weight = value;
    }
  };
}

test('N13a capabilities resolve real expression names case-insensitively and require live morph binds', () => {
  const surprised = morphExpression('Surprised');
  const noBind = { expressionName: 'happy', weight: 0, binds: [] };
  const orphaned = { expressionName: 'angry', weight: 0, binds: [{ material: {}, type: 'color' }] };
  const expressions = manager([surprised, noBind, orphaned]);
  const caps = expressionCapabilities(expressions, surprised.scene);
  assert.deepEqual(caps.find(item => item.name === 'surprised'), {
    name: 'surprised', expression: 'Surprised', supported: true, mode: 'expression', bindCount: 1, bindTypes: ['morph']
  });
  assert.equal(caps.find(item => item.name === 'happy').supported, false);
  assert.equal(caps.find(item => item.name === 'angry').supported, false);
  assert.equal(resolveSupportedExpression(expressions, 'SURPRISED', surprised.scene).expression, surprised);
  assert.equal(findExpression(expressions, 'sUrPrIsEd'), surprised);
  assert.throws(() => resolveSupportedExpression(expressions, 'happy', surprised.scene), /AVATAR_EXPRESSION_UNSUPPORTED/);
  assert.equal(caps.find(item => item.name === 'neutral').supported, true);
  assert.equal(caps.find(item => item.name === 'neutral').mode, 'reset');
});

test('N13a zero-weight, hidden, or detached morph binds cannot claim an expression capability', () => {
  const zero = morphExpression('happy', 0, 0);
  const hidden = morphExpression('angry', 0);
  hidden.mesh.visible = false;
  const detached = morphExpression('sad', 0);
  detached.mesh.parent = null;
  const expressions = manager([zero, hidden, detached]);
  const caps = expressionCapabilities(expressions, zero.scene);
  for (const name of ['happy', 'angry', 'sad']) assert.equal(caps.find(item => item.name === name).supported, false);
});

test('N13a reset clears every registered expression, including capitalized/custom names', () => {
  const expressions = manager([
    { expressionName: 'Surprised', weight: 0.65, binds: [] },
    { expressionName: 'blinkLeft', weight: 1, binds: [] },
    { expressionName: 'customSmile', weight: 0.4, binds: [] }
  ]);
  resetExpressions(expressions);
  assert.deepEqual(expressions.expressions.map(item => item.weight), [0, 0, 0]);
});

test('N13a applied status reports the post-update morph influence rather than requested weight alone', () => {
  const expression = morphExpression('Surprised');
  expression.weight = 0.65;
  expression.outputWeight = 0.65;
  expression.mesh.morphTargetInfluences[0] = 0.52;
  const capability = expressionCapabilities(manager([expression]), expression.scene).find(item => item.name === 'surprised');
  assert.deepEqual(appliedExpressionEvidence(expression, capability, 0.65, expression.scene), {
    requested: 'surprised', resolved: 'Surprised', weight: 0.65, value: 0.65,
    bindCount: 1, applied: true, binds: [{ type: 'morph', index: 0, weight: 0.8, influence: 0.52 }]
  });
  expression.mesh.morphTargetInfluences[0] = 0;
  assert.equal(appliedExpressionEvidence(expression, capability, 0.65, expression.scene).applied, false);
});

test('N13a neutral is verifiable as a reset and reports the previous controlled expression cleared', () => {
  const previous = morphExpression('Surprised');
  const neutral = { expressionName: 'neutral', weight: 0, binds: [{ primitives: [previous.mesh], index: 0, weight: 0 }] };
  const expressions = manager([previous, neutral]);
  previous.weight = 0;
  const capability = expressionCapabilities(expressions, previous.scene).find(item => item.name === 'neutral');
  assert.deepEqual(resetExpressionEvidence(capability, 'Surprised', expressions), {
    requested: 'neutral', resolved: 'neutral', weight: 0, value: 0,
    bindCount: 0, applied: true, reset: true,
    cleared: [{ expression: 'Surprised', value: 0 }], binds: []
  });
});
