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
Solo el dueño.

/admin quitar-aviso TARGET WARNING_ID
Ejemplo: /admin quitar-aviso ID_REAL 1
Solo el dueño.

/admin avisos [TARGET]
Ejemplo: /admin avisos
Solo el dueño.

/admin expulsar TARGET
Ejemplo: /admin expulsar ID_REAL
Solo el dueño.

/admin ban TARGET
Ejemplo: /admin ban ID_REAL
Solo el dueño.

/admin unban TARGET
Ejemplo: /admin unban ID_REAL
Solo el dueño.

/admin promover TARGET
Ejemplo: /admin promover ID_REAL
Solo el dueño.

/admin degradar TARGET
Ejemplo: /admin degradar ID_REAL
Solo el dueño.

/admin silenciar
Ejemplo: /admin silenciar
Solo el dueño.

/admin desilenciar
Ejemplo: /admin desilenciar
Solo el dueño.

/admin cerrar
Ejemplo: /admin cerrar
Solo el dueño.

/admin abrir
Ejemplo: /admin abrir
Solo el dueño.

/admin xp-dar [--objetivo TARGET] [--cuenta ACCOUNT_ID] AMOUNT
Ejemplo: /admin xp-dar --cuenta 1 1
Solo el dueño.

/admin xp-quitar [--objetivo TARGET] [--cuenta ACCOUNT_ID] AMOUNT
Ejemplo: /admin xp-quitar --cuenta 1 1
Solo el dueño.

/admin nuclear-preparar
Ejemplo: /admin nuclear-preparar
Solo el dueño.

/admin nuclear-confirmar DRAFT_ID
Ejemplo: /admin nuclear-confirmar ID_REAL
Solo el dueño.
Requiere recibir la vista previa y confirmar con su comando vigente.

/admin nuclear-cancelar DRAFT_ID
Ejemplo: /admin nuclear-cancelar ID_REAL
Solo el dueño.
```

## /avatar

```text
/avatar fondo studio|neon|sunset|night
Ejemplo: /avatar fondo studio
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/avatar expresion neutral|relaxed|happy|angry|sad|surprised|wink|laugh [--duracion DURATION]
Ejemplo: /avatar expresion neutral
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/avatar gesto wave|nod|shake_head|hand_to_chest [--duracion DURATION]
Ejemplo: /avatar gesto wave
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/avatar rubor suave [--duracion DURATION]
Ejemplo: /avatar rubor suave
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.
```

## /ayuda

```text
/ayuda [TOPIC]
Ejemplo: /ayuda
Lista familias o detalla un comando.
```

## /bj

```text
/bj iniciar [BET]
Ejemplo: /bj iniciar

/bj mesa [BET]
Ejemplo: /bj mesa

/bj entrar [GAME_ID]
Ejemplo: /bj entrar

/bj repartir [GAME_ID]
Ejemplo: /bj repartir

/bj pedir [GAME_ID]
Ejemplo: /bj pedir

/bj plantarse [GAME_ID]
Ejemplo: /bj plantarse

/bj doblar [GAME_ID]
Ejemplo: /bj doblar

/bj estado [GAME_ID]
Ejemplo: /bj estado

/bj cancelar [GAME_ID]
Ejemplo: /bj cancelar
```

## /bot

```text
/bot estado
Ejemplo: /bot estado

/bot modo apagado|discreto|activo
Ejemplo: /bot modo apagado
Solo el dueño.

/bot pausa 15|30|60
Ejemplo: /bot pausa 15
Solo el dueño.

/bot reanudar
Ejemplo: /bot reanudar
Solo el dueño.
```

## /broma

```text
/broma [LABEL]
Ejemplo: /broma
```

## /buscar

```text
/buscar [--terminos REQUIRED_TERMS] QUERY
Ejemplo: /buscar ejemplo
```

## /cancelar

```text
/cancelar [ID]
Ejemplo: /cancelar
```

## /clip

```text
/clip lista
Ejemplo: /clip lista
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip poner [CLIP_ID] [--nombre QUERY]
Ejemplo: /clip poner ID_REAL
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip pausa
Ejemplo: /clip pausa
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip seguir
Ejemplo: /clip seguir
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip repetir
Ejemplo: /clip repetir
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip siguiente
Ejemplo: /clip siguiente
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip parar
Ejemplo: /clip parar
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip volumen VOLUME
Ejemplo: /clip volumen 0.7
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.

