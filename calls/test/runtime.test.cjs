// Port técnico de Zhana: procesos efímeros propios, sin navegador.
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { claimLock, identity, LocalRuntime } = require('../service/runtime.cjs');
const { execFile } = require('node:child_process');
const run = require('node:util').promisify(execFile);

test('Service lock excludes a second instance and recovers a dead owner', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-lock-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'service.lock');
  const release = await claimLock(file);
  await assert.rejects(claimLock(file), { code: 'SERVICE_LOCKED' });
  await release();
  await fs.writeFile(file, JSON.stringify({ pid: 99999999, identity: 'dead' }));
  const release2 = await claimLock(file);
  assert.equal(JSON.parse(await fs.readFile(file, 'utf8')).identity, identity(process.pid));
  await release2();
});

test('A runtime that never acquired ownership cannot erase old process metadata', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-runtime-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const runtime = new LocalRuntime(dir), original = '{"recovery":"needed"}';
  await fs.writeFile(runtime.file, original);
  await runtime.stop();
  assert.equal(await fs.readFile(runtime.file, 'utf8'), original);
});

test('Private audio starts without login paths, coexists with another session and cleans up independently', { timeout: 20000 }, async t => {
  for (const program of ['dbus-daemon', 'pulseaudio', 'Xvfb', 'xauth', 'setpriv', 'pactl']) {
    try { await fs.access('/usr/bin/' + program); } catch { t.skip('Audio runtime dependencies unavailable'); return; }
  }
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-audio-runtime-'));
  const firstDir = path.join(dir, 'first'), secondDir = path.join(dir, 'second');
  await fs.mkdir(firstDir); await fs.mkdir(secondDir);
  const missing = path.join(dir, 'missing-login-session');
  const first = new LocalRuntime(firstDir, { baseEnv: { PATH:'/usr/bin:/bin', LANG:'C.UTF-8', XDG_RUNTIME_DIR: missing, PULSE_RUNTIME_PATH: missing, DBUS_SESSION_BUS_ADDRESS: `unix:path=${missing}/bus` } });
  const second = new LocalRuntime(secondDir);
  t.after(async () => { await second.stop(); await first.stop(); await fs.rm(dir, { recursive: true, force: true }); });
  await first.start(); await second.start();
  const sinks = runtime => run('pactl', ['list', 'short', 'sinks'], { env: runtime.env(), timeout: 3000 });
  assert.match((await sinks(first)).stdout, /botsky_calls/);
  assert.match((await sinks(second)).stdout, /botsky_calls/);
  assert.notEqual(first.env().DBUS_SESSION_BUS_ADDRESS, second.env().DBUS_SESSION_BUS_ADDRESS);
  assert.equal((await fs.stat(first.runtimeDir)).mode & 0o777, 0o700);
  assert.equal((await fs.stat(first.pulseRuntimeDir)).mode & 0o777, 0o700);
  const stoppedRecords = [...second.records];
  await second.stop();
  assert.ok(stoppedRecords.every(record => identity(record.pid) === null));
  await assert.rejects(fs.access(second.busSocket), { code: 'ENOENT' });
  await assert.rejects(fs.access(second.pulseSocket), { code: 'ENOENT' });
  assert.match((await sinks(first)).stdout, /botsky_calls/);
});
test('Botsky real private Pulse capture receives a synthetic tone and releases its own processes', {timeout:20000},async t=>{
 const {spawn}=require('node:child_process');const {toneWave}=require('../service/audio-store.cjs');
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'botsky-r9-pcm-'));
 const runtime=new LocalRuntime(dir,{baseEnv:{PATH:'/usr/bin:/bin',LANG:'C.UTF-8'}});
 let capture;
 t.after(async()=>{capture?.kill('SIGKILL');await runtime.stop();await fs.rm(dir,{recursive:true,force:true});});
 await runtime.start();
 const file=path.join(dir,'tone.wav');await fs.writeFile(file,toneWave(1.4));
 capture=spawn('parec',['--raw','--device=botsky_calls.monitor','--format=s16le','--rate=16000','--channels=1','--latency-msec=40'],{env:runtime.env(),stdio:['ignore','pipe','pipe']});
 const chunks=[];let bytes=0;capture.stdout.on('data',chunk=>{bytes+=chunk.length;if(bytes<256000)chunks.push(chunk);});capture.stderr.resume();
 const exit=new Promise(resolve=>capture.once('exit',resolve));
 await run('paplay',['--device=botsky_calls',file],{env:runtime.env(),timeout:8000});
 await new Promise(r=>setTimeout(r,150));capture.kill('SIGTERM');await exit;
 const pcm=Buffer.concat(chunks);let peak=0;for(let i=0;i+1<pcm.length;i+=2)peak=Math.max(peak,Math.abs(pcm.readInt16LE(i)));
 assert.ok(pcm.length>16000);assert.ok(peak>5000,`peak=${peak}`);
 const records=[...runtime.records];await runtime.stop();assert.ok(records.every(record=>identity(record.pid)===null));
 await assert.rejects(fs.access(runtime.pulseSocket),{code:'ENOENT'});
});
