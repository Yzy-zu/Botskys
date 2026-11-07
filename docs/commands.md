# Comandos v1 · generado desde el registro

Sintaxis disponible no acredita handler ni aceptación de dominio. Los bloques se consultan en el relevo.
Alias: /descargar → /dl, /conv → /convertir, /web → /buscar

Opciones antes del texto final. Desde su primer carácter se conserva el resto literalmente; -- fuerza texto literal.
Comillas agrupan campos múltiples; dentro de comillas solo se escapan la comilla activa y la barra.
No se interpreta shell. Mayúsculas de datos/IDs/URLs se conservan; nombres de comando/enum sin tildes no distinguen mayúsculas.
IDs son los de resultados reales. Fechas completas y horas 00:00–23:59; America/Mexico_City, validación de futuro en backend.

Cada campo, tipo, rango, valor por defecto, permiso y decisión de portado: [commands.json](commands.json) y [command-matrix.csv](command-matrix.csv).

## /admin

```text
/admin advertir TARGET
Ejemplo: /admin advertir ID_REAL
Permiso: owner; implementación: R8.
/admin quitar-aviso TARGET WARNING_ID
Ejemplo: /admin quitar-aviso ID_REAL 1
Permiso: owner; implementación: R8.
/admin avisos [TARGET]
Ejemplo: /admin avisos
Permiso: owner; implementación: R8.
/admin expulsar TARGET
Ejemplo: /admin expulsar ID_REAL
Permiso: owner; implementación: R8.
/admin ban TARGET
Ejemplo: /admin ban ID_REAL
Permiso: owner; implementación: R8.
/admin unban TARGET
Ejemplo: /admin unban ID_REAL
Permiso: owner; implementación: R8.
/admin promover TARGET
Ejemplo: /admin promover ID_REAL
Permiso: owner; implementación: R8.
/admin degradar TARGET
Ejemplo: /admin degradar ID_REAL
Permiso: owner; implementación: R8.
/admin silenciar
Ejemplo: /admin silenciar
Permiso: owner; implementación: R8.
/admin desilenciar
Ejemplo: /admin desilenciar
Permiso: owner; implementación: R8.
/admin cerrar
Ejemplo: /admin cerrar
Permiso: owner; implementación: R8.
/admin abrir
Ejemplo: /admin abrir
Permiso: owner; implementación: R8.
/admin xp-dar [--objetivo TARGET] [--cuenta ACCOUNT_ID] AMOUNT
Ejemplo: /admin xp-dar --cuenta 1 1
Permiso: owner; implementación: R8.
/admin xp-quitar [--objetivo TARGET] [--cuenta ACCOUNT_ID] AMOUNT
Ejemplo: /admin xp-quitar --cuenta 1 1
Permiso: owner; implementación: R8.
/admin nuclear-preparar
Ejemplo: /admin nuclear-preparar
Permiso: owner; implementación: R8.
/admin nuclear-confirmar DRAFT_ID
Ejemplo: /admin nuclear-confirmar ID_REAL
Permiso: owner; implementación: R8.
/admin nuclear-cancelar DRAFT_ID
Ejemplo: /admin nuclear-cancelar ID_REAL
Permiso: owner; implementación: R8.
```

## /avatar

```text
/avatar fondo studio|neon|sunset|night
Ejemplo: /avatar fondo studio
Permiso: call_authorized; implementación: R9.
/avatar expresion neutral|relaxed|happy|angry|sad|surprised|wink|laugh [--duracion DURATION]
Ejemplo: /avatar expresion neutral
Permiso: call_authorized; implementación: R9.
/avatar gesto wave|nod|shake_head|hand_to_chest [--duracion DURATION]
Ejemplo: /avatar gesto wave
Permiso: call_authorized; implementación: R9.
/avatar rubor suave [--duracion DURATION]
Ejemplo: /avatar rubor suave
Permiso: call_authorized; implementación: R9.
```

## /ayuda

```text
/ayuda [TOPIC]
Ejemplo: /ayuda
Permiso: public; implementación: R2.
Lista familias o detalla un comando.
```

## /bj

