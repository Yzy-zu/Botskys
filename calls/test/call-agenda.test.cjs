// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { CallAgenda } = require('../service/call-agenda.cjs');
const { CallManager } = require('../service/manager.cjs');
const { Journal } = require('../service/journal.cjs');
const { createCallDestinationPolicy } = require('../policy/callDestinations');
const { createSchedulePolicy, validateScheduledTime } = require('../policy/callScheduleTime');
const owner = '525511112222@s.whatsapp.net', group = { id: '123456789012345@g.us', name: 'Botsky Lab' };
const policy = createSchedulePolicy({ CALLS_SCHEDULE_ENABLED: 'true' });
async function fixture(t) {
 const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'botsky-agenda-')); let now = Date.parse('2026-10-25T12:00:00-06:00');
 const driver = { dials: 0, call: null, async start() {}, async close() { this.call = null; }, async disarmAudio() { return { released: true }; },
  async snapshot() { return this.call || { active: false }; }, async end() { this.call = null; },
  async dial(target, { cancelled }) { if(cancelled()) throw Object.assign(Error('cancelled'), { code: 'CANCELLED' }); this.dials++; return this.call = { active: true, id: 'native-' + this.dials, outgoing: true, isGroup: true, groupId: target.id, connected: false }; } };
 const manager = new CallManager({ driver, journal: new Journal(path.join(dir, 'journal.json')), group,
  clock: { now: () => now, setTimeout: () => 0, clearTimeout() {} }, destinationPolicy: createCallDestinationPolicy({ lab: group, env: { BOTSKY_OWNER_NUMBER: owner } }),
  audioStore: { get: async () => ({ id: 'a'.repeat(64), durationSeconds: 2 }), read: async () => ({ asset: { id: 'a'.repeat(64) }, data: Buffer.from('audio') }) } });
 await manager.boot();
 const args = { file: path.join(dir, 'agenda.json'), manager, policy, now: () => now };
 const agenda = manager.agenda = new CallAgenda(args); await agenda.init();
 t.after(async () => { await manager.stop(); await fs.rm(dir, { recursive: true, force: true }); });
 const request = overrides => ({ key: 'scheduled-message', targetJid: group.id, origin: { chatId: owner, requesterId: owner },
  dueAt: now + 60000, timeZone: policy.timeZone, sourceReceipt: { chatId: owner, messageKey: { id: 'message-1', remoteJid: owner, fromMe: false } }, ...overrides });
 return { dir, manager, agenda, driver, args, request, advance: ms => { now += ms; }, now: () => now };
}
async function drain(manager) { for(let i=0;i<8;i++) { const queue=manager.queue; await queue; await manager.journal.writes; if(queue===manager.queue)return; } }

test('PM10: schedule is durable, retains the selected audio and makes one call at its time', async t => {
 const f = await fixture(t), request = f.request({ audioId: 'a'.repeat(64), endAfterAudio: true });
 const created = await f.agenda.create(request); await f.agenda.tick(); assert.equal(f.driver.dials, 0);
 assert.equal((await f.agenda.create(request)).replayed, true);
 f.advance(60000); await Promise.all([f.agenda.tick(), f.agenda.tick()]); await drain(f.manager);
 assert.equal(f.driver.dials, 1); assert.equal(f.manager.active.audioId, request.audioId); assert.deepEqual(f.manager.active.origin, request.origin);
 await f.agenda.tick(); assert.equal(f.driver.dials, 1);
 const loaded = new CallAgenda(f.args); await loaded.init(); await loaded.tick(); assert.equal(f.driver.dials, 1);
 assert.equal(loaded.rows[0].status, 'dispatched'); assert.equal(created.schedule.id.length, 8);
});

