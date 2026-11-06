'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { execFile } = require('node:child_process');
const { ServiceError, atomicJson } = require('./common.cjs');
const MAX_CLIP_BYTES = 20 * 1024 * 1024;
const MAX_CLIP_SECONDS = 180;
class ClipStore {
  constructor(privateDir) { this.dir = path.join(privateDir, 'clips'); this.jobs = new Set(); this.busy = false; this.closing = false; }
  async init() {
    await fs.mkdir(this.dir, { recursive: true, mode: 0o700 });
    await fs.rm(path.join(this.dir, 'tmp'), { recursive: true, force: true });
    await fs.mkdir(path.join(this.dir, 'tmp'), { mode: 0o700 });
  }
  run(program, args, signal) {
    signal?.throwIfAborted();
    return new Promise((resolve, reject) => {
      if (this.closing) return reject(new ServiceError('STOPPING', 'Se están cerrando los clips.', 503));
      const job = execFile('setpriv', ['--pdeathsig', 'TERM', program, ...args], { signal, timeout: 90000, killSignal: 'SIGKILL', maxBuffer: 1024 * 1024 }, (error, stdout) => {
        this.jobs.delete(job);
        if (error) reject(new ServiceError('CLIP_PROCESS_FAILED', 'No pude preparar ese video.', 422)); else resolve(stdout);
      });
      this.jobs.add(job);
    });
  }
  async exclusive(work) {
    if (this.closing) throw new ServiceError('STOPPING', 'Se están cerrando los clips.', 503);
    if (this.busy) throw new ServiceError('CLIP_PREPARING', 'Ya estoy preparando otro clip.', 409);
    this.busy = true; let dir;
    try { dir = await fs.mkdtemp(path.join(this.dir, 'tmp/job-')); return await work(dir); }
    finally { if (dir) await fs.rm(dir, { recursive: true, force: true }); this.busy = false; }
  }
  async normalize(input, dir, label, signal) {
    const output = path.join(dir, 'clip.webm');
    await this.run('ffmpeg', ['-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file,pipe', '-i', input,
      '-map', '0:v:0', '-map', '0:a:0?', '-t', String(MAX_CLIP_SECONDS + 1),
      '-vf', 'scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,fps=24,setsar=1',
      '-c:v', 'libvpx', '-deadline', 'realtime', '-cpu-used', '5', '-b:v', '650k', '-threads', '2',
      '-c:a', 'libopus', '-ar', '48000', '-ac', '1', '-b:a', '64k', '-af', 'alimiter=limit=0.85:level=false', output], signal);
    const probe = JSON.parse(await this.run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'json', output], signal));
    const durationSeconds = Number(probe.format?.duration), stat = await fs.stat(output);
    if (!Number.isFinite(durationSeconds) || durationSeconds <= 0 || durationSeconds > MAX_CLIP_SECONDS + 0.05) throw new ServiceError('CLIP_DURATION', 'Usa clips de hasta 3 minutos.', 422);
    if (stat.size > MAX_CLIP_BYTES) throw new ServiceError('CLIP_TOO_LARGE', 'El clip preparado supera 20 MiB.', 413);
    signal?.throwIfAborted();
    const data = await fs.readFile(output), id = createHash('sha256').update(data).digest('hex');
    const asset = { id, label: String(label || 'Clip').slice(0, 100), mimeType: 'video/webm', durationSeconds, bytes: data.length, createdAt: Date.now() };
    try { return await this.get(id); } catch (error) { if (error.code !== 'CLIP_NOT_FOUND') throw error; }
    if ((await this.list()).length >= 50) throw new ServiceError('CLIP_STORE_FULL', 'El catálogo admite 50 clips.', 429);
    await fs.rename(output, path.join(this.dir, id + '.webm'));
    await atomicJson(path.join(this.dir, id + '.json'), asset); return asset;
  }
  async importStream(stream, { signal, label } = {}) {
    return this.exclusive(async dir => {
      signal?.throwIfAborted();
      const input = path.join(dir, 'input'), file = await fs.open(input, 'wx', 0o600);
      let bytes = 0;
      const abort = () => stream.destroy(signal.reason);
      signal?.addEventListener('abort', abort, { once: true });
      try {
        for await (const chunk of stream.iterator({ destroyOnReturn: false })) {
          signal?.throwIfAborted(); bytes += chunk.length;
          if (bytes > MAX_CLIP_BYTES) throw new ServiceError('CLIP_TOO_LARGE', 'El archivo supera 20 MiB.', 413);
          await file.write(chunk);
        }
      } finally { await file.close(); signal?.removeEventListener('abort', abort); }
      if (!bytes) throw new ServiceError('CLIP_EMPTY', 'El archivo está vacío.', 400);
      return this.normalize(input, dir, label, signal);
    });
  }
  async demo({ signal } = {}) {
    const existing = (await this.list()).find(asset => asset.demo === true || asset.label === 'Prueba audiovisual V3');
    if (existing) {
      if (existing.demo) return existing;
      return this.exclusive(async () => {
        const asset = await this.get(existing.id); asset.demo = true;
        await atomicJson(path.join(this.dir, asset.id + '.json'), asset); return asset;
      });
    }
    return this.exclusive(async dir => {
      const input = path.join(dir, 'demo.mkv');
      await this.run('ffmpeg', ['-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=24',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '12', '-c:v', 'libvpx', '-deadline', 'realtime', '-cpu-used', '5', '-threads', '2', '-c:a', 'libopus', input], signal);
      const asset = await this.normalize(input, dir, 'Prueba audiovisual V3', signal);
      asset.demo = true; await atomicJson(path.join(this.dir, asset.id + '.json'), asset); return asset;
    });
  }
  async get(id) {
    if (!/^[a-f0-9]{64}$/.test(id || '')) throw new ServiceError('INVALID_CLIP_ID', 'Clip no válido.', 400);
    try {
      const asset = JSON.parse(await fs.readFile(path.join(this.dir, id + '.json'), 'utf8'));
      if (asset.id !== id || asset.mimeType !== 'video/webm' || !Number.isFinite(asset.durationSeconds) || asset.durationSeconds <= 0 || asset.durationSeconds > MAX_CLIP_SECONDS + 0.05 || !Number.isInteger(asset.bytes) || asset.bytes < 1 || asset.bytes > MAX_CLIP_BYTES) throw new ServiceError('CLIP_INVALID', 'El registro del clip no es válido.', 422);
      return asset;
    } catch (error) { if (error.code === 'ENOENT') throw new ServiceError('CLIP_NOT_FOUND', 'No encontré ese clip.', 404); throw error; }
  }
  async list() {
    const names = await fs.readdir(this.dir), result = [];
    for (const name of names.filter(name => /^[a-f0-9]{64}\.json$/.test(name))) result.push(await this.get(name.slice(0, -5)));
    return result;
  }
  async update({ id, label, aliases } = {}) {
    if ((label !== undefined && (typeof label !== 'string' || !label.trim() || label.length > 100)) ||
        (aliases !== undefined && (!Array.isArray(aliases) || aliases.length > 12 || aliases.some(alias => typeof alias !== 'string' || !alias.trim() || alias.length > 100)))) throw new ServiceError('INVALID_CLIP_METADATA', 'Usa un nombre y hasta 12 alias de como máximo 100 caracteres.', 400);
    return this.exclusive(async () => {
      const asset = await this.get(id);
      if (label !== undefined) asset.label = label.trim();
      if (aliases !== undefined) asset.aliases = [...new Set(aliases.map(alias => alias.trim()))];
      await atomicJson(path.join(this.dir, id + '.json'), asset); return asset;
    });
  }
  async read(id) {
    const asset = await this.get(id), file = path.join(this.dir, id + '.webm');
    if ((await fs.stat(file)).size !== asset.bytes) throw new ServiceError('CLIP_INVALID', 'El clip guardado está incompleto.', 422);
    const data = await fs.readFile(file);
    if (data.length !== asset.bytes || createHash('sha256').update(data).digest('hex') !== id) throw new ServiceError('CLIP_INVALID', 'El clip guardado está incompleto.', 422);
    return { asset, data };
  }
  async close() { this.closing = true; for (const job of this.jobs) job.kill('SIGKILL'); }
}
module.exports = { ClipStore, MAX_CLIP_BYTES };
