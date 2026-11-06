'use strict';
// Identity primitives only; no historical admin/school policy or environment discovery.
function cleanJidNumber(jid) {
    if (!jid || typeof jid !== 'string') return '';
    const trimmed = jid.trim();
    if (trimmed.endsWith('@lid') || trimmed.includes('@lid')) {
        return '';
    }
    const withoutServer = trimmed.split('@')[0];
    const withoutDevice = withoutServer.split(':')[0];
    return withoutDevice.replace(/[^0-9]/g, '');
}

function normalizePhoneNumber(num) {
    if (!num || typeof num !== 'string') return '';
    const clean = num.replace(/[^0-9]/g, '');
    if (clean.length === 13 && clean.startsWith('521')) {
        return '52' + clean.slice(3);
    }
    if (clean.length === 10) {
        return '52' + clean;
    }
    return clean;
}

function getOwnerNumber(env = {}) {
    const configured = env.BOTSKY_OWNER_NUMBER || env.CALLS_INCOMING_OWNER;
    const candidates = String(configured || env.ALLOWED_NUMBERS_ADMIN || '').split(',').map(value => value.trim()).filter(Boolean);
    if (candidates.length !== 1) return '';
    const number = normalizePhoneNumber(cleanJidNumber(candidates[0]));
    return /^\d{10,15}$/.test(number) ? number : '';
}
module.exports = { cleanJidNumber, normalizePhoneNumber, getOwnerNumber };
