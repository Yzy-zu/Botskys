import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { AVATAR_WIDTH, AVATAR_HEIGHT, AVATAR_CAMERA_DISTANCE } from './avatar-quality.mjs';
import { trimLowerBody, removeOutlinePasses } from './avatar-geometry.mjs';
import { createMotionLayer } from './avatar-motion.mjs';
import { appliedExpressionEvidence, expressionCapabilities, resetExpressionEvidence, resetExpressions, resolveSupportedExpression } from './avatar-expressions.mjs';

let modelBytes;
globalThis.__botskyAvatarRenderer = {
  prepare(base64) {
    const raw = atob(base64); modelBytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) modelBytes[i] = raw.charCodeAt(i);
  },
  create({ mouthLevel = () => 0 } = {}) {
    if (!modelBytes) throw Error('AVATAR_NOT_LOADED');
    const renderer = new THREE.WebGLRenderer({ canvas: new OffscreenCanvas(AVATAR_WIDTH, AVATAR_HEIGHT), alpha: true, antialias: false, preserveDrawingBuffer: true, powerPreference: 'low-power' });
    renderer.setPixelRatio(1); renderer.setSize(AVATAR_WIDTH, AVATAR_HEIGHT, false); renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(38, AVATAR_WIDTH / AVATAR_HEIGHT, 0.05, 10);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x6a557b, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2); light.position.set(1, 2, 3); scene.add(light);
    const loader = new GLTFLoader(); loader.register(parser => new VRMLoaderPlugin(parser));
    let vrm, stopped = false, frames = 0, last = performance.now(), mouth = 0, blinkAt = 3, blinkStart = -10;
    let expression = 'relaxed', defaultExpression = 'relaxed', expressionUntil = 0, background = 'neon', renderedMs = 0, animationMs = 0, omittedTriangles = 0;
    let appliedExpression = null, previousControlledExpressionName = null, motion;
    let blushUntil = 0, blushStarted = 0, appliedBlush = null;
    const blushSprites = [], blushResources = [];
    const cheekPosition = new THREE.Vector3();
    const started = performance.now();
    const ready = loader.parseAsync(modelBytes.buffer.slice(0), '').then(gltf => {
      vrm = gltf.userData.vrm;
      if (!vrm) throw Error('AVATAR_VRM_UNAVAILABLE');
      if (stopped) { VRMUtils.deepDispose(vrm.scene); throw Error('AVATAR_CANCELLED'); }
      removeOutlinePasses(vrm.scene);
      omittedTriangles = trimLowerBody(vrm);
      VRMUtils.removeUnnecessaryVertices(vrm.scene);
      VRMUtils.combineSkeletons(vrm.scene);
      VRMUtils.combineMorphs(vrm);
      const capabilities = expressionCapabilities(vrm.expressionManager);
      defaultExpression = ['relaxed', 'neutral'].find(name => capabilities.some(item => item.name === name && item.supported)) ||
        capabilities.find(item => item.supported)?.name || null;
      expression = defaultExpression;
      // Flat textured anime materials keep software WebGL practical on the VPS.
      // Morph targets and the humanoid rig remain intact; textures stay shared.
      const replacements = new Map();
      vrm.scene.traverse(object => {
        if (!object.isMesh) return;
        const replace = material => {
          if (!replacements.has(material)) replacements.set(material, new THREE.MeshBasicMaterial({
            map: material.map, color: material.color?.clone() || new THREE.Color(0xffffff),
            transparent: material.transparent, opacity: material.opacity, alphaTest: material.alphaTest, visible: material.visible && material.opacity > 0,
            side: material.side, depthWrite: material.depthWrite, forceSinglePass: true
          }));
          return replacements.get(material);
        };
        object.material = Array.isArray(object.material) ? object.material.map(replace) : replace(object.material);
      });
      for (const material of replacements.keys()) material.dispose();
      VRMUtils.rotateVRM0(vrm); scene.add(vrm.scene);
      const bone = name => vrm.humanoid.getNormalizedBoneNode(name);
      if (bone('leftUpperArm')) bone('leftUpperArm').rotation.z = 1.15;
      if (bone('rightUpperArm')) bone('rightUpperArm').rotation.z = -1.15;
      motion = createMotionLayer(vrm.humanoid);
      // Original soft cheek overlay, generated in memory; the source VRM is untouched.
      const patch = new OffscreenCanvas(64, 64), ctx = patch.getContext('2d');
      const gradient = ctx.createRadialGradient(32, 32, 2, 32, 32, 31);
      gradient.addColorStop(0, 'rgba(245,84,118,0.65)'); gradient.addColorStop(1, 'rgba(245,84,118,0)');
      ctx.fillStyle = gradient; ctx.fillRect(0, 0, 64, 64);
      const texture = new THREE.CanvasTexture(patch);
      blushResources.push(texture);
      for (const side of [-1, 1]) {
        const material = new THREE.SpriteMaterial({ map: texture, transparent: true, opacity: 0, depthWrite: false });
        const sprite = new THREE.Sprite(material); sprite.scale.set(0.065, 0.028, 1);
        sprite.userData.cheekSide = side; sprite.visible = false; scene.add(sprite);
        blushSprites.push(sprite); blushResources.push(material);
      }
      vrm.update(0); vrm.scene.updateMatrixWorld(true);
      const head = bone('head').getWorldPosition(new THREE.Vector3());
      camera.position.set(head.x, head.y + 0.02, AVATAR_CAMERA_DISTANCE); camera.lookAt(head.x, head.y - 0.06, 0);
      renderer.render(scene, camera);
    });
    const controller = {
      canvas: renderer.domElement, ready,
      readPixels() {
        const gl = renderer.getContext(), stride = AVATAR_WIDTH * 4;
        const raw = new Uint8Array(stride * AVATAR_HEIGHT), rgba = new Uint8ClampedArray(raw.length);
        gl.readPixels(0, 0, AVATAR_WIDTH, AVATAR_HEIGHT, gl.RGBA, gl.UNSIGNED_BYTE, raw);
        // WebGL rows start at the bottom; ImageData expects top-down, straight alpha.
        for (let y = 0; y < AVATAR_HEIGHT; y++) {
          const source = (AVATAR_HEIGHT - y - 1) * stride;
          rgba.set(raw.subarray(source, source + stride), y * stride);
        }
        for (let i = 0; i < rgba.length; i += 4) {
          const alpha = rgba[i + 3];
          if (alpha > 0 && alpha < 255) { const scale = 255 / alpha; rgba[i] *= scale; rgba[i + 1] *= scale; rgba[i + 2] *= scale; }
        }
        return rgba;
      },
      draw() {
        if (stopped || !vrm) return false;
        const now = performance.now();
        const animationStart = now;
        const dt = Math.max(0, Math.min(0.06, (now - last) / 1000)); last = now;
        const seconds = (now - started) / 1000;
        if (seconds > blinkAt) { blinkStart = seconds; blinkAt = seconds + 2.8 + Math.random() * 2.5; }
        const blink = Math.max(0, 1 - Math.abs(seconds - blinkStart - 0.1) / 0.1);
        const level = Math.max(0, Math.min(1, mouthLevel())); mouth += (level - mouth) * Math.min(1, dt * (level > mouth ? 25 : 12));
        const expressions = vrm.expressionManager;
        resetExpressions(expressions);
        if (expressionUntil && now >= expressionUntil) { expression = defaultExpression; expressionUntil = 0; }
        expressions?.setValue('aa', mouth * 0.85);
        expressions?.setValue('ou', mouth * (0.12 + 0.10 * Math.sin(seconds * 9)));
        let selectedExpression = null;
        if (expression) {
          try { selectedExpression = resolveSupportedExpression(expressions, expression, vrm.scene); } catch { /* no supported default expression */ }
        }
        const expressionWeight = expression === 'relaxed' ? 0.22 : expression === 'wink' ? 1 : 0.65;
        if (selectedExpression?.expression && selectedExpression.capability.mode !== 'reset') {
          expressions?.setValue(selectedExpression.expression.expressionName, expressionWeight);
        }
        expressions?.setValue('blink', blink);
        motion.reset();
        const head = vrm.humanoid.getNormalizedBoneNode('head');
        head.rotation.set(Math.sin(seconds * 1.7) * 0.025 + mouth * 0.02, Math.sin(seconds * 0.65) * 0.07, Math.sin(seconds * 0.8) * 0.035);
        const chest = vrm.humanoid.getNormalizedBoneNode('chest');
        if (chest) chest.rotation.x = Math.sin(seconds * 1.8) * 0.008;
        const left = vrm.humanoid.getNormalizedBoneNode('leftLowerArm');
        if (left) left.rotation.y = Math.sin(seconds * 0.9) * mouth * 0.12;
        motion.apply(now);
        vrm.update(dt);
        vrm.scene.updateMatrixWorld(true);
        const blushWeight = blushUntil > now ? Math.min(1, (now - blushStarted + 60) / 280, (blushUntil - now) / 350) : 0;
        // Head-local positions follow posture, rather than a fixed screen decoration.
        const rawHead = vrm.humanoid.getRawBoneNode('head');
        for (const sprite of blushSprites) {
          cheekPosition.set(sprite.userData.cheekSide * 0.045, -0.025, vrm.meta?.metaVersion === '0' ? -0.075 : 0.075);
          rawHead.localToWorld(cheekPosition); sprite.position.copy(cheekPosition);
          sprite.visible = blushWeight > 0; sprite.material.opacity = blushWeight * 0.8;
        }
        appliedBlush = blushWeight > 0 ? { requested: 'soft', applied: true, weight: blushWeight, cheeks: blushSprites.map(sprite => ({ position: sprite.position.toArray(), opacity: sprite.material.opacity })) } : null;
        const appliedGesture = motion.status().appliedGesture;
        if (appliedGesture) appliedGesture.joints = [...new Set(appliedGesture.bones.map(item => item.bone))].map(name => ({ bone: name, position: vrm.humanoid.getRawBoneNode(name).getWorldPosition(new THREE.Vector3()).toArray() }));
        appliedExpression = selectedExpression?.capability.mode === 'reset'
          ? resetExpressionEvidence(selectedExpression.capability, previousControlledExpressionName, expressions)
          : selectedExpression?.expression
          ? appliedExpressionEvidence(selectedExpression.expression, selectedExpression.capability, expressionWeight, vrm.scene)
          : expression ? { requested: expression, resolved: null, weight: 0, value: 0, bindCount: 0, applied: false, binds: [] } : null;
        previousControlledExpressionName = selectedExpression?.capability.mode === 'reset' ? null : selectedExpression?.expression?.expressionName || null;
        animationMs = performance.now() - animationStart;
        const renderStart = performance.now(); renderer.render(scene, camera); renderedMs = performance.now() - renderStart; frames++;
        return true;
      },
      control({ action, name, duration }) {
        if (duration === undefined) duration = action === 'gesture' ? 2 : action === 'blush' ? 4 : 6;
        if (stopped || !vrm) throw Error('AVATAR_NOT_READY');
        if (action === 'background') {
          if (!['studio', 'neon', 'sunset', 'night'].includes(name)) throw Error('AVATAR_BACKGROUND_INVALID');
          background = name;
        } else if (action === 'expression') {
          if (typeof name !== 'string' || !['neutral', 'relaxed', 'happy', 'angry', 'sad', 'surprised', 'wink', 'laugh'].includes(name.toLowerCase())) throw Error('AVATAR_EXPRESSION_INVALID');
          if (!Number.isFinite(duration) || duration < 1 || duration > 15) throw Error('AVATAR_DURATION_INVALID');
          const requested = name.toLowerCase();
          resolveSupportedExpression(vrm.expressionManager, requested, vrm.scene);
          expression = requested;
          expressionUntil = performance.now() + (requested === 'wink' ? 700 : duration * 1000);
          if (!controller.draw()) throw Error('AVATAR_NOT_READY');
        } else if (action === 'gesture' || action === 'blush') {
          if (!Number.isFinite(duration) || duration < 1 || duration > 15) throw Error('AVATAR_DURATION_INVALID');
          if (action === 'gesture') motion.start(name, duration, performance.now());
          else {
            if (name !== 'soft') throw Error('AVATAR_BLUSH_INVALID');
            blushStarted = performance.now(); blushUntil = blushStarted + duration * 1000;
          }
          if (!controller.draw()) throw Error('AVATAR_NOT_READY');
        } else throw Error('AVATAR_ACTION_INVALID');
        return controller.status();
      },
      status() { return { ready: !!vrm && !stopped, name: 'Botsky', background, expression, expressionCapabilities: vrm ? expressionCapabilities(vrm.expressionManager, vrm.scene) : [], appliedExpression, ...motion?.status(), gestureCapabilities: motion?.capabilities() || [], blushCapabilities: vrm ? [{ name: 'soft', supported: true, mode: 'procedural-overlay' }] : [], appliedBlush, mouth: Number(mouth.toFixed(3)), frames, renderMs: Math.round(renderedMs), animationMs: Math.round(animationMs), omittedTriangles, drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles }; },
      stop() {
        if (stopped) return; stopped = true;
        if (vrm) { VRMUtils.deepDispose(vrm.scene); scene.remove(vrm.scene); }
        for (const sprite of blushSprites) scene.remove(sprite);
        for (const resource of blushResources) resource.dispose();
        renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.width = 0; renderer.domElement.height = 0;
      }
    };
    return controller;
  }
};