```text
/bj iniciar [BET]
Ejemplo: /bj iniciar
Permiso: friend; implementación: R7.
/bj mesa [BET]
Ejemplo: /bj mesa
Permiso: friend; implementación: R7.
/bj entrar [GAME_ID]
Ejemplo: /bj entrar
Permiso: friend; implementación: R7.
/bj repartir [GAME_ID]
Ejemplo: /bj repartir
Permiso: friend; implementación: R7.
/bj pedir [GAME_ID]
Ejemplo: /bj pedir
Permiso: friend; implementación: R7.
/bj plantarse [GAME_ID]
Ejemplo: /bj plantarse
Permiso: friend; implementación: R7.
/bj doblar [GAME_ID]
Ejemplo: /bj doblar
Permiso: friend; implementación: R7.
/bj estado [GAME_ID]
Ejemplo: /bj estado
Permiso: friend; implementación: R7.
/bj cancelar [GAME_ID]
Ejemplo: /bj cancelar
Permiso: friend; implementación: R7.
```

## /bot

```text
/bot estado
Ejemplo: /bot estado
Permiso: friend; implementación: R2.
/bot modo apagado|discreto|activo
Ejemplo: /bot modo apagado
Permiso: owner; implementación: R2.
/bot pausa 15|30|60
Ejemplo: /bot pausa 15
Permiso: owner; implementación: R2.
/bot reanudar
Ejemplo: /bot reanudar
Permiso: owner; implementación: R2.
```

## /broma

```text
/broma [LABEL]
Ejemplo: /broma
Permiso: friend; implementación: R7.
```

## /buscar

```text
/buscar [--terminos REQUIRED_TERMS] QUERY
Ejemplo: /buscar ejemplo
Permiso: friend; implementación: R3.
```

## /cancelar

```text
/cancelar ID
Ejemplo: /cancelar ID_REAL
Permiso: friend; implementación: R2.
```

## /clip

```text
/clip lista
Ejemplo: /clip lista
Permiso: call_authorized; implementación: R9.
/clip poner [CLIP_ID] [--nombre QUERY]
Ejemplo: /clip poner ID_REAL
Permiso: call_authorized; implementación: R9.
/clip pausa
Ejemplo: /clip pausa
Permiso: call_authorized; implementación: R9.
/clip seguir
Ejemplo: /clip seguir
Permiso: call_authorized; implementación: R9.
/clip repetir
Ejemplo: /clip repetir
Permiso: call_authorized; implementación: R9.
/clip siguiente
Ejemplo: /clip siguiente
Permiso: call_authorized; implementación: R9.
/clip parar
Ejemplo: /clip parar
Permiso: call_authorized; implementación: R9.
/clip volumen VOLUME
Ejemplo: /clip volumen 0.7
Permiso: call_authorized; implementación: R9.
/clip ajustar subir|bajar ADJUSTMENT
Ejemplo: /clip ajustar subir 0.1
Permiso: call_authorized; implementación: R9.
```

## /confirmar

```text
/confirmar ID
Ejemplo: /confirmar ID_REAL
Permiso: friend; implementación: R2.
```

## /contactos

```text
/contactos
Ejemplo: /contactos
Permiso: owner; implementación: R6.
```

## /convertir

```text
/convertir pdf|docx|doc|odt|rtf|xlsx|xls|ods|csv|pptx|ppt|odp|txt|png|jpg|webp|json|html|md + adjunto o cita exacta
Ejemplo: /convertir pdf
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /coop

```text
/coop crear CATEGORY TARGET_XP
Ejemplo: /coop crear ejemplo 50
Permiso: friend; implementación: R7.
/coop aportar CHALLENGE_ID AMOUNT
Ejemplo: /coop aportar ID_REAL 1
Permiso: friend; implementación: R7.
/coop estado [CHALLENGE_ID]
Ejemplo: /coop estado
Permiso: friend; implementación: R7.
/coop cancelar CHALLENGE_ID
Ejemplo: /coop cancelar ID_REAL
Permiso: friend; implementación: R7.
```

## /daily

```text
/daily
Ejemplo: /daily
Permiso: friend; implementación: R7.
```

## /dl

```text
/dl mp3 [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] URL
Ejemplo: /dl mp3 https://media.w3.org/2010/05/bunny/trailer.mp4
Permiso: friend; implementación: R3.
/dl mp4 [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] URL
Ejemplo: /dl mp4 https://media.w3.org/2010/05/bunny/trailer.mp4
Permiso: friend; implementación: R3.
/dl webm [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] URL
Ejemplo: /dl webm https://media.w3.org/2010/05/bunny/trailer.mp4
Permiso: friend; implementación: R3.
/dl srt [--idioma es|en] URL
Ejemplo: /dl srt https://media.w3.org/2010/05/bunny/trailer.mp4
Permiso: friend; implementación: R3.
/dl buscar mp3|mp4|webm|srt [--fuente youtube|dailymotion|vimeo|facebook|instagram|tiktok|spotify|pornhub|xnxx|adult] [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] [--idioma es|en] QUERY
Ejemplo: /dl buscar mp3 ejemplo
Permiso: friend; implementación: R3.
/dl elegir VIEW_ID CHOICE
Ejemplo: /dl elegir ID_REAL 1
Permiso: friend; implementación: R3.
/dl anterior mp3|mp4|webm|srt [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] [--idioma es|en]
Ejemplo: /dl anterior mp3
Permiso: friend; implementación: R3.
```

## /drive

```text
/drive guardar + adjunto o cita exacta
Ejemplo: /drive guardar
Permiso: friend; implementación: R6.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
/drive buscar [QUERY]
Ejemplo: /drive buscar
Permiso: friend; implementación: R6.
/drive elegir VIEW_ID CHOICE
Ejemplo: /drive elegir ID_REAL 1
Permiso: friend; implementación: R6.
/drive cuota
Ejemplo: /drive cuota
Permiso: owner; implementación: R6.
```

## /editar

```text
/editar mp3|mp4|webm|srt [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] [--idioma es|en] + adjunto o cita exacta
Ejemplo: /editar mp3
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /encuesta

