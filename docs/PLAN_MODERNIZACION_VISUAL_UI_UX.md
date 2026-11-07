# Modernización visual y de experiencia de Botsky

Versión 1 · 07/11/2026 · Encargo: recuperar la calidad visual de Zhana en toda la experiencia.
Estado: **plan y auditoría documental terminados; implementación pendiente**.
Este documento amplía `PROPUESTA_UI_UX_20261107.md` y concreta una continuación de
R1/R3/R7/R8/R9/R11 del plan de construcción, sin reabrir campañas históricas.

## 1. Resultado que buscamos

Botsky debe sentirse como un producto de chat cuidado: el usuario entiende el
resultado, distingue las opciones y sabe qué hacer después sin leer identificadores
internos. Recuperar de Zhana sus composiciones, tablas y recursos visuales útiles,
con datos y persistencia propios de Botsky. El alcance incluye las 30 herramientas
de dominio, el núcleo de ayuda/seguimiento y las adaptaciones audiovisuales:
**154 rutas actuales, 190 campos declarados entre sus rutas y 32 raíces de operación**,
según el registro de comandos. Los campos se cuentan por ruta; no son 190 nombres únicos.

La presentación respeta la sintaxis explícita vigente. No se recupera la entrada
NLP de Zhana. Su frase «elige la segunda» se adapta a un comando corto y verificable;
no se convierte la prosa, un QR o el contenido de una tabla en una orden.

Entregables finales: sistema visual común; presentadores por dominio; collages de
videos; tablas nativas; ayuda navegable; seguimiento sin IDs intrusivos; archivos
con leyendas; composición audiovisual revisada; catálogo de muestras sintéticas;
matriz de verificación y despliegue reversible de las mejoras.

## 2. Auditoría de referencia y diferencias actuales

| Superficie | Evidencia concreta de Zhana | Situación y decisión para Botsky |
| --- | --- | --- |
| Tablas reales | `rich_text.py`, `providers/evolution.py:send_native_table`, migración 030 | Botsky no integra esa ruta. Añadir parte tipada y envío por HTTP propio. |
| Composición | `rich_delivery.py`, `UI_NATIVA_Y_COMPOSICION.md` | Aprovechar la outbox/CAS propios, ampliar tipos sin importar tablas/runtime de Zhana. |
| Videos | `jobs.py`, rama `search_media`, `search_collage.py` | Botsky conserva metadatos pero su lista expone principalmente título/ID. Recuperar imagen y ficha legible. |
| Búsqueda web | `web_search.py:SearchBackend.execute` | Zhana numera y separa resultados. Botsky concatena líneas. Crear una lista editorial clara. |
| Drive | `drive_runtime.py:run_drive` | Tablas de cuota y archivos con tamaños, ámbito y pie. Conservar límites actuales de Botsky, no copiar límites históricos. |
| Organización | `school.py`, `reminders.py`, `polls_store.py` | Tablas para horarios/tareas/recordatorios/resultados de encuesta. Preservar páginas, fechas, estados y preguntas. |
| Economía y juegos | `economy.py`, `blackjack_store.py`, `roulette.py` | Top en tabla; partidas con encabezados, manos y consecuencias legibles. No forzar todo a tabla. |
| Cooperacha | `cooperacha_image.py`, `cooperacha.py` | Vista previa censurada. Botsky ya tiene flujo propio: auditar paridad visual y entrega, no duplicarlo. |
| Minecraft | `minecraft.py`, `UI_RICA_DOMINIOS.md` | Resumen de paquetes en columnas. Conservar el diagnóstico y recuperación más recientes de Botsky. |
| Microinteracciones | `GUIA_UI_UX_Y_PERSONALIDAD.md` | Estado discreto, resultado primero, errores útiles. Verificar soporte actual de reacción/presencia antes de incorporarlas. |
| Avatar y clips | Guía UI y componentes propios ya portados | Mantener PIP/pausa/reconexión; revisar legibilidad y restos de marca. `avatar-renderer.mjs` aún devuelve `name: 'Zhana'`. |

