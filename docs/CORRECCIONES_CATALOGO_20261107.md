# Correcciones encargadas · 07/11/2026

El propietario pidió eliminar SoundCloud y corregir `/hh reclamar` y la ayuda de
llamadas tras el contraste de los35claims. Se conservan evidencia y adjudicaciones
históricas; estos cambios son posteriores a ellas.

SoundCloud se eliminó de las fuentes, validación de URLs directas/cortas,
extractor, proxy/hosts y ramas de descarga. El catálogo ya no lo ofrece y los
enlaces dejan de admitirse. Las pruebas conservan referencias negativas y los
informes históricos conservan lo que observaron.

`/hh reclamar DROP_ID` usa `drop_id` tanto en el parser como en el handler. El
anuncio ya emitía el comando correcto con ese ID; los demás comandos `/hh` siguen
usando `event_id`. La comprobación completa crea y publica un AirDrop sintético,
rechaza el ID del evento y premia con500XP al reclamar su ID correcto. No requiere
migración SQLite: cambia el argumento tipado de esta acción síncrona, no tablas.
La matriz mantiene `original=event_id` como referencia al inventario histórico.

La ayuda distingue `DURACION_CON_UNIDAD`, explica unidades y muestra un ejemplo.
Para llamadas indica rango5–3600segundos y valor por defecto300segundos. Ejemplos
válidos: `--duracion 600s` y `--duracion 10m`; la sintaxis del parser se conserva.
La presentación de todos los campos `duration` usa esa misma información del
registro, evitando firmas que sugieran números sin unidad.

Documentación generada actualizada desde el catálogo:154rutas. Incluye las rutas
Minecraft de diagnóstico y recuperación que ya existían en código pero faltaban
en el documento anterior. No se cambiaron esas operaciones.

Validación:37pruebas locales pasan (comandos13, packs16, descargas8), sin conexiones
externas; el test de proxy usa loopback. Ruff/formato correctos, ayuda y154entradas
JSON conciliadas con el registro. Evidencia en
[CORRECCIONES-CATALOGO-20261107](evidencia/CORRECCIONES-CATALOGO-20261107/observations.json).
No se reiniciaron servicios productivos ni se ejecutaron llamadas o descargas
remotas. Los cambios están en el repositorio; los procesos ya cargados requieren
un reinicio para adoptar el código nuevo.
