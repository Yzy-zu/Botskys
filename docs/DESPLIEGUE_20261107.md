# Despliegue de correcciones · 07/11/2026

Encargo expreso del propietario: reiniciar y desplegar. **Código67500bf cargado en
producción** mediante parada limpia y arranque del supervisor existente. Incluye
la retirada de SoundCloud, DROP_ID de hora feliz, ayuda de duraciones, lectura QR
local en/ia y términos obligatorios enviados al buscador.

Preflight: núcleo/calls listos, sin llamadas, medios ociosos liberados, agendas sin
reservas, cero jobs y solo una entrega anterior aceptada. Se detuvo únicamente
`botsky-production-runtime`, sin cambiar el puente, webhook o supervisores ajenos.
Backup SQLite consistente estando parado, integridad/FK correctas, cero jobs activos
o entregas inciertas. Configuración propia y fuente anterior1e4dbe9 archivadas
privadas para reversión. No se copió el perfil de navegador ni se restauraron datos.

PID anterior3256051; nuevo3303101. Runtime/calls ready, ninguna llamada activa o
externa, cero trabajos/entregas pendientes, sin advertencias al comprobar el estado
final y medios ociosos liberados. Recuento de recursos propios: un bus, una pantalla,
un audio y un navegador. Ningún otro supervisor cambió PID. Contador de reinicios
automáticos del runtime sigue0: esta fue parada/arranque deliberada.

La primera comprobación agregada tras arrancar terminó en AssertionError; no se
conservó una respuesta que permita atribuirlo a un campo concreto. La comprobación
posterior completa pasó, sin repetir el arranque. No se anuncia éxito de aquella
primera muestra ni se atribuye una causa no observada.

Contenedor Evolution real accede al puente con health200/ready y token vigente.
GET del webhook confirma destino/autenticación propios sin mutarlo. PM2 guardado;
dump y respaldo mantienen Botsky y excluyen los supervisores archivados de Zhana.
47pruebas de QR/búsqueda y37de correcciones previas conservan sus evidencias: no se
repitieron sin cambio posterior del producto. Sin mensajes, llamadas, pruebas de
herramientas con efectos o afirmaciones de recepción humana durante el despliegue.

Respaldos/recibos privados en `private/deploy-20261107-0107/`, permisos0700/0600.
Evidencia saneada: [summary.json](evidencia/DESPLIEGUE-20261107/summary.json).
La fuente cargada67500bf y los hashes de módulos están registrados. El cierre
documental posterior no requiere otro reinicio.

Reversión: parar el runtime bajo estado observado, conservar DB/journal actuales
y efectos nuevos, desplegar fuente previa desde el archivo/Git y validar antes de
arrancar con la misma configuración. No restaurar automáticamente el backupSQLite
sobre datos nuevos ni reintentar efectos inciertos. Zhana permanece archivada.
