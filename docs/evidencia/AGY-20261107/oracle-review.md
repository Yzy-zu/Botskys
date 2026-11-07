# Revisión de oráculos para AGY · 2026-11-07

## Alcance

Revisión estática de `ops/stress_agy.py`, `src/botsky/commands/registry.py`,
`docs/CONTRASTE_STRESS_20261106.md` y adjudicaciones de
`docs/evidencia/CONTRASTE-20261106/`. No se lanzó AGY ni se cambió producto u
operaciones. El guion ya fija el modelo `gemini-3.8-flash-medium` y reúne 30
entradas de campaña; eso no demuestra ejecución ni éxito.

La campaña anterior tuvo 783 casos registrados: 379 `SUSPECTED`, 83 `BLOCKED`,
134 rutas observadas de 152 y reportes para 29 de 30 herramientas. Sus
adjudicaciones muestran que una discrepancia de estado no basta para declarar un
bug. Mantener resultados anteriores intactos y tratar esta revisión solo como
guía para congelar oráculos nuevos.

## Oráculo y alcance de esta campaña

- Una sesión AGY por cada una de las 30 etiquetas de herramienta; proponer 8–16
  casos por herramienta, ampliando solo hasta 40 cuando el número de operaciones
  lo requiera. Incluir una lista de rutas/campos cubiertos y huecos, no forzar
  casos de relleno.
- Drive: `write=false`; una guardia en escritura se registra como `BLOCKED`, no
  como éxito ni como bug. El estado conocido de OAuth es válido: no copiar la
  hipótesis histórica `invalid_grant` al oracle. Consultas disponibles pueden
  probarse según el alcance local/remoto autorizado.
- Evolution: todo envío queda capturado localmente; no hacer POST real. Un recibo
  local de captura no equivale a proveedor ni a recepción humana.
- Minecraft: lectura real permitida dentro de alcance; mutaciones deben quedar en
  guardia. Diferenciar observación del servidor y respuesta de rechazo de una
  mutación; la segunda no acredita que la acción de juego funcione.
- Llamadas: deshabilitadas y sin perfil propio. Probar solo sintaxis/guardias
  locales, sin perfil operativo, producción, navegador ni llamada real. No
  etiquetar la guardia como prueba de llamada.
- Ningún caso de esta campaña modifica el producto. Errores sospechados quedan
  como hallazgos para contraste posterior.

## Reglas concretas para congelar casos

- Derivar rutas, campos obligatorios/opcionales, enumeraciones, límites, ejemplos
  y permisos del `Registry` en cada tanda. Cubrir todas las rutas y campos con una
  matriz; una ruta cuenta como cubierta solo si se ejecutó esa acción. No deducir
  cobertura de `/ayuda`, un parseo o una respuesta de guardia.
- Un caso positivo debe describir el efecto contractual mínimo y un observable
  disponible: estado/datos/recibo/artefacto. Un caso negativo debe fijar el
  campo inválido y código contractual cuando exista. No exigir `failed` si
  `needs_input` es la respuesta prevista para corrección; tampoco aceptar una
  lista genérica de estados que haga pasar cualquier resultado.
- Separar sintaxis, validación, reserva/inicio, ejecución del motor, vista previa,
  confirmación, entrega del proveedor y recepción humana. Cada etapa tiene su
  propio oracle. Un ACK del proveedor no acredita lectura humana; una guardia no
  acredita el efecto de negocio.
- Comprobar dimensiones, bytes, páginas, duración y formato reales del fixture
  contra el límite efectivo antes de exigir éxito. Registrar entradas de control
  dentro del límite. “Grande”, “corrupto” o “vacío” no predicen por sí mismos el
  resultado. Añadir contenido-oracle (por ejemplo, texto visible) solo cuando el
  fixture realmente lo contiene.
- Respetar la dirección de cada transformación: por ejemplo, SRT es extracción
  desde una pista admitida, no aceptación automática de un `.srt` como origen;
  PDF escaneado no equivale a PDF con texto. No inferir conversiones no descritas.
- Hacer cada recorrido con estado aislado o limpiar/cancelar explícitamente la
  sesión previa. Encadenar IDs únicamente desde la respuesta real inmediatamente
  anterior y dentro del mismo actor/chat/cuenta/época. La etiqueta `output:cNN`
  del harness no sustituye la cita de una parte aceptada ni una referencia de
  artefacto válida.
- Para idempotencia y estados terminales, comparar el estado final/recibo y
  ausencia de duplicación; no exigir que la segunda lectura o reintento seguro
  falle. Congelar comandos y expectativas antes de ejecutar.
- Generar textos, nombres, fechas, importes y argumentos con fixtures sintéticos
  por corrida. No insertar secretos, identificadores personales, datos de cuentas,
  destinos reales ni IDs inventados. El tester puede proponer casos, pero no
  decidir permisos ni convertir instrucciones en prosa en comandos.
- AGY sí puede contrastar contenido con un oracle determinista fijado antes de la
  ejecución (por ejemplo, una cadena sintética que el fixture contiene). Dejar
  `NOT_TESTED` para percepción/aceptación humana, calidad subjetiva y recepción
  humana; un resultado de modelo o de transporte no las acredita.

## Expectativa primaria por cada una de las 30 herramientas

La expectativa es una guía de cobertura, no un PASS anticipado. Por herramienta,
congelar al menos un camino admisible, uno de rechazo ligado a campo/límite real
y un caso de estado/continuación cuando el contrato lo permita; expandir hasta
cubrir todas sus acciones del catálogo.