La investigación anterior sobre «solo texto» de Zhana fue corregida en sus propios
documentos. La referencia vigente sí incluye tablas estructuradas. La evidencia
histórica de aceptación HTTP/tableMetadata no certifica por sí sola el aspecto en
un teléfono actual. Las propuestas estéticas de una guía tampoco prueban que cada
detalle estuviera implementado. Cada requisito llevará origen: **código**,
**evidencia histórica**, **guía** o **mejora nueva**.

La [lámina de diseño](UI_UX_LAMINA_PROPUESTA.svg) ilustra seis muestras sintéticas;
la [matriz de rutas](UI_UX_MATRIZ_RUTAS.csv) permite seguir la cobertura.

Fuentes y hashes se registran en `evidencia/UI-UX-20261107/fuentes.json`. No se han
consultado privados, conversaciones, DB31 o perfiles de Zhana para este plan.

## 3. Reglas del sistema visual

### Jerarquía y composición

- Orden normal: resultado o título útil → contenido → contexto necesario → siguiente acción.
- Un título breve por unidad. Negrita para jerarquía y datos decisivos; cursiva para
  pies; citas para metadatos secundarios. No poner cada línea en negrita.
- Una línea vacía entre opciones y secciones; evitar tanto el bloque apretado como
  mensajes separados para cada frase. Una respuesta breve cabe en una entrega.
- Listas numeradas cuando se elige; tablas cuando se comparan columnas; texto
  normal para una confirmación o dato único. No presentar una tabla vacía.
- Los símbolos de cartas y emojis contextuales siguen siendo válidos. No exigir
  decoración en cada respuesta ni depender solo del color/emoji para explicar estado.
- Mantener nombres, enlaces, cifras y texto literal. Marcar los extractos como vistas
  previas; conservar el contenido completo y una vía explícita para consultarlo.

### Sintaxis y compatibilidad

El renderizador de texto produce los marcadores de WhatsApp para negrita, cursiva,
tachado, monoespaciado, citas y listas. El detalle del soporte se comprueba en la
ruta/cliente actual antes de declararlo aceptado. `**negrita**`, tablas con pipes,
HTML y enlaces Markdown no se envían suponiendo un renderizado universal.

No transformar todo el texto final con expresiones regulares. Un título generado
por el producto y un texto literal del usuario necesitan tratamientos distintos.
Los marcadores presentes en un nombre o una cita no deben escapar de su bloque ni
cambiar datos para «arreglar» el formato. Conservar una representación canónica
íntegra. Si un bloque literal no cabe en texto seguro, ofrecer archivo y vista previa
marcada. Revisar enlaces largos, backticks, asteriscos, RTL y caracteres combinados.

### Identidad, unidades y accesibilidad

- Marca visible Botsky; recorrer leyendas, nombres de archivo, overlays y placeholders.
  No renombrar claves históricas, contratos o recursos privados a ciegas.
- Fechas humanas con zona de la configuración vigente; formato técnico exacto en
  ejemplos copiables. Nunca inventar la zona a partir del idioma o ubicación supuesta.
- Duraciones `m:ss` y `h:mm:ss`; desconocido no equivale a 0. Tamaños con unidad
  definida y consistente; distinguir cuota decimal del proveedor y límites en MiB/GiB.
- Porcentaje solo desde estado medido. En volumen mostrar el valor aplicado, no el pedido.
- Collages con números contrastados y alternativa textual completa. A 320–390 px de
  ancho efectivo deben seguir identificándose opción/fuente/duración; verificar la
  imagen comprimida por el canal, además del original de 1280 px.
- Tablas cortas por defecto, con 2–4 columnas útiles cuando sea posible; dividir por
  sentido, sin quitar campos esenciales para que «quepa». No contar con un ancho
  configurable en el cliente. Nombres largos y lectura con fuente grande son casos obligatorios.

## 4. Videos: recuperar el collage y la ficha de Zhana

**Prioridad máxima de la primera entrega visual**, junto con la limpieza de IDs.

