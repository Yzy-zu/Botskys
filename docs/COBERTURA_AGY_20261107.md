# Cobertura complementaria de AGY · 07/11/2026

**45/45rutas y56/56campos pendientes comprobados localmente.** Encargo del
propietario: punto2 de los pendientes. Es un suplemento a la campaña cerrada de
378casos, sin reabrir AGY ni alterar sus109/154rutas observadas históricas.
Producto de referencia funcional67500bf; documentación del despliegue5d216d1.

Pasaron **268pruebas Python y4Node**, cero fallos, errores u omisiones, cero intentos
de conexión fuera de loopback en la medición Python; Node usa su guardia de red
local. Se emplearon SQLite temporal, motores sobre archivos sintéticos, HTTP/IPC
local y dobles. No se cargaron credenciales de integración en el recolector ni
se activaron llamadas, navegador, SSH, envíos o cambios de servicios/producto.

Los56grupos ruta/campos tienen un oracle revisado. El recolector registra recibos
confirmados y trabajos finalizados en tests con aserciones; excluye sondeos fríos
y parseo puro. El cierre cruza cada ruta/campo contra sus testIDs específicos
pasados, no contra cualquier respuesta aislada o una lista de comandos propuestos.

| Ámbito | Comprobación y alcance |
| --- | --- |
| Estado/cancelación/confirmación y PDF | ID propio, aislamiento, cancelación sin publicación tardía; vista entregada y autorización explícita reentregan el mismo artefacto sin repetir motor. |
| Descargas y voz | Idioma persistido hasta trabajo; vista de búsqueda y rechazo específico al no existir pista local; voz/efecto de cita y voz de última respuesta comprobados ante CLI doble, texto exacto y audio Opus real. No acredita subtítulos remotos ni escucha humana. |
| Packs, blackjack, ruleta y recados | Compra/estado con IDs propios, saldo/escrow, idempotencia y fuente de cita; liquidación o devolución y efectos de grupo exclusivamente simulados. |
| Administración | Objetivos y avisos propios, roles, cambios y bans ante dobles, XP exacto en SQLite y nuclear con confirmación/cancelación. No participantes reales. |
| Minecraft | Inicio/parada/reinicio/recuperación, mods/consola y backup pasan por adaptador y runner sintético. Backup comprueba exactamente una acción y destino/params; no crea ni certifica un respaldo remoto nuevo. Las pruebas previas del worker real conservan su evidencia separada. |
| Clips/avatar/agenda | Cambios de estado/volumen, IDs, nombres/duración transmitidos, confirmaciones de avatar y agenda persistida con fecha/zona/audio/fin. Diales y efectos son de fixture, sin llamada ni render o recepción reales. |

Para `/clip siguiente`, la integración de chat comprueba explícitamente
`av_control_unconfirmed`: ese fixture no acredita avance. El test Node V4 verifica
por separado que el controlador selecciona el segundo clip sintético y conserva
idempotencia/repetición. Los dos niveles están enlazados; no se declara que la
respuesta no confirmada sea un éxito de reproducción.

Se ampliaron aserciones de voz e idioma, un recorrido de controles clip/avatar y
una prueba positiva de `/mc backup` con runner doble. El resto reutiliza oracles
existentes suficientes, medidos de nuevo. **No se confirmó un defecto nuevo ni
se modificó `src/`, `calls/` o código productivo.** No hace falta desplegar este
suplemento: únicamente cambian pruebas, recolector y documentación.

## Evidencia y reproducción

[Resumen final](evidencia/COBERTURA-AGY-20261107/final-summary.json),
[56oracles y sus observaciones](evidencia/COBERTURA-AGY-20261107/reviewed-gaps-final.json),
[cobertura medida](evidencia/COBERTURA-AGY-20261107/route-coverage.json),
[268pruebas](evidencia/COBERTURA-AGY-20261107/python-tests.txt) y
[4pruebas Node](evidencia/COBERTURA-AGY-20261107/node-clip-tests.txt).
Los planes por ámbito y el manifiesto SHA se conservan en el mismo directorio.
Cada medición tiene una carpeta nueva en `runs/`; el índice superior refiere la
última medición. La entrada históricaAGY no cambia.

```text
.venv/bin/python ops/cobertura_agy_local.py
NODE_OPTIONS=--require=/home/petrov/botsky/ops/restringir_red_local.cjs node --test calls/test/clip-commands.test.cjs
```

La cobertura local no certifica disponibilidad de proveedores, efecto remoto ni
percepción/recepción humana. Las validaciones reales pendientes del proyecto siguen
separadas. Se conserva el umbral5% y no hay reanudación automática de campañas.
