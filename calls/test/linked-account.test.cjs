// Port técnico de Zhana; solo VM, sin navegador.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { BrowserDriver } = require('../service/browser.cjs');

test('runtime verifies configured linked account without exporting identity', async () => {
  const driver = new BrowserDriver({ privateDir: '/tmp/botsky-account-fixture' });
  driver.ready = true;
  driver.snapshot = async () => ({ runtimeVersion: 'fixture', active: false });
  let actual = { _serialized: '5215511112222:9@c.us' };
  driver.page = { evaluate: async (fn, arg) => JSON.parse(JSON.stringify(vm.runInNewContext(`(${fn.toString()})(expected)`, { expected: arg, window: { WPP: { conn: { getMyUserId: () => actual } } } }))) };
  const expected = '525511112222@s.whatsapp.net';
  assert.deepEqual((await driver.inspectCallRuntime({ accountJid: expected })).account, { known: true, matches: true });
  actual = { _serialized: '525533334444@c.us' };
  assert.deepEqual((await driver.inspectCallRuntime({ accountJid: expected })).account, { known: true, matches: false });
  actual = undefined;
  assert.deepEqual((await driver.inspectCallRuntime({ accountJid: expected })).account, { known: false, matches: false });
});
