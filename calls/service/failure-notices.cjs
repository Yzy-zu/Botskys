'use strict';

const { ServiceError, terminal } = require('./common.cjs');
const { canonicalPhoneJid } = require('../policy/callDestinations');

const benign = new Set(['requested', 'cancelled', 'cancelled_before_dial', 'remote_or_native_end', 'remote_left',
  'remote_rejected', 'not_answered', 'answer_timeout', 'dial_timeout', 'duration_limit', 'audio_completed',
  'audience_empty', 'service_shutdown']);

function sourceReceipt(receipt, origin) {
  if (receipt === undefined) return undefined;
  const fail = () => { throw new ServiceError('INVALID_RECEIPT', 'El mensaje de origen no es válido.', 400); };
  if (!origin || !receipt || Array.isArray(receipt) || Object.keys(receipt).some(k => !['chatId', 'messageKey'].includes(k)) || receipt.chatId !== origin.chatId) fail();
  const key = receipt.messageKey;
  if (!key || Array.isArray(key) || Object.keys(key).some(k => !['id', 'remoteJid', 'fromMe', 'participant'].includes(k)) ||
      typeof key.id !== 'string' || !/^[A-Za-z0-9._:-]{1,200}$/.test(key.id) || key.fromMe !== false || typeof key.remoteJid !== 'string') fail();
  const group = origin.chatId.endsWith('@g.us');
  if (key.remoteJid !== origin.chatId && (group || (canonicalPhoneJid(key.remoteJid) !== origin.chatId && !/^\d+(?::\d+)?@lid$/.test(key.remoteJid)))) fail();
  if (key.participant !== undefined && (!group || typeof key.participant !== 'string' || !/^\d+(?::\d+)?@(s\.whatsapp\.net|c\.us|lid)$/.test(key.participant))) fail();
  return { chatId: origin.chatId, messageKey: { id: key.id, remoteJid: key.remoteJid, fromMe: false, ...(key.participant ? { participant: key.participant } : {}) } };
}

function needsFailureNotice(record) {
  if (!record.sourceReceipt || !terminal(record.state)) return false;
  if (record.cleanup?.state === 'unconfirmed') return true;
  if (benign.has(record.reason) || benign.has(record.endRequested)) return false;
  return ['failed', 'interrupted'].includes(record.state) || record.recovery?.phase === 'failed' || ['audio_failed', 'live_failed', 'incoming_accept_failed'].includes(record.reason);
}

function queueFailureNotice(record, now) {
  if (!record.failureNotice && needsFailureNotice(record)) record.failureNotice = { state: 'pending', attempts: 0, availableAt: now };
}

module.exports = { sourceReceipt, needsFailureNotice, queueFailureNotice };
