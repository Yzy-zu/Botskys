'use strict';
// Operator-only R10 probe. Requires an exclusively handed-off, offline profile.
// Opens the configured browser, renders own assets, then releases everything.
// Never dials, sends messages, links a new account or starts agenda timers.
const fs = require('node:fs/promises');
const path = require('node:path');
const { startConfigured } = require('../calls/main.cjs');
const { BrowserDriver } = require('../calls/service/browser.cjs');

async function main() {
  const [flag, optionsFile, outputDir] = process.argv.slice(2);
  if (flag !== '--run-with-exclusive-profile' || !path.isAbsolute(optionsFile || '') ||
      !path.isAbsolute(outputDir || '')) throw Error('EXPLICIT_PROBE_CONFIGURATION_REQUIRED');
  const stat = await fs.lstat(optionsFile);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.mode & 0o077 || stat.size > 65536)
    throw Error('PRIVATE_CONFIGURATION_REQUIRED');
  const options = JSON.parse(await fs.readFile(optionsFile, 'utf8'));
  if (options.agendaTimers !== false) throw Error('TIMERS_NOT_ALLOWED_IN_PROBE');
  await fs.mkdir(outputDir, { mode: 0o700 }); // Reject reuse of previous evidence.
  let service, driver, startFailure;
  const result = { startedAt: new Date().toISOString(), callDispatched: false,
    messagesSent: false, humanReception: 'NOT_TESTED', ready: false };
  try {
    service = await startConfigured(options, { driver: config => {
      driver = new BrowserDriver(config);
      const start = driver.start.bind(driver);
      driver.start = async () => {
        try { return await start(); }
        catch (error) { startFailure = { code: error.code || 'BROWSER_START_FAILED',
          name: error.name, detail: String(error.stack || error) }; throw error; }
      };
      return driver;
    } });
    result.ready = true;
    result.accountVerified = await driver.verifyAccount(options.document.account);
    if (!result.accountVerified) throw Error('ACCOUNT_MISMATCH');
    const snapshot = await driver.snapshot();
    result.idle = snapshot.active === false;
    if (!result.idle) throw Error('EXTERNAL_CALL_PRESENT');
    const render = await driver.page.evaluate(async () => {
      const avatar = window.__botskyAvatar.create();
      try {
        await avatar.ready;
        const first = avatar.status();
        const controls = [];
        for (const command of [
          { action: 'background', name: 'studio' },
          { action: 'expression', name: 'happy', duration: 2 },
          { action: 'gesture', name: 'wave', duration: 2 },
          { action: 'blush', name: 'soft', duration: 2 },
        ]) controls.push({ command, status: await avatar.control(command) });
        const pixels = avatar.canvas.getContext('2d').getImageData(0, 0,
          avatar.canvas.width, avatar.canvas.height).data;
        let opaque = 0, colored = 0;
        for (let i = 0; i < pixels.length; i += 4) {
          if (pixels[i + 3]) opaque++;
          if (pixels[i] !== pixels[i + 1] || pixels[i + 1] !== pixels[i + 2]) colored++;
        }
        return { first, controls, last: avatar.status(), opaquePixels: opaque,
          coloredPixels: colored, png: avatar.canvas.toDataURL('image/png').split(',')[1] };
      } finally { avatar.stop(); }
    });
    const png = Buffer.from(render.png, 'base64'); delete render.png;
    await fs.writeFile(path.join(outputDir, 'avatar.png'), png, { mode: 0o600 });
    result.render = render;
    if (!(render.last.frames > render.first.frames && render.coloredPixels > 0 &&
        render.last.ready && render.controls.length === 4)) throw Error('RENDER_ORACLE_FAILED');
    const applied = render.controls.map(control => control.status);
    if (applied[0].background !== 'studio' ||
        applied[1].appliedExpression?.requested !== 'happy' ||
        applied[1].appliedExpression?.applied !== true ||
        applied[2].appliedGesture?.applied !== true ||
        applied[3].appliedBlush?.applied !== true) throw Error('CONTROL_ORACLE_FAILED');
    result.operations = await service.manager.operations.report();
    result.success = true;
  } catch (error) {
    result.success = false;
    result.error = error.code || error.message;
    if (startFailure) await fs.writeFile(path.join(outputDir, 'startup-error.json'),
      JSON.stringify(startFailure, null, 2), { mode: 0o600 });
    process.exitCode = 1;
  } finally {
    try { await service?.close(); result.resourcesClosed = true; }
    catch { result.resourcesClosed = false; process.exitCode = 1; }
    result.finishedAt = new Date().toISOString();
    await fs.writeFile(path.join(outputDir, 'result.json'), JSON.stringify(result, null, 2),
      { mode: 0o600 });
    process.stdout.write(JSON.stringify({ success: result.success, ready: result.ready,
      error: result.error, resourcesClosed: result.resourcesClosed }) + '\n');
  }
}
if (require.main === module) main().catch(() => { process.stderr.write('AV_PROBE_FAILED\n'); process.exitCode = 1; });
