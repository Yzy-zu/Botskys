'use strict';
const { normalizeCallDuration } = require('../policy/callDuration');
const { scheduledWindowEnd } = require('../policy/callScheduleTime');
const { normalizeLiveRequest } = require('../policy/liveCallRequest');

const { randomUUID, createHash } = require('node:crypto');
const { ServiceError, terminal } = require('./common.cjs');
const { createCallDestinationPolicy, canonicalPhoneJid } = require('../policy/callDestinations');

const { sourceReceipt, queueFailureNotice } = require('./failure-notices.cjs');

const realClock = { now: Date.now, setTimeout, clearTimeout };
const AVATAR_NAMES = {
  background: new Set(['studio', 'neon', 'sunset', 'night']),
  expression: new Set(['neutral', 'relaxed', 'happy', 'angry', 'sad', 'surprised', 'wink', 'laugh']),
  gesture: new Set(['wave', 'nod', 'shake_head', 'hand_to_chest']),
  blush: new Set(['soft'])
};

class CallManager {
  constructor({ driver, journal, group, audioStore, audiencePolicy = {}, destinationPolicy, clock = realClock, pollMs = 1000, log = () => {} }) {
    Object.assign(this, { driver, journal, group, audioStore, clock, pollMs, log });
    this.audiencePolicy = { emptyGraceMs: 5000, unavailableGraceMs: 15000, ...audiencePolicy };
    this.destinationPolicy = destinationPolicy || createCallDestinationPolicy({ lab: group, env: {} });
    this.state = 'starting'; this.active = null; this.observed = null;
    this.queue = Promise.resolve(); this.commandQueue = Promise.resolve();
    this.stopping = false; this.failureCount = 0; this.generation = 0;
    this.timers = new Map(); this.lastError = null; this.finishing = new Map(); this.cleanupPending = new WeakSet();
    driver.onLost = reason => this.lost(reason).catch(error => this.fatal(error));
  }
  serial(task) {
    const result = this.queue.then(async () => {
      this.browserBusySince = this.clock.now();
      try { return await task(); } finally { this.browserBusySince = null; }
    });
    this.queue = result.catch(() => {});
    return result;
  }
  command(task) {
    const result = this.commandQueue.then(task);
    this.commandQueue = result.catch(() => {});
    return result;
  }
  timer(name, ms, action) {
    this.clearTimer(name);
    const remaining = Math.max(0, ms), chunk = Math.min(remaining, 2147483647);
    const deadline = this.clock.now() + remaining;
    this.timers.set(name, this.clock.setTimeout(() => {
      this.timers.delete(name);
      if (this.clock.now() < deadline) { this.timer(name, deadline - this.clock.now(), action); return; }
      Promise.resolve().then(action).catch(error => this.fatal(error));
    }, chunk));
  }
  clearTimer(name) { if (this.timers.has(name)) this.clock.clearTimeout(this.timers.get(name)); this.timers.delete(name); }
  publicCall(record) {
    if (!record) return null;
    const { key, nativeId, incomingPeer, endRequested, audioRequests, clipRequests, autoplayAttempted, sourceReceipt, failureNotice, liveRequest, ...result } = record;
    if (result.recovery) { const { originalNativeId, ...safeRecovery } = result.recovery; result.recovery = safeRecovery; }
    return structuredClone(result);
  }
  featureEnabled(name) { return this.featureStore?.value[name] !== false; }
  status() {
    return { state: this.state, group: this.group, activeCall: this.publicCall(this.active),
      lastCall: this.publicCall(this.journal.records.at(-1)),
      externalCallPresent: !!(this.observed && !this.active), lastError: this.lastError, audioRuntime: this.audioRuntime || null,
      liveRuntime: this.liveController?.status?.() || null, audiencePolicy: this.audiencePolicy,
      callRecoveryPolicy: { maxAttempts: 1, probeWindowMs: 12000, resume: 'confirmed_position', redial: 'same_native_failed_twice', onRestart: 'interrupt_without_redial' },
      features: this.featureStore?.value || { outgoing:true, incoming:true, live:true, agenda:true },
      agenda: { ready: !!this.agenda?.ready, ...this.agenda?.policy, enabled: !!this.agenda?.policy.enabled && this.featureEnabled('agenda') && this.featureEnabled('outgoing') },
      closePolicy: { maxConcurrentCalls: 1, cleanupBlocksNewCall: true, durableFailureReactions: true },
      privateCallCapabilities: this.privateCallCapabilities || null,
      destinationPolicy: { ownerAnyGroupEnabled: this.destinationPolicy.ownerAnyGroupEnabled, allGroupsEnabled: this.destinationPolicy.allGroupsEnabled, ownerExternalEnabled: this.destinationPolicy.ownerExternalEnabled,
        groupAudienceValidated: this.destinationPolicy.groupAudienceValidated,
        enabledPrivateCount: this.destinationPolicy.privateIds.size,
        enabledGroupCount: this.destinationPolicy.groups.filter(group => this.destinationPolicy.groupEnabled(group.id)).length },
      incomingAutoAnswer: { enabled: !!this.incomingPolicy?.enabled && this.featureEnabled('incoming') && this.featureEnabled('live'), scope: 'owner_voice_and_video', lastSeen: this.incomingObservation || null } };
  }
  getCall(id) {
    const record = this.journal.byId(id);
    if (!record) throw new ServiceError('CALL_NOT_FOUND', 'No se encontró esa llamada.', 404);
    return this.publicCall(record);
  }
  async boot() {
    await this.journal.load();
    for (const record of this.journal.records) {
      if (!terminal(record.state)) {
        Object.assign(record, { state: 'interrupted', endedAt: this.clock.now(), reason: 'service_restart' });
        if (record.recovery && !['recovered', 'failed'].includes(record.recovery.phase)) Object.assign(record.recovery, { phase: 'failed', failure: 'service_restart' });
      }
      queueFailureNotice(record, this.clock.now());
      for (const playback of [record.playback, ...(record.audioRequests || []).map(r => r.playback)]) {
        if (playback && ['starting', 'playing', 'paused'].includes(playback.state)) Object.assign(playback, { state: 'interrupted', finishedAt: this.clock.now() });
      }
    }
    await this.journal.save();
    return this.recover();
  }
  async recover() {
    if (this.stopping || this.recovering || this.state === 'error') return;
    this.recovering = true;
    const generation = ++this.generation;
    this.state = this.failureCount ? 'recovering' : 'starting';
    try {
      await this.serial(async () => {
        await this.driver.close();
        if (this.stopping || generation !== this.generation) return;
        await this.driver.start();
      });
      if (this.stopping || generation !== this.generation) return;
      this.state = 'ready'; this.failureCount = 0; this.lastError = null;
      this.log('browser_ready');
      this.schedulePoll();
    } catch (error) {
      if (this.stopping) return;
      this.state = error.code === 'NEEDS_LINK' ? 'needs_link' : 'recovering';
      this.lastError = { code: error.code || 'BROWSER_START_FAILED', message: error.code ? error.message : 'No se pudo preparar el navegador.' };
      this.failureCount++;
      this.log('browser_retry', { code: this.lastError.code });
      if (this.state === 'needs_link') this.scheduleLinkCheck();
      else this.scheduleRecovery();
    } finally { this.recovering = false; }
  }
  scheduleRecovery() {
    if (!this.stopping && this.state !== 'error') this.timer('recovery', Math.min(30_000, 2000 * 2 ** Math.min(this.failureCount - 1, 4)), () => this.recover());
  }
  scheduleLinkCheck() {
    if (this.stopping) return;
    this.timer('link', 2000, async () => {
      try {
        if (await this.serial(() => this.driver.completeLink())) {
          this.state = 'ready'; this.failureCount = 0; this.lastError = null;
          this.log('browser_ready'); this.schedulePoll();
        } else this.scheduleLinkCheck();
      } catch {
        this.state = 'recovering'; this.failureCount++; this.scheduleRecovery();
      }
    });
  }
  schedulePoll() {
    if (!this.stopping && this.state === 'ready') this.timer('poll', this.pollMs, async () => {
      try { await this.serial(() => this.poll()); }
      catch (error) { await this.pollFailure(error); }
      this.schedulePoll();
    });
  }
  async liveStep(record, action) {
    try { return await this.liveController[action](record); }
    catch (error) { error.callFailureSource ||= 'live'; throw error; }
  }
  async pollFailure(error) {
    if (error.callFailureSource !== 'live') return this.lost(error.code || 'browser_unavailable');
    const record = this.active;
    if (!record || terminal(record.state) || record.endRequested) return;
    record.liveError = { code: error.code || 'LIVE_FAILED' };
    await this.journal.save();
    void this.requestEnd(record, 'live_failed').catch(error => this.fatal(error));
  }
  async lost(reason = 'browser_disconnected') {
    if (this.stopping || this.state !== 'ready') return;
    if (this.active && await this.beginCallRecovery(this.active, reason, { browserLost: true })) return;
    this.state = 'recovering'; this.lastError = { code: 'BROWSER_LOST', message: 'Se perdió la sesión del navegador.' };
    this.clearTimer('poll');
    if (this.active) await this.finish(this.active, 'interrupted', reason);
    this.observed = null; this.failureCount++;
    this.scheduleRecovery();
  }
  recoveryAllowed(record) {
    return this.active === record && !this.stopping && !record.endRequested && !terminal(record.state) &&
      record.nativeId && (record.expiresAt === null || this.clock.now() < record.expiresAt) && !Object.hasOwn(this.journal.cancelledKeys, record.key);
  }
  async beginCallRecovery(record, trigger, { browserLost = false } = {}) {
    if (!this.recoveryAllowed(record) || record.recovery?.attempts || (!record.connectedAt && trigger !== 'native_FAILED')) return false;
    record.recovery = { attempts: 1, phase: 'checking', trigger, claimedAt: this.clock.now(),
      originalNativeId: record.nativeId, originalConnectedAt: record.connectedAt || null, failedObserved: trigger === 'native_FAILED', deadline: Math.min(record.expiresAt ?? Infinity, this.clock.now() + 12000), redialUsed: false };
    record.state = 'recovering';
    // Persist the budget before probing or dispatching. Restarting the process
    // cannot produce a second attempt (boot interrupts unfinished work).
    await this.journal.save();
    if (!this.recoveryAllowed(record)) return true;
    try {
      if (record.playback?.state === 'starting') throw new ServiceError('RECOVERY_AUDIO_UNCONFIRMED', 'No se confirmó el inicio del audio antes del corte.');
      if (record.live && record.liveStarted) await this.liveStep(record, 'suspend');
      else if (record.playback?.state === 'playing') {
        const playback = record.playback;
        const offset = playback.confirmedPositionSeconds || playback.offsetSeconds || 0;
        if (offset >= playback.durationSeconds) { void this.requestEnd(record, 'audio_completed'); return true; }
        await this.driver.pauseAudio(record.nativeId, playback.id, offset);
        Object.assign(playback, { state: 'paused', confirmedPositionSeconds: offset });
      }
      if (!this.recoveryAllowed(record)) return true;
      record.recovery.phase = 'waiting';
      if (browserLost) { this.state = 'recovering_call'; this.clearTimer('poll'); }
      await this.journal.save();
      this.scheduleCallRecovery(record);
      this.log('call_recovery_claimed', { id: record.id, trigger });
    } catch (error) {
      if (error.callFailureSource === 'live') { await this.pollFailure(error); return true; }
      await this.failCallRecovery(record, error.code || 'RECOVERY_PAUSE_FAILED', browserLost);
    }
    return true;
  }
  scheduleCallRecovery(record) {
    this.timer('call-recovery', 1000, () => this.serial(() => this.advanceCallRecovery(record)));
  }
  async failCallRecovery(record, reason, browserLost = false) {
    if (this.active !== record || terminal(record.state)) return;
    if (record.recovery) Object.assign(record.recovery, { phase: 'failed', failure: reason });
    if (browserLost) {
      this.state = 'recovering';
      await this.finish(record, 'interrupted', reason);
      this.failureCount++; this.scheduleRecovery();
    } else {
      void this.requestEnd(record, reason).catch(error => this.fatal(error));
    }
  }
  async advanceCallRecovery(record) {
    if (!this.recoveryAllowed(record) || record.recovery?.phase !== 'waiting') return;
    const unavailable = this.state === 'recovering_call';
    if (this.clock.now() >= record.recovery.deadline) { await this.failCallRecovery(record, 'recovery_timeout', unavailable); return; }
    try {
      const snapshot = await (this.driver.recoverSnapshot ? this.driver.recoverSnapshot() : this.driver.snapshot());
      if (!this.recoveryAllowed(record)) return;
      this.state = 'ready';
      this.observed = snapshot.active ? snapshot : null;
      if (snapshot.userEnded || (snapshot.active && (snapshot.id !== record.nativeId || !!snapshot.isVideo !== !!record.video || snapshot.outgoing === (record.direction === 'incoming')))) {
        await this.finish(record, 'ended', snapshot.userEnded ? 'remote_or_native_end' : 'different_call_observed');
      } else if (snapshot.active && snapshot.id === record.nativeId && snapshot.connected) {
        if (snapshot.audience?.known && snapshot.audience.connectedHumans === 0) {
          record.state = 'connected'; record.recovery.phase = 'recovered';
          await this.observeAudience(record, snapshot); await this.journal.save(); this.schedulePoll(); return;
        }
        if (!snapshot.audience?.known || snapshot.audience.connectedHumans < 1) { this.scheduleCallRecovery(record); this.schedulePoll(); return; }
        if (record.playback?.state === 'paused') {
          await this.driver.resumeAudio(record.nativeId, record.playback.id, record.playback.confirmedPositionSeconds || 0);
          if (!this.recoveryAllowed(record)) return;
          record.playback.state = 'playing';
        }
        if (record.live && record.liveStarted) await this.liveStep(record, 'resume');
        if (!this.recoveryAllowed(record)) return;
        if (!record.connectedAt) { record.connectedAt = this.clock.now(); this.answerDeadline(record); }
        record.state = 'connected'; record.recovery.phase = 'recovered'; record.recovery.recoveredAt = this.clock.now();
        await this.journal.save();
        this.log('call_recovered', { id: record.id, mode: 'same_native_call' });
      } else if (!snapshot.active) {
        // No inference from a disappeared call or numeric None/HandledRemotely.
        // Only a second explicit FAILED observation authorizes a new offer.
        if (snapshot.id === record.nativeId && snapshot.state === 'FAILED' && snapshot.outgoing && record.direction !== 'incoming' && !record.recovery.redialUsed && (record.expiresAt === null || record.expiresAt - this.clock.now() >= 5000)) {
          if (!record.recovery.failedObserved) {
            record.recovery.failedObserved = true; await this.journal.save(); this.scheduleCallRecovery(record);
          } else if (this.clock.now() < record.recovery.deadline) await this.redialRecovery(record);
          else await this.failCallRecovery(record, 'recovery_timeout');
        } else await this.finish(record, 'ended', 'remote_or_native_end');
      } else if (this.clock.now() >= record.recovery.deadline) {
        await this.failCallRecovery(record, 'recovery_timeout');
      } else this.scheduleCallRecovery(record);
      this.schedulePoll();
    } catch (error) {
      if (!this.recoveryAllowed(record)) return;
      if (error.callFailureSource === 'live') { await this.pollFailure(error); return; }
      if (this.clock.now() < record.recovery.deadline && record.recovery.phase === 'waiting') this.scheduleCallRecovery(record);
      else await this.failCallRecovery(record, error.code || 'recovery_unavailable', unavailable);
    }
  }
  async redialRecovery(record) {
    if (!this.recoveryAllowed(record) || record.recovery.redialUsed) return;
    record.recovery.redialUsed = true; record.recovery.phase = 'redial_reserved';
    const oldPlayback = record.playback;
    if (oldPlayback && ['paused', 'playing'].includes(oldPlayback.state)) {
      record.recovery.resume = { audioId: oldPlayback.audioId, offsetSeconds: oldPlayback.confirmedPositionSeconds || oldPlayback.offsetSeconds || 0 };
      record.audioId = oldPlayback.audioId;
      Object.assign(oldPlayback, { state: 'interrupted', finishedAt: this.clock.now() });
      record.playback = null;
    }
    await this.journal.save();
    if (!this.recoveryAllowed(record)) return;
    record.audioToken = record.id + '-recovery-1';
    record.autoplayAttempted = false;
    if (record.live) record.liveStarted = false;
    record.state = 'starting'; record.nativeId = null;
    await this.dial(record);
    if (this.active !== record || terminal(record.state) || record.endRequested) return;
    record.recovery.phase = record.connectedAt && record.state === 'connected' ? 'recovered' : 'redialing';
    await this.journal.save();
    this.log('call_recovery_redial', { id: record.id });
  }
  async resolveGroup({ origin, name, id } = {}) {
    const currentGroup = this.destinationPolicy.allGroupsEnabled && id && origin?.chatId === id && /^\d+(?:-\d+)?@g\.us$/.test(id);
    if (!(this.destinationPolicy.ownerAnyGroupEnabled && this.destinationPolicy.ownerPrivate(origin)) && !currentGroup) throw new ServiceError('CALL_DESTINATION_DENIED', 'Solo el propietario desde su privado o el chat grupal actual puede buscar destinos unidos.', 403);
    if ((name === undefined) === (id === undefined) || (name !== undefined && (typeof name !== 'string' || !name.trim() || name.length > 300)) || (id !== undefined && !/^\d+(?:-\d+)?@g\.us$/.test(id))) throw new ServiceError('CALL_TARGET_CLARIFICATION', 'Indica un solo nombre de grupo válido.', 400);
    return this.serial(async () => {
      if (this.state !== 'ready' || this.stopping) throw new ServiceError('NOT_READY', 'El servicio no está listo.', 503);
      return { group: await this.driver.resolveGroup({ name, id }) };
    });
  }
  async startCall({ key, groupId, targetJid, origin, maxSeconds, audioId, volume = 0.7, endAfterAudio = false, durationFromAnswer = false, live = false, video = false, liveRequest, sourceReceipt: receipt, scheduleWindow } = {}) {
    return this.command(async () => {
      if (this.stopping) throw new ServiceError('STOPPING', 'El servicio se está deteniendo.', 503);
      if (this.policyCurrent && !this.policyCurrent()) throw new ServiceError('POLICY_MISMATCH', 'La política cambió; reinicia el servicio antes de iniciar.', 409);
      if (typeof key !== 'string' || !/^[A-Za-z0-9._:-]{8,128}$/.test(key)) throw new ServiceError('INVALID_KEY', 'Usa una clave de idempotencia de 8 a 128 caracteres.', 400);
      if (groupId && targetJid && groupId !== targetJid) throw new ServiceError('INVALID_TARGET', 'El destino no coincide.', 400);
      let destination;
      try { destination = this.destinationPolicy.authorize(targetJid || groupId || this.group.id, origin); }
      catch (error) { throw new ServiceError(error.code || 'DESTINATION_NOT_ENABLED', error.userMessage || 'Destino no habilitado.', 403); }
      const videoDestination = (destination.kind === 'private' && destination.id === this.destinationPolicy.ownerJid) ||
        (destination.kind === 'group' && (destination.id === this.group.id || this.destinationPolicy.allGroupsEnabled));
      if (typeof video !== 'boolean' || (video && (!live || !videoDestination))) throw new ServiceError('INVALID_VIDEO_POLICY', 'El ensayo de video solo admite Live con el propietario o Botsky Lab.', 400);
      receipt = sourceReceipt(receipt, origin);
      groupId = destination.kind === 'group' ? destination.id : null;
      maxSeconds = normalizeCallDuration(live, maxSeconds);
      if (typeof endAfterAudio !== 'boolean' || typeof durationFromAnswer !== 'boolean' || (endAfterAudio && !audioId)) throw new ServiceError('INVALID_AUDIO_POLICY', 'La política de audio no es válida.', 400);
      if (typeof live !== 'boolean' || (live && (audioId || endAfterAudio || !this.liveController))) throw new ServiceError('INVALID_LIVE_POLICY', 'La conversación en vivo no es compatible con esa solicitud.', 400);
      liveRequest = normalizeLiveRequest(live, liveRequest);
      if (live) durationFromAnswer = true;
      this.validateVolume(volume);
      if (scheduleWindow && (!Number.isSafeInteger(scheduleWindow.dispatchBy) || !this.scheduleCanDial({ scheduleWindow, maxSeconds }))) throw new ServiceError('SCHEDULE_WINDOW_CLOSED', 'La hora de ese encargo ya pasó o no cabe en el horario.', 409);
      if (audioId !== undefined) audioId = (await this.audioStore.get(audioId)).id;
      if (Object.hasOwn(this.journal.cancelledKeys, key)) throw new ServiceError('CANCELLED', 'Ese encargo fue cancelado.', 409);
      this.journal.prune(this.clock.now());
      const prior = this.journal.byKey(key);
      if (prior) {
        if (JSON.stringify(prior.sourceReceipt || null) !== JSON.stringify(receipt || null) || prior.maxSeconds !== maxSeconds || (prior.targetJid || prior.groupId) !== destination.id || (prior.origin?.chatId || null) !== (origin?.chatId || null) || (prior.origin?.requesterId || null) !== (origin?.requesterId || null) || (prior.audioId || null) !== (audioId || null) || !!prior.video !== video || !!prior.live !== live || (prior.liveRequest || null) !== (liveRequest || null) || !!prior.endAfterAudio !== endAfterAudio || !!prior.durationFromAnswer !== durationFromAnswer || (prior.requestedVolume ?? prior.volume ?? 0.7) !== volume) throw new ServiceError('KEY_CONFLICT', 'Esa clave ya se usó con otros parámetros.');
        return { replayed: true, call: this.publicCall(prior) };
      }
      if (destination.requireMembership) destination.name = (await this.resolveGroup({ origin, id: destination.id })).group.name;
      if (Object.hasOwn(this.journal.cancelledKeys, key)) throw new ServiceError('CANCELLED', 'Ese encargo fue cancelado.', 409);
      if (this.stopping) throw new ServiceError('STOPPING', 'El servicio se está deteniendo.', 503);
      if (!this.featureEnabled('outgoing')) throw new ServiceError('OUTGOING_DISABLED', 'Las llamadas salientes están desactivadas.', 503);
      if (live && !this.featureEnabled('live')) throw new ServiceError('LIVE_DISABLED', 'La conversación en vivo está desactivada.', 503);
      if (this.state !== 'ready') throw new ServiceError('NOT_READY', 'El navegador todavía no está listo.', 503);
      if (this.active || this.observed) throw new ServiceError('CALL_BUSY', 'Ya hay una llamada o un intento en curso.');
      if (this.journal.records.length >= 1000) throw new ServiceError('HISTORY_FULL', 'Se alcanzó el límite de solicitudes de las últimas 24 horas.', 429);
      const record = { id: randomUUID(), key, groupId, groupName: destination.name, targetJid: destination.id, destinationKind: destination.kind, maxSeconds,
        requestedAt: this.clock.now(), expiresAt: this.clock.now() + (durationFromAnswer ? 90 : maxSeconds) * 1000, state: 'starting', endAfterAudio, durationFromAnswer, live,
        ...(live && groupId ? { liveInterruption: true } : {}), ...(video ? { video: true } : {}) };
      if (liveRequest) record.liveRequest = liveRequest;
      if (receipt) record.sourceReceipt = receipt;
      if (scheduleWindow) record.scheduleWindow = { dispatchBy: scheduleWindow.dispatchBy, closeAt: scheduledWindowEnd(this.clock.now(), this.agenda.policy) };
      record.volume = volume;
      if (origin) record.origin = { chatId: origin.chatId, requesterId: origin.requesterId };
      record.requestedVolume = volume;
      if (audioId) record.audioId = audioId;
      this.active = record;
      this.journal.records.push(record);
      try { await this.journal.save(); }
      catch (error) { this.active = null; this.journal.records.pop(); throw error; }
      this.timer('deadline', (durationFromAnswer ? 90 : maxSeconds) * 1000, () => this.requestEnd(record, durationFromAnswer ? 'dial_timeout' : 'duration_limit'));
      void this.serial(() => this.dial(record)).catch(error => this.fatal(error));
      return { replayed: false, call: this.publicCall(record) };
    });
  }
  scheduleCanDial(record) {
    if (!record.scheduleWindow) return true;
    const now = this.clock.now();
    if (now > record.scheduleWindow.dispatchBy) return false;
    try { require('../policy/callScheduleTime').validateScheduledTime(now, this.agenda?.policy, { now: now - 1, maxSeconds: record.maxSeconds }); return true; }
    catch { return false; }
  }
  async dial(record) {
    if (this.stopping || this.active !== record || record.endRequested) return;
    try {
      if (Object.hasOwn(this.journal.cancelledKeys, record.key)) throw new ServiceError('CANCELLED', 'Ese encargo fue cancelado.', 409);
      if (this.policyCurrent && !this.policyCurrent()) { await this.finish(record, 'failed', 'POLICY_MISMATCH'); return; }
      if (!this.featureEnabled('outgoing') || (record.live && !this.featureEnabled('live'))) { await this.finish(record, 'failed', 'FEATURE_DISABLED'); return; }
      if (!this.scheduleCanDial(record)) { await this.finish(record, 'failed', 'SCHEDULE_WINDOW_CLOSED'); return; }
      if (record.live && !record.recovery?.redialUsed) await this.liveController.prepare(record);
      const destination = this.destinationPolicy.authorize(record.targetJid || record.groupId, record.origin);
      const result = await this.driver.dial(destination, {
        video: record.video === true,
        audioToken: record.audioToken || record.id,
        recoveryNativeId: record.recovery?.redialUsed ? record.recovery.originalNativeId : undefined,
        preparedAudio: record.audioId ? await this.audioStore.read(record.audioId) : undefined,
        cancelled: () => (this.policyCurrent && !this.policyCurrent()) || this.stopping || this.active !== record || !!record.endRequested || Object.hasOwn(this.journal.cancelledKeys, record.key) || (record.expiresAt !== null && this.clock.now() >= record.expiresAt) || !this.scheduleCanDial(record) || !this.featureEnabled('outgoing') || (record.live && !this.featureEnabled('live')),
      });
      if (this.active !== record || terminal(record.state)) return;
      record.nativeId = result.id; record.startedAt = this.clock.now();
      record.nativeRepresentation = { kind: result.isGroup ? 'group' : 'private', groupContextMatches: !!record.groupId && result.groupId === record.groupId };
      if (result.active === false) {
        if (result.state === 'FAILED' && !result.userEnded && await this.beginCallRecovery(record, 'native_FAILED')) return;
        await this.finish(record, 'ended', result.state === 'REJECTED' ? 'remote_rejected' : result.state === 'NOT_ANSWERED' ? 'not_answered' : 'native_end_during_dial');
        return;
      }
      const answered = result.connected && result.audience?.known && result.audience.connectedHumans > 0;
      record.state = record.endRequested ? 'ending' : answered ? 'connected' : 'dialing';
      if (answered && !record.endRequested) { record.connectedAt = this.clock.now(); this.answerDeadline(record); }
      else if (record.durationFromAnswer) {
        if (!record.recovery?.redialUsed) record.expiresAt = this.clock.now() + 45000;
        this.timer('deadline', Math.min(45000, record.expiresAt === null ? Infinity : record.expiresAt - this.clock.now()), () => this.requestEnd(record, 'answer_timeout'));
      }
      await this.journal.save();
      this.log('call_started', { id: record.id });
    } catch (error) {
      if (this.active !== record || terminal(record.state)) return;
      if (error.code === 'CANCELLED' && !record.endRequested && (!this.featureEnabled('outgoing') || (record.live && !this.featureEnabled('live')))) {
        await this.finish(record, 'failed', 'FEATURE_DISABLED');
      } else if (error.code === 'CANCELLED' && !record.endRequested && !this.scheduleCanDial(record)) {
        await this.finish(record, 'failed', 'SCHEDULE_WINDOW_CLOSED');
      } else if (error.code === 'CANCELLED') {
        await this.finish(record, 'ended', record.endRequested || 'cancelled_before_dial');
      } else {
        await this.finish(record, error.dispatched ? 'interrupted' : 'failed', error.code || 'DIAL_FAILED');
        if (error.dispatched && error.code !== 'CALL_CHANGED') {
          this.state = 'recovering';
          await this.driver.close();
          this.failureCount++; this.scheduleRecovery();
        }
      }
    }
  }
  async poll() {
    if (this.state !== 'ready' || this.stopping) return;
    const snapshot = await this.driver.snapshot();
    this.lastSuccessfulPollAt = this.clock.now();
    this.audioRuntime = snapshot.audio || null;
    this.privateCallCapabilities = snapshot.privateCapabilities || null;
    this.observed = snapshot.active ? snapshot : null;
    if (snapshot.active && !snapshot.outgoing && [3, 'INCOMING_RING'].includes(snapshot.state)) {
      this.incomingObservation = { state: snapshot.state, isGroup: !!snapshot.isGroup, isVideo: !!snapshot.isVideo,
        phoneAvailable: !!(snapshot.peerPhone || snapshot.peerJid?.endsWith('@s.whatsapp.net')),
        allowed: !!this.incomingPolicy?.allows(snapshot) && this.featureEnabled('incoming') && this.featureEnabled('live'), seenAt: this.clock.now() };
    }
    const record = this.active;
    if (!record) {
      if (this.liveController && this.incomingPolicy?.allows(snapshot)) await this.receiveIncoming(snapshot);
      return;
    }
    if (!record.nativeId) return;
    if (record.state === 'recovering' && record.recovery?.phase === 'waiting') return;
    if (!record.endRequested && !snapshot.userEnded && snapshot.id === record.nativeId && ['FAILED', 'CONNECTION_LOST', 9, 'Rejoining'].includes(snapshot.state)) {
      if (await this.beginCallRecovery(record, 'native_' + snapshot.state)) return;
      if (record.recovery?.attempts) { await this.failCallRecovery(record, 'recovery_exhausted'); return; }
    }
    if (snapshot.active && (snapshot.id !== record.nativeId || !!snapshot.isVideo !== !!record.video)) {
      await this.finish(record, 'interrupted', 'different_call_observed');
    } else if (!snapshot.active) {
      await this.finish(record, 'ended', record.endRequested || 'remote_or_native_end');
    } else if (snapshot.connected && !record.connectedAt && snapshot.audience?.known && snapshot.audience.connectedHumans > 0) {
      record.state = 'connected'; record.connectedAt = this.clock.now();
      this.answerDeadline(record);
      if (record.recovery?.redialUsed) record.recovery.phase = 'recovered';
      await this.journal.save(); this.log('call_connected', { id: record.id });
    }
    if (record.recovery?.phase === 'redialing' && snapshot.active && snapshot.id === record.nativeId && snapshot.connected && snapshot.audience?.known && snapshot.audience.connectedHumans > 0) {
      record.state = 'connected'; record.recovery.phase = 'recovered'; this.answerDeadline(record); await this.journal.save();
    }
    if (this.active === record && snapshot.active && snapshot.id === record.nativeId) {
      const representation = { kind: snapshot.isGroup ? 'group' : 'private', groupContextMatches: !!record.groupId && snapshot.groupId === record.groupId };
      if (record.nativeRepresentation?.kind !== representation.kind || record.nativeRepresentation?.groupContextMatches !== representation.groupContextMatches) {
        record.nativeRepresentation = representation;
        await this.journal.save();
      }
    }
    if (this.active === record && snapshot.active && snapshot.id === record.nativeId && record.connectedAt && !record.endRequested) {
      await this.observeAudience(record, snapshot);
    }
    if (this.active === record && record.connectedAt && !record.endRequested && snapshot.active && snapshot.id === record.nativeId && snapshot.connected) {
      if (record.live) {
        if (record.liveStarted && (record.audiencePaused || this.liveController.active?.suspended) && this.canStartForAudience(record)) {
          await this.liveStep(record, 'resume');
          if (this.active !== record || record.endRequested) return;
          record.audiencePaused = false;
        }
        if (!record.liveStarted && this.canStartForAudience(record)) {
          record.liveStarted = true;
          try {
            if (record.recovery?.redialUsed) await this.liveStep(record, 'resume');
            else await this.liveStep(record, 'start');
          }
          catch (error) {
            if (error.callFailureSource === 'browser') throw error;
            record.liveError = { code: error.code || 'LIVE_FAILED' };
            void this.requestEnd(record, 'live_failed').catch(error => this.fatal(error));
          }
        }
        return;
      }
      const playback = record.playback;
      if (playback?.state === 'paused' && this.canStartForAudience(record)) {
        await this.driver.resumeAudio(record.nativeId, playback.id, playback.confirmedPositionSeconds || 0);
        if (this.active !== record || record.endRequested) return;
        playback.state = 'playing';
      }
      const position = snapshot.audio?.playback;
      if (playback?.state === 'playing' && position?.id === playback.id && position.state === 'playing' && Number.isFinite(position.positionSeconds) && position.positionSeconds >= (playback.confirmedPositionSeconds || 0) && position.positionSeconds <= playback.durationSeconds && (!record.groupId || this.canStartForAudience(record))) {
        playback.confirmedPositionSeconds = position.positionSeconds;
        if (!playback.checkpointAt || this.clock.now() - playback.checkpointAt >= 2000) { playback.checkpointAt = this.clock.now(); await this.journal.save(); }
      }
      if (playback?.state === 'playing' && snapshot.audio?.playback?.id === playback.id && snapshot.audio.playback.state !== 'playing') {
        Object.assign(playback, { state: snapshot.audio.playback.state, finishedAt: this.clock.now() });
        await this.journal.save();
        if (record.endAfterAudio && playback.state === 'ended') {
          void this.requestEnd(record, 'audio_completed').catch(error => this.fatal(error));
          return;
        }
      }
      if (record.audioId && !record.autoplayAttempted && !record.endRequested && this.canStartForAudience(record)) {
        record.autoplayAttempted = true;
        try { await this.performPlayback(record, { key: `autoplay:${record.id}${record.recovery?.redialUsed ? ':recovery:1' : ''}`, audioId: record.audioId, volume: record.volume, offsetSeconds: record.recovery?.redialUsed ? record.recovery.resume?.offsetSeconds || 0 : 0 }); }
        catch (error) {
          record.audioError = { code: error.code || 'AUDIO_FAILED' }; await this.journal.save();
          if (record.endAfterAudio) void this.requestEnd(record, 'audio_failed').catch(error => this.fatal(error));
        }
      }
    }
  }
  canStartForAudience(record) {
    return !record.groupId || (record.audience?.known && record.audience.connectedHumans > 0);
  }
  async observeAudience(record, snapshot) {
    if (!record.groupId) {
      if (snapshot.audience?.known && snapshot.audience.connectedHumans === 0) {
        void this.requestEnd(record, 'remote_left').catch(error => this.fatal(error));
      }
      return;
    }
    const now = this.clock.now(), prior = record.audience;
    const sample = snapshot.audience;
    const known = sample?.known === true && Number.isSafeInteger(sample.connectedHumans) && sample.connectedHumans >= 0;
    const connectedHumans = known ? sample.connectedHumans : null;
    const next = {
      known, connectedHumans, source: sample?.source || 'unavailable', observedAt: now,
      emptySince: known && connectedHumans === 0 ? prior?.emptySince ?? now : null,
      unavailableSince: !known ? prior?.unavailableSince ?? now : null,
    };
    record.audience = next;
    if (!prior || prior.known !== known || prior.connectedHumans !== connectedHumans || prior.source !== next.source) {
      await this.journal.save();
      this.log('call_audience', { id: record.id, known, connectedHumans, source: next.source });
    }
    let reason;
    if (next.emptySince !== null && now - next.emptySince >= this.audiencePolicy.emptyGraceMs) reason = 'audience_empty';
    if (next.unavailableSince !== null && now - next.unavailableSince >= this.audiencePolicy.unavailableGraceMs) reason = 'audience_unavailable';
    // Keep the call during the grace period, but do not consume a recado or
    // feed Live with an empty/unverified audience. Rejoin resumes the same work.
    if (!reason && (!known || connectedHumans === 0)) {
      if (record.live && record.liveStarted && !record.audiencePaused && !this.liveController.active?.suspended) {
        await this.liveStep(record, 'suspend');
        record.audiencePaused = true;
      } else if (!record.live && record.playback?.state === 'playing') {
        const playback = record.playback, sample = snapshot.audio?.playback;
        const offset = sample?.id === playback.id && Number.isFinite(sample.positionSeconds) && sample.positionSeconds >= (playback.confirmedPositionSeconds || 0) && sample.positionSeconds <= playback.durationSeconds
          ? sample.positionSeconds : playback.confirmedPositionSeconds || playback.offsetSeconds || 0;
        if (offset >= playback.durationSeconds) {
          Object.assign(playback, { state: 'ended', confirmedPositionSeconds: offset, finishedAt: now });
          if (record.endAfterAudio) void this.requestEnd(record, 'audio_completed').catch(error => this.fatal(error));
        } else {
          await this.driver.pauseAudio(record.nativeId, playback.id, offset);
          Object.assign(playback, { state: 'paused', confirmedPositionSeconds: offset });
        }
      }
    }
    // poll() already owns the browser queue. Do not await a second serial task.
    if (reason) void this.requestEnd(record, reason).catch(error => this.fatal(error));
  }
  async receiveIncoming(snapshot) {
    if (this.stopping || this.active || !this.featureEnabled('incoming') || !this.featureEnabled('live') || !this.incomingPolicy?.allows(snapshot)) return;
    const key = 'incoming:' + createHash('sha256').update(String(snapshot.id)).digest('hex');
    this.journal.prune(this.clock.now());
    if (this.journal.byKey(key) || this.journal.records.length >= 1000) return;
    const video = snapshot.isVideo === true, answerTimeoutMs = video ? 45000 : 30000;
    const record = { id: randomUUID(), key, nativeId: snapshot.id, incomingPeer: snapshot.peerJid,
      targetJid: canonicalPhoneJid(snapshot.peerPhone || snapshot.peerJid), destinationKind: 'private',
      groupId: null, groupName: 'Llamada privada entrante', direction: 'incoming', state: 'starting',
      requestedAt: this.clock.now(), expiresAt: this.clock.now() + answerTimeoutMs,
      maxSeconds: null, durationFromAnswer: true, endAfterAudio: false, live: true,
      ...(video ? { video: true } : {}),
      volume: 0.7, requestedVolume: 0.7 };
    this.active = record; this.journal.records.push(record);
    try { await this.journal.save(); }
    catch {
      this.active = null; this.journal.records.pop();
      this.log('incoming_reservation_failed', { code: 'INCOMING_STORAGE_FAILED' }); return;
    }
    this.timer('deadline', answerTimeoutMs, () => this.requestEnd(record, 'incoming_answer_timeout'));
    try {
      await this.liveController.prepare(record);
      const result = await this.driver.answer(snapshot, { audioToken: record.id,
        cancelled: () => this.stopping || this.active !== record || !!record.endRequested || (record.expiresAt !== null && this.clock.now() >= record.expiresAt) });
      if (this.active !== record || terminal(record.state)) return;
      record.incomingAccepted = true; record.startedAt = this.clock.now();
      record.state = record.endRequested ? 'ending' : result.connected ? 'connected' : 'connecting';
      if (result.connected && !record.endRequested) { record.connectedAt = this.clock.now(); this.answerDeadline(record); }
      await this.journal.save(); this.log('incoming_answered', { id: record.id });
    } catch (error) {
      if (this.active !== record || terminal(record.state)) return;
      if (error.dispatched && error.code !== 'CALL_CHANGED') {
        record.liveError = { code: error.code || 'INCOMING_ACCEPT_FAILED' };
        void this.requestEnd(record, 'incoming_accept_failed').catch(error => this.fatal(error));
      } else await this.finish(record, error.code === 'CALL_CHANGED' || error.code === 'CANCELLED' ? 'ended' : 'failed', error.code || 'INCOMING_FAILED');
    }
  }
  answerDeadline(record) {
    if (!record.durationFromAnswer) return;
    this.clearTimer('deadline');
    if (!(record.recovery?.redialUsed && record.recovery.originalConnectedAt)) {
      const requested = record.maxSeconds === null ? null : record.connectedAt + record.maxSeconds * 1000;
      const closeAt = record.scheduleWindow?.closeAt;
      record.expiresAt = closeAt ? Math.min(requested ?? Infinity, closeAt) : requested;
      record.deadlineReason = closeAt && record.expiresAt === closeAt ? 'schedule_window_closed' : 'duration_limit';
    }
    if (record.expiresAt !== null) this.timer('deadline', Math.max(0, record.expiresAt - this.clock.now()),
      () => this.requestEnd(record, record.deadlineReason || 'duration_limit'));
  }
  validateVolume(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) throw new ServiceError('INVALID_VOLUME', 'El volumen debe estar entre 0 y 1.', 400);
  }
  requireConnected(record) {
    if (!record || record !== this.active || record.state !== 'connected' || record.endRequested) throw new ServiceError('CALL_NOT_CONNECTED', 'Se requiere una llamada propia conectada.');
  }
  async performPlayback(record, { key, audioId, volume, offsetSeconds = 0 }) {
    if (record.live) throw new ServiceError('LIVE_AUDIO_EXCLUSIVE', 'La conversación en vivo está usando el audio de la llamada.');
    if (typeof key !== 'string' || !/^[A-Za-z0-9._:-]{8,128}$/.test(key)) throw new ServiceError('INVALID_KEY', 'Usa una clave de idempotencia para reproducir el audio.', 400);
    const { asset, data } = await this.audioStore.read(audioId);
    if (Object.hasOwn(this.journal.cancelledKeys, key)) throw new ServiceError('CANCELLED', 'Ese audio fue cancelado.', 409);
    if (!Number.isFinite(offsetSeconds) || offsetSeconds < 0 || offsetSeconds >= asset.durationSeconds) throw new ServiceError('INVALID_OFFSET', 'Posición de audio no válida.', 400);
    record.audioRequests ||= [];
    const prior = record.audioRequests.find(request => request.key === key);
    if (volume === undefined) volume = prior?.playback.volumeRequested ?? record.volume;
    this.validateVolume(volume);
    if (prior) {
      if (prior.playback.audioId !== asset.id || prior.playback.volumeRequested !== volume || (prior.playback.offsetSeconds || 0) !== offsetSeconds) throw new ServiceError('KEY_CONFLICT', 'Esa clave ya se usó con otro audio o volumen.');
      return { replayed: true, playback: structuredClone(prior.playback) };
    }
    this.requireConnected(record);
    if (record.playback && ['starting', 'playing'].includes(record.playback.state)) throw new ServiceError('AUDIO_BUSY', 'Detén el audio actual antes de reproducir otro.');
    if (record.audioRequests.length >= 100) throw new ServiceError('AUDIO_LIMIT', 'Se alcanzó el límite de reproducciones de esta llamada.', 429);
    const playback = { id: randomUUID(), audioId: asset.id, offsetSeconds, confirmedPositionSeconds: offsetSeconds, state: 'starting', durationSeconds: asset.durationSeconds, volume, volumeRequested: volume };
    const previousPlayback = record.playback;
    record.playback = playback; record.audioRequests.push({ key, playback });
    try { await this.journal.save(); }
    catch (error) { record.playback = previousPlayback; record.audioRequests.pop(); throw error; }
    const nativeId = record.nativeId;
    try {
      this.requireConnected(record);
      if (Object.hasOwn(this.journal.cancelledKeys, key)) throw new ServiceError('CANCELLED', 'Ese audio fue cancelado.', 409);
      await this.driver.playAudio(nativeId, playback.id, data, volume, asset.id, offsetSeconds);
      if (this.active !== record || record.nativeId !== nativeId || record.endRequested || terminal(record.state) || record.playback !== playback || record.state !== 'connected') throw new ServiceError('AUDIO_CALL_CHANGED', 'El resultado de audio llegó después de cerrar o cambiar la llamada.');
      Object.assign(playback, { state: 'playing', startedAt: this.clock.now() });
    } catch (error) {
      Object.assign(playback, { state: 'interrupted', finishedAt: this.clock.now(), error: error.code || 'AUDIO_FAILED' });
      await this.driver.stopAudio(nativeId, playback.id).catch(() => {});
      await this.journal.save(); throw error;
    }
    await this.journal.save();
    return { replayed: false, playback: structuredClone(playback) };
  }
  async avatarCommand({ callId, action, name, duration, signal } = {}) {
    try {
      if (!Object.hasOwn(AVATAR_NAMES, action) || typeof name !== 'string' || !AVATAR_NAMES[action].has(name.toLowerCase())) throw new ServiceError('INVALID_AVATAR_CONTROL', 'Control de avatar no válido.', 400);
      name = name.toLowerCase();
      const timed = action === 'expression' || action === 'gesture' || action === 'blush';
      if ((timed && duration !== undefined && (!Number.isFinite(duration) || duration < 1 || duration > 15)) || (!timed && duration !== undefined)) throw new ServiceError('INVALID_AVATAR_DURATION', 'La duración debe estar entre 1 y 15 segundos y solo aplica a expresión, gesto o rubor.', 400);
      return await this.serial(async () => {
        signal?.throwIfAborted();
        const record = this.clipCall(callId);
        const controlId = randomUUID(), nativeId = record.nativeId;
        const cancel = () => {
          if (this.active === record && record.nativeId === nativeId && !record.endRequested) void Promise.resolve(this.driver.cancelAvatarControl?.(nativeId, controlId)).catch(() => {});
        };
        signal?.addEventListener('abort', cancel, { once: true });
        let avatar;
        try { avatar = await this.driver.avatarControl(nativeId, { action, name, controlId, ...(duration !== undefined ? { duration } : {}) }); }
        finally { signal?.removeEventListener('abort', cancel); }
        signal?.throwIfAborted();
        if (this.clipCall(record.id) !== record) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada.', 409);
        if (action === 'expression' && (!avatar?.appliedExpression?.applied || avatar.appliedExpression.requested !== name?.toLowerCase())) throw new ServiceError('AVATAR_EXPRESSION_UNCONFIRMED', 'No se confirmó la expresión.', 409);
        if (action === 'gesture' && (!avatar?.appliedGesture?.applied || avatar.appliedGesture.requested !== name)) throw new ServiceError('AVATAR_GESTURE_UNCONFIRMED', 'No se confirmó el gesto en un frame.', 409);
        if (action === 'blush' && (!avatar?.appliedBlush?.applied || avatar.appliedBlush.requested !== name)) throw new ServiceError('AVATAR_BLUSH_UNCONFIRMED', 'No se confirmó el rubor en un frame.', 409);
        const deferred = action === 'background' && avatar?.deferred === true;
        const label = { background: 'Fondo actualizado.', expression: 'Expresión actualizada.', gesture: 'Gesto aplicado.', blush: 'Rubor aplicado.' }[action];
        return { success: true, avatar, ...(deferred ? { deferred: true } : {}), message: deferred ? 'Fondo pedido; lo aplicaré cuando termine o detengas el clip.' : label };
      });
    } catch { return { success: false, message: 'No pude cambiar el avatar. Necesito una videollamada conectada y una opción disponible.' }; }
  }
  clipCall(callId) {
    const record = this.active;
    if (!record || (callId && record.id !== callId) || record.endRequested || record.state !== 'connected' || !record.video || !record.live) throw new ServiceError('CLIP_CALL_REQUIRED', 'Necesito una videollamada Live conectada para reproducir clips.', 409);
    return record;
  }
  async pendingClipOperation(record, action, signal) {
    // A cancelled browser operation may resolve much later. Drain it before
    // starting another clip on this call so its late stop cannot hit a newer clip.
    const prior = this.clipOperationDrain;
    if (prior?.record === record) {
      if (!signal) await prior.promise;
      else {
        signal.throwIfAborted();
        await new Promise((resolve, reject) => {
          const cleanup = () => signal.removeEventListener('abort', onAbort);
          const onAbort = () => { cleanup(); reject(new ServiceError('CANCELLED', 'La operación del clip fue cancelada.', 409)); };
          signal.addEventListener('abort', onAbort, { once: true });
          prior.promise.then(() => { cleanup(); resolve(); }, error => { cleanup(); reject(error); });
          if (signal.aborted) onAbort();
        });
      }
    }
    signal?.throwIfAborted();
    if (this.active !== record || record.endRequested || record.state !== 'connected') throw new ServiceError('CALL_CHANGED', 'Cambió la llamada.', 409);
    const nativeId = record.nativeId;
    const pending = { record, nativeId };
    this.pendingClip = pending;
    let aborted = false, rejectAbort;
    let releaseDrain;
    const drain = new Promise(resolve => { releaseDrain = resolve; });
    const drainState = { record, nativeId, promise: drain };
    this.clipOperationDrain = drainState;
    const stopSameCall = () => {
      if (this.active !== record || record.nativeId !== nativeId || record.endRequested || record.state !== 'connected') return Promise.resolve();
      return Promise.resolve().then(() => this.driver.controlClip(nativeId, 'stop')).catch(() => {});
    };
    const abortError = () => new ServiceError('CANCELLED', 'La operación del clip fue cancelada.', 409);
    const abortedResult = new Promise((_, reject) => { rejectAbort = reject; });
    const onAbort = () => {
      if (aborted) return;
      aborted = true;
      if (this.pendingClip === pending) this.pendingClip = null;
      void stopSameCall();
      rejectAbort(abortError());
    };
    const operation = Promise.resolve().then(() => {
      if (aborted) throw abortError();
      return action(nativeId);
    }).then(async value => {
      if (aborted) { await stopSameCall(); throw abortError(); }
      return value;
    }, async error => {
      if (aborted) { await stopSameCall(); throw abortError(); }
      throw error;
    });
    operation.finally(() => {
      if (this.clipOperationDrain === drainState) this.clipOperationDrain = null;
      releaseDrain();
    }).catch(() => {});
    if (signal) signal.addEventListener('abort', onAbort, { once: true });
    if (signal?.aborted) onAbort();
    try { return await Promise.race([operation, abortedResult]); }
    finally {
      signal?.removeEventListener('abort', onAbort);
      if (this.pendingClip === pending) this.pendingClip = null;
    }
  }
  async playClip({ callId, clipId, volume = 0.5, key, signal } = {}) {
    signal?.throwIfAborted();
    if (typeof key !== 'string' || !/^[A-Za-z0-9._:-]{8,128}$/.test(key)) throw new ServiceError('INVALID_KEY', 'Usa una clave de reproducción válida.', 400);
    this.validateVolume(volume);
    return this.command(() => this.serial(async () => {
      signal?.throwIfAborted();
      const record = this.clipCall(callId);
      if (!this.clipStore) throw new ServiceError('NOT_READY', 'El catálogo no está listo.', 503);
      const prior = (record.clipRequests || []).find(request => request.key === key);
      if (prior) {
        if (prior.clipId !== clipId || prior.volume !== volume) throw new ServiceError('KEY_CONFLICT', 'La clave ya corresponde a otro clip o volumen.', 409);
        if (prior.state !== 'started') throw new ServiceError('CLIP_ATTEMPT_FAILED', 'Ese intento no confirmó reproducción. Usa una clave nueva para reintentarlo.', 409);
        return { replayed: true, callId: record.id, clip: prior.clip || null, state: prior.state };
      }
      if ((record.clipRequests || []).length >= 100) throw new ServiceError('CLIP_HISTORY_FULL', 'Esta llamada ya alcanzó 100 reproducciones.', 429);
      const { asset, data } = await this.clipStore.read(clipId);
      signal?.throwIfAborted();
      if (this.clipCall(record.id) !== record) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada.', 409);
      const request = { key, clipId, volume, id: randomUUID(), state: 'starting' };
      (record.clipRequests ||= []).push(request); await this.journal.save();
      const nativeId = record.nativeId;
      try {
        signal?.throwIfAborted();
        if (this.clipCall(record.id) !== record) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada.', 409);
        const clip = await this.pendingClipOperation(record, id => this.driver.playClip(id, request.id, asset, data, volume), signal);
        signal?.throwIfAborted();
        if (this.clipCall(record.id) !== record) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada.', 409);
        request.state = 'started'; request.clip = clip; record.clipVolume = volume; record.clip = { id: request.id, clipId, label: asset.label };
        await this.journal.save();
        return { replayed: false, callId: record.id, clip };
      } catch (error) {
        request.state = 'failed'; await this.journal.save();
        if (error.code !== 'CANCELLED' && this.active === record && record.nativeId === nativeId && !record.endRequested) await this.driver.controlClip(nativeId, 'stop').catch(() => {});
        throw new ServiceError(error.code || 'CLIP_PLAY_FAILED', 'No pude reproducir el clip en esta llamada.', 409);
      }
    }));
  }
  async controlClip({ callId, action, volume, signal } = {}) {
    if (!['pause', 'resume', 'stop', 'volume'].includes(action)) throw new ServiceError('INVALID_CLIP_ACTION', 'Usa pause, resume, stop o volume.', 400);
    if (action === 'volume') this.validateVolume(volume);
    const apply = async () => {
      signal?.throwIfAborted();
      const record = this.clipCall(callId);
      try {
        const clip = action === 'resume'
          ? await this.pendingClipOperation(record, id => this.driver.controlClip(id, action, volume), signal)
          : await this.driver.controlClip(record.nativeId, action, volume);
        if (this.clipCall(record.id) !== record) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada.', 409);
        if (action === 'volume') record.clipVolume = clip.volume;
        return { callId: record.id, clip };
      }
      catch (error) { throw new ServiceError(error.code || 'CLIP_CONTROL_FAILED', 'No pude aplicar ese control al clip.', 409); }
    };
    // A paused/resuming play() may wait on media indefinitely. Pause/stop must
    // reach that same call while the normal browser queue is awaiting it.
    if (['pause', 'stop'].includes(action) && (this.pendingClip?.record === this.active || this.clipOperationDrain?.record === this.active)) return apply();
    return this.serial(apply);
  }
  async playAudio({ callId, ...request }) {
    return this.command(() => this.serial(async () => {
      const record = callId ? this.journal.byId(callId) : this.active;
      if (!record) throw new ServiceError('CALL_NOT_FOUND', 'No se encontró una llamada para el audio.', 404);
      return { callId: record.id, ...await this.performPlayback(record, request) };
    }));
  }
  async stopAudio(callId) {
    return this.command(() => this.serial(async () => {
      const record = callId ? this.journal.byId(callId) : this.active;
      if (record?.live) {
        this.requireConnected(record);
        await this.liveController.silence(record);
        return { callId: record.id, live: true, stopped: true };
      }
      if (!record || terminal(record.state) || !record.playback || !['starting', 'playing'].includes(record.playback.state)) return { alreadyStopped: true };
      this.requireConnected(record);
      await this.driver.stopAudio(record.nativeId);
      Object.assign(record.playback, { state: 'stopped', finishedAt: this.clock.now() });
      await this.journal.save(); return { alreadyStopped: false, playback: structuredClone(record.playback) };
    }));
  }
  async setVolume({ callId, volume }) {
    this.validateVolume(volume);
    return this.command(() => this.serial(async () => {
      const record = callId ? this.journal.byId(callId) : this.active;
      this.requireConnected(record);
      await this.driver.volume(record.nativeId, volume);
      record.volume = volume;
      if (record.playback) record.playback.volume = volume;
      await this.journal.save(); return { volume };
    }));
  }
  async cancelKey(key) {
    if (typeof key !== 'string' || !/^[A-Za-z0-9._:-]{8,128}$/.test(key)) throw new ServiceError('INVALID_KEY', 'Clave no válida.', 400);
    // Set synchronously, outside command/browser queues. Even an offer whose
    // HTTP response was lost cannot outrun cancellation and appear later.
    Object.defineProperty(this.journal.cancelledKeys, key, { value: this.clock.now(), enumerable: true, configurable: true, writable: true });
    const cancellation = this.agenda?.cancelByKey(key);
    const record = this.journal.byKey(key);
    const ending = record && this.active === record && !terminal(record.state)
      ? this.requestEnd(record, 'cancelled') : null;
    await this.journal.save();
    await cancellation;
    if (ending) await ending;
    if (!record && !this.active?.audioRequests?.some(request => request.key === key)) return { cancelled: true };
    // Playback has its own idempotency key. Never stop an unrelated successor.
    await this.serial(async () => {
      const call = this.active;
      const playback = call?.audioRequests?.find(request => request.key === key)?.playback;
      if (!playback || call.playback?.id !== playback.id || !['starting', 'playing'].includes(playback.state)) return;
      await this.driver.stopAudio(call.nativeId);
      Object.assign(playback, { state: 'stopped', finishedAt: this.clock.now() });
      await this.journal.save();
    });
    return { cancelled: true };
  }
  async endCall(id) {
    const record = id ? this.journal.byId(id) : this.active;
    if (id && !record) throw new ServiceError('CALL_NOT_FOUND', 'No se encontró esa llamada.', 404);
    if (!record || terminal(record.state)) return { alreadyEnded: true, call: this.publicCall(record) };
    await this.requestEnd(record, 'requested');
    return { alreadyEnded: terminal(record.state), call: this.publicCall(record) };
  }
  captureLiveUsage(record) {
    // Telemetry is optional and must never prevent closing a call.
    try {
      const value = this.liveController?.status?.();
      if (value?.callId !== record.id) return;
      const count = n => Number.isFinite(n) && n >= 0 ? n : 0;
      record.usage = { inputAudioSeconds: count(value.inputSeconds), modelOutputAudioSeconds: count(value.outputSeconds),
        bridgeAcceptedAudioSeconds: count(value.bridgeAcceptedSeconds), firstAudioLatencyMs: Number.isFinite(value.firstAudioLatencyMs) && value.firstAudioLatencyMs >= 0 ? value.firstAudioLatencyMs : null,
        completedInputTurns: count(value.completedInputTurns), outputTurns: count(value.outputTurns), connectionRenewals: count(value.renewals) };
    } catch { this.log('live_usage_unavailable', { id: record.id }); }
  }
  async requestEnd(record, reason) {
    if (this.active !== record || terminal(record.state)) return;
    this.clearTimer('call-recovery');
    record.endRequested ||= reason;
    record.state = 'ending';
    // Independent of the browser command queue: a hung evaluate must not defeat
    // the duration limit. Closing the browser cannot start another call.
    if (!this.timers.has('emergency')) this.timer('emergency', 5000, async () => {
      if (this.active !== record) return;
      this.state = 'recovering';
      await this.driver.abort();
      await this.finish(record, 'interrupted', 'forced_browser_close');
      this.failureCount++; this.scheduleRecovery();
    });
    this.captureLiveUsage(record);
    await this.liveController?.stop(record.id);
    await this.journal.save();
    return this.serial(async () => {
      if (this.active !== record || terminal(record.state)) return;
      try {
        if (record.nativeId) await this.driver.end(record.nativeId, { incoming: record.direction === 'incoming' });
        await this.finish(record, 'ended', record.endRequested || reason);
      } catch (error) {
        // Hangup already completed; a cleanup/storage failure is retried by
        // finish, not treated as a reason to close the browser again.
        if (terminal(record.state)) throw error;
        // Never terminate an unrelated incoming or manually initiated call.
        if (error.code === 'CALL_CHANGED') {
          await this.finish(record, 'interrupted', 'different_call_observed');
        } else {
          this.state = 'recovering'; await this.driver.close();
          await this.finish(record, 'interrupted', 'hangup_unconfirmed');
          this.failureCount++; this.scheduleRecovery();
        }
      }
    });
  }
  scheduleCleanupRetry(record) {
    if (this.stopping || this.active !== record) return;
    this.timer('cleanup-retry', 1000, async () => {
      if (this.stopping || this.active !== record) return;
      try { await this.serial(() => this.finish(record, record.state, record.reason)); }
      catch { /* finish has scheduled the next cleanup attempt; do not flood logs. */ }
    });
  }
  async finish(record, state, reason) {
    if (this.finishing.has(record.id)) return this.finishing.get(record.id);
    // Terminal state alone does not prove cleanup and its receipt were completed.
    if (terminal(record.state) && this.active !== record) return;
    const work = this.finishOwned(record, terminal(record.state) ? record.state : state, terminal(record.state) ? record.reason : reason);
    this.finishing.set(record.id, work);
    try { return await work; }
    catch (error) { this.cleanupPending.add(record); this.scheduleCleanupRetry(record); throw error; }
    finally { if (this.finishing.get(record.id) === work) this.finishing.delete(record.id); }
  }
  async finishOwned(record, state, reason) {
    if (record.recovery && !['recovered', 'failed'].includes(record.recovery.phase)) Object.assign(record.recovery, { phase: 'failed', failure: reason });
    Object.assign(record, { state, reason, endedAt: record.endedAt ?? this.clock.now() });
    if (record.playback && ['starting', 'playing', 'paused'].includes(record.playback.state)) Object.assign(record.playback, { state: 'stopped', finishedAt: this.clock.now() });
    if (this.active === record) {
      this.clearTimer('deadline'); this.clearTimer('emergency'); this.clearTimer('call-recovery');
    }
    this.captureLiveUsage(record);
    if (!['released', 'browser_closed'].includes(record.cleanup?.state)) {
      await this.liveController?.stop(record.id);
      const cleanup = await this.driver.disarmAudio?.(record.audioToken || record.id);
      if (cleanup?.released === false) {
        const current = await this.driver.snapshot().catch(() => null);
        if (current?.active && current.id !== record.nativeId) {
          this.state = 'error'; this.lastError = { code: 'AUDIO_CLEANUP_UNCONFIRMED', message: 'No se pudo confirmar la limpieza sin afectar otra llamada.' };
          record.cleanup = { state: 'unconfirmed', reason: 'different_call_observed' };
          queueFailureNotice(record, this.clock.now()); await this.journal.save();
          return; // Keep the reservation. Never close a known unrelated call.
        }
        this.state = 'recovering'; await this.driver.close();
        record.cleanup = { state: 'browser_closed' };
      } else record.cleanup = { state: 'released' };
    }
    queueFailureNotice(record, this.clock.now());
    await this.journal.save();
    const retryingCleanup = this.cleanupPending.has(record); this.cleanupPending.delete(record);
    if (this.active === record) {
      this.active = null; this.clearTimer('cleanup-retry');
      if (this.observed?.id === record.nativeId) this.observed = null;
    }
    this.log('call_finished', { id: record.id, state, reason });
    if (this.state === 'recovering_call' || record.cleanup.state === 'browser_closed' || (retryingCleanup && (this.state === 'recovering' || (this.state === 'error' && this.lastError?.code === 'SERVICE_ERROR')))) { this.state = 'recovering'; this.failureCount++; this.scheduleRecovery(); }
  }
  async claimFailureNotices() {
    return this.command(async () => {
      const now = this.clock.now(), notices = []; let changed = false;
      for (const record of this.journal.records) {
        const notice = record.failureNotice;
        if (!terminal(record.state) || !record.sourceReceipt || !notice || !['pending', 'claimed'].includes(notice.state) || notice.availableAt > now || this.finishing.has(record.id)) continue;
        if (notice.attempts >= 3) { notice.state = 'abandoned'; changed = true; continue; }
        Object.assign(notice, { state: 'claimed', lease: randomUUID(), attempts: notice.attempts + 1, availableAt: now + 90000 });
        notices.push({ callId: record.id, lease: notice.lease, requesterId: record.origin?.requesterId, ...structuredClone(record.sourceReceipt) });
        if (notices.length === 1) break; // One delivery per lease; slow Evolution calls cannot expire a waiting batch.
      }
      if (notices.length || changed) await this.journal.save();
      return { notices };
    });
  }
  async beginFailureNotice({ callId, lease }) {
    return this.command(async () => {
      const notice = this.journal.byId(callId)?.failureNotice;
      if (!notice || notice.state !== 'claimed' || notice.lease !== lease || notice.availableAt <= this.clock.now()) return { begun: false };
      Object.assign(notice, { state: 'sending', availableAt: this.clock.now() });
      await this.journal.save();
      return { begun: true };
    });
  }
  async ackFailureNotice({ callId, lease, outcome, delivered }) {
    return this.command(async () => {
      if (outcome === undefined && typeof delivered === 'boolean') outcome = delivered ? 'accepted' : 'failed';
      if (!['accepted', 'failed', 'uncertain', 'rejected'].includes(outcome)) throw new ServiceError('INVALID_NOTICE', 'Acuse no válido.', 400);
      const notice = this.journal.byId(callId)?.failureNotice;
      if (!notice || notice.state !== 'sending' || notice.lease !== lease) throw new ServiceError('NOTICE_LEASE_CHANGED', 'El aviso ya cambió.', 409);
      const now = this.clock.now();
      if (outcome === 'accepted') Object.assign(notice, { state: 'sent', availableAt: now });
      else if (outcome === 'uncertain') Object.assign(notice, { state: 'uncertain', availableAt: now });
      else if (outcome === 'rejected' || notice.attempts >= 3) Object.assign(notice, { state: 'abandoned', availableAt: now });
      else Object.assign(notice, { state: 'pending', availableAt: now + 5000 * 2 ** notice.attempts });
      await this.journal.save();
      return { acknowledged: true, state: notice.state };
    });
  }
  async restartBrowser() {
    return this.command(async () => {
      if (this.active || this.observed) throw new ServiceError('CALL_BUSY', 'Finaliza la llamada antes de reiniciar el navegador.');
      if (this.state !== 'ready') throw new ServiceError('NOT_READY', 'El navegador ya se está preparando.', 503);
      if ((await this.serial(() => this.driver.snapshot())).active) throw new ServiceError('CALL_BUSY', 'WhatsApp tiene una llamada activa.');
      this.state = 'recovering'; this.clearTimer('poll'); this.failureCount = 1;
      void this.recover().catch(error => this.fatal(error));
      return this.status();
    });
  }
  async fatal(error) {
    if (this.active?.cleanup?.state === 'unconfirmed' && this.active.cleanup.reason === 'different_call_observed') {
      this.state = 'error';
      this.lastError = { code: 'AUDIO_CLEANUP_UNCONFIRMED', message: 'No se pudo confirmar la limpieza sin afectar otra llamada.' };
      this.log('service_error', { code: error.code || 'UNKNOWN' });
      this.scheduleCleanupRetry(this.active);
      return; // A storage failure must not close a known unrelated call.
    }
    this.lastError = { code: 'SERVICE_ERROR', message: 'Error de almacenamiento o control; el navegador se cerrará.' };
    this.log('service_error', { code: error.code || 'UNKNOWN' });
    this.state = 'error';
    await this.driver.close().catch(() => {});
    if (this.active) await this.finish(this.active, 'interrupted', 'service_error').catch(() => {});
  }
  async stop() {
    this.agenda?.stop();
    this.stopping = true; this.state = 'stopping'; ++this.generation;
    for (const name of [...this.timers.keys()]) this.clearTimer(name);
    if (this.active) {
      const record = this.active; record.endRequested = 'service_shutdown';
      try { if (record.nativeId) await this.driver.end(record.nativeId, { incoming: record.direction === 'incoming' }); } catch {}
      await this.finish(record, 'interrupted', 'service_shutdown');
    }
    await this.driver.close();
    await this.queue;
    await this.journal.writes;
    this.state = 'stopped';
  }
}

module.exports = { CallManager };