test('PM10: future agenda is private to its source and requester and reprogramming is idempotent', async t => {
 const f=await fixture(t), created=await f.agenda.create(f.request());
 assert.equal((await f.agenda.list({ chatId: group.id, requesterId: owner })).schedules.length,0);
 const update={id:created.schedule.id,origin:f.request().origin,key:'update-message',dueAt:f.now()+120000,timeZone:policy.timeZone};
 await f.agenda.update(update); assert.equal((await f.agenda.update(update)).replayed,true); assert.equal(f.agenda.rows[0].revision,2);
 f.advance(60000); await f.agenda.tick(); assert.equal(f.driver.dials,0);
 await f.agenda.cancel({id:created.schedule.id,origin:f.request().origin});
 f.advance(60000); await f.agenda.tick(); assert.equal(f.driver.dials,0); assert.equal(f.agenda.rows[0].status,'cancelled');
 assert.equal(Object.hasOwn(f.manager.journal.cancelledKeys,'scheduled-message'),true);
});

test('PM10: cancellation during a claimed dispatch prevents the late call', async t => {
 const f=await fixture(t), created=await f.agenda.create(f.request()); let release,entered;
 const gate=new Promise(r=>{release=r}), reached=new Promise(r=>{entered=r});
 const original=f.manager.startCall.bind(f.manager);
 f.manager.startCall=async args=>{entered();await gate;return original(args);};
 f.advance(60000); const work=f.agenda.tick(); await reached;
 await f.agenda.cancel({id:created.schedule.id,origin:f.request().origin}); release(); await work; await drain(f.manager);
 assert.equal(f.driver.dials,0); assert.equal(f.agenda.rows[0].status,'cancelled');
});

test('PM10: restart after claiming cannot replay an uncertain offer, with or without a call receipt', async t => {
 for(const dispatched of [false,true]) {
  const f=await fixture(t); await f.agenda.create(f.request()); f.advance(60000);
  if(dispatched){await f.agenda.tick();await drain(f.manager);}
  f.agenda.rows[0].status='executing';await f.agenda.save();
  const loaded=new CallAgenda(f.args);await loaded.init();await loaded.tick();
  assert.equal(f.driver.dials,dispatched?1:0);assert.equal(loaded.rows[0].status,dispatched?'dispatched':'interrupted');
  assert.ok(f.manager.journal.byKey('scheduled-message'));
 }
});

test('PM10: overdue, busy and outside-hours events fail once without moving themselves or calling anyone', async t => {
 for(const kind of ['overdue','busy','outside']) {
  const f=await fixture(t);await f.agenda.create(f.request());
  if(kind==='busy')f.manager.observed={active:true,id:'foreign'};
  f.advance(kind==='overdue'?120001:kind==='outside'?12*3600000:60000);
  await f.agenda.tick();await f.agenda.tick();
  assert.equal(f.driver.dials,0,kind);assert.equal(f.agenda.rows[0].status,'failed');
  assert.equal(f.manager.journal.byKey('scheduled-message').failureNotice.state,'pending');
 }
});

test('PM10: failed claim persistence and corrupt agenda cannot dispatch', async t => {
 const f=await fixture(t);await f.agenda.create(f.request());f.advance(60000);
 const original=f.agenda.save.bind(f.agenda);f.agenda.save=async()=>{throw Error('disk failure');};
 await f.agenda.tick();assert.equal(f.driver.dials,0);
 assert.equal(f.agenda.rows[0].status,'failed');assert.equal(f.agenda.rows[0].reason,'RESERVATION_SAVE_FAILED');
 assert.equal(f.manager.journal.byKey('scheduled-message').failureNotice.state,'pending');
 // Reload the receipt from disk, as a new process would.
 const journal=new Journal(f.manager.journal.file);await journal.load();f.manager.journal=journal;
 assert.equal(journal.byKey('scheduled-message').reason,'SCHEDULE_RESERVATION_SAVE_FAILED');
 // The old disk row is still pending, but its durable failure receipt fences a restart.
 const loaded=new CallAgenda(f.args);await loaded.init();await loaded.tick();assert.equal(loaded.rows[0].status,'failed');assert.equal(f.driver.dials,0);
 f.agenda.save=original;await f.agenda.tick();assert.equal(f.agenda.pendingFailures.size,0);assert.equal(f.driver.dials,0);
 await fs.writeFile(f.args.file,'{"version":1,"rows":[{}]}');
 await assert.rejects(new CallAgenda(f.args).init(),{code:'AGENDA_INVALID'});assert.equal(f.driver.dials,0);
});

