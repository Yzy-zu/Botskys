# Minecraft: fallo nativo y recuperación remota

Encargo nuevo: investigar el fallo del reinicio y probar recuperación segura en
el Minecraft configurado. No reabre campañas cerradas. La recuperación remota
queda acreditada; la causa exacta del fallo nativo histórico sigue abierta.

## Diagnóstico y correcciones confirmadas

El extracto histórico con timestamps, en `checks/native-review.json`, distingue
apagado y nuevo arranque: `Quit correctly` a21:56:51; nuevo proceso Bedrock
1.26.63.1 a21:57:00 y `free(): invalid next size (normal)` después de habilitar
el log de contenido. El host es ARM64 y usa Box64. Esto identifica una detección
de corrupción de memoria en el proceso del juego, pero no quién la ocasionó.
No demuestra que el ciclo de dependencias, un addon o Box64 sea su causa.

Se corrigieron cinco defectos de Botsky:

1. `docker logs` descartaba stderr. Se capturan ambos canales solo para logs;
   inspect JSON y demás comandos conservan su separación. **Corrección de la
   hipótesis inicial:** la captura separada muestra el error histórico en stdout;
   no se atribuye ese caso a la pérdida de stderr. La regresión con proceso real
   sí demuestra la pérdida y posterior detección de un fatal emitido en stderr.
2. El límite interno128KiB impedía observar un arranque sano con muchos avisos
   de addons. Reproducción real aislada:362492bytes, marcador `Server started.`,
   sin firma fatal, resultado original `game_startup_unverified`. Los tres lectores
   de log permiten ahora8MiB, con plazo y límite de memoria. Salida JSON remota,
   consola y resto de procesos conservan128KiB. Un log mayor sigue siendo desconocido.
3. El timeout de recuperar omitía la clasificación incierta de una mutación.
   Ahora informa incertidumbre y no repite la petición.
4. La admisión y el índice único bloqueaban parar/recuperar después de un efecto
   incierto. Los controles explícitos pueden conciliarlo, conservando exclusión
   contra operaciones reservadas/en envío. Las filas antiguas pasan a `reconciling`,
   que sigue bloqueando operaciones normales. Cancelar/fallar un control conserva
   ese bloqueo. Recuperación observada offline concilia start/restart/stop/recover;
   rollback comprobado concilia mods. No desbloquea backups u otros efectos ni
   cambia resultados históricos de inbox. No hay reintentos automáticos.
5. Arranque/parada/reinicio no tomaban el bloqueo de recuperación. Ahora comparten
   bloqueo por mundo; diario y despacho Docker se verifican dentro. Contención
   responde `minecraft_change_busy`, `dispatched:false`. Las guardias se probaron
   también contra el mundo real sin despachar ninguna acción Docker.

Los controles anteriores coordinan workers propios. Un operador externo que
arranque Docker o edite archivos sin respetar el bloqueo sigue siendo externo;
no se promete exclusión sobre herramientas ajenas.

