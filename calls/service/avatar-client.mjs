// WhatsApp's thread only composites 2D frames. Model loading and software WebGL
// run in a worker; one outstanding CPU frame bounds memory and render pressure.
import { AVATAR_WIDTH, AVATAR_HEIGHT, AVATAR_FPS, VIDEO_WIDTH, VIDEO_HEIGHT } from './avatar-quality.mjs';
let model;
window.__botskyAvatar = {
  output: { width: VIDEO_WIDTH, height: VIDEO_HEIGHT },
  prepare(base64) { model = base64; },
  create({ mouthLevel = () => 0 } = {}) {
    if (!model) throw Error('AVATAR_NOT_LOADED');
    const canvas = document.createElement('canvas'); canvas.width = AVATAR_WIDTH; canvas.height = AVATAR_HEIGHT;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    let worker, watchdog, stopped = false, loaded = false, sequence = 0, recoveries = 0;
    let lastFrameAt = performance.now(), workerStartedAt = lastFrameAt;
    const modelSource = model;
    let state = { ready: false, name: 'Botsky', frames: 0, mouth: 0, background: 'neon', expression: 'relaxed', renderMs: 0, width: AVATAR_WIDTH, height: AVATAR_HEIGHT, targetFps: AVATAR_FPS };
    const requests = new Map();
    let resolveReady, rejectReady;
    const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
    function rejectRequests() {
      for (const pending of requests.values()) { clearTimeout(pending.timer); pending.reject(Error('AVATAR_STOPPED')); }
      requests.clear();
    }
    function fail(owner) {
      if (stopped || worker !== owner) return;
      owner.terminate(); rejectRequests(); loaded = false;
      if (recoveries === 0) {
        recoveries++;
        state = { ...state, ready: false, recovering: true, failed: false, recoveries };
        launch();
      } else {
        clearInterval(watchdog); worker = null;
        state = { ...state, ready: false, recovering: false, failed: true, recoveries };
        rejectReady(Error('AVATAR_UNAVAILABLE'));
      }
    }
    function stop() {
      if (stopped) return;
      stopped = true; clearInterval(watchdog); worker?.terminate(); worker = null;
      state = { ...state, ready: false, recovering: false };
      rejectReady(Error('AVATAR_STOPPED'));
      rejectRequests(); canvas.width = canvas.height = 0;
    }
    function launch() {
      const url = URL.createObjectURL(new Blob([AVATAR_WORKER_SOURCE], { type: 'text/javascript' }));
      let owner;
      try { owner = new Worker(url); }
      catch { worker = null; state = { ...state, ready: false, recovering: false, failed: true }; rejectReady(Error('AVATAR_UNAVAILABLE')); return; }
      finally { URL.revokeObjectURL(url); }
      worker = owner; workerStartedAt = performance.now();
      const restore = recoveries > 0 ? state.background : null;
      let firstFrame = true;
      owner.onerror = event => { event.preventDefault(); fail(owner); };
      owner.onmessageerror = () => fail(owner);
      owner.onmessage = ({ data }) => {
        if (stopped || worker !== owner) return;
        if (data.type === 'frame') {
          context.putImageData(new ImageData(data.rgba, AVATAR_WIDTH, AVATAR_HEIGHT), 0, 0);
          state = { ...data.status, recovering: false, failed: false, recoveries };
          loaded = true; lastFrameAt = performance.now(); resolveReady();
          // Only background is durable; never replay a timed expression/gesture.
          if (firstFrame && restore) owner.postMessage({ type: 'control', id: ++sequence, options: { action: 'background', name: restore } });
          firstFrame = false;
          owner.postMessage({ type: 'ack', frameId: data.frameId, mouth: mouthLevel() });
        } else if (data.type === 'control') {
          const pending = requests.get(data.id);
          if (pending) {
            requests.delete(data.id); clearTimeout(pending.timer);
            if (data.error) pending.reject(Error(data.code || 'AVATAR_CONTROL_INVALID'));
            else { state = { ...state, ...data.status }; pending.resolve(state); }
          }
        } else if (data.type === 'error') fail(owner);
      };
      owner.postMessage({ type: 'init', base64: modelSource });
    }
    launch();
    watchdog = setInterval(() => {
      if (stopped || !worker) { clearInterval(watchdog); return; }
      const since = loaded ? lastFrameAt : workerStartedAt;
      if (performance.now() - since >= (loaded ? 5000 : 15000)) fail(worker);
    }, 1000);
    return {
      canvas, ready,
      draw() {
        return loaded && !stopped;
      },
      control(options) {
        if (stopped || !loaded) throw Error('AVATAR_NOT_READY');
        const { controlId, ...renderOptions } = options;
        const id = ++sequence;
        const owner = worker;
        return new Promise((resolve, reject) => {
          const timer = setTimeout(() => {
            requests.delete(id);
            if (worker === owner) owner.postMessage({ type: 'cancel-control', id });
            reject(Error('AVATAR_CONTROL_TIMEOUT'));
          }, 4000);
          requests.set(id, { resolve, reject, timer, controlId }); worker.postMessage({ type: 'control', id, options: renderOptions });
        });
      },
      cancelControl(controlId) {
        for (const [id, pending] of requests) {
          if (!controlId || pending.controlId !== controlId) continue;
          requests.delete(id); clearTimeout(pending.timer);
          worker?.postMessage({ type: 'cancel-control', id });
          pending.reject(Error('AVATAR_CONTROL_CANCELLED'));
        }
      },
      status() { return { ...state, worker: !stopped && !!worker }; },
      stop
    };
  }
};
