'use strict';
const { randomUUID } = require('node:crypto');
const { clipRequestErrors, CLIP_ACTIONS } = require('../policy/clipRequest');
const clean = text => String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const CLIP_TOOLS = [{ functionDeclarations: [{ name: 'controlar_clips', description: 'Consulta el catálogo real y reproduce o controla clips de esta videollamada. No descarga ni inventa clips. Si falta precisión pregunta con las opciones devueltas.', parameters: { type: 'OBJECT', properties: {
  action: { type: 'STRING', enum: CLIP_ACTIONS }, query: { type: 'STRING', description: 'Nombre o alias pedido por el usuario; solo con play.' }, selection: { type: 'INTEGER', description: 'Número de la última lista de opciones, solo con play.' }, volume: { type: 'NUMBER', description: 'Volumen absoluto 0..1, solo con volume.' }, adjustment: { type: 'NUMBER', description: 'Cambio de volumen relativo: bajar -0.2, subir 0.2, solo con volume.' }
}, required: ['action'] } }] }];
class ClipCommands {
  constructor(manager) { this.manager = manager; this.queue = Promise.resolve(); this.context = new Map(); this.results = new Map(); }
  execute({ callId, scope = 'voice', key, request, signal } = {}) {
    const errors = clipRequestErrors(request);
    if (errors.length || typeof scope !== 'string' || scope.length > 200 || (key !== undefined && (typeof key !== 'string' || key.length > 128))) return Promise.resolve({ success: false, message: 'No quedó claro qué quieres hacer con el clip.' });
    const record = this.manager.active;
    if (callId && record?.id !== callId) return Promise.resolve({ success: false, message: 'Esa llamada ya terminó o cambió.' });
    const token = `${record?.id || 'catalog'}:${scope}:${key || randomUUID()}`;
    const signature = JSON.stringify(Object.fromEntries(Object.entries(request).sort(([a], [b]) => a.localeCompare(b))));
    const prior = this.results.get(token);
    if (prior) return prior.signature === signature ? prior.work : Promise.resolve({ success: false, message: 'Esa petición ya correspondía a otra acción.' });
    if (this.callId !== record?.id) { this.context.clear(); this.results.clear(); this.callId = record?.id; this.clipEpoch = 0; }
    const urgent = ['pause', 'stop'].includes(request.action);
    const epoch = this.clipEpoch || 0;
    if (urgent) this.clipEpoch = epoch + 1;
    const obsolete = () => ['play', 'next', 'replay', 'resume'].includes(request.action) && (this.clipEpoch || 0) !== epoch;
    const work = (urgent ? Promise.resolve() : this.queue).then(async () => {
      if (signal?.aborted || obsolete() || (record && (this.manager.active !== record || record.endRequested))) return { success: false, message: 'La petición fue cancelada o la llamada terminó.' };
      const assets = (await this.manager.clipStore.list()).sort((a, b) => a.createdAt - b.createdAt || a.id.localeCompare(b.id));
      if (signal?.aborted || obsolete() || (record && (this.manager.active !== record || record.endRequested))) return { success: false, message: 'La petición fue cancelada o la llamada terminó.' };
      const previous = this.context.get(scope);
      const options = items => {
        this.context.set(scope, { ids: items.map(a => a.id), at: Date.now() });
        return items.map((a, index) => ({ number: index + 1, name: a.label, ...(a.aliases?.length ? { aliases: a.aliases } : {}) }));
      };
      if (request.action === 'list') return { success: true, clips: options(assets), message: assets.length ? 'Estos son los clips disponibles.' : 'El catálogo está vacío; todavía no tengo clips cargados.' };
      this.manager.clipCall(record?.id);
      let asset;
      if (request.action === 'play') {
        if (request.selection !== undefined) {
          if (!previous || Date.now() - previous.at > 300000) return { success: false, needs_clarification: true, question: 'Esa lista ya no está vigente. ¿Qué clip quieres por nombre?' };
          asset = assets.find(a => a.id === previous.ids[request.selection - 1]);
          if (!asset) return { success: false, needs_clarification: true, question: 'Ese número no corresponde a la lista. ¿Cuál clip quieres?' };
        } else if (request.query) {
          const query = clean(request.query);
          if (!query) return { success: false, needs_clarification: true, question: '¿Qué clip quieres por nombre?' };
          const exact = assets.filter(a => [a.label, ...(a.aliases || [])].some(name => clean(name) === query));
          const matches = exact.length ? exact : assets.filter(a => [a.label, ...(a.aliases || [])].some(name => clean(name).includes(query)));
          if (matches.length === 1) asset = matches[0];
          else if (matches.length > 1) return { success: false, needs_clarification: true, question: 'Hay varios clips con ese nombre. ¿Cuál quieres?', clips: options(matches) };
          else return { success: false, message: 'No encontré ese clip en el catálogo. No reproduje otro en su lugar.' };
        } else return { success: false, needs_clarification: true, question: '¿Qué clip quieres?', clips: options(assets) };
      } else if (request.action === 'replay') {
        asset = assets.find(a => a.id === record.clip?.clipId);
        if (!asset) return { success: false, message: 'Todavía no hay un clip anterior para repetir en esta llamada.' };
      } else if (request.action === 'next') {
        const index = assets.findIndex(a => a.id === record.clip?.clipId);
        if (assets.length < 2 && index >= 0) return { success: false, message: 'Solo hay un clip en el catálogo; puedo repetirlo si quieres.' };
        asset = assets[(index + 1) % assets.length];
        if (!asset) return { success: false, message: 'El catálogo está vacío.' };
      }
      if (asset) {
        if (signal?.aborted) return { success: false, message: 'Petición cancelada.' };
        const result = await this.manager.playClip({ callId: record.id, clipId: asset.id, key: 'natural-' + randomUUID(), volume: record.clipVolume ?? 0.5, signal });
        this.context.delete(scope);
        return { success: true, clip: { name: asset.label, state: result.clip.state, pauseReason: result.clip.pauseReason, volume: result.clip.volume }, message: `Clip preparado: ${asset.label}. Se pausa cuando hablo y continúa después.` };
      }
      if (request.action === 'resume') {
        const snapshot = await this.manager.serial(() => this.manager.driver.snapshot());
        if (this.manager.active !== record || snapshot.id !== record.nativeId) return { success: false, message: 'Cambió la llamada.' };
        const media = snapshot.audio?.video?.clip;
        if (media && ['ended', 'stopped', 'failed'].includes(media.state)) return { success: false, needs_clarification: true,
          question: media.state === 'ended' ? 'Ya terminó. ¿Lo repito?' : 'Ese clip ya se detuvo. ¿Quieres repetirlo?' };
      }
      let volume = request.volume;
      if (request.adjustment !== undefined) {
        const snapshot = await this.manager.serial(() => this.manager.driver.snapshot());
        if (this.manager.active !== record || snapshot.id !== record.nativeId) return { success: false, message: 'Cambió la llamada.' };
        const media = snapshot.audio?.video?.clip;
        const finished = media && ['ended', 'stopped', 'failed'].includes(media.state);
        const current = finished ? (record.clipVolume ?? media.volume) : media?.volume;
        if (!Number.isFinite(current)) return { success: false, message: 'No hay un clip cuyo volumen pueda ajustar.' };
        volume = Math.round(Math.max(0, Math.min(1, current + request.adjustment)) * 100) / 100;
      }
      const result = await this.manager.controlClip({ callId: record.id, action: request.action, signal, ...(volume !== undefined ? { volume } : {}) });
      if (request.action === 'pause' && result.clip.state !== 'paused') return { success: false, message: 'El clip ya terminó o se detuvo; puedo repetirlo si quieres.' };
      const percentage = Number.isFinite(result.clip.volume) ? `${Math.round(result.clip.volume * 100)}%` : 'actualizado';
      const volumeMessage = ['ended', 'stopped', 'failed'].includes(result.clip.state)
        ? `Volumen del siguiente clip: ${percentage}.` : `Volumen del clip: ${percentage}.`;
      return { success: true, clip: { name: record.clip?.label, state: result.clip.state, volume: result.clip.volume, pauseReason: result.clip.pauseReason }, message: { pause: 'Clip pausado.', resume: result.clip.state === 'paused' ? 'Continuará cuando termine de hablar.' : 'Clip reanudado.', stop: 'Clip detenido.', volume: volumeMessage }[request.action] };
    }).catch(() => ({ success: false, message: 'No pude completar esa acción. Comprueba que haya una videollamada conectada y un clip disponible.' }));
    if (!urgent) this.queue = work.then(() => {});
    this.results.set(token, { signature, work });
    while (this.results.size > 1000) this.results.delete(this.results.keys().next().value);
    return work;
  }
}
module.exports = { ClipCommands, CLIP_TOOLS };
