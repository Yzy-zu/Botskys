'use strict';

const http = require('node:http');
const { timingSafeEqual } = require('node:crypto');
const { ServiceError } = require('./common.cjs');
const { MAX_UPLOAD } = require('./audio-store.cjs');
const { MAX_CLIP_BYTES } = require('./clip-store.cjs');

function json(response, status, data) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  response.end(JSON.stringify(data) + '\n');
}

async function body(request, limit = 4096) {
  if (request.headers['content-type']?.split(';')[0].trim() !== 'application/json') throw new ServiceError('JSON_REQUIRED', 'Se requiere application/json.', 415);
  const chunks = []; let bytes = 0;
  await new Promise((resolve, reject) => {
    let oversized = false;
    request.on('data', chunk => {
      bytes += chunk.length;
      if (bytes > limit) {
        if (!oversized) { oversized = true; chunks.length = 0; reject(new ServiceError('BODY_TOO_LARGE', 'La solicitud es demasiado grande.', 413)); }
      } else if (!oversized) chunks.push(chunk);
    });
    request.once('end', resolve); request.once('error', reject);
    request.once('aborted', () => reject(new ServiceError('REQUEST_ABORTED', 'Se interrumpió la solicitud.', 400)));
  });
  try {
    const data = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
    if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error();
    return data;
  } catch { throw new ServiceError('INVALID_JSON', 'El cuerpo JSON no es válido.', 400); }
}

function fields(data, allowed) {
  if (Object.keys(data).some(key => !allowed.includes(key))) throw new ServiceError('UNKNOWN_FIELD', 'La solicitud contiene un campo desconocido.', 400);
}

function validateCallId(value) {
  if (value !== undefined && (typeof value !== 'string' || !/^[A-Za-z0-9-]{1,80}$/.test(value))) throw new ServiceError('INVALID_CALL_ID', 'El identificador no es válido.', 400);
}

