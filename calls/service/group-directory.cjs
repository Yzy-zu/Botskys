'use strict';

// Runs inside the account's browser. No opening chats, invitation acceptance or calls.
async function resolveJoinedGroup({ name, id }) {
  const key = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const jid = chat => chat?.id?._serialized || chat?.id?.toString();
  const title = chat => chat?.groupMetadata?.subject || chat?.name || chat?.formattedTitle || '';
  const chats = (await window.WPP.group.getAllGroups()).filter(chat => /^\d+(?:-\d+)?@g\.us$/.test(jid(chat) || '') && !chat.isParentGroup && !chat.groupMetadata?.isParentGroup);
  const exact = chats.filter(chat => id ? jid(chat) === id : key(title(chat)) === key(name));
  const candidates = exact.length || id ? exact : chats.filter(chat => key(name) && key(title(chat)).includes(key(name)));
  const joined = []; let unverified = false;
  for (const chat of candidates) {
    try {
      await window.WPP.group.getParticipants(jid(chat));
      const member = chat.groupMetadata?.participants?.iAmMember?.();
      if (member === true) joined.push({ id: jid(chat), name: String(title(chat)) });
      else if (member !== false) unverified = true;
    } catch { unverified = true; }
    if (joined.length > 1) return { error: 'ambiguous' };
  }
  if (unverified) return { error: 'unverified' };
  return joined.length === 1 ? { group: joined[0] } : { error: 'not_found' };
}
module.exports = { resolveJoinedGroup };