La referencia usa un lienzo de 1280×720, JPEG calidad 88, entre 1 y 6 opciones, recorte
centrado sin deformación y separadores oscuros de 2 px. Distribuciones: 1 pantalla;
2 columnas; 3 con dos arriba y una abajo; 4 en 2×2; 5 con 3 arriba y 2 abajo; 6 en 3×2.
Conservar esta base, parametrizada y con alternativas revisadas si la miniatura
resulta demasiado pequeña en teléfono.

Cada celda muestra número arriba a la izquierda, fuente arriba a la derecha y
duración abajo a la derecha si se conoce. Zhana usa distintivo rosa RGB 225/29/72,
texto blanco y cápsulas oscuras; es referencia estética, no requisito de identidad
inamovible. Tipografía/empaquetado propios, fallback explícito si falta la fuente;
evitar una dependencia obligatoria de una ruta de fuentes del sistema.

La imagen acompaña una lista con el mismo orden:

```text
*Videos · música de prueba*

*1. Concierto de ejemplo*
> 4:12 · Canal de ejemplo · YouTube

*2. Versión acústica de ejemplo*
> 3:48 · Canal de ejemplo · YouTube

_Lista disponible durante 15 minutos._
`/dl elegir 2`
```

Ejemplo de diseño futuro: `/dl elegir 2` es una adaptación propuesta, **no una
sintaxis existente**. Mientras se construye, el presentador debe mostrar únicamente
comandos realmente admitidos. Al publicar una lista con menos opciones, el pie
indica el rango real. El TTL mostrado procede de la vista durable, no de una frase fija.

Requisitos pequeños que forman parte del cierre:

1. El número de la imagen, el de la ficha y la selección apuntan al mismo objeto
   inmutable; la descarga no vuelve a buscar el título. Deduplicar antes de numerar.
2. Título completo retenido; vista previa abreviada a límite editorial explícito.
   Metadatos desconocidos indicados brevemente; no inventar autor/duración.
3. Una miniatura fallida deja una tarjeta con título/fuente y número; fallos parciales
   no cambian el orden ni borran opciones. Si falla el collage entero, la lista sigue útil.
4. Obtener miniaturas mediante la frontera de red propia: validación de destino y
   redirecciones, límites de bytes/píxeles/tiempo, concurrencia acotada y limpieza.
   La implementación histórica `_fetch_thumbnail` no se copia sin revisar esas fronteras.
5. Si la generación de una tarjeta falla, detectar el fallo; no confundir «función
   existente» con «todos los placeholders comprobados». Probar expresamente el autor largo.
6. Caducidad/retención acordes con la vista; no descargar miniaturas de nuevo al
   reenviar un texto de ayuda. Cache por origen/ámbito conforme al dato, sin filtrar privados.
7. La vista se activa solo al completar las partes requeridas. Con imagen aceptada
   y lista incierta no anunciar que toda la selección está disponible.
8. Las fuentes habilitadas siguen su política actual. SoundCloud permanece retirado.
   Búsqueda web genérica no activa búsqueda de videos por interpretar la frase.

## 5. Interacciones: quitar fricción sin perder control

### Identificadores y selección

Eliminar el sufijo global `/estado HASH` de `Store.enqueue`. Los recibos internos
siguen existiendo; se consultan en diagnóstico, no se imponen tras cada respuesta.
Mantener IDs de negocio útiles: nota, tarea, evento o partida. Un token requerido
por una confirmación sensible conserva validez y queda en una instrucción copiable.

Añadir variantes explícitas para el uso habitual: `/dl elegir NUMERO`, `/drive
elegir NUMERO`, `/estado`, `/cancelar`, y operaciones mediante cita propia verificada
cuando corresponda. Son ampliaciones del parser determinista, con sus contratos y
pruebas, no atajos resueltos por Gemini. Las formas con ID siguen compatibles.

- Resolver solo vistas/trabajos propios de mismo actor/chat/instancia/época,
  vigentes y entregados. Varios candidatos → lista corta para elegir; nunca «el último»
  sin comprobar ambigüedad. Distinguir lista de Drive, videos y confirmación.
- Una respuesta citada puede ser una parte intermedia: índice de todos los IDs
  aceptados de la composición hacia el recibo padre. No aceptar citas ajenas o vencidas.