```text
/encuesta crear QUESTION OPTIONS ...
Ejemplo: /encuesta crear "¿Hora?" "Opción 1" "Opción 2"
Permiso: friend; implementación: R5.
/encuesta votar POLL_ID CHOICE
Ejemplo: /encuesta votar 1 1
Permiso: friend; implementación: R5.
/encuesta resultados POLL_ID
Ejemplo: /encuesta resultados 1
Permiso: friend; implementación: R5.
/encuesta cerrar POLL_ID
Ejemplo: /encuesta cerrar 1
Permiso: friend; implementación: R5.
```

## /escuela

```text
/escuela resumen configurar ENABLED [--hora DIGEST_TIME]
Ejemplo: /escuela resumen configurar si --hora 18:00
Permiso: owner; implementación: R5.
/escuela resumen estado
Ejemplo: /escuela resumen estado
Permiso: friend; implementación: R5.
```

## /estado

```text
/estado ID
Ejemplo: /estado ID_REAL
Permiso: friend; implementación: R2.
```

## /hh

```text
/hh iniciar [--duracion DURACION_CON_UNIDAD]
Ejemplo: /hh iniciar
Permiso: owner; implementación: R7.
--duracion: entero con unidad s, m, h o d; ejemplo 10m. Rango: 60–86400 segundos. Por defecto: 3600 segundos.
/hh parar [EVENT_ID]
Ejemplo: /hh parar
Permiso: owner; implementación: R7.
/hh estado [EVENT_ID]
Ejemplo: /hh estado
Permiso: friend; implementación: R7.
/hh lluvia [EVENT_ID]
Ejemplo: /hh lluvia
Permiso: owner; implementación: R7.
/hh airdrop [EVENT_ID]
Ejemplo: /hh airdrop
Permiso: owner; implementación: R7.
/hh reclamar DROP_ID
Ejemplo: /hh reclamar ID_REAL
Permiso: friend; implementación: R7.
```

## /horario

```text
/horario agregar --materia SUBJECT --dia WEEKDAY --inicio START_TIME --fin END_TIME
Ejemplo: /horario agregar --materia ejemplo --dia 1 --inicio 12:00 --fin 13:00
Permiso: owner; implementación: R5.
/horario listar [--dia WEEKDAY]
Ejemplo: /horario listar
Permiso: friend; implementación: R5.
/horario borrar LESSON_ID
Ejemplo: /horario borrar 1
Permiso: owner; implementación: R5.
```

## /ia

```text
/ia TEXT
Ejemplo: /ia ejemplo
Permiso: friend; implementación: R4.
```

## /llamada

```text
/llamada estado
Ejemplo: /llamada estado
Permiso: call_authorized; implementación: R9.
/llamada colgar
Ejemplo: /llamada colgar
Permiso: call_authorized; implementación: R9.
/llamada cancelar
Ejemplo: /llamada cancelar
Permiso: call_authorized; implementación: R9.
/llamada programar DATE TIME [--duracion DURACION_CON_UNIDAD] [--tema LIVE_REQUEST] [--audio AUDIO_ID] [--terminar-audio] [--volumen VOLUME]
Ejemplo: /llamada programar 2026-12-01 12:00
Permiso: owner; implementación: R9.
--duracion: entero con unidad s, m, h o d; ejemplo 10m. Rango: 5–3600 segundos. Por defecto: 300 segundos.
/llamada agenda
Ejemplo: /llamada agenda
Permiso: owner; implementación: R9.
/llamada reprogramar ID DATE TIME
Ejemplo: /llamada reprogramar ID_REAL 2026-12-01 12:00
Permiso: owner; implementación: R9.
/llamada cancelar-agenda ID
Ejemplo: /llamada cancelar-agenda ID_REAL
Permiso: owner; implementación: R9.
```

