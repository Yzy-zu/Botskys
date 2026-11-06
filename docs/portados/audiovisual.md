# Audiovisual · R9 parcial, NO cerrado

Referencia técnica Zhana7e12d54 fijada en R0; audio-bridge.cjs, startLive/liveAudio/
clearLive: PCM s16le mono24k, paquete hasta96000bytes, presión10s y epoch creciente
para retirar audio interrumpido. Hash de la referencia consultada en R9-partial.json.
No se importa servicio/bucle/browser antiguo ni perfil, sesión, cookie o VRM privado.

Primer componente nuevo: calls/pcm-queue.cjs. Cola por callId/sessionId/epoch con
secuencia monótona, copia de entrada, memoria480000bytes (10s), drenaje por número
de muestras, clear solo con epoch superior y cierre irreversible. Consume Buffer
PCM explícito, nunca interpreta audio o texto como comandos. Devuelve s16le24k mono.
No reproduce ni captura sonido y no existe aún un servidor de llamadas conectado.

Dos pruebas Node20.20.2 con muestras sintéticas reales en Buffer: signo/amplitud,
identidad ajena/epoch viejo, duplicados, presión/reintento, drenaje y limpieza.
Evidencia R9-pcm-initial-tests.txt. No es una llamada, WebRTC, pista, PCM recibido
del teléfono ni escucha humana. R9 continúa NOT_CLOSED/REVIEW.

Falta: control/agenda/recados de llamadas con recibos, exclusión/cancelación y
journal; audio/resampling/captura/liberación, Gemini Live y audiencia/control;
video/clips/avatar y ACK de frame. Contrato de servicio autenticado nuevo, puertos
optativos, datos propios. Verificar inventario audiovisual48archivos y soluciones
por dominio sin arrastrar fases de otros planes. WebRTC local real pendiente;
no abrir navegador ni copiar perfiles activos por instrucción del propietario.
Evaluar frontera local sin navegador antes de necesitar aclaración externa.
Dependencias Node de llamada aún no instaladas en Botsky ni tomadas del runtime.

Al5% se guarda este checkpoint. R0–R8 cerrados localmente; R10 local espera R9;
proveedores/remoto R10 y transición R11 necesitan encargo posterior. Sin NLP,
servicios activos, mensajes remotos, llamadas o GitHub.