test('PM10: timezone and daytime checks are independent of the server timezone', () => {
 const now=Date.parse('2026-10-25T12:00:00-06:00');
 assert.equal(validateScheduledTime(Date.parse('2026-10-26T08:00:00-06:00'),policy,{now}),Date.parse('2026-10-26T08:00:00-06:00'));
 for(const fecha of ['2026-10-26T07:59:00-06:00','2026-10-26T23:00:00-06:00']) assert.throws(()=>validateScheduledTime(Date.parse(fecha),policy,{now}));
 assert.throws(()=>validateScheduledTime(Date.parse('2026-10-26T22:59:00-06:00'),policy,{now,maxSeconds:60}),{code:'SCHEDULE_WINDOW_SHORT'});
});

test('PM10: a delayed manager queue cannot turn an expired schedule into a late offer', async t => {
 const f=await fixture(t);await f.agenda.create(f.request());f.advance(60000);
 let release;const gate=new Promise(r=>{release=r;});
 const blocked=f.manager.command(()=>gate);const tick=f.agenda.tick();
 for(let i=0;i<20&&f.agenda.rows[0].status!=='executing';i++)await new Promise(r=>setImmediate(r));
 f.advance(60001);release();await blocked;await tick;await drain(f.manager);
 assert.equal(f.driver.dials,0);assert.equal(f.agenda.rows[0].status,'failed');
});

test('PM10: source privacy and destination permissions still apply after creation', async t => {
 const f=await fixture(t),created=await f.agenda.create(f.request());
 await assert.rejects(f.agenda.cancel({id:created.schedule.id,origin:{chatId:group.id,requesterId:owner}}),{code:'SCHEDULE_NOT_FOUND'});
 f.manager.destinationPolicy.authorize=()=>{throw Object.assign(Error('revoked'),{code:'DESTINATION_NOT_ENABLED'});};
 f.advance(60000);await f.agenda.tick();assert.equal(f.driver.dials,0);assert.equal(f.agenda.rows[0].status,'failed');
});

test('PM10: a concurrent move to a later date invalidates the old due-time snapshot', async t => {
 const f=await fixture(t),created=await f.agenda.create(f.request());f.advance(60000);
 let release;const gate=new Promise(r=>{release=r;});const blocked=f.agenda.serial(()=>gate);
 const update=f.agenda.update({id:created.schedule.id,origin:f.request().origin,key:'move-before-claim',dueAt:f.now()+60000,timeZone:policy.timeZone});
 const tick=f.agenda.tick();release();await blocked;await update;await tick;await drain(f.manager);
 assert.equal(f.driver.dials,0);assert.equal(f.agenda.rows[0].status,'pending');
 f.advance(60000);await f.agenda.tick();await drain(f.manager);assert.equal(f.driver.dials,1);
});

test('PM10: an archived schedule key stays spent even after call history and agenda detail are pruned', async t => {
 const f=await fixture(t);await f.agenda.create(f.request());f.agenda.rows[0].status='dispatched';await f.agenda.save();
 f.advance(2*86400000);await f.agenda.create(f.request({key:'another-future-message'}));
 assert.equal(f.agenda.rows.some(r=>r.key==='scheduled-message'),false);
 const loaded=new CallAgenda(f.args);await loaded.init();
 await assert.rejects(loaded.create(f.request()),{code:'SCHEDULE_ALREADY_PROCESSED'});assert.equal(f.driver.dials,0);
});

