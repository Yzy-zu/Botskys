'use strict';
const {createHash} = require('node:crypto');
const {createCallDestinationPolicy, canonicalPhoneJid} = require('./callDestinations');
const {createSchedulePolicy} = require('./callScheduleTime');
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k)+':'+canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
function makePolicy(document) {
  document=structuredClone(document);
  const freeze = value => {if(value && typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
  freeze(document);
  if (!document || Object.keys(document).some(k => !['version','instance','account','epoch','owner','actors','privateChats','groups','features','schedule'].includes(k)) || document.version !== 1 || !Number.isSafeInteger(document.epoch) || document.epoch < 1 || document.epoch > 1000000 || typeof document.instance!=='string' || !document.instance.trim() || typeof document.account!=='string' || !document.account.trim() || canonicalPhoneJid(document.owner) !== document.owner) throw Error('CALLS_POLICY_INVALID');
  const {actors, privateChats, groups, features, schedule} = document;
  if (!Array.isArray(actors) || !actors.length || actors.length > 100 || actors.some(v=>canonicalPhoneJid(v)!==v) || new Set(actors).size!==actors.length || !Array.isArray(privateChats) || privateChats.length>100 || new Set(privateChats).size!==privateChats.length || privateChats.some(v=>canonicalPhoneJid(v)!==v) || !Array.isArray(groups) || groups.length > 50 || groups.some(g=>!g || Object.keys(g).some(k=>!['id','name','maxParticipants'].includes(k)) || !/^\d+(?:-\d+)?@g\.us$/.test(g.id) || typeof g.name!=='string' || !g.name.trim() || !Number.isInteger(g.maxParticipants) || g.maxParticipants<2 || g.maxParticipants>32) || new Set(groups.map(g=>g.id)).size!==groups.length) throw Error('CALLS_POLICY_IDENTITIES');
  if (!features || Object.keys(features).sort().join(',')!=='agenda,incoming,live,outgoing' || Object.values(features).some(v=>typeof v!=='boolean') || features.incoming !== false) throw Error('CALLS_POLICY_FEATURES');
  if (!schedule || Object.keys(schedule).sort().join(',')!=='endHour,startHour,timeZone' || schedule.timeZone!=='America/Mexico_City' || !Number.isInteger(schedule.startHour) || !Number.isInteger(schedule.endHour)) throw Error('CALLS_POLICY_SCHEDULE');
  const lab = groups[0] ? {...groups[0],minParticipants:2} : {id:'',name:'Sin grupo configurado',minParticipants:2,maxParticipants:2,enabled:false};
  const env = {BOTSKY_OWNER_NUMBER:document.owner.split('@')[0],CALLS_PRIVATE_ALLOWED_NUMBERS:privateChats.join(','),CALLS_GROUPS_JSON:JSON.stringify(groups.slice(1)),CALLS_GROUP_AUDIENCE_VALIDATED:'true',CALLS_SAME_CHAT_ONLY:'true',CALLS_SCHEDULE_ENABLED:String(features.agenda),CALLS_SCHEDULE_TIMEZONE:schedule.timeZone,CALLS_SCHEDULE_START_HOUR:String(schedule.startHour),CALLS_SCHEDULE_END_HOUR:String(schedule.endHour)};
  const destination = createCallDestinationPolicy({lab,env});
  // The legacy destination helper always includes owner; the explicit new allowlist is authoritative.
  destination.privateIds.clear(); for (const id of privateChats) destination.privateIds.add(id);
  const authorize = destination.authorize, localEnabled = destination.localEnabled;
  destination.localEnabled = origin => !!origin && actors.includes(origin.requesterId) && localEnabled(origin);
  destination.authorize = (id, origin) => {
    if (!origin || !actors.includes(origin.requesterId) || !destination.localEnabled(origin)) throw Object.assign(Error('CALLS_DENIED'),{code:'DESTINATION_NOT_ENABLED',status:403});
    return authorize(id,origin);
  };
  return {document,revision:createHash('sha256').update(canonical(document)).digest('hex'),group:lab,destinationPolicy:destination,schedulePolicy:createSchedulePolicy(env),features:{...features},env};
}
module.exports={makePolicy,canonical};