- Mensajes sueltos como `2`, «sí» o «la segunda» no adquieren autoridad por el rediseño.
- Una selección vencida explica «La lista venció; vuelve a buscar» y ofrece el
  comando pertinente, sin reconstruir una elección de otra búsqueda.

### Ayuda y descubrimiento

`/ayuda` muestra categorías cortas; `/ayuda llamada` agrupa iniciar, controlar y
agendar; `/ayuda llamada programar` muestra un ejemplo y opciones pertinentes.
Nombre humano y descripción de una línea; ejemplos con unidades claras. Mostrar
«Solo el dueño» cuando corresponda y explicar «durante una llamada autorizada».
`R9`, `call_authorized`, `LIVE_REQUEST` y detalles de implementación van a la guía
de operador. No ocultar límites o capacidades desactivadas detrás de una ayuda bonita.
La ayuda sale del registro con metadatos editoriales separados; no mantener un
catálogo manual paralelo que se desactualice al añadir comandos.

### Progreso y cierre

Trabajo rápido → resultado directo. Si tarda, una reacción/presencia compatible,
o un aviso breve tras un umbral configurable. Si el canal no soporta reacción,
no simularla con varios mensajes. Actualizar solo ante estados reales; no afirmar
«descargado» mientras sigue en cola. No introducir polling del usuario por ID como
requisito para recibir resultados. Cancelar informa qué se detuvo y qué ya se envió.

Archivo entregado con leyenda suficiente → no añadir otro «Listo». Sticker pedido
→ sticker sin texto de éxito redundante. El usuario confirmó que el sticker actual
funciona: conservar su motor/envío y cambiar solo la presentación necesaria.

## 6. Contratos visuales por herramienta

Todas las filas deben probar éxito, vacío cuando aplique, entrada incompleta,
error, contenido largo y aislamiento. Los números/fechas de las muestras son sintéticos.

