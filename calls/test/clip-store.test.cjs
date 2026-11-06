// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs/promises'), os = require('node:os'), path = require('node:path');
const { Readable } = require('node:stream');
const { ClipStore } = require('../service/clip-store.cjs');
test('local clips normalize with audio, persist, deduplicate the demo and release failed imports', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-clips-'));
  const store = new ClipStore(dir); await store.init();
  t.after(async () => { await store.close(); await fs.rm(dir, { recursive: true, force: true }); });
  await assert.rejects(store.importStream(Readable.from([Buffer.from('not video')])), { code: 'CLIP_PROCESS_FAILED' });
  assert.equal(store.busy, false);
  const asset = await store.demo();
  assert.equal(asset.mimeType, 'video/webm'); assert.ok(asset.durationSeconds >= 11 && asset.durationSeconds <= 13);
  assert.equal((await store.demo()).id, asset.id); assert.equal((await store.list()).length, 1);
  assert.equal((await store.read(asset.id)).data.length, asset.bytes);
  const renamed = await store.update({ id: asset.id, label: 'Colores', aliases: ['prueba', 'arcoiris'] });
  assert.deepEqual(renamed.aliases, ['prueba', 'arcoiris']);
  assert.equal((await store.demo()).id, asset.id); assert.equal((await store.list()).length, 1);
  await fs.writeFile(path.join(store.dir, asset.id + '.webm'), 'incomplete');
  await assert.rejects(store.read(asset.id), { code: 'CLIP_INVALID' });
});
