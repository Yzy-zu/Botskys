# Superficie audiovisual · R0

Referencia exacta y hashes: reference.json y audiovisual-files.json. Inventario
de contratos; ninguna de estas capacidades está implementada o activada en Botsky.

| Área | Operaciones / campos técnicos | Referencia | Evidencia de origen a consultar en R9 |
| --- | --- | --- | --- |
| Llamada | start/status/hangup/cancel; topic, max_seconds 5–3600, video | call_tools.py; manager, private-call, group-call | tests/test_call_tools.py; cancel-by-id, dial-cancellation |
| Agenda | create/list/get/update/cancel/cancelByKey; key, targetJid, origin(chatId, requesterId), dueAt, timeZone, maxSeconds, audioId, volume, live, liveRequest, endAfterAudio, durationFromAnswer=true, sourceReceipt; revisión | call-agenda; callScheduleTime/Id, callDestinations | call-agenda, recovery-guards |
| Audio preparado | upload/consulta/borrado; audioId propio, volumen, fin después de audio; plazos y propiedad | audio-store, audio-bridge, runtime | audio-store, audio-bridge |
| Live | entrada PCM s16le mono 16 kHz; salida PCM mono 24 kHz; chunks pares ≤96000 bytes, sesión y epoch; renovación, interrupción, drenaje | gemini-live, live-controller; liveCallRequest | gemini-live, live-controller, live-errors |
| Audiencia | cambios, vacío vs desconocido; permisos de voz, agradecimiento acotado; turnos, silencio, reconexión | group-director, group-voice-gate, spoken-controls, group-directory | group-director, group-voice-gate, call-audience |
| Video | pista ligada a llamada, primer frame, compositor/PIP, recuperación sin remarcar; audio conservado | native-video, video-bridge, browser | native-video; n12b/n13a/n13b |
| Clips | list/play/next/replay/pause/resume/stop/volume; query o selection 1–50; volume 0–1 o adjustment no cero ±1; key, scope y callId | clip-commands, clip-store; policy/clipRequest | clip-commands, clip-store, n12b-clips |
| Avatar | background/expression/gesture/blush; name; duration 1–15 s salvo fondo; ACK frame aplicado, capacidades del VRM | avatar-tools, avatar-renderer, avatar-motion, avatar-expressions | n13a-expressions/frame-confirmation; n13b-motion/render |
| Control hablado | sesión ya autorizada: despedida/colgar, conservar, volumen/voz, clips/avatar; sin herramientas generales | spoken-controls, gemini-live, manager | spoken-controls, spoken-audit-fixes, live-tools |
| Operación | auth/revisión de política, journal/notices, elegibilidad, propiedad de perfil; entrantes optativos | policy/auth, common, journal, incoming-policy, main | config-policy, operations, incoming-policy |

Los campos targetJid, callId nativo, audioId, key, origin, sourceReceipt y epoch se
resuelven en backend; no se piden al usuario. Botsky expondrá IDs propios visibles
y controles cortos ligados a la llamada autorizada. Programación, audio preparado,
ajuste relativo de volumen y duración de avatar requieren adaptación explícita en R1/R9.

No se ejecutan los tests antiguos como aceptación nueva. Ningún HTTP 200/pista
creada demuestra recepción Android. R9 necesita WebRTC local; R10 real y aceptación
humana siguen pendientes y requieren el encargo posterior indicado por el propietario.
