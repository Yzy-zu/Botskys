'use strict';
// Local asset boundary; rendering/motion code remains the ported Zhana implementation.
const fsp = require('node:fs/promises');
const { constants } = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { build } = require('esbuild');
const MAX_MODEL = 50 * 1024 * 1024;
async function readOwned(file, maximum) {
  const handle = await fsp.open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || !stat.size || stat.size > maximum || (stat.mode & 0o077)) throw Error('AVATAR_ASSET_PERMISSIONS');
    const data = await handle.readFile();
    if (data.length !== stat.size) throw Error('AVATAR_ASSET_CHANGED');
    return data;
  } finally { await handle.close(); }
}
function validateModel(model, manifest) {
  if (model.length < 20 || model.toString('ascii',0,4) !== 'glTF' || model.readUInt32LE(4) !== 2 ||
      model.readUInt32LE(8) !== model.length || model.readUInt32LE(16) !== 0x4e4f534a ||
      model.readUInt32LE(12) > 4*1024*1024 || model.readUInt32LE(12)+20 > model.length) throw Error('AVATAR_INVALID_GLB');
  const doc = JSON.parse(model.toString('utf8',20,20+model.readUInt32LE(12)));
  if ([...(doc.buffers||[]),...(doc.images||[])].some(v=>v.uri && !v.uri.startsWith('data:'))) throw Error('AVATAR_EXTERNAL_RESOURCE');
  const meta = doc.extensions?.VRMC_vrm?.meta || doc.extensions?.VRM?.meta;
  if (!meta || (meta.licenseName || meta.licenseUrl) !== manifest.license || manifest.usage !== 'private_only') throw Error('AVATAR_LICENSE_MISMATCH');
  return meta;
}
async function loadAvatarAssets(privateDir) {
  const directory = path.join(privateDir,'avatar');
  try { if ((await fsp.lstat(directory)).isSymbolicLink()) throw Error('AVATAR_ASSET_SYMLINK'); }
  catch(error) { if (error.code === 'ENOENT') return null; throw error; }
  let manifest;
  try { manifest = JSON.parse(await readOwned(path.join(directory,'manifest.json'),65536)); }
  catch(error) { if (error.code === 'ENOENT') return null; throw error; }
  if (manifest.file !== 'botsky.vrm' || !/^[a-f0-9]{64}$/.test(manifest.sha256)) throw Error('AVATAR_MANIFEST_INVALID');
  const model = await readOwned(path.join(directory,manifest.file),MAX_MODEL);
  if (createHash('sha256').update(model).digest('hex') !== manifest.sha256) throw Error('AVATAR_HASH_MISMATCH');
  const metadata = validateModel(model,manifest);
  const options = { bundle: true, format: 'iife', platform: 'browser', minify: true, write: false, logLevel: 'silent' };
  const worker = await build({ ...options, entryPoints: [path.join(__dirname,'avatar-worker.mjs')] });
  const output = await build({ ...options, entryPoints: [path.join(__dirname,'avatar-client.mjs')], define: { AVATAR_WORKER_SOURCE: JSON.stringify(worker.outputFiles[0].text) } });
  return {script:output.outputFiles[0].text,base64:model.toString('base64'),name:manifest.name,metadata};
}
module.exports = {loadAvatarAssets,validateModel};
