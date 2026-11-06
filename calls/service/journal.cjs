'use strict';
const { normalizeLiveRequest } = require('../policy/liveCallRequest');

const fs = require('node:fs/promises');
const { sourceReceipt } = require('./failure-notices.cjs');
const { atomicJson, ServiceError } = require('./common.cjs');

class Journal {
  constructor(file) { this.file = file; this.records = []; this.cancelledKeys = {}; this.writes = Promise.resolve(); }
  async load() {
    try {
      const data = JSON.parse(await fs.readFile(this.file, 'utf8'));
      if (data.version !== 1 || !Array.isArray(data.records) || data.records.some(r => !r.id || !r.key || !r.state || !Number.isFinite(r.requestedAt) || (r.recovery !== undefined && (!r.recovery || r.recovery.attempts !== 1 || !['checking', 'waiting', 'redial_reserved', 'redialing', 'recovered', 'failed'].includes(r.recovery.phase) || !Number.isFinite(r.recovery.claimedAt) || !Number.isFinite(r.recovery.deadline) || typeof r.recovery.originalNativeId !== 'string' || typeof r.recovery.redialUsed !== 'boolean')))) {
        throw new Error('Invalid journal schema');
      }
      let recoveredNotice = false;
      for (const record of data.records) {
        normalizeLiveRequest(record.live, record.liveRequest);
        sourceReceipt(record.sourceReceipt, record.origin);
        const notice = record.failureNotice;
        if (notice !== undefined && (!record.sourceReceipt || !notice || !['pending', 'claimed', 'sending', 'sent', 'failed', 'uncertain', 'abandoned'].includes(notice.state) ||
          !Number.isInteger(notice.attempts) || notice.attempts < 0 || notice.attempts > 3 || !Number.isFinite(notice.availableAt) ||
          (['claimed', 'sending'].includes(notice.state) && (typeof notice.lease !== 'string' || !/^[a-f0-9-]{36}$/.test(notice.lease))))) throw new Error('Invalid failure notice');
        if (notice?.state === 'sending') {
          // The external POST may have crossed the process boundary. Never issue it again.
          Object.assign(notice, { state: 'uncertain', availableAt: Date.now() });
          recoveredNotice = true;
        }
      }
      this.records = data.records;
      if (data.cancelledKeys !== undefined && (!data.cancelledKeys || typeof data.cancelledKeys !== 'object' || Array.isArray(data.cancelledKeys) || Object.entries(data.cancelledKeys).some(([k, v]) => !/^[A-Za-z0-9._:-]{8,128}$/.test(k) || !Number.isFinite(v)))) throw new Error('Invalid cancellations');
      this.cancelledKeys = data.cancelledKeys || {};
      if (recoveredNotice) await this.save();
    } catch (error) {
      if (error.code !== 'ENOENT') throw new ServiceError('JOURNAL_INVALID', 'El historial de llamadas no se puede leer; no se marcará ninguna llamada.', 500);
    }
  }
  save() {
    const snapshot = { version: 1, records: structuredClone(this.records), cancelledKeys: { ...this.cancelledKeys } };
    const write = this.writes.then(() => atomicJson(this.file, snapshot));
    this.writes = write.catch(() => {});
    return write;
  }
  prune(now) { this.records = this.records.filter(r => !r.endedAt || r.endedAt > now - 24 * 60 * 60 * 1000); }
  byKey(key) { return this.records.find(r => r.key === key); }
  byId(id) { return this.records.find(r => r.id === id); }
}

module.exports = { Journal };
