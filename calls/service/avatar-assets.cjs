'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { build } = require('esbuild');
async function loadAvatarAssets(privateDir) {
  let manifest;
  try { manifest = JSON.parse(await fs.readFile(path.join(privateDir, 'avatar/manifest.json'), 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  if (manifest.file !== 'botsky.vrm') throw Error('Unknown avatar asset');
  const model = await fs.readFile(path.join(privateDir, 'avatar', manifest.file));
  if (createHash('sha256').update(model).digest('hex') !== manifest.sha256) throw Error('Avatar asset is incomplete');
  const options = { bundle: true, format: 'iife', platform: 'browser', minify: true, write: false, logLevel: 'silent' };
  const worker = await build({ ...options, entryPoints: [path.join(__dirname, 'avatar-worker.mjs')] });
  const output = await build({ ...options, entryPoints: [path.join(__dirname, 'avatar-client.mjs')], define: { AVATAR_WORKER_SOURCE: JSON.stringify(worker.outputFiles[0].text) } });
  return { script: output.outputFiles[0].text, base64: model.toString('base64'), name: manifest.name };
}
module.exports = { loadAvatarAssets };
