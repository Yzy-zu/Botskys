'use strict';

// Install before WhatsApp loads: the call stack may retain a bound reference.
function installNativeMediaHook() {
  const devices = navigator.mediaDevices;
  if (!devices?.getUserMedia || window.__botskyNativeMediaInstalled) return;
  const original = devices.getUserMedia;
  devices.getUserMedia = function (constraints) {
    return window.__botskyAudio?.capture(constraints, 'native') || original.call(this, constraints);
  };
  window.__botskyNativeMediaInstalled = true;
}

// Runs inside WhatsApp's page. No network, DOM controls, or call initiation.
function installAudioBridge() {
  if (window.__botskyAudio) return;
  const media = window.require('WAGetUserMedia');
  const original = media.getUserMedia;
  const devices = navigator.mediaDevices;
  const originalNative = devices?.getUserMedia;
  const bridge = {
    videoSource: null,
    token: null, nativeId: null, incoming: false, context: null, gain: null, analyser: null,
    destinations: [], source: null, playback: null, micRequests: 0, captures: { module: 0, native: 0 }, prepared: null, resumeBuffer: null,
    liveSession: null, liveEpoch: 0, liveSources: new Set(), liveTimings: new Map(), liveNext: 0,
    isSpeaking() {
      if (this.context?.state !== 'running') return false;
      const now = this.context.currentTime;
      return [...this.liveTimings.values()].some(({ start, end }) => now >= start && now < end);
    },
    native() {
      const collection = window.require('WAWebCallCollection');
      return collection.activeCall || collection.lastActiveCall;
    },
    ownsMedia() {
      if (!this.token) return false;
      try {
        const call = this.native();
        if (this.incoming && (!call || String(call.id) !== this.nativeId || [0, 7, 'ENDED', 'FAILED', 'REJECTED', 'NOT_ANSWERED', 'HANDLED_REMOTELY'].includes(call.getState?.()))) return false;
        return !(call && call.getState?.() !== 0 && (!!call.outgoing === this.incoming || (this.nativeId && String(call.id) !== this.nativeId)));
      } catch { return false; }
    },
    stop() {
      const source = this.source; this.source = null;
      if (source) { try { source.stop(); source.disconnect(); } catch {} }
      if (this.playback?.state === 'playing') this.playback.state = 'stopped';
      for (const node of this.liveSources) { try { node.stop(); node.disconnect(); } catch {} }
      this.liveSources.clear(); this.liveTimings.clear(); this.liveNext = 0;
    },
    disarm(token) {
      if (token && token !== this.token) return false;
      this.stop();
      this.videoSource?.stop(); this.videoSource = null;
      for (const destination of this.destinations) {
        try { this.gain.disconnect(destination); } catch {}
        destination.stream.getTracks().forEach(track => track.stop());
      }
      this.destinations = []; this.token = null; this.nativeId = null; this.incoming = false; this.prepared = null; this.resumeBuffer = null; this.liveSession = null;
      return true;
    },
    async arm(token, { incomingNativeId, video = false } = {}) {
      this.disarm();
      if (!this.context || this.context.state === 'closed') {
        this.context = new AudioContext({ sampleRate: 48000 });
        this.gain = this.context.createGain();
        this.analyser = this.context.createAnalyser();
        this.analyser.fftSize = 2048;
        this.voiceAnalyser = this.context.createAnalyser(); this.voiceAnalyser.fftSize = 256;
        this.voiceSamples = new Float32Array(256);
        this.gain.connect(this.analyser);
      }
      this.token = token;
      this.incoming = !!incomingNativeId; this.nativeId = incomingNativeId || null;
      this.micRequests = 0; this.captures = { module: 0, native: 0 }; this.nativeVideo = null; this.playback = null;
      if (video) {
        const source = this.videoSource = window.__botskyVideo.create({ audioContext: this.context, audioOutput: this.gain, isSpeaking: () => this.isSpeaking(), valid: () => this.token === token,
          mouthLevel: () => {
            if (!this.isSpeaking()) return 0;
            this.voiceAnalyser.getFloatTimeDomainData(this.voiceSamples);
            return Math.min(1, Math.sqrt(this.voiceSamples.reduce((sum, n) => sum + n * n, 0) / this.voiceSamples.length) * 8);
          } });
        await source.ready;
        if (this.token !== token || this.videoSource !== source) { source.stop(); throw Error('AUDIO_OWNER_CHANGED'); }
      }
      this.gain.gain.value = 0.7;
      await this.context.resume();
    },
    bind(token, id) {
      if (token !== this.token) throw new Error('AUDIO_OWNER_CHANGED');
      this.nativeId = id;
    },
    matches(id, allowLonely = false) {
      const call = this.native();
      const state = call?.getState?.();
      const connected = [6, 'ACTIVE'].includes(state) || (allowLonely && [11, 'ConnectedLonely', 'CONNECTED_LONELY'].includes(state));
      return !!this.token && this.nativeId === id && call && String(call.id) === id && !!call.outgoing !== this.incoming && connected;
    },
    async decode(base64) {
      const binary = atob(base64), bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return this.context.decodeAudioData(bytes.buffer);
    },
    async preload({ token, audioId, base64 }) {
      if (token !== this.token) throw new Error('AUDIO_OWNER_CHANGED');
      const buffer = await this.decode(base64);
      if (token !== this.token) throw new Error('AUDIO_OWNER_CHANGED');
      this.prepared = { audioId, buffer };
      return true;
    },
    async play({ nativeId, id, audioId, base64, volume, offsetSeconds = 0 }) {
      if (!this.matches(nativeId)) throw new Error('AUDIO_CALL_CHANGED');
      if (this.source || this.liveSession) throw new Error('AUDIO_BUSY');
      const token = this.token;
      const buffer = audioId && this.resumeBuffer?.audioId === audioId ? this.resumeBuffer.buffer
        : audioId && this.prepared?.audioId === audioId ? this.prepared.buffer : await this.decode(base64);
      if (!Number.isFinite(offsetSeconds) || offsetSeconds < 0 || offsetSeconds >= buffer.duration) throw new Error('AUDIO_OFFSET_INVALID');
      if (token !== this.token || !this.matches(nativeId)) throw new Error('AUDIO_CALL_CHANGED');
      if (!this.destinations.some(d => d.stream.getAudioTracks().some(t => t.readyState === 'live'))) throw new Error('AUDIO_MIC_NOT_CAPTURED');
      await this.context.resume();
      if (token !== this.token || !this.matches(nativeId)) throw new Error('AUDIO_CALL_CHANGED');
      const source = this.context.createBufferSource();
      source.buffer = buffer; source.connect(this.gain);
      this.gain.gain.setValueAtTime(volume, this.context.currentTime);
      this.source = source;
      this.resumeBuffer = { audioId, buffer };
      this.playback = { id, audioId, offsetSeconds, startedContextTime: this.context.currentTime, state: 'playing', volume, durationSeconds: buffer.duration, startedAt: Date.now() };
      source.onended = () => {
        source.disconnect();
        if (this.source === source) { this.source = null; this.playback.state = 'ended'; }
      };
      source.start(0, offsetSeconds);
      return this.status();
    },
    pause({ nativeId, id, offsetSeconds }) {
      const call = this.native();
      if (!this.token || this.nativeId !== nativeId || String(call?.id) !== nativeId || !!call.outgoing === this.incoming || this.playback?.id !== id) throw new Error('AUDIO_CALL_CHANGED');
      if (!Number.isFinite(offsetSeconds) || offsetSeconds < 0 || offsetSeconds >= this.playback.durationSeconds) throw new Error('AUDIO_OFFSET_INVALID');
      const source = this.source; this.source = null;
      if (source) { try { source.stop(); source.disconnect(); } catch {} }
      Object.assign(this.playback, { state: 'paused', offsetSeconds });
      return this.status();
    },
    async resume({ nativeId, id, offsetSeconds }) {
      if (this.playback?.id !== id) throw new Error('AUDIO_CALL_CHANGED');
      if (this.playback.state === 'playing') return this.status();
      if (this.playback.state !== 'paused') throw new Error('AUDIO_CALL_CHANGED');
      return this.play({ nativeId, id, audioId: this.resumeBuffer?.audioId, volume: this.playback.volume, offsetSeconds });
    },
    async startLive({ nativeId, sessionId, epoch = 0 }) {
      if (this.matches(nativeId) && !this.source && this.liveSession === sessionId && this.liveEpoch === epoch) return;
      if (!this.matches(nativeId) || this.source || this.liveSession) throw new Error('AUDIO_CALL_CHANGED');
      if (!this.destinations.some(d => d.stream.getAudioTracks().some(track => track.readyState === 'live'))) throw new Error('AUDIO_MIC_NOT_CAPTURED');
      const token = this.token;
      await this.context.resume();
      if (token !== this.token || !this.matches(nativeId)) throw new Error('AUDIO_CALL_CHANGED');
      this.liveSession = sessionId; this.liveEpoch = epoch; this.liveNext = 0;
    },
    liveAudio({ nativeId, sessionId, base64, epoch = 0 }) {
      // Keep an existing session alive during the manager's empty-audience grace.
      if (!this.matches(nativeId, true) || this.liveSession !== sessionId) throw new Error('AUDIO_CALL_CHANGED');
      if (epoch !== this.liveEpoch) return { discarded: true };
      const binary = atob(base64);
      if (!binary.length || binary.length > 96000 || binary.length % 2) throw new Error('LIVE_AUDIO_FORMAT');
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < bytes.length; i++) bytes[i] = binary.charCodeAt(i);
      const view = new DataView(bytes.buffer), buffer = this.context.createBuffer(1, bytes.length / 2, 24000);
      const samples = buffer.getChannelData(0);
      for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
      const start = Math.max(this.context.currentTime + 0.04, this.liveNext);
      const ahead = start - this.context.currentTime + buffer.duration;
      if (ahead > 10) return { retryAfterMs: Math.min(250, Math.max(20, (ahead - 10) * 1000)) };
      const node = this.context.createBufferSource(); node.buffer = buffer; node.connect(this.gain); node.connect(this.voiceAnalyser);
      this.liveSources.add(node);
      this.liveTimings.set(node, { start, end: start + buffer.duration });
      node.onended = () => { node.disconnect(); this.liveSources.delete(node); this.liveTimings.delete(node); };
      node.start(start); this.liveNext = start + buffer.duration;
      return { accepted: true };
    },
    livePlayback({ nativeId, sessionId, epoch }) {
      if (!this.matches(nativeId, true) || this.liveSession !== sessionId || epoch !== this.liveEpoch) return { discarded: true };
      const remaining = Math.max(0, this.liveNext - this.context.currentTime);
      const playing = this.liveSources.size > 0 || remaining > 0;
      return { playing, remainingSeconds: remaining,
        endedAt: !playing && this.liveNext > 0 && this.context.state === 'running' ? Date.now() - Math.max(0, this.context.currentTime - this.liveNext) * 1000 : null };
    },
    clearLive({ nativeId, sessionId, epoch }) {
      if (!this.matches(nativeId, true) || this.liveSession !== sessionId) throw new Error('AUDIO_CALL_CHANGED');
      if (!Number.isSafeInteger(epoch) || epoch < 0) throw new Error('AUDIO_CALL_CHANGED');
      if (epoch <= this.liveEpoch) return { discarded: true };
      this.stop(); this.liveEpoch = epoch; this.videoSource?.setActivity('listening');
      return { cleared: true };
    },
    stopLive({ nativeId, sessionId }) {
      if (this.nativeId !== nativeId || this.liveSession !== sessionId) return;
      this.stop(); this.liveSession = null;
    },
    liveActivity({ nativeId, sessionId, state, epoch = 0 }) {
      if (!this.matches(nativeId, true) || this.liveSession !== sessionId || epoch < this.liveEpoch) return { discarded: true };
      if (!['listening', 'thinking', 'speaking', 'reconnecting'].includes(state)) throw Error('LIVE_VISUAL_INVALID');
      this.videoSource?.setActivity(state);
      return { accepted: true };
    },
    avatarControl({ nativeId, ...options }) {
      if (!this.matches(nativeId, true) || !this.videoSource) throw Error('AVATAR_CALL_CHANGED');
      return this.videoSource.avatarControl(options);
    },
    cancelAvatarControl({ nativeId, controlId }) {
      if (!this.matches(nativeId, true) || !this.videoSource) return;
      this.videoSource.cancelAvatarControl(controlId);
    },
    async playClip({ nativeId, ...options }) {
      if (!this.matches(nativeId) || !this.videoSource) throw Error('CLIP_CALL_CHANGED');
      return this.videoSource.playClip(options);
    },
    async controlClip({ nativeId, action, volume }) {
      if (!this.matches(nativeId, true) || !this.videoSource) throw Error('CLIP_CALL_CHANGED');
      return this.videoSource.controlClip(action, volume);
    },
    setVolume(value) {
      if (this.gain) this.gain.gain.setValueAtTime(value, this.context.currentTime);
      if (this.playback) this.playback.volume = value;
    },
    status() {
      let rms = 0;
      if (this.analyser && (this.source || this.liveSources.size || this.videoSource?.status().clip?.state === 'playing')) {
        const samples = new Float32Array(this.analyser.fftSize);
        this.analyser.getFloatTimeDomainData(samples);
        rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
      }
      const positionSeconds = this.playback?.state === 'ended' ? this.playback.durationSeconds : this.playback ? Math.min(this.playback.durationSeconds, this.playback.offsetSeconds + (this.playback.state === 'playing' ? Math.max(0, this.context.currentTime - this.playback.startedContextTime) : 0)) : null;
      return { playback: this.playback ? { ...this.playback, positionSeconds } : null,
        video: this.videoSource?.status() || { active: false, frames: 0, liveTracks: 0 },
        armed: !!this.token, microphoneStreams: this.micRequests, captures: { ...this.captures }, nativeVideo: this.nativeVideo || null,
        liveTracks: this.destinations.reduce((n, d) => n + d.stream.getAudioTracks().filter(t => t.readyState === 'live').length, 0),
        contextState: this.context?.state || null, rms };
    },
  };
  const capture = (constraints, via) => {
    const allowed = bridge.ownsMedia() && (constraints?.audio || (constraints?.video && bridge.videoSource)) && (!constraints?.video || !!bridge.videoSource);
    if (!allowed) return null;
    const token = bridge.token, source = bridge.videoSource;
    const acquire = () => {
      if (bridge.token !== token || !bridge.ownsMedia() || (constraints.video && bridge.videoSource !== source)) throw Error('AUDIO_CALL_CHANGED');
      let stream;
      if (constraints.audio) {
        const destination = bridge.context.createMediaStreamDestination();
        bridge.gain.connect(destination);
        bridge.destinations.push(destination); bridge.micRequests++;
        stream = destination.stream;
      } else stream = new MediaStream();
      if (constraints.video) stream.addTrack(source.track());
      bridge.captures[via]++;
      return stream;
    };
    return constraints.video ? Promise.resolve(source.ready).then(acquire) : Promise.resolve(acquire());
  };
  // WhatsApp's camera preview and its native call stack can use different
  // acquisition paths. Both must receive the same owned audio/video sources.
  media.getUserMedia = function (constraints) {
    return capture(constraints, 'module') || original.call(this, constraints);
  };
  bridge.capture = capture;
  if (originalNative && !window.__botskyNativeMediaInstalled) {
    devices.getUserMedia = function (constraints) {
      return capture(constraints, 'native') || originalNative.call(this, constraints);
    };
    window.__botskyNativeMediaInstalled = true;
  }
  window.__botskyAudio = bridge;
}

module.exports = { installAudioBridge, installNativeMediaHook };
