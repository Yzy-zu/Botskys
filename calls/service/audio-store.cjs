'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { execFile } = require('node:child_process');
const { ServiceError, atomicJson } = require('./common.cjs');

const MAX_UPLOAD = 20 * 1024 * 1024;
const MAX_DURATION = 900;
const MAX_PCM = (MAX_DURATION + 1) * 96000 + 4096;
const FORMATS = 'wav,mp3,ogg,flac,aac,mov';

function toneWave(seconds = 1.4) {
  const samples = Math.round(seconds * 48000), wav = Buffer.alloc(44 + samples * 2);
  wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(48000, 24); wav.writeUInt32LE(96000, 28); wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++) {
    const t = i / 48000, note = Math.floor(t / 0.45), local = t % 0.45;
    const envelope = local < 0.3 ? Math.min(1, local / 0.015, (0.3 - local) / 0.03) : 0;
    const frequency = [440, 660, 880, 660, 550, 440][note % 6];
    wav.writeInt16LE(Math.round(0.3 * envelope * Math.sin(2 * Math.PI * frequency * t) * 32767), 44 + i * 2);
  }
  return wav;
}

class AudioStore {
  constructor(privateDir) {
    this.dir = path.join(privateDir, 'audio'); this.jobs = new Set(); this.busy = false; this.closing = false;
  }
  async init() {
    await fs.mkdir(this.dir, { recursive: true, mode: 0o700 });
    await fs.rm(path.join(this.dir, 'tmp'), { recursive: true, force: true });
    await fs.mkdir(path.join(this.dir, 'tmp'), { mode: 0o700 });
    this.tone = await this.exclusive(async dir => {
      const input = path.join(dir, 'input'); await fs.writeFile(input, toneWave(), { mode: 0o600 });
      return this.normalize(input, dir, { label: 'Tres tonos de prueba' });
    });
  }
  run(program, args, timeout = 15000, signal) {
    signal?.throwIfAborted();
    if (this.closing) return Promise.reject(new ServiceError('STOPPING', 'Se está cerrando el audio.', 503));
    return new Promise((resolve, reject) => {
      const child = execFile('setpriv', ['--pdeathsig', 'TERM', program, ...args], { signal, timeout, killSignal: 'SIGKILL', maxBuffer: 1024 * 1024 }, (error, stdout) => {
        this.jobs.delete(child);
        if (signal?.aborted) { reject(signal.reason); return; }
        if (error) reject(new ServiceError('AUDIO_PROCESS_FAILED', 'No se pudo preparar el audio con ese proveedor o formato.', 422));
        else resolve(stdout);
      });
      this.jobs.add(child);
    });
  }
  async exclusive(action, signal) {
    if (this.closing) throw new ServiceError('STOPPING', 'Se está cerrando el audio.', 503);
    signal?.throwIfAborted();
    if (this.busy) throw new ServiceError('AUDIO_PREPARING', 'Ya se está preparando otro audio.');
    this.busy = true;
    let dir;
    try { dir = await fs.mkdtemp(path.join(this.dir, 'tmp/job-')); signal?.throwIfAborted(); return await action(dir); }
    finally { if (dir) await fs.rm(dir, { recursive: true, force: true }); this.busy = false; }
  }
  async normalize(input, dir, extra = {}, signal) {
    const output = path.join(dir, 'output.wav');
    await this.run('ffmpeg', ['-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-format_whitelist', FORMATS,
      '-i', input, '-map', '0:a:0', '-vn', '-t', String(MAX_DURATION + 1), '-af', 'alimiter=limit=0.85:level=false',
      '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', output], 60000, signal);
    const probe = JSON.parse(await this.run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'json', output], 5000, signal));
    const durationSeconds = Number(probe.format?.duration);
    if (!Number.isFinite(durationSeconds) || durationSeconds <= 0 || durationSeconds > MAX_DURATION + 0.01) {
      throw new ServiceError('AUDIO_DURATION', 'El audio debe durar como máximo 15 minutos.', 422);
    }
    signal?.throwIfAborted();
    const data = await fs.readFile(output);
    const id = createHash('sha256').update(data).digest('hex');
    try { return await this.get(id); } catch (error) { if (error.code !== 'AUDIO_NOT_FOUND') throw error; }
    if ((await this.list()).length >= 100) throw new ServiceError('AUDIO_STORE_FULL', 'Se alcanzó el límite de 100 audios.', 429);
    const asset = { id, durationSeconds, bytes: data.length, sampleRate: 48000, channels: 1, createdAt: Date.now(), ...extra };
    await fs.chmod(output, 0o600);
    await fs.rename(output, path.join(this.dir, `${id}.wav`));
    await atomicJson(path.join(this.dir, `${id}.json`), asset);
    return asset;
  }
  async importStream(stream, { signal } = {}) {
    return this.exclusive(async dir => {
      const file = await fs.open(path.join(dir, 'input'), 'wx', 0o600);
      let size = 0;
      const onAbort = () => stream.destroy(signal.reason);
      signal?.addEventListener('abort', onAbort, { once: true });
      try {
        signal?.throwIfAborted();
        for await (const chunk of stream.iterator({ destroyOnReturn: false })) {
          signal?.throwIfAborted();
          size += chunk.length;
          if (size > MAX_UPLOAD) throw new ServiceError('AUDIO_TOO_LARGE', 'El archivo supera 20 MiB.', 413);
          await file.write(chunk);
        }
      } finally { signal?.removeEventListener('abort', onAbort); await file.close(); }
      if (!size) throw new ServiceError('AUDIO_EMPTY', 'El archivo está vacío.', 400);
      return this.normalize(path.join(dir, 'input'), dir, {}, signal);
    }, signal);
  }
  async get(id) {
    if (id === 'tone') return this.tone;
    if (typeof id !== 'string' || !/^[a-f0-9]{64}$/.test(id)) throw new ServiceError('INVALID_AUDIO_ID', 'El identificador de audio no es válido.', 400);
    try {
      const asset = JSON.parse(await fs.readFile(path.join(this.dir, `${id}.json`), 'utf8'));
      if (asset.id !== id || !Number.isFinite(asset.durationSeconds) || asset.durationSeconds <= 0 || asset.durationSeconds > MAX_DURATION + 0.01 || !Number.isInteger(asset.bytes) || asset.bytes > MAX_PCM || asset.bytes < 44 || asset.sampleRate !== 48000 || asset.channels !== 1) {
        throw new ServiceError('AUDIO_INVALID', 'El registro de audio no es válido.', 422);
      }
      return asset;
    }
    catch (error) { if (error.code === 'ENOENT') throw new ServiceError('AUDIO_NOT_FOUND', 'No se encontró ese audio.', 404); throw error; }
  }
  async read(id) {
    const asset = await this.get(id);
    const stat = await fs.stat(path.join(this.dir, `${asset.id}.wav`));
    if (stat.size > MAX_PCM || stat.size !== asset.bytes) throw new ServiceError('AUDIO_INVALID', 'El tamaño del audio no coincide con su registro.', 422);
    const data = await fs.readFile(path.join(this.dir, `${asset.id}.wav`));
    if (data.length > MAX_PCM || createHash('sha256').update(data).digest('hex') !== asset.id) throw new ServiceError('AUDIO_INVALID', 'El archivo de audio no coincide con su registro.', 422);
    return { asset, data };
  }
  async list() {
    const names = (await fs.readdir(this.dir)).filter(name => /^[a-f0-9]{64}\.json$/.test(name));
    return Promise.all(names.map(name => this.get(name.slice(0, -5))));
  }
  async close() { this.closing = true; for (const child of this.jobs) child.kill('SIGKILL'); }
}

module.exports = { AudioStore, toneWave, MAX_UPLOAD, MAX_DURATION };