test('PM11: paused agenda preserves pending work, never dispatches while disabled, and does not replay missed events', async t => {
 const f=await fixture(t);await f.agenda.create(f.request());f.manager.featureStore={value:{agenda:false}};f.advance(60000);
 await f.agenda.tick();assert.equal(f.driver.dials,0);assert.equal(f.agenda.rows[0].status,'pending');
 f.advance(60001);f.manager.featureStore.value.agenda=true;await f.agenda.tick();
 assert.equal(f.driver.dials,0);assert.equal(f.agenda.rows[0].status,'failed');
});

test('agenda list follows the current due date without reordering stored events or exposing another source', async t => {
 const f=await fixture(t);
 const late=await f.agenda.create(f.request({key:'created-first-later',dueAt:f.now()+120000}));
 const early=await f.agenda.create(f.request({key:'created-second-earlier',dueAt:f.now()+60000}));
 const originalOrder=f.agenda.rows.map(row=>row.id);
 assert.deepEqual((await f.agenda.list(f.request().origin)).schedules.map(row=>row.id),[early.schedule.id,late.schedule.id]);
 await f.agenda.update({id:late.schedule.id,origin:f.request().origin,key:'move-earlier-date',dueAt:f.now()+30000,timeZone:policy.timeZone});
 assert.deepEqual((await f.agenda.list(f.request().origin)).schedules.map(row=>row.id),[late.schedule.id,early.schedule.id]);
 assert.deepEqual(f.agenda.rows.map(row=>row.id),originalOrder);
 assert.equal((await f.agenda.list({chatId:group.id,requesterId:owner})).schedules.length,0);
});


test('PM11: failed reservation and journal writes are retried only as bookkeeping, even while paused', async t => {
 const f=await fixture(t);await f.agenda.create(f.request());f.advance(60000);
 const save=f.agenda.save.bind(f.agenda),journalSave=f.manager.journal.save.bind(f.manager.journal);
 f.agenda.save=async()=>{throw Error('disk');};f.manager.journal.save=async()=>{throw Error('journal');};
 await f.agenda.tick();await f.agenda.tick();
 assert.equal(f.driver.dials,0);assert.equal(f.agenda.rows[0].status,'failed');
 assert.equal(f.manager.journal.byKey('scheduled-message'),undefined);assert.equal(f.agenda.pendingFailures.size,1);
 f.agenda.save=save;f.manager.journal.save=journalSave;
 f.agenda.policy={...f.agenda.policy,enabled:false};await f.agenda.tick();await f.agenda.tick();
 assert.equal(f.agenda.pendingFailures.size,0);assert.equal(f.driver.dials,0);
 const records=f.manager.journal.records.filter(r=>r.key==='scheduled-message');assert.equal(records.length,1);
 assert.equal(records[0].failureNotice.state,'pending');
 const loaded=new CallAgenda(f.args);await loaded.init();assert.equal(loaded.rows[0].status,'failed');
});

test('PM11: result queries normalize pasted IDs, stay source scoped and never dial', async t => {
 const f=await fixture(t),created=await f.agenda.create(f.request());
 const id='  #'+created.schedule.id.toUpperCase()+'  ',origin=f.request().origin;
 assert.equal((await f.agenda.get({id,origin})).result.state,'pending');
 await assert.rejects(f.agenda.get({id,origin:{chatId:group.id,requesterId:owner}}),{code:'SCHEDULE_NOT_FOUND'});
 await assert.rejects(f.agenda.get({id:'bad id',origin}),{code:'SCHEDULE_NOT_FOUND'});
 await f.agenda.update({id,origin,key:'normalized-update',dueAt:f.now()+120000,timeZone:policy.timeZone});
 await f.agenda.cancel({id,origin});assert.equal((await f.agenda.get({id,origin})).result.state,'cancelled');assert.equal(f.driver.dials,0);
});

