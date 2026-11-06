'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');
const { ServiceError, sleep } = require('./common.cjs');
const { identity, terminate } = require('./runtime.cjs');
const { installVideoBridge } = require('./video-bridge.cjs');
const { installAudioBridge, installNativeMediaHook } = require('./audio-bridge.cjs');
const { installNativeVideoAdapter } = require('./native-video.cjs');
const { dispatchVoiceClick } = require('./voice-click.cjs');
const { readCallSnapshot } = require('./call-snapshot.cjs');
const { resolvePrivatePeer, dispatchPrivateVoiceCall } = require('./private-call.cjs');
const { resolveJoinedGroup } = require('./group-directory.cjs');
const { dispatchGroupVoiceCall } = require('./group-call.cjs');
const { canonicalPhoneJid } = require('../policy/callDestinations');

function bounded(promise, ms, code) {
  let timer;
  const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(new ServiceError(code, 'El navegador no respondió a tiempo.', 503)), ms); });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function ensureOwnedVideoCapture({ allowPending = false } = {}) {
  const adapter = window.__botskyNativeVideoAdapter;
  if (typeof adapter?.ensureOwnedCapture === 'function') return adapter.ensureOwnedCapture({ allowPending });
  throw Error('VIDEO_ADAPTER_UNAVAILABLE');
}

