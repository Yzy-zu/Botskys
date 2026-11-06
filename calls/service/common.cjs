'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

class ServiceError extends Error {
  constructor(code, message, status = 409) { super(message); this.code = code; this.status = status; }
}

async function atomicJson(file, data) {
  await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  const temp = `${file}.${process.pid}.${crypto.randomUUID()}.tmp`;
  const handle = await fs.open(temp, 'wx', 0o600);
  try { await handle.writeFile(JSON.stringify(data, null, 2) + '\n'); await handle.sync(); }
  finally { await handle.close(); }
  try { await fs.rename(temp, file); }
  finally { await fs.rm(temp, { force: true }); }
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const terminal = state => ['ended', 'failed', 'interrupted'].includes(state);

module.exports = { ServiceError, atomicJson, sleep, terminal };
