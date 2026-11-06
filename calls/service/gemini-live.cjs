'use strict';

const WebSocket = require('ws');
const { ServiceError } = require('./common.cjs');
const { liveSetupError, liveCloseError } = require('./live-errors.cjs');
const { GROUP_VOICE_TOOL, GROUP_VOICE_SYSTEM } = require('./group-voice-gate.cjs');
const { GroupDirector } = require('./group-director.cjs');
const { SPOKEN_SYSTEM, VOICES } = require('./spoken-controls.cjs');

const LIVE_SYSTEM = 'Eres Botsky. Habla en español claro y breve. Escucha antes de responder. Solo las herramientas cerradas de esta llamada están disponibles; nunca decides comandos de chat ni accedes al ejecutor general. No inventes acciones, memoria ni identidad de hablantes. Si se superponen voces pide repetir sin inventar lo que dijeron.';

class GeminiLive {
  constructor({ key, model, onAudio, onFailure, onTurn = () => {}, onInput = () => {}, onActivity = () => {}, onInterrupted = () => {}, onGenerationComplete = () => {}, interruptOnSpeech = false, groupVoice = false, callId, sessionId, tools, onToolCall, voiceName = 'Aoede', Socket = WebSocket }) {
    Object.assign(this, { key, model, onAudio, onFailure, onTurn, onInput, onActivity, onInterrupted, onGenerationComplete, interruptOnSpeech, tools, onToolCall, voiceName, Socket });
    this.voiceGate = groupVoice ? new GroupDirector({ callId, sessionId }) : null;
    if (this.voiceGate) this.tools = [...(tools || []), GROUP_VOICE_TOOL];
    this.toolResults = new Map(); this.toolControllers = new Map(); this.toolCancelled = new Set();
    this.closed = false; this.ready = false; this.responding = false; this.outputMuted = false;
    this.stats = { inputBytes: 0, outputBytes: 0, inputTurns: 0, outputTurns: 0, inputEnds: 0 };
  }
  isOutputCurrent(token) { return !this.closed && (!this.voiceGate || this.voiceGate.isCurrent(token)); }
  outputCompleted(token, endedAt) { this.voiceGate?.playbackEnded(token, endedAt); }
  async connect({ timeoutMs = 15000 } = {}) { return this.openConnection(undefined, timeoutMs); }
  async openConnection(handle, timeoutMs = 15000) {
    if (typeof this.model !== 'string' || !this.model.trim()) throw new ServiceError('LIVE_MODEL_UNCONFIGURED', 'Live necesita un modelo explícito.', 503);
    if (this.closed) throw new ServiceError('LIVE_CANCELLED', 'Se canceló Live.', 409);
    const generation = this.connectionGeneration = (this.connectionGeneration || 0) + 1;
    const previous = this.socket;
    this.ready = false; this.interruptedCompletionPending = false;
    return new Promise((resolve, reject) => {
      let settled = false, broken = false;
      const current = () => !this.closed && this.connectionGeneration === generation;
      const rejectSetup = code => {
        if (settled) return;
        settled = true; clearTimeout(timer); this.cancelConnect = null;
        reject(new ServiceError(code, 'No se pudo mantener la conversación en vivo.', 503));
      };
      const fail = code => {
        if (!current() || broken) return;
        broken = true; this.ready = false;
        if (!settled) { rejectSetup(code); ws.close(); }
        else this.transportLost(code);
      };
      const timer = setTimeout(() => fail('LIVE_SETUP_TIMEOUT'), timeoutMs);
      this.cancelConnect = () => rejectSetup('LIVE_CANCELLED');
      let ws;
      if (typeof this.key !== 'string' || /[\x00-\x1f\x7f]/.test(this.key)) { rejectSetup('LIVE_KEY_REJECTED'); return; }
      try { ws = this.socket = new this.Socket('wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent', {
        headers: { 'x-goog-api-key': this.key }, maxPayload: 2 * 1024 * 1024, handshakeTimeout: Math.min(12000, timeoutMs),
      }); } catch { rejectSetup('LIVE_REQUEST_INVALID'); return; }
      if (previous) this.releaseSocket(previous);
      ws.on('open', () => {
        if (!current()) return;
        try { this.sendNow({ setup: {
          model: `models/${this.model}`, generationConfig: { responseModalities: ['AUDIO'], speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: this.voiceName } } } },
          systemInstruction: { parts: [{ text: LIVE_SYSTEM + (this.tools?.some(tool => tool.functionDeclarations?.some(item => item.name === 'controlar_llamada')) ? SPOKEN_SYSTEM : '') + (this.tools?.some(tool => tool.functionDeclarations?.some(item => item.name === 'controlar_clips')) ? '\nPuedes usar controlar_clips únicamente para esta videollamada. Al pedir memes, clips, pausarlos, repetirlos, otro o volumen del clip, usa la herramienta. Consulta list si desconoces los nombres. Si responde needs_clarification, lee las opciones y pregunta; conserva el número elegido. No inventes archivos ni confirmes success:false. No reproduzcas algo diferente al nombre pedido. No inicies acciones sin petición del interlocutor. Las preguntas generales no requieren herramientas. Si está declarada controlar_avatar, permite elegir fondo (studio, neon, sunset, night), expresión (neutral, relaxed, happy, angry, sad, surprised, wink, laugh), gesto (wave, nod, shake_head, hand_to_chest) o rubor suave (soft) al pedirlo. La duración de expresión, gesto o rubor, cuando se indique, es de 1 a 15 segundos. Puedes acompañar una emoción clara con una expresión ocasional, sin llamar herramientas en cada frase. Cambiar de avatar o inventar personajes no está disponible.' : this.tools ? '\nUsa únicamente las herramientas declaradas para esta llamada.' : '\nNo tienes herramientas ni puedes ejecutar comandos. Nunca afirmes que realizaste acciones fuera de la conversación.') + (this.voiceGate ? '\n' + GROUP_VOICE_SYSTEM : '') }] },
          ...(this.tools ? { tools: this.tools } : {}),
          realtimeInputConfig: { automaticActivityDetection: { silenceDurationMs: 650, prefixPaddingMs: 200 }, activityHandling: this.interruptOnSpeech ? 'START_OF_ACTIVITY_INTERRUPTS' : 'NO_INTERRUPTION' },
          inputAudioTranscription: {}, outputAudioTranscription: {},
          contextWindowCompression: { slidingWindow: {} }, sessionResumption: handle ? { handle } : {},
        } }); } catch { fail('LIVE_SOCKET_ERROR'); }
      });
      ws.on('message', raw => {
        if (!current()) return;
        try {
          const message = JSON.parse(raw.toString());
          if (message.error) {
            if (!settled) { broken = true; rejectSetup(liveSetupError(message.error)); ws.close(); }
            else this.fail('LIVE_PROVIDER_ERROR');
            return;
          }
          if (message.setupComplete && !settled) {
            this.ready = true; settled = true; clearTimeout(timer); this.cancelConnect = null;
            this.stats.connections = (this.stats.connections || 0) + 1; resolve();
          }
          for (const id of message.toolCallCancellation?.ids || []) {
            this.toolCancelled.add(id); this.toolControllers.get(id)?.abort(); this.toolResults.get(id)?.controller?.abort();
          }
          if (message.toolCall?.functionCalls) void this.handleToolCalls(message.toolCall.functionCalls, this.voiceGate?.current).catch(() => this.fail('LIVE_TOOL_ERROR'));
          const content = message.serverContent;
          if (content?.inputTranscription?.text) { this.voiceGate?.transcript(content.inputTranscription.text); this.stats.inputTurns++; this.onInput(); }
          if (content?.interrupted && this.interruptOnSpeech) {
            if (this.voiceGate && this.inputInterruptionCleared && !this.voiceGate.current.interrupted) this.interruptedCompletionPending = true;
            if (!this.inputInterruptionCleared) {
              this.responding = false; this.generationDone = true;
              this.cancelToolCallsForTurn(this.voiceGate?.current);
              this.voiceGate?.interrupted(); this.onInterrupted();
              this.inputInterruptionCleared = true; this.setActivity('listening');
            }
          }
          for (const part of content?.interrupted ? [] : content?.modelTurn?.parts || []) {
            if (part.inlineData?.data) {
              if (!/^audio\/pcm(?:;rate=24000)?$/.test(part.inlineData.mimeType || '')) return this.fail('LIVE_AUDIO_FORMAT');
              const data = Buffer.from(part.inlineData.data, 'base64');
              if (data.length > 96000 || data.length % 2) return this.fail('LIVE_AUDIO_FORMAT');
              this.generationDone = false;
              this.stats.outputBytes += data.length; this.responding = true;
              if (!this.outputMuted && (!this.voiceGate || this.voiceGate.allowed)) { this.voiceGate?.speaking(); this.setActivity('speaking'); this.onAudio(data, this.voiceGate?.token()); } else if (this.voiceGate) this.stats.suppressedBytes = (this.stats.suppressedBytes || 0) + data.length;
            }
          }
          if (content?.outputTranscription?.text) this.voiceGate?.outputText(content.outputTranscription.text);
          if (content?.generationComplete && !content.interrupted && !this.interruptedCompletionPending) {
            this.generationDone = true;
            if (this.voiceGate && !this.voiceGate.current.generationDone) {
              this.voiceGate.generationFinished(); this.onGenerationComplete(this.voiceGate.token());
            }
          }
          if (content?.turnComplete) {
            if (content.interactionStatus !== 'IN_PROGRESS' && this.interruptedCompletionPending) {
              // This is the completion of the interrupted predecessor, not the
              // response belonging to the new input that already replaced it.
              this.interruptedCompletionPending = false;
            } else if (content.interactionStatus !== 'IN_PROGRESS') {
              this.responding = false; this.generationDone = true; this.silenceWaiting = false;
              if (this.resumeAfterSilence) this.outputMuted = false;
              this.setActivity('listening');
              if (this.voiceGate && !this.voiceGate.current.generationDone) {
                this.voiceGate.generationFinished(); this.onGenerationComplete(this.voiceGate.token());
              }
              this.voiceGate?.end();
            }
            this.stats.outputTurns++; this.onTurn();
          }
          if (message.sessionResumptionUpdate) {
            const update = message.sessionResumptionUpdate;
            this.resumable = update.resumable === true && typeof update.newHandle === 'string' && !!update.newHandle;
            if (this.resumable) this.resumeHandle = update.newHandle;
          }
          if (message.goAway) this.requestRenewal(message.goAway);
          this.maybeResume();
        } catch { this.fail('LIVE_PROTOCOL_ERROR'); }
      });
      ws.on('error', () => fail('LIVE_SOCKET_ERROR'));
      ws.on('unexpected-response', (_request, response) => {
        response.resume();
        fail(liveSetupError({ code: response.statusCode }));
        ws.terminate();
      });
      ws.on('close', (code, reason) => fail(settled ? 'LIVE_SOCKET_CLOSED' : liveCloseError(code, reason)));
    });
  }
  async handleToolCalls(calls, voiceTurn = this.voiceGate?.current) {
    const transportGeneration = this.connectionGeneration;
    const invalidControlPlan = calls.some(call => call.name === 'controlar_llamada') && calls.length !== 1;
    this.setActivity('thinking');
    for (const call of calls) {
      if (this.closed || typeof call.id !== 'string' || !call.id || this.toolCancelled.has(call.id)) continue;
      let entry = this.toolResults.get(call.id);
      if (!entry) {
        if (this.toolResults.size >= 1000) { this.fail('LIVE_TOOL_LIMIT'); return; }
        const controller = new AbortController(); this.toolControllers.set(call.id, controller);
        const signature = JSON.stringify({ name: call.name, args: call.args });
        const work = Promise.resolve().then(() => {
          if (invalidControlPlan) return { success: false, message: 'Pide un solo control de llamada por vez.' };
          if (this.closed || controller.signal.aborted || transportGeneration !== this.connectionGeneration) return { success: false, message: 'Petición cancelada.' };
          if (this.voiceGate && call.name === 'autorizar_turno') return this.voiceGate.authorize(call.args?.addressed, voiceTurn, controller.signal, call.args?.answeringPending);
          if (this.voiceGate && call.name === 'dejar_pregunta') return this.voiceGate.proposeQuestion(call.args?.question, voiceTurn);
          if (!this.tools || !this.tools.flatMap(tool => tool.functionDeclarations || []).some(declaration => declaration.name === call.name) || !this.onToolCall) return { success: false, message: 'Herramienta no disponible.' };
          if (this.voiceGate && (voiceTurn !== this.voiceGate.current || voiceTurn?.completed || (!this.voiceGate.allowed && call.name !== 'controlar_avatar'))) return { success: false, message: 'Intervención sin autorización.' };
          return this.onToolCall(call.args || {}, { id: call.id, name: call.name, signal: controller.signal });
        }).catch(() => ({ success: false, message: 'No pude ejecutar esa acción.' }));
        entry = { signature, work, voiceTurn, controller, name: call.name }; this.toolResults.set(call.id, entry);
      }
      const signature = JSON.stringify({ name: call.name, args: call.args });
      let response = entry.signature === signature ? await entry.work : { success: false, message: 'La petición cambió con el mismo identificador.' };
      this.toolControllers.delete(call.id);
      if (this.voiceGate && (entry.voiceTurn !== this.voiceGate.current || entry.voiceTurn?.completed)) response = call.name === 'autorizar_turno' ? { allowVoice: false } : { success: false, message: 'La intervención ya terminó.' };
      if (transportGeneration !== this.connectionGeneration) continue;
      if (!this.closed && !this.toolCancelled.has(call.id)) {
        const declaration = this.tools?.flatMap(tool => tool.functionDeclarations || []).find(item => item.name === call.name);
        const functionResponse = { id: call.id, name: call.name, response };
        if (declaration?.behavior === 'NON_BLOCKING' && ['controlar_avatar', 'dejar_pregunta'].includes(call.name)) {
          functionResponse.willContinue = false;
          functionResponse.scheduling = 'SILENT';
        }
        const payload = { toolResponse: { functionResponses: [functionResponse] } };
        // Complete the pending function on the old connection before rotating;
        // queueing this response would prevent the provider from ending its turn.
        if (this.renewal && this.ready && !this.renewal.connecting) this.sendNow(payload);
        else this.send(payload);
      }
      if (this.pendingVoiceName) this.requestRenewal({ timeLeft: '20s', reason: 'voice' });
      this.maybeResume();
    }
  }
  cancelToolCallsForTurn(turn) {
    const privateAvatarOnly = !this.voiceGate && !turn;
    if (!turn && !privateAvatarOnly) return;
    for (const [id, entry] of this.toolResults) {
      if ((privateAvatarOnly ? entry.name !== 'controlar_avatar' : entry.voiceTurn !== turn) || !this.toolControllers.has(id)) continue;
      this.toolCancelled.add(id);
      this.toolControllers.get(id)?.abort();
    }
  }
  requestVoiceChange(name, { signal } = {}) {
    if (signal?.aborted) return { success: false, message: 'Cambio cancelado.' };
    if (!Object.hasOwn(VOICES, name)) return { success: false, message: 'Esa voz no está disponible.' };
    if (name === this.voiceName) {
      const pending = this.pendingVoiceChange;
      if (pending?.started) return { success: false, message: 'El cambio de voz ya está en curso.' };
      pending?.cancel();
      return { success: true, unchanged: true, voice: name };
    }
    if (this.closed || !this.ready || !this.resumable || !this.resumeHandle || this.renewal || this.pendingVoiceName) return { success: false, message: 'Ahora no puedo cambiar la voz conservando esta conversación.' };
    if ((this.renewalTimes || []).filter(time => Date.now() - time < 60000).length >= 2) return { success: false, message: 'Espera un poco antes de cambiar otra vez la voz.' };
    const change = this.pendingVoiceChange = { name, signal, started: false };
    change.cancel = () => {
      if (this.pendingVoiceChange !== change || change.started) return;
      signal?.removeEventListener('abort', change.cancel);
      this.pendingVoiceName = null; this.pendingVoiceChange = null;
      const renewal = this.renewal;
      if (renewal?.reason === 'voice' && !renewal.connecting) {
        clearTimeout(renewal.timer); this.renewal = null;
        // Preserve input buffered while waiting for the safe checkpoint.
        try {
          for (const message of renewal.queue) if (!this.sendNow(message)) { this.fail('LIVE_RESUMPTION_FAILED'); break; }
        } catch { this.fail('LIVE_RESUMPTION_FAILED'); }
        renewal.queue = [];
      }
    };
    signal?.addEventListener('abort', change.cancel, { once: true });
    this.pendingVoiceName = name;
    if (!this.toolControllers.size) { this.requestRenewal({ timeLeft: '20s', reason: 'voice' }); this.maybeResume(); }
    return { success: true, pending: true, voice: name, message: 'Cambio solicitado; espera la reanudación antes de confirmar que se aplicó.' };
  }
  fail(code) {
    if (this.closed || this.failed) return;
    this.failed = true;
    this.close();
    this.onFailure?.(new ServiceError(code, 'No se pudo mantener la conversación en vivo.', 503));
  }
  transportLost(code) {
    if (this.closed) return;
    if (this.resumable && this.resumeHandle && (!this.responding || this.generationDone) && !this.inputOpen) {
      this.requestRenewal({ timeLeft: '15s' }); this.maybeResume();
    } else this.fail(this.renewal ? 'LIVE_RESUMPTION_UNAVAILABLE' : code);
  }
  requestRenewal({ timeLeft, reason = 'provider' } = {}) {
    if (this.closed) return;
    if (this.renewal) {
      if (reason === 'provider') this.renewal.reason = 'provider';
      return;
    }
    // Finish any partially transmitted utterance before pausing new input.
    if (this.inputOpen && this.ready) this.endAudio();
    const match = typeof timeLeft === 'string' && /^(\d+(?:\.\d+)?)s$/.exec(timeLeft);
    const waitMs = match ? Math.max(0, Math.min(60000, Number(match[1]) * 1000 - 1000)) : 10000;
    this.renewal = { queue: [], bytes: 0, connecting: false, reason,
      timer: setTimeout(() => this.fail('LIVE_RESUMPTION_UNAVAILABLE'), waitMs) };
  }
  maybeResume() {
    const renewal = this.renewal;
    if (this.closed || this.toolControllers.size || !renewal || renewal.connecting || !this.resumable || !this.resumeHandle || (this.responding && !this.generationDone) || this.inputOpen) return;
    const now = Date.now();
    this.renewalTimes = (this.renewalTimes || []).filter(time => now - time < 60000);
    if (this.renewalTimes.length >= 2) return this.fail('LIVE_RENEWAL_LIMIT');
    this.renewalTimes.push(now);
    renewal.connecting = true; clearTimeout(renewal.timer);
    this.voiceGate?.setReconnecting(true);
    this.setActivity(this.activityState || 'listening');
    const handle = this.resumeHandle;
    this.resumable = false;
    this.responding = false; this.silenceWaiting = false;
    if (this.resumeAfterSilence) this.outputMuted = false;
    const changingVoice = this.pendingVoiceName;
    const voiceChange = this.pendingVoiceChange;
    if (voiceChange) voiceChange.started = true;
    if (changingVoice) this.voiceName = changingVoice;
    void this.openConnection(handle).then(() => {
      if (this.closed || this.renewal !== renewal) return;
      this.voiceGate?.setReconnecting(false);
      if (changingVoice) { voiceChange?.signal?.removeEventListener('abort', voiceChange.cancel); this.pendingVoiceChange = null; this.pendingVoiceName = null; this.stats.voiceChanges = (this.stats.voiceChanges || 0) + 1; }
      this.renewal = null; this.stats.renewals = (this.stats.renewals || 0) + 1;
      this.setActivity(this.activityState || 'listening');
      for (const message of renewal.queue) {
        if (!this.sendNow(message)) return this.fail('LIVE_RESUMPTION_FAILED');
        if (message.realtimeInput?.audioStreamEnd) { this.responding = true; this.setActivity('thinking'); }
      }
      renewal.queue = [];
    }).catch(() => { if (!this.closed) this.fail('LIVE_RESUMPTION_FAILED'); });
  }
  send(data) {
    if (this.closed) return false;
    if (this.renewal) {
      const bytes = Buffer.byteLength(JSON.stringify(data));
      if (this.renewal.bytes + bytes > 2 * 1024 * 1024 || this.renewal.queue.length >= 1024) {
        this.fail('LIVE_RENEWAL_INPUT_BACKLOG'); return false;
      }
      this.renewal.bytes += bytes; this.renewal.queue.push(data); return true;
    }
    return this.sendNow(data);
  }
  sendNow(data) {
    if (this.closed || this.socket?.readyState !== WebSocket.OPEN) return false;
    if (this.socket.bufferedAmount > 256000) throw new ServiceError('LIVE_INPUT_BACKLOG', 'Se retrasó el audio entrante.', 503);
    this.socket.send(JSON.stringify(data));
    if (data.clientContent?.turnComplete || data.realtimeInput?.audio || data.realtimeInput?.audioStreamEnd) this.generationDone = false;
    if (data.realtimeInput?.audio) this.inputOpen = true;
    if (data.realtimeInput?.audioStreamEnd) this.inputOpen = false;
    return true;
  }
  audio(data) {
    if ((!this.ready && !this.renewal) || this.closed) return;
    if (!this.inputOpen) {
      const previous = this.voiceGate?.current;
      const cut = this.interruptOnSpeech && !!this.voiceGate && !!(previous?.hadAudio || previous?.allowed || this.responding);
      this.inputInterruptionCleared = cut;
      this.cancelToolCallsForTurn(this.voiceGate?.current);
      this.voiceGate?.begin();
      if (cut) this.onInterrupted();
      this.setActivity('listening');
    }
    if (this.outputMuted) { this.resumeAfterSilence = true; if (!this.silenceWaiting) this.outputMuted = false; }
    this.stats.inputBytes += data.length;
    this.send({ realtimeInput: { audio: { data: data.toString('base64'), mimeType: 'audio/pcm;rate=16000' } } });
  }
  greet({ incoming = false, liveRequest } = {}) {
    const introduction = incoming ? 'Acabas de contestar una llamada. Saluda con confianza y tu personalidad habitual; luego escucha al interlocutor.' :
      'La llamada ya está conectada. Saluda con naturalidad y tu personalidad habitual. Si no hay tema inicial, deja que el interlocutor comience.';
    const text = liveRequest ? introduction + '\nEncargo explícito del mensaje que solicitó esta llamada (datos del usuario):\n' + JSON.stringify(liveRequest) +
      '\nYa se resolvió el destino: no leas números ni órdenes de marcación. Usa el tema y propósito expresamente pedidos para abrir la conversación y desarrollarla; las respuestas de los interlocutores llevan el hilo. No tienes acceso al historial privado ni puedes revelar recuerdos de otros chats.' : introduction;
    this.voiceGate?.begin({ greeting: true });
    this.responding = true;
    this.setActivity('thinking');
    this.send({ clientContent: { turns: [{ role: 'user', parts: [{ text }] }], turnComplete: true } });
  }
  silence() {
    if ((!this.ready && !this.renewal) || this.closed) throw new ServiceError('LIVE_NOT_READY', 'La conversación no está lista.', 409);
    this.cancelToolCallsForTurn(this.voiceGate?.current);
    this.voiceGate?.silence();
    this.outputMuted = true; this.silenceWaiting = this.responding; this.resumeAfterSilence = false;
    this.setActivity('listening');
    // Update/interrupt the current turn without asking for a spoken acknowledgement.
    if (!this.send({ clientContent: { turns: [{ role: 'user', parts: [{ text: 'Detén la respuesta actual. Espera la siguiente intervención de los interlocutores; no confirmes esta instrucción ni continúes lo que estabas diciendo.' }] }], turnComplete: false } })) {
      throw new ServiceError('LIVE_NOT_READY', 'La conversación no está lista.', 409);
    }
  }
  endAudio() {
    if ((!this.ready && !this.renewal) || this.closed) return;
    this.responding = true; this.stats.inputEnds++;
    this.setActivity('thinking');
    this.send({ realtimeInput: { audioStreamEnd: true } });
  }
  releaseSocket(ws) {
    ws.close();
    const timer = setTimeout(() => ws.terminate(), 1000); timer.unref();
  }
  setActivity(state) {
    this.activityState = state;
    const visible = this.renewal?.connecting ? 'reconnecting' : state;
    if (this.closed || this.reportedActivity === visible) return;
    this.reportedActivity = visible; this.onActivity(visible);
  }
  close() {
    if (this.closed) return;
    this.closed = true; this.ready = false;
    const voiceChange = this.pendingVoiceChange;
    voiceChange?.signal?.removeEventListener('abort', voiceChange.cancel);
    this.pendingVoiceChange = null; this.pendingVoiceName = null;
    this.voiceGate?.close();
    for (const controller of this.toolControllers.values()) controller.abort();
    this.toolControllers.clear();
    this.cancelConnect?.(); this.cancelConnect = null;
    clearTimeout(this.renewal?.timer);
    this.renewal = null; this.resumeHandle = null; this.resumable = false;
    if (this.socket) this.releaseSocket(this.socket);
  }
}

module.exports = { GeminiLive, LIVE_SYSTEM };