class BrowserDriver {
  constructor({ privateDir, runtime, executable, avatarAssets, allowBrowserLaunch = false }) {
    Object.assign(this, { privateDir, runtime, executable, avatarAssets, allowBrowserLaunch });
    this.profile = path.join(privateDir, 'profile-brave');
    this.context = null; this.page = null; this.closingPromise = null;
    this.linkingEvents = { requestFailed: {}, consoleError: {} };
    this.ready = false;
  }
  async start() {
    if (this.allowBrowserLaunch !== true) throw new ServiceError("BROWSER_NOT_AUTHORIZED", "El navegador requiere encargo posterior explícito.", 403);
    try {
      const lock = await fs.readlink(path.join(this.profile, 'SingletonLock'));
      const pid = Number(lock.slice(lock.lastIndexOf('-') + 1));
      if (pid && identity(pid)) throw new ServiceError('PROFILE_IN_USE', 'El perfil ya está abierto; cierra la consola de prueba.', 503);
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const prefsPath = path.join(this.profile, 'Default', 'Preferences');
    try {
      const prefs = JSON.parse(await fs.readFile(prefsPath, 'utf8'));
      prefs.session = { ...prefs.session, restore_on_startup: 5, startup_urls: [] };
      await fs.writeFile(prefsPath, JSON.stringify(prefs), { mode: 0o600 });
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    await fs.rm(path.join(this.profile, 'Default', 'Sessions'), { recursive: true, force: true });
    const silence = path.join(this.privateDir, 'service-silence.wav');
    const wav = Buffer.alloc(44 + 48000 * 2);
    wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
    wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(48000, 24); wav.writeUInt32LE(96000, 28); wav.writeUInt16LE(2, 32);
    wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(wav.length - 44, 40);
    await fs.writeFile(silence, wav, { mode: 0o600 });
    const context = await chromium.launchPersistentContext(this.profile, {
      executablePath: this.executable, headless: false, env: this.runtime.env(),
      handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false,
      viewport: { width: 1280, height: 900 }, locale: 'es-MX', permissions: ['microphone', 'camera'],
      // Our locally bundled renderer uses a blob worker, outside WhatsApp's
      // own Trusted Types/CSP resource factories.
      bypassCSP: true,
      timeout: 45_000,
      args: ['--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${silence}`, '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--use-gl=angle', '--use-angle=swiftshader-webgl', '--enable-unsafe-swiftshader'],
    });
    this.context = context;
    await context.addInitScript(installNativeMediaHook);
    const lock = await fs.readlink(path.join(this.profile, 'SingletonLock'));
    const pid = Number(lock.slice(lock.lastIndexOf('-') + 1));
    this.processRecord = { pid, identity: identity(pid) };
    this.runtime.track(pid, 'browser');
    const lost = reason => {
      if (this.context === context && this.ready) {
        this.ready = false;
        Promise.resolve(this.onLost?.(reason)).catch(() => {});
      }
    };
    context.browser().on('disconnected', () => lost('browser_disconnected'));
    this.page = context.pages()[0] || await context.newPage();
    const page = this.page;
    for (const extra of context.pages()) if (extra !== page) await extra.close();
    page.on('requestfailed', request => {
      if (this.ready) return;
      try {
        const url = new URL(request.url());
        if (!(url.hostname === 'whatsapp.com' || url.hostname.endsWith('.whatsapp.com') || url.hostname === 'whatsapp.net' || url.hostname.endsWith('.whatsapp.net'))) return;
        const kind = url.hostname === 'web.whatsapp.com' ? 'web' : 'whatsapp';
        const resource = ['document', 'websocket', 'xhr', 'fetch'].includes(request.resourceType()) ? request.resourceType() : 'other';
        const error = request.failure()?.errorText || '';
        const reason = /ERR_(?:NAME_NOT_RESOLVED|INTERNET_DISCONNECTED|CONNECTION_RESET|CONNECTION_CLOSED|TIMED_OUT)/.exec(error)?.[0] || 'OTHER';
        const key = `${kind}:${resource}:${reason}`;
        this.linkingEvents.requestFailed[key] = Math.min(100, (this.linkingEvents.requestFailed[key] || 0) + 1);
      } catch { /* Ignore malformed URLs; never store request data. */ }
    });
    page.on('console', message => {
      if (this.ready || message.type() !== 'error') return;
      const reason = /ERR_(?:NAME_NOT_RESOLVED|INTERNET_DISCONNECTED|CONNECTION_RESET|CONNECTION_CLOSED|TIMED_OUT)/.exec(message.text())?.[0];
      if (reason) this.linkingEvents.consoleError[reason] = Math.min(100, (this.linkingEvents.consoleError[reason] || 0) + 1);
    });
    page.on('close', () => lost('page_closed'));
    page.on('crash', () => lost('page_crashed'));
    page.on('framenavigated', frame => { if (frame === page.mainFrame()) lost('page_reloaded'); });
    page.setDefaultTimeout(7000);
    await page.goto('https://web.whatsapp.com/', { waitUntil: 'domcontentloaded', timeout: 45_000 });
    for (let i = 0; i < 180; i++) {
      if (await page.locator('#pane-side').isVisible()) break;
      if (await page.locator('[data-ref] canvas').count()) throw new ServiceError('NEEDS_LINK', 'La cuenta necesita vincularse de nuevo.', 503);
      if (i === 179) throw new ServiceError('LOGIN_TIMEOUT', 'WhatsApp no terminó de cargar.', 503);
      await sleep(250);
    }
    await this.initialize();
  }
  async completeLink() {
    if (!this.context || !this.page || this.page.isClosed()) throw new ServiceError('BROWSER_LOST', 'Se cerró la página de vinculación.', 503);
    if (!await this.page.locator('#pane-side').isVisible()) return false;
    await this.initialize();
    return true;
  }
  async initialize() {
    const page = this.page;
    // Close a known introductory dialog, without touching notification settings.
    const intro = page.getByRole('dialog').getByRole('button', { name: 'Continuar', exact: true });
    if (await intro.count() === 1 && await intro.isVisible()) await intro.click();
    if (!await page.evaluate(() => !!window.WPP)) await page.evaluate(await fs.readFile(require.resolve('@wppconnect/wa-js'), 'utf8'));
    await page.waitForFunction(() => window.WPP?.isReady, undefined, { timeout: 30_000 });
    await bounded(page.evaluate(async () => {
      await window.WPP.call.enableCallInterface();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      stream.getTracks().forEach(track => track.stop());
      const devices = await navigator.mediaDevices.enumerateDevices();
      if (!devices.some(d => d.kind === 'audiooutput')) throw new Error('Missing audio output');
    }), 30_000, 'VOIP_INIT_TIMEOUT');
    if (this.avatarAssets) {
      await page.evaluate(this.avatarAssets.script);
      await page.evaluate(base64 => window.__botskyAvatar.prepare(base64), this.avatarAssets.base64);
      await bounded(page.evaluate(async () => {
        const avatar = window.__botskyAvatar.create();
        try { await avatar.ready; } finally { avatar.stop(); }
      }), 30000, 'AVATAR_INIT_TIMEOUT');
    }
    await page.evaluate(installVideoBridge);
    await page.evaluate(installAudioBridge);
    if (this.avatarAssets && !await page.evaluate(installNativeVideoAdapter)) throw new ServiceError('VIDEO_ADAPTER_UNAVAILABLE', 'No se pudo preparar el formato de video de WhatsApp.', 503);
    await page.evaluate(() => {
      if (window.__botskyIncomingObserverInstalled) return;
      window.__botskyIncomingObserverInstalled = true;
      window.WPP.on('call.incoming_call', call => {
        const jid = value => value?._serialized || value?.toString?.() || null;
        window.__botskyIncoming = { id: String(call.id), sender: jid(call.sender) };
      });
    });
    this.ready = true;
  }
  async verifyAccount(expected) {
    if (!this.ready || !this.page || typeof expected !== 'string') return false;
    return bounded(this.page.evaluate(expected => {
      const normalize = value => String(value?._serialized || value?.toString?.() || '').replace(/:\d+@/, '@').replace(/@c\.us$/, '@s.whatsapp.net').replace(/^521(\d{10})@/, '52$1@');
      const actual = window.WPP?.conn?.getMyUserId?.();
      return !!actual && normalize(actual) === expected;
    }, expected), 5000, 'ACCOUNT_CHECK_TIMEOUT');
  }
  async snapshot() {
    if (!this.ready || !this.page) throw new ServiceError('NOT_READY', 'El navegador no está listo.', 503);
    try { return await bounded(this.page.evaluate(readCallSnapshot), 5000, 'SNAPSHOT_TIMEOUT'); }
    catch (error) {
      if (error.code === 'SNAPSHOT_TIMEOUT') {
        const probe = await bounded(this.page.evaluate(() => ({ responsive: true, stage: window.__botskySnapshotProgress?.stage || 'not_started' })), 500, 'PROBE_TIMEOUT').catch(() => ({ responsive: false }));
        process.stderr.write(JSON.stringify({ event: 'snapshot_timeout_probe', ...probe }) + '\n');
      }
      throw error;
    }
  }
  async recoverSnapshot() {
    // Read the existing page before any destructive browser restart. Never
    // navigate, arm a microphone or initiate a call during this probe.
    if (!this.page || this.page.isClosed()) throw new ServiceError('BROWSER_LOST', 'No queda una página recuperable.', 503);
    const snapshot = await bounded(this.page.evaluate(readCallSnapshot), 3000, 'SNAPSHOT_TIMEOUT');
    this.ready = true;
    return snapshot;
  }
  async inspectCallRuntime({ lookupOwner = false, ownerJid, accountJid, groupSources = false, videoSources = false } = {}) {
    if (!this.ready || !this.page) throw new ServiceError('NOT_READY', 'El navegador no está listo.', 503);
    const snapshot = await this.snapshot();
    const account = accountJid ? await bounded(this.page.evaluate(expected => {
      const normalize = value => String(value?._serialized || value?.toString?.() || '').replace(/:\d+@/, '@').replace(/@c\.us$/, '@s.whatsapp.net').replace(/^521(\d{10})@/, '52$1@');
      const actual = window.WPP?.conn?.getMyUserId?.();
      return { known: !!actual, matches: !!actual && normalize(actual) === expected };
    }, accountJid), 5000, 'ACCOUNT_CHECK_TIMEOUT') : { known: false, matches: false };
    const videoRuntime = videoSources ? await this.inspectVideoRuntime() : null;
    let ownerLookup;
    if (lookupOwner && ownerJid) ownerLookup = await bounded(this.page.evaluate(async target => {
      const normalize = value => String(value?._serialized || value?.toString?.() || '').replace(/:\d+@/, '@').replace(/@c\.us$/, '@s.whatsapp.net').replace(/^521(\d{10})@/, '52$1@');
      const summarize = entry => {
        const peer = entry?.lid || entry?.wid;
        let self = null;
        try { self = peer ? window.require('WAWebUserPrefsMeUser').isMeAccount(peer) : null; } catch {}
        return { exists: !!entry, keys: entry ? Object.keys(entry) : [], widType: typeof entry?.wid,
          widServer: String(entry?.wid?._serialized || '').split('@')[1] || null,
          lidServer: String(entry?.lid?._serialized || '').split('@')[1] || null,
          phoneMatches: !!entry?.wid && normalize(entry.wid) === target, selfCheckType: typeof self, isSelf: self === true };
      };
      const primary = summarize(await window.WPP.contact.queryExists(target.replace(/@s\.whatsapp\.net$/, '@c.us')));
      const legacy = /^52\d{10}@/.test(target) ? summarize(await window.WPP.contact.queryExists(target.replace(/^52/, '521').replace(/@s\.whatsapp\.net$/, '@c.us'))) : null;
      return { primary, legacy };
    }, ownerJid), 15000, 'PRIVATE_LOOKUP_TIMEOUT');
    if (ownerLookup) {
      try { ownerLookup.verification = await bounded(this.page.evaluate(resolvePrivatePeer, { targetJid: ownerJid, verifyOnly: true }), 15000, 'PRIVATE_LOOKUP_TIMEOUT'); }
      catch (error) { ownerLookup.verification = { verified: false, code: error.code || 'PRIVATE_TARGET_UNVERIFIED' }; }
    }
    let groupRuntime;
    if (groupSources) groupRuntime = await bounded(this.page.evaluate(() => {
      const modules = window.require('__debug').modulesMap;
      const names = Object.keys(modules).filter(name => /^WAWeb/.test(name) && /VoipStart|GroupCall.*(?:Utils|Action)|Voip.*Group.*Start/.test(name));
      const sources = {};
      for (const name of ['WAWebVoipStartCall', 'WAWebOutgoingGroupCallUtils', 'WAWebVoipLobbyUtils', 'WAWebVoipStackInterface', ...names]) {
        if (sources[name]) continue;
        try {
          const exports = modules[name]?.exports || window.require(name);
          const code = {};
          if (typeof exports === 'function') code.default = String(exports).slice(0, 100000);
          else for (const key of Object.keys(exports || {})) if (typeof exports[key] === 'function') code[key] = String(exports[key]).slice(0, 100000);
          if (typeof modules[name]?.factory === 'function') code.factory = String(modules[name].factory).slice(0, 150000);
          sources[name] = code;
        } catch {}
      }
      return { names, sources };
    }), 5000, 'DIAGNOSTICS_TIMEOUT');
    if (groupRuntime) {
      const session = await this.page.context().newCDPSession(this.page);
      try {
        await session.send('Debugger.enable');
        const value = await session.send('Runtime.evaluate', { expression: 'window.require("WAWebVoipStartCall").startWAWebVoipGroupCallFromChat', objectGroup: 'botsky-static-inspection' });
        const properties = await session.send('Runtime.getProperties', { objectId: value.result.objectId, ownProperties: false });
        const location = properties.internalProperties?.find(item => item.name === '[[FunctionLocation]]')?.value?.value;
        if (location) {
          const { scriptSource } = await session.send('Debugger.getScriptSource', { scriptId: location.scriptId });
          const lines = scriptSource.split('\n');
          const offset = lines.slice(0, location.lineNumber).reduce((size, line) => size + line.length + 1, 0) + location.columnNumber;
          const start = Math.max(0, scriptSource.lastIndexOf('__d(', offset));
          const end = scriptSource.indexOf('__d(', offset + 1);
          groupRuntime.startCallModule = scriptSource.slice(start, end < 0 ? start + 350000 : Math.min(end, start + 350000));
        }
      } finally {
        await session.send('Runtime.releaseObjectGroup', { objectGroup: 'botsky-static-inspection' }).catch(() => {});
        await session.send('Debugger.disable').catch(() => {});
        await session.detach();
      }
    }
    return { version: snapshot.runtimeVersion, account, native: { present: snapshot.active,
      state: snapshot.state, isGroup: snapshot.isGroup, hasGroupContext: !!snapshot.groupId },
      audience: snapshot.audience, privateCapabilities: snapshot.privateCapabilities, ...(ownerLookup ? { ownerLookup } : {}), ...(groupRuntime ? { groupRuntime } : {}), ...(videoRuntime ? { videoRuntime } : {}) };
  }
  async inspectVideoRuntime() {
    const data = await bounded(this.page.evaluate(() => {
      const names = [...new Set([...Object.keys(window.require('__debug').modulesMap).filter(name => /^WA/.test(name) && /(?:Voip|Call).*(?:Video|Camera|Capture|MediaEnums|WebCodecs|Encoder)|(?:Video|Camera|Capture).*Voip/.test(name)).slice(0, 90), 'WAWebVoipStackInterfaceImpl'])];
      const exports = {}, sources = {};
      for (const name of [...names, 'WAWebVoipStackInterface']) {
        try {
          const module = window.require(name);
          exports[name] = Object.keys(module || {}).filter(key => typeof module[key] === 'function');
          sources[name] = Object.fromEntries(exports[name].map(key => [key, String(module[key]).slice(0, 50000)]));
        } catch {}
      }
      let stack = window.require('WAWebVoipStackInterface').getCachedVoipStackInterface();
      const stackSources = {};
      for (const key of ['acceptCall', 'setCallVideoMute']) if (typeof stack?.[key] === 'function') stackSources[key] = String(stack[key]);
      const capture = window.require('WAWebVoipVideoCameraCapture').WAWebVoipVideoCameraCapture;
      const camera = { state: capture.captureInitState, params: capture.getOpenCaptureParams?.(),
        tracks: capture.getLastCapturedStream?.()?.getVideoTracks().map(track => ({ label: track.label, state: track.readyState, settings: { width: track.getSettings().width, height: track.getSettings().height } })),
        nativeHook: !!window.__botskyNativeMediaInstalled, adapter: !!window.__botskyNativeVideoAdapter,
        virtualDriver: window.require('WAWebABProps').getABPropConfigValue('enable_web_voip_virtual_video_capture_driver') };
      const methods = new Set();
      for (let depth = 0; stack && depth < 4; depth++, stack = Object.getPrototypeOf(stack)) for (const key of Object.getOwnPropertyNames(stack)) if (/video|camera|capture|orientation/i.test(key)) methods.add(key);
      return { names, exports, sources, stackMethods: [...methods], stackSources, camera, modules: {} };
    }), 5000, 'DIAGNOSTICS_TIMEOUT');
    const session = await this.context.newCDPSession(this.page);
    try {
      await session.send('Debugger.enable');
      const scripts = new Map();
      for (const [name, keys] of Object.entries(data.exports)) {
        if (!keys.length) continue;
        const ref = await session.send('Runtime.evaluate', { expression: `window.require(${JSON.stringify(name)})[${JSON.stringify(keys[0])}]`, objectGroup: 'botsky-video-inspection' });
        if (!ref.result.objectId) continue;
        const properties = await session.send('Runtime.getProperties', { objectId: ref.result.objectId, ownProperties: false });
        const location = properties.internalProperties?.find(item => item.name === '[[FunctionLocation]]')?.value?.value;
        if (!location) continue;
        if (!scripts.has(location.scriptId)) scripts.set(location.scriptId, (await session.send('Debugger.getScriptSource', { scriptId: location.scriptId })).scriptSource);
        const source = scripts.get(location.scriptId), lines = source.split('\n');
        const offset = lines.slice(0, location.lineNumber).reduce((size, line) => size + line.length + 1, 0) + location.columnNumber;
        const start = Math.max(0, source.lastIndexOf('__d(', offset)), end = source.indexOf('__d(', offset + 1);
        data.modules[name] = source.slice(start, end < 0 ? start + 160000 : Math.min(end, start + 160000));
      }
      // Exports can re-export an imported helper or a singleton instead of a
      // constructor. Match the registration by name in the collected scripts.
      for (const name of data.names) for (const source of scripts.values()) {
        const start = source.indexOf(`__d(${JSON.stringify(name)},`);
        if (start < 0) continue;
        const end = source.indexOf('__d(', start + 4);
        data.modules[name] = source.slice(start, end < 0 ? start + 160000 : Math.min(end, start + 160000));
        break;
      }
    } finally {
      await session.send('Runtime.releaseObjectGroup', { objectGroup: 'botsky-video-inspection' }).catch(() => {});
      await session.send('Debugger.disable').catch(() => {}); await session.detach();
    }
    return data;
  }
  async resolveGroup(query) {
    const result = await bounded(this.page.evaluate(resolveJoinedGroup, query), 15000, 'GROUP_DIRECTORY_UNAVAILABLE');
    if (result.error === 'ambiguous') throw new ServiceError('CALL_TARGET_CLARIFICATION', 'Hay varios grupos con ese nombre. Dime un nombre más preciso.', 409);
    if (result.error === 'not_found') throw new ServiceError('CALL_TARGET_CLARIFICATION', 'No encontré un grupo con ese nombre donde Zhana sea miembro. Dime su nombre completo.', 404);
    if (!result.group) throw new ServiceError('GROUP_DIRECTORY_UNAVAILABLE', 'No pude verificar los grupos de Zhana ahora. Inténtalo de nuevo en un momento.', 503);
    return result.group;
  }
  async dial(group, { cancelled, audioToken, preparedAudio, recoveryNativeId, video = false }) {
    if (group.kind === 'private') return this.dialPrivate(group, { cancelled, audioToken, preparedAudio, recoveryNativeId, video });
    let dispatched = false;
    let stage = 'preflight';
    const check = () => { if (cancelled()) throw new ServiceError('CANCELLED', 'Se canceló antes de marcar.'); };
    try {
      check();
      if ((await this.snapshot()).active) throw new ServiceError('CALL_BUSY', 'WhatsApp ya tiene una llamada activa.');
      stage = 'open_group';
      const selected = await bounded(this.page.evaluate(async id => {
        await window.WPP.chat.openChatBottom(id);
        const chat = window.WPP.chat.getActiveChat();
        const participants = await window.WPP.group.getParticipants(id);
        return { id: chat?.id?._serialized || chat?.id?.toString(), count: participants.length, member: chat?.groupMetadata?.participants?.iAmMember?.() === true, community: !!(chat?.isParentGroup || chat?.groupMetadata?.isParentGroup) };
      }, group.id), 10_000, 'OPEN_GROUP_TIMEOUT');
      if (selected.id !== group.id || (selected.count < (group.minParticipants || 2) || selected.count > (group.maxParticipants || 2))) throw new ServiceError('GROUP_MISMATCH', 'El grupo solicitado no coincide o su tamaño no permite iniciar esta llamada.');
      if (group.requireMembership && (!selected.member || selected.community)) throw new ServiceError('GROUP_NOT_JOINED', 'Zhana ya no es miembro de ese grupo o ese chat no admite esta llamada.', 403);
      check();
      stage = 'arm_audio';
      await bounded(this.page.evaluate(({ token, video }) => window.__botskyAudio.arm(token, { video }), { token: audioToken, video }), video ? 30000 : 5000, 'AUDIO_ARM_TIMEOUT');
      this.preloadedAudioId = null;
      if (preparedAudio) {
        stage = 'preload_audio';
        await this.preloadAudio(audioToken, preparedAudio.asset.id, preparedAudio.data);
        check();
      }
      stage = video ? 'group_video_offer' : 'group_voice_offer';
      check(); dispatched = true;
      await this.dispatchGroupCall(group, audioToken, recoveryNativeId, video);
      stage = 'observe_call';
      for (let i = 0; i < 40; i++) {
        const snapshot = await this.snapshot();
        if (snapshot.active) {
          if (!snapshot.outgoing || !snapshot.isGroup || snapshot.groupId !== group.id || snapshot.isVideo !== video) throw new ServiceError('CALL_CHANGED', 'WhatsApp no conservó el grupo solicitado; no se reproducirá el encargo en otra llamada.');
          stage = 'bind_audio';
          await this.page.evaluate(({ token, id }) => window.__botskyAudio.bind(token, id), { token: audioToken, id: snapshot.id });
          let boundSnapshot = snapshot;
          if (video) {
            await bounded(this.page.evaluate(ensureOwnedVideoCapture), 10_000, 'VIDEO_CAPTURE_TIMEOUT');
            boundSnapshot = await this.snapshot();
            if (!boundSnapshot.active || boundSnapshot.id !== snapshot.id || !boundSnapshot.outgoing || !boundSnapshot.isGroup || boundSnapshot.groupId !== group.id || !boundSnapshot.isVideo) throw new ServiceError('CALL_CHANGED', 'La llamada cambió durante la captura de video.');
          }
          if (cancelled()) {
            await this.end(boundSnapshot.id);
            throw new ServiceError('CANCELLED', 'Se canceló después de marcar; se colgó la llamada de este intento.');
          }
          return boundSnapshot;
        }
        await sleep(250);
      }
      throw new ServiceError('DIAL_UNCONFIRMED', 'No se pudo confirmar el inicio de la llamada.');
    } catch (error) {
      const controls = await bounded(this.page.evaluate(() => Array.from(document.querySelectorAll('[role="menuitem"], [role="dialog"]')).filter(el => el.getBoundingClientRect().width).map(el => (el.innerText || el.getAttribute('aria-label') || '').slice(0, 500))), 2000, 'DIAGNOSTIC_TIMEOUT').catch(() => []);
      await fs.writeFile(path.join(this.privateDir, 'last-dial-error.json'), JSON.stringify({ stage, message: error.message, controls, time: Date.now() }), { mode: 0o600 }).catch(() => {});
      await this.disarmAudio(audioToken); error.dispatched = dispatched;
      if (!error.code) error.code = ['CALL_CHANGED', 'CANCELLED', 'GROUP_MISMATCH', 'GROUP_CALL_UNAVAILABLE', 'GROUP_NOT_JOINED'].find(code => error.message.includes(code)) || `DIAL_${stage.toUpperCase()}`;
      throw error;
    }
  }
  async dispatchGroupCall(group, token, recoveryNativeId, video = false) {
    return bounded(this.page.evaluate(dispatchGroupVoiceCall, { groupId: group.id, token, video,
      minParticipants: group.minParticipants || 2, maxParticipants: group.maxParticipants || 2, requireMembership: group.requireMembership === true, recoveryNativeId }), 30000, 'GROUP_OFFER_TIMEOUT');
  }
  async dialPrivate(target, { cancelled, audioToken, preparedAudio, recoveryNativeId, video = false }) {
    let dispatched = false;
    const check = () => { if (cancelled()) throw new ServiceError('CANCELLED', 'Se canceló antes de marcar.'); };
    try {
      check();
      if (canonicalPhoneJid(target.id) !== target.id) throw new ServiceError('PRIVATE_TARGET_UNVERIFIED', 'El número no es válido.');
      const before = await this.snapshot();
      if (before.active) throw new ServiceError('CALL_BUSY', 'WhatsApp ya tiene una llamada activa.');
      await bounded(this.page.evaluate(({ token, video }) => window.__botskyAudio.arm(token, { video }), { token: audioToken, video }), video ? 30000 : 5000, 'AUDIO_ARM_TIMEOUT');
      this.preloadedAudioId = null;
      if (preparedAudio) await this.preloadAudio(audioToken, preparedAudio.asset.id, preparedAudio.data);
      const params = { targetJid: target.id, token: audioToken, recoveryNativeId, video };
      const resolved = await bounded(this.page.evaluate(resolvePrivatePeer, params), 15000, 'PRIVATE_LOOKUP_TIMEOUT');
      check();
      dispatched = true; // Ambiguous dispatch is never retried.
      await bounded(this.page.evaluate(dispatchPrivateVoiceCall, params), 15000, 'PRIVATE_OFFER_TIMEOUT');
      for (let i = 0; i < 40; i++) {
        const snapshot = await this.snapshot();
        const samePeer = snapshot.peerJid?.replace(/:\d+@/, '@').replace(/@c\.us$/, '@s.whatsapp.net') === resolved.peerId ||
          canonicalPhoneJid(snapshot.peerPhone || snapshot.peerJid) === target.id;
        if (!snapshot.active && snapshot.id && snapshot.id !== before.id && snapshot.outgoing && !snapshot.isGroup && snapshot.isVideo === video && samePeer) {
          if (cancelled()) throw new ServiceError('CANCELLED', 'Se canceló después de marcar; la llamada ya había terminado.');
          return snapshot;
        }
        if (snapshot.active) {
          if (!snapshot.outgoing || snapshot.isGroup || snapshot.isVideo !== video || snapshot.groupId || !samePeer) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada observada.');
          await this.page.evaluate(({ token, id, video }) => {
            const call = window.require('WAWebCallCollection').activeCall;
            if (!call || String(call.id) !== id || !call.outgoing || call.isGroup || !!call.isVideo !== video || call.groupJid) throw Error('CALL_CHANGED');
            window.__botskyAudio.bind(token, id);
          }, { token: audioToken, id: snapshot.id, video });
          let boundSnapshot = snapshot;
          if (video) {
            await bounded(this.page.evaluate(ensureOwnedVideoCapture), 10_000, 'VIDEO_CAPTURE_TIMEOUT');
            boundSnapshot = await this.snapshot();
            const boundPeer = boundSnapshot.peerJid?.replace(/:\d+@/, '@').replace(/@c\.us$/, '@s.whatsapp.net') === resolved.peerId ||
              canonicalPhoneJid(boundSnapshot.peerPhone || boundSnapshot.peerJid) === target.id;
            if (!boundSnapshot.active || boundSnapshot.id !== snapshot.id || !boundSnapshot.outgoing || boundSnapshot.isGroup || !boundSnapshot.isVideo || !boundPeer) throw new ServiceError('CALL_CHANGED', 'La llamada cambió durante la captura de video.');
          }
          if (cancelled()) {
            await this.end(boundSnapshot.id);
            throw new ServiceError('CANCELLED', 'Se canceló después de marcar; se colgó la llamada de este intento.');
          }
          return boundSnapshot;
        }
        await sleep(250);
      }
      throw new ServiceError('DIAL_UNCONFIRMED', 'No se confirmó el inicio de la llamada privada.');
    } catch (error) {
      await this.disarmAudio(audioToken); error.dispatched = dispatched;
      if (!error.code) error.code = ['CALL_CHANGED', 'CANCELLED', 'PRIVATE_CALL_UNAVAILABLE', 'PRIVATE_TARGET_UNVERIFIED'].find(code => error.message.includes(code)) || 'PRIVATE_DIAL_FAILED';
      throw error;
    }
  }
  async activateVoiceMenu(groupId, token, check, markDispatched) {
    const until = Date.now() + 7000;
    let openings = 0, nextOpen = 0;
    while (Date.now() < until) {
      check();
      // The page may dispatch before the response is lost. Only an explicit
      // pre-dispatch result permits reopening/retrying the menu.
      markDispatched(true);
      const result = await bounded(this.page.evaluate(dispatchVoiceClick, { groupId, token, openMenu: Date.now() >= nextOpen && openings < 3 }), 2000, 'VOICE_CLICK_TIMEOUT');
      if (result.state === 'dispatched') return;
      markDispatched(false);
      if (result.state === 'group_changed') throw new ServiceError('GROUP_MISMATCH', 'Cambió el chat abierto antes de marcar.');
      if (result.state === 'owner_changed') throw new ServiceError('CANCELLED', 'Se canceló el audio antes de marcar.');
      if (result.state === 'call_busy') throw new ServiceError('CALL_BUSY', 'Apareció otra llamada antes de marcar.');
      if (!['menu_unavailable', 'menu_opened'].includes(result.state)) throw new ServiceError('VOICE_MENU_INVALID', 'No se pudo identificar el menú de llamada.');
      check();
      if (result.state === 'menu_opened') { openings++; nextOpen = Date.now() + 1500; }
      await sleep(100);
    }
    throw new ServiceError('VOICE_MENU_UNAVAILABLE', 'No apareció un botón de llamada disponible. No se marcó.');
  }
  async disarmAudio(token) {
    if (!this.page) { await this.closingPromise; return { released: true }; }
    try {
      return await bounded(this.page.evaluate(token => {
        const audio = window.__botskyAudio;
        if (!audio) return { released: true };
        if (audio.token && audio.token !== token) return { released: true, ownerChanged: true };
        audio.disarm(token);
        const status = audio.status();
        return { released: !status.armed && status.liveTracks === 0 && !(status.video?.liveTracks > 0) };
      }, token), 3000, 'AUDIO_CLEANUP_TIMEOUT');
    } catch { return { released: false }; }
  }
  async answer(incoming, { audioToken, cancelled }) {
    let dispatched = false;
    const video = incoming.isVideo === true;
    const check = () => { if (cancelled()) throw new ServiceError('CANCELLED', 'Se canceló antes de contestar.'); };
    try {
      check();
      const current = await this.snapshot();
      if (!current.active || current.id !== incoming.id || current.outgoing || !!current.isVideo !== video || current.isGroup || current.groupId || current.peerJid !== incoming.peerJid || ![3, 'INCOMING_RING'].includes(current.state)) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada entrante.');
      await bounded(this.page.evaluate(async ({ token, id, peer, video }) => {
        const call = window.require('WAWebCallCollection').activeCall;
        const jid = call?.peerJid?._serialized || call?.peerJid?.toString();
        if (!call || String(call.id) !== id || call.outgoing || !!call.isVideo !== video || call.isGroup || call.groupJid || jid !== peer || ![3, 'INCOMING_RING'].includes(call.getState?.())) throw new Error('CALL_CHANGED');
        await window.__botskyAudio.arm(token, { incomingNativeId: id, video });
        // Incoming UI can prewarm the physical/fake camera while still ringing,
        // before this call owns media. It must not reuse that cached stream.
        if (video) {
          await window.require('WAWebVoipCameraPrewarm').cleanupPrewarmedCamera();
          await window.__botskyNativeVideoAdapter?.ensureOwnedCapture?.({ allowPending: true });
        }
      }, { token: audioToken, id: incoming.id, peer: incoming.peerJid, video }), video ? 30000 : 5000, 'INCOMING_AUDIO_TIMEOUT');
      check(); dispatched = true;
      await bounded(this.page.evaluate(async ({ token, id, peer, video }) => {
        const call = window.require('WAWebCallCollection').activeCall;
        const jid = call?.peerJid?._serialized || call?.peerJid?.toString();
        if (!call || String(call.id) !== id || call.outgoing || !!call.isVideo !== video || call.isGroup || call.groupJid || jid !== peer || ![3, 'INCOMING_RING'].includes(call.getState?.()) || window.__botskyAudio.token !== token) throw new Error('CALL_CHANGED');
        if (window.__botskyIncomingAccept?.id === id) return;
        window.__botskyIncomingAccept = { id, token };
        const accepted = await window.WPP.call.accept(id);
        if (accepted === false) throw new Error('ACCEPT_UNCONFIRMED');
      }, { token: audioToken, id: incoming.id, peer: incoming.peerJid, video }), 10000, 'INCOMING_ACCEPT_TIMEOUT');
      if (video) await bounded(this.page.evaluate(ensureOwnedVideoCapture), 10_000, 'VIDEO_CAPTURE_TIMEOUT');
      const result = await this.snapshot();
      if (!result.active || result.id !== incoming.id || result.outgoing || !!result.isVideo !== video || result.isGroup || result.groupId || result.peerJid !== incoming.peerJid) throw new ServiceError('CALL_CHANGED', 'Terminó o cambió la llamada al contestar.');
      await this.page.evaluate(({ token, id }) => window.__botskyAudio.bind(token, id), { token: audioToken, id: incoming.id });
      return result;
    } catch (error) {
      await this.disarmAudio(audioToken); error.dispatched = dispatched;
      if (!error.code) error.code = error.message.includes('CALL_CHANGED') ? 'CALL_CHANGED' : 'INCOMING_ACCEPT_FAILED';
      throw error;
    }
  }
  async preloadAudio(token, audioId, data) {
    await bounded(this.page.evaluate(args => window.__botskyAudio.preload(args), { token, audioId, base64: data.toString('base64') }), 45000, 'AUDIO_PRELOAD_TIMEOUT');
    this.preloadedAudioId = audioId;
  }
  async playAudio(nativeId, id, data, volume, audioId, offsetSeconds = 0) {
    try {
      const payload = { nativeId, id, audioId, volume, offsetSeconds, ...(audioId && this.preloadedAudioId === audioId ? {} : { base64: data.toString('base64') }) };
      return await bounded(this.page.evaluate(args => window.__botskyAudio.play(args), payload), 45000, 'AUDIO_PLAY_TIMEOUT');
    } catch (error) {
      if (error instanceof ServiceError) throw error;
      const code = ['AUDIO_BUSY', 'AUDIO_CALL_CHANGED', 'AUDIO_MIC_NOT_CAPTURED'].find(code => error.message.includes(code));
      throw new ServiceError(code || 'AUDIO_PLAY_FAILED', code ? 'El audio no se puede reproducir en esta llamada o ya hay otro activo.' : 'El navegador no pudo reproducir el audio.', 409);
    }
  }
  async pauseAudio(nativeId, id, offsetSeconds) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.pause(args), { nativeId, id, offsetSeconds }), 3000, 'AUDIO_PAUSE_TIMEOUT');
  }
  async resumeAudio(nativeId, id, offsetSeconds) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.resume(args), { nativeId, id, offsetSeconds }), 5000, 'AUDIO_RESUME_TIMEOUT');
  }
  async stopAudio(nativeId, playbackId) {
    return bounded(this.page.evaluate(({ id, playbackId }) => {
      const audio = window.__botskyAudio;
      if (!audio?.token) return;
      if (audio.nativeId !== id) throw new Error('AUDIO_CALL_CHANGED');
      if (playbackId && audio.playback?.id !== playbackId) return;
      audio.stop();
    }, { id: nativeId, playbackId }), 3000, 'AUDIO_STOP_TIMEOUT');
  }
  async avatarControl(nativeId, options) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.avatarControl(args), { nativeId, ...options }), 5000, 'AVATAR_CONTROL_TIMEOUT');
  }
  async cancelAvatarControl(nativeId, controlId) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.cancelAvatarControl(args), { nativeId, controlId }), 3000, 'AVATAR_CANCEL_TIMEOUT');
  }
  async playClip(nativeId, id, asset, data, volume) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.playClip(args),
      { nativeId, id, clipId: asset.id, base64: data.toString('base64'), volume }), 20000, 'CLIP_LOAD_TIMEOUT');
  }
  async controlClip(nativeId, action, volume) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.controlClip(args),
      { nativeId, action, volume }), 5000, 'CLIP_CONTROL_TIMEOUT');
  }
  async startLive(nativeId, sessionId, epoch = 0) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.startLive(args), { nativeId, sessionId, epoch }), 5000, 'LIVE_START_TIMEOUT');
  }
  async liveAudio(nativeId, sessionId, data, epoch = 0) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.liveAudio(args), { nativeId, sessionId, epoch, base64: data.toString('base64') }), 3000, 'LIVE_OUTPUT_TIMEOUT');
  }
  async liveActivity(nativeId, sessionId, state, epoch = 0) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.liveActivity(args), { nativeId, sessionId, state, epoch }), 3000, 'LIVE_VISUAL_TIMEOUT');
  }
  async livePlayback(nativeId, sessionId, epoch = 0) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.livePlayback(args), { nativeId, sessionId, epoch }), 3000, 'LIVE_PLAYBACK_TIMEOUT');
  }
  async clearLive(nativeId, sessionId, epoch) {
    return bounded(this.page.evaluate(args => window.__botskyAudio.clearLive(args), { nativeId, sessionId, epoch }), 3000, 'LIVE_STOP_TIMEOUT');
  }
  async stopLive(nativeId, sessionId) {
    if (this.page) await bounded(this.page.evaluate(args => window.__botskyAudio.stopLive(args), { nativeId, sessionId }), 3000, 'LIVE_STOP_TIMEOUT');
  }
  async volume(nativeId, value) {
    return bounded(this.page.evaluate(({ id, value }) => {
      if (!window.__botskyAudio.matches(id)) throw new Error('AUDIO_CALL_CHANGED');
      window.__botskyAudio.setVolume(value);
    }, { id: nativeId, value }), 3000, 'AUDIO_VOLUME_TIMEOUT');
  }
  async end(expectedId, { incoming = false } = {}) {
    const snapshot = await this.snapshot();
    if (!snapshot.active) return;
    if (snapshot.id !== expectedId || snapshot.outgoing === incoming) throw new ServiceError('CALL_CHANGED', 'La llamada activa ya no corresponde al intento.');
    await this.stopAudio(expectedId);
    const result = await bounded(this.page.evaluate(async ({ id, incoming }) => {
      const stack = await window.WPP.whatsapp.functions.getVoipStackInterface();
      const collection = window.require('WAWebCallCollection');
      const call = collection.activeCall || collection.lastActiveCall;
      if (!call || call.getState?.() === 0) return 'ended';
      if (String(call.id) !== id || !!call.outgoing === incoming) return 'changed';
      call.userEndedCall = true;
      // WA-JS 4.7.2 / native stack: endCall(reason=Self, isUserInitiated=true).
      await stack.endCall(2, true);
      return 'requested';
    }, { id: expectedId, incoming }), 5000, 'HANGUP_TIMEOUT');
    if (result === 'changed') throw new ServiceError('CALL_CHANGED', 'Cambió la llamada activa.');
    for (let i = 0; i < 16; i++) {
      const current = await this.snapshot();
      if (!current.active) return;
      if (current.id !== expectedId) throw new ServiceError('CALL_CHANGED', 'Cambió la llamada activa.');
      await sleep(200);
    }
    throw new ServiceError('HANGUP_UNCONFIRMED', 'WhatsApp no confirmó el cierre.');
  }
  async inspectLinking() {
    if (!this.page || this.page.isClosed()) throw new ServiceError('QR_UNAVAILABLE', 'El navegador aún no tiene un QR.', 503);
    const details = await bounded(this.page.evaluate(() => {
      // Atomic page-side guard: never inspect a linked chat view.
      if (location.hostname !== 'web.whatsapp.com' || document.querySelector('#pane-side')) return { loginVisible: false };
      const labels = ['Selecciona para actualizar el código QR', 'Haz clic para recargar el código QR', 'Click to reload QR code'];
      const cookieLabels = ['Aceptar todas', 'Aceptar todas las cookies', 'Permitir todas las cookies', 'Accept all', 'Allow all cookies'];
      const phoneLabels = ['Iniciar sesión con número de teléfono', 'Log in with phone number', 'Vincular con el número de teléfono', 'Vincular con número de teléfono', 'Link with phone number', 'Siguiente', 'Next'];
      const nodes = [...document.querySelectorAll('button,[role="button"]')];
      const visible = node => { const r = node.getBoundingClientRect(); const s = getComputedStyle(node); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
      return { loginVisible: true, host: location.hostname,
        whatsappTitle: document.title === 'WhatsApp',
        qrCanvases: Math.min(10, document.querySelectorAll('[data-ref] canvas').length),
        dataRefElements: Math.min(10, document.querySelectorAll('[data-ref]').length),
        dialogs: Math.min(10, document.querySelectorAll('[role=dialog],dialog').length),
        rateLimited: [...document.querySelectorAll('[role=dialog],dialog')].some(dialog => visible(dialog) && [...dialog.querySelectorAll('*')].some(node => visible(node) && ['Demasiados intentos', 'Too many attempts'].includes((node.textContent || '').trim()))),
        cookieButtons: cookieLabels.filter(label => nodes.some(node => visible(node) && (node.getAttribute('aria-label') === label || node.textContent.trim() === label))),
        phoneInputs: Math.min(10, document.querySelectorAll('input[type=tel]').length),
        inputCounts: { text: Math.min(10, document.querySelectorAll('input[type=text]').length), noType: Math.min(10, document.querySelectorAll('input:not([type])').length), phoneMode: Math.min(10, document.querySelectorAll('input[inputmode=tel],input[autocomplete=tel]').length) },
        phoneInputLabels: ['Número de teléfono', 'Phone number'].filter(label => [...document.querySelectorAll('input')].some(node => node.getAttribute('aria-label') === label || node.getAttribute('placeholder') === label)),
        phoneButtons: phoneLabels.filter(label => nodes.some(node => visible(node) && (node.getAttribute('aria-label') === label || node.textContent.trim() === label))),
        refreshButtons: labels.filter(label => nodes.some(node => visible(node) && (node.getAttribute('aria-label') === label || node.textContent.trim() === label))) };
    }), 5000, 'LINK_DIAGNOSTICS_TIMEOUT');
    return details.loginVisible ? { ...details, events: structuredClone(this.linkingEvents) } : details;
  }
  async linkingScreenshot() {
    if (!this.page || this.page.isClosed()) throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
    const unsafe = () => location.hostname !== 'web.whatsapp.com' || !!document.querySelector('#pane-side');
    if (await this.page.evaluate(unsafe)) throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
    const bytes = await bounded(this.page.screenshot({ type: 'png', timeout: 5000 }), 6000, 'LINK_SCREENSHOT_TIMEOUT');
    if (await this.page.evaluate(unsafe)) throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
    return bytes;
  }
  async assertLinkNotRateLimited() {
    for (const label of ['Demasiados intentos', 'Too many attempts']) {
      const marker = this.page.getByText(label, { exact: true });
      if (await marker.count() && await marker.first().isVisible()) throw new ServiceError('LINK_RATE_LIMITED', 'WhatsApp ha limitado temporalmente la vinculación. Inténtalo más tarde.', 429);
    }
  }
  async currentLinkCode(accountJid) {
    const account = typeof accountJid === 'string' && accountJid.match(/^([1-9]\d{9,14})@s\.whatsapp\.net$/);
    if (!account || !this.page || this.page.isClosed()) throw new ServiceError('LINK_UNAVAILABLE', 'No se pudo consultar la vinculación.', 409);
    const page = this.page;
    await this.assertLinkNotRateLimited();
    const result = await bounded(page.evaluate(expected => {
      if (location.hostname !== 'web.whatsapp.com' || document.querySelector('#pane-side')) return null;
      const codes = new Set(), phones = new Set();
      for (const node of document.querySelectorAll('div,span,p')) {
        const rect = node.getBoundingClientRect(), style = getComputedStyle(node);
        if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden') continue;
        const text = (node.textContent || '').trim();
        if (/^[A-Z0-9]{4}[-\s][A-Z0-9]{4}$/.test(text)) codes.add(text.replace(/[-\s]/g, ''));
        if (text.length < 200 && /(?:Vinculando la cuenta de WhatsApp|Linking WhatsApp account)/i.test(text)) {
          for (const match of text.matchAll(/\+[0-9][0-9\s().-]{8,22}/g)) phones.add(match[0].replace(/\D/g, ''));
        }
      }
      return { code: codes.size === 1 ? [...codes][0] : null, accountMatches: phones.size === 1 && phones.has(expected) };
    }, account[1]), 5000, 'LINK_DIAGNOSTICS_TIMEOUT');
    if (!result?.code || !/^[A-Z0-9]{8}$/.test(result.code)) throw new ServiceError('LINK_CODE_UNAVAILABLE', 'No hay un código visible de vinculación.', 409);
    if (await page.evaluate(() => location.hostname !== 'web.whatsapp.com' || !!document.querySelector('#pane-side'))) throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
    await this.assertLinkNotRateLimited();
    return { code: result.code, accountMatches: result.accountMatches === true, expires: null };
  }
  async linkWithPhoneNumber(accountJid) {
    const account = typeof accountJid === 'string' && accountJid.match(/^([1-9]\d{9,14})@s\.whatsapp\.net$/);
    if (!account || !this.page || this.page.isClosed()) throw new ServiceError('LINK_UNAVAILABLE', 'No se pudo preparar la vinculación.', 503);
    const page = this.page;
    await this.assertLinkNotRateLimited();
    const ensureLogin = async () => {
      await this.assertLinkNotRateLimited();
      if (await page.evaluate(() => location.hostname !== 'web.whatsapp.com' || !!document.querySelector('#pane-side'))) throw new ServiceError('LINK_UNAVAILABLE', 'La cuenta ya no espera vinculación.', 409);
    };
    await ensureLogin();
    const phone = page.locator('input');
    const formHeading = page.getByText(/^(Ingresa el número de teléfono|Enter phone number)$/);
    if ((await phone.count() !== 1 || !await phone.isVisible()) && !(await formHeading.count() === 1 && await formHeading.isVisible())) {
      let opener;
      for (const label of ['Iniciar sesión con número de teléfono', 'Log in with phone number', 'Vincular con el número de teléfono', 'Vincular con número de teléfono', 'Link with phone number']) {
        const candidate = page.getByText(label, { exact: true });
        if (await candidate.count() === 1 && await candidate.isVisible()) { opener = candidate; break; }
      }
      if (!opener) throw new ServiceError('LINK_UI_UNSUPPORTED', 'No se encontró la opción de vinculación por número.', 409);
      await ensureLogin();
      try { await opener.click({ timeout: 5000 }); }
      catch (error) {
        const message = String(error?.message || '');
        const reason = /intercepts pointer events/i.test(message) ? 'interceptado' : /not stable/i.test(message) ? 'inestable' : /navigation/i.test(message) ? 'navegación' : error?.name === 'TimeoutError' ? 'plazo' : 'acción';
        throw new ServiceError('LINK_UI_ACTION_FAILED', `No se pudo activar el control (${reason}).`, 409);
      }
      await ensureLogin();
    }
    let phoneReady = false;
    for (let i = 0; i < 80; i++) {
      await ensureLogin();
      if (await phone.count() === 1 && await phone.isVisible()) { phoneReady = true; break; }
      await sleep(250);
    }
    if (!phoneReady) throw new ServiceError('LINK_UI_UNSUPPORTED', 'No se pudo verificar el campo de número.', 409);
    const initial = (await phone.inputValue()).trim();
    const inlinePrefix = initial.match(/^\+([1-9]\d{0,2})$/);
    let value;
    if (inlinePrefix) {
      if (!account[1].startsWith(inlinePrefix[1]) || account[1].length - inlinePrefix[1].length < 7) throw new ServiceError('LINK_COUNTRY_UNVERIFIED', 'No se pudo verificar el prefijo seleccionado.', 409);
      value = account[1].slice(inlinePrefix[1].length);
    } else {
      if (initial) throw new ServiceError('LINK_COUNTRY_UNVERIFIED', 'No se pudo verificar el campo de número.', 409);
      const prefixes = await page.evaluate(() => {
        if (location.hostname !== 'web.whatsapp.com' || document.querySelector('#pane-side')) return null;
        const nodes = [...document.querySelectorAll('[role="combobox"],select,button')];
        return [...new Set(nodes.map(n => (n.textContent || '').match(/(?:^|\s)\+(\d{1,3})(?:\s|$)/)?.[1]).filter(Boolean))];
      });
      if (!prefixes || prefixes.length !== 1 || !account[1].startsWith(prefixes[0])) throw new ServiceError('LINK_COUNTRY_UNVERIFIED', 'No se pudo verificar el prefijo seleccionado.', 409);
      value = account[1].slice(prefixes[0].length);
      if (value.length < 7) throw new ServiceError('LINK_COUNTRY_UNVERIFIED', 'No se pudo verificar el número.', 409);
    }
    await ensureLogin(); await phone.fill(value); await ensureLogin();
    const expected = inlinePrefix ? account[1] : value;
    await sleep(2000);
    let verified = false;
    for (let i = 0; i < 8; i++) {
      await ensureLogin();
      if ((await phone.inputValue()).replace(/\D/g, '') === expected) { verified = true; break; }
      await sleep(250);
    }
    if (!verified) throw new ServiceError('LINK_COUNTRY_UNVERIFIED', 'No se pudo verificar el número.', 409);
    let next;
    for (const label of ['Siguiente', 'Next']) {
      const candidate = page.getByRole('button', { name: label, exact: true });
      if (await candidate.count() === 1 && await candidate.isVisible()) { next = candidate; break; }
    }
    if (!next) throw new ServiceError('LINK_UI_UNSUPPORTED', 'No se encontró el control para continuar.', 409);
    await ensureLogin(); await next.click();
    for (let i = 0; i < 30; i++) {
      const code = await page.evaluate(() => {
        if (location.hostname !== 'web.whatsapp.com' || document.querySelector('#pane-side')) return null;
        const codes = new Set();
        for (const node of document.querySelectorAll('div,span')) {
          const rect = node.getBoundingClientRect(), style = getComputedStyle(node);
          if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden') continue;
          const text = (node.textContent || '').trim();
          if (/^[A-Z0-9]{4}[-\s][A-Z0-9]{4}$/.test(text)) codes.add(text.replace(/[-\s]/g, ''));
        }
        return codes.size === 1 ? [...codes][0] : null;
      });
      if (code) { await ensureLogin(); return { code, expires: null }; }
      await ensureLogin(); await sleep(250);
    }
    throw new ServiceError('LINK_CODE_UNAVAILABLE', 'No se pudo leer un código de vinculación.', 409);
  }
  async qr() {
    if (!this.page) throw new ServiceError('QR_UNAVAILABLE', 'El navegador aún no tiene un QR.', 503);
    await this.assertLinkNotRateLimited();
    // Only exact known login labels are actionable, and never after chat appears.
    if (await this.page.locator('#pane-side').count()) throw new ServiceError('QR_UNAVAILABLE', 'La cuenta ya no está esperando vinculación.', 409);
    for (const label of ['Selecciona para actualizar el código QR', 'Haz clic para recargar el código QR', 'Click to reload QR code']) {
      const refresh = this.page.getByRole('button', { name: label, exact: true });
      if (await refresh.count() === 1 && await refresh.isVisible()) {
        if (await this.page.locator('#pane-side').count()) throw new ServiceError('QR_UNAVAILABLE', 'La cuenta ya no está esperando vinculación.', 409);
        await this.assertLinkNotRateLimited();
        await refresh.click();
        await refresh.waitFor({ state: 'hidden', timeout: 5000 });
        break;
      }
    }
    const qr = this.page.locator('[data-ref] canvas').first();
    if (!await qr.isVisible() || await this.page.locator('#pane-side').count()) throw new ServiceError('QR_UNAVAILABLE', 'No hay un QR de vinculación visible.', 409);
    return qr.screenshot({ timeout: 5000 });
  }
  async abort() {
    const record = this.processRecord;
    if (record && identity(record.pid) === record.identity) {
      try { process.kill(record.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    }
    return this.close();
  }
  async close() {
    if (this.closingPromise) return this.closingPromise;
    const context = this.context; this.context = null; this.page = null; this.ready = false; this.preloadedAudioId = null;
    if (!context) return;
    const record = this.processRecord;
    this.closingPromise = (async () => {
      await bounded(context.close(), 5000, 'BROWSER_CLOSE_TIMEOUT').catch(() => {});
      await terminate(record);
    })().finally(() => { this.closingPromise = null; });
    return this.closingPromise;
  }
}

module.exports = { BrowserDriver, bounded };
