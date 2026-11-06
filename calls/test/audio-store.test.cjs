// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Readable, PassThrough } = require('node:stream');
const { AudioStore, toneWave, MAX_UPLOAD } = require('../service/audio-store.cjs');

async function fixture(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-audio-'));
  const store = new AudioStore(dir); await store.init();
  t.after(async () => { await store.close(); await fs.rm(dir, { recursive: true, force: true }); });
  return { store, dir };
}

test('Real FFmpeg conversion produces bounded mono PCM, deduplicates and detects corruption', async t => {
  const { store } = await fixture(t);
  const asset = await store.importStream(Readable.from([toneWave()]));
  assert.equal(asset.id, store.tone.id); assert.equal((await store.list()).length, 1);
  assert.equal(asset.sampleRate, 48000); assert.equal(asset.channels, 1);
  assert.ok(Math.abs(asset.durationSeconds - 1.4) < 0.02);
  const result = await store.read(asset.id); assert.equal(result.data.toString('ascii', 0, 4), 'RIFF');
  assert.equal((await fs.stat(path.join(store.dir, `${asset.id}.wav`))).mode & 0o777, 0o600);
  await fs.writeFile(path.join(store.dir, `${asset.id}.wav`), 'tampered');
  await assert.rejects(store.read(asset.id), { code: 'AUDIO_INVALID' });
  await assert.rejects(store.get('../../secret'), { code: 'INVALID_AUDIO_ID' });
  await fs.writeFile(path.join(store.dir, `${asset.id}.json`), JSON.stringify({ ...asset, id: '../../wrong' }));
  await assert.rejects(store.get(asset.id), { code: 'AUDIO_INVALID' });
});

test('Compressed music is decoded by content instead of a filename extension', async t => {
  const { store, dir } = await fixture(t);
  const input = path.join(dir, 'source.wav'), compressed = path.join(dir, 'music.ogg');
  await fs.writeFile(input, toneWave(3));
  await store.run('ffmpeg', ['-v', 'error', '-y', '-i', input, '-c:a', 'libopus', compressed]);
  const asset = await store.importStream(Readable.from([await fs.readFile(compressed)]));
  assert.ok(Math.abs(asset.durationSeconds - 3) < 0.05);
  assert.equal(asset.sampleRate, 48000); assert.equal(asset.channels, 1);
});

test('Empty, oversized, overlong and playlist inputs are rejected and cleaned up', async t => {
  const { store, dir } = await fixture(t);
  await assert.rejects(store.importStream(Readable.from([])), { code: 'AUDIO_EMPTY' });
  await assert.rejects(store.importStream(Readable.from([Buffer.alloc(MAX_UPLOAD + 1)])), { code: 'AUDIO_TOO_LARGE' });
  const overlong = path.join(dir, 'overlong.flac');
  await store.run('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono', '-t', '901', '-c:a', 'flac', overlong], 30000);
  await assert.rejects(store.importStream(Readable.from([await fs.readFile(overlong)])), { code: 'AUDIO_DURATION' });
  const validFile = path.join(dir, 'valid.wav'); await fs.writeFile(validFile, toneWave());
  const playlist = Buffer.from(`ffconcat version 1.0\nfile '${validFile}'\n`);
  await assert.rejects(store.importStream(Readable.from([playlist])), { code: 'AUDIO_PROCESS_FAILED' });
  assert.deepEqual(await fs.readdir(path.join(store.dir, 'tmp')), []);
  assert.equal((await store.list()).length, 1);
});

test('Only one preparation job runs at a time', async t => {
  const { store } = await fixture(t);
  const stream = new PassThrough();
  const first = store.importStream(stream);
  await assert.rejects(store.importStream(Readable.from([toneWave()])), { code: 'AUDIO_PREPARING' });
  stream.end(toneWave()); await first;
  assert.equal(store.jobs.size, 0);
});

test('Ten-minute compressed audio is normalized and read completely, beyond the old PCM limit', async t => {
  const { store, dir } = await fixture(t);
  const input = path.join(dir, 'ten-minutes.flac');
  await store.run('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono', '-t', '600', '-c:a', 'flac', input], 30000);
  const asset = await store.importStream(Readable.from([await fs.readFile(input)]));
  assert.ok(Math.abs(asset.durationSeconds - 600) < 0.02);
  assert.ok(asset.bytes > 57000000);
  assert.equal((await store.read(asset.id)).data.length, asset.bytes);
});

test('PM05A: cancellation interrupts an upload waiting for the next chunk', async t => {
  const { store } = await fixture(t);
  const stream = new PassThrough(), controller = new AbortController();
  const work = store.importStream(stream, { signal: controller.signal });
  const rejected = assert.rejects(work, /cancel upload/);
  // Wait until the file and stream iterator are installed.
  while (!stream.listenerCount('readable')) await new Promise(resolve => setImmediate(resolve));
  controller.abort(new Error('cancel upload')); await rejected;
  assert.equal(store.busy, false);
});
