# Unión operativa · puntos 1, 2 y 3

**Estado posterior06/11:** el propietario dispensó R10 como gate y Botsky ya está en producción. [Corte R11, estado y reversión](R11_PRODUCCION_20261106.md). Se conservan los resultados y límites históricos siguientes; R10 no fue reclasificado como aceptación completa.

Encargo posterior del propietario: programar transporte WhatsApp, proceso continuo
y composición de llamadas. Continúa rebuildbotsky.md, R2/R9/R10 local. Se conserva
la instalación activa; este cierre no es activación ni transición.

## Qué se añadió

- `adapters/evolution_normalize.py`: contratos propios para mensajes privados/grupos,
  identidad de teléfono/LID coherente, timestamp obligatorio, wrappers, adjuntos,
  citas y menciones. Se ignoran mensajes propios, reacciones y eventos ajenos a
  `messages.upsert`. El contenido citado no se interpreta como comando nuevo.
- `adapters/evolution.py`: recibo del webhook en SQLite18 antes del HTTP202. Cola
  acotada, duplicado estable/conflicto, recuperación, corte/frescura y permisos
  antes de descargar. Las descargas usan únicamente la API autenticada de medios
  y el registro técnico del evento; ningún fetch de enlaces del texto. Base64
  incremental, tamaños máximos, firma y referencias propias con ámbito/época.
- Entrega asíncrona con CAS y leases existentes. Cada parte corresponde a un POST:
  texto, documento/imagen/video/audio, sticker nativo o nota de voz OGG/Opus según
  el resultado del motor. ACK del proveedor distinto de recepción humana. Una
  respuesta perdida, cancelación durante envío o reinicio queda incierta; no se
  reenvía. Una parte incierta tampoco bloquea respuestas de otros encargos.
- `runtime.py`: HTTP solo127.0.0.1, Bearer propio, sin CORS, body1MiB, cabeceras16KiB,
  timeout10s y máximo32conexiones. Bucles independientes de texto y descarga de medios (un medio lento no retiene
  comandos de otros chats), worker con
  concurrencia ya acotada, entrega, scheduler/avisos optativos y limpieza. Un fallo
  de bucle detiene el proceso de forma visible. SIGTERM/SIGINT detienen admisión,
  esperan trabajo acotado y conservan recibos al cancelar. Exclusión propia antes
  de recuperar envíos; conexiones HTTP incompletas se cierran antes de esperar al
  servidor. No es todavía la cesión exclusiva de la cuenta activa de Zhana.
- `Integrations` inyecta `CallsClient` real, revisa política/health y admite servicio
  externo propio o subproceso administrado. `call_service.py` pasa configuración
  y secretos por pipe, verifica ready/revisión/loopback, supervisa salida y cierra
  solo su hijo. `calls/main.cjs` compone los componentes ya portados de Zhana:
  runtime privado, BrowserDriver con cuenta verificada, Live de clave única,
  journal/agenda/audio/clips/avatar. `bootstrap.cjs` inicia runtime dentro del lock
  del servicio y antes del driver. Cualquier fallo libera recursos y lock.

El parser sigue siendo explícito y determinista. Live conserva exclusivamente los
controles cerrados de la llamada autorizada; no hay NLP ni ejecutor general por IA.
No se importan sesiones/perfiles antiguos. El navegador requiere permiso explícito
en configuración; no se abrió ninguno al desarrollar o comprobar este cierre.

## Configuración y entrada

La configuración propia ignorada `private/integrations.json` conserva proveedores
ya validados y ahora prepara tokens independientes de webhook/servicio AV0600.
`private/config.integrations.toml` conserva transporte local y corte previo; añade
política de llamadas propia restringida al dueño, sin grupos y features apagadas.
Se guardaron copias previas mecánicas en `private/integration-checks/`.
Las rutas de almacenamiento se resuelven respecto al directorio del TOML: en esta
configuración SQLite queda en `private/botsky-integrations.sqlite3` y los recursos
relativos en `private/private/` (incluido `calls/`). Se conserva esa ubicación
previa para evitar una migración silenciosa de datos propios.

Estado comprobable sin arrancar servicios:

```sh
.venv/bin/python -m botsky.connected --config private/config.integrations.toml --providers private/integrations.json status
```

