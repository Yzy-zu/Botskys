'use strict';
// Offline compatibility audit: real GLB meshes/bones/morphs, placeholder textures.
// No browser, renderer, account or provider is created.
const path = require('node:path');
const {createHash} = require('node:crypto');
const {loadAvatarAssets} = require('./service/avatar-assets.cjs');
async function inspectAssets(projectRoot) {
  const assets = await loadAvatarAssets(path.join(projectRoot,'private/calls'));
  if (!assets) throw Error('AVATAR_NOT_CONFIGURED');
  const THREE = await import('three');
  const {GLTFLoader} = await import('three/addons/loaders/GLTFLoader.js');
  const {VRMLoaderPlugin,VRMUtils} = await import('@pixiv/three-vrm');
  const {expressionCapabilities,resolveSupportedExpression,appliedExpressionEvidence,resetExpressions} = await import('./service/avatar-expressions.mjs');
  const {createMotionLayer} = await import('./service/avatar-motion.mjs');
  const loader = new GLTFLoader();
  loader.register(()=>({name:'BotskyOfflineTexturePlaceholder',loadTexture:async()=>new THREE.Texture()}));
  loader.register(parser=>new VRMLoaderPlugin(parser));
  const bytes = Buffer.from(assets.base64,'base64');
  const gltf = await loader.parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  const vrm = gltf.userData.vrm;
  if (!vrm?.humanoid?.getNormalizedBoneNode('head')) throw Error('AVATAR_HUMANOID_MISSING');
  let meshes=0,vertices=0,morphMeshes=0;
  vrm.scene.traverse(o=>{if(o.isMesh){meshes++;vertices+=o.geometry?.attributes?.position?.count||0;if(o.morphTargetInfluences?.length)morphMeshes++;}});
  const expressions=expressionCapabilities(vrm.expressionManager,vrm.scene);
  const expressionEffects=[];
  for(const cap of expressions.filter(v=>v.supported&&v.name!=='neutral')){
    resetExpressions(vrm.expressionManager);
    const {expression}=resolveSupportedExpression(vrm.expressionManager,cap.name,vrm.scene);
    vrm.expressionManager.setValue(expression.expressionName,0.8);vrm.update(1/30);
    const evidence=appliedExpressionEvidence(expression,cap,0.8,vrm.scene);
    if(!evidence.applied)throw Error('AVATAR_MORPH_NOT_APPLIED');
    expressionEffects.push({name:cap.name,applied:true});
  }
  resetExpressions(vrm.expressionManager);vrm.update(0);
  vrm.humanoid.getNormalizedBoneNode('leftUpperArm').rotation.z=1.15;
  vrm.humanoid.getNormalizedBoneNode('rightUpperArm').rotation.z=-1.15;
  const layer=createMotionLayer(vrm.humanoid),gestures=layer.capabilities(),gestureEffects=[];
  for(const cap of gestures.filter(v=>v.supported)){
    layer.reset();layer.start(cap.name,2,0);layer.apply(500);
    if(!layer.status().appliedGesture?.applied)throw Error('AVATAR_BONES_NOT_APPLIED');
    gestureEffects.push({name:cap.name,applied:true});
  }
  layer.reset();
  if(!meshes||!vertices||!morphMeshes)throw Error('AVATAR_GEOMETRY_MISSING');
  const result={sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,meshes,vertices,morphMeshes,
    expressions:expressions.map(e=>({name:e.name,supported:e.supported,bindCount:e.bindCount})),expressionEffects,gestures,gestureEffects,
    bundle_bytes:Buffer.byteLength(assets.script),textures:'placeholders only; no GPU/render tested',browser_started:false,providers_started:false};
  VRMUtils.deepDispose(vrm.scene);
  return result;
}
module.exports={inspectAssets};
if(require.main===module){
  if(process.argv.length!==3||!path.isAbsolute(process.argv[2]))throw Error('EXPLICIT_ROOT_REQUIRED');
  inspectAssets(process.argv[2]).then(data=>process.stdout.write(JSON.stringify(data)+'\n')).catch(()=>{process.stderr.write('AVATAR_AUDIT_FAILED\n');process.exitCode=1;});
}
