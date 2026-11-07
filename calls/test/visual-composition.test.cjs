'use strict';
// Canvas/medios sintéticos en VM: prueba de composición, NO raster ni navegador.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { installVideoBridge } = require('../service/video-bridge.cjs');

async function fixture() {
  const paints = [], videos = [];
  let drawTick, time = 0, speaking = false, valid = true, frames = 0, held = false, release;
  const context = { fillRect() {}, fillText(text) { paints.push({ type: 'text', text }); },
    drawImage(image, ...rect) { paints.push({ type: 'image', source: image.tag, rect }); },
    measureText(text) { return { width: text.length * 9 }; }, createLinearGradient() { return { addColorStop() {} }; } };
  const track = { readyState: 'live', stop() { this.readyState = 'ended'; } };
  const canvas = { tag: 'output', getContext: () => context,
    captureStream: () => ({ getVideoTracks: () => [track], getTracks: () => [track] }) };
  const avatar = { canvas: { tag: 'avatar', width: 384, height: 384 }, ready: Promise.resolve(),
    draw: () => { frames++; return true; }, status: () => ({ name: 'Botsky', frames, background: 'night', recovering: false }),
    stop() {}, control: async () => ({ applied: true }) };
  function video() {
    const listeners = new Map();
    return { tag: 'clip', readyState: 2, duration: 5, currentTime: 1, videoWidth: 640, videoHeight: 360,
      addEventListener(name, fn) { listeners.set(name, fn); }, removeEventListener(name) { listeners.delete(name); },
      load() { queueMicrotask(() => listeners.get('loadeddata')?.()); }, removeAttribute() {}, pause() {},
      play() { return held ? new Promise(resolve => { release = resolve; }) : Promise.resolve(); } };
  }
  const globals = { window: { __botskyAvatar: { output: { width: 640, height: 360 }, create: () => avatar } },
    document: { createElement(kind) { if (kind === 'canvas') return canvas; const element = video(); videos.push(element); return element; } },
    performance: { now: () => time }, setInterval: fn => { drawTick = fn; return 1; }, clearInterval() {},
    Blob, Uint8Array, AbortController, queueMicrotask,
    atob: str => Buffer.from(str, 'base64').toString('binary'), URL: { createObjectURL: () => 'blob:synthetic', revokeObjectURL() {} } };
  vm.runInNewContext(`(${installVideoBridge.toString()})()`, globals);
  const audioContext = { createMediaElementSource: () => ({ connect() {}, disconnect() {} }),
    createGain: () => ({ gain: {}, connect() {}, disconnect() {} }) };
  const bridge = globals.window.__botskyVideo.create({ audioContext, audioOutput: {}, isSpeaking: () => speaking, valid: () => valid });
  await bridge.ready;
  return { bridge, paints, videos, tick() { paints.length = 0; drawTick(); },
    time(value) { time = value; }, speaking(value) { speaking = value; }, valid(value) { valid = value; }, hold() { held = true; }, release() { held = false; release(); } };
}

test('visual: clip/PIP survives pending resume; ended signal returns to avatar without autoplay', async () => {
  const f = await fixture();
  try {
    await f.bridge.playClip({ id: 'this-call-clip', clipId: 'synthetic', base64: 'Zml4dHVyZQ==' });
    f.tick();
    const inset = f.paints.find(p => p.type === 'image' && p.source === 'avatar');
    assert.deepEqual(inset.rect, [24, 196, 140, 140]);
    assert.equal(f.paints[0].source, 'clip');
    await f.bridge.controlClip('pause'); f.hold();
    const pending = f.bridge.controlClip('resume');
    f.tick();
    assert.equal(f.bridge.status().clip.state, 'resuming');
    assert.equal(f.paints.some(p => p.type === 'image' && p.source === 'avatar' && p.rect[2] > 140), false);
    f.release(); await pending;
    f.videos[0].onended(); f.tick();
    assert.equal(f.bridge.status().clip.state, 'ended');
    assert.equal(f.paints.some(p => p.source === 'clip'), false);
    assert.equal(f.paints.some(p => p.type === 'text' && p.text === 'Botsky'), true);
    await assert.rejects(f.bridge.controlClip('resume'), /CLIP_NOT_PAUSED/);
  } finally { f.bridge.stop(); }
});

test('visual: reconnect replaces pause in one layer; obsolete session cannot continue clip', async () => {
  const f = await fixture();
  try {
    await f.bridge.playClip({ id: 'current-session', clipId: 'synthetic', base64: 'Zml4dHVyZQ==' });
    await f.bridge.controlClip('pause');
    f.bridge.setActivity('reconnecting'); f.time(400); f.tick();
    assert.deepEqual(f.paints.filter(p => p.type === 'text').map(p => p.text), ['Reconectando…']);
    f.valid(false); f.tick();
    assert.equal(f.bridge.status().clip.state, 'stopped');
    assert.equal(f.paints.some(p => p.source === 'clip'), false);
    await assert.rejects(f.bridge.controlClip('resume'), /CLIP_CALL_CHANGED/);
  } finally { f.bridge.stop(); }
});
