'use strict';

// WhatsApp's contacts/WID routes reduce a single remote participant to a private
// call. The from-chat route passes the actual group JID to startGroupCall.
function dispatchGroupVoiceCall({ groupId, token, minParticipants = 2, maxParticipants = 2, requireMembership = false, recoveryNativeId, video = false }) {
  if (window.__botskyGroupDispatch?.token === token) return Promise.resolve({ state: 'dispatched' });
  if (window.__botskyAudio?.token !== token) throw Error('CANCELLED');
  const chat = window.WPP?.chat.getActiveChat();
  if ((chat?.id?._serialized || chat?.id?.toString()) !== groupId) throw Error('GROUP_MISMATCH');
  if (requireMembership && (chat.isParentGroup || chat.groupMetadata?.isParentGroup || chat.groupMetadata?.participants?.iAmMember?.() !== true)) throw Error('GROUP_NOT_JOINED');
  const participants = chat.groupMetadata?.participants?.toArray?.();
  if (!Array.isArray(participants) || participants.length < minParticipants || participants.length > maxParticipants) throw Error('GROUP_MISMATCH');
  const collection = window.require('WAWebCallCollection');
  const active = collection.activeCall || collection.lastActiveCall;
  if (recoveryNativeId && (!active || String(active.id) !== recoveryNativeId || active.getState?.() !== 'FAILED' || active.userEndedCall === true || !active.outgoing)) throw Error('RECOVERY_UNSAFE');
  if (active && ![0, 7, 'HANDLED_REMOTELY', 'ENDED', 'FAILED', 'REJECTED', 'NOT_ANSWERED'].includes(active.getState?.())) throw Error('CALL_CHANGED');
  const native = window.require('WAWebVoipStartCall');
  if (typeof native.startWAWebVoipGroupCallFromChat !== 'function') throw Error('GROUP_CALL_UNAVAILABLE');
  window.__botskyGroupDispatch = { token };
  return Promise.resolve(native.startWAWebVoipGroupCallFromChat(chat, video, 8, 5)).then(() => ({ state: 'dispatched' }));
}

module.exports = { dispatchGroupVoiceCall };