| Herramienta | Presentación prevista y detalles obligatorios |
| --- | --- |
| `conversation` | Párrafos breves y jerarquía; tabla tipada solo si ayuda a comparar. Contenido literal intacto. LecturaQR verificada separada del análisis generativo. Fuentes y fallos parciales conservados. |
| `save_note` | «Nota guardada · #N» y vista previa opcional; conservar texto exacto y número útil. |
| `find_notes` | Lista de notas, ID/fecha si disponibles, fragmento marcado, página/total y consulta conservada. Tabla solo si mejora esa lista. |
| `manage_memory` | Qué se guardó/quitó y ámbito; sin prometer borrado de copias históricas. No imprimir estructuras internas. |
| `read_image` | OCR como texto copiable; QR como contenido verificado. No decorar dentro del literal ni abrir automáticamente sus enlaces. |
| `transcribe_media` | Transcripción literal separada de resumen; títulos solo para distinguirlos. Texto largo descargable y continuación explícita. |
| `make_voice` | Nota de voz correcta; leyenda corta si aporta voz/efecto/modo. No duplicar todo el texto hablado. Fallo de voz elegida explícito, sin sustitución silenciosa. |
| `download_media` | Collage+lista numerada+metadatos; formato/calidad/recorte visibles; selección estable; archivo final con título/nombre. Spotify anuncia coincidencia, no equivalencia garantizada. |
| `search_web` | Consulta, opciones con título destacado, fuente, extracto marcado y URL íntegra; aviso único de candidatos no verificados. No duración ni miniatura inventadas. |
| `edit_media` | Archivo final, formato y cambio relevante; avisar recorte/reducción si ocurrió. Nombres legibles; sin narrar procesos internos. |
| `convert_document` | Formato final, páginas/hojas medidas, limitaciones relevantes: imagen por página, OCR ausente o fidelidad parcial. |
| `manage_pdf` | Sesión con cantidad/orden/páginas reales; siguiente comando útil. Reintento distingue motor de entrega y advierte duplicación si incierta. |
| `make_sticker` | Sticker como resultado; petición breve de adjunto cuando falte. Sin `/estado` automático. |
| `send_sticker` | Reacción del catálogo sin texto extra; disponibilidad de opciones claras en ayuda. |
| `manage_reminder` | Confirmación con fecha/hora/zona y texto; tabla de lista: referencia, fecha, estado, vista previa; avisos puntuales legibles. |
| `manage_school` | Tareas por estado/entrega con vistas previas; horario en tabla día/inicio/fin/materia y referencia accesible. Vacío no implica que no haya deberes reales. |
| `manage_poll` | Pregunta fuera de tabla; resultados con opción/respuesta/votos, estado y total. Crear/votar/cerrar distinguidos. No confundir tabla con encuesta interactiva nativa. |
| `manage_drive` | Cuota con disponible/capacidad/usado y ámbito compartido; lista número/nombre/tamaño; exclusiones claras. Archivo con nombre seguro original. |
| `manage_messages` | Vista previa: destinatario verificado, texto literal, adjuntos y efecto; instrucción de confirmación. «Aceptado por el servicio» no equivale a leído. |
| `manage_economy` | Saldo, reservado y disponible distinguidos; daily con importe/espera reales; top en tabla con identidades aptas para el chat, sin teléfonos expuestos. |
| `manage_blackjack` | Encabezado de mesa, apuesta, manos/puntuaciones, turno y comandos válidos. Carta oculta sigue oculta. Cierre distingue devolución, premio bruto y ganancia. |
| `manage_roulette` | Sala, asientos, coste y consecuencias visibles antes de entrar/jugar; resultado con estado confirmado/incierto. No ocultar un efecto de moderación con decoración. |
| `manage_pack` | Categoría/stock/coste/condiciones antes de comprar; entrega privada y fallos parciales diferenciados; sin fingir fotos cuando el stock es 0. |
| `manage_cooperacha` | Previa censurada, categoría/meta/avance/coste, plazo y acción; no filtrar el original en miniatura/caption. Imagen final solo por flujo autorizado. |
| `manage_happy_hour` | Estado/duración/reglas/precios y drops legibles; `/hh reclamar` usa referencia del DROP real; lluvia/airdrop sin mensajes técnicos repetidos. |
| `make_prank` | Explicar alcance ficticio; no afirmar hackeo/moderación real. Mensaje breve y reconocible. |
| `manage_admin` | Objetivo verificado, acción, resultado y próximo paso cuando proceda. Nuclear conserva vista previa, alcance y confirmación íntegros. |
| `manage_minecraft` | Resumen salud/jugadores/mundo observados; tablas de paquetes con nombres reales y distinción instalado/configurado/cargado/desconocido. Backup con tamaño/estado verificados y recuperación explícita. |
| `control_call` | Preparando/marcando/conectada/terminada/incierta; duración y motivo útiles, sin JSON. Ocupado sin revelar interlocutor. No declarar conexión por aceptación de marcado. |
| `manage_conversation` | Modo/pausa/reanudación y vencimiento visibles; explicar efecto sobre respuestas y tareas según contrato real. |
| Núcleo `core` | Ayuda por tarea; estado con descripción humana, cancelación y confirmación claras; IDs operativos bajo solicitud explícita. |
| Adaptación `audiovisual` | Clip actual, lista numerada, pausa/fin/repetición distintos, volumen aplicado, avatar/gestos disponibles y agenda con zona. Ver sección7. |

Matriz completa: `UI_UX_MATRIZ_RUTAS.csv`, una fila por cada ruta y todos sus campos
actuales, con fase, presentador y criterios aplicables. Inventario no equivale a
aceptación: todas las rutas comienzan en **PENDIENTE_IMPLEMENTAR**.

## 7. Audiovisual y superficies fuera del texto

Auditar lo ya portado antes de cambiarlo. Base actual de Botsky:
`avatar-quality.mjs` define video 640×360, avatar 384×384, 20 fps y distancia 1.08;
`video-bridge.cjs` compone PIP y avisos de pausa/reconexión. La guía de Zhana
aporta dirección visual, pero no sustituye comprobación de frames/recepción.

- Conservar encuadre horizontal, cabeza completa y margen; PIP animado en esquina
  inferior izquierda durante clips. No aumentar resolución a costa de voz/movimiento.
