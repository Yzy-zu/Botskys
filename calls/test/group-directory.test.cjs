// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { resolveJoinedGroup } = require('../service/group-directory.cjs');
const { dispatchGroupVoiceCall } = require('../service/group-call.cjs');
const { CallManager } = require('../service/manager.cjs');
const { createCallDestinationPolicy } = require('../policy/callDestinations');
const owner='525511112222@s.whatsapp.net',origin={chatId:owner,requesterId:owner};
function chat(id,name,member=true,extra={}) {
 return {id:{_serialized:id+'@g.us'},name,groupMetadata:{subject:name,participants:{iAmMember:()=>member}},...extra};
}
async function lookup(chats,query) {
 const window={WPP:{group:{getAllGroups:async()=>chats,getParticipants:async()=>[]}}};
 return vm.runInNewContext('('+resolveJoinedGroup.toString()+')(query)',{window,query});
}
test('Any-group directory resolves joined groups by exact/accent-insensitive name, partial name or ID',async()=>{
 const chats=[chat('100','PePiNo 🥒'),chat('101','Los católicos'),chat('102-200','Legado')];
 assert.equal((await lookup(chats,{name:'pepino'})).group.id,'100@g.us');
 assert.equal((await lookup(chats,{name:'catolicos'})).group.id,'101@g.us');
 assert.equal((await lookup(chats,{id:'100@g.us'})).group.name,'PePiNo 🥒');
 assert.equal((await lookup(chats,{name:'Legado'})).group.id,'102-200@g.us');
});
test('Any-group directory rejects ambiguous names, former groups, communities and unverifiable membership',async()=>{
 assert.equal((await lookup([chat('100','Pepe norte'),chat('101','Pepe sur')],{name:'Pepe'})).error,'ambiguous');
 assert.equal((await lookup([chat('100','Pepino',false)],{name:'Pepino'})).error,'not_found');
 assert.equal((await lookup([chat('100','Pepino',true,{isParentGroup:true})],{name:'Pepino'})).error,'not_found');
 const unknown=chat('100','Pepino');unknown.groupMetadata.participants={};
 assert.equal((await lookup([unknown],{name:'Pepino'})).error,'unverified');
 assert.equal((await lookup([unknown,chat('101','Pepino')],{name:'Pepino'})).error,'unverified');
});
test('Directory does not use an old positive membership flag after metadata refresh',async()=>{
 const target=chat('100','Pepino');let joined=true;target.groupMetadata.participants.iAmMember=()=>joined;
 const window={WPP:{group:{getAllGroups:async()=>[target],getParticipants:async()=>{joined=false;return [];}}}};
 const result=await vm.runInNewContext('('+resolveJoinedGroup.toString()+')({name:"Pepino"})',{window});
 assert.equal(result.error,'not_found');
});
test('Group resolver authorizes the owner before browser lookup and never calls dial',async()=>{
 const policy=createCallDestinationPolicy({lab:{id:'123456789012345@g.us',name:'Lab'},env:{BOTSKY_OWNER_NUMBER:owner,CALLS_OWNER_ANY_GROUP_ENABLED:'true'}});let lookups=0;
 const manager={destinationPolicy:policy,state:'ready',stopping:false,serial:async f=>f(),driver:{resolveGroup:async query=>{lookups++;return {id:'100@g.us',name:query.name};},dial:()=>assert.fail('Must not call')}};
 for(const candidate of [{chatId:'100@g.us',requesterId:owner},{chatId:'525533334444@s.whatsapp.net',requesterId:owner},null]) {
  await assert.rejects(CallManager.prototype.resolveGroup.call(manager,{origin:candidate,name:'Pepino'}),{code:'CALL_DESTINATION_DENIED'});
 }
 assert.equal(lookups,0);
 await assert.rejects(CallManager.prototype.resolveGroup.call(manager,{origin,name:'Pepino',id:'100@g.us'}),{code:'CALL_TARGET_CLARIFICATION'});
 const result=await CallManager.prototype.resolveGroup.call(manager,{origin,name:'Pepino'});assert.equal(result.group.id,'100@g.us');assert.equal(lookups,1);
});
test('Group resolver still requires the explicit any-group policy for owner searches',async()=>{
 const policy=createCallDestinationPolicy({lab:{id:'123456789012345@g.us',name:'Lab'},env:{BOTSKY_OWNER_NUMBER:owner}});
 const manager={destinationPolicy:policy,state:'ready',stopping:false,serial:async f=>f(),driver:{resolveGroup:async()=>assert.fail('Must not look up')}};
 await assert.rejects(CallManager.prototype.resolveGroup.call(manager,{origin,name:'Pepino'}),{code:'CALL_DESTINATION_DENIED'});
});
test('Native dispatch rechecks membership immediately before offering even for large joined groups',async()=>{
 let calls=0,member=false;
 const participants={iAmMember:()=>member,toArray:()=>Array(100).fill({})};
 const window={__botskyAudio:{token:'attempt'},WPP:{chat:{getActiveChat:()=>({id:{_serialized:'100@g.us'},groupMetadata:{participants}})}},require:name=>name==='WAWebCallCollection'?{}:{startWAWebVoipGroupCallFromChat:()=>{calls++;}}};
 const args={groupId:'100@g.us',token:'attempt',requireMembership:true,minParticipants:2,maxParticipants:Number.MAX_SAFE_INTEGER};
 assert.throws(()=>vm.runInNewContext('('+dispatchGroupVoiceCall.toString()+')(args)',{window,args}),/GROUP_NOT_JOINED/);assert.equal(calls,0);
 member=true;await vm.runInNewContext('('+dispatchGroupVoiceCall.toString()+')(args)',{window,args});assert.equal(calls,1);
});
