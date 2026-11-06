// Port técnico de Zhana; fixtures locales, sin navegador ni proveedores.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { GroupDirector } = require('../service/group-director.cjs');

function fixture() {
  let now = 100000;
  const director = new GroupDirector({ now: () => now, waitMs: 5 });
  director.begin({ greeting: true }); director.speaking();
  director.proposeQuestion('¿Prefieren playa o montaña?', director.current);
  director.outputText('¿Prefieren playa o montaña?'); director.generationFinished();
  const token = director.token(); director.end();
  return { director, token, setNow: value => { now = value; } };
}

test('A pending question starts from confirmed playback end and accepts a contextual answer once, without a name', async () => {
  const f = fixture(), d = f.director;
  assert.equal(d.snapshot().pendingQuestion, null);
  f.setNow(120000); d.playbackEnded(f.token, 119500);
  assert.equal(d.snapshot().pendingQuestion.openedAt, 119500);
  assert.equal(d.snapshot().pendingQuestion.expiresAt, 149500);
  f.setNow(149000); d.begin(); d.transcript('Preferimos montaña.');
  f.setNow(150000); d.snapshot(); // Speech began in time even if classification finishes later.
  assert.deepEqual(await d.authorize(false, d.current, undefined, true), { allowVoice: true });
  assert.equal(d.snapshot().pendingQuestion, null);
  d.end(); d.begin(); d.transcript('Y también otra cosa.');
  assert.deepEqual(await d.authorize(false, d.current, undefined, true), { allowVoice: false });
});

test('Expired questions, unrelated speech, interrupted playback and retired calls cannot authorize name-free speech', async () => {
  const expired = fixture(); expired.director.playbackEnded(expired.token, 100000);
  expired.setNow(130001); expired.director.begin(); expired.director.transcript('Montaña.');
  assert.deepEqual(await expired.director.authorize(false, expired.director.current, undefined, true), { allowVoice: false });
  const unrelated = fixture(); const d = unrelated.director;
  d.playbackEnded(unrelated.token, 100000); d.begin(); d.transcript('Oye Ana, ¿viste el partido?');
  assert.deepEqual(await d.authorize(false, d.current, undefined, false), { allowVoice: false });
  assert.equal(d.pendingQuestion, null);
  const interrupted = fixture(); interrupted.director.begin();
  interrupted.director.playbackEnded(interrupted.token, 100000);
  assert.equal(interrupted.director.pendingQuestion, null);
  const closed = fixture(); closed.director.close(); closed.director.playbackEnded(closed.token, 100000);
  assert.equal(closed.director.pendingQuestion, null);
});

test('A declared question may have a spoken invitation after it, but an unspoken declared question cannot open a window', () => {
  const d = new GroupDirector({ now: () => 100000 });
  d.begin({ greeting: true }); d.speaking();
  assert.equal(d.proposeQuestion('¿Qué prefieren?', d.current).success, true);
  d.outputText('¿Qué prefieren? Cuéntenme.'); d.generationFinished(); const token = d.token(); d.end();
  d.playbackEnded(token, 100000); assert.ok(d.pendingQuestion);
  const unspoken = new GroupDirector({ now: () => 100000 });
  unspoken.begin({ greeting: true }); unspoken.speaking(); unspoken.proposeQuestion('¿Qué prefieren?', unspoken.current);
  unspoken.outputText('Hoy hace buen día.'); unspoken.generationFinished(); const other = unspoken.token(); unspoken.end();
  unspoken.playbackEnded(other, 100000); assert.equal(unspoken.pendingQuestion, null);
});
