// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { dispatchGroupVoiceCall } = require('../service/group-call.cjs');
const { dispatchPrivateVoiceCall } = require('../service/private-call.cjs');

for (const [kind, dispatch] of [['group', dispatchGroupVoiceCall], ['private', dispatchPrivateVoiceCall]]) {
  test(`PM05B: ${kind} native dispatch rechecks a confirmed failed call atomically before its only recovery offer`, async () => {
    for (const [state, id, outgoing, userEndedCall, allowed] of [
      ['FAILED', 'old', true, false, true], ['ENDED', 'old', true, false, false],
      ['REJECTED', 'old', true, false, false], ['NOT_ANSWERED', 'old', true, false, false],
      [0, 'old', true, false, false], ['FAILED', 'foreign', true, false, false],
      ['FAILED', 'old', false, false, false], ['FAILED', 'old', true, true, false]
    ]) {
      let offers = 0;
      const call = { id, outgoing, userEndedCall, getState: () => state };
      const chat = { id: { _serialized: 'lab@g.us' }, groupMetadata: { participants: { toArray: () => [{}, {}] } } };
      const nativeOffer = () => { offers++; return Promise.resolve(); };
      const window = {
        __botskyAudio: { token: 'recovery-token' },
        __botskyPrivateTarget: { targetJid: '525511112222@s.whatsapp.net', token: 'recovery-token', peer: {} },
        WPP: { chat: { getActiveChat: () => chat }, whatsapp: { functions: { startWAWebVoipCall: nativeOffer } } },
        require(name) {
          if (name === 'WAWebCallCollection') return { lastActiveCall: call };
          if (name === 'WAWebVoipStartCall') return { startWAWebVoipGroupCallFromChat: nativeOffer };
          throw Error('unexpected module');
        }
      };
      const args = { groupId: 'lab@g.us', targetJid: '525511112222@s.whatsapp.net', token: 'recovery-token', recoveryNativeId: 'old' };
      const invoke = async () => vm.runInNewContext(`(${dispatch.toString()})(args)`, { window, args });
      if (allowed) { await invoke(); await invoke(); assert.equal(offers, 1); }
      else { await assert.rejects(invoke(), /RECOVERY_UNSAFE/); assert.equal(offers, 0); }
    }
  });
}
