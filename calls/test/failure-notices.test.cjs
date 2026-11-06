// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { sourceReceipt } = require('../service/failure-notices.cjs');
const owner = '525511112222@s.whatsapp.net';
const origin = { chatId: owner, requesterId: owner };
const receipt = { chatId: owner, messageKey: { id: 'source-message', remoteJid: owner, fromMe: false } };

test('PM05C: receipt is scoped to its verified source, with no text, destination change or extra fields', () => {
  assert.deepEqual(sourceReceipt(receipt, origin), receipt);
  assert.equal(sourceReceipt(undefined, origin), undefined);
  for (const invalid of [null, [], { ...receipt, chatId: '525599998888@s.whatsapp.net' },
    { ...receipt, text: 'secret' }, { ...receipt, messageKey: { ...receipt.messageKey, fromMe: true } },
    { ...receipt, messageKey: { ...receipt.messageKey, remoteJid: '120363999999@g.us' } },
    { ...receipt, messageKey: { ...receipt.messageKey, id: 'new\nmessage' } }]) {
    assert.throws(() => sourceReceipt(invalid, origin), { code: 'INVALID_RECEIPT' });
  }
});
