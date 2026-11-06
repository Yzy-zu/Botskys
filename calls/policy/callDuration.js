'use strict';

function normalizeCallDuration(live, value) {
    if (live === true && (value === undefined || value === null)) return null;
    if (value === undefined) value = 60;
    if (!Number.isSafeInteger(value) || value < 5 || !Number.isSafeInteger(value * 1000) ||
        !Number.isFinite(new Date(value * 1000).getTime()) || (!live && value > 960)) {
        throw Object.assign(new Error(live ? 'Indica una duración entera de al menos 5 segundos.' :
            'La duración debe ser un entero entre 5 y 960 segundos.'), { code: 'INVALID_DURATION', status: 400 });
    }
    return value;
}

module.exports = { normalizeCallDuration };
