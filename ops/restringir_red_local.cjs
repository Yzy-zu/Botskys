'use strict';
// Local acceptance harness only. Not installed in the application/runtime.
const net = require('node:net');
const original = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const normalized = Array.isArray(args[0]) ? args[0] : args;
  const first = normalized[0];
  const options = first && typeof first === 'object' ? first : {};
  if (!options.path && (typeof first !== 'string' || /^\d+$/.test(first))) {
    const host = options.host || (typeof normalized[1] === 'string' ? normalized[1] : 'localhost');
    if (!['localhost', '127.0.0.1', '::1'].includes(host)) {
      const error = Error('R10_NON_LOOPBACK_NETWORK_DENIED');
      error.code = 'R10_NON_LOOPBACK_NETWORK_DENIED';
      throw error;
    }
  }
  return original.apply(this, args);
};