/clip ajustar subir|bajar ADJUSTMENT
Ejemplo: /clip ajustar subir 0.1
Requiere llamadas habilitadas y autorización en este chat.
Durante una llamada autorizada.
```

## /confirmar

```text
/confirmar ID
Ejemplo: /confirmar ID_REAL
Requiere recibir la vista previa y confirmar con su comando vigente.
```

## /contactos

```text
/contactos
Ejemplo: /contactos
Solo el dueño.
```

## /convertir

```text
/convertir pdf|docx|doc|odt|rtf|xlsx|xls|ods|csv|pptx|ppt|odp|txt|png|jpg|webp|json|html|md + adjunto o cita exacta
Ejemplo: /convertir pdf
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /coop

```text
/coop crear CATEGORY TARGET_XP
Ejemplo: /coop crear ejemplo 50

/coop aportar CHALLENGE_ID AMOUNT
Ejemplo: /coop aportar ID_REAL 1

/coop estado [CHALLENGE_ID]
Ejemplo: /coop estado

/coop cancelar CHALLENGE_ID
Ejemplo: /coop cancelar ID_REAL
```

## /daily

```text
/daily
Ejemplo: /daily
```

## /dl

```text
/dl mp3 [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] URL
Ejemplo: /dl mp3 https://media.w3.org/2010/05/bunny/trailer.mp4

/dl mp4 [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] URL
Ejemplo: /dl mp4 https://media.w3.org/2010/05/bunny/trailer.mp4

/dl webm [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] URL
Ejemplo: /dl webm https://media.w3.org/2010/05/bunny/trailer.mp4

/dl srt [--idioma es|en] URL
Ejemplo: /dl srt https://media.w3.org/2010/05/bunny/trailer.mp4

/dl buscar mp3|mp4|webm|srt [--fuente youtube|dailymotion|vimeo|facebook|instagram|tiktok|spotify|pornhub|xnxx|adult] [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] [--idioma es|en] QUERY
Ejemplo: /dl buscar mp3 ejemplo

/dl elegir [VIEW_ID] CHOICE
Ejemplo: /dl elegir ID_REAL 1

/dl anterior mp3|mp4|webm|srt [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] [--idioma es|en]
Ejemplo: /dl anterior mp3
```

## /drive

```text
/drive guardar + adjunto o cita exacta
Ejemplo: /drive guardar
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.

/drive buscar [QUERY]
Ejemplo: /drive buscar

/drive elegir [VIEW_ID] CHOICE
Ejemplo: /drive elegir ID_REAL 1

/drive cuota
Ejemplo: /drive cuota
Solo el dueño.
```

## /editar

```text
/editar mp3|mp4|webm|srt [--calidad small|standard|high] [--desde START_SECONDS] [--hasta END_SECONDS] [--idioma es|en] + adjunto o cita exacta
Ejemplo: /editar mp3
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /encuesta

```text
/encuesta crear QUESTION OPTIONS ...
Ejemplo: /encuesta crear "¿Hora?" "Opción 1" "Opción 2"

/encuesta votar POLL_ID CHOICE
Ejemplo: /encuesta votar 1 1

/encuesta resultados POLL_ID
Ejemplo: /encuesta resultados 1

/encuesta cerrar POLL_ID
Ejemplo: /encuesta cerrar 1
```

## /escuela

```text
/escuela resumen configurar ENABLED [--hora DIGEST_TIME]
Ejemplo: /escuela resumen configurar si --hora 18:00
Solo el dueño.

/escuela resumen estado
Ejemplo: /escuela resumen estado
```

## /estado

```text
/estado [ID]
Ejemplo: /estado
```

## /hh

```text
/hh iniciar [--duracion DURACION_CON_UNIDAD]
Ejemplo: /hh iniciar
Solo el dueño.
--duracion: entero con unidad s, m, h o d; ejemplo 10m. Rango: 60–86400 segundos. Por defecto: 3600 segundos.

/hh parar [EVENT_ID]
Ejemplo: /hh parar
Solo el dueño.

