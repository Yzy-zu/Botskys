# Contraste de los hallazgos AGY · 07/11/2026

**35/35 hallazgos revisados. Tres defectos de catálogo/ayuda confirmados y una
respuesta incorrecta del generador.** Esta fase comprueba y clasifica; no aplica
correcciones ni despliega. Producto de referencia `80e4745`, runtime funcional
sin cambios respecto a la campaña. No se reabrió la campaña ni se hicieron
peticiones remotas, mensajes, llamadas o cambios de producción.

| Defecto confirmado | Evidencia y alcance |
| --- | --- |
| Búsqueda de SoundCloud anunciada aunque no implementada | `/dl buscar` admite `--fuente soundcloud` en sus opciones; dominio y adaptador devuelven `source_search_unavailable` antes de la red. No es un proveedor caído. La descarga por URL y la búsqueda son capacidades diferentes; el catálogo de búsqueda incluye fuentes que no admite esa operación. |
| Identificador equivocado en ayuda de AirDrop | `/hh reclamar EVENT_ID` anuncia el ID de la hora feliz, pero el handler consulta `happy_drops.id`: necesita el `drop_id`. La respuesta de creación imprime el comando correcto; la firma estática sigue siendo contradictoria y el tester usó el ID indicado por ella. |
| Duración ambigua en ayuda de llamadas | `/llamar` y `/llamada programar` muestran `--duracion MAX_SECONDS`, pero su campo es `duration`: `600` falla y `600s` funciona. El ejemplo interno `10m` y el parser son coherentes entre sí; la firma de ayuda debe expresar unidades. No se ha demostrado un fallo al establecer una llamada. |

Las tres inconsistencias tienen reproducción local nueva en
[catalog-reproduction.json](evidencia/CONTRASTE-AGY-20261107/catalog-reproduction.json).
No se recomienda inventar implementación remota para ocultar un error de catálogo:
el arreglo debe alinear capacidad anunciada, campos y ejecución.

También hay **un error de contenido comprobado**: en `conversation/c07` Gemini
respondió que el QR contenía `BOTSKY LAB 31415`; el archivo contiene
`BOTSKY-LAB-27182`. El decodificador QR local confirma el contenido. El hash coincide
con el adjunto registrado en la DB de campaña y un recorrido nuevo de análisis+SDK
con doble conserva exactamente los bytes PNG. Esto comprueba la respuesta final
incorrecta; no demuestra un defecto de transporte del backend ni reconstruye el
request remoto original, que no se capturó. No hubo generación remota nueva.
La ruta `/qr` es la capacidad determinista de decodificación.

## Balance de adjudicaciones

| Clasificación | Hallazgos |
| --- | ---: |
| Defecto de producto confirmado, alcance catálogo/ayuda | 3 |
| Dependencia externa/contenido generado | 3 |
| Expectativa equivocada del tester | 8 |
| Límite o comportamiento contractual correcto | 13 |
| Problema de fixture o arnés | 4 |
| Evidencia insuficiente | 1 |
| No formula un defecto verificable | 3 |
| Total | 35 |

Las tres adjudicaciones externas incluyen el QR incorrecto, una descarga de
subtítulos que falló y `gemini_unavailable` al componer voz. Los dos últimos son
fallos reales observados, pero sin captura original suficiente para atribuir su
causa concreta al proveedor, transporte o extractor. La prueba sintética503 solo
comprueba el mapeo controlado de Gemini; no reproduce una caída histórica.

La búsqueda con `--terminos` queda **sin evidencia suficiente** para confirmar un
filtro defectuoso: la campaña no guardó los RSS originales de esos casos. El filtro
ALL sobre título/fragmento de los primeros10candidatos puede devolver vacío de forma
correcta. Los controles sintéticos y el replay de otra captura histórica pasan;
no sustituyen la respuesta original ausente.

## Falsas alarmas comprobadas

- Las cooperachas se intentaron crear en categorías sin fotos del fixture. La
  preparación falló y retiró su publicación; los aportes posteriores encontraron
  retos fallidos. La categoría sintética disponible era `lab-sintetico`.
- `large_image` es una imagen azul uniforme4000×4000: no contiene el texto exigido
  por el oracle OCR. `wide_image` tiene4097px en un eje, por encima del máximo4096.
- El PDF multipágina tiene501páginas y supera el máximo500de entrada. El audio
  grande tiene11200078bytes y supera10MiB de ASR. El video mide3s; recortarlo hasta4/5s
  excede EOF. Son rechazos de límites comprobados sobre los archivos reales.
- La duración de voz compuesta es orientativa; el pipeline entrega Ogg/Opus, aunque
  los casos exigían MP3 y una duración exacta no contratada.
- El archivo escolar sí está referenciado en el resultado y se entrega con el
  transporte local; la lista de artefactos generados del arnés no incluye por sí
  sola todos los archivos entrantes reutilizados.
- Consultas a páginas inexistentes solicitan corrección. Los auxiliares requieren
  ID. Repetir un cierre o consultar un juego terminal no obliga a producir error.

## Validación y conservación

**45 pruebas locales pasan:**18de IA/búsqueda,11de organización y16de galería,
packs/cooperacha. Se bloquearon conexiones en las suites. Reproducciones nuevas
comprueban las tres inconsistencias de catálogo, bytes SDK/QR, error503 sintético,
dimensiones/frames/páginas/duración/tamaño de fixtures. No se modificó código de
producto, arneses históricos, configuración o servicios activos. No corresponde
una regresión productiva ni un despliegue en esta fase documental.

Se verificaron SHA de los182archivos privados del manifiesto de cierre: intactos.
Los35claims originales y las378filas históricas se conservan. No se alteraron sus
PASS/SUSPECTED/BLOCKED ni se convirtió una guardia en éxito de negocio.

[Resumen](evidencia/CONTRASTE-AGY-20261107/summary.json),
[35adjudicaciones revisadas](evidencia/CONTRASTE-AGY-20261107/adjudications.json),
[reproducción de contenido](evidencia/CONTRASTE-AGY-20261107/content-reproduction.json) y
[comprobación de fixtures](evidencia/CONTRASTE-AGY-20261107/fixture-checks.json).
Los procedimientos `.py.txt` son evidencia para ejecución deliberada local, no un
encargo automático. Recepción humana permanece NOT_TESTED. Sin NLP ni GitHub.
