# R10 nueva aceptación y preparación de producción · 06/11

**Estado posterior06/11:** el propietario dispensó R10 como gate y Botsky ya está en producción. [Corte R11, estado y reversión](R11_PRODUCCION_20261106.md). Se conservan los resultados y límites históricos siguientes; R10 no fue reclasificado como aceptación completa.

El propietario encargó ejecutar R10/R11 y reemplazar Zhana por Botsky. El permiso
está registrado en AGENTS.md. No se reanudaron campañas históricas. El propietario
indicó después que no está disponible para comprobar Android o contestar llamadas.

**R10 parcial; R11 sin corte productivo.** El plan exige aceptar R10 antes del
reemplazo y no permite omitir capacidades silenciosamente. Faltan entrada auténtica
del dueño, recepción humana de archivos/audio/video y pruebas con objetivos de
moderación elegibles. No se retiró Zhana ni cambió el webhook activo. Los materiales
productivos están preparados; no constituyen aceptación ni un servicio instalado.

## Comprobaciones nuevas

| Frontera | Resultado y límite |
| --- | --- |
| Regresión Python | PASS: 260 pruebas, cero fallos/omisiones/intentos de red no loopback |
| Regresión Node | PASS: 286 pruebas, cero fallos/omisiones |
| Cuenta/browser propios | PASS: Brave propio, cuenta verificada, sesión ociosa, sin llamadas ni mensajes durante la prueba AV |
| Avatar con navegador real | PASS: Kazumi original con texturas reales, frames RGBA, fondo studio, happy con morphs aplicados, wave con huesos aplicados y rubor con overlay aplicado. No demuestra transmisión ni recepción Android |
| Cesión temporal del perfil | PASS: ZhanaCalls detenido y propietario Chromium ausente; respaldo offline; rename al laboratorio propio; cierre de recursos; devolución por rename. Nunca se clonó un perfil activo. No se importaron journals/agendas ni DB31 a Botsky |
| Entrega nueva WhatsApp | PASS del proveedor: nota sintética y conversión PNG→PDF de una página; tres partes aceptadas exclusivamente en Botsky Lab verificado. Entrada simulada de operador expresamente etiquetada; no ingreso auténtico desde teléfono ni recepción humana |
| Duplicados/reinicio | PASS: mismo recibo no vuelve a enviar y otra composición sobre la misma DB de laboratorio conserva los ACK sin reenvío |
| Red de despliegue | PASS: desde el contenedor real Evolution, GET /healthz atraviesa socat en 172.18.0.1:3000 al runtime loopback; Bearer correcto→200/ready, sin Bearer→401. Runtime y puente temporales detenidos. Sin cambiar webhook/firewall |
| Estado anterior restaurado | PASS: núcleo y llamadas Zhana ready, sin llamada activa, cuenta Evolution open y webhook original exacto |

Evidencia nueva saneada: [R10-PRODUCCION-20261106](evidencia/R10-PRODUCCION-20261106/summary.json).
Las regresiones completas y sus resultados originales se conservan separadamente.
El PNG del avatar, perfiles, opciones, respuestas privadas y respaldos permanecen
fuera de Git con permisos privados; no se redistribuye el modelo.

## Fallos y límites conservados

- La configuración preparada apuntaba a `/usr/bin/brave-browser`, inexistente.
  Se copió el navegador de tercero ya instalado a `private/browser/brave`, con sus
  recursos/licencias; producción apunta a esa copia independiente. Sin instalar
  paquetes del sistema ni importar runtime de Zhana.
- El primer harness de texto usó `/estado` sin su ID obligatorio: `missing_field`,
  cero POST. Es error del harness, no defecto del producto. Control nuevo con
  nota sintética y PDF PASS; no se reutilizó un envío incierto.
- Puerto candidato3012: timeout real desde Evolution por firewall existente. Se
  cambió la plantilla al3000 ya permitido, ligado solo a la dirección del bridge.
  Control nuevo PASS; no se amplió firewall ni tocó puerto3011 de Zhana.
- Al devolver el perfil, ZhanaCalls no arrancó: ENOENT del enlace VRM roto conocido
  antes de este encargo. Se detuvo su bucle de reinicios, conservó el enlace como
  `zhana.vrm.pretransition-broken-link` y repuso archivo regular0600 con SHA exacto
  del manifiesto original. Tras esta recuperación separada volvió a ready. El
  primer resultado de devolución fallida se conserva; no se reescribe como PASS.
- No se realizó llamada, captura/escucha de una persona, emisión Live, video a
  Android ni prueba de moderación sobre terceros. No se cuenta un render como
  video recibido, ni tres ACK como lectura humana.

## Evidencia previa conciliada

Backup Minecraft50GiB, recuperación durable de configuración y guardias reales:
PASS acotados según informes BACKUP-AMPLIADO y MINECRAFT_NATIVO_RECUPERACION.
Box64 corregido/aplicado con19fixtures y ciclos reales sanos: ver
[MINECRAFT_BOX64_CORREGIDO_20261106.md](MINECRAFT_BOX64_CORREGIDO_20261106.md).
El FAIL histórico de mods21:56 y la ausencia de core histórico se conservan. No
se adjudica un PASS post-parche a la función del mismo par a partir de un log que
solo acredita arranque. Drive fixture verificado/limpiado y Lab lock reversible
siguen acreditados por sus propios recibos, sin extrapolar a otras operaciones.

## Preparación y siguiente gate

Se creó `private/production/config.toml`, SQLite18 nuevo con todas las tablas de
usuario vacías, activos propios copiados y `private/integrations.production.json`
con tokens nuevos. DB de pruebas y recibos no se copiaron. Permisos de integraciones
conservan el ámbito previo; no se habilitaron mutaciones por el hecho de preparar
producción. La falta de aceptación no se resuelve dejando funciones apagadas.

Hay copia SQLite consistente de Zhana con integrity_check/FK correctos, configuración
y PM2 privados, archivo de código/Git y perfil respaldado offline. Zhana conserva
su instalación y datos; no se importan a Botsky. La copia previa no reemplaza la
instantánea final de trabajos/DB/config al efectuar el corte.

La plantilla [PM2](../ops/examples/botsky-production.ecosystem.config.cjs) está
revisada y sin instalar. Define runtime propio y puente al loopback; no contiene
secretos. Antes de activar: cerrar aceptación faltante, conciliar trabajos y
llamadas de nuevo, actualizar corte temporal, respaldar estado final, detener
admisión/schedulers antiguos, ceder perfil offline y cambiar webhook con CAS del
original. Solo entonces iniciar Botsky y comprobar salud/identidad/recepción.

Reversión: detener admisión y automatismos Botsky, conciliar efectos/ACK inciertos,
liberar navegador/puente, devolver sesión offline al propietario exclusivo y
restaurar configuración del webhook previamente guardada. Volver a arrancar Zhana
con sus datos actuales; no restaurar una DB anterior encima de efectos nuevos ni
reproducir agendas vencidas. La devolución temporal ensayada ya reveló y corrigió
el activo roto que habría impedido esta reversión.

R10 queda abierto por evidencia pendiente; el encargo de despliegue y R11 permanece
registrado. No hace falta repetir autorización. Falta observación/entrada real,
no permiso del operador. No hay reanudación automática de campañas ni llamadas.