test('PM11: result explanations are bounded, private and do not invent a successful call', () => {
 const {scheduleResult}=require('../service/schedule-result.cjs');
 for(const reason of ['SCHEDULE_RESERVATION_SAVE_FAILED','SCHEDULE_MISSED','SCHEDULE_CALL_BUSY','remote_rejected','not_answered']) {
  const result=scheduleResult({status:'dispatched'},{state:'failed',reason});assert.equal(typeof result.explanation,'string');assert.doesNotMatch(result.explanation,/SCHEDULE_|remote_rejected|not_answered/);
 }
 assert.equal(scheduleResult({status:'dispatched'}).state,'unknown');
 assert.equal(scheduleResult({status:'dispatched'},{state:'connected',reason:'private-secret'}).explanation,'La llamada está conectada.');
 for(const value of ['private-secret','__proto__','constructor']) {
  const result=scheduleResult({status:'failed',reason:value},{state:value,reason:value});
  assert.equal(result.state,'unknown');assert.equal(typeof result.explanation,'string');assert.equal(JSON.stringify(result).includes(value),false);
 }
});

test('Owner any-group schedules store the verified name and recheck membership at dispatch',async t=>{
 const f=await fixture(t);const targetJid='120363000000888@g.us';let joined=true;
 f.manager.destinationPolicy=createCallDestinationPolicy({lab:group,env:{BOTSKY_OWNER_NUMBER:owner,CALLS_OWNER_ANY_GROUP_ENABLED:'true'}});
 f.driver.resolveGroup=async()=>{if(!joined)throw Object.assign(Error('left'),{code:'GROUP_NOT_JOINED'});return {id:targetJid,name:'Pepino'};};
 const created=await f.agenda.create(f.request({targetJid}));assert.equal(created.schedule.target,'Pepino');
 joined=false;f.advance(60000);await f.agenda.tick();await drain(f.manager);
 assert.equal(f.driver.dials,0);assert.equal(f.agenda.rows[0].status,'failed');
});

test('Group lookup cannot overwrite a call that arrives while membership is being verified',async t=>{
 const f=await fixture(t);const targetJid='120363000000888@g.us';
 f.manager.destinationPolicy=createCallDestinationPolicy({lab:group,env:{BOTSKY_OWNER_NUMBER:owner,CALLS_OWNER_ANY_GROUP_ENABLED:'true'}});
 f.driver.resolveGroup=async()=>{f.manager.observed={active:true,id:'foreign-during-lookup'};return {id:targetJid,name:'Pepino'};};
 await assert.rejects(f.manager.startCall({key:'directory-race',targetJid,origin:f.request().origin}),{code:'CALL_BUSY'});
 assert.equal(f.manager.active,null);assert.equal(f.driver.dials,0);assert.equal(f.manager.observed.id,'foreign-during-lookup');
 assert.equal(f.manager.journal.byKey('directory-race'),undefined);
});

test('High audit: a confirmed cancellation during membership lookup cannot create a call reservation',async t=>{
 const f=await fixture(t);const targetJid='120363000000888@g.us';let enter,release;
 const reached=new Promise(resolve=>{enter=resolve;}),gate=new Promise(resolve=>{release=resolve;});
 f.manager.destinationPolicy=createCallDestinationPolicy({lab:group,env:{BOTSKY_OWNER_NUMBER:owner,CALLS_OWNER_ANY_GROUP_ENABLED:'true'}});
 f.driver.resolveGroup=async()=>{enter();await gate;return {id:targetJid,name:'Pepino'};};
 const start=f.manager.startCall({key:'cancel-member-lookup',targetJid,origin:f.request().origin});
 const rejected=assert.rejects(start,{code:'CANCELLED'});await reached;
 assert.equal((await f.manager.cancelKey('cancel-member-lookup')).cancelled,true);
 release();await rejected;await drain(f.manager);
 assert.equal(f.manager.active,null);assert.equal(f.driver.dials,0);assert.equal(f.manager.journal.byKey('cancel-member-lookup'),undefined);
});

