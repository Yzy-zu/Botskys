'use strict';

// These functions execute inside WhatsApp. Lookups finish before the caller's
// cancellation check; the second step dispatches atomically, at most once.
async function resolvePrivatePeer({ targetJid, token, verifyOnly = false }) {
  const normalize = value => String(value?._serialized || value?.toString?.() || '').replace(/:\d+@/, '@').replace(/@c\.us$/, '@s.whatsapp.net').replace(/^521(\d{10})@/, '52$1@');
  const functions = window.WPP?.whatsapp?.functions;
  if (typeof window.WPP?.contact?.queryExists !== 'function' || typeof functions?.startWAWebVoipCall !== 'function' || typeof functions?.getVoipStackInterface !== 'function') throw Error('PRIVATE_CALL_UNAVAILABLE');
  const lookup = async jid => {
    const result = await window.WPP.contact.queryExists(jid);
    if (!result?.wid) return null;
    if (normalize(result.wid) === targetJid) return result;
    // queryWidExists may return a LID directly in wid, even for a phone query.
    if (normalize(result.wid).endsWith('@lid') && typeof window.WPP.contact.getPnLidEntry === 'function') {
      try {
        const mapping = await window.WPP.contact.getPnLidEntry(result.wid);
        if (normalize(mapping?.lid) === normalize(result.wid) && normalize(mapping?.phoneNumber) === targetJid) return result;
      } catch {}
    }
    return null;
  };
  let entry = await lookup(targetJid.replace(/@s\.whatsapp\.net$/, '@c.us'));
  let usedLegacy = false;
  if (!entry && /^52\d{10}@/.test(targetJid)) {
    entry = await lookup(targetJid.replace(/^52/, '521').replace(/@s\.whatsapp\.net$/, '@c.us'));
    usedLegacy = !!entry;
  }
  if (!entry) throw Error('PRIVATE_TARGET_UNVERIFIED');
  const peer = normalize(entry.wid).endsWith('@lid') ? entry.wid : entry.lid || entry.wid;
  const peerId = normalize(peer);
  if (!/^\d+@(lid|s\.whatsapp\.net)$/.test(peerId)) throw Error('PRIVATE_TARGET_UNVERIFIED');
  const me = window.require('WAWebUserPrefsMeUser');
  if (typeof me.isMeAccount !== 'function' || me.isMeAccount(peer) !== false) throw Error('PRIVATE_TARGET_UNVERIFIED');
  if (verifyOnly) return { verified: true, peerIsLid: peerId.endsWith('@lid'), usedLegacy };
  await functions.getVoipStackInterface();
  if (window.__botskyAudio?.token !== token) throw Error('CANCELLED');
  window.__botskyPrivateTarget = { targetJid, token, peer, peerId };
  return { peerId };
}

function dispatchPrivateVoiceCall({ targetJid, token, recoveryNativeId, video = false }) {
  if (window.__botskyPrivateDispatch?.token === token) return Promise.resolve({ dispatched: true });
  const prepared = window.__botskyPrivateTarget;
  if (window.__botskyAudio?.token !== token || prepared?.token !== token || prepared.targetJid !== targetJid) throw Error('CANCELLED');
  const calls = window.require('WAWebCallCollection');
  const call = calls.activeCall || calls.lastActiveCall;
  if (recoveryNativeId && (!call || String(call.id) !== recoveryNativeId || call.getState?.() !== 'FAILED' || call.userEndedCall === true || !call.outgoing)) throw Error('RECOVERY_UNSAFE');
  if (call && ![0, 7, 'HANDLED_REMOTELY', 'ENDED', 'FAILED', 'REJECTED', 'NOT_ANSWERED'].includes(call.getState?.())) throw Error('CALL_CHANGED');
  // Match WA-JS 4.7.2's native voice offer, after resolving the peer. No await
  // between the ownership checks and entering WhatsApp's native dispatch.
  window.__botskyPrivateDispatch = { token };
  return Promise.resolve(window.WPP.whatsapp.functions.startWAWebVoipCall(prepared.peer, video, 8, 5, null, { entryTrust: 'user_gesture' }))
    .then(() => ({ dispatched: true }));
}

module.exports = { resolvePrivatePeer, dispatchPrivateVoiceCall };
