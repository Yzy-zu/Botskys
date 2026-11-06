'use strict';

const fail = (code, message) => Object.assign(new Error(message), { code, userMessage: message, status: 400 });

function createSchedulePolicy(env = {}) {
    const policy = { enabled: env.CALLS_SCHEDULE_ENABLED === 'true', timeZone: env.CALLS_SCHEDULE_TIMEZONE || 'America/Mexico_City',
        startHour: Number(env.CALLS_SCHEDULE_START_HOUR ?? 8), endHour: Number(env.CALLS_SCHEDULE_END_HOUR ?? 23), maxLatenessMs: 60000 };
    new Intl.DateTimeFormat('en', { timeZone: policy.timeZone });
    if (!Number.isInteger(policy.startHour) || !Number.isInteger(policy.endHour) || policy.startHour < 0 || policy.endHour > 24 || policy.startHour >= policy.endHour) throw Error('Horario de agenda inválido');
    return policy;
}
function validateScheduledTime(dueAt, policy, { now = Date.now(), maxSeconds } = {}) {
    if (!policy?.enabled) throw fail('SCHEDULE_DISABLED', 'Las llamadas programadas aún no están habilitadas.');
    if (!Number.isSafeInteger(dueAt) || dueAt <= now || !Number.isFinite(new Date(dueAt).getTime())) throw fail('SCHEDULE_TIME_INVALID', 'Dime una fecha y hora futuras para la llamada.');
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: policy.timeZone, hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit' }).formatToParts(dueAt).map(p => [p.type, p.value]));
    const second = Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second);
    const hours = `${String(policy.startHour).padStart(2, '0')}:00–${String(policy.endHour).padStart(2, '0')}:00`;
    if (second < policy.startHour * 3600 || second >= policy.endHour * 3600) throw fail('SCHEDULE_OUTSIDE_HOURS', `¿Qué otra hora prefieres? Las llamadas programadas van de ${hours}, ${policy.timeZone === 'America/Mexico_City' ? 'hora de Ciudad de México' : policy.timeZone}.`);
    if (maxSeconds !== undefined && dueAt + ((maxSeconds ?? 5) + 90) * 1000 > scheduledWindowEnd(dueAt, policy)) throw fail('SCHEDULE_WINDOW_SHORT', 'Elige una hora más temprano para que dé tiempo de contestar y terminar la llamada antes del cierre.');
    return dueAt;
}
function scheduledWindowEnd(timestamp, policy) {
    const formatter = new Intl.DateTimeFormat('en-GB', { timeZone: policy.timeZone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const parts = time => Object.fromEntries(formatter.formatToParts(time).map(p => [p.type, Number(p.value)]));
    const local = parts(timestamp);
    const target = Date.UTC(local.year, local.month - 1, local.day, policy.endHour);
    let candidate = target;
    for (let i = 0; i < 5; i++) {
        const p = parts(candidate);
        const delta = target - Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
        if (!delta) return candidate;
        candidate += delta;
    }
    throw fail('SCHEDULE_TIME_INVALID', 'No se pudo resolver el cierre del horario.');
}
function formatScheduledTime(timestamp, timeZone) {
    return new Intl.DateTimeFormat('es-MX', { timeZone, dateStyle: 'medium', timeStyle: 'short' }).format(timestamp);
}
module.exports = { createSchedulePolicy, validateScheduledTime, formatScheduledTime, scheduledWindowEnd };
