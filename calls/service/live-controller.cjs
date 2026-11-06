'use strict';

const { spawn } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const { GeminiLive } = require('./gemini-live.cjs');
const { liveKeys } = require('./live-credentials.cjs');
const { ServiceError } = require('./common.cjs');

class LiveController {
  constructor({ driver, runtime, onFailure = () => {}, log = () => {}, makeSession = options => new GeminiLive(options), capture = spawn, getKeys = liveKeys, wait = ms => new Promise(resolve => setTimeout(resolve, ms)), now = Date.now, getTools = () => ({}), onTurn = () => {}, onStop = () => {} }) {
    Object.assign(this, { driver, runtime, onFailure, log, makeSession, capture, getKeys, wait, now, getTools, onTurn, onStop });
    this.active = null;
  }
  status() {
    const s = this.active;
    return s ? { callId: s.callId, voice: s.session?.voiceName || 'Aoede', pendingVoice: s.session?.pendingVoiceName || null, state: s.session?.renewal ? 'renewing' : s.state, renewals: s.session?.stats.renewals || 0, inputSeconds: (s.session?.stats.inputBytes || 0) / 32000,
      outputSeconds: (s.session?.stats.outputBytes || 0) / 48000, inputEvents: s.session?.stats.inputTurns || 0,
      outputTurns: s.session?.stats.outputTurns || 0, completedInputTurns: s.session?.stats.inputEnds || 0,
      bridgeAcceptedSeconds: (s.bridgeAcceptedBytes || 0) / 48000, firstAudioLatencyMs: s.firstAudioAt && s.listeningAt ? Math.max(0, s.firstAudioAt-s.listeningAt) : null,
      groupDirector: s.session?.voiceGate?.snapshot?.() || null, receivedSpeechFrames: s.speechFrames, peakInput: s.peak, queuedBytes: s.queued } : null;
  }
  async prepare(record) {
    if (this.active) throw new ServiceError('LIVE_BUSY', 'Ya hay una conversación en vivo.', 409);
    const s = this.active = { callId: record.id, video: !!record.video, interruptOnSpeech: !!record.groupId && record.liveInterruption === true, id: randomUUID(), nativeId: null, state: 'preparing', epoch: 0, speechFrames: 0, peak: 0, queued: 0, output: Promise.resolve(), stopped: false };
    try {
      s.prepareAbort = new AbortController();
      const keys = await this.getKeys();
      if (!Array.isArray(keys) || keys.length !== 1 || typeof keys[0] !== 'string' || !keys[0].trim()) throw new ServiceError('LIVE_NO_KEY', 'Se requiere una única credencial explícita de Gemini.', 503);
      if (s.stopped || this.active !== s) throw new ServiceError('CANCELLED', 'Se canceló Live.');
      const key = keys[0].trim();
        let candidate;
        candidate = this.makeSession({ ...this.getTools(record), key, callId: s.callId, sessionId: s.id, groupVoice: !!record.groupId, onTurn: () => { if (s.session === candidate) this.onTurn(record); }, interruptOnSpeech: s.interruptOnSpeech, onGenerationComplete: token => {
          if (s.session === candidate) this.watchPlayback(s, token);
        }, onInterrupted: () => {
          if (s.session === candidate) void this.interrupt(s);
        }, onAudio: (data, turnToken) => {
          if (s.session === candidate) this.output(s, data, turnToken);
        }, onActivity: state => {
          if (s.session === candidate) this.activity(s, state);
        }, onFailure: error => {
          if (s.session === candidate) this.fail(s, error);
        } });
      s.session = candidate;
      await candidate.connect({timeoutMs:15000});
      if (s.stopped || this.active !== s) throw new ServiceError('CANCELLED', 'Se canceló Live.');
      s.state = 'waiting_answer';
    }
    catch (error) { const cancelled = s.stopped || this.active !== s; await this.stop(record.id);
      if (cancelled || error.name === 'AbortError') throw new ServiceError('CANCELLED', 'Se canceló Live.');
      throw error; }
  }
  async start(record) {
    const s = this.active;
    if (!s || s.callId !== record.id || s.stopped) throw new ServiceError('LIVE_OWNER_CHANGED', 'Cambió la llamada de Live.');
    const epoch = s.epoch;
    const valid = () => !s.stopped && !s.suspended && this.active === s && s.epoch === epoch;
    s.nativeId = record.nativeId;
    await this.bridge(() => this.driver.startLive(s.nativeId, s.id, s.epoch));
    if (!valid()) return;
    if (typeof record.volume === 'number') await this.bridge(() => this.driver.volume(s.nativeId, record.volume));
    if (!valid()) return;
    s.state = 'listening'; s.listeningAt ||= Date.now();
    this.activity(s, s.activity || 'listening');
    const child = s.child = this.capture('setpriv', ['--pdeathsig', 'TERM', 'parec', '--raw', '--device=botsky_calls.monitor',
      '--format=s16le', '--rate=16000', '--channels=1', '--latency-msec=40'], { env: this.runtime.env(), stdio: ['ignore', 'pipe', 'pipe'] });
    child.stderr.resume();
    let pending = Buffer.alloc(0), speaking = false, quietFrames = 0, lead = [];
    child.stdout.on('data', data => {
      if (s.stopped || s.suspended || this.active !== s) return;
      if (s.captureEpoch !== s.epoch) { pending = Buffer.alloc(0); lead = []; speaking = false; quietFrames = 0; s.captureEpoch = s.epoch; }
      pending = Buffer.concat([pending, data]);
      while (pending.length >= 1920) {
        const frame = pending.subarray(0, 1920); pending = pending.subarray(1920);
        let energy = 0;
        for (let i = 0; i < frame.length; i += 2) energy += (frame.readInt16LE(i) / 32768) ** 2;
        const rms = Math.sqrt(energy / (frame.length / 2));
        s.peak = Math.max(s.peak, rms); if (rms > 0.008) s.speechFrames++;
        try {
          if (rms > 0.008) {
            if (!speaking) { for (const previous of lead) s.session.audio(previous); lead = []; }
            speaking = true; quietFrames = 0;
          }
          if (speaking) {
            s.session.audio(frame);
            if (rms <= 0.008 && ++quietFrames >= 11) {
              s.session.endAudio(); speaking = false; quietFrames = 0;
            }
          } else { lead.push(Buffer.from(frame)); if (lead.length > 4) lead.shift(); }
        } catch (error) { this.fail(s, error); break; }
      }
    });
    child.on('error', () => this.fail(s, new ServiceError('LIVE_CAPTURE_FAILED', 'No se pudo capturar el audio.')));
    child.on('exit', () => { if (!s.stopped) this.fail(s, new ServiceError('LIVE_CAPTURE_STOPPED', 'Se detuvo la captura de audio.')); });
    s.session.greet({ incoming: record.direction === 'incoming', liveRequest: record.liveRequest });
    this.log('live_started', { id: record.id });
  }
  activity(s, state) {
    if (s.suspended) state = 'reconnecting';
    s.activity = state;
    if (!s.video || !s.nativeId || s.stopped || this.active !== s || !this.driver.liveActivity) return Promise.resolve();
    const epoch = s.epoch;
    s.visualOutput = (s.visualOutput || Promise.resolve()).then(() => {
      if (s.stopped || this.active !== s || s.epoch !== epoch) return;
      return this.driver.liveActivity(s.nativeId, s.id, state, epoch);
    }).catch(() => { this.log('live_visual_update_failed', { id: s.callId }); });
    return s.visualOutput;
  }
  output(s, data, turnToken) {
    if (s.stopped || s.suspended || s.failing || this.active !== s || !s.nativeId) return;
    const epoch = s.epoch, session = s.session;
    const valid = () => !s.stopped && !s.suspended && !s.failing && s.epoch === epoch && this.active === s && s.session === session && (!session?.isOutputCurrent || session.isOutputCurrent(turnToken));
    s.queued += data.length;
    // Bounded memory, independent of response length. The browser controls how
    // far ahead playback is scheduled, so long replies do not overflow its queue.
    if (s.queued > 32 * 1024 * 1024) { s.queued -= data.length; return this.fail(s, new ServiceError('LIVE_OUTPUT_BACKLOG', 'Se retrasó el audio de Live.')); }
    s.output = s.output.then(async () => {
      if (s.clearing) await s.clearing;
      while (valid()) {
        const result = await this.driver.liveAudio(s.nativeId, s.id, data, epoch);
        if (!valid() || result?.discarded) return;
        if (result?.retryAfterMs) { await this.wait(Math.min(250, Math.max(20, result.retryAfterMs))); continue; }
        s.bridgeAcceptedBytes = (s.bridgeAcceptedBytes || 0) + data.length; s.firstAudioAt ||= Date.now();
        return;
      }
    }).catch(error => { if (valid()) this.fail(s, error); }).finally(() => { s.queued -= data.length; });
  }
  watchPlayback(s, token) {
    if (!this.driver.livePlayback || !s.session?.voiceGate) return;
    const session = s.session, epoch = s.epoch, output = s.output;
    const valid = () => this.active === s && !s.stopped && !s.suspended && !s.failing && s.session === session && s.epoch === epoch && session.isOutputCurrent(token);
    s.playbackWatch = (async () => {
      await output; // Every generated chunk must be accepted/discarded before checking browser playback.
      while (valid()) {
        const playback = await this.driver.livePlayback(s.nativeId, s.id, epoch);
        if (!valid() || playback?.discarded) return;
        if (playback?.playing === false && Number.isFinite(playback.endedAt)) {
          session.outputCompleted(token, playback.endedAt); return;
        }
        await this.wait(200);
      }
    })().catch(() => { if (valid()) this.log('live_playback_observation_failed', { id: s.callId }); });
  }
  async interrupt(s) {
    if (!s.interruptOnSpeech || s.stopped || s.suspended || s.failing || this.active !== s || !s.nativeId) return;
    const epoch = ++s.epoch;
    try {
      // The browser may have scheduled seconds of PCM ahead of the receiver.
      // Fence old Node output immediately, then remove scheduled browser audio.
      const previous = s.clearing;
      const nativeId = s.nativeId;
      s.clearing = Promise.resolve(previous).then(() => {
        if (s.stopped || s.suspended || this.active !== s || s.epoch !== epoch) return;
        return this.driver.clearLive(nativeId, s.id, epoch);
      });
      await s.clearing;
      if (this.active === s && !s.stopped && !s.suspended && s.epoch === epoch) await this.activity(s, 'listening');
    } catch (error) { if (this.active === s && !s.stopped) this.fail(s, error); }
  }
  async silence(record) {
    const s = this.active;
    if (!s || s.callId !== record.id || s.stopped || s.failing || s.suspended || s.state !== 'listening') throw new ServiceError('LIVE_NOT_READY', 'La conversación no está lista.', 409);
    const epoch = ++s.epoch; s.silencing = true;
    try {
      s.session.silence();
      s.clearing = this.driver.clearLive(s.nativeId, s.id, epoch);
      await s.clearing;
      if (this.active === s && !s.stopped && !s.suspended && s.epoch === epoch) s.silencing = false;
    } catch (error) { this.fail(s, error); throw error; }
  }
  async suspend(record) {
    const s = this.active;
    if (!s || s.callId !== record.id || s.stopped) return;
    if (s.session?.voiceGate) s.session.cancelToolCallsForTurn?.(s.session.voiceGate.current);
    s.session?.voiceGate?.silence(); s.session?.voiceGate?.setReconnecting(true);
    s.suspended = true; s.epoch = (s.epoch || 0) + 1; s.state = 'recovering';
    await this.activity(s, 'reconnecting');
    if (s.nativeId) await this.bridge(() => this.driver.stopLive(s.nativeId, s.id));
  }
  async resume(record) {
    const s = this.active;
    if (!s || s.callId !== record.id || s.stopped || s.failing) throw new ServiceError('LIVE_OWNER_CHANGED', 'No queda una sesión recuperable.');
    if (!s.child) { s.session?.voiceGate?.setReconnecting(false); s.suspended = false; return this.start(record); }
    const epoch = s.epoch;
    s.nativeId = record.nativeId;
    await this.bridge(() => this.driver.startLive(s.nativeId, s.id, s.epoch));
    if (typeof record.volume === 'number') await this.bridge(() => this.driver.volume(s.nativeId, record.volume));
    if (this.active !== s || s.stopped || s.epoch !== epoch) return;
    s.session?.voiceGate?.setReconnecting(false);
    s.suspended = false; s.silencing = false; s.state = 'listening';
    this.activity(s, s.session?.activityState || 'listening');
  }
  async bridge(action) {
    try { return await action(); }
    catch (error) { error.callFailureSource = 'browser'; throw error; }
  }
  fail(s, error) {
    if (s.stopped || s.failing || this.active !== s) return;
    s.failing = true; s.state = 'failed';
    this.log('live_failed', { id: s.callId, code: error.code || 'LIVE_FAILED' });
    s.session?.close();
    Promise.resolve(this.onFailure(s.callId, error.code || 'LIVE_FAILED')).catch(() => {});
  }
  async stop(callId) {
    const s = this.active;
    if (!s || (callId && s.callId !== callId)) return;
    this.onStop(s.callId);
    s.stopped = true; this.active = null; s.prepareAbort?.abort(); s.session?.close();
    if (s.child && s.child.exitCode === null && s.child.signalCode == null) {
      const child = s.child;
      const timer = setTimeout(() => { if (child.exitCode === null && child.signalCode == null) child.kill('SIGKILL'); }, 1000); timer.unref();
      child.once('exit', () => clearTimeout(timer));
      child.kill('SIGTERM');
    }
    if (s.nativeId) await this.driver.stopLive(s.nativeId, s.id).catch(() => {});
    this.log('live_stopped', { id: s.callId });
  }
}

module.exports = { LiveController };
