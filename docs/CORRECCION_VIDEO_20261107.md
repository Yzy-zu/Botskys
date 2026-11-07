# Búsqueda de video, miniaturas y descarga · 07/11/2026

Se investigó el fallo reciente y se corrigieron los problemas demostrados, conservando
históricos y sin enviar respuestas de prueba por WhatsApp.

## Conversación

El frontend usaMP4por defecto para buscar video. El campo container es opcional
solo en el catálogo natural de dl.buscar;la construcción nativa añadeMP4si falta.
Una petición explícita de audio conservaMP3;WebM/SRT explícitos se respetan. CLI
no cambia. La fuente sigue validándose contra las habilitadas y los permisos
permanecen en el backend. No se introdujo un clasificador ni selección previa.

Las instrucciones indican usarYouTubepara búsqueda general de video yfuente adulta
habilitada ante petición explícita,sin pedir fuente otra vez. Una palabra ambigua
sin indicación explícita conserva aclaración. Cuatro casos sintéticos nuevos con
Qwen/cf06pasaron:video general,adulto explícito,audio explícito yambigüedad.

Una comprobación adicional con la frase original reprodujo otra aclaración
innecesaria. Se conservó ese fallo y se añadió instrucción/ejemplo explícito para
el término coloquial usado. La nueva comprobación propuso dl.buscar,sourceadult,
containermp4yconsulta correspondiente en7,89segundos,sin aclarar. Total5casos únicos
correctos en6intentos. No equivale a garantía universal del LLM. El caso de audio
demoró34,708s:esta corrección no promete resolver toda la latencia. Ninguna propuesta
se ejecutó. Manifiestos y resultados separados en frontend/,regression/ yregression-fixed/.

## Miniaturas: causa demostrada y corregida

Dos de seis miniaturas devolvían403,y no había denegaciones de la allowlist del
proxy. GETcon Referer público de origen yUser-AgentMozilla/5.0devolvió200 para las
mismas dosURLs. fetch_thumbnail incorpora esas cabeceras estáticas únicamente para
esas fuentes. Comprobación con código corregido:ambas descargan ydecodifican,
6.533y8.833bytes. No se publicaron ni visualizaron imágenes durante el diagnóstico.

Sin cookies,autorización,perfiles o sesiones;Referer no contiene consulta/ID de video.
Se mantienen HTTPS,allowlist,DNS público fijado,sin redirects,límite2MiB,timeout,
decodificación acotada yconcurrencia2. Pruebas nuevas de cabeceras yfronteras existentes.

## Descarga: alcance de lo que se pudo demostrar

El intento histórico fallósource_failedtras44,127segundos;no se conservó stderr.
No es posible adjudicar retrospectivamente una causa exacta a partir de ese código.
El sondeo nuevo obtuvo metadatos/formats ystreams permitidos. Dos muestras acotadas
respondieron206. La prueba nueva del extractor con --test,formato seleccionado HLS,
outputpropio ylímites de proceso produjo117.277bytes parciales yse limpió al terminar.
No hubo descarga completa,conversión final ni entrega. Esto demuestra acceso ylectura
parcial actuales,no éxito histórico ni preparación completa actual.

Se incorporó clasificación de fallos del extractor para estas fuentes,que antes
convertían process_faileden source_failedsin más detalle:acceso403,recurso404,
formato inexistente,cliente no disponible yconexión. Persisten códigos saneados,
nuncaURLs,títulos,cookies ostderr enrespuestas. El fallo desconocido sigue genérico
sin afirmar falsamente bloqueo de origen. Nuevos mensajes de error indican el
problema yevitan remitir exclusivamente a comandos de ayuda. No se cambió el
selector,allowlist ni motor por una hipótesis no demostrada.

## Validación y corte

56pruebas locales pasan:default/diagnóstico3,miniaturas4,frontend34,roundtrip1,
presentación6ydescargas8. Qwen:5casos únicos correctos conel fallo intermedio preservado.
La inferencia adicional se usó solo para propuestas. Sondeos de proveedor nuevos
acotados,sin repetir la campaña cerrada. Sin comandos desde contenido extraído.

Dos cortes reversibles:primeroMP4/miniaturas/errores,ysegundo instrucción de la
regresión real. Fuentesa9b6980y5c02559,respectivamente. Backups privados propios
con DB consistente,perfil,configuración,pool7yfuentes anteriores,integridad/FK,
sin migraciones. El segundo corte conserva toda la primera corrección;la reversión
restaura los módulos modificados,sin restaurar DB ni perder datos nuevos.

Estado final de salud/PID ycuentas en deployment.json;first-deployment.json conserva
el primer recibo. El perfil,Qwenlow,compacto íntegro,cuotas yservicios ajenos se
preservan. Sin envíos ni inferencias durante los cortes. No afirmar recepción
humana oprueba de descarga completa.

Evidencia saneada:docs/evidencia/CORRECCION_VIDEO_20261107. Los sondeos conservan
solo formatos/códigos/tamaños;datos diagnósticos sensibles propios fueraGit0600.
Referencia de flags de extracción: https://github.com/yt-dlp/yt-dlp .