test('Medium audit: an ordinary failed schedule retries its notice after journal recovery without dispatching again',async t=>{
 const f=await fixture(t);await f.agenda.create(f.request());f.advance(120001);
 const save=f.manager.journal.save.bind(f.manager.journal);f.manager.journal.save=async()=>{throw Error('journal unavailable');};
 await f.agenda.tick();await f.agenda.tick();assert.equal(f.agenda.rows[0].status,'failed');assert.equal(f.agenda.pendingFailures.size,1);
 assert.equal(f.manager.journal.byKey('scheduled-message'),undefined);assert.equal(f.driver.dials,0);
 f.manager.journal.save=save;f.agenda.policy={...f.agenda.policy,enabled:false};await f.agenda.tick();await f.agenda.tick();
 assert.equal(f.agenda.pendingFailures.size,0);assert.equal(f.manager.journal.records.length,1);assert.equal(f.driver.dials,0);
 const notice=(await f.manager.claimFailureNotices()).notices[0];assert.ok(notice);
 await f.manager.beginFailureNotice({callId:notice.callId,lease:notice.lease});
 await f.manager.ackFailureNotice({callId:notice.callId,lease:notice.lease,delivered:true});
 const journal=new Journal(f.manager.journal.file);await journal.load();f.manager.journal=journal;
 const loaded=new CallAgenda(f.args);await loaded.init();await loaded.tick();
 assert.equal(journal.records.length,1);assert.equal(journal.records[0].failureNotice.state,'sent');assert.equal(f.driver.dials,0);
});

test('Medium audit: both failed-state and notice persistence recover without turning the event pending again',async t=>{
 const f=await fixture(t);await f.agenda.create(f.request());f.advance(120001);
 const agendaSave=f.agenda.save.bind(f.agenda),journalSave=f.manager.journal.save.bind(f.manager.journal);let writes=0;
 f.agenda.save=async()=>{if(++writes===1)return agendaSave();throw Error('agenda unavailable');};
 f.manager.journal.save=async()=>{throw Error('journal unavailable');};
 await f.agenda.tick();assert.equal(f.agenda.rows[0].status,'failed');assert.equal(f.agenda.pendingFailures.size,1);assert.equal(f.driver.dials,0);
 f.agenda.save=agendaSave;f.manager.journal.save=journalSave;await f.agenda.tick();await f.agenda.tick();
 assert.equal(f.agenda.pendingFailures.size,0);assert.equal(f.manager.journal.records.length,1);assert.equal(f.driver.dials,0);
 const loaded=new CallAgenda(f.args);await loaded.init();await loaded.tick();assert.equal(loaded.rows[0].status,'failed');assert.equal(f.driver.dials,0);
});

test('Medium audit: startup reconstructs failed-notice work and can finish it after a transient journal outage',async t=>{
 const f=await fixture(t);await f.agenda.create(f.request());
 Object.assign(f.agenda.rows[0],{status:'failed',reason:'MISSED'});await f.agenda.save();
 const save=f.manager.journal.save.bind(f.manager.journal);f.manager.journal.save=async()=>{throw Error('journal unavailable');};
 const loaded=new CallAgenda(f.args);await loaded.init();assert.equal(loaded.ready,true);assert.equal(loaded.pendingFailures.size,1);
 f.manager.journal.save=save;await loaded.tick();await loaded.tick();assert.equal(loaded.pendingFailures.size,0);assert.equal(f.manager.journal.records.length,1);assert.equal(f.driver.dials,0);
});

test('Medium audit: an old failed event awaiting its notice is not pruned by a new schedule',async t=>{
 const f=await fixture(t);await f.agenda.create(f.request());f.advance(120001);
 const save=f.manager.journal.save.bind(f.manager.journal);f.manager.journal.save=async()=>{throw Error('journal unavailable');};
 await f.agenda.tick();const failedId=f.agenda.rows[0].id;f.advance(25*3600000);
 await f.agenda.create(f.request({key:'new-future-event'}));assert.equal(f.agenda.rows.some(row=>row.id===failedId),true);
 f.manager.journal.save=save;await f.agenda.tick();assert.equal(f.agenda.pendingFailures.size,0);assert.equal(f.driver.dials,0);
});

