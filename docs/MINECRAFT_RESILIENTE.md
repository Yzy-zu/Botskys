# Minecraft: descubrimiento dinámico, reconciliación y recuperación segura

Bloque encargado el 06/11/2026. Implementación determinista; sin ejecutor de IA.

## Operación

- `/mc diagnostico`: inspecciona el contenedor configurado; obtiene imagen,
  identidad, directorio de trabajo y montaje más específico. Resuelve los datos
  dentro de la base autorizada, rechaza escapes/symlinks y lee el mundo activo.
  Los nombres de mods y dependencias siguen descubriéndose desde manifiestos.
- `/mc estado`: informa disponibilidad del juego y cambios de mods pendientes.
  Las lecturas y mutaciones normales usan el descubrimiento, no `base/data` fijo.
- Iniciar/reiniciar: una aceptación Docker inicia hasta 90 segundos de sondeos
  de solo lectura. Solo el arranque del juego verificado acredita éxito. Fallo
  conocido o plazo agotado producen incertidumbre, sin repetir el efecto.
- `/mc recuperar`: recuperación explícita, solo dueño, permisos de escritura y
  servidor apagado. Restituye los bytes/modos/existencia anteriores del último
  cambio de paquetes, incluidos subpacks y registro de desactivados. No arranca
  automáticamente ni restaura el mundo desde un backup.

## Persistencia y límites de recuperación

Antes de escribir paquetes se guarda `.botsky-recovery.json` privado0600 con
identidad de operación, fingerprint del entorno, imágenes anteriores y hashes
posteriores. Escrituras atómicas y fsync de archivo/directorio; fases pending,
applied y recovered. Un bloqueo por mundo serializa aplicación y recuperación;
se revalida la configuración al aplicar el plan. Un pending bloquea nuevos cambios
de paquetes y arranques, aun después de terminar/reiniciar el worker.

La recuperación compara **todos** los archivos antes de tocar ninguno. Acepta
solo preimagen o postimagen conocidas; rechaza ediciones externas y cambios de
imagen/identidad/montaje respecto del diario. Una interrupción de la recuperación
puede continuarse con otra orden explícita: los archivos ya recuperados coinciden
con su preimagen. No hay bucle automático ni sobrescritura de datos de terceros.

Una parada explícita permanece disponible frente a operaciones inciertas. Tras
recuperación comprobada se concilian las operaciones inciertas de mods; observar
el servidor apagado mediante recuperar concilia arranques/reinicios anteriores.
Los recibos de inbox y resultados históricos conservan su incertidumbre original.
Otros efectos inciertos no se desbloquean indiscriminadamente.

## Alcance comprobado

Pruebas locales con archivos reales sintéticos: montaje movido/anidado, límites
territoriales y symlinks, interrupción tras reemplazar un archivo, recuperación
exacta tras reinicio, conflictos externos, idempotencia, estado de juego y no
repetición de un arranque fallido. Evidencia en
`docs/evidencia/MINECRAFT-RESILIENTE-20261106/`.

Worker propio remoto actualizado; descubrimiento y estado reales de solo lectura
verificados: juego ready. No se volvió a provocar el fallo nativo anterior ni se
cambiaron paquetes reales, imagen, servicios o permisos operativos. Recuperación
remota ante un nuevo fallo nativo sigue sin acreditarse: las pruebas de fallos
son locales, no se presentan como recepción o recuperación remota real.

Esta implementación conserva contratos explícitos de Bedrock y Docker: JSON de
paquetes, manifiestos, comandos y señales del log del juego. No descubre cualquier
servidor ni migra automáticamente a cualquier futura imagen incompatible. Si una
imagen cambia esas interfaces, se detiene o informa desconocido. El fingerprint
permite detectar cambios; no es una certificación de compatibilidad de versiones.
El diario conserva el último cambio, no una historia ilimitada ni snapshots del
mundo. El fallo nativo del bloque anterior sigue abierto. R10 global/R11 pendientes.

Validación:32 pruebas focales finales PASS; suite general252 con un timeout
audiovisual IPC seedClip, repetición aislada PASS en calls-rerun.txt. El intento previo
con un error de fixture ya corregido se conserva como tests.txt. Ruff/format145
y diffcheck PASS. No se atribuye el timeout audiovisual a Minecraft sin prueba.
