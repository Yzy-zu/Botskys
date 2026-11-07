'use strict';

// Self-contained: runs in WhatsApp's page. Produces video only; never reads a camera.
function installVideoBridge() {
  if (window.__botskyVideo) return;
  window.__botskyVideo = {
    create({ audioContext, audioOutput, isSpeaking = () => false, mouthLevel = () => 0, valid = () => true } = {}) {
      const canvas = document.createElement('canvas');
      const width = window.__botskyAvatar?.output?.width || 640, height = window.__botskyAvatar?.output?.height || 360;
      const portrait = height > width;
      canvas.width = width; canvas.height = height;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context || typeof canvas.captureStream !== 'function') throw Error('VIDEO_UNAVAILABLE');
      let frame = 0, stopped = false;
      const clones = new Set();
      let clip = null, quietSince = null, pendingBackground = null;
      let lastLayout, lastAvatarFrame = -1, lastBackground, lastActivityLabel;
      let activity = 'listening', activitySince = performance.now();
      const activityLabel = () => {
        const recovering = !!avatar?.status().recovering;
        const reconnecting = recovering || (activity === 'reconnecting' && performance.now() - activitySince >= 300);
        if (recovering || (reconnecting && clip?.state === 'paused')) return 'Reconectando…';
        return isSpeaking() ? '' : reconnecting ? 'Reconectando…' : '';
      };
      const paintActivity = label => {
        if (!label) return;
        context.font = '18px sans-serif';
        const badgeWidth = Math.ceil(context.measureText(label).width) + 24;
        context.fillStyle = '#101426dd'; context.fillRect(24, 24, badgeWidth, 34);
        context.fillStyle = '#fff'; context.fillText(label, 36, 47);
      };
      const paintPause = reason => {
        const label = reason === 'gemini' ? 'Pausado mientras hablo' : 'Pausado';
        context.font = `${portrait ? 15 : 20}px sans-serif`;
        const badgeWidth = Math.ceil(context.measureText(label).width) + 28;
        const x = Math.round((width - badgeWidth) / 2), y = 20;
        context.fillStyle = '#101426e8'; context.fillRect(x, y, badgeWidth, 38);
        context.fillStyle = '#fff'; context.fillText(label, x + 14, y + 25);
      };
      const paintClipStatus = (label, reason) => {
        if (!label) return paintPause(reason);
        context.font = `${portrait ? 15 : 20}px sans-serif`;
        const badgeWidth = Math.ceil(context.measureText(label).width) + 28;
        const x = Math.round((width - badgeWidth) / 2), y = 20;
        context.fillStyle = '#101426e8'; context.fillRect(x, y, badgeWidth, 38);
        context.fillStyle = '#fff'; context.fillText(label, x + 14, y + 25);
      };
      const avatar = window.__botskyAvatar?.create({ mouthLevel });
      const fit = (sourceWidth, sourceHeight, x, y, boxWidth, boxHeight) => {
        const scale = Math.min(boxWidth / sourceWidth, boxHeight / sourceHeight);
        const w = sourceWidth * scale, h = sourceHeight * scale;
        return [x + (boxWidth - w) / 2, y + (boxHeight - h) / 2, w, h];
      };
      const paintBackground = () => {
        const palette = { studio: ['#c6c1dc', '#4a557b'], neon: ['#181c4c', '#7a215e'], sunset: ['#e9ad91', '#695087'], night: ['#080c1f', '#17284c'] }[avatar?.status().background || 'neon'];
        const gradient = context.createLinearGradient(0, 0, width, height); gradient.addColorStop(0, palette[0]); gradient.addColorStop(1, palette[1]);
        context.fillStyle = gradient; context.fillRect(0, 0, width, height);
      };
      const dispose = record => {
        if (!record || record.disposed) return;
        record.disposed = true; record.abort.abort(); record.element.pause();
        record.node?.disconnect(); record.gain?.disconnect();
        record.element.removeAttribute('src'); record.element.load(); URL.revokeObjectURL(record.url);
      };
      const failClip = record => {
        if (!record || record.disposed) return;
        record.position = Number.isFinite(record.element.currentTime) ? record.element.currentTime : record.position;
        record.state = 'failed'; record.playAttempt++;
        dispose(record);
        void applyPendingBackground();
      };
      const applyPendingBackground = async () => {
        if (!pendingBackground || !avatar) return;
        const options = pendingBackground; pendingBackground = null;
        try { await avatar.control(options); }
        catch { if (!pendingBackground) pendingBackground = options; }
      };
      const clipStatus = () => clip ? { id: clip.id, clipId: clip.clipId, state: clip.state,
        pauseReason: clip.pauseReason || null, positionSeconds: clip.disposed ? clip.position : clip.element.currentTime,
        durationSeconds: clip.duration, volume: clip.volume } : null;
      const pauseClip = reason => {
        if (!clip || !['loading', 'playing', 'paused', 'resuming'].includes(clip.state)) return;
        if (reason === 'gemini' && clip.pauseReason === 'manual') return;
        if (clip.state === 'resuming') clip.playAttempt++;
        clip.element.pause(); clip.state = 'paused'; clip.pauseReason = reason;
        if (reason === 'manual') clip.wantsPlay = false;
      };
      const resumeClip = async () => {
        const record = clip;
        if (!record || record.disposed || !['playing', 'paused'].includes(record.state)) throw Error('CLIP_NOT_PAUSED');
        record.wantsPlay = true;
        record.pauseReason = null;
        if (isSpeaking()) {
          pauseClip('gemini');
          return clipStatus();
        }
        record.state = 'resuming';
        const attempt = ++record.playAttempt;
        try { await record.element.play(); }
        catch (error) {
          if (record.playAttempt !== attempt) return clipStatus();
          if (clip === record && !record.disposed) failClip(record);
          throw error;
        }
        if (record.playAttempt !== attempt) {
          if (clip === record && !record.disposed && record.state !== 'resuming') record.element.pause();
          return clipStatus();
        }
        if (clip !== record || record.disposed || stopped || !valid()) { dispose(record); throw Error('CLIP_CALL_CHANGED'); }
        if (!record.wantsPlay || record.pauseReason === 'manual') { record.element.pause(); record.state = 'paused'; return clipStatus(); }
        record.state = 'playing'; record.pauseReason = null;
        return clipStatus();
      };
      const draw = () => {
        if (stopped) return;
        const avatarReady = avatar?.draw();
        const label = activityLabel();
        if (clip && !clip.disposed && ['playing', 'paused', 'resuming'].includes(clip.state)) {
          if (!valid()) { clip.position = clip.element.currentTime; clip.state = 'stopped'; dispose(clip); }
          else if (isSpeaking()) { quietSince = null; if (clip.state === 'playing' || clip.state === 'resuming') pauseClip('gemini'); }
          else if (clip.state === 'paused' && clip.pauseReason === 'gemini' && clip.wantsPlay) {
            quietSince ??= performance.now();
            if (performance.now() - quietSince >= 700) {
              quietSince = null; void resumeClip().catch(() => {});
            }
          }
          if (clip && !clip.disposed && clip.element.readyState >= 2) {
            frame++; lastLayout = 'inset';
            context.fillStyle = '#000'; context.fillRect(0, 0, width, height);
            context.drawImage(clip.element, ...fit(clip.element.videoWidth, clip.element.videoHeight, 0, 0, width, height));
            if (clip.state === 'paused') paintClipStatus(label, clip.pauseReason);
            if (avatarReady) {
              const pipWidth = portrait ? 108 : 140, pipHeight = portrait ? 192 : 140;
              const x = 24, y = height - pipHeight - 24;
              context.fillStyle = '#10142699'; context.fillRect(x - 4, y - 4, pipWidth + 8, pipHeight + 8);
              context.drawImage(avatar.canvas, ...fit(avatar.canvas.width, avatar.canvas.height, x, y, pipWidth, pipHeight));
            }
            if (clip.state !== 'paused') paintActivity(label);
            return;
          }
        }
        if (avatarReady) {
          const state = avatar.status();
          if (lastLayout === 'full' && lastAvatarFrame === state.frames && lastBackground === state.background && lastActivityLabel === label) return;
          frame++; lastLayout = 'full'; lastAvatarFrame = state.frames; lastBackground = state.background; lastActivityLabel = label;
          paintBackground(); context.drawImage(avatar.canvas, ...fit(avatar.canvas.width, avatar.canvas.height, 0, 0, width, height));
          context.fillStyle = '#ffffffbb'; context.font = '18px sans-serif'; context.fillText('Botsky', 24, height - 26);
          paintActivity(label);
          return;
        }
        frame++; lastLayout = 'fallback';
        context.fillStyle = '#101b35'; context.fillRect(0, 0, width, height);
        context.fillStyle = '#f3efff'; context.font = 'bold 42px sans-serif';
        context.fillText('Botsky', 40, 82);
        context.font = `${portrait ? 20 : 26}px sans-serif`;
        context.fillText('La imagen no está disponible', 40, 128);
        paintActivity(label);
      };
      let stream = null, timer = null;
      const start = () => {
        if (stopped) throw Error('VIDEO_STOPPED');
        draw(); stream = canvas.captureStream(24);
        if (!stream.getVideoTracks().length) throw Error('VIDEO_UNAVAILABLE');
        timer = setInterval(draw, 1000 / 24);
      };
      const ready = avatar ? avatar.ready.then(start) : Promise.resolve(start());
      return {
        ready,
        setActivity(state) { if (activity !== state) { activity = state; activitySince = performance.now(); } },
        cancelAvatarControl(controlId) { avatar?.cancelControl(controlId); },
        async avatarControl(options) {
          if (!avatar) throw Error('AVATAR_UNAVAILABLE');
          if (options.action === 'background' && clip && !clip.disposed && ['loading', 'playing', 'paused', 'resuming'].includes(clip.state)) {
            pendingBackground = { action: 'background', name: options.name };
            return { ...avatar.status(), deferred: true, requestedBackground: options.name };
          }
          return avatar.control(options);
        },
        async playClip({ id, clipId, base64, volume = 0.5 }) {
          if (stopped || !valid() || !audioContext || !audioOutput) throw Error('CLIP_CALL_CHANGED');
          if (!Number.isFinite(volume) || volume < 0 || volume > 1) throw Error('INVALID_VOLUME');
          if (clip?.id === id) return clipStatus();
          if (clip) { clip.position = clip.element.currentTime; clip.state = 'stopped'; dispose(clip); }
          const binary = atob(base64), bytes = new Uint8Array(binary.length);
          for (let i = 0; i < bytes.length; i++) bytes[i] = binary.charCodeAt(i);
          const element = document.createElement('video'); element.playsInline = true; element.preload = 'auto';
          const url = URL.createObjectURL(new Blob([bytes], { type: 'video/webm' }));
          const record = clip = { id, clipId, element, url, abort: new AbortController(), state: 'loading', volume, wantsPlay: true, position: 0, duration: null, playAttempt: 0 };
          try {
            await new Promise((resolve, reject) => {
              const done = error => { element.removeEventListener('loadeddata', loaded); element.removeEventListener('error', failed); record.abort.signal.removeEventListener('abort', aborted); error ? reject(error) : resolve(); };
              const loaded = () => done(), failed = () => done(Error('CLIP_DECODE_FAILED')), aborted = () => done(Error('CLIP_CANCELLED'));
              element.addEventListener('loadeddata', loaded, { once: true }); element.addEventListener('error', failed, { once: true });
              record.abort.signal.addEventListener('abort', aborted, { once: true });
              element.src = url; element.load();
            });
            if (clip !== record || record.disposed || stopped || !valid()) throw Error('CLIP_CALL_CHANGED');
            record.duration = element.duration;
            record.node = audioContext.createMediaElementSource(element); record.gain = audioContext.createGain();
            record.gain.gain.value = volume; record.node.connect(record.gain); record.gain.connect(audioOutput);
            element.onended = () => { if (clip === record) { record.position = element.duration; record.state = 'ended'; dispose(record); void applyPendingBackground(); } };
            element.onerror = () => { if (clip === record && !record.disposed) failClip(record); };
            if (record.state === 'paused' && record.pauseReason === 'manual') return clipStatus();
            record.state = 'paused'; record.pauseReason = isSpeaking() ? 'gemini' : null;
            if (record.pauseReason === 'gemini') record.wantsPlay = true;
            await resumeClip();
            return clipStatus();
          } catch (error) { if (!record.disposed) failClip(record); throw error; }
        },
        async controlClip(action, volume) {
          if (stopped || !valid()) throw Error('CLIP_CALL_CHANGED');
          if (!clip) throw Error('CLIP_NOT_PLAYING');
          if (action === 'pause') pauseClip('manual');
          else if (action === 'resume') await resumeClip();
          else if (action === 'stop') { clip.position = clip.disposed ? clip.position : clip.element.currentTime; clip.state = 'stopped'; dispose(clip); await applyPendingBackground(); }
          else if (action === 'volume') {
            if (!Number.isFinite(volume) || volume < 0 || volume > 1) throw Error('INVALID_VOLUME');
            clip.volume = volume; if (clip.gain) clip.gain.gain.value = volume;
          } else throw Error('INVALID_CLIP_ACTION');
          return clipStatus();
        },
        stopClip() { if (clip) { clip.position = clip.disposed ? clip.position : clip.element.currentTime; clip.state = 'stopped'; dispose(clip); } },
        track() {
          if (stopped || !stream) throw Error('VIDEO_STOPPED');
          const track = stream.getVideoTracks()[0].clone(); clones.add(track);
          track.addEventListener('ended', () => clones.delete(track), { once: true });
          return track;
        },
        ownsTrack(track) { return !stopped && clones.has(track) && track.readyState === 'live'; },
        status() { return { active: !stopped, frames: frame, width, height, activity, activityLabel: activityLabel(),
          avatar: avatar ? { ...avatar.status(), layout: clip && !clip.disposed ? 'inset' : 'full' } : null,
          error: avatar?.status().failed ? 'VIDEO_UNAVAILABLE' : null,
          clip: clipStatus(),
          liveTracks: [...(stream?.getVideoTracks() || []), ...clones].filter(track => track.readyState === 'live').length }; },
        stop() {
          if (stopped) return;
          stopped = true; clearInterval(timer); avatar?.stop();
          if (clip) { clip.position = clip.disposed ? clip.position : clip.element.currentTime; clip.state = 'stopped'; dispose(clip); }
          for (const track of [...(stream?.getTracks() || []), ...clones]) track.stop();
          clones.clear(); canvas.width = 0; canvas.height = 0;
        }
      };
    }
  };
}
module.exports = { installVideoBridge };
