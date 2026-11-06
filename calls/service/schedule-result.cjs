'use strict';

const states = new Set(['starting','dialing','connecting','connected','recovering','ending','ended','failed','interrupted','pending','executing','cancelled']);
const reasons = {
  RESERVATION_SAVE_FAILED: 'No pude guardar la reserva para ejecutar el encargo. No inicié la llamada.',
  MISSED: 'Pasó la ventana de ejecución y el encargo no se realizó.',
  CALL_BUSY: 'Había otra llamada en curso a esa hora y no inicié una segunda.',
  NOT_READY: 'El servicio no estaba listo a esa hora.',
  STOPPING: 'El servicio se estaba deteniendo.',
  OUTGOING_DISABLED: 'Las llamadas salientes estaban desactivadas.',
  LIVE_DISABLED: 'La conversación en vivo estaba desactivada.',
  SCHEDULE_POLICY_CHANGED: 'Cambió la zona horaria configurada y el encargo necesita revisarse.',
  SCHEDULE_OUTSIDE_HOURS: 'La ejecución quedó fuera del horario permitido.',
  SCHEDULE_WINDOW_SHORT: 'No quedaba tiempo suficiente para contestar y terminar antes del cierre.',
  SCHEDULE_WINDOW_CLOSED: 'Se agotó el margen para iniciar la llamada a la hora acordada.',
  GROUP_NOT_JOINED: 'Zhana ya no pertenece a ese grupo o el chat no admite esa llamada.',
  GROUP_DIRECTORY_UNAVAILABLE: 'No pude verificar la pertenencia de Zhana al grupo.',
  DESTINATION_NOT_ENABLED: 'El destino ya no estaba habilitado para esa orden.',
  CALL_DESTINATION_DENIED: 'Los permisos actuales ya no permitían ese destino.',
  audio_completed: 'La llamada terminó al acabar el audio.',
  remote_rejected: 'La llamada fue rechazada.',
  not_answered: 'No se contestó la llamada.',
  answer_timeout: 'No se contestó dentro del tiempo de espera.',
  dial_timeout: 'No se confirmó el inicio de la llamada a tiempo.',
  native_end_during_dial: 'WhatsApp terminó el intento durante la marcación.',
  remote_or_native_end: 'WhatsApp informó que la llamada terminó.',
  requested: 'La llamada terminó a petición del usuario.',
  cancelled: 'El encargo fue cancelado.',
  cancelled_before_dial: 'El intento fue cancelado antes de marcar.',
  duration_limit: 'La llamada terminó al alcanzar el tiempo permitido.',
  audience_empty: 'La llamada terminó al quedarse sin oyentes.',
  remote_left: 'La otra persona salió de la llamada.',
  service_restart: 'El servicio se reinició y el encargo quedó interrumpido.',
  service_shutdown: 'El servicio se detuvo.',
  recovery_exhausted: 'Se agotó el único intento de recuperación.',
  recovery_timeout: 'La conexión no se recuperó dentro del margen permitido.',
  FEATURE_DISABLED: 'Se desactivó una función necesaria para iniciar esa llamada.',
  audio_failed: 'No se pudo reproducir el audio de la llamada.',
  live_failed: 'Falló la conversación en vivo.',
};
function scheduleResult(row, record) {
  const state = record?.state || row.status;
  // An offer receipt is not evidence that a phone rang or heard the audio.
  if (!record && row.status === 'dispatched') return { state: 'unknown', explanation: 'El encargo se envió al servicio, pero ya no conservo el detalle de cómo terminó.' };
  const current = {
    pending: 'Está programado y todavía no se ha ejecutado.', executing: 'Se está intentando ejecutar el encargo.',
    starting: 'Se está preparando la llamada.', dialing: 'Se está marcando.', connecting: 'La llamada se está conectando.',
    connected: 'La llamada está conectada.', recovering: 'Se está intentando recuperar la conexión.', ending: 'Se está cerrando la llamada.',
  };
  if (Object.hasOwn(current, state)) return { state, explanation: current[state] };
  const reason = record?.reason || row.reason;
  const lookup = key => Object.hasOwn(reasons, key) ? reasons[key] : null;
  const explanation = lookup(reason) || (typeof reason === 'string' && reason.startsWith('SCHEDULE_') ? lookup(reason.slice(9)) : null);
  return { state: states.has(state) ? state : 'unknown', explanation: explanation || (state === 'cancelled' ? 'El encargo fue cancelado.' : state === 'failed' ? 'El encargo falló; no tengo una causa más precisa para mostrar.' : state === 'interrupted' ? 'El encargo quedó interrumpido.' : 'No tengo una causa más precisa para confirmar cómo terminó.') };
}
module.exports = { scheduleResult };