- Revisar si los avisos «Pausado», «Pausado mientras hablo» y «Reconectando…» reflejan
  el estado exacto; una sola capa prioritaria, sin tapar cara/subtítulos importantes.
- `resuming` mantiene la composición del clip; `ended` vuelve a avatar; no destello
  de avatar grande mientras `play()` está pendiente. Fin no reinicia automáticamente.
- Fondos, expresiones, gestos y rubor confirman aplicación observada; cambios
  diferidos dicen cuándo ocurrirán. Inventario de capacidades propio, sin prometer
  animaciones de un nombre que el modelo no soporta.
- Labios por audio real de la sesión, animación discreta y retorno neutral; no
  reemplazar el personaje para esconder un fallo de rendimiento.
- Agenda: fecha/hora/zona, modo, duración y estado; no exponer IDs de audio largos
  como título principal. Identificadores técnicos disponibles para operador.
- Reutilizar los avisos durables existentes sin duplicar mensajes. Fallo visual
  no se presenta como caída total de una llamada cuya voz sigue funcionando.

## 8. Arquitectura propuesta

```mermaid
flowchart LR
  A[Dominio y resultado verificable] --> B[Presentador propio por familia]
  B --> C[Documento tipado y versión visual]
  C --> D[Plan inmutable de partes]
  E[Capacidades del transporte] --> D
  D --> F[Outbox propia con CAS y recibos]
  F --> G[Texto / tabla nativa / medio / reacción]
  G --> H[IDs de partes y estado observado]
  H --> I[Selección y seguimiento por ámbito]
```

Módulos propuestos, aún inexistentes: `presentation/models.py`, `theme.py`,
`formatters.py`, `splitter.py`, `presenters/`, `engines/search_collage.py`.
El nombre/ruta se ajustará al implementar; no se importa código de Zhana al arrancar.

- Bloques mínimos: heading, paragraph, literal, quote, numbered_list, native_table,
  media con nombre/caption, notice y next_action. Reacción/presencia con ciclo y
  capacidades separados de las partes de contenido. No un campo libre de destinoHTTP.
- Datos del dominio son autoridad para cifras/estado. Gemini puede producir contenido
  y tablas tipadas de su respuesta, nunca decidir comandos, permisos, rutas o envíos.
  La maqueta de herramientas es determinista, sin llamada extra a un modelo.
- `Result` conserva status/code/data y representación canónica. El plan visual
  durable conserva versión, orden, hashes y partes antes del primer envío. Un
  reinicio o cambio de tema no recompone una entrega parcialmente enviada.
- Ampliar `DeliveryPart`/outbox con tipo y payload tipado, migración propia siguiente
  a esquema 18 tras preflight real. Diseñar migración compatible y probar conDB
  sintética de la versión anterior; no crear un segundo journal que pueda divergir.
- Reutilizar aceptación por partes, leases/CAS, cancelación y bloqueo de repetición.
  La migración 030 de Zhana solo es referencia; no se copia su esquema entero.
- Tabla validada antes dePOST: rectangularidad, celdas/título/filas/columnas/tamaño.
  Sus límites locales históricos1–20 columnas, 1–100 filas y 60 KiB son un punto de
  partida que debe contrastarse con el transporte instalado, no límites oficiales universales.
- Capacidades obtenidas por configuración explícita y comprobación de instalación
  de solo lectura; no hacer un envío de tanteo a un usuario. Componer una alternativa
  textual antes del despacho cuando no haya soporte. Ante timeout: incierto, sin
  enviar una alternativa que pueda duplicar contenido. Rechazos concluyentes se
  gestionan con recibo explícito, sin cambiar silenciosamente el plan ya enviado.
- Separar por bloques/párrafos, manteniendo marcadores y contenido literal. Una
  URL o celda indivisible sobredimensionada necesita representación alternativa
  marcada; no cortar en mitad y fingir que sigue íntegra.
- Nombres seguros derivados del título verificado; captions útiles donde se soporten.
  Nota de voz/sticker no se convierten en documento por uniformar la presentación.
- Reintento de entrega usa las partes originales; no vuelve a generar collage,
  descargar, apostar, cobrar o marcar una llamada. Retención protege recursos activos.

