# Procedimiento documental de transición y reversión

**Estado posterior06/11:** el propietario dispensó R10 como gate y Botsky ya está en producción. [Corte R11, estado y reversión](R11_PRODUCCION_20261106.md). Se conservan los resultados y límites históricos siguientes; R10 no fue reclasificado como aceptación completa.

Actualización06/11: propietario ya encargó R10/R11 y producción. Preflight,
respaldo y cesión temporal AV en [R10_PRODUCCION_20261106.md](R10_PRODUCCION_20261106.md).
El corte final no se ha ejecutado: R10 requiere todavía aceptación real pendiente.

Procedimiento original exigido por R10, conservado como referencia.
R11 exige R10 aceptado y encargo expreso (este último ya recibido). No contiene instrucciones para
activar un MVP ni para saltar capacidades pendientes.

Antes de una campaña remota se debe fijar su alcance concreto: cuenta/chat,
proveedor/modelo, destinatarios verificados, operaciones, límites y oracles humanos.
La matriz local conserva por separado sintaxis, efectos locales, dobles y pruebas
pendientes. Una pista creada, un HTTP 200 o aceptación del proveedor no demuestra
recepción en Android. Resolver bloqueos o solicitar un recorte expreso antes del
reemplazo; el encargo actual no ha dado tal recorte.

Preflight de una transición futura, una vez autorizado:

1. Conciliar inventario de 30 herramientas, audiovisual y cada acción/campo contra
   sus evidencias finales. Confirmar licencia/activos, configuración, modelos,
   versiones y recursos; verificar todas las capacidades que se habilitarán.
2. Inventariar entonces los trabajos, entregas inciertas, agendas y recordatorios
   de Zhana. Resolver su cierre o suspensión con el propietario. No importarlos ni
   dejarlos enviando en paralelo. Esa inspección de datos activos no se ha hecho.
3. Crear respaldo consistente y privado de DB31, configuración y referencias de
   cuenta/sesión/servicios de Zhana; registrar integridad, revisión y recuperación.
   No migrar sus datos a Botsky ni ejecutar el esquema propio sobre DB31.
4. Fijar propiedad exclusiva de cuenta, webhook, worker, puertos y navegador de
   llamadas. Preparar configuración propia revisable y el mecanismo soportado de
   cesión/revinculación. No clonar perfiles activos, abrir un segundo navegador ni
   exigir por suposición un número permanente adicional.
5. Crear datos productivos de Botsky desde cero, distintos de todo laboratorio:
   instancia/cuenta/época, DB propia con migraciones desde v1 y tablas de usuario
   vacías, directorios 0700, archivos sensibles 0600. No trasladar fixtures,
   historiales, XP, memorias, mensajes, archivos guardados o recibos del laboratorio.
6. Detener la admisión y ejecución de Zhana según el cierre acordado; retirar sus
   automatismos sin borrar evidencias. Ceder una sola vez la propiedad de transporte
   y llamadas. Fijar el corte de activación y la política de eventos históricos antes
   de admitir entradas de Botsky.
7. Activar únicamente la configuración aceptada, verificar salud, ausencia de
   duplicados e identidad del dueño/chat. Ejecutar los recorridos humanos acordados
   con envíos acotados y evidencia de archivos/escucha/video cuando aplique.
8. Archivar Zhana recuperable, con referencias de revisión/respaldo y restricciones
   de acceso; conservar código, cambios, auditorías y evidencia anteriores.

Reversión futura:

- Suspender nueva admisión y automatismos de Botsky; conservar su DB y journal.
  Conciliar sus envíos, llamadas, cargos y demás efectos aceptados o inciertos.
- Retirar de Botsky la propiedad exclusiva de cuenta/webhook/navegador antes de
  reactivar el producto archivado. Confirmar que no queda otro worker/temporizador
  enviando ni una llamada propia sin resolver.
- Recuperar Zhana desde su instalación/referencia y respaldo consistentes. No
  restaurar una DB antigua encima de efectos nuevos ni convertir incertidumbre en
  permiso para repetir una acción. Ajustar deliberadamente corte/época/reconexión.
- Comprobar salud e identidad y realizar solo las verificaciones acordadas. Documentar
  qué efectos quedaron conciliados o inciertos, el punto de reversión y el estado
  conservado de ambos proyectos.

El alcance y los resultados nuevos de preparación/respaldo/cesión temporal están
en el informe enlazado al principio. No se modificó el webhook activo ni se
ejecutó el corte final de producción. Los límites históricos anteriores mantienen
su fecha; no describen por sí solos el estado posterior.