| Herramienta | Oráculo que evita falsas sospechas |
|---|---|
| `download_media` | Separar búsqueda, elección y descarga; validar enlace/formato/recorte/calidad. Resultado remoto no garantizado y búsqueda sin selección no es descarga. |
| `convert_document` | Exigir solo destinos/rutas soportados; PDF escaneado puede dar `document_no_text`; verificar límite de páginas antes de esperar artefacto. |
| `edit_media` | El origen es medio reconocido; `/editar srt` extrae pista de subtítulos, no normaliza un archivo SRT de entrada. |
| `manage_pdf` | `iniciar/agregar` reservan sesión; validación ocurre al procesar. Aislar sesiones, observar fallo de motor sin presumir cierre y seleccionar páginas solo en PDF admisible (máximo 500). |
| `make_sticker` | Imagen estática admisible; 4097px por eje excede el límite y WebP animado no promete seleccionar frame. Verificar WebP generado (512×512) para entrada válida. |
| `read_image` | OCR/QR se juzga contra contenido presente; imagen uniforme puede producir `empty`. Aplican límites compartidos de dimensiones. |
| `transcribe_media` | Audio debe contener habla para exigir texto; silencio/no habla puede quedar vacío. Comparar artefacto con `output_mode` y vigilar el límite de bytes. |
| `make_voice` | Distinguir generación literal de voz y composición; duración solicitada puede ser indicativa/advisory. Verificar formato contractual, no asumir MP3. |
| `conversation` | Validar tipo/firma/contenedor del medio antes de atribuir fallo a interpretación; evaluar contenido humano aparte de status técnico. |
| `search_web` | `required_terms` son restricciones literales y cuentan para el máximo efectivo; resultados dependen de RSS/red y no acreditan relevancia universal. |
| `manage_conversation` | Modos/pausa respetan sintaxis tipada; no exigir sensibilidad a mayúsculas ni restricciones extra no declaradas. |
| `save_note` | Texto obligatorio y literal; entrada corregible puede devolver ayuda/`needs_input`, no necesariamente `failed`. |
| `find_notes` | Consultar filtros/paginación y datos presentes; página válida sin resultados puede ser `empty`, no error de índice. |
| `manage_memory` | Consultas/listado y ausencia son estados observables; no exigir `failed` para recurso inexistente si no lo fija el contrato. |
| `manage_reminder` | Distinguir formato de duración (`10m`) de entero desnudo; comparar estado terminal tras cancelar/archivar y tolerar lectura idempotente. |
| `manage_school` | Adjuntar conserva referencia; no presupone abrir/parsear PDF al crear tarea. Probar por separado campos de fecha/hora y el ciclo de tarea/horario. |
| `manage_poll` | IDs/opciones deben proceder de creación; resultados de encuesta cerrada pueden seguir siendo consultables. |
| `manage_drive` | Respetar `write=false`: guardia de escritura es `BLOCKED`, no éxito. El OAuth actual está válido; no esperar `invalid_grant`. `needs_input` para elegir/corregir es válido; diferenciar evidencia local de Drive remoto. |
| `manage_messages` | Preparar muestra vista previa/validación de adjunto (firma PNG no asegura decodificación); estado de borrador puede devolver lectura correcta aun cuando una transición no aplica. Evolution captura localmente: ningún POST real; captura no es ACK ni lectura humana. |
| `send_sticker` | Resolver sticker de catálogo/ID real; mayúsculas y comillas permitidas por lexer no alteran por sí solas validez. Recepción humana separada. |
| `manage_pack` | Usar categorías presentes en el catálogo; compra requiere selección/confirmación y recibo. Un reintento idempotente no tiene que ser rechazado. |
| `manage_cooperacha` | Elegir categoría/objetivo/importe dentro del catálogo, saldo y límites reales; no inventar disponibilidad ni exigir error a un reintento seguro. |
| `manage_happy_hour` | Duración usa sintaxis contractual con unidad; acciones de lluvia/reclamo requieren evento/ID y anuncio/condiciones válidas. |
| `manage_economy` | Verificar saldo/diario/top con DB sintética; no imponer política de adjuntos que la ruta no declara. XP no equivale a compra real. |
| `manage_blackjack` | IDs se encadenan desde la mesa; acciones dependen de fase. Estado final puede consultarse idempotentemente; no probar reglas expresamente excluidas. |
| `manage_roulette` | Crear sala y usar ID devuelto; importe respeta tipo entero/límites. No dar por bug una consulta bloqueada por falta de sala. |
| `manage_admin` | Probar lectura/preview en ámbito sintético; targets/IDs provienen de fixtures. Mutaciones a participantes no forman parte de cobertura permisible. |
| `manage_minecraft` | Priorizar consultas de estado; si se usan acciones de laboratorio, observar precondición/estado/recibo y restaurar. `needs_input` de sintaxis no demuestra fallo del worker. |
| `make_prank` | Validar etiqueta literal; no inferir lectura, OCR ni rechazo de adjunto no especificado por el contrato. |
| `control_call` | Catálogo agrupa clip/avatar/agenda y controles de llamada. Respetar guardia y permiso por acción; llamada está deshabilitada y sin perfil. No abrir perfil operativo ni llamar; una guardia no es PASS funcional. |

`control_call` es una etiqueta del set de campaña para familias `audiovisual.*`,
no una sola operación. El conteo de 30 herramientas no sustituye el recuento de
rutas/campos: registrar por separado las acciones audiovisuales efectivamente
cubiertas y las bloqueadas.

## Límites de interpretación

Mantener archivos originales de campaña y sus fallos sin reescritura. Para cada
sospecha nueva, enlazar caso, comando congelado, ruta/campos, fixture y recibo;
contrastar con el contrato vigente antes de clasificarla. No reutilizar valores de
la campaña pasada como datos operativos ni inferir un arreglo del producto a
partir de esta revisión. “No reproducido”, externo, bloqueado y no probado son
resultados distintos de un defecto confirmado.
