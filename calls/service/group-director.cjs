'use strict';

const { randomUUID } = require('node:crypto');
const { GroupVoiceGate } = require('./group-voice-gate.cjs');

// Owns local call/turn identity; semantic classification remains in Live.
class GroupDirector extends GroupVoiceGate {
  constructor({ callId, sessionId, now = Date.now, questionWindowMs = 30000, ...options } = {}) {
    super(options);
    this.owner = Object.freeze({ callId: callId || randomUUID(), sessionId: sessionId || randomUUID() });
    this.pendingQuestion = null;
    this.now = now; this.questionWindowMs = questionWindowMs;
    this.emotion = null;
    this.ended = false; this.reconnecting = false;
  }
  begin(options) {
    if (this.ended) return this.current;
    const turn = super.begin(options);
    this.expireQuestion();
    turn.pendingAnswer = this.pendingQuestion;
    this.pendingQuestion = null; // Only the first ensuing intervention may answer it.
    turn.startedAt = this.now?.() ?? Date.now();
    this.turnState = 'listening';
    return turn;
  }
  token() { return Object.freeze({ owner: this.owner, turn: this.current }); }
  isCurrent(token) { return !this.ended && token?.owner === this.owner && token.turn === this.current && !token.turn.interrupted; }
  expireQuestion() {
    if (this.pendingQuestion && this.now() >= this.pendingQuestion.expiresAt) this.pendingQuestion = null;
  }
  outputText(text) {
    if (this.ended || !(this.current.allowed || this.current.hadAudio) || typeof text !== 'string') return;
    this.current.outputText = ((this.current.outputText || '') + text).slice(-4000);
    if (Number.isFinite(this.current.playbackEndedAt)) this.playbackEnded(this.token(), this.current.playbackEndedAt);
  }
  generationFinished() { if (!this.ended) this.current.generationDone = true; }
  proposeQuestion(question, turn) {
    if (this.ended || turn !== this.current || turn.completed || !turn.allowed || typeof question !== 'string' || !question.trim() || question.length > 500) return { success: false };
    turn.question = question.trim();
    if (Number.isFinite(turn.playbackEndedAt)) this.playbackEnded(this.token(), turn.playbackEndedAt);
    return { success: true, deferred: true };
  }
  playbackEnded(token, endedAt) {
    if (!this.isCurrent(token) || !token.turn.generationDone || !token.turn.hadAudio || token.turn.questionRegistered || !Number.isFinite(endedAt) || endedAt > this.now()) return;
    token.turn.playbackEndedAt = endedAt;
    // A declared question must actually occur in the spoken transcript.
    const spoken = token.turn.outputText || '';
    const declared = token.turn.question && token.turn.question.trim().length >= 3 && spoken.includes(token.turn.question.trim());
    if (!declared) return;
    token.turn.questionRegistered = true;
    const expiresAt = endedAt + this.questionWindowMs;
    if (expiresAt > this.now()) this.pendingQuestion = { generation: token.turn.epoch, openedAt: endedAt, expiresAt };
  }
  async authorize(addressed, turn, signal, answeringPending = false) {
    if (this.ended || this.reconnecting || !turn || turn !== this.current || turn.completed || signal?.aborted) return { allowVoice: false };
    const authorization = turn.authorizationVersion = (turn.authorizationVersion || 0) + 1;
    const question = turn?.pendingAnswer;
    const answering = answeringPending === true && question && turn.startedAt < question.expiresAt;
    if (turn === this.current) { this.pendingQuestion = null; turn.pendingAnswer = null; } // An answer or a new topic consumes this question.
    if (answering && turn === this.current && !signal?.aborted) {
      if (!turn.text) await new Promise(resolve => {
        const finish = () => { clearTimeout(timer); signal?.removeEventListener('abort', finish); if (turn.finish === finish) delete turn.finish; resolve(); };
        const timer = setTimeout(finish, this.waitMs);
        turn.waitForAnyText = true; turn.finish = finish;
        signal?.addEventListener('abort', finish, { once: true });
        if (signal?.aborted) finish();
      });
      if (!this.ended && !this.reconnecting && turn === this.current && !turn.completed && turn.authorizationVersion === authorization && !signal?.aborted && turn.text) {
        turn.allowed = true; return { allowVoice: true };
      }
      return { allowVoice: false };
    }
    const result = await super.authorize(addressed, turn, signal, authorization);
    if (this.ended || this.reconnecting || turn?.completed) {
      if (turn === this.current) this.current.allowed = false;
      return { allowVoice: false };
    }
    if (!this.ended && turn === this.current && !result.allowVoice) this.turnState = 'waiting_addressed';
    return result;
  }
  speaking() { if (!this.ended && this.allowed) { this.current.hadAudio = true; this.turnState = 'responding'; } }
  interrupted() {
    if (this.ended) return;
    this.current.allowed = false; this.current.completed = true; this.current.interrupted = true;
    this.current.finish?.(); this.pendingQuestion = null; this.current.pendingAnswer = null;
    this.turnState = 'listening';
  }
  end() {
    if (this.ended) return;
    // Already admitted PCM keeps its identity until another input supersedes it.
    // New PCM after provider turnComplete must obtain a new permission.
    this.current.allowed = false;
    this.current.completed = true;
    this.current.finish?.();
    this.turnState = 'waiting_addressed';
  }
  setReconnecting(value) {
    if (this.ended) return;
    this.reconnecting = value;
    if (value) { this.current.allowed = false; this.current.completed = true; this.current.finish?.(); }
  }
  silence() { if (!this.ended) { this.pendingQuestion = null; this.begin(); this.turnState = 'waiting_addressed'; } }
  close() {
    if (this.ended) return;
    this.begin(); this.ended = true; this.pendingQuestion = null;
    this.turnState = 'ended'; this.reconnecting = false;
  }
  snapshot() {
    this.expireQuestion();
    return { ...this.owner, generation: this.current.epoch,
      state: this.ended ? 'ended' : this.reconnecting ? 'reconnecting' : this.turnState,
      allowVoice: !this.ended && !this.reconnecting && this.allowed,
      pendingQuestion: this.pendingQuestion, emotion: this.emotion };
  }
}

module.exports = { GroupDirector };
