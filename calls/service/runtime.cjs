'use strict';

const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const { ServiceError, sleep } = require('./common.cjs');

function identity(pid) {
  try {
    const stat = fs.readFileSync(`/proc/${pid}/stat`, 'utf8');
    const fields = stat.slice(stat.lastIndexOf(')') + 2).split(' ');
    return fields[0] === 'Z' ? null : `${pid}:${fields[19]}`;
  } catch (error) { if (error.code === 'ENOENT' || error.code === 'ESRCH') return null; throw error; }
}

async function terminate(record) {
  if (!record || identity(record.pid) !== record.identity) return;
  try { process.kill(record.pid, 'SIGTERM'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
  for (let i = 0; i < 20 && identity(record.pid) === record.identity; i++) await sleep(100);
  if (identity(record.pid) === record.identity) {
    try { process.kill(record.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
  }
}

async function claimLock(file) {
  const owner = { pid: process.pid, identity: identity(process.pid) };
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const handle = await fsp.open(file, 'wx', 0o600);
      try { await handle.writeFile(JSON.stringify(owner)); } finally { await handle.close(); }
      return async () => {
        try {
          const current = JSON.parse(await fsp.readFile(file, 'utf8'));
          if (current.identity === owner.identity) await fsp.unlink(file);
        } catch (error) { if (error.code !== 'ENOENT') throw error; }
      };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let previous;
      try { previous = JSON.parse(await fsp.readFile(file, 'utf8')); }
      catch { throw new ServiceError('SERVICE_LOCKED', 'El bloqueo del servicio no está disponible.', 503); }
      if (identity(previous.pid) === previous.identity) throw new ServiceError('SERVICE_LOCKED', 'Ya hay una instancia del servicio.', 503);
      await fsp.unlink(file).catch(error => { if (error.code !== 'ENOENT') throw error; });
    }
  }
  throw new ServiceError('SERVICE_LOCKED', 'No se pudo adquirir el bloqueo del servicio.', 503);
}

class LocalRuntime {
  constructor(privateDir, { baseEnv = process.env } = {}) {
    this.privateDir = privateDir;
    this.baseEnv = baseEnv;
    this.file = path.join(privateDir, 'service-runtime.json');
    this.runtimeDir = path.join(privateDir, 'runtime');
    this.pulseRuntimeDir = path.join(this.runtimeDir, 'pulse');
    this.busSocket = path.join(this.runtimeDir, 'bus');
    this.pulseSocket = path.join(privateDir, 'service-pulse.sock');
    this.records = []; this.children = []; this.stopping = false;
  }
  persist() {
    const temp = this.file + '.tmp';
    fs.writeFileSync(temp, JSON.stringify({ owner: { pid: process.pid, identity: identity(process.pid) }, records: this.records }), { mode: 0o600 });
    fs.renameSync(temp, this.file);
    this.ownsFile = true;
  }
  track(pid, kind) {
    const id = identity(pid);
    if (!id) return;
    this.records = this.records.filter(record => record.pid !== pid && identity(record.pid) === record.identity);
    this.records.push({ pid, identity: id, kind });
    this.persist();
  }
  async start() {
    try {
      const old = JSON.parse(await fsp.readFile(this.file, 'utf8'));
      if (old.owner && identity(old.owner.pid) === old.owner.identity && old.owner.pid !== process.pid) {
        throw new ServiceError('RUNTIME_IN_USE', 'Otro proceso conserva el entorno de llamadas.', 503);
      }
      for (const record of (old.records || []).slice().reverse()) await terminate(record);
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    this.persist();
    await fsp.mkdir(this.pulseRuntimeDir, { recursive: true, mode: 0o700 });
    await fsp.chmod(this.runtimeDir, 0o700);
    await fsp.chmod(this.pulseRuntimeDir, 0o700);
    const log = fs.openSync(path.join(this.privateDir, 'service-runtime.log'), 'a', 0o600);
    try {
      // PulseAudio claims a well-known D-Bus name. A private session keeps it
      // independent of a desktop/login daemon and of /run/user after reboot.
      await fsp.rm(this.busSocket, { force: true });
      const bus = this.spawnOwned('dbus-daemon', ['--session', '--nofork', '--nopidfile', `--address=unix:path=${this.busSocket}`], log, 'bus');
      for (let i = 0; i < 50 && bus.exitCode === null && !fs.existsSync(this.busSocket); i++) await sleep(100);
      if (!fs.existsSync(this.busSocket) || bus.exitCode !== null) throw new ServiceError('AUDIO_BUS_UNAVAILABLE', 'No se pudo preparar la sesión privada de audio.', 503);
      for (let display = 90; display < 150; display++) {
        if (fs.existsSync(`/tmp/.X11-unix/X${display}`) || fs.existsSync(`/tmp/.X${display}-lock`)) continue;
        const authority = path.join(this.privateDir, 'service.Xauthority');
        await fsp.writeFile(authority, '', { mode: 0o600 });
        const auth = spawn('xauth', ['-f', authority], { stdio: ['pipe', 'ignore', log] });
        auth.stdin.end(`add :${display} . ${crypto.randomBytes(16).toString('hex')}\n`);
        await new Promise((resolve, reject) => { auth.once('error', reject); auth.once('exit', code => code === 0 ? resolve() : reject(new Error('xauth failed'))); });
        const server = this.spawnOwned('Xvfb', [`:${display}`, '-screen', '0', '1366x1000x24', '-nolisten', 'tcp', '-auth', authority], log, 'display');
        for (let i = 0; i < 50 && server.exitCode === null && !fs.existsSync(`/tmp/.X11-unix/X${display}`); i++) await sleep(100);
        if (server.exitCode === null && fs.existsSync(`/tmp/.X11-unix/X${display}`)) {
          this.display = `:${display}`; this.authority = authority; break;
        }
        await terminate(this.records.find(r => r.pid === server.pid));
      }
      if (!this.display) throw new Error('No X display available');
      await fsp.rm(this.pulseSocket, { force: true });
      const audio = this.spawnOwned('pulseaudio', ['-n', '--daemonize=no', '--use-pid-file=no', '--exit-idle-time=-1',
        `--load=module-native-protocol-unix socket=${this.pulseSocket} auth-anonymous=1`,
        '--load=module-null-sink sink_name=botsky_calls rate=48000 channels=2'], log, 'audio');
      for (let i = 0; i < 50 && audio.exitCode === null && !fs.existsSync(this.pulseSocket); i++) await sleep(100);
      if (!fs.existsSync(this.pulseSocket) || audio.exitCode !== null) throw new ServiceError('AUDIO_RUNTIME_UNAVAILABLE', 'No se pudo iniciar el servidor privado de audio.', 503);
    } finally { fs.closeSync(log); }
  }
  spawnOwned(program, args, log, kind) {
    // Linux terminates the direct child if the service dies, including SIGKILL.
    const child = spawn('setpriv', ['--pdeathsig', 'TERM', program, ...args], { env: this.env(), stdio: ['ignore', log, log] });
    child.on('error', () => {});
    this.children.push(child);
    if (child.pid) this.track(child.pid, kind);
    child.on('exit', () => { if (!this.stopping) this.onLost?.(kind); });
    return child;
  }
  env() { return { ...this.baseEnv, DISPLAY: this.display, XAUTHORITY: this.authority,
    XDG_RUNTIME_DIR: this.runtimeDir, PULSE_RUNTIME_PATH: this.pulseRuntimeDir,
    DBUS_SESSION_BUS_ADDRESS: `unix:path=${this.busSocket}`, PULSE_SERVER: `unix:${this.pulseSocket}` }; }
  async stop() {
    this.stopping = true;
    if (!this.ownsFile) return;
    for (const record of this.records.slice().reverse()) await terminate(record);
    await fsp.rm(this.file, { force: true });
    await fsp.rm(this.pulseSocket || path.join(this.privateDir, 'service-pulse.sock'), { force: true });
    await fsp.rm(this.busSocket, { force: true });
  }
}

module.exports = { LocalRuntime, claimLock, identity, terminate };