function createServer({ manager, driver, audioStore, token, log = () => {}, policyRevision, policyCurrent = () => true, accountJid = null, allowLinking = false, requireVerifiedTransport = false }) {
  const expected = Buffer.from(`Bearer ${token}`);
  const preparationJobs = new Map();
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      if (request.method === 'GET' && url.pathname === '/healthz') {
        const agendaRequired = manager.agenda?.policy?.enabled && (manager.featureEnabled?.('agenda') ?? true);
        const ready = manager.state === 'ready' && (!agendaRequired || !!manager.agenda?.ready);
        return json(response, ready ? 200 : 503, { ready });
      }
      const supplied = Buffer.from(request.headers.authorization || '');
      if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) throw new ServiceError('UNAUTHORIZED', 'Credenciales locales inválidas.', 401);
      if (request.headers.origin) throw new ServiceError('ORIGIN_NOT_ALLOWED', 'Esta API admite clientes locales de terminal.', 403);
      if ((url.pathname.startsWith('/v1/linking/') || url.pathname.startsWith('/v1/diagnostics/linking') || url.pathname === '/v1/qr') && allowLinking !== true) throw new ServiceError('LINKING_NOT_AUTHORIZED', 'Vincular requiere encargo posterior.', 403);
      const controller = new AbortController();
      request.once('aborted', () => controller.abort());
      response.once('close', () => { if (!response.writableFinished) controller.abort(); });
      async function prepare(action) {
        const key = request.headers['x-call-job-key'];
        if (key === undefined) return action();
        if (typeof key !== 'string' || !/^[A-Za-z0-9._:-]{8,128}$/.test(key)) throw new ServiceError('INVALID_KEY', 'Clave no válida.', 400);
        if (Object.hasOwn(manager.journal?.cancelledKeys || {}, key)) throw new ServiceError('CANCELLED', 'Encargo cancelado.', 409);
        if (preparationJobs.has(key)) throw new ServiceError('AUDIO_PREPARING', 'Ese audio ya se está preparando.', 409);
        let finish;
        const job = { controller, finished: new Promise(resolve => { finish = resolve; }) };
        preparationJobs.set(key, job);
        try { return await action(); }
        finally { if (preparationJobs.get(key) === job) preparationJobs.delete(key); finish(); }
      }
      if (request.method === 'GET' && url.pathname === '/v1/operations') {
        if (!manager.operations) throw new ServiceError('NOT_READY', 'El diagnóstico se está preparando.', 503);
        return json(response, 200, await manager.operations.report());
      }
      if (url.pathname === '/v1/operations/features' && ['GET', 'POST'].includes(request.method)) {
        if (!manager.featureStore) throw new ServiceError('NOT_READY', 'Los controles se están preparando.', 503);
        if (request.method === 'GET') return json(response, 200, manager.featureStore.status());
        const patch = await body(request); return json(response, 200, await manager.featureStore.update(patch));
      }
      if (request.method === 'GET' && url.pathname === '/v1/status') return json(response, 200, { ...manager.status(), policyRevision });
      if (request.method === 'GET' && url.pathname === '/v1/calls/by-id') {
        const id = url.searchParams.get('callId');
        validateCallId(id);
        if (!id) throw new ServiceError('INVALID_CALL_ID', 'Indica la llamada que quieres consultar.', 400);
        const record = manager.journal.byId(id);
        if (!record) throw new ServiceError('CALL_NOT_FOUND', 'No se encontró esa llamada.', 404);
        return json(response, 200, { call: manager.publicCall(record), key: record.key });
      }
      if (request.method === 'GET' && url.pathname === '/v1/calls/by-key') {
        const key = url.searchParams.get('key');
        if (!key || !/^[A-Za-z0-9._:-]{8,128}$/.test(key)) throw new ServiceError('INVALID_KEY', 'Clave no válida.', 400);
        const record = manager.journal.byKey(key);
        return json(response, 200, { call: record ? manager.publicCall(record) : null, cancelled: Object.hasOwn(manager.journal.cancelledKeys, key) });
      }
      if (request.method === 'GET' && url.pathname === '/v1/linking/code') {
        if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
        return json(response, 200, await manager.serial(async () => {
          if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
          if (!accountJid) throw new ServiceError('LINK_ACCOUNT_UNCONFIGURED', 'La cuenta de llamadas no está configurada.', 409);
          if (!policyCurrent()) throw new ServiceError('POLICY_MISMATCH', 'La política de llamadas no coincide.', 409);
          const result = await driver.currentLinkCode(accountJid);
          if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
          return result;
        }));
      }
      if (request.method === 'POST' && url.pathname === '/v1/linking/phone') {
        const data = await body(request); fields(data, []);
        if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
        return json(response, 200, await manager.serial(async () => {
          if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
          if (!accountJid) throw new ServiceError('LINK_ACCOUNT_UNCONFIGURED', 'La cuenta de llamadas no está configurada.', 409);
          if (!policyCurrent()) throw new ServiceError('POLICY_MISMATCH', 'La política de llamadas no coincide.', 409);
          return driver.linkWithPhoneNumber(accountJid);
        }));
      }
      if (request.method === 'GET' && url.pathname === '/v1/diagnostics/linking/screenshot') {
        if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
        const png = await manager.serial(async () => {
          if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
          const bytes = await driver.linkingScreenshot();
          if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
          return bytes;
        });
        response.writeHead(200, { 'Content-Type': 'image/png', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
        return response.end(png);
      }
      if (request.method === 'GET' && url.pathname === '/v1/diagnostics/linking') {
        if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
        return json(response, 200, await manager.serial(async () => {
          if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'No se está vinculando la cuenta.', 409);
          return driver.inspectLinking();
        }));
      }
      if (request.method === 'GET' && url.pathname === '/v1/diagnostics/call-runtime') return json(response, 200, await manager.serial(() => driver.inspectCallRuntime({ accountJid, lookupOwner: url.searchParams.get('ownerLookup') === '1', ownerJid: manager.destinationPolicy?.ownerJid, groupSources: url.searchParams.get('groupSources') === '1', videoSources: url.searchParams.get('videoSources') === '1' })));
      if (request.method === 'POST' && url.pathname === '/v1/avatar/control') {
        const data = await body(request); fields(data, ['callId', 'action', 'name', 'duration']); validateCallId(data.callId);
        return json(response, 200, await manager.avatarCommand({ ...data, signal: controller.signal }));
      }
      if (url.pathname.startsWith('/v1/clips')) {
        if (!manager.clipStore) throw new ServiceError('NOT_READY', 'El catálogo se está preparando.', 503);
        if (request.method === 'GET' && url.pathname === '/v1/clips') return json(response, 200, { clips: await manager.clipStore.list() });
        if (request.method === 'POST' && url.pathname === '/v1/clips') {
          if (request.headers['content-type']?.split(';')[0].trim() !== 'application/octet-stream') throw new ServiceError('CLIP_TYPE_REQUIRED', 'Envía el archivo de video binario.', 415);
          if (Number(request.headers['content-length']) > MAX_CLIP_BYTES) throw new ServiceError('CLIP_TOO_LARGE', 'El clip supera 20 MiB.', 413);
          return json(response, 201, { clip: await manager.clipStore.importStream(request, { signal: controller.signal, label: url.searchParams.get('name') || 'Clip' }) });
        }
        if (request.method === 'POST' && url.pathname === '/v1/clips/demo') {
          const data = await body(request); fields(data, []);
          return json(response, 201, { clip: await manager.clipStore.demo({ signal: controller.signal }) });
        }
        if (request.method === 'POST' && url.pathname === '/v1/clips/command') {
          const data = await body(request); fields(data, ['callId', 'scope', 'request']); validateCallId(data.callId);
          if (!manager.clipCommands) throw new ServiceError('NOT_READY', 'Los controles se están preparando.', 503);
          return json(response, 200, await manager.clipCommands.execute({ ...data, key: request.headers['idempotency-key'], signal: controller.signal }));
        }
        if (request.method === 'POST' && url.pathname === '/v1/clips/metadata') {
          const data = await body(request); fields(data, ['id', 'label', 'aliases']);
          return json(response, 200, { clip: await manager.clipStore.update(data) });
        }
        if (request.method === 'POST' && url.pathname === '/v1/clips/play') {
          const data = await body(request); fields(data, ['clipId', 'callId', 'volume']); validateCallId(data.callId);
          const result = await manager.playClip({ ...data, key: request.headers['idempotency-key'] });
          return json(response, result.replayed ? 200 : 202, result);
        }
        if (request.method === 'POST' && url.pathname === '/v1/clips/control') {
          const data = await body(request); fields(data, ['callId', 'action', 'volume']); validateCallId(data.callId);
          return json(response, 200, await manager.controlClip(data));
        }
      }
      if (request.method === 'GET' && url.pathname === '/v1/audio') return json(response, 200, { audio: await audioStore.list() });
      if (request.method === 'POST' && url.pathname === '/v1/audio') {
        const type = request.headers['content-type']?.split(';')[0].trim();
        if (type !== 'application/octet-stream' && !type?.startsWith('audio/')) throw new ServiceError('AUDIO_TYPE_REQUIRED', 'Envía un archivo de audio binario.', 415);
        if (Number(request.headers['content-length']) > MAX_UPLOAD) throw new ServiceError('AUDIO_TOO_LARGE', 'El archivo supera 20 MiB.', 413);
        return json(response, 201, { audio: await prepare(() => audioStore.importStream(request, { signal: controller.signal })) });
      }
      if (request.method === 'POST' && url.pathname === '/v1/audio/play') {
        const data = await body(request); fields(data, ['audioId', 'callId', 'volume']); validateCallId(data.callId);
        const result = await manager.playAudio({ ...data, key: request.headers['idempotency-key'] });
        return json(response, result.replayed ? 200 : 202, result);
      }
      if (request.method === 'POST' && url.pathname === '/v1/audio/stop') {
        const data = await body(request); fields(data, ['callId']); validateCallId(data.callId);
        return json(response, 200, await manager.stopAudio(data.callId));
      }
      if (request.method === 'POST' && url.pathname === '/v1/audio/volume') {
        const data = await body(request); fields(data, ['callId', 'volume']); validateCallId(data.callId);
        return json(response, 200, await manager.setVolume(data));
      }
      if (request.method === 'GET' && /^\/v1\/calls\/[A-Za-z0-9-]+$/.test(url.pathname)) {
        return json(response, 200, manager.getCall(url.pathname.split('/').at(-1)));
      }
      if (request.method === 'GET' && url.pathname === '/v1/qr') {
        if (manager.state !== 'needs_link') throw new ServiceError('QR_UNAVAILABLE', 'La sesión no está esperando vinculación.', 409);
        const png = await driver.qr();
        response.writeHead(200, { 'Content-Type': 'image/png', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
        return response.end(png);
      }
      if (request.method === 'POST' && url.pathname === '/v1/destinations/group') {
        const data = await body(request); fields(data, ['origin', 'name', 'id']);
        return json(response, 200, await manager.resolveGroup(data));
      }
      if (request.method === 'POST' && (url.pathname === '/v1/calls' || url.pathname === '/v1/schedules' || url.pathname === '/v1/schedules/update')) {
        if (!policyRevision || request.headers['x-calls-policy-revision'] !== policyRevision || !policyCurrent()) throw new ServiceError('POLICY_MISMATCH', 'La política de llamadas no coincide.', 409);
      }
      if (request.method === 'POST' && url.pathname === '/v1/calls') {
        const data = await body(request, 32 * 1024); fields(data, ['inputTransport', 'groupId', 'targetJid', 'origin', 'maxSeconds', 'audioId', 'volume', 'endAfterAudio', 'durationFromAnswer', 'live', 'video', 'liveRequest', 'sourceReceipt']);
        if(requireVerifiedTransport && data.inputTransport !== 'evolution' && !(driver.isFixture === true && data.inputTransport === 'local')) throw new ServiceError('TRANSPORT_REQUIRED','Se requiere ingreso verificado.',403);
        delete data.inputTransport;
        const result = await manager.startCall({ ...data, key: request.headers['idempotency-key'] });
        return json(response, result.replayed ? 200 : 202, result);
      }
      if (request.method === 'POST' && ['/v1/schedules', '/v1/schedules/list', '/v1/schedules/cancel', '/v1/schedules/update', '/v1/schedules/get'].includes(url.pathname)) {
        if (!manager.agenda?.ready) throw new ServiceError('SCHEDULE_NOT_READY', 'La agenda se está preparando.', 503);
        const data = await body(request, 32 * 1024);
        if (url.pathname === '/v1/schedules') {
          fields(data, ['inputTransport', 'targetJid', 'origin', 'dueAt', 'timeZone', 'maxSeconds', 'audioId', 'volume', 'endAfterAudio', 'durationFromAnswer', 'live', 'liveRequest', 'sourceReceipt']);
          if(requireVerifiedTransport && data.inputTransport !== 'evolution' && !(driver.isFixture === true && data.inputTransport === 'local')) throw new ServiceError('TRANSPORT_REQUIRED','Se requiere ingreso verificado.',403);
          delete data.inputTransport;
          return json(response, 201, await manager.agenda.create({ ...data, key: request.headers['idempotency-key'] }));
        }
        if (url.pathname.endsWith('/list')) { fields(data, ['origin']); return json(response, 200, await manager.agenda.list(data.origin)); }
        if (url.pathname.endsWith('/get')) { fields(data, ['origin', 'id']); return json(response, 200, await manager.agenda.get(data)); }
        if (url.pathname.endsWith('/cancel')) { fields(data, ['origin', 'id']); return json(response, 200, await manager.agenda.cancel(data)); }
        fields(data, ['origin', 'id', 'dueAt', 'timeZone']);
        return json(response, 200, await manager.agenda.update({ ...data, key: request.headers['idempotency-key'] }));
      }
      if (request.method === 'POST' && url.pathname === '/v1/notices/claim') {
        const data = await body(request); fields(data, []);
        return json(response, 200, await manager.claimFailureNotices());
      }
      if (request.method === 'POST' && url.pathname === '/v1/notices/begin') {
        const data = await body(request); fields(data, ['callId', 'lease']); validateCallId(data.callId);
        if (typeof data.callId !== 'string' || typeof data.lease !== 'string' || !/^[a-f0-9-]{36}$/.test(data.lease)) throw new ServiceError('INVALID_NOTICE', 'Acuse no válido.', 400);
        return json(response, 200, await manager.beginFailureNotice(data));
      }
      if (request.method === 'POST' && url.pathname === '/v1/notices/ack') {
        const data = await body(request); fields(data, ['callId', 'lease', 'delivered', 'outcome']); validateCallId(data.callId);
        const validOutcome = ['accepted', 'failed', 'uncertain', 'rejected'].includes(data.outcome);
        if (typeof data.callId !== 'string' || typeof data.lease !== 'string' || !/^[a-f0-9-]{36}$/.test(data.lease) ||
            (data.delivered !== undefined && typeof data.delivered !== 'boolean') ||
            (data.outcome !== undefined && !validOutcome) ||
            (data.delivered === undefined) === (data.outcome === undefined)) throw new ServiceError('INVALID_NOTICE', 'Acuse no válido.', 400);
        return json(response, 200, await manager.ackFailureNotice(data));
      }
      if (request.method === 'POST' && url.pathname === '/v1/calls/cancel-by-id') {
        const data = await body(request); fields(data, ['callId', 'onlyPreparing']); validateCallId(data.callId);
        if (!data.callId) throw new ServiceError('INVALID_CALL_ID', 'Indica la llamada que quieres cancelar.', 400);
        if (data.onlyPreparing !== undefined && typeof data.onlyPreparing !== 'boolean') throw new ServiceError('INVALID_FIELD', 'onlyPreparing debe ser booleano.', 400);
        const record = manager.journal.byId(data.callId);
        if (!record) throw new ServiceError('CALL_NOT_FOUND', 'No se encontró esa llamada.', 404);
        if (data.onlyPreparing && (!['starting', 'dialing'].includes(record.state) || record.connectedAt)) return json(response, 200, { cancelled: false, skipped: true });
        // cancelKey records the cancellation synchronously before its first await.
        const ending = manager.cancelKey(record.key);
        const running = preparationJobs.get(record.key);
        running?.controller.abort();
        ending.catch(() => {});
        await running?.finished;
        return json(response, 200, await ending);
      }
      if (request.method === 'POST' && url.pathname === '/v1/calls/cancel') {
        const data = await body(request); fields(data, ['key']);
        const running = preparationJobs.get(data.key);
        running?.controller.abort();
        const ending = manager.cancelKey(data.key);
        ending.catch(() => {});
        await running?.finished;
        return json(response, 200, await ending);
      }
      if (request.method === 'POST' && url.pathname === '/v1/hangup') {
        const data = await body(request); fields(data, ['callId']);
        validateCallId(data.callId);
        if (!data.callId) throw new ServiceError('INVALID_CALL_ID', 'Indica la llamada que quieres terminar.', 400);
        return json(response, 200, await manager.endCall(data.callId));
      }
      if (request.method === 'POST' && url.pathname === '/v1/browser/restart') {
        const data = await body(request); fields(data, []);
        return json(response, 202, await manager.restartBrowser());
      }
      throw new ServiceError('NOT_FOUND', 'Ruta no disponible.', 404);
    } catch (error) {
      request.resume();
      if (response.headersSent) return response.destroy();
      if (!error.code || !error.status) log('http_error', { code: 'INTERNAL_ERROR' });
      json(response, error.status || 500, { error: { code: error.status ? error.code : 'INTERNAL_ERROR', message: error.status ? error.message : 'No se pudo completar la operación.' } });
    }
  });
  server.requestTimeout = 15_000; server.headersTimeout = 10_000;
  server.keepAliveTimeout = 3000;
  return server;
}

module.exports = { createServer };