## 9. Estados, errores y microtexto

| Estado comprobado | Comunicación prevista |
| --- | --- |
| Falta adjunto | «Adjunta la imagen aquí o responde al mensaje que la contiene.» Plazo real de espera, sin hash. |
| En cola | «Lo estoy preparando» solo si ese estado es real y necesita aviso; sin porcentaje ficticio. |
| Sin coincidencias | «No encontré resultados con esos términos.» Conservar consulta y alternativa pertinente. |
| Servicio no disponible | Explicar qué no pudo hacerse y un siguiente paso válido; código técnico en diagnóstico. |
| Resultado parcial | Entregar parte comprobada y explicar lo que falta; no un éxito genérico. |
| Entrega incierta | «No pude confirmar si llegó. Revisa antes de reenviarlo.» Sin reintento automático. |
| Permiso insuficiente | «Esta acción está disponible solo para el dueño» o condición exacta del dominio. |
| Cancelación efectiva | «Cancelado.» Si ya salió algo: explicar qué quedaba y qué ya fue enviado. |
| Acción sensible | Vista previa con destino, coste, consecuencias y comando de confirmación vigente. |

El catálogo de mensajes se mantiene junto a códigos estables. No esconder límites
de proveedor, galería vacía o falta de permisos con una frase amistosa engañosa.
La cercanía se expresa mediante claridad y ritmo; el encargo no cambia la
personalidad/voz completa ni introduce apodos automáticos.

## 10. Ejecución por fases y dependencias

| Fase | Dependencias | Entrega revisable | Cierre obligatorio |
| --- | --- | --- | --- |
| V0 · Referencia y contrato | Este encargo | Plan, matriz154 rutas, fuentes con hashes, lámina de diseño | Inventario automático conciliado; referencias distinguen código/guía/evidencia. **Completada en este cierre documental.** |
| V1 · Base visual y ruido | V0 | Modelos/presentador, splitter, ayuda, IDs fuera del flujo, errores comunes | Ningún HASH/R9/permiso interno automático; textos literales y comandos conservados; no regresión de entrega. |
| V2 · Videos y búsquedas | V1; soporte de listas durables | Collage1–6, metadatos, fichas web, miniaturas acotadas, selección corta explícita | Imagen/lista/selección coinciden; pruebas de fallos parciales; SoundCloud sigue retirado. |
| V3 · Tablas y entrega enriquecida | V1; migración y soporte observados | Tipo tabla+transporte+plan durable+índice de citas | Validación y recuperación sin duplicados; aceptación de partes completa antes de activar vistas. |
| V4 · Organización y archivos | V3; V1 | Notas/memoria/OCR/QR/PDF/voz/escuela/encuestas/Drive/recados | Campos, páginas, destinos y advertencias completos; nombres/captions medidos. |
| V5 · Comunidad y operación | V3; V1 | Economía/juegos/packs/cooperachas/HH/admin/Minecraft/modos | Costes/reglas/confirmaciones intactos; estados desconocidos explícitos; vistas censuradas seguras. |
| V6 · Audiovisual | V1; inventario de capacidades propio | Chat de llamada/agenda/clips/avatar, overlays/marca/PIP | Estados y frames ligados a la sesión correcta; voz no degradada; cero llamadas por automatismo de formato. |
| V7 · Revisión global y despliegue | V2–V6 | Catálogo visual, matriz cerrada, migración/despliegue y reversión | Validación técnica y estado visual separados; solo recargar servicios propios bajo alcance vigente. |

V2 y V3 pueden avanzar como ramas de trabajo tras V1; integración secuencial y
selectiva. El collage entra temprano por su valor para el propietario. Ninguna
fase se cierra diciendo «el presentador existe» si sus rutas siguen en texto anterior.

Cada cierre conserva evidencias, actualiza matriz y relevo y hace commit selectivo.
No cambiar resultados históricos de campañas. No ejecutar herramientas con efectos
para obtener una captura. El plan no solicita reanudar R10 ni vuelve a imponerlo
como gate de la transición ya realizada. Producción se mantiene hasta desplegar
código verificado; verificación humana pendiente se informa sin inventarPASS.

