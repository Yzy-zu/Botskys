'use strict';
const fs = require('node:fs/promises');
const { atomicJson, ServiceError } = require('./common.cjs');
const names = ['outgoing', 'incoming', 'live', 'agenda'];
const valid = patch => patch && !Array.isArray(patch) && typeof patch === 'object' && Object.keys(patch).every(k => names.includes(k) && typeof patch[k] === 'boolean');
class FeatureControls {
  constructor({ file, base = {}, log = () => {} }) { Object.assign(this, { file, log }); this.base = Object.fromEntries(names.map(k => [k, base[k] !== false])); this.overrides = {}; this.queue = Promise.resolve(); this.value = { ...this.base }; }
  async init() {
    try {
      const data = JSON.parse(await fs.readFile(this.file, 'utf8'));
      if (data.version !== 1 || !valid(data.overrides)) throw Error('schema');
      this.overrides = data.overrides;
    } catch (error) { if (error.code !== 'ENOENT') throw new ServiceError('FEATURE_CONTROLS_INVALID', 'Los controles operativos no son válidos; no se iniciará el servicio.', 500); }
    this.publish(); await atomicJson(this.file, { version: 1, overrides: this.overrides });
  }
  publish() { this.value = Object.fromEntries(names.map(k => [k, this.base[k] && this.overrides[k] !== false])); }
  status() { return { enabled: { ...this.value }, configured: { ...this.base } }; }
  update(patch) {
    const work = this.queue.then(async () => {
      if (!valid(patch) || !Object.keys(patch).length) throw new ServiceError('INVALID_FEATURE_CONTROLS', 'Usa únicamente outgoing, incoming, live o agenda con true/false.', 400);
      if (Object.entries(patch).some(([key, value]) => value && !this.base[key])) throw new ServiceError('FEATURE_NOT_CONFIGURED', 'Esa función está desactivada en la configuración de despliegue.', 409);
      const next = { ...this.overrides, ...patch };
      await atomicJson(this.file, { version: 1, overrides: next });
      this.overrides = next; this.publish(); this.log('features_updated', { ...patch });
      return this.status();
    });
    this.queue = work.catch(() => {}); return work;
  }
}
module.exports = { FeatureControls };
