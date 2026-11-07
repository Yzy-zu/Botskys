# Runner review · AGY 2026-11-07

## Recomendación operativa

La campaña nueva debe entrar por `ops/retest_agy.py`, en un directorio privado
nuevo y con `--run`. No ejecutar directamente `ops/stress_agy.py` ni el
`ops/campana_lab.py` histórico para esta ronda. El wrapper crea tres tandas de
diez herramientas, hasta tres sesiones concurrentes, una sesión/modelo
`gemini-3.8-flash-medium` por herramienta, una SQLite propia por herramienta y
un proceso backend aislado. No reanuda directorios existentes.

```sh
PYTHONPATH=src:ops .venv/bin/python ops/retest_agy.py \
  --directory private/agy-retest-20261107 --run
```

La bandera `--run` es obligatoria y el directorio debe no existir. La campaña
parará ante el umbral de cuota del 5% o el archivo `STOP`; una ejecución parcial
no debe reanudarse automáticamente.

## Diferencias importantes del harness histórico

- `ops/campana_lab.py` es el runner de campaña anterior: sus salidas de casos y
  resumen pueden llegar al grupo Botsky Lab. No cumple el requisito actual de
  cero mensajes reales.
- `ops/stress_backend.py` hace capturables por defecto las respuestas, pero
  acepta `publish=true` para hasta dos muestras reales y luego manda un resumen
  por herramienta. El worker reutilizado aquí fuerza `live=False` en su
  transporte; las respuestas y resúmenes quedan en el ledger local.
- El backend histórico pone Drive de escritura en el perfil efímero. El wrapper
  lo baja a `false`, igual que las escrituras de grupos y Minecraft. Los
  handlers de mensajes conservan permisos en la copia efímera para poder
  recorrer su flujo; `CaptureOnlyToolHTTP` impide que sus POST alcancen
  Evolution. No se altera el perfil productivo.
- Las fixtures `output:cNN` dependían de volver a adjuntar artefactos como si
  fueran ingreso original y podían producir `attachment_source_mismatch`. El
  wrapper las excluye y guarda el caso original como `NOT_TESTED`; las cadenas
  de archivos producidos quedan sin cobertura en esta ronda.
- La regla de 20–32 casos y la instrucción obsoleta de que Drive ya tenía
  `invalid_grant` se eliminan del prompt efectivo. Cada propuesta conserva
  `proposal-original.json`; publish se fuerza a falso antes de ejecutarse.
- El reporte histórico cortaba cada resultado a 1.700 caracteres. El wrapper
  añade evidencia local completa saneada, hasta 12.000 caracteres por resultado;
  una salida mayor conserva ese límite y no equivale a JSON completo.

## Fronteras y límites

Se verifica de forma remota metadata de grupos durante la preparación heredada;
esto es una consulta de solo lectura, no un envío. Los proveedores de contenido
y consultas de Minecraft permitidas pueden ser reales. Drive, grupos y
Minecraft no tienen escritura habilitada; llamadas y navegador siguen fuera.
Un ACK de fixture es exclusivamente evidencia local. Ningún estado de este
runner demuestra entrega al teléfono, lectura humana, reproducción o recepción
en Android. `SUSPECTED` requiere contraste independiente antes de llamarlo bug.

Las herramientas con más de 16 casos útiles, operaciones que dependan de
archivos previamente producidos y efectos con guardia o permiso deshabilitado
deben quedar explícitamente como huecos; pasar una validación, sondeo o guardia
no acredita el efecto.

## Comprobación de este wrapper

- `python3 -m py_compile ops/retest_agy.py`: PASS.
- `--help` desde el entorno propio: PASS; enumera 30 herramientas y requiere
  directorio nuevo más `--run` para ejecutar.
- Transporte HTTP con host Evolution sintético: POST interceptado, ACK marcado
  `delivery_fixture` y ledger local, sin conexión de red: PASS.
- No se iniciaron sesiones AGY ni preparación con APIs reales en esta revisión.
- No se verificó recepción humana ni el efecto de ninguna herramienta.
