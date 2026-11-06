'use strict';
// Explicit composition: importing this file starts no service, process or call.
const fs = require('node:fs/promises');
const path = require('node:path');
const { canonicalPhoneJid } = require('./policy/callDestinations');
const { makePolicy } = require('./policy/botsky-policy.cjs');
const { claimLock } = require('./service/runtime.cjs');
const { Journal } = require('./service/journal.cjs');
const { CallManager } = require('./service/manager.cjs');
const { FeatureControls } = require('./service/feature-controls.cjs');
const { Operations } = require('./service/operations.cjs');
const { CallAgenda } = require('./service/call-agenda.cjs');
const { AudioStore } = require('./service/audio-store.cjs');
const { ClipStore } = require('./service/clip-store.cjs');
const { ClipCommands, CLIP_TOOLS } = require('./service/clip-commands.cjs');
const { AVATAR_TOOLS } = require('./service/avatar-tools.cjs');
const { SpokenControls, SPOKEN_TOOLS } = require('./service/spoken-controls.cjs');
const { LiveController } = require('./service/live-controller.cjs');
const { GeminiLive } = require('./service/gemini-live.cjs');
const { liveKeys } = require('./service/live-credentials.cjs');
const { createServer } = require('./service/http.cjs');

async function ownDirectory(root) {
  root = path.resolve(root);
  const dir = path.join(root, 'private', 'calls');
  for (const target of [root, path.join(root, 'private'), dir]) {
    try {
      const old = await fs.lstat(target);
      if (old.isSymbolicLink() || !old.isDirectory()) throw Error('CALLS_PRIVATE_PATH');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    await fs.mkdir(target, { recursive: true, mode: 0o700 });
    const stat = await fs.lstat(target);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw Error('CALLS_PRIVATE_PATH');
  }
  // Validate owned persistent paths before any legacy component can read them.
  for (const name of ['audio', 'audio/tmp', 'clips', 'clips/tmp', 'avatar', 'profile-brave',
    'journal.json', 'agenda.json', 'features.json', 'service.lock']) {
    try {
      const stat = await fs.lstat(path.join(dir, name));
      if (stat.isSymbolicLink()) throw Error('CALLS_PRIVATE_PATH');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  await fs.chmod(dir, 0o700);
  return dir;
}

function bindAccount(driver, document, privateDir) {
  if (driver.isFixture === true) return;
  if (canonicalPhoneJid(document.account) !== document.account ||
      typeof driver.verifyAccount !== 'function' || driver.privateDir !== privateDir) {
    throw Error('VERIFIED_ACCOUNT_REQUIRED');
  }
  const verify = async () => {
    if (await driver.verifyAccount(document.account) !== true) {
      throw Object.assign(Error('ACCOUNT_MISMATCH'), { code: 'ACCOUNT_MISMATCH', status: 403 });
    }
  };
  const methods = ['start', 'dial', 'end', 'playAudio', 'stopAudio', 'pauseAudio',
    'resumeAudio', 'volume', 'playClip', 'controlClip', 'avatarControl'];
  for (const name of methods) {
    if (typeof driver[name] !== 'function') continue;
    const original = driver[name].bind(driver);
    driver[name] = name === 'start'
      ? async (...args) => { const result = await original(...args); await verify(); return result; }
      : async (...args) => { await verify(); return original(...args); };
  }
}

async function createService({ projectRoot, document, token, driver, runtime, live = {},
  clock, log = () => {}, port = 0, agendaTimers = false } = {}) {
  if (!projectRoot || !driver || !runtime || typeof token !== 'string' ||
      !/^[a-f0-9]{64}$/.test(token) || !Number.isInteger(port) || port < 0 || port > 65535) {
    throw Error('CALLS_EXPLICIT_CONFIGURATION_REQUIRED');
  }
  const policy = makePolicy(document), privateDir = await ownDirectory(projectRoot);
  if (driver.privateDir !== undefined && path.resolve(driver.privateDir) !== privateDir) throw Error('FOREIGN_DRIVER_PATH');
  if (runtime.privateDir !== undefined && path.resolve(runtime.privateDir) !== privateDir) throw Error('FOREIGN_RUNTIME_PATH');
  const releaseLock = await claimLock(path.join(privateDir, 'service.lock'));
  let manager, audioStore, clipStore, server, closed = false;
  async function close() {
    if (closed) return;
    closed = true;
    // Always release all independently owned resources, including after startup failure.
    const errors = [];
    for (const action of [
      () => manager?.stop(), () => audioStore?.close(), () => clipStore?.close(),
      async () => {
        if (!server) return;
        server.closeAllConnections();
        if (server.listening) await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
      },
      () => runtime.privateDir === privateDir ? runtime.stop?.() : undefined,
      releaseLock,
    ]) {
      try { await action(); } catch (error) { errors.push(error); }
    }
    if (errors.length) throw new AggregateError(errors, 'CALLS_CLEANUP_FAILED');
  }
  try {
    bindAccount(driver, document, privateDir);
    const journal = new Journal(path.join(privateDir, 'journal.json'));
    audioStore = new AudioStore(privateDir); await audioStore.init();
    clipStore = new ClipStore(privateDir); await clipStore.init();
    manager = new CallManager({ driver, journal, audioStore, group: policy.group,
      destinationPolicy: policy.destinationPolicy, ...(clock ? { clock } : {}), log });
    manager.policyRevision = policy.revision;
    manager.policyCurrent = () => true; // Document is explicit and immutable for this instance.
    manager.featureStore = new FeatureControls({ file: path.join(privateDir, 'features.json'), base: policy.features, log });
    await manager.featureStore.init();
    manager.clipStore = clipStore; manager.clipCommands = new ClipCommands(manager);
    const spoken = new SpokenControls(manager);
    manager.liveController = new LiveController({
      driver, runtime, log, getKeys: () => liveKeys(live),
      makeSession: options => new GeminiLive({ ...options, model: live.model }),
      onTurn: record => spoken.turnComplete(record), onStop: id => spoken.cancel(id),
      getTools: record => ({
        tools: [...(!record.groupId ? SPOKEN_TOOLS : []), ...(record.video ? [...CLIP_TOOLS, ...AVATAR_TOOLS] : [])],
        onToolCall: (request, { id, name, signal }) => {
          if (name === 'controlar_llamada') return spoken.execute(record, request, { signal });
          if (name === 'controlar_avatar') return manager.avatarCommand({ callId: record.id, ...request, signal });
          if (name === 'controlar_clips') return manager.clipCommands.execute({ callId: record.id, scope: 'voice', key: id, request, signal });
          return Promise.resolve({ success: false });
        },
      }),
      onFailure: async (id, code) => {
        const record = manager.active;
        if (record?.id === id) { record.liveError = { code }; await manager.requestEnd(record, 'live_failed'); }
      },
    });
    // Only a driver explicitly marked as synthetic may replace Live with a fixture.
    if (driver.isFixture === true && driver.liveController) manager.liveController = driver.liveController;
    manager.operations = new Operations({ manager, audioStore, runtime, privateDir });
    manager.incomingPolicy = { enabled: false, allows: () => false };
    await manager.boot();
    manager.agenda = new CallAgenda({ file: path.join(privateDir, 'agenda.json'), manager,
      policy: policy.schedulePolicy, ...(clock ? { now: clock.now } : {}), log });
    await manager.agenda.init();
    if (agendaTimers) manager.agenda.start();
    server = createServer({ manager, driver, audioStore, token, policyRevision: policy.revision,
      allowLinking: false, requireVerifiedTransport: true, log });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
    return { manager, policy, server, url: `http://127.0.0.1:${server.address().port}`, close };
  } catch (error) {
    try { await close(); } catch (cleanup) { throw new AggregateError([error, cleanup], 'CALLS_STARTUP_FAILED'); }
    throw error;
  }
}
module.exports = { createService, ownDirectory };
if (require.main === module) {
  process.stderr.write('El servicio requiere composición explícita y proveedor propio; no se inició nada.\n');
  process.exitCode = 2;
}
