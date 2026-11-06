# Punto4 · comprobaciones reales acotadas

El propietario encargó punto4 y autorizó ejecutar las acciones necesarias sin
otra confirmación. Se usó una DB propia nueva, entrada simulada del propietario,
credenciales propias y permisos de escritura efímeros solo para esta ejecución.
No se reabrieron campañas anteriores ni se activó el perfil operativo.

**Aceptación parcial: Drive y ajuste del Lab comprobados; Minecraft recuperado
y sano, respaldo no aceptado.** No se da por cerrado el punto4 completo.

| Recorrido real | Resultado y oracle |
| --- | --- |
| Drive cuota | Cuenta de5TiB confirmada desde `/drive cuota`. |
| Guardar/buscar/elegir | Fixture propio TXT de73bytes; subida real, búsqueda por nombre y ámbito, selección tras ACK local de vista, recuperación con SHA256 idéntico. El reingreso del mismo mensaje conserva su recibo sin reservar otra subida. |
| Limpieza Drive | Solo el ID generado y registrado por esta ejecución, verificado por appProperties del ámbito, se mandó a papelera. No se borraron archivos de usuario. |
| Botsky Lab | Grupo verificado por metadata, bot administrador, dos participantes. `/admin cerrar` cambió el ajuste `locked`; `/admin abrir` lo restauró. Metadata posterior confirma miembros/roles y anuncio sin cambios. |
| Minecraft consultas | Estado, jugadores, mundos, mods y configuración pasaron por parser/recibo/job/SSH reales. Nombres de mundo, jugadores y configuración quedan solo en evidencia privada0600. |
| Consola | `list` fue aceptado por el puente; ese ACK no prueba por sí solo ejecución dentro del juego. Las consultas de jugadores verificaron respuesta real antes y después del ciclo. |
| Parada | Cero jugadores comprobados inmediatamente antes. `/mc parar` aceptado y contenedor observado apagado. |
| Respaldo | `/mc backup` devolvió `worker_timeout`, recibo `minecraft_uncertain`. Se conservó y no se repitió. Inspección posterior no encontró archivo de esta prueba. |
| Recuperación | El arranque desde la aplicación fue bloqueado por la incertidumbre conservada. Una acción distinta de recuperación `start`, ejecutada por el operador mediante el adaptador real, restauró el servidor. Estado final running/healthy, mundo inicial conservado, jugadores verificados:0. |

Se ejecutaron15comandos de aplicación:13resultados previstos, un respaldo incierto
y un arranque bloqueado por ese recibo. La recuperación directa se registra
aparte, sin atribuir éxito al arranque bloqueado. Las vistas/outbox son locales:
no se envió ningún mensaje a WhatsApp ni se certifica recepción humana.

El worker remoto tiene límites de1.073.741.824bytes de origen y25segundos para
backup/worker. Los datos observados suman1.591.454.143bytes. El plazo se agotó
antes de conseguir el respaldo; el volumen supera además su máximo admitido.
No se elevaron límites ni se sustituyó el worker activo de Zhana para forzar PASS.
Su hash difiere del fichero local de referencia; las consultas, acciones y límites
desplegados se comprobaron explícitamente, sin importar su runtime.

La conciliación observa ausencia de archivo y servidor restaurado; el recibo
histórico de incertidumbre no se reescribe. Es un bloqueo real de aceptación del
respaldo con este servidor/presupuesto, no prueba de corrupción del mundo.
Los primeros checks de jugadores tras iniciar todavía no daban lista verificada;
una consulta posterior, tras comprobar health, confirmó cero jugadores. Ambos
momentos se conservan por separado.

Pendientes para aceptar todas las capacidades del punto4: respaldo compatible
con el volumen real y sus tiempos; mutaciones de participantes con un objetivo
de prueba elegible (el Lab actual solo contiene dueño/bot protegidos); activación/
desactivación de mods y el comando específico de reinicio. Los contratos con
dobles no se convierten aquí en aceptación de esos efectos reales.

Al cierre: cero jobs activos,16partes de outbox pendientes canceladas, SQLite
integrity_check=ok y marcador privado CLOSED/no_auto_resume. Los permisos write
del perfil operativo siguen false para Drive/grupos/Minecraft; solo se habilitaron
en memoria para el laboratorio. Se conservaron datos/auditorías anteriores. Sin
llamadas, navegador, webhook, transición, GitHub, NLP, DB31 o sesiones/perfiles.

Validación local focal:50tests PASS, cero fallos/errores/omisiones e intentos fuera
de loopback. Ruff check/format138archivos, pip check y diffcheck correctos. No se
modificó `src/` ni `calls/`; no se repitió la regresión completa sin cambio de
producto. El script de operador limita la recuperación directa de arranque al
caso de denegación previa al despacho, nunca a reintentar un arranque incierto.

Evidencia saneada: [summary.json](evidencia/INTEGRACIONES-P4-20261106/summary.json),
[recibos](evidencia/INTEGRACIONES-P4-20261106/20261106T212353Z/results.json),
[conciliación](evidencia/INTEGRACIONES-P4-20261106/reconciliation.json) y
[salud final](evidencia/INTEGRACIONES-P4-20261106/server-health.json).
Evidencia completa privada0700/0600 en `private/integraciones-p4-20261106T212353Z/`.
`ops/integraciones_p4.py` es una herramienta de operador con efectos reales y
**no debe ejecutarse automáticamente ni para repetir esta ejecución cerrada**.
R10global permanece abierto; punto3 audiovisual y transición siguen pendientes.
