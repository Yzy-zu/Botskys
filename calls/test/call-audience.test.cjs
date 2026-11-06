// Port técnico de Zhana; fixtures locales sin navegador ni proveedor.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { readCallSnapshot } = require('../service/call-snapshot.cjs');
const { BrowserDriver } = require('../service/browser.cjs');

const wid = id => ({ _serialized: `${id}@lid` });
async function snapshot(patch = {}, { identityAvailable = true } = {}) {
  const call = { id: 'native-fixture', getState() { return this.state; }, state: 6,
    isGroup: true, peerJid: wid(2), groupCallParticipantsConnected: [wid(1), wid(2)], ...patch };
  const me = identityAvailable ? { isMeAccount: id => id._serialized === '1@lid' } : {};
  const window = { WPP: { isReady: true, contact: {} }, require: name => {
    if (name === 'WAWebCallCollection') return { activeCall: call };
    if (name === 'WAWebUserPrefsMeUser') return me;
    throw Error('Unexpected module');
  } };
  return vm.runInNewContext(`(${readCallSnapshot.toString()})()`, { window, document: { querySelector: () => true } });
}

test('Native connected audience excludes self, invitees and duplicate devices', async () => {
  const s = await snapshot({ groupCallParticipants: [wid(1), wid(2), wid(3), wid(4)],
    groupCallParticipantsConnected: [wid(1), wid(2), wid(3), wid('3:9')] });
  assert.equal(s.audience.connectedHumans, 2);
  assert.equal(s.audience.source, 'native_connected_participants');
  assert.equal(s.audience.known, true);
  assert.equal('participants' in s.audience, false);
});

test('ConnectedLonely is connected transport with no listeners, including during a missing list', async () => {
  const s = await snapshot({ state: 11, groupCallParticipantsConnected: undefined });
  assert.equal(s.connected, true);
  assert.equal(s.audience.known, true);
  assert.equal(s.audience.connectedHumans, 0);
});

test('Missing or unfamiliar group telemetry cannot be mistaken for zero or a peer call', async () => {
  for (const participants of [undefined, null, {}, ['unexpected'], [{ state: 'ringing' }]]) {
    const s = await snapshot({ groupCallParticipantsConnected: participants });
    assert.equal(s.audience.known, false);
    assert.equal(s.audience.connectedHumans, null);
  }
  const unknownSelf = await snapshot({}, { identityAvailable: false });
  assert.equal(unknownSelf.audience.known, false);
  const empty = await snapshot({ groupCallParticipantsConnected: [] });
  assert.equal(empty.audience.known, true);
  assert.equal(empty.audience.connectedHumans, 0);
});

test('Native peer representation of a two-member group and incoming private calls remain supported', async () => {
  const peer = await snapshot({ isGroup: false, groupCallParticipantsConnected: undefined });
  assert.equal(peer.audience.connectedHumans, 1);
  const ringing = await snapshot({ isGroup: false, state: 3 });
  assert.equal(ringing.audience.known, false);
  const ended = await snapshot({ isGroup: false, state: 0 });
  assert.equal(ended.active, false);
  assert.equal(ended.connected, false);
});

test('Terminal audience diagnostics expose counts without native IDs, phones or participant identities', async () => {
  const driver = new BrowserDriver({ privateDir: '/tmp/botsky-audience-diagnostics-test' });
  driver.ready = true; driver.page = {};
  driver.snapshot = async () => ({ ...await snapshot(), runtimeVersion: 'fixture-version',
    id: 'private-call-id', peerPhone: 'private-phone', groupId: 'private-group' });
  const diagnostic = await driver.inspectCallRuntime();
  assert.equal(diagnostic.audience.connectedHumans, 1);
  assert.equal(diagnostic.version, 'fixture-version');
  assert.equal(diagnostic.native.hasGroupContext, true);
  assert.doesNotMatch(JSON.stringify(diagnostic), /private-|@lid|peerPhone|peerJid/);
});

test('The three-member Lab trial requires an explicit configuration and cannot bypass the selected chat check', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-audience-browser-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  for (const [count, maxParticipants, selectedId, allowed] of [
    [1, 2, 'lab@g.us', false], [2, 2, 'lab@g.us', true],
    [3, 2, 'lab@g.us', false], [3, 3, 'lab@g.us', true],
    [4, 3, 'lab@g.us', false], [3, 3, 'other@g.us', false],
  ]) {
    let arms = 0, clicks = 0;
    const driver = new BrowserDriver({ privateDir: dir });
    const window = { WPP: { chat: { openChatBottom: async () => {}, getActiveChat: () => ({ id: { _serialized: selectedId } }) },
      group: { getParticipants: async () => Array(count).fill({}) } }, __botskyAudio: { arm: async () => { arms++; } } };
    driver.page = { evaluate: async (fn, arg) => vm.runInNewContext(`(${fn.toString()})(arg)`, {
      window, document: { querySelectorAll: () => [] }, arg,
    }) };
    driver.snapshot = async () => ({ active: false });
    driver.disarmAudio = async () => {};
    driver.dispatchGroupCall = async () => { clicks++; throw Object.assign(Error('Stop before any actual call'), { code: 'FIXTURE_STOP' }); };
    await assert.rejects(driver.dial({ id: 'lab@g.us', minParticipants: 2, maxParticipants }, { cancelled: () => false, audioToken: 'fixture' }),
      { code: allowed ? 'FIXTURE_STOP' : 'GROUP_MISMATCH' });
    assert.equal(arms, Number(allowed));
    assert.equal(clicks, Number(allowed));
  }
});
