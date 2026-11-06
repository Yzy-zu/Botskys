"use strict";
const { ServiceError } = require('./common.cjs');
async function liveKeys(config = {}) {
  if (typeof config.key !== 'string' || !config.key.trim() || /[\x00-\x1f\x7f]/.test(config.key)) throw new ServiceError('LIVE_NO_KEY','Live no está configurado.',503);
  return [config.key];
}
module.exports = {liveKeys};
