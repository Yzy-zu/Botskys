'use strict';

const { cleanJidNumber, normalizePhoneNumber, getOwnerNumber } = require('../policy/auth');

function createIncomingPolicy(env = {}) {
  const owner = getOwnerNumber(env);
  const enabled = env.CALLS_AUTOANSWER_OWNER === 'true' && /^\d{10,15}$/.test(owner);
  return {
    enabled,
    allows(snapshot) {
      if (!enabled || !snapshot.active || snapshot.outgoing || snapshot.isGroup || snapshot.groupId ||
        ![3, 'INCOMING_RING'].includes(snapshot.state)) return false;
      const jid = snapshot.peerPhone || snapshot.peerJid;
      if (typeof jid !== 'string' || !/^\d+(?::\d+)?@s\.whatsapp\.net$/.test(jid)) return false;
      return normalizePhoneNumber(cleanJidNumber(jid)) === owner;
    }
  };
}

module.exports = { createIncomingPolicy };
