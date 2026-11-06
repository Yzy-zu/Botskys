// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test=require('node:test');const assert=require('node:assert/strict');
const {liveSetupError,liveCloseError,NEXT_KEY_ERRORS}=require('../service/live-errors.cjs');
test('LIVE-2C: provider statuses distinguish credential failures from invalid input and unavailable models',()=>{
 const cases=[[{code:400,status:'INVALID_ARGUMENT'},'LIVE_REQUEST_INVALID'],[{code:400,details:[{reason:'API_KEY_INVALID'}]},'LIVE_KEY_REJECTED'],
 [{code:401},'LIVE_KEY_REJECTED'],[{code:403},'LIVE_KEY_REJECTED'],[{code:429},'LIVE_QUOTA_EXCEEDED'],[{code:503},'LIVE_PROVIDER_UNAVAILABLE'],
 [{status:'RESOURCE_EXHAUSTED'},'LIVE_QUOTA_EXCEEDED'],[{status:'UNAVAILABLE'},'LIVE_PROVIDER_UNAVAILABLE'],[{code:404},'LIVE_MODEL_UNAVAILABLE'],[{},'LIVE_PROVIDER_ERROR'],[{code:402},'LIVE_PROVIDER_ERROR']];
 for(const [input,expected]of cases)assert.equal(liveSetupError(input),expected);
 for(const code of ['LIVE_REQUEST_INVALID','LIVE_MODEL_UNAVAILABLE','LIVE_PROVIDER_ERROR'])assert.equal(NEXT_KEY_ERRORS.has(code),false);
});
test('LIVE-2C: setup close reasons are classified without retaining sensitive text',()=>{
 const cases=[[1007,'API key not valid. secret-key','LIVE_KEY_REJECTED'],[1007,'Quota exceeded project-private','LIVE_QUOTA_EXCEEDED'],[1007,'Unknown field in setup','LIVE_REQUEST_INVALID'],
 [1011,'','LIVE_PROVIDER_UNAVAILABLE'],[1007,'Model not found','LIVE_MODEL_UNAVAILABLE'],[1006,'unknown','LIVE_SOCKET_CLOSED']];
 for(const [code,reason,expected]of cases)assert.equal(liveCloseError(code,Buffer.from(reason)),expected);
});
