'use strict';
const AVATAR_TOOLS = [{ functionDeclarations: [{ name: 'controlar_avatar', description: 'Cambia el fondo, una expresión o un gesto breve del avatar de esta videollamada. No cambia el personaje ni la voz.', behavior: 'NON_BLOCKING', parameters: {
  type: 'OBJECT', properties: {
    action: { type: 'STRING', enum: ['background', 'expression', 'gesture', 'blush'] },
    name: { type: 'STRING', description: 'Fondo: studio, neon, sunset, night. Expresión: neutral, relaxed, happy, angry, sad, surprised, wink, laugh. Gesto: wave, nod, shake_head, hand_to_chest. Rubor: soft.' },
    duration: { type: 'NUMBER', description: 'Duración entre 1 y 15 segundos para expresión, gesto o rubor. Omite para fondos.' }
  }, required: ['action', 'name']
} }] }];
module.exports = { AVATAR_TOOLS };
