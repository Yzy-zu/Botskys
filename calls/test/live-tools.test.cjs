// Port técnico de Zhana; fixtures locales sin navegador ni proveedor.
'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const { WebSocket, WebSocketServer } = require('ws');
const { GeminiLive } = require('../service/gemini-live.cjs');
const { CLIP_TOOLS } = require('../service/clip-commands.cjs');
async function fixture(t, onToolCall) {
  const server = new WebSocketServer({ port: 0, host: '127.0.0.1' }); await new Promise(r => server.once('listening', r));
  let peer; const received = [];
  server.on('connection', ws => { peer = ws; ws.on('message', bytes => { const message = JSON.parse(bytes); received.push(message); if (message.setup) ws.send(JSON.stringify({ setupComplete: {} })); }); });
  const Socket = function(_url, opts) { return new WebSocket(`ws://127.0.0.1:${server.address().port}`, opts); };
  const live = new GeminiLive({model:'models/fixture-live', key: 'fixture', Socket, onAudio() {}, onFailure() {}, tools: CLIP_TOOLS, onToolCall });
  t.after(() => { live.close(); for (const client of server.clients) client.terminate(); server.close(); });
  await live.connect();
  const wait = async predicate => { for (let i = 0; i < 100; i++) { if (predicate()) return; await new Promise(r => setTimeout(r, 5)); } throw Error('tool response timeout'); };
  return { live, received, send: data => peer.send(JSON.stringify(data)), wait };
}
test('V4 Live tool protocol sends actual results and does not repeat duplicate actions', async t => {
  let actions = 0;
  const f = await fixture(t, async args => { actions++; return { success: true, clip: args.query }; });
  assert.ok(f.received[0].setup.tools[0].functionDeclarations.length);
  const call = { toolCall: { functionCalls: [{ id: 'clip-1', name: 'controlar_clips', args: { action: 'play', query: 'gato' } }] } };
  f.send(call); await f.wait(() => f.received.some(m => m.toolResponse));
  f.send(call); await f.wait(() => f.received.filter(m => m.toolResponse).length === 2);
  assert.equal(actions, 1); const response = f.received.at(-1).toolResponse.functionResponses[0];
  assert.equal(response.id, 'clip-1'); assert.equal(response.response.success, true);
});
test('V4 Live cancellations and closure abort pending tool work without a late confirmation', async t => {
  let release, entered, signal;
  const gate = new Promise(r => { release = r; }), started = new Promise(r => { entered = r; });
  const f = await fixture(t, async (_, info) => { signal = info.signal; entered(); await gate; return { success: !signal.aborted }; });
  f.send({ toolCall: { functionCalls: [{ id: 'cancelled', name: 'controlar_clips', args: { action: 'play' } }] } }); await started;
  f.send({ toolCallCancellation: { ids: ['cancelled'] } }); await f.wait(() => signal.aborted);
  release(); await f.wait(() => f.live.toolControllers.size === 0);
  assert.equal(f.received.filter(m => m.toolResponse).length, 0);
});
