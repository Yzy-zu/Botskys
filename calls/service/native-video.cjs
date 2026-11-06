'use strict';

// WhatsApp requests capture dimensions separately from getUserMedia. Keep its
// camera/converter contract aligned with our virtual track, not the desktop default.
function installNativeVideoAdapter() {
  if (window.__botskyNativeVideoAdapter) return true;
  let camera;
  try { camera = window.require('WAWebVoipVideoCameraCapture').WAWebVoipVideoCameraCapture; } catch { return false; }
  if (typeof camera?.startCameraCapture !== 'function' || typeof camera.getOpenCaptureParams !== 'function') return false;
  const original = camera.startCameraCapture;
  const originalOpen = camera.getOpenCaptureParams;
  const originalWithStream = camera.startWithStream;
  const ownedVideo = () => {
    const bridge = window.__botskyAudio, video = bridge?.videoSource?.status();
    return bridge?.ownsMedia() && video?.active ? { bridge, video } : null;
  };
  // WhatsApp's virtual capture driver bypasses getUserMedia entirely. Route
  // that entry point through the same owned source as ordinary camera capture.
  if (typeof originalWithStream === 'function') camera.startWithStream = async function (stream, width, height, fps, trackStream) {
    const owned = ownedVideo();
    if (!owned) return originalWithStream.call(this, stream, width, height, fps, trackStream);
    const { bridge, video } = owned, token = bridge.token, source = bridge.videoSource;
    const observedCall = bridge.native();
    const observedCallId = bridge.nativeId != null ? String(bridge.nativeId) : (observedCall?.id == null ? null : String(observedCall.id));
    const check = () => {
      const current = bridge.native();
      if (bridge.token !== token || !bridge.ownsMedia() || bridge.videoSource !== source ||
          (observedCallId && String(current?.id) !== observedCallId)) throw Error('AUDIO_CALL_CHANGED');
    };
    let replacement;
    try {
      replacement = await bridge.capture({ video: true }, 'native');
      check();
      const tracks = replacement?.getVideoTracks?.() || [];
      if (!tracks.length || typeof source.ownsTrack !== 'function' || !tracks.every(track => source.ownsTrack(track))) throw Error('VIDEO_SOURCE_UNCONFIRMED');
      stream.getTracks().forEach(track => track.stop());
      bridge.nativeVideo = { path: 'startWithStream', requested: { width, height }, source: { width: video.width, height: video.height } };
      const result = await originalWithStream.call(this, replacement, video.width, video.height, fps, true);
      check();
      if (tracks.some(track => track.readyState !== 'live' || !source.ownsTrack(track))) throw Error('VIDEO_SOURCE_UNCONFIRMED');
      return result;
    } catch (error) {
      replacement?.getTracks().forEach(track => track.stop());
      // The input stream may belong to a successor call if ownership changed
      // while acquisition or WhatsApp's startWithStream was pending.
      try { check(); stream.getTracks().forEach(track => track.stop()); } catch {}
      throw error;
    }
  };
  camera.getOpenCaptureParams = function () {
    const params = originalOpen.call(this), owned = ownedVideo();
    if (!params || !owned) return params;
    const { width, height } = owned.video;
    let a = width, b = height;
    while (b) { const remainder = a % b; a = b; b = remainder; }
    // Respect WhatsApp's pixel budget after all its caps, while keeping the
    // source aspect ratio and even NV12 dimensions. Independent width/height
    // caps otherwise turn a portrait request into a square or landscape crop.
    const unitWidth = width / a * 2, unitHeight = height / a * 2;
    const steps = Math.floor(Math.min(a / 2, Math.sqrt(params.width * params.height / (unitWidth * unitHeight))));
    if (steps < 1) return params;
    const adapted = { ...params, width: unitWidth * steps, height: unitHeight * steps };
    if (owned.bridge.nativeVideo) owned.bridge.nativeVideo.adapted = { width: adapted.width, height: adapted.height };
    return adapted;
  };
  camera.startCameraCapture = function (request) {
    const owned = ownedVideo();
    if (!owned) return original.call(this, request);
    const { bridge, video } = owned, source = bridge.videoSource, { width, height } = video;
    const token = bridge.token, observedCall = bridge.native();
    const observedCallId = bridge.nativeId != null ? String(bridge.nativeId) : (observedCall?.id == null ? null : String(observedCall.id));
    bridge.nativeVideo = { requested: { width: request.width, height: request.height }, source: { width, height } };
    return Promise.resolve(original.call(this, request)).then(result => {
      const current = bridge.native();
      if (bridge.token !== token || !bridge.ownsMedia() || bridge.videoSource !== source ||
          (observedCallId && String(current?.id) !== observedCallId)) throw Error('AUDIO_CALL_CHANGED');
      const open = this.getOpenCaptureParams?.();
      const tracks = this.getLastCapturedStream?.()?.getVideoTracks?.();
      if (typeof this.getLastCapturedStream === 'function' && (!tracks?.length || !tracks.every(track => track.readyState === 'live' && source.ownsTrack?.(track)))) throw Error('VIDEO_SOURCE_UNCONFIRMED');
      const settings = tracks?.[0]?.getSettings();
      bridge.nativeVideo.open = open ? { width: open.width, height: open.height } : null;
      bridge.nativeVideo.track = settings ? { width: settings.width, height: settings.height } : null;
      return result;
    });
  };
  window.__botskyNativeVideoAdapter = {
    async ensureOwnedCapture({ allowPending = false } = {}) {
      const owned = ownedVideo();
      if (!owned) throw Error('AUDIO_CALL_CHANGED');
      const { bridge } = owned, token = bridge.token, source = bridge.videoSource, observedCall = bridge.native();
      const observedCallId = bridge.nativeId != null ? String(bridge.nativeId) : (observedCall?.id == null ? null : String(observedCall.id));
      const check = () => {
        const current = bridge.native();
        if (bridge.token !== token || !bridge.ownsMedia() || bridge.videoSource !== source ||
            (observedCallId && String(current?.id) !== observedCallId)) throw Error('AUDIO_CALL_CHANGED');
      };
      // Incoming calls may already have native capture running before we own
      // media. Clearing the prewarm cache cannot replace that active capture.
      if (camera.captureInitState === 'Initializing' && camera.captureInitResolvable?.promise) await camera.captureInitResolvable.promise;
      check();
      const tracks = camera.getLastCapturedStream?.()?.getVideoTracks() || [];
      if (tracks.length && tracks.every(track => source.ownsTrack?.(track) && track.readyState === 'live')) return { owned: true };
      if (!tracks.length) {
        if (allowPending) return { pending: true };
        throw Error('VIDEO_SOURCE_UNCONFIRMED');
      }
      if (typeof camera.retryCameraCapture !== 'function') throw Error('VIDEO_SOURCE_UNCONFIRMED');
      const restarted = await camera.retryCameraCapture();
      check();
      const replacement = camera.getLastCapturedStream?.()?.getVideoTracks() || [];
      if (!restarted || !replacement.length || !replacement.every(track => source.ownsTrack?.(track) && track.readyState === 'live')) throw Error('VIDEO_SOURCE_UNCONFIRMED');
      return { owned: true, restarted: true };
    }
  };
  return true;
}
module.exports = { installNativeVideoAdapter };
