'use strict';
// Operational composition, adapted from Zhana service/main. Imports have no effects.
const path = require('node:path');
const { createService, ownDirectory } = require('./bootstrap.cjs');
const { LocalRuntime } = require('./service/runtime.cjs');
const { BrowserDriver } = require('./service/browser.cjs');
const { loadAvatarAssets } = require('./service/avatar-assets.cjs');
const { makePolicy } = require('./policy/botsky-policy.cjs');

function validate(options) {
  const allowed = ['projectRoot', 'document', 'token', 'live', 'port', 'executable', 'allowBrowserLaunch', 'agendaTimers'];
  if (!options || Object.keys(options).some(k => !allowed.includes(k)) ||
      typeof options.projectRoot !== 'string' || !path.isAbsolute(options.projectRoot) ||
      !/^[a-f0-9]{64}$/.test(options.token) || !Number.isInteger(options.port) || options.port < 0 || options.port > 65535 ||
      typeof options.executable !== 'string' || !path.isAbsolute(options.executable) ||
      typeof options.agendaTimers !== 'boolean') throw Error('CALLS_CONFIGURATION_INVALID');
  makePolicy(options.document);
  if (!options.live || Object.keys(options.live).sort().join(',') !== 'key,model' ||
      !['key', 'model'].every(k => typeof options.live[k] === 'string' && options.live[k].trim())) throw Error('CALLS_EXPLICIT_LIVE_REQUIRED');
  // Before directories, runtime, assets or browser construction.
  if (options.allowBrowserLaunch !== true) throw Error('BROWSER_NOT_AUTHORIZED');
  return options;
}

async function startConfigured(options, factories = {}) {
  validate(options);
  const privateDir = await ownDirectory(options.projectRoot);
  const runtime = factories.runtime ? factories.runtime(privateDir) : new LocalRuntime(privateDir,
    { baseEnv: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
  // Load only assets belonging to this service. Never discover a foreign profile.
  const avatarAssets = await (factories.assets || loadAvatarAssets)(privateDir);
  const driverOptions = { privateDir, runtime, executable: options.executable, avatarAssets, allowBrowserLaunch: true };
  const driver = factories.driver ? factories.driver(driverOptions) : new BrowserDriver(driverOptions);
  const service = await createService({ ...options, driver, runtime, startRuntime: true });
  if (service.manager.state !== 'ready') {
    await service.close();
    throw Error('CALLS_NOT_READY');
  }
  return service;
}

async function main() {
  if (process.argv.slice(2).join(' ') !== '--run') throw Error('EXPLICIT_RUN_REQUIRED');
  // Secrets go over a bounded private pipe, never argv, global environment or stdout.
  let bytes = 0;
  const chunks = [];
  for await (const chunk of process.stdin) {
    bytes += chunk.length;
    if (bytes > 65536) throw Error('CALLS_CONFIGURATION_INVALID');
    chunks.push(chunk);
  }
  if (!bytes) throw Error('CALLS_CONFIGURATION_REQUIRED');
  const options = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  let service, closing;
  const shutdown = code => {
    if (!closing) closing = (async () => {
      try { await service?.close(); } catch { code = 1; }
      process.exitCode = code;
    })();
    return closing;
  };
  // During boot, wait for owned resources to be assigned before closing them.
  let requestedExit = null;
  const requestStop = code => {
    requestedExit = Math.max(requestedExit ?? 0, code);
    if (service) void shutdown(requestedExit);
  };
  const signal = () => requestStop(0);
  process.on('SIGTERM', signal); process.on('SIGINT', signal);
  process.on('uncaughtException', () => requestStop(1));
  process.on('unhandledRejection', () => requestStop(1));
  try {
    service = await startConfigured(options);
    service.manager.driver.runtime.onLost = () => requestStop(1);
    if (requestedExit !== null) { await shutdown(requestedExit); return; }
    process.stdout.write(JSON.stringify({ ready: true, url: service.url, revision: service.policy.revision }) + '\n');
  } catch (error) {
    await shutdown(1);
    throw error;
  }
}
module.exports = { startConfigured, validate };
if (require.main === module) main().catch(() => {
  process.stderr.write('CALLS_STARTUP_FAILED\n');
  process.exitCode = 1;
});
