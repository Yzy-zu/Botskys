'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { identity } = require('./runtime.cjs');
const allowedCodes = new Set([
  'starting','dialing','connecting','connected','recovering','recovering_call','ending','ended','failed','interrupted','pending','executing','dispatched','cancelled','claimed','sent','abandoned','error','needs_link','ready','stopping','stopped',
  'display','audio','browser','bus','AUDIO_BUS_UNAVAILABLE','AUDIO_RUNTIME_UNAVAILABLE','requested','cancelled_before_dial','remote_or_native_end','remote_left','remote_rejected','not_answered','dial_timeout','answer_timeout','duration_limit','schedule_window_closed','audio_completed','audience_empty','audience_unavailable','service_shutdown','service_restart','incoming_answer_timeout','different_call_observed','forced_browser_close','hangup_unconfirmed','native_end_during_dial','incoming_accept_failed','audio_failed','live_failed','recovery_timeout','recovery_exhausted','browser_disconnected','page_closed','page_crashed','page_reloaded','browser_unavailable','recovery_unavailable','service_error',
  'BROWSER_LOST','SNAPSHOT_TIMEOUT','RECOVERY_AUDIO_UNCONFIRMED','AUDIO_PAUSE_TIMEOUT','AUDIO_RESUME_TIMEOUT','DIAL_UNCONFIRMED','CALL_CHANGED','PRIVATE_TARGET_UNVERIFIED','PRIVATE_DIAL_FAILED','GROUP_MISMATCH','GROUP_CALL_UNAVAILABLE','GROUP_NOT_JOINED','GROUP_DIRECTORY_UNAVAILABLE','NOT_READY','CALL_BUSY','FEATURE_DISABLED','SCHEDULE_WINDOW_CLOSED','LIVE_NO_KEY','LIVE_SETUP_TIMEOUT','LIVE_PROVIDER_ERROR','LIVE_KEY_REJECTED','LIVE_QUOTA_EXCEEDED','LIVE_PROVIDER_UNAVAILABLE','LIVE_MODEL_UNAVAILABLE','LIVE_REQUEST_INVALID','LIVE_SOCKET_CLOSED','LIVE_SOCKET_ERROR','LIVE_SESSION_ROTATION_REQUIRED','LIVE_RESUMPTION_UNAVAILABLE','LIVE_RESUMPTION_FAILED','LIVE_RENEWAL_LIMIT','LIVE_RENEWAL_INPUT_BACKLOG','LIVE_CAPTURE_FAILED','LIVE_CAPTURE_STOPPED','AUDIO_PROCESS_FAILED','AUDIO_PRELOAD_TIMEOUT','OPEN_GROUP_TIMEOUT','VOIP_INIT_TIMEOUT','INVALID_AUDIO_ID','AUDIO_NOT_FOUND',
  'SCHEDULE_GROUP_NOT_JOINED','SCHEDULE_GROUP_DIRECTORY_UNAVAILABLE','SCHEDULE_RESERVATION_SAVE_FAILED','SCHEDULE_MISSED','SCHEDULE_CALL_BUSY','SCHEDULE_NOT_READY','SCHEDULE_STOPPING','SCHEDULE_CANCELLED','SCHEDULE_SERVICE_RESTART','SCHEDULE_service_restart','SCHEDULE_DESTINATION_NOT_ENABLED','SCHEDULE_CALL_DESTINATION_DENIED','SCHEDULE_WINDOW_CLOSED','SCHEDULE_SCHEDULE_WINDOW_CLOSED','SCHEDULE_SCHEDULE_OUTSIDE_HOURS','SCHEDULE_SCHEDULE_WINDOW_SHORT','SCHEDULE_SCHEDULE_POLICY_CHANGED','SCHEDULE_LIVE_DISABLED','SCHEDULE_OUTGOING_DISABLED'
]);
const safeCode = value => allowedCodes.has(value) ? value : 'OTHER';
const finite = value => Number.isFinite(value) && value >= 0 ? value : null;
const sum = values => values.filter(v => v !== null).reduce((total, value) => total + value, 0);
function latency(values) {
  const sorted = values.filter(v => v !== null).sort((a,b) => a-b);
  return { samples: sorted.length, medianMs: sorted.length ? sorted[Math.floor((sorted.length-1)*0.5)] : null, p95Ms: sorted.length ? sorted[Math.ceil(sorted.length*0.95)-1] : null };
}
function reportSnapshot({ manager, now = Date.now(), resources = {}, storage = {} }) {
  const records = manager.journal.records, active = manager.active, live = manager.liveController?.status?.() || null;
  const states = {}, reasons = {}, notices = {}, schedules = {};
  for (const record of records) {
    const state = safeCode(record.state); states[state] = (states[state] || 0) + 1;
    if (record.reason) { const reason = safeCode(record.reason); reasons[reason] = (reasons[reason] || 0) + 1; }
    if (record.failureNotice) { const state = safeCode(record.failureNotice.state); notices[state] = (notices[state] || 0) + 1; }
  }
  for (const row of manager.agenda?.rows || []) { const state = safeCode(row.status); schedules[state] = (schedules[state] || 0) + 1; }
  const audio = manager.audioRuntime || {}, pollAt = manager.lastSuccessfulPollAt;
  const observationAgeMs = Number.isFinite(pollAt) ? Math.max(0, now-pollAt) : null;
  const idle = !active && !manager.observed;
  const freshAfterClose = Number.isFinite(pollAt) && pollAt >= (records.at(-1)?.endedAt || 0);
  const idleReleased = !idle ? null : !freshAfterClose ? null : !audio.armed && !(audio.liveTracks > 0) && !(audio.video?.liveTracks > 0) && !live;
  const warnings = [];
  if (idleReleased === false) warnings.push('IDLE_MEDIA_PRESENT');
  if (observationAgeMs !== null && observationAgeMs > 15000) warnings.push('OBSERVATION_DELAYED');
  if (Object.keys(notices).some(k => ['abandoned'].includes(k))) warnings.push('FAILURE_NOTICE_ABANDONED');
  if (storage.audioFiles >= 90) warnings.push('AUDIO_STORE_NEAR_CAPACITY');
  if (storage.error) warnings.push('STORAGE_OBSERVATION_FAILED');
  if (storage.availableBytes !== undefined && storage.availableBytes < 256*1024*1024) warnings.push('LOW_DISK_SPACE');
  const agendaRequired = manager.featureEnabled('agenda') && manager.agenda?.policy.enabled;
  const ready = manager.state === 'ready' && (!agendaRequired || !!manager.agenda?.ready);
  return {
    version: require('../package.json').version, at: new Date(now).toISOString(), ready, service: safeCode(manager.state),
    features: manager.featureStore?.status() || { enabled: { outgoing:true, incoming:true, live:true, agenda:true } },
    health: { observationAgeMs, browserQueueBusyMs: manager.browserBusySince == null ? null : finite(now-manager.browserBusySince), idleMediaReleased: idleReleased, warnings },
    current: { present: !!active, externalCallPresent: !!manager.observed && !active, state: active ? safeCode(active.state) : null, kind: active ? active.direction === 'incoming' ? 'incoming_private' : active.groupId ? 'group' : 'private' : null,
      ageSeconds: active ? finite((now-active.requestedAt)/1000) : null, recoveryAttempts: active?.recovery?.attempts || 0,
      video: !!active?.video, videoRuntime: audio.video || null, live: !!live, liveUsage: live ? { inputAudioSeconds: finite(live.inputSeconds), modelOutputAudioSeconds: finite(live.outputSeconds), bridgeAcceptedAudioSeconds: finite(live.bridgeAcceptedSeconds), speechFrames: finite(live.receivedSpeechFrames), connectionRenewals: finite(live.renewals) } : null, audioArmed: !!audio.armed, liveTracks: Number.isInteger(audio.liveTracks) ? audio.liveTracks : null },
    destinations: { ownerGroupOrdersAllowed: !!manager.destinationPolicy?.ownerAnyGroupEnabled, enabledGroups: manager.destinationPolicy?.groups.filter(group => manager.destinationPolicy.groupEnabled(group.id)).length ?? null, localPrivate: manager.destinationPolicy?.privateIds.size ?? null, ownerExternalOrdersAllowed: !!manager.destinationPolicy?.ownerExternalEnabled },
    history: { scope: 'retained_journal', calls: records.length, states, reasons, failureNotices: notices },
    agenda: { ready: !!manager.agenda?.ready, states: schedules, reservedKeys: Object.keys(manager.agenda?.reservedKeys || {}).length },
    latencies: { dial: latency(records.map(r => finite(r.startedAt-r.requestedAt))), answer: latency(records.map(r => finite(r.connectedAt-r.startedAt))),
      firstLiveAudio: latency(records.map(r => finite(r.usage?.firstAudioLatencyMs))) },
    usage: { scope: 'retained_finished_calls_with_usage', coveredCalls: records.filter(r => r.usage).length, inputAudioSeconds: sum(records.map(r => finite(r.usage?.inputAudioSeconds))),
      modelOutputAudioSeconds: sum(records.map(r => finite(r.usage?.modelOutputAudioSeconds))), bridgeAcceptedAudioSeconds: sum(records.map(r => finite(r.usage?.bridgeAcceptedAudioSeconds))),
      billingCost: null, billingNote: 'No cost or remaining API quota is inferred from audio duration.' },
    resources, storage
  };
}
class Operations {
  constructor({ manager, audioStore, runtime, privateDir }) { Object.assign(this, { manager, audioStore, runtime, privateDir }); }
  async report() {
    const memory = process.memoryUsage(), cpu = process.resourceUsage();
    const tracked = {};
    for (const record of this.runtime.records || []) if (identity(record.pid) === record.identity) { const kind = safeCode(record.kind); tracked[kind] = (tracked[kind] || 0)+1; }
    const resources = { scope: 'calls_service_process', uptimeSeconds: process.uptime(), rssBytes: memory.rss, heapUsedBytes: memory.heapUsed, cpuUserMicros: cpu.userCPUTime, cpuSystemMicros: cpu.systemCPUTime, trackedProcesses: tracked };
    let storage;
    try {
      const [space, names, jobs] = await Promise.all([fs.statfs(this.privateDir), fs.readdir(this.audioStore.dir), fs.readdir(path.join(this.audioStore.dir, 'tmp'))]);
      const wavs = names.filter(name => /^[a-f0-9]{64}\.wav$/.test(name));
      const sizes = await Promise.all(wavs.map(name => fs.lstat(path.join(this.audioStore.dir,name))));
      storage = { availableBytes: space.bavail*space.bsize, audioFiles: sizes.filter(s => s.isFile()).length, audioBytes: sizes.filter(s => s.isFile()).reduce((n,s) => n+s.size,0),
        tempJobs: jobs.length, preparing: !!this.audioStore.busy, subprocesses: this.audioStore.jobs.size };
    } catch { storage = { error: 'STORAGE_OBSERVATION_FAILED' }; }
    return reportSnapshot({ manager:this.manager, now:this.manager.clock.now(), resources, storage });
  }
}
module.exports = { Operations, reportSnapshot };