test('LIVE-1: a scheduled Live topic survives restart, remains outside visible agenda data and reaches the intended call',async t=>{
 const f=await fixture(t);let context;
 f.manager.liveController={prepare:async record=>{context=record.liveRequest;},stop:async()=>{},status:()=>null};
 const created=await f.agenda.create(f.request({live:true,liveRequest:'Hablen de música'}));assert.equal(created.schedule.liveRequest,undefined);
 const loaded=f.manager.agenda=new CallAgenda(f.args);await loaded.init();assert.equal(loaded.rows[0].call.liveRequest,'Hablen de música');
 assert.equal(JSON.stringify(await loaded.list(f.request().origin)).includes('Hablen de música'),false);
 f.advance(60000);await loaded.tick();await drain(f.manager);assert.equal(context,'Hablen de música');assert.equal(f.driver.dials,1);
});

test('LIVE-2: unlimited scheduled Live survives reload and ends at the local closing hour',async t=>{
 const f=await fixture(t);f.advance(Date.parse('2026-10-25T22:50:00-06:00')-f.now());
 f.manager.liveController={prepare:async()=>{},start:async()=>{},stop:async()=>{},status:()=>null};
 await f.agenda.create(f.request({live:true}));const loaded=new CallAgenda(f.args);await loaded.init();
 assert.equal(loaded.rows[0].call.maxSeconds,null);f.manager.agenda=loaded;
 f.advance(60000);await loaded.tick();await drain(f.manager);f.driver.call.connected=true;
 f.driver.call.audience={known:true,connectedHumans:1,source:'fixture'};await f.manager.poll();
 const record=f.manager.active;assert.equal(record.maxSeconds,null);assert.equal(record.deadlineReason,'schedule_window_closed');
 assert.equal(record.expiresAt,Date.parse('2026-10-25T23:00:00-06:00'));assert.equal(f.driver.dials,1);
 // This fixture deliberately stores no timers; inspect and invoke the captured deadline.
 let deadline,delay;f.manager.clock.setTimeout=(fn,ms)=>{deadline=fn;delay=ms;return 1;};
 f.manager.answerDeadline(record);assert.equal(delay,9*60*1000);f.advance(delay);deadline();await new Promise(r=>setImmediate(r));await drain(f.manager);
 assert.equal(f.manager.active,null);assert.equal(record.reason,'schedule_window_closed');
});

test('LIVE-2: explicit long scheduled Live must fit the window and indefinite Live needs answer margin',async t=>{
 const f=await fixture(t);const dueAt=Date.parse('2026-10-25T22:00:00-06:00');
 await f.agenda.create(f.request({live:true,maxSeconds:1800,dueAt}));
 await assert.rejects(f.agenda.create(f.request({key:'too-long-live-window',live:true,maxSeconds:7200,dueAt})),{code:'SCHEDULE_WINDOW_SHORT'});
 await assert.rejects(f.agenda.create(f.request({key:'too-late-live-window',live:true,dueAt:Date.parse('2026-10-25T22:59:00-06:00')})),{code:'SCHEDULE_WINDOW_SHORT'});
});

test('LIVE-2: scheduled closing hour follows the configured timezone across a DST change',()=>{
 const {scheduledWindowEnd}=require('../policy/callScheduleTime');
 const dstPolicy=createSchedulePolicy({CALLS_SCHEDULE_ENABLED:'true',CALLS_SCHEDULE_TIMEZONE:'America/New_York',CALLS_SCHEDULE_START_HOUR:'0'});
 assert.equal(scheduledWindowEnd(Date.parse('2026-11-01T00:00:00-04:00'),dstPolicy),Date.parse('2026-11-01T23:00:00-05:00'));
 const midnightPolicy={...dstPolicy,endHour:24};
 assert.equal(scheduledWindowEnd(Date.parse('2026-11-01T00:00:00-04:00'),midnightPolicy),Date.parse('2026-11-02T00:00:00-05:00'));
});