/hh estado [EVENT_ID]
Ejemplo: /hh estado

/hh lluvia [EVENT_ID]
Ejemplo: /hh lluvia
Solo el dueño.

/hh airdrop [EVENT_ID]
Ejemplo: /hh airdrop
Solo el dueño.

/hh reclamar DROP_ID
Ejemplo: /hh reclamar ID_REAL
```

## /horario

```text
/horario agregar --materia SUBJECT --dia WEEKDAY --inicio START_TIME --fin END_TIME
Ejemplo: /horario agregar --materia ejemplo --dia 1 --inicio 12:00 --fin 13:00
Solo el dueño.

/horario listar [--dia WEEKDAY]
Ejemplo: /horario listar

/horario borrar LESSON_ID
Ejemplo: /horario borrar 1
Solo el dueño.
```

## /ia

```text
/ia TEXT
Ejemplo: /ia ejemplo
```

## /llamada

```text
*Llamadas*

Requieren llamadas habilitadas y autorización en este chat.

*Iniciar*

/llamar

*Controlar*

/llamada estado
/llamada colgar
/llamada cancelar

*Agendar · solo el dueño*

/llamada programar
/llamada agenda
/llamada reprogramar
/llamada cancelar-agenda

Ejemplo de ayuda: /ayuda llamada programar
```

## /llamar

```text
/llamar [--video] [--duracion DURACION_CON_UNIDAD] [--tema TOPIC]
Ejemplo: /llamar
Requiere llamadas habilitadas y autorización en este chat.
--duracion: entero con unidad s, m, h o d; ejemplo 10m. Rango: 5–3600 segundos. Por defecto: 300 segundos.
```

## /mc

```text
/mc estado
Ejemplo: /mc estado

/mc jugadores
Ejemplo: /mc jugadores

/mc mundos
Ejemplo: /mc mundos

/mc mods
Ejemplo: /mc mods

/mc config
Ejemplo: /mc config

/mc diagnostico
Ejemplo: /mc diagnostico

/mc iniciar
Ejemplo: /mc iniciar
Solo el dueño.

/mc parar
Ejemplo: /mc parar
Solo el dueño.

/mc reiniciar
Ejemplo: /mc reiniciar
Solo el dueño.

/mc backup
Ejemplo: /mc backup
Solo el dueño.

/mc recuperar
Ejemplo: /mc recuperar
Solo el dueño.

/mc mod activar NAME
Ejemplo: /mc mod activar ejemplo
Solo el dueño.

/mc mod desactivar NAME
Ejemplo: /mc mod desactivar ejemplo
Solo el dueño.

/mc consola COMMAND
Ejemplo: /mc consola ejemplo
Solo el dueño.
```

## /mem

```text
/mem guardar [--tipo preferencia|dato] TEXT
Ejemplo: /mem guardar ejemplo

/mem listar [--tipo preferencia|dato] [--pagina PAGE]
Ejemplo: /mem listar

/mem corregir MEMORY_ID TEXT
Ejemplo: /mem corregir 1 ejemplo

/mem olvidar MEMORY_ID
Ejemplo: /mem olvidar 1

/mem borrar-todo
Ejemplo: /mem borrar-todo
Requiere recibir la vista previa y confirmar con su comando vigente.
```

## /nota

```text
/nota guardar TEXT
Ejemplo: /nota guardar ejemplo
```

## /notas

```text
/notas [--pagina PAGE] [QUERY]
Ejemplo: /notas
```

## /ocr

```text
/ocr + adjunto o cita exacta
Ejemplo: /ocr
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /pack

```text
/pack catalogo [--categoria CATEGORY] [--pagina PAGE]
Ejemplo: /pack catalogo

/pack comprar CATEGORY
Ejemplo: /pack comprar ejemplo
Requiere recibir la vista previa y confirmar con su comando vigente.

/pack confirmar PURCHASE_ID
Ejemplo: /pack confirmar ID_REAL
Requiere recibir la vista previa y confirmar con su comando vigente.

/pack estado PURCHASE_ID
Ejemplo: /pack estado ID_REAL
```

## /pdf