## 11. Aceptación y revisión minuciosa

### Catálogo de muestras

Crear fixtures propios para las154 rutas, agrupando estados comunes sin multiplicar
pruebas idénticas. Cada muestra conserva entrada explícita, datos de dominio,
documento tipado, partes, representación de texto y metadatos visuales. Muestras
representativas: video 1/2/3/4/5/6, miniatura rota, búsqueda vacía, tabla larga,
ayuda llamada, nota conMarkdownliteral, QR con comando, OCR largo,PDF por imágenes,
saldo, blackjack, ruleta con consecuencia, cooperacha censurada, mods desconocidos,
Drive compartido, llamada ocupada y agenda con zona. Sin datos reales del propietario.

### Casos y puertas de calidad

1. **Exactitud:** campos obligatorios idénticos al resultado verificado, precio,
   destino, fecha/zona, importe, unidad, ID de negocio y condiciones sin pérdidas.
2. **Composición:** títulos largos, URLs largas, Markdownliteral, emojis/acentos/RTL,
   singular/plural, nombres vacíos,0 resultados y 1 resultado, límites exactos y exceso.
3. **Collage:** layouts1–6sin huecos/deformación, numeración inmutable, metadatos
   desconocidos, sin fuentes, imágenes corruptas, límite de píxeles/bytes, timeout,
   redirección y destino privado; inspección del JPEG final además de dimensiones.
4. **Entrega:** duplicado, reinicio tras parte aceptada, timeout de tabla/collage,
   cancelación durante envío, cita de parte intermedia, TTL, actor ajeno y dos vistas
   simultáneas. Ninguna publicación/confirmación antes de la barrera de entrega.
5. **Accesibilidad:** modo claro/oscuro, fuente grande, ancho estrecho, texto
   alternativo completo, orden de lectura y cifras legibles en la imagen comprimida.
6. **Compatibilidad:** cliente Android yWeb mediante observación real cuando esté
   disponible; transporteHTTP y eco no se etiquetan como aceptación visual.
7. **Rendimiento:** medir latencia/bytes antes/después con fixtures iguales; miniaturas
   con presupuesto, render acotado yfallback puntual; no bloquear otros chats.
8. **Operación:** compatibilidad de esquema, respaldo consistente antes de migrar,
   preservación de planes pendientes, volver al código anterior sin restaurar una DB
   antigua sobre efectos nuevos. Activación de capacidades por etapa y diagnóstico.

Estados separados en la matriz: IMPLEMENTADO, LOCAL_VERIFICADO,
TRANSPORTE_VERIFICADO, VISUAL_OBSERVADO o BLOQUEADO/NO_PROBADO. Una muestra SVG
es una intención de diseño, no una captura de WhatsApp ni evidencia de transporte.

### Métricas de cierre

- 154/154 rutas clasificadas y revisadas;32/32 raíces con presentador o adaptación
  explícita. Documentar toda ruta nueva incorporada durante el trabajo.
- Cero sufijos técnicos automáticos; cero marcadores de implementación en ayuda.
- Misma selección en imagen/texto/efecto en todos los fixtures de búsqueda.
- Cero cambios de costes/permisos/consentimiento ocasionados por presentación.
- Cero duplicados ante los fallos inyectados; toda incertidumbre permanece visible.
- Medir mensajes por tarea, longitud y latencia: reducir ruido sin omitir el resultado
  ni crear entregas extra para cada adorno. Comparar con el baseline, no prometer cifras aún no medidas.
- Registro explícito de qué se ve bien en cliente real y qué solo está comprobado localmente.

## 12. Primer corte concreto

Comenzar V1 por la eliminación del sufijo global de estado y la ayuda de llamadas,
apoyadas en un presentador común; construir a continuación V2 con el collage y las
fichas de video. Implementar las tablas nativas en V3 sobre la outbox propia y
extender los dominios V4/V5. Revisar V6 con los componentes portados antes de
modificarlos. No ejecutar todo como una sustitución masiva sin cierres verificables.

La prioridad visual es explícita: un comando que funciona pero produce una
respuesta confusa aún no cumple el contrato de experiencia de este plan.
