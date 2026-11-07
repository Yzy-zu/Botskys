# Recuperación del Botsky legacy de octubre

Encargo del propietario: buscar `botsky/` en los respaldos de Drive para
restaurar el legacy. Aclaración expresa: Botsky de octubre, anterior a Zhana.

## Fuente encontrada y recuperada

Drive: `Backups_Flota/Miroslav/miroslav_backup_2026-10-28_03-00_e45c4180.tar.gz.enc`.
[Respaldo original](https://drive.google.com/file/d/1WDeSKY-QI73D2UARLJUWo89-lc_3L5of/view).
Tamaño 2.794.665.248 bytes; MD5 proveedor y descarga coinciden:
`37896cd8d5d2245ef0a6e48d5dfd1e5f`.

El conector rechaza archivos de más de 256 MiB. Descarga de solo lectura mediante
OAuth propio ya configurado, sin copiar credenciales de otros servicios. Hubo
cierres de conexión; se completaron los tramos faltantes y se verificó el checksum
del archivo entero antes de descifrar. AES-256-CBC/PBKDF2 con referencia a la clave
local existente, sin imprimirla ni modificarla. Descifrado finalizó con código 0.

31.632 entradas en el archivo; 6.992 entradas bajo `botsky/`. Recuperados 5.158
archivos de código y recursos, 1.252.682.898 bytes, en:

`private/legacy-recovery-20261107/oct28-source/`

Paquete `whatsapp-bot` 1.0.0, Node.js, entrada `src/core/server.js`. El respaldo
cifrado original y los manifiestos individuales quedan en el directorio privado
padre, con directorios 0700 y archivos 0600. Los archivos recuperados se verificaron
por tamaño y SHA256 mediante una segunda lectura completa. Comprobación sintáctica
`node --check` de entrada y `ecosystem.config.js`: PASS.

No se extrajeron al árbol de código las carpetas de datos, perfiles, sesiones,
credenciales, logs o dependencias, ni `.git`/`.agents`. No se leyeron contenidos de
DB ni cookies. El archivo cifrado conserva el respaldo original sin modificar.
No se ejecutó el runtime legacy, clasificadores, instalación ni pruebas funcionales.
La recuperación de archivos no certifica funcionamiento o aceptación de proveedores.

## Otras copias observadas

La carpeta independiente `Botsky` de Drive estaba vacía. En Miroslav se observaron
respaldos del 28/10, 31/10, 01/11, 02/11, 03/11, 04/11 y 06/11; se inspeccionó el
contenido del 28/10 por corresponder al periodo legacy, sin afirmar que sea el
último cambio de octubre. Los otros archivos no se descargaron ni compararon.

Copia local completa de archivo del 15/10 en
`/home/petrov/backups/botsky_archive_20261015_204506.tar.gz`: 294 archivos de código
recuperados en `private/legacy-recovery-20261107/oct15-source/`, también con
manifiesto de hashes. Copia funcional local del 24/10 contiene solo 22 archivos de
código: referencia parcial, no reemplazo completo ni mezcla aplicada.

## Alcance al cierre

Código legacy recuperado de Drive y listo para revisión aislada. No se sustituyó
`/home/petrov/botsky`, no se activó legacy ni se cambiaron servicios, webhook,
proveedores o datos productivos. Activarlo requiere preparar aparte dependencias,
configuración, datos y compatibilidad, y acordar el destino del corte. La
restricción vigente de no ejecutar/investigar NLP sigue intacta.

Evidencia privada: `drive-metadata.json`, `download-verified.json`,
`oct28-recovery-manifest.json`, `recovery-verified.json` y manifiesto del 15/10.
Sin archivos privados en Git; no envíos, llamadas, navegador ni GitHub.
