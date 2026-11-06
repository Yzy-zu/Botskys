# Cobertura complementaria local · punto1

Encargo del propietario: completar las18rutas y44campos explícitos que no se
observaron en la campaña cerrada de134/152rutas. Este suplemento usa bases y
fixtures sintéticos propios, motores locales, dobles HTTP y el servicio Node de
prueba. No reabre campañas ni habilita efectos externos o servicios activos.

**Punto1 cerrado localmente:18/18rutas y44/44campos pendientes conciliados.**
La pasada final ejecutó224pruebas: cero fallos, errores, omisiones o intentos de
conexión fuera de loopback. Los28grupos de ruta/campos afectados tienen oracles
revisados en [reviewed-gaps.json](evidencia/COBERTURA-20261106/reviewed-gaps.json).
No se confirmó ningún defecto nuevo ni se modificó código de producto.
Ruff comprueba estilo/formato de135archivos; pip check y diffcheck pasan.

Varias rutas ya tenían pruebas locales con oracles de negocio; ahora se concilian
contra los huecos concretos del registro de campaña. Se ampliaron los casos cuya
comprobación era insuficiente. Las observaciones proceden de recibos ejecutados
y trabajos finalizados en pruebas con aserciones, excluyendo los sondeos fríos
de disponibilidad y los tests que solo parsean ejemplos.

| Rutas ausentes de la campaña | Comprobación local |
| --- | --- |
| `/estado`, `/cancelar`, `/confirmar` | ID y estado propios, aislamiento, retiro sin escritura, vista entregada y confirmación consumida sin repetir motor. |
| `/admin advertir`, `/admin quitar-aviso` | Aviso persistido una vez y revocación del ID exacto del miembro. |
| `/admin expulsar`, `/admin promover`, `/admin degradar` | Objetivo verificado, acción exacta ante doble, permisos y efectos únicos frente a duplicados. |
| `/admin ban`, `/admin unban` | Registro del ban antes del efecto incierto, bloqueo de nuevas mutaciones y no repetición; unban revoca el registro local sin reincorporar participantes. |
| `/admin nuclear-confirmar`, `/admin nuclear-cancelar` | Vista previa, roles, coste, liquidación/incertidumbre y cancelación sin efecto o cargo. Todos los participantes y transportes son dobles. |
| `/ruleta cancelar` | Devolución exacta a contribuyentes, cero reservas y ninguna expulsión. |
| `/drive elegir` | Vista entregada propia, selección/límites/TTL y bytes exactos del archivo descargado mediante HTTP doble. |
| `/clip poner` | ID de catálogo y nombre generan acciones diferentes y conservan la llamada exacta. ACK sintético, sin reproducción humana acreditada. |
| `/llamada programar`, `/llamada reprogramar`, `/llamada cancelar-agenda` | Fecha/hora de México, ID, ámbito, modos Live/audio, volumen y política de fin; actualización/cancelación persistidas sin llamada real. |

Los campos adicionales incluyen duración/tema/video de `/llamar`; voz/efecto de
`/voz crear`; fecha/hora y opciones de agenda; objetivos de avisos/XP; duración
de hora feliz e ID de reparto de blackjack. Las aserciones verifican los valores
transmitidos, saldos, estado y efectos del doble, no solo presencia en el parser.

En medios, `/dl anterior --desde 0.1 --hasta 0.5` produce un recorte medido con
`ffprobe` de0.4s con tolerancia de0.15s, sin nueva descarga. La selección de idioma
de subtítulos sobre el retenido sin pista devuelve el error específico previsto;
no se declara extracción exitosa de una pista ausente. `/pdf reintentar ID --confirmar-incierto` también se prueba con vista entregada: autoriza una vez,
reentrega el mismo artefacto y conserva un solo trabajo de motor.

Los oracles por ruta/campo y sus testIDs están en
[root-plan.json](evidencia/COBERTURA-20261106/root-plan.json),
[admin-plan.json](evidencia/COBERTURA-20261106/admin-plan.json) y
[av-plan.json](evidencia/COBERTURA-20261106/av-plan.json).
El principal revisó los casos y sus límites, incluido que `unban` es una mutación
del registro local y que el contador de llamadas del driver Node es sintético.

Reproducción en el entorno propio:

```text
.venv/bin/python ops/cobertura_pendiente_local.py
```

El runner bloquea conexiones fuera de loopback y propaga la guardia Node local.
Registra nombres de campos, rutas, códigos, fases y testIDs, sin secretos, texto
de usuario ni credenciales. Conserva cada ejecución en `runs/`; la primera
pasada detectó un error de importación del nuevo módulo AV, corregido para el
mismo modo de discovery que el resto de la suite. Ese fallo de harness permanece
archivado y no se atribuye al producto.

Resultados y recuentos finales en
[summary.json](evidencia/COBERTURA-20261106/summary.json),
[route-coverage.json](evidencia/COBERTURA-20261106/route-coverage.json) y
[test-results.json](evidencia/COBERTURA-20261106/test-results.json).
La observación de un campo no demuestra todas sus combinaciones o fronteras.
El original `STRESS-20261106/route-coverage.json` se conserva con su hash y sus
NOT_TESTED originales. Este cierre local no acredita proveedores, recepción
Android, escucha/render humano, agenda de producción ni mutaciones reales;
R10 remoto y R11 conservan sus pendientes y condiciones.
