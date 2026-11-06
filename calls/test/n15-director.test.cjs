// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { GroupDirector } = require('../service/group-director.cjs');

async function spokenQuestion({ late = false } = {}) {
  let now = 100000;
  const d = new GroupDirector({ now: () => now, waitMs: 10 });
  d.transcript('Zhana, haz una pregunta'); await d.authorize(true, d.current);
  d.proposeQuestion('¿Qué película prefieren?', d.current);
  if (!late) d.outputText('¿Qué película prefieren?'); // transcription can precede PCM
  d.speaking(); d.generationFinished(); const token = d.token(); d.end();
  assert.equal(d.pendingQuestion, null);
  d.playbackEnded(token, now);
  if (late) d.outputText('¿Qué película prefieren?'); // can also follow drain/turnComplete
  return { d, advance: ms => { now += ms; } };
}
for (const late of [false, true]) test(`N15 question opens after real drain when output transcription arrives ${late ? 'late' : 'before PCM'}`, async () => {
  const { d } = await spokenQuestion({ late });
  assert.equal(d.pendingQuestion?.openedAt, 100000);
  d.begin(); d.transcript('La de aventuras');
  assert.deepEqual(await d.authorize(false, d.current, undefined, true), { allowVoice: true });
  assert.equal(d.pendingQuestion, null);
});
test('N15 expired question and incidental mention cannot authorize unrelated voice', async () => {
  const { d, advance } = await spokenQuestion(); advance(30001); d.begin(); d.transcript('La de aventuras');
  assert.deepEqual(await d.authorize(false, d.current, undefined, true), { allowVoice: false });
  d.begin(); d.transcript('Ayer Zhana dijo algo');
  assert.deepEqual(await d.authorize(false, d.current), { allowVoice: false });
});
test('N15 interrupted and reconnecting turns cannot retain or regain old permission', async () => {
  const d = new GroupDirector({ waitMs: 10 });
  d.transcript('Zhana, hola'); await d.authorize(true,d.current); d.speaking();
  const token=d.token(); d.interrupted();
  assert.equal(d.allowed,false); assert.equal(d.isCurrent(token),false);
  assert.deepEqual(await d.authorize(true,d.current),{allowVoice:false});
  d.begin(); const waiting=d.authorize(true,d.current); d.setReconnecting(true); d.transcript('Zhana, hola');
  assert.deepEqual(await waiting,{allowVoice:false}); d.setReconnecting(false);
  assert.deepEqual(await d.authorize(true,d.current),{allowVoice:false});
  d.begin(); d.transcript('Zhana, seguimos'); assert.deepEqual(await d.authorize(true,d.current),{allowVoice:true});
});
test('N15 unspoken transcription never creates a pending question', () => {
  const d=new GroupDirector({now:()=>100000}); d.outputText('¿Vamos?'); d.generationFinished(); d.playbackEnded(d.token(),100000);
  assert.equal(d.pendingQuestion,null);
});

test('N15 an intervening topic consumes the question even if Live stays silent', async () => {
  const {d}=await spokenQuestion(); d.begin(); d.transcript('Voy por agua');
  d.begin(); d.transcript('La de aventuras');
  assert.deepEqual(await d.authorize(false,d.current,undefined,true),{allowVoice:false});
});

for (const pendingAnswer of [false,true]) test(`N15 a delayed ${pendingAnswer ? 'answer' : 'invocation'} authorization cannot override a newer rejection`, async()=>{
  const d=pendingAnswer ? (await spokenQuestion()).d : new GroupDirector({waitMs:20});
  if(pendingAnswer) d.begin();
  const first=d.authorize(!pendingAnswer,d.current,undefined,pendingAnswer);
  assert.deepEqual(await d.authorize(false,d.current),{allowVoice:false});
  d.transcript('Zhana, sí');
  assert.deepEqual(await first,{allowVoice:false});assert.equal(d.allowed,false);
});
