'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {createHash}=require('node:crypto');
const {loadAvatarAssets}=require('../service/avatar-assets.cjs');
function model(external=false){
  let json=Buffer.from(JSON.stringify({asset:{version:'2.0'},extensions:{VRM:{meta:{title:'Synthetic',licenseName:'Redistribution_Prohibited'}}},...(external?{images:[{uri:'https://example.invalid/model'}]}:{})}));
  if(json.length%4)json=Buffer.concat([json,Buffer.alloc(4-json.length%4,32)]);
  const head=Buffer.alloc(20);head.write('glTF');head.writeUInt32LE(2,4);head.writeUInt32LE(20+json.length,8);head.writeUInt32LE(json.length,12);head.writeUInt32LE(0x4e4f534a,16);
  return Buffer.concat([head,json]);
}
async function fixture(t,external=false){
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'botsky-avatar-boundary-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const directory=path.join(root,'avatar');await fs.mkdir(directory,{mode:0o700});
  const bytes=model(external),manifest={file:'botsky.vrm',name:'Synthetic',sha256:createHash('sha256').update(bytes).digest('hex'),license:'Redistribution_Prohibited',usage:'private_only'};
  const modelPath=path.join(directory,'botsky.vrm'),manifestPath=path.join(directory,'manifest.json');
  await fs.writeFile(modelPath,bytes,{mode:0o600});await fs.writeFile(manifestPath,JSON.stringify(manifest),{mode:0o600});
  return {root,directory,bytes,manifest,modelPath,manifestPath};
}
test('owned VRM boundary keeps license/hash and bundles without browser or model mutation',async t=>{
  const f=await fixture(t),assets=await loadAvatarAssets(f.root);
  assert.equal(assets.metadata.licenseName,'Redistribution_Prohibited');assert.deepEqual(Buffer.from(assets.base64,'base64'),f.bytes);assert.ok(assets.script.length>10000);
  assert.deepEqual(await fs.readFile(f.modelPath),f.bytes);
});
test('VRM boundary rejects unsafe mode, symlink, changed hash and invented license',async t=>{
  const f=await fixture(t);
  await fs.chmod(f.modelPath,0o644);await assert.rejects(()=>loadAvatarAssets(f.root),/PERMISSIONS/);await fs.chmod(f.modelPath,0o600);
  await fs.rename(f.modelPath,f.modelPath+'.original');await fs.symlink(f.modelPath+'.original',f.modelPath);await assert.rejects(()=>loadAvatarAssets(f.root));
  await fs.unlink(f.modelPath);await fs.rename(f.modelPath+'.original',f.modelPath);
  await fs.writeFile(f.manifestPath,JSON.stringify({...f.manifest,sha256:'0'.repeat(64)}));await assert.rejects(()=>loadAvatarAssets(f.root),/HASH_MISMATCH/);
  await fs.writeFile(f.manifestPath,JSON.stringify({...f.manifest,license:'invented'}));await assert.rejects(()=>loadAvatarAssets(f.root),/LICENSE_MISMATCH/);
});
test('VRM boundary refuses external buffers or textures',async t=>{
  const f=await fixture(t,true);await assert.rejects(()=>loadAvatarAssets(f.root),/EXTERNAL_RESOURCE/);
});
