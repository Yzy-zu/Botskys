'use strict';

const GROUP_VOICE_TOOL = { functionDeclarations: [{
  name: 'autorizar_turno', behavior: 'BLOCKING',
  description: 'Antes de responder por voz, decide si la intervención actual se dirige explícitamente a Botsky. Una mención casual no autoriza voz.',
  parameters: { type: 'OBJECT', properties: { addressed: { type: 'BOOLEAN' }, answeringPending: { type: 'BOOLEAN', description: 'La intervención responde directamente a la última pregunta que acabas de dejar a los participantes, sin cambiar de tema.' } }, required: ['addressed'] },
}, {
  name: 'dejar_pregunta', behavior: 'NON_BLOCKING',
  description: 'Registra una pregunta que dejas esperando respuesta de los participantes. No la uses para preguntas retóricas ni para texto que no vayas a decir.',
  parameters: { type: 'OBJECT', properties: { question: { type: 'STRING', description: 'Pregunta exacta que acabas de decir o vas a decir en voz alta.' } }, required: ['question'] },
}] };
const GROUP_VOICE_SYSTEM = `Estás en una llamada grupal. Te llamas Botsky.
Antes de CADA respuesta hablada a una intervención, llama autorizar_turno.
Interpreta la intervención actual: marca addressed=true si se dirigen a ti por el contexto, sin exigir un nombre o apodo fijo; una mención incidental, una frase de compra o charla entre humanos no son una invocación.
Si la herramienta devuelve allowVoice=false, escucha en silencio, sin disculpas, confirmaciones ni pedir silencio.
No ejecutes controles de clips por una mención casual. Puedes reaccionar visualmente sin hablar.
El saludo inicial responde al pedido de llamar y está autorizado. Cuando te interrumpan, escucha. No dispones de detector de voces superpuestas ni puedes identificar hablantes: si no entiendes un pedido dirigido a ti, pide que lo repitan sin inventar lo que dijeron.
Si acabas de preguntar algo a los participantes, cualquiera puede responder sin nombrarte: marca answeringPending=true solo si su respuesta continúa esa pregunta. El backend comprobará si la pregunta terminó de oírse y si sigue abierta durante sus 30 segundos. No atribuyas identidad a la voz. Una frase ajena o cambio de tema no es continuación.
Las nuevas preguntas deben dirigirse a ti según tu interpretación contextual. Cuando dejes una pregunta esperando respuesta, llama dejar_pregunta con la pregunta exacta. Es una herramienta silenciosa: no anuncies que registraste nada. No registres preguntas retóricas ni preguntas que no hayas dicho o no vayas a decir.`;

class GroupVoiceGate {
  constructor({ waitMs = 1500 } = {}) { this.waitMs = waitMs; this.epoch = 0; this.begin(); }
  begin({ greeting = false } = {}) {
    this.current?.finish?.();
    return this.current = { epoch: ++this.epoch, text: '', allowed: greeting, greeting };
  }
  transcript(text) {
    if (typeof text !== 'string' || !text || this.current.greeting) return;
    this.current.text = (this.current.text + text).slice(-8000);
    if (this.current.text.trim()) this.current.finish?.();
  }
  get allowed() { return this.current.allowed; }
  async authorize(addressed, turn, signal, authorization) {
    if (turn !== this.current || signal?.aborted) return { allowVoice: false };
    authorization ??= turn.authorizationVersion = (turn.authorizationVersion || 0) + 1;
    if (turn.greeting) return { allowVoice: true };
    turn.allowed = false;
    if (addressed !== true) return { allowVoice: false };
    // Transcription and tool messages can arrive independently. Require speech captured in the current turn as well as the semantic
    // decision; missing evidence leaves this turn closed.
    if (!turn.text.trim()) await new Promise(resolve => {
      const finish = () => { clearTimeout(timer); signal?.removeEventListener('abort', finish); if (turn.finish === finish) delete turn.finish; resolve(); };
      const timer = setTimeout(finish, this.waitMs);
      turn.finish = finish;
      signal?.addEventListener('abort', finish, { once: true });
      if (signal?.aborted) finish();
    });
    if (turn !== this.current || signal?.aborted) return { allowVoice: false };
    if (turn.authorizationVersion !== authorization) return { allowVoice: false };
    turn.allowed = addressed === true && Boolean(turn.text.trim());
    return { allowVoice: turn.allowed };
  }
  end() { if (this.current.greeting) this.begin(); }
  close() { this.begin(); }
}

module.exports = { GroupVoiceGate, GROUP_VOICE_TOOL, GROUP_VOICE_SYSTEM };
