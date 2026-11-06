'use strict';

const { getOwnerNumber, normalizePhoneNumber } = require('./auth');
const fail = (code, userMessage) => Object.assign(new Error(userMessage), { code, userMessage });
const nameKey = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();

function canonicalPhoneJid(value, countryCode = '52') {
    if (typeof value !== 'string') return null;
    const input = value.trim();
    const jid = input.match(/^(\d+)(?::\d+)?@(s\.whatsapp\.net|c\.us)$/);
    if (!jid && !/^[+\d\s().-]+$/.test(input)) return null;
    let number = jid ? jid[1] : input.replace(/\D/g, '');
    if (!jid && !input.startsWith('+') && number.length === 10) number = countryCode + number;
    if (number.length === 13 && number.startsWith('521')) number = normalizePhoneNumber(number);
    return /^[1-9]\d{9,14}$/.test(number) ? `${number}@s.whatsapp.net` : null;
}

function callOrigin(from, messageData = {}) {
    if (/^\d+(?:-\d+)?@g\.us$/.test(from || '')) {
        const raw = messageData.key?.participantAlt || messageData.key?.participantPn || messageData.key?.participant || messageData.participant;
        const requesterId = canonicalPhoneJid(raw) || (/^\d+@lid$/.test(raw || '') ? raw : null);
        return requesterId ? { chatId: from, requesterId } : null;
    }
    // A private chat's identity is the chat itself, never a claimed participant.
    const chatId = canonicalPhoneJid(from) || (/^\d+@lid$/.test(from || '') ? canonicalPhoneJid(messageData.key?.remoteJidAlt) : null);
    return chatId ? { chatId, requesterId: chatId } : null;
}

function createCallDestinationPolicy({ lab,
    env = {} } = {}) {
    if (!lab || typeof lab.id !== 'string') throw new Error('Grupo de llamadas inválido');
    const owner = getOwnerNumber(env);
    const ownerJid = owner ? canonicalPhoneJid(owner) : null;
    const countryCode = String(env.CALLS_DEFAULT_COUNTRY_CODE || '52');
    if (!/^[1-9]\d{0,2}$/.test(countryCode)) throw new Error('CALLS_DEFAULT_COUNTRY_CODE inválido');
    const privateIds = new Set([ownerJid].filter(Boolean));
    for (const value of String(env.CALLS_PRIVATE_ALLOWED_NUMBERS || '').split(',').filter(v => v.trim())) {
        const jid = canonicalPhoneJid(value, countryCode);
        if (!jid) throw new Error('CALLS_PRIVATE_ALLOWED_NUMBERS inválido');
        privateIds.add(jid);
    }
    const configured = env.CALLS_GROUPS_JSON ? JSON.parse(env.CALLS_GROUPS_JSON) : [];
    if (!Array.isArray(configured) || configured.length > 50) throw new Error('CALLS_GROUPS_JSON inválido');
    const groups = new Map([[lab.id, { ...lab, kind: 'group' }]]);
    for (const group of configured) {
        if (!group || !/^\d+(?:-\d+)?@g\.us$/.test(group.id || '') || typeof group.name !== 'string' || !group.name.trim() || groups.has(group.id) ||
            !Number.isInteger(group.maxParticipants) || group.maxParticipants < 2 || group.maxParticipants > 32) throw new Error('Destino grupal inválido');
        groups.set(group.id, { id: group.id, name: group.name.trim(), kind: 'group', minParticipants: 2, maxParticipants: group.maxParticipants });
    }
    const ownerPrivate = origin => !!ownerJid && origin?.chatId === ownerJid && origin.requesterId === ownerJid;
    const ownerAnyGroupEnabled = env.CALLS_OWNER_ANY_GROUP_ENABLED === 'true';
    const allGroupsEnabled = env.CALLS_ALL_GROUPS_ENABLED === 'true';
    const groupAudienceValidated = env.CALLS_GROUP_AUDIENCE_VALIDATED === 'true';
    const groupEnabled = id => (id === lab.id && lab.enabled !== false) || (groupAudienceValidated && groups.has(id)) || (allGroupsEnabled && /^\d+(?:-\d+)?@g\.us$/.test(id || ''));
    function authorize(id, origin = null) {
        if (origin !== null && origin !== undefined && (typeof origin !== 'object' || Array.isArray(origin) || typeof origin.chatId !== 'string' || typeof origin.requesterId !== 'string' ||
            (!/^\d+(?:-\d+)?@g\.us$/.test(origin.chatId || '') && canonicalPhoneJid(origin.chatId) !== origin.chatId) ||
            (!/^\d+@lid$/.test(origin.requesterId || '') && canonicalPhoneJid(origin.requesterId) !== origin.requesterId) ||
            (!origin.chatId.endsWith('@g.us') && origin.chatId !== origin.requesterId))) {
            throw fail('CALL_IDENTITY_UNKNOWN', 'No pude verificar el origen de la llamada.');
        }
        const phone = canonicalPhoneJid(id, countryCode);
        const groupId = /^\d+(?:-\d+)?@g\.us$/.test(id || '');
        const dynamicGroup = (ownerAnyGroupEnabled || allGroupsEnabled) && ownerPrivate(origin) && groupId;
        // An authenticated message from an admitted group proves the current
        // chat context; arbitrary group IDs still require owner order + lookup.
        const currentGroup = allGroupsEnabled && groupId && origin?.chatId === id;
        const target = (!allGroupsEnabled && groups.get(id)) || (dynamicGroup || currentGroup ? { id, kind: 'group', name: 'grupo de WhatsApp', minParticipants: 2, maxParticipants: Number.MAX_SAFE_INTEGER, requireMembership: true } : null) || (phone ? { id: phone, kind: 'private', name: 'llamada privada' } : null);
        if (!target || (target.kind === 'group' && !groupEnabled(target.id) && !dynamicGroup)) throw fail('DESTINATION_NOT_ENABLED', 'Ese destino todavía no está habilitado para llamadas.');
        const local = origin?.chatId === target.id;
        if (origin && !local && (env.CALLS_SAME_CHAT_ONLY === 'true' || !ownerPrivate(origin))) throw fail('CALL_DESTINATION_DENIED', 'Solo puedes encargar llamadas a otro chat desde el privado del propietario.');
        if (target.kind === 'private' && !privateIds.has(target.id) && !(ownerPrivate(origin) && env.CALLS_OWNER_EXTERNAL_ENABLED === 'true')) {
            throw fail('DESTINATION_NOT_ENABLED', 'Ese chat privado todavía no está habilitado para llamadas.');
        }
        return { ...target };
    }
    return { lab, ownerJid, countryCode, groups: [...groups.values()], privateIds,
        ownerAnyGroupEnabled: ownerAnyGroupEnabled || allGroupsEnabled, allGroupsEnabled, ownerExternalEnabled: env.CALLS_OWNER_EXTERNAL_ENABLED === 'true', groupAudienceValidated, ownerPrivate, groupEnabled, authorize,
        localEnabled: origin => !!origin && (origin.chatId.endsWith('@g.us') ? groupEnabled(origin.chatId) : privateIds.has(origin.chatId)),
    };
}

function canControlCall(call, origin, policy) {
    if (!call || !origin) return false;
    const destination = call.targetJid || call.groupId;
    return destination === origin.chatId || (policy.ownerPrivate(origin) && call.origin?.chatId === origin.chatId && call.origin?.requesterId === origin.requesterId);
}

module.exports = { canonicalPhoneJid, callOrigin, createCallDestinationPolicy, canControlCall };
