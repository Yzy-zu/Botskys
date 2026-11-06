'use strict';
const { normalizeCallDuration } = require('../policy/callDuration');
const { normalizeLiveRequest } = require('../policy/liveCallRequest');

const fs = require('node:fs/promises');
const { randomUUID } = require('node:crypto');
const { atomicJson, ServiceError } = require('./common.cjs');
const { sourceReceipt, queueFailureNotice } = require('./failure-notices.cjs');
const { validateScheduledTime } = require('../policy/callScheduleTime');

const { normalizeCallScheduleId } = require('../policy/callScheduleId');
const { scheduleResult } = require('./schedule-result.cjs');

const statuses = ['pending', 'executing', 'dispatched', 'cancelled', 'failed', 'interrupted'];
class CallAgenda {
  constructor({ file, manager, policy, now = Date.now, log = () => {} }) {
    Object.assign(this, { file, manager, policy, now, log }); this.rows = []; this.reservedKeys = {}; this.queue = Promise.resolve(); this.ready = false; this.running = false; this.pendingFailures = new Set();
  }
  serial(fn) { const work = this.queue.then(fn); this.queue = work.catch(() => {}); return work; }
  save() { return atomicJson(this.file, { version: 1, rows: this.rows, reservedKeys: this.reservedKeys }); }
  owns(row, origin) { return !!origin && row.origin.chatId === origin.chatId && row.origin.requesterId === origin.requesterId; }
  visible(row) { return { id: row.id.slice(0, 8), target: row.targetName, dueAt: row.dueAt, timeZone: row.timeZone, state: row.status, revision: row.revision,
    mode: row.call.live ? 'conversación' : row.call.audioId ? 'audio preparado' : 'llamada' }; }
  find(id, origin) {
    id = normalizeCallScheduleId(id);
    if (!id) throw new ServiceError('SCHEDULE_NOT_FOUND', 'Indica el ID de una llamada de tu agenda.', 404);
    const matches = this.rows.filter(r => this.owns(r, origin) && r.id.startsWith(id));
    if (matches.length !== 1) throw new ServiceError('SCHEDULE_NOT_FOUND', 'No identifiqué ese encargo entre tus llamadas programadas.', 404);
    return matches[0];
  }
  async init() {
    try {
      const data = JSON.parse(await fs.readFile(this.file, 'utf8'));
      if (data.version !== 1 || !Array.isArray(data.rows) || data.rows.length > 1000) throw Error('schema');
      const keys = new Set(), ids = new Set();
      for (const r of data.rows) {
        if (!r || !/^[a-f0-9-]{36}$/.test(r.id) || !/^[A-Za-z0-9._:-]{8,128}$/.test(r.key) || ids.has(r.id) || keys.has(r.key) ||
            !statuses.includes(r.status) || !Number.isSafeInteger(r.dueAt) || !Number.isFinite(r.createdAt) || typeof r.timeZone !== 'string' ||
            !Number.isInteger(r.revision) || r.revision < 1 || !r.origin || !r.call || normalizeCallDuration(r.call.live, r.call.maxSeconds) !== r.call.maxSeconds ||
            !Number.isFinite(r.call.volume) || r.call.volume < 0 || r.call.volume > 1 || typeof r.call.live !== 'boolean' || typeof r.call.endAfterAudio !== 'boolean' || r.call.durationFromAnswer !== true ||
            (r.call.live && r.call.audioId) || (r.call.endAfterAudio && !r.call.audioId) || !r.sourceReceipt ||
            !Array.isArray(r.edits) || r.edits.length > 100) throw Error('row');
        normalizeLiveRequest(r.call.live, r.call.liveRequest);
        sourceReceipt(r.sourceReceipt, r.origin); new Intl.DateTimeFormat('en', { timeZone: r.timeZone });
        ids.add(r.id); keys.add(r.key);
      }
      if (data.reservedKeys !== undefined && (!data.reservedKeys || Array.isArray(data.reservedKeys) || typeof data.reservedKeys !== 'object' || Object.entries(data.reservedKeys).some(([key,value]) => !/^[A-Za-z0-9._:-]{8,128}$/.test(key) || value !== true))) throw Error('keys');
      this.reservedKeys = data.reservedKeys || {};
      this.rows = data.rows;
      for (const row of this.rows) Object.defineProperty(this.reservedKeys, row.key, { value: true, enumerable: true, configurable: true });
    } catch (error) { if (error.code !== 'ENOENT') throw new ServiceError('AGENDA_INVALID', 'No se puede leer la agenda; no se programarán llamadas.', 500); }
    for (const row of this.rows) {
      if (Object.hasOwn(this.manager.journal.cancelledKeys, row.key) && ['pending', 'executing'].includes(row.status)) row.status = 'cancelled';
      if (['pending', 'executing'].includes(row.status) && this.manager.journal.byKey(row.key)?.reason === 'SCHEDULE_RESERVATION_SAVE_FAILED') {
        row.status = 'failed'; row.reason = 'RESERVATION_SAVE_FAILED';
      }
      if (row.status === 'executing') {
        const prior = this.manager.journal.byKey(row.key);
        row.status = prior ? 'dispatched' : 'interrupted'; row.reason = prior ? 'recovered_call_receipt' : 'service_restart';
        if (prior) row.callId = prior.id;
      }
    }
    await this.save(); this.ready = true;
    for (const row of this.rows.filter(r => ['failed', 'interrupted'].includes(r.status))) this.pendingFailures.add(row.id);
    await this.flushPendingFailures();
  }
  validateOrigin(origin) {
    if (!origin || !this.manager.destinationPolicy.localEnabled(origin)) throw new ServiceError('SCHEDULE_DENIED', 'No puedes gestionar llamadas programadas desde este chat.', 403);
  }
  async create({ key, targetJid, origin, dueAt, timeZone, maxSeconds, audioId, volume = 0.7, live = false, liveRequest, endAfterAudio = false, durationFromAnswer = true, sourceReceipt: receipt }) {
    return this.serial(async () => {
      this.validateOrigin(origin);
      if (!this.ready || !this.policy.enabled || !this.manager.featureEnabled('agenda') || !this.manager.featureEnabled('outgoing')) throw new ServiceError('SCHEDULE_DISABLED', 'Las llamadas programadas no están disponibles.', 503);
      if (typeof key !== 'string' || !/^[A-Za-z0-9._:-]{8,128}$/.test(key)) throw new ServiceError('INVALID_KEY', 'Clave de encargo no válida.', 400);
      if (Object.hasOwn(this.manager.journal.cancelledKeys, key)) throw new ServiceError('CANCELLED', 'Ese encargo fue cancelado.');
      let target;
      try { target = this.manager.destinationPolicy.authorize(targetJid, origin); }
      catch { throw new ServiceError('DESTINATION_NOT_ENABLED', 'Ese destino no está habilitado para esta orden.', 403); }
      if (target.requireMembership) target.name = (await this.manager.resolveGroup({ origin, id: target.id })).group.name;
      receipt = sourceReceipt(receipt, origin);
      maxSeconds = normalizeCallDuration(live, maxSeconds);
      if (!receipt || timeZone !== this.policy.timeZone ||
          !Number.isFinite(volume) || volume < 0 || volume > 1 || typeof live !== 'boolean' || typeof endAfterAudio !== 'boolean' ||
          durationFromAnswer !== true || (live && (audioId || endAfterAudio)) || (endAfterAudio && !audioId)) throw new ServiceError('INVALID_SCHEDULE', 'El encargo o su horario no son válidos.', 400);
      liveRequest = normalizeLiveRequest(live, liveRequest);
      if (live && !this.manager.featureEnabled('live')) throw new ServiceError('LIVE_DISABLED', 'La conversación en vivo está desactivada.', 503);
      if (audioId) audioId = (await this.manager.audioStore.get(audioId)).id;
      const call = { maxSeconds, volume, live, ...(liveRequest ? { liveRequest } : {}), endAfterAudio, durationFromAnswer, ...(audioId ? { audioId } : {}) };
      const fingerprint = JSON.stringify({ targetJid: target.id, origin, dueAt, timeZone, call, receipt });
      const prior = this.rows.find(r => r.key === key);
      if (prior) {
        if (prior.fingerprint !== fingerprint) throw new ServiceError('KEY_CONFLICT', 'Ese mensaje ya corresponde a otro encargo.');
        return { replayed: true, schedule: this.visible(prior) };
      }
      if (Object.hasOwn(this.reservedKeys, key)) throw new ServiceError('SCHEDULE_ALREADY_PROCESSED', 'Ese mensaje ya tenía un encargo procesado. Envíame uno nuevo si quieres otra llamada.', 409);
      validateScheduledTime(dueAt, this.policy, { now: this.now(), maxSeconds });
      this.rows = this.rows.filter(r => this.pendingFailures.has(r.id) || ['pending', 'executing'].includes(r.status) || r.createdAt > this.now() - 86400000);
      if (this.rows.length >= 1000) throw new ServiceError('AGENDA_FULL', 'La agenda está llena.', 429);
      const row = { id: randomUUID(), key, targetJid: target.id, targetName: target.name, origin: { chatId: origin.chatId, requesterId: origin.requesterId },
        dueAt, timeZone, call, sourceReceipt: receipt, createdAt: this.now(), status: 'pending', revision: 1, edits: [], fingerprint, policyRevision: this.manager.policyRevision };
      this.rows.push(row); Object.defineProperty(this.reservedKeys, key, { value: true, enumerable: true, configurable: true });
      try { await this.save(); } catch (error) { this.rows.pop(); delete this.reservedKeys[key]; throw error; }
      return { replayed: false, schedule: this.visible(row) };
    });
  }
  async list(origin) { this.validateOrigin(origin); return { schedules: this.rows.filter(r => this.owns(r, origin) && ['pending', 'executing'].includes(r.status)).sort((a, b) => a.dueAt - b.dueAt || a.createdAt - b.createdAt || a.id.localeCompare(b.id)).map(r => this.visible(r)) }; }
  async get({ id, origin }) {
    this.validateOrigin(origin);
    const row = this.find(id, origin);
    return { schedule: this.visible(row), result: scheduleResult(row, this.manager.journal.byKey(row.key)) };
  }
  async cancelByKey(key) {
    return this.serial(async () => {
      const row = this.rows.find(r => r.key === key);
      if (row && ['pending', 'executing'].includes(row.status)) { row.status = 'cancelled'; await this.save(); }
    });
  }
  async cancel({ id, origin }) {
    this.validateOrigin(origin); const row = this.find(id, origin);
    if (!['pending', 'executing'].includes(row.status)) return { schedule: this.visible(row), alreadyEnded: true };
    await this.manager.cancelKey(row.key);
    return { schedule: this.visible(row) };
  }
  async update({ id, origin, key, dueAt, timeZone }) {
    return this.serial(async () => {
      this.validateOrigin(origin); const row = this.find(id, origin);
      if (typeof key !== 'string' || !/^[A-Za-z0-9._:-]{8,128}$/.test(key) || timeZone !== row.timeZone) throw new ServiceError('INVALID_SCHEDULE', 'Cambio no válido.', 400);
      const prior = row.edits.find(e => e.key === key);
      if (prior) { if (prior.dueAt !== dueAt) throw new ServiceError('KEY_CONFLICT', 'Ese cambio ya tenía otra hora.'); return { replayed: true, schedule: this.visible(row) }; }
      if (row.status !== 'pending' || row.edits.length >= 100) throw new ServiceError('SCHEDULE_CLOSED', 'Ese encargo ya no admite cambios.');
      validateScheduledTime(dueAt, this.policy, { now: this.now(), maxSeconds: row.call.maxSeconds });
      const before = structuredClone(row);
      row.dueAt = dueAt; row.revision++; row.edits.push({ key, dueAt });
      try { await this.save(); } catch (error) { Object.assign(row, before); throw error; }
      return { replayed: false, schedule: this.visible(row) };
    });
  }
  async reportFailure(row) {
    await this.manager.command(async () => {
      if (this.manager.journal.byKey(row.key)) return;
      const record = { id: randomUUID(), key: row.key, targetJid: row.targetJid, origin: row.origin, sourceReceipt: row.sourceReceipt,
        requestedAt: this.now(), endedAt: this.now(), state: 'failed', reason: 'SCHEDULE_' + (row.reason || 'FAILED'), maxSeconds: row.call.maxSeconds };
      queueFailureNotice(record, this.now()); this.manager.journal.records.push(record);
      try { await this.manager.journal.save(); }
      catch (error) {
        const index = this.manager.journal.records.indexOf(record);
        if (index >= 0) this.manager.journal.records.splice(index, 1);
        throw error;
      }
    });
  }
  async flushPendingFailures() {
    if (!this.pendingFailures.size) return;
    let saved = false;
    // One atomic agenda write covers all pending terminal states.
    try { await this.serial(() => this.save()); saved = true; } catch {}
    for (const id of this.pendingFailures) {
      const row = this.rows.find(entry => entry.id === id);
      if (!row || !['failed', 'interrupted'].includes(row.status)) { this.pendingFailures.delete(id); continue; }
      let reported = false;
      try { await this.reportFailure(row); reported = true; } catch {}
      if (saved && reported) this.pendingFailures.delete(id);
    }
  }
  async tick() {
    if (this.running || !this.ready || this.manager.stopping) return;
    this.running = true;
    try {
      await this.flushPendingFailures();
      if (!this.policy.enabled || !this.manager.featureEnabled('agenda') || !this.manager.featureEnabled('outgoing')) return;
      for (const id of this.rows.filter(r => r.status === 'pending' && r.dueAt <= this.now()).map(r => r.id)) {
        const row = await this.serial(async () => {
          const entry = this.rows.find(r => r.id === id);
          if (!entry || entry.status !== 'pending' || entry.dueAt > this.now()) return null;
          entry.status = 'executing';
          try { await this.save(); }
          catch {
            entry.status = 'failed'; entry.reason = 'RESERVATION_SAVE_FAILED'; this.pendingFailures.add(entry.id);
          }
          return entry;
        });
        if (!row) continue;
        if (row.status === 'failed') { await this.flushPendingFailures(); continue; }
        let error;
        try {
          if (this.manager.policyRevision && (row.policyRevision !== this.manager.policyRevision || !this.manager.policyCurrent())) throw Object.assign(Error('changed policy'), { code: 'SCHEDULE_POLICY_CHANGED' });
          const runAt = this.now();
          if (runAt - row.dueAt > this.policy.maxLatenessMs) throw Error('MISSED');
          if (row.timeZone !== this.policy.timeZone) throw Object.assign(Error('changed policy'), { code: 'SCHEDULE_POLICY_CHANGED' });
          validateScheduledTime(runAt, this.policy, { now: runAt - 1, maxSeconds: row.call.maxSeconds });
          this.manager.destinationPolicy.authorize(row.targetJid, row.origin);
          if (row.status !== 'executing' || Object.hasOwn(this.manager.journal.cancelledKeys, row.key)) throw Object.assign(Error('cancelled'), { code: 'CANCELLED' });
          const result = await this.manager.startCall({ key: row.key, targetJid: row.targetJid, origin: row.origin, sourceReceipt: row.sourceReceipt, ...row.call, scheduleWindow: { dispatchBy: row.dueAt + this.policy.maxLatenessMs } });
          await this.serial(async () => { if (row.status === 'executing') { row.status = 'dispatched'; row.callId = result.call.id; await this.save(); } });
        } catch (failure) { error = failure; }
        if (error) {
          await this.serial(async () => {
            if (row.status === 'cancelled') return;
            row.status = error.code === 'CANCELLED' ? 'cancelled' : 'failed'; row.reason = error.code || error.message || 'FAILED';
            if (row.status === 'failed') {
              this.pendingFailures.add(row.id);
              try { await this.save(); } catch { /* Retry terminal bookkeeping, never the call. */ }
            } else await this.save();
          });
          if (row.status === 'failed') await this.flushPendingFailures();
        }
      }
    } finally { this.running = false; }
  }
  start() { this.timer = setInterval(() => { this.tick().catch(() => this.log('agenda_tick_failed')); }, 1000); this.timer.unref(); }
  stop() { clearInterval(this.timer); }
}
module.exports = { CallAgenda };
