'use strict';
// R9: PCM de contenido, sin comandos, navegador ni proveedor. Referencia en docs/portados/audiovisual.md.
class PcmQueue {
  constructor(callId, sessionId, epoch = 0) {
    if (typeof callId !== 'string' || !callId || typeof sessionId !== 'string' || !sessionId || !Number.isSafeInteger(epoch) || epoch < 0) throw new Error('PCM_IDENTITY');
    this.callId = callId; this.sessionId = sessionId; this.epoch = epoch;
    this.parts = []; this.bytes = 0; this.sequence = -1; this.closed = false;
  }
  push({callId, sessionId, epoch, sequence, pcm}) {
    if (this.closed || callId !== this.callId || sessionId !== this.sessionId || epoch !== this.epoch) return {discarded: true};
    if (!Number.isSafeInteger(sequence) || sequence < 0 || !Buffer.isBuffer(pcm) || !pcm.length || pcm.length > 96000 || pcm.length % 2) throw new Error('PCM_FORMAT');
    if (sequence <= this.sequence) return {discarded: true};
    if (this.bytes + pcm.length > 480000) return {retryAfterMs: 250};
    this.parts.push(Buffer.from(pcm)); this.bytes += pcm.length; this.sequence = sequence;
    return {accepted: true};
  }
  take(frames = 240) {
    if (!Number.isSafeInteger(frames) || frames < 1 || frames > 48000) throw new Error('PCM_FRAME_COUNT');
    if (this.closed || this.bytes === 0) return null;
    const out = Buffer.alloc(Math.min(frames * 2, this.bytes)); let offset = 0;
    while (offset < out.length) {
      const head = this.parts[0], count = Math.min(head.length, out.length - offset);
      head.copy(out, offset, 0, count); offset += count; this.bytes -= count;
      if (count === head.length) this.parts.shift(); else this.parts[0] = head.subarray(count);
    }
    return {callId: this.callId, sessionId: this.sessionId, epoch: this.epoch, sampleRate: 24000, channels: 1, format: 's16le', pcm: out};
  }
  clear(epoch) {
    if (!Number.isSafeInteger(epoch) || epoch <= this.epoch || this.closed) return false;
    this.parts = []; this.bytes = 0; this.sequence = -1; this.epoch = epoch; return true;
  }
  close() { this.parts = []; this.bytes = 0; this.closed = true; }
}
module.exports = {PcmQueue};