Entrada implementada para una futura activación expresamente encargada:

```sh
.venv/bin/python -m botsky.connected --config private/config.integrations.toml --providers private/integrations.json serve
```

`serve` exige `transport="evolution"` y tabla JSON `runtime` con `webhook_token`
hex64, `port`, `scheduler_enabled`, `notices_enabled`, `poll_seconds` y
`shutdown_seconds`. No cambia el webhook del proveedor ni instala proxy/servicio.
La futura configuración Evolution apuntará a `/webhook/evolution` con cabecera
`Authorization: Bearer <token propio>` mediante proxy local explícito. La instancia
Evolution se fija en `evolution.instance`; Botsky usa su propia identidad de
instancia y la cuenta configurada. `sender`, si llega, debe coincidir con la cuenta.

`evolution.delivery_enabled` es independiente de permisos de mutación de las
herramientas. Está **false**. El scheduler y avisos están **false**. `call_service`
está **enabled=false**, `mode="managed"`, token propio, puerto18788 y ruta explícita
de navegador; `allow_browser_launch=false` y `agenda_timers=false`. Los secretos
Live/modelo permanecen en la tabla `live` propia. Nada se hereda del entorno global.

Para modo externo se exigen `enabled=true`, `mode="external"`, `base_url` loopback
y `token` del servicio propio. Para modo managed se exigen `enabled=true`, política
`calls` válida, Live key/modelo únicos, `executable` absoluto y autorización de
navegador explícita. La consulta `status` nunca inicia el subproceso managed.

`ops/examples/botsky.service` es una plantilla de supervisión **sin instalar ni
activar**. La transición deberá resolver propiedad de cuenta, corte/época, proxy,
referencias de sesión propia y automatismos antes de habilitar estos parámetros.

## Comprobación y límites

Evidencias nuevas `docs/evidencia/RUNTIME-*`; no se reescriben R9/R10 anteriores.
Regresión completa188Python PASS con cero intentos de red fuera de loopback.
Cierre focal14runtime +3composición +1CLI PASS, con tres métodos nuevos respecto
a aquella regresión:191métodos Python distintos comprobados. Node completo282PASS
y cierre focal4PASS con un método adicional:283distintos. Ruff/format/pipcheck y
diffcheck correctos; SQLite18 propia integrityok. No son pruebas remotas.
Proveedor HTTP simulado para mensajes/medios; servidor webhook real en loopback.
Se obtiene un PDF real a partir de imagen, se entregan bytes y se abre en receptor;
sticker real WEBP se entrega por su endpoint. Duplicados, citas fuera de ámbito,
LID ambiguo, históricos, ACK perdido, reinicio y apagado quedan comprobados.
Servicio Node real con runtime/driver sintéticos verifica orden de arranque,
cuenta/política, denegación de vinculación y liberación; hijo Python IPC real
verifica ready, revisión y terminación sin navegador ni llamada. CLI Python real
verifica SIGTERM y reinicio conservando una única nota; se cancela también el
arranque AV en curso al detener y no se abre admisión HTTP antes de estar listo. Las regresiones
anteriores mantienen sus niveles de evidencia y límites audiovisuales.

Desarrollo conservado: primer oracle usaba `completed` donde Jobs publica
`succeeded`; se corrigió el oracle. Una imagen simulada con bytes TXT descubrió
la falta de comparación de tipo/firma y se corrigió código. Fixture de composición
olvidaba bot_ids y se corrigió. Prueba de socket incompleto detectó orden de cierre
incompatible con espera de conexiones en Python3.14; corregido cerrando clientes
antes de `server.wait_closed`. La primera regresión concurrente con toda la suite
Node agotó5s al generar clip sintético; se conserva fallo y se repite Python sin
esa carga paralela, sin ampliar el timeout del contrato.

R10 remoto y R11 siguen abiertos. Falta activar por encargo el canal real y verificar
recepción WhatsApp/Android; no se afirma entrega humana, escucha o video por pasar
pruebas locales. Galería/VRM/licencias y demás pendientes de producto ajenos a estos
tres puntos mantienen su estado anterior. No se han enviado mensajes, llamado,
tocado grupos/servidor, abierto navegador, publicado GitHub o alterado Zhana activa.
