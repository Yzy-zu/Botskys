'use strict';

// Inspect provider details only to classify them. Never retain their messages,
// close reasons, credential identifiers or HTTP response bodies.
function liveSetupError(error = {}) {
  const code = Number(error.code);
  const status = String(error.status || '').toUpperCase();
  const reasons = Array.isArray(error.details) ? error.details.map(detail => detail?.reason).filter(reason => typeof reason === 'string') : [];
  if (reasons.some(reason => /^API_KEY_(INVALID|EXPIRED|NOT_FOUND|SERVICE_BLOCKED|HTTP_REFERRER_BLOCKED|IP_ADDRESS_BLOCKED)$/.test(reason))) return 'LIVE_KEY_REJECTED';
  if ([401, 403, 16, 7].includes(code) || ['UNAUTHENTICATED', 'PERMISSION_DENIED'].includes(status)) return 'LIVE_KEY_REJECTED';
  if ([429, 8].includes(code) || status === 'RESOURCE_EXHAUSTED') return 'LIVE_QUOTA_EXCEEDED';
  if ([408, 500, 502, 503, 504, 4, 13, 14].includes(code) || ['DEADLINE_EXCEEDED', 'INTERNAL', 'UNAVAILABLE'].includes(status)) return 'LIVE_PROVIDER_UNAVAILABLE';
  if ([404, 5].includes(code) || status === 'NOT_FOUND') return 'LIVE_MODEL_UNAVAILABLE';
  if ([400, 3].includes(code) || status === 'INVALID_ARGUMENT') return 'LIVE_REQUEST_INVALID';
  return 'LIVE_PROVIDER_ERROR';
}

function liveCloseError(code, reason) {
  // Google can reject setup via a WebSocket close instead of a JSON error.
  const text = String(reason || '').slice(0, 4096);
  if (/api[_ ]?key.{0,50}(invalid|expired|not valid|not found|blocked)|API_KEY_(INVALID|EXPIRED)|unauthenticated|permission.denied/i.test(text)) return 'LIVE_KEY_REJECTED';
  if (/resource.exhausted|quota|rate.limit|too many requests/i.test(text)) return 'LIVE_QUOTA_EXCEEDED';
  if (/unavailable|overload|internal.error|deadline.exceeded/i.test(text) || [1011, 1012, 1013].includes(code)) return 'LIVE_PROVIDER_UNAVAILABLE';
  if (/not.found|unsupported.model/i.test(text)) return 'LIVE_MODEL_UNAVAILABLE';
  if (code === 1007 || /invalid.argument|invalid.json|unknown.field/i.test(text)) return 'LIVE_REQUEST_INVALID';
  return 'LIVE_SOCKET_CLOSED';
}

const NEXT_KEY_ERRORS = new Set(['LIVE_KEY_REJECTED', 'LIVE_QUOTA_EXCEEDED', 'LIVE_PROVIDER_UNAVAILABLE',
  'LIVE_SETUP_TIMEOUT', 'LIVE_SOCKET_CLOSED', 'LIVE_SOCKET_ERROR']);

module.exports = { liveSetupError, liveCloseError, NEXT_KEY_ERRORS };
