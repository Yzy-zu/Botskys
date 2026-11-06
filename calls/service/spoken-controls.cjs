'use strict';
const VOICES = Object.freeze({ Aoede: 'Botsky habitual', Kore: 'Firme', Zephyr: 'Suave' });
const SPOKEN_TOOLS = [{ functionDeclarations: [{ name: 'controlar_llamada', description: 'Controla solo esta llamada privada por petición de la persona. hangup: pide cierre tras tu despedida breve. keep_call cancela un cierre pendiente. volume: dirección up/down o value0.1–1. voices lista voces. voice solicita cambio de voz por reanudación, sin cambiar personaje.', parameters: { type: 'OBJECT', properties: { action: { type: 'STRING', enum: ['hangup','keep_call','volume','voices','voice'] }, direction: { type: 'STRING', enum: ['up','down'] }, value: { type: 'NUMBER', minimum: 0.1, maximum: 1 }, voice: { type: 'STRING', enum: Object.keys(VOICES) } }, required: ['action'] } }] }];
const SPOKEN_SYSTEM = '\nEn llamadas privadas puedes usar controlar_llamada como única herramienta de ese pedido. Interpreta la intención de despedida o cierre dirigida a ti por el contexto, sin exigir nombres, apodos ni frases fijas; si pide terminar, usa hangup: llama primero y, si devuelve cierre pendiente, despídete con una frase breve y natural; el código colgará después del audio. No cuelgues por saludos, ejemplos, frases citadas, despedidas de otras personas ni negaciones («no cuelgues»); si es ambiguo pregunta. Si cambió de opinión usa keep_call. «Habla más fuerte/bajito» pide volume up/down, no cambies solo tu tono ni el volumen del teléfono. No afirmes un cambio fallido. Para cambiar voz lista voices si falta elección: Aoede habitual, Kore firme, Zephyr suave; conserva personalidad Botsky, sin clones. voice devuelve pending: indica que se está intentando, no que ya se aplicó. El cambio puede requerir una pausa; no prometas éxito si no hubo aceptación.';

class SpokenControls {
  constructor(manager, { wait = ms => new Promise(r => setTimeout(r, ms)), graceMs = 10000 } = {}) { this.manager = manager; this.wait = wait; this.graceMs = graceMs; this.pending = new Map(); }
  current(record, session) {
    const live = this.manager.liveController?.active;
    return this.manager.active === record && record.state === 'connected' && !record.groupId && live?.callId === record.id && live.session === session && !live.stopped && !live.suspended && !session.closed;
  }
  async execute(record, args, { signal } = {}) {
    const session = this.manager.liveController?.active?.session;
    if (!args || Array.isArray(args) || Object.keys(args).some(k => !['action','direction','value','voice'].includes(k)) || signal?.aborted || !this.current(record, session)) return { success: false, message: 'Esta llamada ya no admite ese control.' };
    const valid = args.action === 'volume' ? args.voice === undefined && ((['up','down'].includes(args.direction) && args.value === undefined) || (args.direction === undefined && typeof args.value === 'number' && Number.isFinite(args.value) && args.value >= 0.1 && args.value <= 1)) : args.direction === undefined && args.value === undefined && (args.action === 'voice' ? Object.hasOwn(VOICES,args.voice) : args.voice === undefined);
    if (!valid) return { success: false, message: 'Indica una opción válida.' };
    if (args.action === 'voices') return { success: true, voices: VOICES };
    if (args.action === 'voice') {
      if (this.pending.has(record.id)) return { success: false, message: 'La llamada ya está despidiéndose.' };
      return session.requestVoiceChange(args.voice, { signal });
    }
    if (args.action === 'keep_call') { this.cancel(record.id); return { success: true, message: 'Sigue la conversación; no cuelgues.' }; }
    if (args.action === 'volume') {
      const current = typeof record.volume === 'number' ? record.volume : 0.7;
      const volume = Math.round((args.value ?? Math.max(0.1,Math.min(1,current + (args.direction === 'up' ? 0.15 : -0.15)))) * 100) / 100;
      await this.manager.setVolume({ callId: record.id, volume });
      if (signal?.aborted || !this.current(record,session)) return { success: false, message: 'La llamada cambió.' };
      return { success: true, volume, atLimit: volume === 0.1 || volume === 1 };
    }
    if (args.action !== 'hangup') return { success: false, message: 'Control no disponible.' };
    if (!this.pending.has(record.id)) {
      const pending = { record, session, turns: session.stats.outputTurns, bytes: session.stats.outputBytes };
      this.pending.set(record.id,pending);
      pending.timer = setTimeout(() => void this.finish(pending).catch(() => {}),this.graceMs); pending.timer.unref?.();
      signal?.addEventListener('abort', () => { if (this.pending.get(record.id) === pending) this.cancel(record.id); }, { once: true });
    }
    return { success: true, pending: true, message: 'Despídete ahora con una frase breve. Se cerrará después de reproducirla; no continúes otro tema.' };
  }
  turnComplete(record) {
    const p = this.pending.get(record.id);
    if (!p || p.draining || p.session.responding || p.session.generationDone === false || p.session.stats.outputTurns <= p.turns || p.session.stats.outputBytes <= p.bytes) return;
    p.draining = true;
    void this.drain(p).catch(() => {}); // The bounded timer remains the close fallback.
  }
  async drain(p) {
    try {
      const live = this.manager.liveController.active;
      await live.output;
      while (this.pending.get(p.record.id) === p && this.current(p.record,p.session)) {
        const output = live.output;
        await output;
        if (p.session.responding || p.session.generationDone === false) { p.draining = false; return; }
        const playback = await this.manager.driver.livePlayback(live.nativeId,live.id,live.epoch);
        if (p.session.responding || p.session.generationDone === false) { p.draining = false; return; }
        if (live.output !== output) continue;
        if (playback?.discarded) return;
        if (playback?.playing === false && Number.isFinite(playback.endedAt)) { await this.finish(p); return; }
        await this.wait(100);
      }
    } finally {
      p.draining = false;
    }
  }

  async finish(p) {
    if (this.pending.get(p.record.id) !== p) return;
    this.cancel(p.record.id);
    // Closing authority belongs to this exact call record, including recovery.
    if (this.manager.active === p.record && !p.record.groupId && !['ended','failed','cancelled','interrupted'].includes(p.record.state)) await this.manager.requestEnd(p.record,'spoken_goodbye');
  }
  cancel(id) { const p = this.pending.get(id); if (p) { clearTimeout(p.timer); this.pending.delete(id); } }
}
module.exports = { SpokenControls, SPOKEN_TOOLS, SPOKEN_SYSTEM, VOICES };
