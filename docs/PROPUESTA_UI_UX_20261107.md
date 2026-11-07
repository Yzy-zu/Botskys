# Presentación y experiencia de chat · propuesta 07/11/2026

El propietario confirmó que el sticker funcionó y pidió investigar la presentación
de Zhana para mejorar Botsky. Revisión de código/documentación, sin ejecutar Zhana,
leer sus privados, enviar mensajes ni cambiar producción. Esta propuesta no está
implementada y no certifica renderizado actual en Android.

## Hallazgos comprobados

- Botsky `src/botsky/store.py`, `Store.enqueue`: añade `/estado RECEIPT_ID` a todo
  resultado con texto, y divide por posiciones fijas cada3500caracteres. Explica
  IDs en ayuda/resultados y puede separar frases/marcadores.
- `src/botsky/commands/registry.py`, `Registry.help`: expone permisos internos,
  bloque R9, placeholders técnicos y ejemplo por cada ruta.
- `src/botsky/jobs.py`, búsqueda: concatena título/descripción/URL sin numeración
  ni separación entre resultados; conserva los datos estructurados en items.
- `src/botsky/adapters/evolution.py`: envía texto o artefactos; no contiene
  integración `sendNativeTable`. No basta poner pipes en un texto.

## Referencia concreta de Zhana

- `/home/petrov/zhana/src/zhana/rich_text.py`: `NativeTable` tipada, cabeceras,
  filas rectangulares, título y composición prólogo/tabla/pie. No importa runtime.
- `/home/petrov/zhana/src/zhana/providers/evolution.py`, `send_native_table`:
  POST `/message/sendNativeTable/{instance}`, cuerpo number/table; validación y
  distinción de rechazo frente a resultado incierto.
- `/home/petrov/zhana/docs/historico/UI_NATIVA_Y_COMPOSICION.md`: entrega por parte
  durable y evidencia histórica de tableMetadata. Capacidad instalada entonces;
  antes de usar hoy hay que comprobar compatibilidad actual, sin asumirla.
- `/home/petrov/zhana/src/zhana/web_search.py`, `SearchBackend.execute`: búsqueda
  web con título destacado, consulta, resultados numerados, párrafos separados
  y aviso de candidatos. No utiliza tabla nativa ni collage en esta ruta.
- `/home/petrov/zhana/src/zhana/jobs.py`, rama search_media: hasta seis opciones,
  títulos en negrita, citas con duración/autor/fuente, pie en cursiva; genera
  collage opcional con `/home/petrov/zhana/src/zhana/search_collage.py`.
  Videos y búsqueda web son contratos distintos. No heredar SoundCloud retirado.
- Guía UI de Zhana: resultado primero, progreso discreto, errores comprensibles,
  nombres útiles para archivos. Su personalidad y sus entradas NLP no se importan.
  La preferencia posterior02/11 permite emojis contextuales, sin cuota obligatoria.

## Bloque propuesto: presentación unificada y respuestas enriquecidas

1. Presentador propio con bloques tipados: texto, título, lista, cita, tabla,
   archivo y pie. Los dominios entregan datos; formatear no vuelve a ejecutar ni
   reinterpretar comandos. Preservar contenido literal y avisos necesarios.
2. Sacar IDs de diagnóstico del flujo habitual. Mantenerlos internos y accesibles
   en consultas explícitas; conservar identificadores útiles para seleccionar o
   confirmar. Diseñar estado/cancelación mediante cita verificada o comandos
   explícitos y, con varias tareas, elección acotada al mismo actor/chat/época.
3. Ayuda breve por tarea, ejemplos copiables y explicación humana de permisos;
   detalles de arquitectura solo en documentación/diagnóstico de operador.
4. Búsqueda web: encabezado, consulta, opciones numeradas, título destacado,
   fuente, extracto breve marcado como vista previa y URL íntegra. Aviso compacto
   de páginas no verificadas. No inventar duración, miniaturas ni acciones.
5. Videos: lista con duración/autor/fuente medidos, selección explícita existente
   y mosaico opcional de miniaturas. Enlaces web genéricos no se transforman
   automáticamente en videos descargables.
6. Tablas nativas para horarios, encuestas, clasificaciones, cuota/listas Drive y
   mods cuando comparar columnas ayude. Añadir tipo de parte/validación/transporte
   y persistencia propia, conservando CAS, ACK y límites; nunca duplicar envío
   tras timeout con un fallback. Alternativa legible acordada antes del despacho.
7. Dividir por bloques/párrafos manteniendo marcadores; paginar listas con estado
   propio. Archivos con nombre/leyenda útiles y sin confirmaciones redundantes.

Implementación por fases: primero IDs/ayuda/composición/búsqueda; después tablas
nativas y presentación del resto de dominios; finalmente mosaicos y pulido visual.
Pruebas locales de datos/formato, literalidad, límites, aislamiento y recuperación;
muestras reales nuevas solo bajo alcance autorizado. HTTP aceptado no certifica
apariencia ni recepción humana. Sin NLP ni generación extra para maquillar datos.