```text
/pdf iniciar + adjunto o cita exacta
Ejemplo: /pdf iniciar
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.

/pdf agregar + adjunto o cita exacta
Ejemplo: /pdf agregar
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.

/pdf terminar
Ejemplo: /pdf terminar

/pdf cancelar
Ejemplo: /pdf cancelar

/pdf extraer PAGES + adjunto o cita exacta
Ejemplo: /pdf extraer 1,3-5
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.

/pdf reintentar ID [--confirmar-incierto]
Ejemplo: /pdf reintentar ID_REAL
Requiere recibir la vista previa y confirmar con su comando vigente.
```

## /qr

```text
/qr + adjunto o cita exacta
Ejemplo: /qr
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /reaccion

```text
/reaccion saludo|risa|pensando|sonrojo
Ejemplo: /reaccion saludo
```

## /recado

```text
/recado preparar --para RECIPIENTS [--fuente actual|cita] [--adjunto] [TEXT]
Ejemplo: /recado preparar --para Amiga -- hola
Solo el dueño.

/recado estado DRAFT_ID
Ejemplo: /recado estado ID_REAL
Solo el dueño.

/recado enviar DRAFT_ID
Ejemplo: /recado enviar ID_REAL
Solo el dueño.
Requiere recibir la vista previa y confirmar con su comando vigente.

/recado cancelar DRAFT_ID
Ejemplo: /recado cancelar ID_REAL
Solo el dueño.
```

## /recordar

```text
/recordar en DURACION_CON_UNIDAD TEXT
Ejemplo: /recordar en 10m ejemplo
duration_seconds: entero con unidad s, m, h o d; ejemplo 10m. Rango: 1–3.1536e+07 segundos.

/recordar el FECHA HORA TEXT
Ejemplo: /recordar el 2026-12-01 12:00 ejemplo
```

## /recordatorio

```text
/recordatorio cancelar REMINDER_ID
Ejemplo: /recordatorio cancelar 1

/recordatorio archivar REMINDER_ID
Ejemplo: /recordatorio archivar 1
```

## /recordatorios

```text
/recordatorios [--pagina PAGE] [--cerradas]
Ejemplo: /recordatorios
```

## /ruleta

```text
/ruleta crear [BET]
Ejemplo: /ruleta crear

/ruleta entrar ROOM_ID
Ejemplo: /ruleta entrar ID_REAL
Requiere recibir la vista previa y confirmar con su comando vigente.

/ruleta jugar ROOM_ID
Ejemplo: /ruleta jugar ID_REAL
Requiere recibir la vista previa y confirmar con su comando vigente.

/ruleta estado [ROOM_ID]
Ejemplo: /ruleta estado

/ruleta cancelar ROOM_ID
Ejemplo: /ruleta cancelar ID_REAL
```

## /saldo

```text
/saldo
Ejemplo: /saldo
```

## /sticker

```text
/sticker + adjunto o cita exacta
Ejemplo: /sticker
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /tarea

```text
/tarea crear [--materia SUBJECT] --fecha DUE_DATE [--hora DUE_TIME] [--adjunto] TEXT
Ejemplo: /tarea crear --fecha 2026-12-01 ejemplo

/tarea completar TASK_ID
Ejemplo: /tarea completar 1

/tarea borrar TASK_ID
Ejemplo: /tarea borrar 1

/tarea archivo TASK_ID
Ejemplo: /tarea archivo 1
```

## /tareas

```text
/tareas [--pagina PAGE] [--cerradas]
Ejemplo: /tareas
```

## /top

```text
/top
Ejemplo: /top
```

## /transcribir

```text
/transcribir [--salida texto|resumen|ambos] + adjunto o cita exacta
Ejemplo: /transcribir
Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso.
```

## /voces

```text
/voces
Ejemplo: /voces
```

## /voz

```text
/voz [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio] TEXT
Ejemplo: /voz ejemplo

/voz crear [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio] [--duracion REQUESTED_SECONDS] TEXT
Ejemplo: /voz crear ejemplo

/voz cita [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio]
Ejemplo: /voz cita

/voz ultima [--voz botsky|mexicana|colombiana|argentina|espanola|mexicano|colombiano|argentino|espanol|chileno|venezolano|peruano|anime] [--efecto none|robot|radio|ardilla|demonio]
Ejemplo: /voz ultima
```