## /llamar

```text
/llamar [--video] [--duracion DURACION_CON_UNIDAD] [--tema TOPIC]
Ejemplo: /llamar
Permiso: call_authorized; implementación: R9.
--duracion: entero con unidad s, m, h o d; ejemplo 10m. Rango: 5–3600 segundos. Por defecto: 300 segundos.
```

## /mc

```text
/mc estado
Ejemplo: /mc estado
Permiso: friend; implementación: R8.
/mc jugadores
Ejemplo: /mc jugadores
Permiso: friend; implementación: R8.
/mc mundos
Ejemplo: /mc mundos
Permiso: friend; implementación: R8.
/mc mods
Ejemplo: /mc mods
Permiso: friend; implementación: R8.
/mc config
Ejemplo: /mc config
Permiso: friend; implementación: R8.
/mc diagnostico
Ejemplo: /mc diagnostico
Permiso: friend; implementación: R8.
/mc iniciar
Ejemplo: /mc iniciar
Permiso: owner; implementación: R8.
/mc parar
Ejemplo: /mc parar
Permiso: owner; implementación: R8.
/mc reiniciar
Ejemplo: /mc reiniciar
Permiso: owner; implementación: R8.
/mc backup
Ejemplo: /mc backup
Permiso: owner; implementación: R8.
/mc recuperar
Ejemplo: /mc recuperar
Permiso: owner; implementación: R8.
/mc mod activar NAME
Ejemplo: /mc mod activar ejemplo
Permiso: owner; implementación: R8.
/mc mod desactivar NAME
Ejemplo: /mc mod desactivar ejemplo
Permiso: owner; implementación: R8.
/mc consola COMMAND
Ejemplo: /mc consola ejemplo
Permiso: owner; implementación: R8.
```

## /mem

```text
/mem guardar [--tipo preferencia|dato] TEXT
Ejemplo: /mem guardar ejemplo
Permiso: friend; implementación: R5.
/mem listar [--tipo preferencia|dato] [--pagina PAGE]
Ejemplo: /mem listar
Permiso: friend; implementación: R5.
/mem corregir MEMORY_ID TEXT
Ejemplo: /mem corregir 1 ejemplo
Permiso: friend; implementación: R5.
/mem olvidar MEMORY_ID
Ejemplo: /mem olvidar 1
Permiso: friend; implementación: R5.
/mem borrar-todo
Ejemplo: /mem borrar-todo
Permiso: friend; implementación: R5.
```

## /nota

```text
/nota guardar TEXT
Ejemplo: /nota guardar ejemplo
Permiso: friend; implementación: R2.
```

## /notas

```text
/notas [--pagina PAGE] [QUERY]
Ejemplo: /notas
Permiso: friend; implementación: R2.
```

## /ocr

```text
/ocr + adjunto o cita exacta
Ejemplo: /ocr
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /pack

```text
/pack catalogo [--categoria CATEGORY] [--pagina PAGE]
Ejemplo: /pack catalogo
Permiso: friend; implementación: R7.
/pack comprar CATEGORY
Ejemplo: /pack comprar ejemplo
Permiso: friend; implementación: R7.
/pack confirmar PURCHASE_ID
Ejemplo: /pack confirmar ID_REAL
Permiso: friend; implementación: R7.
/pack estado PURCHASE_ID
Ejemplo: /pack estado ID_REAL
Permiso: friend; implementación: R7.
```

## /pdf

```text
/pdf iniciar + adjunto o cita exacta
Ejemplo: /pdf iniciar
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
/pdf agregar + adjunto o cita exacta
Ejemplo: /pdf agregar
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
/pdf terminar
Ejemplo: /pdf terminar
Permiso: friend; implementación: R3.
/pdf cancelar
Ejemplo: /pdf cancelar
Permiso: friend; implementación: R3.
/pdf extraer PAGES + adjunto o cita exacta
Ejemplo: /pdf extraer 1,3-5
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
/pdf reintentar ID [--confirmar-incierto]
Ejemplo: /pdf reintentar ID_REAL
Permiso: friend; implementación: R3.
```

## /qr

```text
/qr + adjunto o cita exacta
Ejemplo: /qr
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /reaccion

