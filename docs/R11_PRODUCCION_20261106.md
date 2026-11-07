# Botsky en producción · R11 · 06/11/2026

**Desplegado.** El propietario dispensó expresamente la aceptación previa de R10
y reiteró el reemplazo de Zhana. Se conserva R10 parcial, sin convertir pruebas
pendientes en PASS. Corte/época de Botsky: **2026-11-06T23:55:17.120641Z**, época1.
Código funcional desplegado:1e4dbe9; este cierre añade documentación/evidencia,
sin modificar el código del runtime.

## Estado observado

- Runtime Python propio y servicio audiovisual managed: ready. Cuenta verificada,
  perfil exclusivo de Botsky y medios ociosos liberados; sin llamada activa.
- Puente PM2/socat:172.18.0.1:3000→127.0.0.1:18787. Desde contenedor Evolution
  real, health autenticado200/ready. Sin ampliar firewall.
- Webhook Evolution apunta a `/webhook/evolution` de Botsky, con Bearer propio;
  configuración final releída del proveedor y comparada con la intención durable.
- Supervisores `botsky-production-runtime` y `botsky-production-webhook-bridge`
  online, cero reinicios durante la comprobación. PM2 y su respaldo `.bak` guardan
  ambos procesos y excluyen los procesos archivados de Zhana.
- ZhanaCore/ZhanaCalls/observador retirados de PM2. Ningún supervisor ajeno fue
  reiniciado ni cambió de PID. La instalación y DB31 de Zhana siguen conservadas.
- Aviso de activación único al Botsky Lab verificado: proveedor aceptó su ID.
  No se afirma lectura humana. Sin llamadas ni campañas de pruebas reanudadas.

Evidencia saneada: [summary.json](evidencia/R11-PRODUCCION-20261106/summary.json).
Los secretos, respaldos, sesión y respuestas privadas están en
`private/r11-cutover-20261106/`, permisos0700/0600, ignorados por Git.

## Datos, permisos y funciones

Configuración propia: `private/production/config.toml` y
`private/integrations.production.json`; DB SQLite18 propia en
`private/production/botsky.sqlite3`. Antes de admitir entradas, todas las tablas de
usuario estaban vacías. No se importaron fixtures, recibos, notas, XP, memoria,
historial, DB31 ni agendas de laboratorio o Zhana. Galería y avatar son las copias
propias ya autorizadas; la galería conserva sus tres álbumes sin fotos.

Se habilitaron las capacidades operativas para los ámbitos explícitos existentes:
privado del dueño y Botsky Lab; recados a los destinos ya configurados. Drive,
Minecraft, grupos, galería, ruleta y nuclear conservan validadores de dueño,
objetivos/roles, consentimiento, vista previa y confirmación. Activar un permiso
no ejecuta la operación ni amplía automáticamente grupos/contactos.

Scheduler, avisos de llamadas y agenda están activos sobre datos nuevos. Llamadas
salientes/Live y grupo Lab están configurados; autoatención entrante permanece
apagada según contrato v1. Gemini solo produce contenido; parser determinista y
sin NLP. OAuth y worker Minecraft son propios; no se importa runtime de Zhana.

## Respaldo y cesión

Preflight y comprobación final tras detener Zhana: inbox/jobs/entregas terminales,
recordatorios terminados/cancelados, sin llamadas ni agendas pendientes. Backup
SQLite consistente con integrity_check y foreign_key_check correctos. Configuración,
credenciales/referencias de sesión y definiciones PM2 privadas conservadas.

`private/r11-cutover-20261106/legacy-final.sqlite3` y
`legacy-profile-final.tar.gz` son las copias finales. Perfil respaldado estando
apagado, TAR leído y CRC gzip completo comprobado; SHA en archivo privado.
Archivo de código+Git completo previo y su manifiesto permanecen en
`private/production-transition-20261106/`. Zhana conserva además su directorio
original y auditorías; archivar no significa borrar el repositorio.

Se detuvo primero el núcleo antiguo y después llamadas, se observó libre el
propietario Chromium y se cedió el perfil con rename al directorio propio
`private/production/private/calls/profile-brave`. No se clonó un perfil activo.
Botsky arrancó sano antes de despachar el cambio de webhook. Se releyó el webhook
original justo antes del único POST y se concilió por GET después; el proveedor
no ofrece CAS atómico, por lo que no se promete esa garantía. No hubo retry de un
cambio incierto. Finalmente se retiraron los procesos antiguos y guardó PM2.

## Reversión operativa

No ejecutar por leer este documento: es una acción deliberada de operador.

1. Guardar definiciones PM2 actuales; detener admisión/runtime y puente Botsky con
   `pm2 stop botsky-production-runtime botsky-production-webhook-bridge`.
   Conservar DB/journal actuales con backup SQLite, revisar trabajos/outbox,
   llamadas y agendas pendientes o inciertos. No reenviar ni resolverlos por
   suposición; no restaurar una base antigua encima de efectos nuevos.
2. Observar que no queda proceso dueño del perfil ni medios propios activos.
   Renombrar el perfil desde la ruta propia de Botsky a
   `/home/petrov/zhana/private/calls/profile-brave`, únicamente si el destino está
   ausente. No copiarlo abierto ni restaurar el perfil viejo sobre uno vivo.
3. Conservar config actual de Zhana y actualizar deliberadamente su
   `activation_cutoff_ms` al instante de reversión, para no ejecutar mensajes del
   periodo Botsky. Usar la DB31 conservada en sitio, no el backup previo salvo
   una restauración separada justificada. No reproducir agendas vencidas.
4. Releer webhook y exigir que siga siendo el de Botsky guardado en
   `webhook-observed.json`; si cambió externamente, detener la reversión y revisar.
   Reconstruir el cuerpo `webhook` desde `webhook-before.json`: enabled/url/headers,
   byEvents←webhookByEvents, base64←webhookBase64 y events. Usar API key propia por
   referencia privada; POST único `/webhook/set/<instancia>`, seguido de GET
   `/webhook/find/<instancia>`. Ante timeout, conciliar por GET, nunca repetir
   automáticamente. No imprimir tokens o JSON privados.
5. Retirar las entradas Botsky detenidas de PM2 y arrancar las definiciones
   conservadas `/home/petrov/zhana/ops/ecosystem.config.cjs`. Comprobar salud,
   cuenta, exclusión y ámbito antes de admitir trabajo. Guardar PM2 dos veces y
   verificar que dump y .bak solo contienen al propietario operativo de la cuenta.
6. Registrar efectos nuevos conciliados o pendientes, corte, estado de ambos
   productos y recibos de transporte; conservar todos los datos de Botsky.

El avatar roto preexistente de Zhana se recuperó en la prueba anterior con su hash
original; enlace roto preservado. Esa reparación permite recuperar el runtime
archivado sin depender de la ruta desaparecida.

## Límites conservados

La dispensa del dueño permite el corte sin cerrar R10. Entrada real desde teléfono,
recepción/escucha/video Android y efectos sobre participantes elegibles siguen sin
validación humana nueva. No se afirmó que todas las herramientas hayan pasado
aceptación remota. La estabilidad futura y compatibilidad con cualquier imagen/mod
no quedan garantizadas por el despliegue. Ninguna llamada automática de prueba,
migración de datos de usuario, instalación NLP o publicación GitHub fue realizada.
