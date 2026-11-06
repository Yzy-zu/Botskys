import './avatar-renderer.mjs';
import { AVATAR_WIDTH, AVATAR_HEIGHT, AVATAR_FPS, AVATAR_FRAME_MS } from './avatar-quality.mjs';

let avatar, timer, mouth = 0, pendingFrame = null, frameId = 0;
const controls = [];
let nextFrameAt = 0;
let firstFrameAt, emittedFrames = 0, totalFrameMs = 0, slowFrames = 0;
function frame() {
  if (!avatar || pendingFrame) return;
  const started = performance.now();
  nextFrameAt = started + AVATAR_FRAME_MS;
  let control = null, drawn = false;
  while (controls.length && !control) {
    const candidate = controls.shift();
    try {
      const previousFrames = avatar.status().frames;
      avatar.control(candidate.options); control = candidate;
      drawn = avatar.status().frames > previousFrames;
    }
    catch (error) {
      postMessage({ type: 'control', id: candidate.id, error: true,
        code: /^AVATAR_[A-Z_]+$/.test(error.message) ? error.message : 'AVATAR_CONTROL_INVALID' });
    }
  }
  if (!drawn && !avatar.draw()) return;
  const renderedAt = performance.now();
  // Read software WebGL back here, never on WhatsApp's control thread.
  const rgba = avatar.readPixels();
  const now = performance.now(), frameMs = now - started;
  firstFrameAt ??= now; emittedFrames++; totalFrameMs += frameMs;
  if (frameMs > AVATAR_FRAME_MS) slowFrames++;
  const status = { ...avatar.status(), width: AVATAR_WIDTH, height: AVATAR_HEIGHT, targetFps: AVATAR_FPS,
    effectiveFps: Number(((emittedFrames - 1) * 1000 / Math.max(1, now - firstFrameAt)).toFixed(1)),
    frameMs: Math.round(frameMs), averageFrameMs: Math.round(totalFrameMs / emittedFrames), readbackMs: Math.round(now - renderedAt), slowFrames };
  pendingFrame = { id: ++frameId, control, status };
  postMessage({ type: 'frame', frameId, rgba, status }, [rgba.buffer]);
}
onmessage = async ({ data }) => {
  try {
    if (data.type === 'init') {
      __botskyAvatarRenderer.prepare(data.base64);
      avatar = __botskyAvatarRenderer.create({ mouthLevel: () => mouth });
      await avatar.ready;
      frame();
    } else if (data.type === 'ack') {
      if (!pendingFrame || data.frameId !== pendingFrame.id) return;
      const confirmed = pendingFrame;
      mouth = data.mouth; pendingFrame = null;
      if (confirmed.control) postMessage({ type: 'control', id: confirmed.control.id, status: confirmed.status });
      clearTimeout(timer);
      timer = setTimeout(frame, Math.max(0, nextFrameAt - performance.now()));
    }
    else if (data.type === 'control') {
      if (controls.length >= 32) throw Error('AVATAR_CONTROL_BUSY');
      controls.push({ id: data.id, options: data.options });
      if (!pendingFrame) { clearTimeout(timer); frame(); }
    } else if (data.type === 'cancel-control') {
      const index = controls.findIndex(control => control.id === data.id);
      if (index >= 0) controls.splice(index, 1);
      if (pendingFrame?.control?.id === data.id) pendingFrame.control = null;
    }
  } catch {
    if (data.type === 'control') { postMessage({ type: 'control', id: data.id, error: true }); return; }
    clearTimeout(timer); avatar?.stop();
    postMessage({ type: 'error' });
  }
};
