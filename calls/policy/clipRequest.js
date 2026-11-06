'use strict';
const CLIP_ACTIONS = ['list', 'play', 'next', 'replay', 'pause', 'resume', 'stop', 'volume'];
function clipRequestErrors(request = {}) {
  const errors = [];
  if (!request || typeof request !== 'object' || Array.isArray(request)) return ['petición de clip inválida'];
  if (!CLIP_ACTIONS.includes(request.action)) errors.push('acción de clip inválida');
  if (Object.keys(request).some(k => !['action', 'query', 'selection', 'volume', 'adjustment'].includes(k))) errors.push('campo de clip desconocido');
  if (request.query !== undefined && (request.action !== 'play' || typeof request.query !== 'string' || !request.query.trim() || request.query.length > 200)) errors.push('nombre de clip inválido');
  if (request.selection !== undefined && (request.action !== 'play' || !Number.isInteger(request.selection) || request.selection < 1 || request.selection > 50 || request.query !== undefined)) errors.push('selección inválida');
  if (request.volume !== undefined && (request.action !== 'volume' || !Number.isFinite(request.volume) || request.volume < 0 || request.volume > 1)) errors.push('volumen inválido');
  if (request.adjustment !== undefined && (request.action !== 'volume' || !Number.isFinite(request.adjustment) || request.adjustment === 0 || Math.abs(request.adjustment) > 1 || request.volume !== undefined)) errors.push('ajuste inválido');
  if (request.action === 'volume' && request.volume === undefined && request.adjustment === undefined) errors.push('falta volumen');
  return errors;
}
function clipPlanToRequest(args) {
  return { action: args.clip_accion, ...(args.consulta !== undefined ? { query: args.consulta } : {}), ...(args.seleccion !== undefined ? { selection: args.seleccion } : {}), ...(args.volumen !== undefined ? { volume: args.volumen } : {}), ...(args.ajuste_volumen !== undefined ? { adjustment: args.ajuste_volumen } : {}) };
}
module.exports = { CLIP_ACTIONS, clipRequestErrors, clipPlanToRequest };
