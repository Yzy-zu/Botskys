# Minecraft: corrección del runtime Box64

Encargo: resolver el fallo nativo, no limitarse a observar reinicios sanos.
Se aisló una corrupción de memoria reproducible en el Box64 instalado y se corrigió
sobre su revisión exacta, sin actualizar Bedrock ni sustituir la imagen base.

## Evidencia y corrección

El fixture propio `ops/native/atexit_race.c` registra32768 destructores C++ desde
16hilos y verifica que todos se ejecuten. En el Box64 original de la imagen falla
con `realloc(): invalid old size`. Bajo GDB, tanto el original como una compilación
sin parche de la revisión9f285eab reproducen la corrupción. El backtrace con símbolos
identifica `__libc_realloc → AddCleanup1Arg → my___cxa_atexit`, con hilos modificando
la misma tabla. No depende de mundos, mods o mensajes.

El código coincide con el defecto descrito por el [reporte upstream4574](https://github.com/ptitSeb/box64/issues/4574).
Ese reporte orientó la investigación; los fixtures y backtraces nuevos acreditan
el defecto en este runtime. No se atribuye causalidad al addon sintético.

`ops/patches/box64-9f285eab-cleanup-lock.patch` serializa ampliaciones, inserciones
y extracción LIFO de las tablas. Suelta el mutex antes de ejecutar callbacks para
permitir reentrada. Protege fork con atfork y reinicializa la copia del mutex en
hijos clone sin memoria compartida; conserva el mutex de los hilos CLONE_VM.
No pretende resolver destrucción concurrente del contexto/ELF por sus llamadores.

La fuente exacta se obtuvo como archivo oficial inmutable, con hash registrado;
se compiló con GCC13/CMake y ARM_DYNAREC, primero sin parche y luego con él, bajo
los mismos ajustes. No se instaló toolchain en el sistema: el compilador cruzado
de los fixtures se extrajo en private/ desde paquetes Ubuntu. La fuente Box64 y
sus binarios conservan licencia MIT y referencias privadas propias.

Resultados previos al despliegue:

- Original instalado: FAIL reproducible en contenedor aislado.
- Revisión exacta sin parche: FAIL con backtrace simbolizado en AddCleanup1Arg.
- Misma revisión parcheada:10 pruebas de32768 callbacks PASS; ninguna omisión.
- Tres pruebas de callbacks recursivos/LIFO y fork/clone PASS.
- Seis ejecuciones adicionales dentro de la misma imagen Docker PASS.
- Minecraft aislado, arranque normal de la imagen, catálogo completo, par sintético,
  configuración efectiva Box64 y caché de traducción existente: un arranque y dos
  reinicios disponibles con el runtime corregido. Mundo sintético, sin red/puertos.

El error histórico `free(): invalid next size (normal)` no dejó un core que permita
atribuir retrospectivamente esa ejecución a una línea exacta. Sí está demostrada
y corregida una carrera nativa del runtime instalado capaz de corromper esa tabla.
Los reinicios sanos son controles de integración; no sustituyen esa prueba causal
ni garantizan que todo futuro fallo nativo tenga el mismo origen.

## Aplicación y persistencia

Se guardó respaldo nuevo del servidor apagado y copia privada exacta de Compose.
La única diferencia de configuración comprobada es un bind de solo lectura del
Box64 probado sobre `/usr/local/bin/box64`. La referencia vive en el Compose real,
no en una modificación efímera de la capa del contenedor. Imagen y montaje de datos
originales se verifican antes/después; el contenedor se recrea primero sin arrancar.
Después se comprueban arranque, reinicio y disponibilidad del juego por Botsky.

El artefacto propio queda bajo `.botsky-native-runtime/` en la base Minecraft;
nombre por SHA256, licencia y metadatos de despliegue, fuente y build separados.
SHA256 del runtime probado:
`1979d98d290610f94ac4ad187c3a55c8a045c9b1a927940fe3b50bebb87feac3`.
No se modificó el Box64 dentro de la imagen original ni se actualizó Bedrock.

Esto conserva el montaje en recreaciones que usen ese Compose. No promete que
un runtime compilado contra esta plataforma sea compatible con cualquier imagen
futura. Actualizar la imagen o retirar el montaje requiere comprobar compatibilidad;
el pin evita que una actualización sustituya silenciosamente la corrección.

## Reversión de operador

No restaurar un mundo ni ejecutar scripts automáticamente. Con cero jugadores y
estado observado, parar el servidor; comparar el hash de Compose con el recibo de
despliegue antes de restaurar la copia privada `compose-before.yml`. Recrear solo
el servicio Minecraft con la imagen local original, sin pull, y verificar arranque
real. Si alguien editó Compose después, conciliar esos cambios antes de sobrescribir.
Quitar el bind devuelve el Box64 original conservado en la imagen y también su
carrera conocida: la reversión es una contingencia, no una corrección alternativa.

Evidencia separada0600 en `docs/evidencia/BOX64-CLEANUP-20261106/`: fuente/hashes,
backtraces, pruebas de callbacks, controles Minecraft y recibos del despliegue.
No se reabren campañas históricas ni se modifican sus FAIL. Sin Zhana runtime,
DB31, perfiles, sesiones, NLP, llamadas, mensajes o transición Botsky. R10global y
R11 no quedan aceptados por esta corrección.
