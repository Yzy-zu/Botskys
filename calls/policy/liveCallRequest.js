'use strict';

// Explicit current-message context only; callers must never fill this from history.
function normalizeLiveRequest(live, value) {
    if (value === undefined) return undefined;
    if (live !== true || typeof value !== 'string' || !value.trim() || value.length > 8000) {
        const error = new Error('El encargo inicial de conversación no es válido.');
        error.code = 'INVALID_LIVE_REQUEST'; error.status = 400; throw error;
    }
    return value.trim();
}
module.exports = { normalizeLiveRequest };