```text
/reaccion saludo|risa|pensando|sonrojo
Ejemplo: /reaccion saludo
Permiso: friend; implementación: R3.
```

## /recado

```text
/recado preparar --para RECIPIENTS [--fuente actual|cita] [--adjunto] [TEXT]
Ejemplo: /recado preparar --para Amiga -- hola
Permiso: owner; implementación: R6.
/recado estado DRAFT_ID
Ejemplo: /recado estado ID_REAL
Permiso: owner; implementación: R6.
/recado enviar DRAFT_ID
Ejemplo: /recado enviar ID_REAL
Permiso: owner; implementación: R6.
/recado cancelar DRAFT_ID
Ejemplo: /recado cancelar ID_REAL
Permiso: owner; implementación: R6.
```

## /recordar

```text
/recordar en DURACION_CON_UNIDAD TEXT
Ejemplo: /recordar en 10m ejemplo
Permiso: friend; implementación: R5.
duration_seconds: entero con unidad s, m, h o d; ejemplo 10m. Rango: 1–3.1536e+07 segundos.
/recordar el DATE TIME TEXT
Ejemplo: /recordar el 2026-12-01 12:00 ejemplo
Permiso: friend; implementación: R5.
```

## /recordatorio

```text
/recordatorio cancelar REMINDER_ID
Ejemplo: /recordatorio cancelar 1
Permiso: friend; implementación: R5.
/recordatorio archivar REMINDER_ID
Ejemplo: /recordatorio archivar 1
Permiso: friend; implementación: R5.
```

## /recordatorios

```text
/recordatorios [--pagina PAGE] [--cerradas]
Ejemplo: /recordatorios
Permiso: friend; implementación: R5.
```

## /ruleta

```text
/ruleta crear [BET]
Ejemplo: /ruleta crear
Permiso: friend; implementación: R7.
/ruleta entrar ROOM_ID
Ejemplo: /ruleta entrar ID_REAL
Permiso: friend; implementación: R7.
/ruleta jugar ROOM_ID
Ejemplo: /ruleta jugar ID_REAL
Permiso: friend; implementación: R7.
/ruleta estado [ROOM_ID]
Ejemplo: /ruleta estado
Permiso: friend; implementación: R7.
/ruleta cancelar ROOM_ID
Ejemplo: /ruleta cancelar ID_REAL
Permiso: friend; implementación: R7.
```

## /saldo

```text
/saldo
Ejemplo: /saldo
Permiso: friend; implementación: R7.
```

## /sticker

```text
/sticker + adjunto o cita exacta
Ejemplo: /sticker
Permiso: friend; implementación: R3.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /tarea

```text
/tarea crear [--materia SUBJECT] --fecha DUE_DATE [--hora DUE_TIME] [--adjunto] TEXT
Ejemplo: /tarea crear --fecha 2026-12-01 ejemplo
Permiso: friend; implementación: R5.
/tarea completar TASK_ID
Ejemplo: /tarea completar 1
Permiso: friend; implementación: R5.
/tarea borrar TASK_ID
Ejemplo: /tarea borrar 1
Permiso: friend; implementación: R5.
/tarea archivo TASK_ID
Ejemplo: /tarea archivo 1
Permiso: friend; implementación: R5.
```

## /tareas

```text
/tareas [--pagina PAGE] [--cerradas]
Ejemplo: /tareas
Permiso: friend; implementación: R5.
```

## /top

```text
/top
Ejemplo: /top
Permiso: friend; implementación: R7.
```

## /transcribir

```text
/transcribir [--salida texto|resumen|ambos] + adjunto o cita exacta
Ejemplo: /transcribir
Permiso: friend; implementación: R4.
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /voces

```text
/voces
Ejemplo: /voces
Permiso: friend; implementación: R4.
```

## /voz

```text
/voz [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio] TEXT
Ejemplo: /voz ejemplo
Permiso: friend; implementación: R4.
/voz crear [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio] [--duracion REQUESTED_SECONDS] TEXT
Ejemplo: /voz crear ejemplo
Permiso: friend; implementación: R4.
/voz cita [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio]
Ejemplo: /voz cita
Permiso: friend; implementación: R4.
/voz ultima [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio]
Ejemplo: /voz ultima
Permiso: friend; implementación: R4.
```
