# Relevo Botsky

## 06/11/2026 · R2 cerrado; siguiente R3 y R4 según dependencias

R1 commits 6c33f10/ac6c0d6 (CSV LF corregido y comprobado en índice). Relevo de
Zhana actualizado documentalmente en d3953cd; cambios anteriores intactos.

R2: aplicación y CLI local funcionales sin IA/clasificador ni proveedores. Ingreso
sintético explícito con fuente/corte/frescura, identidad de adaptador y permisos
revalidados antes de efecto. DB propia esquema v2/application_id, inbox con
fingerprint por instancia/cuenta/mensaje, canonical v1 sin reinterpretación al
recuperar. /ayuda, /estado ID, /cancelar ID, notas literales y búsqueda con filtro.
Nota/recibo/efecto/resultado/outbox en transacción local; CAS por parte de entrega,
sin transacción durante send. Incertidumbre no se reenvía. Vista de notas se
habilita solo tras aceptación completa; TTL 15min, ámbito actor/chat/cuenta/época.

25 pruebas locales pasan (11 sintaxis +14 núcleo), SQLite temporal real, carreras,
reinicio, rollback con crash, identidad, cancelación, filtros y entregas. CLI parse,
init y ayuda comprobados en entorno propio; DB de laboratorio tiene solo recibo de
ayuda sintético, cero notas. Ruff/diffcheck e integridad SQLite correctos. Evidencia
docs/evidencia/R2.json y R2-tests.txt; decisiones en docs/R2.md y ficha de portado.

La DB de laboratorio no se usará al transicionar: R11 requiere datos vacíos nuevos.
R3 siguiente: artefactos/jobs/leases/cancelación en motor, medios/documentos/PDF,
descargas/selecciones y fronteras de red probadas sin llamadas remotas. R4 puede
avanzar sin adjuntos desde R2; R3 se requiere para adjuntos. R5–R9 respetan sus
dependencias. No dar por cerrados dominios que solo tienen sintaxis.

Producción, DB31, configuración, servicios, sesiones y transporte de Zhana no
tocados. Ningún envío remoto, navegador, llamada, compra ni GitHub. Cuota última
84% primaria /52% semanal; umbral5% de cualquier ventana, guardar y detener sin
reanudación automática. Continuación autónoma vigente, solo construcción local.

## 06/11/2026 · R1 cerrado; avanza R2

R0 commit ee22c2e. R1 implementa lexer incremental, registro de 152 rutas / tres
alias sin colisiones, argumentos tipados inmutables, spans y forma canónica v1,
errores por campo con uso/ejemplo y ayuda generada. Matriz 794 filas de acciones y
campos (30 familias más audiovisual). No clasificador, IA ni efectos en el parser.

11 pruebas contractuales pasan; incluyen todos los ejemplos de registro con I/O
prohibido, literalidad, opciones duplicadas/incompatibles, fechas/horas y selección
explícita. Ruff y diffcheck correctos; ayuda/matriz reproducibles. Evidencia:
docs/evidencia/R1.json y R1-tests.txt. Decisiones y límites en docs/R1.md.
No contar parsing como aceptación de negocio: matriz mantiene NOT_TESTED.

Siguiente R2: ingreso local verificado, configuración, ámbito/época/frescura,
recibos SQLite propios, permisos, estado/cancelación exactos, notas/búsqueda con
filtro; recuperación y duplicados sin repetir escrituras. Proveedores y transporte
real deshabilitados. Continuar autónomamente conforme a dependencias del plan.
Cuota comprobada 89 % primaria / 53 % semanal; umbral de parada 5 % sin reanudación.
Instalación activa y evidencia anterior intactas. Solo pruebas y commits locales.

## 06/11/2026 · R0 cerrado; R1 siguiente

Construcción autorizada en /home/petrov/botsky por encargo expreso. Único plan:
rebuildbotsky.md. La restricción documental inicial de ese archivo queda superada
por el encargo de ejecución; R10 remoto/R11 siguen sin autorizar.

R0: Git nuevo, entorno virtual propio, configuración sin secretos, DB SQLite propia
vacía con user_version=1 (solo metadatos de esquema). Inventario 30 declaraciones,
29 modelos con campos/validadores y 48 archivos audiovisuales. Dependencias,
activos/licencias y discrepancias documentados. No runtime prestado ni NLP.

Checkpoint mecánico previo separado: Zhana ref refs/checkpoints/botsky-r0-nlp-20261106,
commit 4efd99a. Patch y archivo de evidencia privados con manifiesto SHA256.
Conservados HEAD/index/worktree y auditorías ajenas. No se ha ejecutado ni
investigado NLP, ni instalado candidata alguna.

Comprobación de cierre: docs/evidencia/R0.json. No pruebas de motor, proveedor,
WhatsApp, navegador o recepción humana. Instalación activa no tocada; DB31,
servicios, configuración, sesiones y transportes intactos. Sin GitHub.

Siguiente: R1 matriz de cada acción/campo, lexer determinista con spans, registro
sin colisiones, argumentos tipados, ayuda y errores específicos. Cero efectos
en parser. Tras cierre, R2 según dependencias. R3–R11 aún pendientes.

Cuota inicial 99 % primaria / 55 % semanal. Consultar periódicamente; al 5 % de
cualquier ventana guardar y parar sin reanudación automática.
