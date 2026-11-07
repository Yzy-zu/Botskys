# Revisión de seguridad del runner AGY · 2026-11-07

**Alcance:** lectura estática de `ops/retest_agy.py` y sus dependencias locales (`ops/stress_backend.py`, `ops/campana_lab.py`, `ops/stress_agy.py`, `src/botsky/integrations.py`, `src/botsky/operational.py`). No se inició AGY, el runner, un worker ni proveedores; no se ejecutaron pruebas. Cuota consultada: 27 % primaria / 55 % semanal (00:22 UTC).

## Comprobaciones

- **DB/perfil separados:** `isolated_prepare()` remapea las lecturas de configuración y perfil fuente a `private/production/config.toml` y `private/integrations.production.json`. `stress_backend.execute_tool()` crea/usa `base/app` y fuerza la DB local `root/lab.sqlite3`; no se observó uso de la DB activa. Las lecturas de referencias de producción son explícitas, conforme al permiso operativo ya registrado.
- **Drive y Minecraft:** el perfil de `base/app` pone `drive.write`, `groups.write` y `minecraft.write` en `false`. `src/botsky/integrations.py` aplica además `PermissionGate` a uploads y cambios Minecraft/grupos. No se observó que el runner escriba sobre esos ámbitos.
- **Llamadas:** `campana_lab.prepare()` fija `call_service.enabled=false`; `Integrations.calls_client()` devuelve `None` en ese caso.
- **Evolution:** `CaptureOnlyToolHTTP.live` devuelve siempre `false` y su setter ignora valores, incluso el `live=True` del backend y el envío de resumen. La ruta `RoutingHTTP` responde con recibo de fixture cuando `live` es falso; no permite los POST Evolution al transporte externo. El bucle de publicación también fuerza `publish=false` en los casos congelados.
- **Procesos:** la versión revisada crea el worker en sesión propia y lo termina con `killpg`/`wait`, también desde `finally`. Hay límite de inactividad/900 s. `agy_lab.sandbox()` usa bubblewrap con `--die-with-parent`/PID namespace; `Session.close()` espera y mata el proceso de sandbox si no sale. El fallo inicial de timeout sin limpieza quedó corregido antes de este cierre.
- **Cuota:** se comprueba por herramienta antes de iniciar su sesión y entre tandas; errores de consulta y umbral ≤5 % escriben STOP. No se verificó comportamiento bajo agotamiento real.

## Hallazgos antes de campaña

La habilitación interna de `messages.send`, `delivery.send` y `evolution.delivery_enabled` viene de la plantilla del laboratorio y permite probar sus handlers. La salida Evolution sigue retenida por `CaptureOnlyToolHTTP.live == False`; la capa `LabHTTP` añade el registro antes de invocar `RoutingHTTP`, por lo que `owner.posts[-1]` existe para el POST de mensaje o resumen. Con esos contratos actuales, no considero la habilitación de perfil ni el acceso al último ledger como bloqueadores.

La cuota se consulta antes de cada herramienta y tanda; el código de esta revisión no vuelve a consultarla antes del turno de reporte. El controlador principal confirmó que hará comprobaciones periódicas y parará la actividad al 5 %, así que no dejo un bloqueo para este punto.

## Resultado

**GO para la revisión de seguridad estática**, sujeto a la supervisión de cuota indicada. La versión revisada conserva la DB y perfil del backend en su base propia; los únicos insumos productivos son las referencias de integración autorizadas. Drive/grupos/Minecraft quedan read-only, llamadas deshabilitadas, Evolution `live` forzado a falso incluso en los POST internos y resúmenes, y los subprocesos tienen timeout con reap del grupo. No se detectó bloqueo de seguridad restante. No ejecuté pruebas ni campaña y no modifiqué código.
