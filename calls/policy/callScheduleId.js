'use strict';

function normalizeCallScheduleId(value) {
    if (typeof value !== 'string') return null;
    const id = value.trim().replace(/^#\s*/, '').toLowerCase();
    return /^[a-f0-9-]{8,36}$/.test(id) ? id : null;
}
module.exports = { normalizeCallScheduleId };
