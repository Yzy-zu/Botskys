'use strict';

// Runs inside WhatsApp's page. Keep this function self-contained for Playwright.
async function readCallSnapshot() {
  const progress = window.__botskySnapshotProgress = { stage: 'reading', at: Date.now() };
  if (!document.querySelector('#pane-side') || !window.WPP?.isReady) throw new Error('Session unavailable');
  const collection = window.require('WAWebCallCollection');
  const call = collection.activeCall || collection.lastActiveCall;
  const state = call?.getState?.();
  const ended = !call || [0, 7, 'HANDLED_REMOTELY', 'ENDED', 'FAILED', 'REJECTED', 'NOT_ANSWERED'].includes(state);
  const lonely = [11, 'ConnectedLonely', 'CONNECTED_LONELY'].includes(state);
  const connected = !ended && (state === 6 || state === 'ACTIVE' || lonely);
  const jid = value => value?._serialized || value?.toString?.() || null;
  const validJid = value => /^\d+(?::\d+)?@(s\.whatsapp\.net|c\.us|lid)$/.test(jid(value) || '');
  const phone = value => {
    const number = jid(value);
    return /^\d+(?::\d+)?@(s\.whatsapp\.net|c\.us)$/.test(number || '') ? number.replace(/@c\.us$/, '@s.whatsapp.net') : null;
  };
  const peerJid = jid(call?.peerJid);
  let peerPhone = phone(call?.peerJid);
  if (!peerPhone && window.__botskyIncoming?.id === String(call?.id)) peerPhone = phone(window.__botskyIncoming.sender);
  if (!peerPhone && peerJid?.endsWith('@lid')) {
    try {
      progress.stage = 'identity_contact';
      const contact = await window.WPP.contact.get(peerJid);
      peerPhone = phone(await contact?.getPnForLid?.()) || phone(contact?.pnForLid);
    } catch {}
    if (!peerPhone) {
      try { progress.stage = 'identity_mapping'; peerPhone = phone((await window.WPP.contact.getPnLidEntry(peerJid))?.phoneNumber); } catch {}
    }
  }
  let audience = { known: false, connectedHumans: null, source: connected ? 'unavailable' : 'not_connected' };
  if (connected) {
    if (lonely) {
      audience = { known: true, connectedHumans: 0, source: 'native_connected_lonely' };
    } else if (call.isGroup === true) {
      try {
        // This is the exact connected list used by WhatsApp's own call UI and
        // watchdog, unlike groupCallParticipants (which also includes invitees).
        const participants = call.groupCallParticipantsConnected;
        const me = window.require('WAWebUserPrefsMeUser');
        if (!Array.isArray(participants) || typeof me.isMeAccount !== 'function' || !participants.every(validJid)) throw new Error('Unsupported participants');
        const humans = new Set();
        for (const participant of participants) {
          const isSelf = me.isMeAccount(participant);
          if (typeof isSelf !== 'boolean') throw new Error('Unknown identity');
          if (!isSelf) humans.add(jid(participant).replace(/:\d+@/, '@').replace(/@c\.us$/, '@s.whatsapp.net'));
        }
        audience = { known: true, connectedHumans: humans.size, source: 'native_connected_participants' };
      } catch { /* Missing or incompatible telemetry is never an empty audience. */ }
    } else if (call.isGroup === false && validJid(call.peerJid)) {
      // A call started from a group of two is represented as a peer call.
      audience = { known: true, connectedHumans: 1, source: 'native_connected_peer' };
    }
  }
  const privateCapabilities = { lookup: false, nativeStart: false, stack: false };
  try {
    privateCapabilities.lookup = typeof window.WPP?.contact?.queryExists === 'function';
    privateCapabilities.nativeStart = typeof window.WPP?.whatsapp?.functions?.startWAWebVoipCall === 'function';
    privateCapabilities.stack = typeof window.WPP?.whatsapp?.functions?.getVoipStackInterface === 'function';
  } catch { /* Capability probing must not break an ongoing call. */ }
  progress.stage = 'complete';
  return { active: !ended, id: call ? String(call.id) : null, connected, state: state ?? null,
    runtimeVersion: window.Debug?.VERSION || null,
    privateCapabilities,
    userEnded: call?.userEndedCall === true,
    outgoing: !!call?.outgoing, isGroup: !!call?.isGroup, isVideo: !!call?.isVideo,
    peerJid, peerPhone, groupId: jid(call?.groupJid), audience,
    audio: window.__botskyAudio?.status() || null };
}

module.exports = { readCallSnapshot };