La documentación de [Box64](https://github.com/ptitSeb/box64/blob/main/docs/box64.pod)
explica emulación y opciones de memoria. Se consultó como referencia de diagnóstico,
no como prueba causal de este caso. No se actualizaron imagen, Box64 o binario,
ni se aplicaron ajustes especulativos al servidor operativo.

## Recuperación real

`20261106T223238Z/results.json` conserva oracles previos,10 comandos/recibos y
comprobaciones nuevas con DB/permisos desechables propios:

- Cero jugadores y juego disponible antes de parar; snapshot privado propio de
  bytes, existencia y modos de ambos JSON de paquetes y registro de desactivados.
- Conjunto behavior/resource sintético con dependencias mutuas: activación,
  carga positiva del behavior, arranque y reinicio con disponibilidad del juego
  y cambio de `StartedAt`. Este intento PASS no corrige retroactivamente el FAIL.
- Parada explícita y `/mc recuperar`: ambos JSON restaurados exactamente y
  registro privado restituido a su ausencia original. Otra recuperación offline
  no produjo cambios.
- Estando apagado, una excepción sintética después de reemplazar el primer JSON
  dejó un diario `pending` y una escritura parcial real. El proceso de inyección
  terminó; otro worker rechazó `/mc iniciar` antes del despacho. `/mc recuperar`
  restituyó todos los bytes, modos y existencia originales desde el diario duradero.
- Solo se retiraron las dos carpetas sintéticas con UUID verificado. Arranque final
  disponible, mismo mundo, cero jugadores,0jobs activos y entregas locales canceladas.

No se simuló corrupción del mundo ni un fallo nativo en producción. La recuperación
real acreditada revierte configuración de paquetes tras aplicación/interrupción;
no acredita reparación del ejecutable ni restauración de un mundo dañado.

La observación final comprueba juego ready, diario recovered, rechazo de recuperar
estando online y las cuatro guardias con bloqueo ocupado. Permisos operativos
Minecraft/Drive/grupos writefalse conservados. Worker propio separado actualizado;
Zhana worker y servicios intactos. No WhatsApp, llamadas, navegador, NLP, DB31,
sesiones, perfiles, publicaciones/mutaciones GitHub o transición.

## Laboratorio y límites

Contenedor separado con imagen/binario existentes, sin puertos publicados,
networknone, restartno, límite3GiB/1.5CPU y mundo sintético. No se copiaron mundos,
usuarios, permisos o historial. Paquetes/copias de trabajo privados no se añaden
a Git. Al terminar se verificó parado y se retiraron su contenedor y scratch propios;
no queda un servicio ni una copia adicional de paquetes.

La fase mínima (vanilla más par sintético) pasó un arranque y tres reinicios.
La fase con catálogo completo reprodujo primero el problema de128KiB; se conserva
como resultado incierto, cerrado con parada observada. Tras corregir el lector
se ejecutó una comprobación nueva, no un reenvío automático del efecto incierto:
un arranque y cinco reinicios PASS. Una última variante con función sintética
`list` pasó un arranque y dos reinicios, con tres confirmaciones de ejecución
del juego. En total10 reinicios aislados y1 reinicio en el servidor configurado
sin repetir el fallo nativo. Resultados en `loaded-v2-cycles.json` y
`function-cycles.json`; no se adjudican a la campaña histórica.

Los problemas iniciales del montaje del laboratorio (permisos/directorios propios)
y una copia interrumpida por symlink colgante se conservan en las notas de desarrollo.
Se corrigió solo el fixture, omitiendo symlinks sin seguir referencias externas.
No se adjudican como errores del juego/producto ni se cuentan como reinicios válidos.

La disponibilidad repetida y la recuperación segura no demuestran ausencia de una
corrupción nativa intermitente. El fallo histórico permanece abierto sin causa
reproducible y sin atribución especulativa. R10 global/R11 continúan pendientes.

## Validación y evidencia

36 pruebas Minecraft PASS,20 de respaldo/integraciones PASS y24 de núcleo,
cancelación y permisos PASS:80 comprobaciones locales pertinentes. No se volvió
a ejecutar la suite audiovisual. Ruff check y format146 archivos de src/tests/ops
PASS, diffcheck PASS. La comprobación indiscriminada de todo el repositorio
detectó un script histórico de evidencia sin formatear; se conservó intacto y se
registró en development-notes. No se modifican auditorías antiguas para pasar lint.

Evidencia separada en `docs/evidencia/NATIVE-RECOVERY-20261106/`, archivos0600,
checksums y procedimientos de operador conservados como texto. Los logs crudos
se guardan en gzip sin pérdida; sus hashes antes de comprimir se conservan aparte. Fuente del worker
y recibo final de despliegue en checks. El script
`ops/verificar_minecraft_recuperacion.py` tiene efectos reales, necesita encargo
explícito y no se ejecuta por leer este informe. Una excepción conserva diario y
snapshots privados para revisión; nunca inicia una reanudación automática.
