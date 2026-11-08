# Auditoría Exhaustiva de Frontend UI/UX: Experiencia Visual, Interacción Conversacional e Inventario de Textos en Botsky

**Fecha de emisión:** 07 de noviembre de 2026  
**Ámbito de auditoría:** Interfaz de usuario y experiencia conversacional (UI/UX) para WhatsApp  
**Módulos auditados:** `src/botsky/frontend/` y `src/botsky/presentation/`  
**Documentos y contratos de contraste:** `remodelacionbotsky.md`, `docs/PLAN_MODERNIZACION_VISUAL_UI_UX.md`, `docs/UI_UX_MATRIZ_RUTAS.csv`, `docs/evidencia/UI-UX-CONT-20261107/`  
**Modo de auditoría:** Exclusivamente de solo lectura (Read-Only). No se modificó ningún archivo de código fuente (`*.py`) ni de configuración del repositorio.

---

## 1. Resumen Ejecutivo

### 1.1 Objetivos y Alcance de la Auditoría
El presente informe documenta la auditoría exhaustiva de Frontend, Presentación y Experiencia de Usuario (UI/UX) llevada a cabo sobre el asistente conversacional **Botsky** para WhatsApp. El propósito fundamental de esta evaluación es auditar integralmente «cómo se ve» y «cómo se siente» el producto en dispositivos móviles reales, evaluar la coherencia de la personalidad conversacional frente a los planes maestros de remodelación, relevar exhaustivamente todos los textos de relleno, placeholders y fórmulas desalineadas, y trazar una hoja de ruta jerarquizada de optimización sin alterar el código fuente del repositorio.

El alcance comprende:
1. **Frontend Conversacional (`src/botsky/frontend/`)**: Modelado de prompts de sistema (`prompts.py`), contratos editoriales y etiquetas (`editorial.py`, `commands/editorial.py`), ciclo de vida del trabajador asíncrono y mensajes de error/fallback (`worker.py`), contexto y gestión de confirmaciones (`context.py`), y servicio de inferencia (`service.py`).
2. **Capa de Presentación (`src/botsky/presentation/`)**: Sistema de bloques tipados y renderizado (`__init__.py`), partición de mensajes y control de desbordamiento a archivos (`splitter.py`), maquetación de planes de entrega (`plan.py`), tablas nativas y fallbacks (`table.py`), catálogo de microtextos de error (`errors.py`), formateo de búsquedas y fichas de video/web (`search.py`), presentadores de dominios de negocio (`domains.py`, `community.py`, `audiovisual.py`, `minecraft.py`), motores de ayuda (`help.py`), y el adaptador de lenguaje natural (`natural.py`).
3. **Contraste con Planes Maestros y Evidencia**: Verificación cruzada contra las 155 rutas declaradas en `docs/UI_UX_MATRIZ_RUTAS.csv`, las directrices del plan supremo `remodelacionbotsky.md`, las especificaciones estéticas de `docs/PLAN_MODERNIZACION_VISUAL_UI_UX.md` y los registros empíricos del benchmark de 776 muestras en `docs/evidencia/UI-UX-CONT-20261107/`.

### 1.2 Metodología y Fuentes Analizadas
La auditoría se ejecutó mediante una inspección estática y dinámica multidimensional:
* **Inspección de código línea a línea**: Identificación de strings textuales, condiciones de renderizado, contratos de error, expresiones regulares y estructuras de datos de presentación.
* **Trazabilidad de contratos**: Análisis de la interacción entre el clasificador del frontend (`GLM`/`Qwen`), el motor de ejecución del backend (`Store`/`jobs`) y la capa de presentación que proyecta los resultados hacia WhatsApp.
* **Evaluación de ergonomía móvil**: Análisis del comportamiento de los mensajes en pantallas móviles estrechas (ancho estándar de 320 px a 390 px), contemplando quiebres de línea, saturación de previsualizaciones y accesibilidad.
* **Revisión de evidencia empírica**: Examen de los logs de ejecución (`file-presentation-tests.log`, `revision-hallazgos.md`, `cierre.md`, `benchmark.json`) generados durante los cortes de desarrollo previos.

### 1.3 Diagnóstico General Sintético: «Cómo se ve y cómo se siente» Botsky hoy
La conclusión global de la auditoría es categórica: **Botsky posee una infraestructura interna extraordinariamente robusta, atómica y segura en su persistencia y despacho; sin embargo, su experiencia de usuario en WhatsApp se encuentra severamente degradada por dos patologías complementarias:**

1. **«Cómo se ve» (Déficit visual y maquetación de consola)**:
   La interfaz visual carece de la riqueza y el cuidado de un producto de mensajería moderno. Los mensajes se emiten como volcados austeros de terminal Unix: casi no se emplean emojis funcionales, las tablas se fuerzan a bloques de código monoespaciado que se desalinean catastróficamente en pantallas verticales, cualquier fragmento con acentos graves o código se desvía agresivamente a archivos `.txt` adjuntos (`"Contenido literal.txt"`), las búsquedas saturan la pantalla con múltiples URLs crudas que disparan previsualizaciones desordenadas, y los marcadores de acción exponen comodines técnicos en mayúsculas como `NUMERO` o `CANTIDAD`.
2. **«Cómo se siente» (Personalidad hiperdefensiva y peritaje legalista)**:
   El bot suena como un perito informático o un actuario judicial en lugar de un asistente útil y empático. Prácticamente cada respuesta exitosa viene acompañada de descargos de responsabilidad legalistas y deslindes de transporte (*«la aceptación no acredita percepción humana»*, *«entrega aún no comprobada»*, *«no se promete borrar copias históricas»*, *«incertidumbre la conserva sin reenviar»*). Esto viola de manera directa el principio rector estipulado en `remodelacionbotsky.md:647` (*«Distinguir aceptación del envío de recepción/lectura cuando sea relevante, sin convertir cada respuesta normal en un informe de transporte»*). Además, el frontend conversacional fue programado con un sesgo 80% punitivo («no hagas», «no inventes», «no tienes resultados»), lo que deriva en respuestas secas, robóticas (*«De acuerdo.»*) o errores con vocabulario interno de ingeniería (*«La interpretación caducó»*, *«La cuota de las cuentas configuradas está agotada»*).

---

## 2. Diagnóstico de UI/UX: Experiencia Visual y Sensación Conversacional

### 2.1 Experiencia Visual: «Cómo se ve»

#### A. Legibilidad en Pantallas Móviles (320–390 px)
WhatsApp es consumido predominantemente en teléfonos inteligentes cuyas pantallas ofrecen entre 320 px (dispositivos compactos como iPhone SE) y 390 px (gama media/alta como iPhone 13/14 o Samsung Galaxy estándar) de ancho efectivo. En estas dimensiones, el ancho de columna equivale aproximadamente a 32–38 caracteres monoespaciados o 45–55 caracteres proporcionales.
* **El problema del límite de 3.500 caracteres (`splitter.py:37`)**: El divisor de mensajes utiliza un límite de 3.500 unidades UTF-16 antes de fragmentar. Un mensaje de 3.500 caracteres en WhatsApp móvil genera una burbuja gigantesca que abarca entre 6 y 9 pantallas completas de desplazamiento vertical («muro de texto»), imposibilitando una lectura ágil.
* **Ausencia de burbujas múltiples y cadencia**: No existe lógica de envío secuencial en dos burbujas coordinadas (por ejemplo: primero una confirmación breve y luego el detalle de la consulta).

#### B. Tipografía, Jerarquía y el Bug Silencioso de Negritas (`presentation/__init__.py:16`)
La jerarquía tipográfica es deficiente debido a una condición restrictiva en el formateador de bloques:
```python
# src/botsky/presentation/__init__.py:16
if self.kind == "heading" and not any(c in self.text for c in "*_`\n"):
    return "*" + self.text + "*"
```
Si un título generado por el sistema contiene cualquier carácter de formato (`*`, `_`, `` ` ``) o un salto de línea (`\n`), la condición se evalúa como falsa y el encabezado se renderiza silenciosamente como texto plano. Esto destruye la jerarquía visual del mensaje, haciendo que el título principal sea indistinguible del cuerpo de texto.
Por otro lado, los bloques de tipo `notice` devuelven texto plano sin ningún formateo (`self.text`), ignorando la recomendación del plan maestro de emplear cursivas (`_texto_`) para pies y notas secundarias (`PLAN_MODERNIZACION_VISUAL_UI_UX.md:69-70`).

#### C. Carencia de Emojis Funcionales y Divisores Visuales
La interfaz actual es 100% monocromática y árida. Con la única excepción de los palos de las cartas en el minijuego de Blackjack (`domains.py:592`), el bot ha proscrito totalmente el uso de emojis contextuales.
* No se usan divisores visuales limpios (como líneas punteadas o viñetas destacadas). Toda separación depende únicamente de dobles saltos de línea (`\n\n`).
* La ausencia de iconos funcionales universales (`✅` para éxito, `❌` para error, `⏱️` para tiempos y plazos, `📄` para documentos, `🔍` para búsquedas, `🔔` para recordatorios) priva al usuario de anclas visuales rápidas para escanear el contenido en una fracción de segundo.

#### D. Saturación Visual por URLs Crudas (`search.py:71`)
En la búsqueda de videos y búsquedas web, `search.py` añade un bloque de párrafo con la URL completa para cada resultado:
```python
blocks.append(Block("paragraph", choice["url"]))
```
En WhatsApp para móviles, volcar de 3 a 6 URLs completas (de 60 a 120 caracteres cada una) provoca que el cliente intente generar tarjetas de previsualización web pesadas, ocupando un área vertical desproporcionada y desordenando el flujo del chat. El plan original establecía asociar la acción al número ordinal, manteniendo las URLs contenidas o como enlaces limpios.

#### E. Renderizado Deficiente de Tablas Fallback (`table.py:51-60` y `plan.py:168-174`)
Cuando el canal no admite tablas nativas enriquecidas, el sistema recurre al método `NativeTable.fallback()`:
```python
# table.py:51-60
def fallback(self):
    return "\n\n".join(
        [self.title]
        + ["\n".join(f"{label}: {value}" for label, value in zip(self.headers, row))
           for row in self.rows]
    )
```
Al integrarse en `plan.py:171`, este texto con saltos de línea se envuelve forzosamente en un bloque de código literal (`Block("literal", table.fallback())`), lo que provoca que en WhatsApp se renderice dentro de triple acento grave (```` ``` ```` monoespaciado). En pantallas móviles verticales, los bloques de código monoespaciado no se ajustan automáticamente, sufren quiebres de línea antiestéticos y se muestran con fondo gris oscuro, asemejándose a un volcado de error de terminal en lugar de una tarjeta estructurada legible.

#### F. El Desvío Invasivo a Archivos `.txt` Adjuntos (`splitter.py:70` y `plan.py:76-88`)
Uno de los problemas de UX más graves detectados radica en la función `needs_file()`:
```python
# splitter.py:70
def needs_file(text, limit=3500):
    return (
        "```" in text
        or any(units(word) > limit for word in text.split())
        or any(char in text for char in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
    )
```
La condición `"```" in text` intercepta **cualquier mensaje que contenga un bloque de código markdown**. Cuando esto ocurre, `plan.py:77-88` suprime completamente el texto del cuerpo del chat y envía en su lugar:
> *«El contenido completo está en el archivo de texto adjunto; conserva todos los caracteres.»*
junto con un archivo `.txt` adjunto llamado `"Contenido literal.txt"`.  
**Impacto en la experiencia:** Si un usuario solicita a Botsky un ejemplo breve de código Python de 4 líneas o una fórmula matemática formateada, el bot censura la respuesta en el chat y obliga al usuario a descargar un archivo `.txt`, buscar una app para abrirlo y leer 50 bytes de texto. Esto rompe totalmente la fluidez de una conversación en WhatsApp.

---

### 2.2 Sensación Conversacional: «Cómo se siente»

#### A. Peritaje Legalista y Deslindes Hiperdefensivos
El aspecto más disonante de Botsky es su tono editorial en los mensajes de confirmación y estado de dominio. Los módulos `domains.py`, `community.py`, `audiovisual.py`, `minecraft.py` y `errors.py` están plagados de fórmulas de descargo de responsabilidad redactadas con léxico judicial y pericial:
* Al programar un recordatorio: *«Aviso pendiente; entrega aún no comprobada.»* (`domains.py:183`).
* Al borrar recuerdos en memoria: *«En este chat; no se promete borrar copias históricas.»* (`domains.py:215`).
* Al enviar un recado a un contacto: *«Aceptado por el servicio no acredita lectura. Si una parte es incierta, revisa antes de repetir.»* (`domains.py:571`).
* Al programar una llamada: *«La programación no acredita una llamada conectada ni recepción humana.»* (`domains.py:750`).
* Al ejecutar una acción de moderación comunitaria: *«La aceptación no acredita percepción humana.»* (`community.py:130`).
* Al comprar un pack de fotos con XP: *«Rechazo conocido devuelve su parte; incertidumbre la conserva sin reenviar.»* (`community.py:23`).
* Al consultar el servidor de Minecraft: *«Contenedor activo no equivale a juego disponible ni a paquetes cargados.»* (`minecraft.py:136`).
* Al fallar un escaneo de código QR: *«No pude decodificar un QR. Esto no demuestra que la imagen no contenga uno.»* (`errors.py:25`).
* Al fallar una consulta de búsqueda web: *«No pude consultar el buscador. No lo interpreto como una búsqueda sin resultados.»* (`errors.py:18`).

**Violación de la directriz maestra:** El plan supremo de Botsky advirtió explícitamente en `remodelacionbotsky.md:647`:
> *«Distinguir aceptación del envío de recepción/lectura cuando sea relevante, sin convertir cada respuesta normal en un informe de transporte.»*

La implementación actual ignoró por completo la segunda mitad de esta directriz: convirtió **todas las respuestas cotidianas en informes de transporte y peritaje forense**, generando desconfianza, frustración y frialdad en el usuario final.

#### B. Vocabulario Técnico Interno y Exposición de Arquitectura
Cuando ocurren fallos o excepciones, los textos exponen sin pudor conceptos de ingeniería de software, arquitectura de microservicios y cuotas de APIs:
* *«La interpretación se interrumpió.»* (`worker.py:33`) $\rightarrow$ Emplea el término interno «interpretación».
* *«La interpretación caducó; envía una petición nueva.»* (`worker.py:65`) $\rightarrow$ Jerga de deadline y tareas asíncronas.
* *«La cuota diaria de las cuentas configuradas está agotada. La interpretación volverá a estar disponible cuando el proveedor renueve la cuota.»* (`worker.py:71`) $\rightarrow$ Expone el pool de cuentas de LLMs y contratos de proveedores.
* *«La cuenta elegida agotó su cuota. Puedes enviar la petición de nuevo para usar otra cuenta disponible.»* (`worker.py:71`) $\rightarrow$ Revela la rotación interna de credenciales.
* *«La propuesta no es válida.»* (`worker.py:80`) $\rightarrow$ Alude a la clase interna `ActionRequest`.
* *«El cliente de descarga no está disponible para esta fuente.»* (`errors.py:5`) $\rightarrow$ Filtra componentes de backend (`yt-dlp` wrapper).

#### C. Respuestas Rígidas y Ausencia de Cortesía Conversacional
El frontend trata la conversación como un inconveniente. Cuando el usuario decide no realizar ninguna acción (por ejemplo, al responder «no, gracias» o cancelar un flujo), `worker.py:98` emite:
> *«De acuerdo.»*

Es una respuesta telegráfica, seca y distante. No hay frases amables de cierre (*«Entendido. Si necesitas algo más, aquí estaré»*), ni preguntas de seguimiento guiadas.

---

## 3. Auditoría Detallada de Presentación e Interacción Conversacional (R1)

### 3.1 Coherencia del Tono Editorial y Persona Conversacional
Al comparar `src/botsky/frontend/prompts.py` y `remodelacionbotsky.md:81-83`, se evidencia una profunda contradicción doctrinal:
* **El plan maestro ordenaba**:
  > *«La IA puede hablar antes de ejecutar: saludar, explicar brevemente capacidades y formular preguntas. No se reduce a un clasificador invisible con frases rígidas.»*
* **La implementación real en `prompts.py:2-6` impone**:
  > *«Eres el frontend conversacional de Botsky en español. Usa exactamente una función... No ejecutas ni afirmas haber ejecutado acciones. El backend valida, ejecuta y entrega sin devolverte resultados. No inventes referencias, archivos ni permisos.»*

El 80% del prompt del sistema está compuesto de prohibiciones punitivas. En la definición de herramientas (`prompts.py:21`), `reply` se describe como:
> *`'reply': 'Solo charla breve o saludo. Nunca afirma que una acción fue realizada; no guarda, busca ni ejecuta.'`*

No existe una sola directriz propositiva que enseñe al modelo cómo dar la bienvenida, cómo transmitir cordialidad, cómo estructurar opciones de manera amigable o cómo asistir al usuario en WhatsApp. La IA fue confinada al rol de un clasificador de seguridad paranoico.

### 3.2 Formato Visual de Mensajes en WhatsApp
`remodelacionbotsky.md:356-357` estableció límites editoriales muy claros:
* Respuestas breves de conversación: **hasta 1.200 caracteres**.
* Preguntas de aclaración: **hasta 300 caracteres**.
* Máximo de opciones simultáneas: **hasta 6 opciones**.
* Separación: **una línea vacía** entre secciones y opciones.

**Brecha en frontend**: El esquema de validación (`prompts.py:24` y `service.py:50`) fija un límite técnico crudo de `maxLength: 2000`, pero **nunca se le informa al LLM en el prompt del sistema sobre estos límites ni sobre el uso de negritas o numeración**. Como resultado, cuando el modelo genera preguntas de aclaración (`clarify`), tiende a escribir párrafos largos y desestructurados en texto plano, sin negritas (`*opción*`) ni listas numeradas (`1. `, `2. `).

### 3.3 Flujos de Ayuda (`help.py`)
En `src/botsky/presentation/help.py` coexisten dos enfoques con deficiencias marcadas:
1. **Ayuda CLI (`render_help`)**:
   - Agrupa los comandos en categorías fijas concatenadas con puntos flotantes en una sola línea (`/buscar · /dl · /ia · /voz · /transcribir · /ocr · /qr`), lo que produce cortes de línea antiestéticos y aleatorios en pantallas de 320 px.
   - En la ayuda detallada de parámetros (`help.py:93-101`), se filtran descripciones de tipos de datos del código fuente ininteligibles para el usuario común:
     > *«duracion: entero con unidad s, m, h o d; ejemplo 30s. Rango: 1–3600 segundos. Por defecto: 30 segundos.»*
   - Si el comando no existe (`help.py:45`), despacha un mensaje cortante: *«Comando desconocido. Usa /ayuda.»*
2. **Ayuda Natural (`render_natural_help`)**:
   - Presenta ejemplos naturales útiles (`«Guarda una nota: comprar pan»`), pero impone una poda artificial: si la consulta coincide con varias familias, solo muestra las dos primeras (`families[:2]`, línea 137), descartando el resto sin advertir al usuario que existen más opciones disponibles.
   - Cierra con una frase burocrática (`help.py:145`): *«Las acciones sujetas a confirmación conservan su vista previa.»*

### 3.4 Gestión de Errores (`errors.py` y `worker.py`)
El diccionario centralizado de errores (`presentation/errors.py:3-26`) presenta tres problemas estructurales:
1. **Fuga de nombres de configuración interna**: Errores como `tts_not_configured`, `gemini_not_configured`, `downloads_not_configured` informan al usuario que la función «no está configurada», revelando detalles de despliegue de la VPS.
2. **Recomendaciones que obligan a usar sintaxis CLI**: Ante fallos en parámetros, sugiere *«Consulta /ayuda dl»* (línea 15) o *«Consulta /ayuda editar»* (línea 24), contradiciendo el objetivo de ofrecer una interfaz en lenguaje natural.
3. **Ausencia de recuperación guiada**: No se ofrece una alternativa inmediata (por ejemplo: si falla una descarga de video, ofrecer la búsqueda de la versión en audio o sugerir reformular los términos de búsqueda).

### 3.5 Búsqueda y Cotizaciones (`search.py`, `quotes.py`, `plan.py`)
* **Fichas de búsqueda de video (`search.py:46-92`)**:
  - Además de la saturación por URLs crudas, el bloque de vigencia (`search.py:78-85`) emite sellos de tiempo excesivamente técnicos:
    > *«Vigencia máxima: 14:59 desde la preparación. Vence: 2026-11-07 16:30:00 · America/Mexico_City. Opciones 1–6.»*
    Esto genera ruido visual. Debería formularse como: *«⏱️ Válido durante 15 minutos (hasta las 4:30 p.m.).»*
  - Los llamados a la acción (`next_action`, líneas 89-91) se emiten envueltos en comillas invertidas con comodines técnicos sin rellenar:
    > `` `Título y autor completos: /dl detalle NUMERO` ``  
    > `` `/dl elegir NUMERO` ``  
    Al tocar estos bloques en WhatsApp para copiarlos, el usuario copia la palabra `NUMERO`, viéndose obligado a editar el texto en el teclado móvil.
* **Búsqueda web (`search.py:99-127`)**:
  - Incluye un descargo legal innecesario al pie: *«Resultados candidatos. No se han abierto ni verificado las páginas completas.»*
  - Si el extracto (`snippet`) contiene asteriscos o saltos, se encierra en bloque literal (`literal`), rompiendo la coherencia de la tarjeta.
* **Citas (`quotes.py:6-14`)**:
  - Las citas vinculan de forma determinista al mensaje padre en SQLite (`own_delivered_parent`) con una ventana de 24 horas. Sin embargo, si la cita ha expirado, el bot emite un error plano sin explicar al usuario que han pasado más de 24 horas desde el mensaje original.

### 3.6 Adaptación en Lenguaje Natural (`natural.py`)
El módulo `src/botsky/presentation/natural.py` adapta mensajes para el modo conversacional. Sin embargo:
* `NEXT_ACTIONS` (líneas 8-24) solo cuenta con 15 mapeos. Comandos como `/tarea archivo`, `/hh reclamar`, `/coop aportar` o `/ayuda` no tienen traducción y se vuelcan en texto crudo como comandos CLI en la conversación.
* Las respuestas del diccionario `MESSAGES` (líneas 26-48) conservan asperezas:
  - *«La vista previa no está disponible, no es tuya o venció. Pide una nueva.»* (línea 42).
  - *«El borrador venció. Prepara el recado de nuevo para revisarlo antes de enviar.»* (línea 43).

---

## 4. Contraste con Planes Maestros y Matriz de Rutas

### 4.1 Análisis de las 155 Rutas de `docs/UI_UX_MATRIZ_RUTAS.csv`
La matriz de rutas documenta **155 rutas operativas** divididas en 34 familias y asignadas a 5 fases de modernización visual:

```
Distribución de las 155 rutas por fase de modernización:
┌────────┬──────────────────────────────────────────┬──────────────┐
│ Fase   │ Enfoque funcional                        │ N.º de Rutas │
├────────┼──────────────────────────────────────────┼──────────────┤
│ V1     │ Núcleo (/ayuda, /estado, /cancelar, /ok) │      4       │
│ V2     │ Videos, búsquedas y descargas            │      9       │
│ V4     │ Organización, notas, PDFs, Drive, voz    │     54       │
│ V5     │ Comunidad, economía, juegos, Minecraft   │     67       │
│ V6     │ Audiovisual, avatar, llamadas y agenda   │     21       │
└────────┴──────────────────────────────────────────┴──────────────┘
Total: 155 rutas
```

Al cruzar los contratos declarados en la matriz contra la implementación real del frontend, se descubrieron divergencias funcionales críticas:

```
+-----------------------------------+-----------------------------------+------------------------------------+
| Dimensión en la Matriz            | Comportamiento Declarado          | Brecha en Código Actual            |
+-----------------------------------+-----------------------------------+------------------------------------+
| Confirmaciones Sensibles          | 9 rutas requieren confirmación    | context.py:12-18 solo mapea 5      |
| (/confirmar, /recado, /pack,      | obligatoria: recados, nuclear,    | flujos en CONFIRMATIONS. Rutas     |
| /ruleta, /pdf)                    | packs, memoria, ruleta y reintento| como ruleta y reintento de PDF     |
|                                   | PDF (confirmación != 'none').     | carecen de soporte conversacional. |
+-----------------------------------+-----------------------------------+------------------------------------+
| Operaciones con Adjuntos          | 10 rutas exigen adjunto obligatorio| prompts.py:52-55 solo instruye     |
| (/sticker, /ocr, /qr, /editar,    | (sticker, ocr, qr, transcribir,   | clarify para 'convertir'. En OCR o |
| /transcribir, /pdf iniciar)       | editar, pdf iniciar/agregar, etc.)| sticker no se pide adjunto guiado. |
+-----------------------------------+-----------------------------------+------------------------------------+
| Consultas de Búsqueda con Filtros | /notas y /buscar usan 'query'     | prompts.py solo enseña             |
| (/notas, /buscar)                 | como parámetro principal.         | nota.guardar con 'text'. Riesgo de |
|                                   |                                   | proponer 'text' y fallar schema.   |
+-----------------------------------+-----------------------------------+------------------------------------+
| Resúmenes Operativos              | 155 rutas con propósitos          | 153 de 155 comandos tienen         |
| en el Catálogo                    | funcionales diferenciados.        | spec.summary == "" (98.7% omisión).|
+-----------------------------------+-----------------------------------+------------------------------------+
| Nombres de Campos en Esquemas     | 73 campos únicos de entrada.      | 55 campos sin traducir en          |
|                                   |                                   | FIELD_LABELS (inglés expuesto).    |
+-----------------------------------+-----------------------------------+------------------------------------+
```

#### Detalle de las brechas críticas identificadas:
1. **Desconexión en Confirmaciones de Ruleta y Reintentos PDF**:
   La matriz documenta que `/ruleta entrar ROOM_ID`, `/ruleta jugar ROOM_ID` y `/pdf reintentar ID [--confirmar-incierto]` son operaciones de riesgo que exigen confirmación sensible. No obstante, `src/botsky/frontend/context.py:12-18` únicamente reconoce en su diccionario `CONFIRMATIONS`:
   * `'message_preview'`, `'nuclear'`, `'pack_offer'`, `'memory_forget_all'` y `'delivery_retry'`.  
   Si un usuario en un grupo participa en una ruleta y responde «sí, juego», el frontend conversacional no puede asociar la confirmación y obliga al usuario a recurrir a la sintaxis CLI `/ruleta jugar <ROOM_ID>`.
2. **Omisión Masiva de Resúmenes Operativos (`spec.summary` vacío en 153 comandos)**:
   En `src/botsky/frontend/editorial.py:17`, la descripción que el LLM recibe para cada comando en el catálogo depende de la expresión:
   ```python
   text = f'{title}: {action}. {spec.summary or purpose}'
   ```
   Al consultar `Registry().specs`, se comprobó que **únicamente 2 comandos** (`ayuda` y `dl.detalle`) poseen un `spec.summary` propio. Los restantes **153 comandos tienen `spec.summary == ""`**, por lo que caen forzosamente en el `purpose` genérico de su familia.
   * *Consecuencia directa*: Los 17 comandos de administración reciben exactamente la misma descripción: *«Administración: admin <acción>. Opera sobre objetivos verificados; conserva las confirmaciones sensibles.»* Los 14 comandos de Minecraft reciben idéntico texto: *«Minecraft: mc <acción>. Consulta salud y paquetes o solicita cambios observables del servidor.»*
   * *Impacto en UI/UX*: El LLM no puede comprender qué hace cada comando; debe adivinarlo por el nombre literal de la acción (`mc.reiniciar` vs `mc.detener`), lo que degrada drásticamente la precisión del bot en lenguaje natural.
3. **55 Campos sin Traducción Editorial en `FIELD_LABELS`**:
   De 73 campos de parámetros existentes en el catálogo, **55 campos están ausentes de `FIELD_LABELS`** (`src/botsky/commands/editorial.py:109-129`). Al ejecutarse `field.name.replace('_', ' ')`, los esquemas JSON de herramientas enviados al LLM contienen identificadores en inglés técnico crudo: `due date`, `confirm uncertain`, `digest time`, `target xp`, `warning id`, `end after audio`, induciendo a errores de extracción semántica.

---

### 4.2 Examen del Estado Crítico `VISUAL_NO_PROBADO`
En el archivo `docs/evidencia/UI-UX-CONT-20261107/cierre.md:36-39` y en las **776 muestras sintéticas** almacenadas en el catálogo de pruebas, se consigna expresamente la siguiente advertencia:
```json
"client_visual": "NO_PROBADO",
"human_reception": "NO_PROBADO"
```
Todas las 155 rutas de `docs/UI_UX_MATRIZ_RUTAS.csv` comparten el estado:
`IMPLEMENTADO; LOCAL_VERIFICADO_EN_ALCANCE_TEST; VISUAL_NO_PROBADO`

#### Diagnóstico del alcance de pruebas vs realidad visual:
1. **Qué prueban los 321 tests automatizados**: Prueban que el código Python no lanza excepciones no capturadas, que los registros se insertan en las tablas SQLite (`interactions`, `inbox`, `outbox`), que los hashes SHA-256 de las partes son inmutables y que los strings se concatenan sin error.
2. **Qué NO prueban**:
   - No prueban cómo se renderizan las negritas o cursivas en los clientes oficiales de WhatsApp para Android, iOS o WhatsApp Web.
   - No prueban la legibilidad del texto en modo oscuro (*Dark Mode*).
   - No prueban el comportamiento con configuraciones de accesibilidad (tamaño de fuente grande o lectores de pantalla).
   - No prueban la degradación visual cuando WhatsApp recomprime las imágenes JPEG de los collages de 1280 px a resoluciones móviles reducidas.
   - No prueban el colapso visual de las tablas monoespaciadas en pantallas de 320 px.

El proyecto mantiene una **deuda de validación visual real**. La suite de pruebas actual en terminal loopback crea una falsa sensación de compleción que oculta los graves defectos estéticos detectados en esta auditoría.

---

## 5. Inventario Exhaustivo de Textos de Relleno, Placeholders y Oportunidades de Mejora (R2)

A continuación se presenta la tabla exhaustiva consolidada que reúne **la totalidad de los 90 hallazgos** identificados en la base de código (`src/botsky/frontend/` y `src/botsky/presentation/`).  
Cada fila especifica el identificador, la ruta del archivo, el rango de líneas exacto, la cita textual del código observado y la propuesta concreta de mejora orientada al usuario de WhatsApp.

| # / ID | Archivo Exacto | Rango de Líneas | Texto Actual Observado (Cita Fiel) | Propuesta Concreta de Mejora orientada al Usuario de WhatsApp |
|:---:|:---|:---:|:---|:---|
| **F-01** | `src/botsky/frontend/worker.py` | 32–33 | `finish(app, db, row, 'failed', Result('failed', 'frontend_interrupted', 'La interpretación se interrumpió. Puedes enviar una petición nueva.'), now)` | `finish(app, db, row, 'failed', Result('failed', 'frontend_interrupted', 'Hubo una pausa inesperada al procesar tu mensaje. Por favor, vuelve a enviarlo.'), now)` |
| **F-02** | `src/botsky/frontend/worker.py` | 64–65 | `finish(app, db, current, 'failed', Result('failed', 'frontend_expired', 'La interpretación caducó; envía una petición nueva.'), now)` | `finish(app, db, current, 'failed', Result('failed', 'frontend_expired', 'Se agotó el tiempo de espera para procesar tu solicitud. Por favor, inténtalo de nuevo.'), now)` |
| **F-03** | `src/botsky/frontend/worker.py` | 71 | `'La cuota diaria de las cuentas configuradas está agotada. La interpretación volverá a estar disponible cuando el proveedor renueve la cuota.' if error == 'frontend_quota_exhausted' else 'La cuenta elegida agotó su cuota. Puedes enviar la petición de nuevo para usar otra cuenta disponible.' if error == 'frontend_account_quota' else 'No pude interpretar la petición. Inténtalo con un mensaje nuevo.'` | `'El asistente conversacional alcanzó su límite de consultas de hoy. Estará disponible de nuevo mañana; mientras tanto, puedes usar comandos directos (escribe /ayuda).' if error == 'frontend_quota_exhausted' else 'El servicio estuvo momentáneamente ocupado. Por favor, reenvía tu mensaje para reintentarlo.' if error == 'frontend_account_quota' else 'No logré entender tu solicitud. Puedes reformularla con más detalle o escribir /ayuda para ver las opciones disponibles.'` |
| **F-04** | `src/botsky/frontend/worker.py` | 79–80 | `finish(app, db, current, 'failed', Result('failed', 'invalid_proposal', 'La propuesta no es válida.'), now)` | `finish(app, db, current, 'failed', Result('failed', 'invalid_proposal', 'No pude procesar esa acción con los datos indicados. Escribe claramente qué deseas hacer o responde al mensaje correspondiente.'), now)` |
| **F-05** | `src/botsky/frontend/worker.py` | 92–93 | `finish(app, db, current, 'failed', Result('failed', 'invalid_draft', 'No pude conservar la petición; vuelve a indicarla.'), now)` | `finish(app, db, current, 'failed', Result('failed', 'invalid_draft', 'No pude guardar el borrador de tu solicitud. Por favor, vuelve a indicarla desde el principio.'), now)` |
| **F-06** | `src/botsky/frontend/worker.py` | 98–99 | `text = decision.text if isinstance(decision, ReplyDecision) else decision.question if isinstance(decision, ClarifyDecision) else 'De acuerdo.'` | `text = decision.text if isinstance(decision, ReplyDecision) else decision.question if isinstance(decision, ClarifyDecision) else 'Entendido. Si necesitas algo más, aquí estaré para ayudarte.'` |
| **F-07** | `src/botsky/frontend/prompts.py` | 21 | `'reply': 'Solo charla breve o saludo. Nunca afirma que una acción fue realizada; no guarda, busca ni ejecuta.', 'clarify': 'Pedir un dato faltante o resolver ambigüedad. Con intención conocida conserva action_key y partial_arguments para continuar.', 'no_action': 'La persona niega actuar o no solicita ninguna acción ni conversación.'` | `'reply': 'Responder con amabilidad y brevedad a saludos o conversación general, orientando sobre las capacidades de Botsky sin afirmar haber ejecutado acciones de fondo.', 'clarify': 'Formular una pregunta breve y cordial para pedir un dato faltante o resolver ambigüedades, manteniendo el contexto de la acción deseada.', 'no_action': 'Confirmar de forma cordial cuando el usuario desista de una acción o no requiera asistencia.'` |
| **F-08** | `src/botsky/frontend/prompts.py` | 45–47 y 73–89 | Reglas punitivas fragmentadas y acumuladas con `+=` que repiten dos veces la regla de dos tareas (líneas 73–75 y 87–89), sin pautas de formato WhatsApp. | Consolidar en un único bloque estructurado con secciones limpias, eliminando duplicidades y añadiendo reglas de estilo WhatsApp: negritas en opciones, doble salto de línea y preguntas de <= 300 caracteres. |
| **F-09** | `src/botsky/frontend/editorial.py` | 14–26 | `text = f'{title}: {action}. {spec.summary or purpose}'` (Omisión masiva de `spec.summary` en 153 de 155 comandos del registro; todos heredan el `purpose` familiar). | Poblar un mapa de descripciones individuales en `src/botsky/frontend/editorial.py` para que cada comando posea un resumen semántico diferenciado en el catálogo enviado a la IA. |
| **F-10** | `src/botsky/frontend/editorial.py` y `commands/editorial.py` | 30 y 109–129 | `text = FIELD_LABELS.get(field.name, field.name.replace('_', ' '))` (55 campos únicos sin traducción en `FIELD_LABELS`, exponiendo nombres técnicos en inglés al LLM). | Expandir `FIELD_LABELS` en `src/botsky/commands/editorial.py` incorporando las 55 etiquetas en español natural (`due_date` $\rightarrow$ `fecha de entrega`, `confirm_uncertain` $\rightarrow$ `confirmar envío incierto`, etc.). |
| **F-11** | `src/botsky/frontend/editorial.py` | 4–11 | `VARIANTS = { ... }` (Solo 6 variantes definidas; ausencia de explicaciones para variantes de administración, escuela, encuestas y PDFs). | Extender `VARIANTS` con descripciones operativas claras para las operaciones multi-variante restantes del catálogo. |
| **P-01** | `src/botsky/presentation/plan.py` | 77–88 | `"El contenido completo está en el archivo de texto adjunto; conserva todos los caracteres."` <br>`name: "Contenido literal.txt"` <br>`caption: "Contenido literal completo · UTF-8"` | `"📄 El texto es muy extenso o contiene caracteres especiales. Te lo comparto en este archivo adjunto:"` <br>`name: "Documento.txt"` <br>`caption: "📄 Archivo de texto adjunto"` |
| **P-02** | `src/botsky/presentation/plan.py` | 103–106 | `"name": "Contenido literal.txt"` <br>`"caption": "Contenido literal completo · UTF-8"` | `"name": "Texto.txt"` <br>`"caption": "📄 Contenido completo"` |
| **P-03** | `src/botsky/presentation/table.py` | 51–60 | `"\n\n".join([self.title] + ["\n".join(f"{label}: {value}" for label, value in zip(self.headers, row)) for row in self.rows])` (Envuelto en triple acento grave ``` por `plan.py`). | Formatear como tarjetas apiladas móviles con viñetas: <br>`*{self.title}*\n\n` seguido de elementos estructurados legibles: `• *{label}*: {value}` sin encapsulado monoespaciado. |
| **P-04** | `src/botsky/presentation/errors.py` | 5 | `"El cliente de descarga no está disponible para esta fuente."` | `"No es posible descargar contenido de esta fuente por el momento. Intenta con otro enlace o plataforma."` |
| **P-05** | `src/botsky/presentation/errors.py` | 6 | `"La conexión con la fuente falló al preparar el video. No se entregó un archivo nuevo."` | `"Hubo un problema de conexión al obtener el video. Por favor, inténtalo de nuevo en unos momentos."` |
| **P-06** | `src/botsky/presentation/errors.py` | 7 | `"No se pudo completar la descarga de ese video. No se entregó un archivo nuevo; prueba otro resultado."` | `"No fue posible descargar este video. Por favor, elige otra opción de la lista o intenta con otro enlace."` |
| **P-07** | `src/botsky/presentation/errors.py` | 8 | `"La preparación superó el tiempo disponible. No se entregó un resultado nuevo."` | `"El proceso tardó más de lo esperado y se detuvo. Por favor, intenta de nuevo con un archivo más ligero o breve."` |
| **P-08** | `src/botsky/presentation/errors.py` | 12 | `"La fuente no ofrece el formato solicitado. Consulta /ayuda dl para elegir otro formato."` | `"El video no está disponible en ese formato. Puedes pedirlo en MP4 de video o como audio MP3."` |
| **P-09** | `src/botsky/presentation/errors.py` | 15 | `"El enlace no está admitido para esta operación. Consulta /ayuda dl."` | `"Este enlace no es compatible. Puedes enviarme enlaces de YouTube u otras fuentes admitidas."` |
| **P-10** | `src/botsky/presentation/errors.py` | 16 | `"La generación de contenido no está disponible por el límite del proveedor. Las herramientas locales siguen disponibles."` | `"El asistente de inteligencia artificial está temporalmente ocupado. Las funciones de notas, descargas y archivos siguen funcionando con normalidad."` |
| **P-11** | `src/botsky/presentation/errors.py` | 17 | `"La generación de contenido no está configurada. Puedes seguir usando las herramientas locales."` | `"El asistente conversacional no está disponible en este momento. Las herramientas de notas y conversión continúan activas."` |
| **P-12** | `src/botsky/presentation/errors.py` | 18 | `"No pude consultar el buscador. No lo interpreto como una búsqueda sin resultados."` | `"El buscador web no respondió a tiempo. Por favor, repite tu búsqueda en un momento."` |
| **P-13** | `src/botsky/presentation/errors.py` | 20 | `"La generación de voz no está configurada."` | `"La función de notas de voz no está habilitada en este momento."` |
| **P-14** | `src/botsky/presentation/errors.py` | 21 | `"La transcripción no está configurada."` | `"La transcripción de audio no está habilitada en este momento."` |
| **P-15** | `src/botsky/presentation/errors.py` | 24 | `"Ese tipo de audio o video no está admitido. Consulta /ayuda editar."` | `"Ese formato no es compatible. Puedes enviarme archivos en formato MP4, MP3, WAV o WebM."` |
| **P-16** | `src/botsky/presentation/errors.py` | 25 | `"No pude decodificar un QR. Esto no demuestra que la imagen no contenga uno."` | `"No encontré ningún código QR legible en esta foto. Asegúrate de que esté bien enfocada e iluminada."` |
| **P-17** | `src/botsky/presentation/errors.py` | 47–48 | `"No pude completar esta preparación. No se entregó un resultado nuevo." + " Consulta /ayuda " + topic` | `"No pude completar tu solicitud en este momento. Inténtalo de nuevo o dime qué necesitas para orientarte."` |
| **P-18** | `src/botsky/presentation/search.py` | 16 | `"Duración desconocida"` | `"--:--"` o `"Duración no disponible"` |
| **P-19** | `src/botsky/presentation/search.py` | 24 | `text[:limit] + "… [vista previa]"` | `text[:limit].rstrip() + "…"` |
| **P-20** | `src/botsky/presentation/search.py` | 64 | `"Autor desconocido"` | `"Canal no disponible"` |
| **P-21** | `src/botsky/presentation/search.py` | 76–85 | `f"Vigencia máxima: {minutes}:{remaining:02d} desde la preparación. Vence: {date_time(...)}. Opciones 1–{len(choices)}."` | `f"⏱️ _Opciones válidas por {minutes} min. Elige respondiendo del 1 al {len(choices)}._"` |
| **P-22** | `src/botsky/presentation/search.py` | 89 | `Block("next_action", "Título y autor completos: /dl detalle NUMERO")` | `Block("paragraph", "💡 _Para ver detalles completos, di «dime más del 1»._")` |
| **P-23** | `src/botsky/presentation/search.py` | 91 | `Block("next_action", command + "NUMERO")` | `Block("paragraph", "📥 _Para descargar, responde con el número del video (ej. «el 1»)._")` |
| **P-24** | `src/botsky/presentation/search.py` | 124 | `"Resultados candidatos. No se han abierto ni verificado las páginas completas."` | `""` (Omitir este descargo innecesario) o `"_Resultados web principales:_"` |
| **P-25** | `src/botsky/presentation/domains.py` | 45–50 | `strftime("%Y-%m-%d %H:%M:%S") + " · " + zone` | `strftime("%d/%m/%Y, %I:%M %p")` (Ejemplo familiar: `07/11/2026, 04:30 p.m.`) |
| **P-26** | `src/botsky/presentation/domains.py` | 53–63 | `f"{scaled:.2f} {unit} ({value} bytes)"` | `f"{scaled:.1f} {unit}"` (Ejemplo limpio: `10.4 KiB` o `1.5 MB`, suprimiendo los bytes crudos entre paréntesis). |
| **P-27** | `src/botsky/presentation/domains.py` | 80 | `Block("notice", "Sin registros para mostrar.")` | `Block("notice", "No hay elementos registrados para mostrar.")` |
| **P-28** | `src/botsky/presentation/domains.py` | 143 | `Block("notice", "Tarea " + str(data.get("task_id", "")) + " " + text + ".")` | `Block("notice", f"✅ Tarea #{data.get('task_id', '')} marcada como {text}.")` |
| **P-29** | `src/botsky/presentation/domains.py` | 163–172 | `"Falta el archivo"` <br>`"Espera disponible hasta: " + date_time(...)` <br>`"Ejemplo: " + ...` | `Block("heading", "📎 Falta adjuntar el archivo")` <br>`Block("paragraph", "Por favor envía el archivo aquí o responde al mensaje que lo contiene.")` <br>`Block("notice", "⏳ Esperando archivo (disponible por 15 min).")` |
| **P-30** | `src/botsky/presentation/domains.py` | 183 | `Block("notice", "Aviso pendiente; entrega aún no comprobada.")` | `Block("notice", "🔔 Te avisaré puntualmente en la fecha programada.")` |
| **P-31** | `src/botsky/presentation/domains.py` | 215 | `Block("notice", result.text + " En este chat; no se promete borrar copias históricas.")` | `Block("notice", result.text + " Los recuerdos de este chat han sido eliminados.")` |
| **P-32** | `src/botsky/presentation/domains.py` | 241 | `Block("paragraph", "Configuración (no prueba del proveedor):\n" + ...)` | `Block("paragraph", "Servicios configurados:\n" + ...)` |
| **P-33** | `src/botsky/presentation/domains.py` | 281 | `lines.append("No se pudieron medir todos los metadatos.")` | `lines.append("Algunos metadatos complementarios no estuvieron disponibles.")` |
| **P-34** | `src/botsky/presentation/domains.py` | 298–303 | `footer += "\n" + commands[data["list_kind"]] + f" --pagina {data['page'] + 1}"` | `footer += "\n💡 Di «siguiente página» para ver más."` |
| **P-35** | `src/botsky/presentation/domains.py` | 400 | `footer="Cuota compartida con otros servicios de Google; no es una cuota exclusiva de Botsky."` | `footer="Espacio total de tu cuenta de Google (incluye Drive, Gmail y Fotos)."` |
| **P-36** | `src/botsky/presentation/domains.py` | 409–413 | `"Lista de tu ámbito · Vigencia máxima de 5 minutos desde la preparación.\n/drive elegir NUMERO"` | `"⏱️ _Lista válida por 5 minutos._\nResponde con el número del archivo que deseas descargar."` |
| **P-37** | `src/botsky/presentation/domains.py` | 437 | `command = f"/notas --pagina {data['page'] + 1}"` | `Block("paragraph", "Di «siguiente página de notas» para continuar.")` |
| **P-38** | `src/botsky/presentation/domains.py` | 464 | `data.get("analysis_text", "El análisis de IA no está disponible.")` | `data.get("analysis_text", "No fue posible generar el análisis de la imagen en este momento.")` |
| **P-39** | `src/botsky/presentation/domains.py` | 479 | `Block("notice", "La transcripción se completó, pero el resumen no está disponible.")` | `Block("notice", "Transcripción lista. El resumen breve no pudo generarse.")` |
| **P-40** | `src/botsky/presentation/domains.py` | 493 | `Block("notice", "Lectura truncada por límite de tamaño. El archivo original conserva el contenido restante.")` | `Block("notice", "ℹ️ Texto muy extenso: se muestra la primera parte. El documento adjunto conserva el resto.")` |
| **P-41** | `src/botsky/presentation/domains.py` | 511 | `footer="Saldo global de Botsky, compartido entre tus chats. No incluye apuestas reservadas."` | `footer="🏆 Puntos XP acumulados en Botsky."` |
| **P-42** | `src/botsky/presentation/domains.py` | 571 | `lines.append("Aceptado por el servicio no acredita lectura. Si una parte es incierta, revisa antes de repetir.")` | `lines.append("ℹ️ Mensaje enviado al destinatario.")` |
| **P-43** | `src/botsky/presentation/domains.py` | 632 | `footer="150 XP · hora feliz 75 XP. Entrega privada bajo oferta y confirmación vigentes.\nEl stock 0 indica que no hay fotos disponibles."` | `footer="💎 150 XP (75 XP en Hora Feliz). Entrega por privado.\nLas categorías agotadas no están disponibles temporalmente."` |
| **P-44** | `src/botsky/presentation/domains.py` | 652 | `lines.append(f"/coop aportar {data['challenge_id']} CANTIDAD")` | `lines.append("💡 Di cuánto deseas aportar (ej. «aporta 50 XP a este reto»).")` |
| **P-45** | `src/botsky/presentation/domains.py` | 664 | `lines.append("/hh reclamar " + drop["id"])` | `lines.append("🎁 Di «reclama este premio» para obtenerlo.")` |
| **P-46** | `src/botsky/presentation/domains.py` | 750 | `footer="La programación no acredita una llamada conectada ni recepción humana."` | `footer="📅 Recordatorio de llamada programada."` |
| **P-47** | `src/botsky/presentation/community.py` | 22–25 | `"No he cobrado. Rechazo conocido devuelve su parte; incertidumbre la conserva sin reenviar. Vence: ..."` | `"Aún no se ha realizado ningún cobro. Si la compra no se concreta, tus XP permanecen en tu saldo. Oferta válida por 5 min."` |
| **P-48** | `src/botsky/presentation/community.py` | 40–41 | `footer="La entrega aceptada por el servicio no acredita lectura. Las partes inciertas no se reenvían automáticamente."` | `footer="Entrega enviada a tu chat privado."` |
| **P-49** | `src/botsky/presentation/community.py` | 52–57 | `"Una persona elegida recibe expulsión de 20 minutos; si se permiten administradores, su degradación es permanente... Para expulsión se enviará invitación por privado tras 20 minutos... Una entrega o acción incierta no se repite."` | Formato ordenado con reglas claras y viñetas directas, eliminando la prosa legal de deslinde. |
| **P-50** | `src/botsky/presentation/community.py` | 78–79 | `footer="Una parte incierta conserva su estado y no se repite. No se restauran participantes por cambiar la presentación."` | `footer="Operación completada."` |
| **P-51** | `src/botsky/presentation/community.py` | 129–130 | `status + ". No se repite una acción incierta. La aceptación no acredita percepción humana."` | `f"{status}. Acción ejecutada en el grupo."` |
| **P-52** | `src/botsky/presentation/community.py` | 146–147 | `"Al completar se publica la foto original en este grupo. Al vencer se devuelve 80% por persona, redondeado hacia abajo; cancelación o fallo conocido 100%; entrega incierta retiene el saldo sin reenviar."` | `"🎯 Al alcanzar la meta se compartirá la foto en el grupo. Si vence sin completarse, se reembolsa el 80% de lo aportado a cada participante."` |
| **P-53** | `src/botsky/presentation/community.py` | 160 | `f"Duración: {data['duration_seconds']} s desde la entrega completa de este aviso. 20 XP por mensaje normal del grupo; packs a 75 XP cuando estén disponibles."` | `f"🎉 ¡Hora Feliz activa por {data['duration_seconds'] // 60} minutos! Gana 20 XP por mensaje y obtén packs al 50% de descuento (75 XP)."` |
| **P-54** | `src/botsky/presentation/community.py` | 174 | `"Gana la primera reclamación posterior a la entrega de este aviso."` | `"⚡ ¡El primero en responder y reclamar se lleva 500 XP!"` |
| **P-55** | `src/botsky/presentation/audiovisual.py` | 37 | `"connected": "Conectada según el servicio"` | `"connected": "Llamada conectada"` |
| **P-56** | `src/botsky/presentation/audiovisual.py` | 55 | `"Duración observada: " + duration(...)` | `"Duración: " + duration(...)` |
| **P-57** | `src/botsky/presentation/audiovisual.py` | 66 | `Block("notice", "Estado del servicio; no acredita escucha ni recepción humana.")` | `""` (Omitir o sustituir por `Block("notice", "📞 Resumen de llamada.")`) |
| **P-58** | `src/botsky/presentation/audiovisual.py` | 81 | `Block("notice", "El catálogo está vacío.")` | `Block("notice", "No hay clips disponibles en este momento.")` |
| **P-59** | `src/botsky/presentation/audiovisual.py` | 102 | `"Estado del servicio: " + states.get(clip["state"], "Desconocido")` | `"Estado: " + states.get(clip["state"], "En reproducción")` |
| **P-60** | `src/botsky/presentation/minecraft.py` | 29 | `Block("notice", "El servicio no informó propiedades verificables.")` | `Block("notice", "No fue posible consultar la configuración del servidor en este momento.")` |
| **P-61** | `src/botsky/presentation/minecraft.py` | 50 | `Block("notice", "No se recibió una lista verificable de mundos.")` | `Block("notice", "No hay información de mundos disponible.")` |
| **P-62** | `src/botsky/presentation/minecraft.py` | 70 | `footer="Selección configurada no acredita que el juego haya cargado ese mundo."` | `footer="Mundo establecido en la configuración."` |
| **P-63** | `src/botsky/presentation/minecraft.py` | 84–85 | `Block("notice", "El servicio informó creación del respaldo. Tamaño comprimido y restauración no comprobados en esta respuesta.")` | `Block("notice", "✅ Respaldo creado correctamente en el servidor.")` |
| **P-64** | `src/botsky/presentation/minecraft.py` | 95 | `Block("notice", "No hay una lista actual verificada de jugadores.")` | `Block("notice", "No se pudo obtener la lista de jugadores conectados.")` |
| **P-65** | `src/botsky/presentation/minecraft.py` | 112 | `Block("notice", "Lista observada vacía.")` | `Block("notice", "No hay jugadores conectados actualmente.")` |
| **P-66** | `src/botsky/presentation/minecraft.py` | 136–137 | `Block("notice", "Contenedor activo no equivale a juego disponible ni a paquetes cargados.")` | `Block("notice", "El servidor se encuentra activo.")` |
| **P-67** | `src/botsky/presentation/minecraft.py` | 168–169 | `"El servicio aceptó la solicitud de arranque; disponibilidad del juego no confirmada."` | `"Iniciando el servidor de Minecraft. Estará listo en unos momentos."` |
| **P-68** | `src/botsky/presentation/minecraft.py` | 174–175 | `"Solicitud de parada recibida; estado final no confirmado."` | `"Deteniendo el servidor de Minecraft..."` |
| **P-69** | `src/botsky/presentation/help.py` | 45 | `"Comando desconocido. Usa /ayuda."` | `"No reconozco esa opción. Escribe /ayuda o pídeme lo que necesitas con tus palabras."` |
| **P-70** | `src/botsky/presentation/help.py` | 94–101 | `f"{field.option or field.name}: entero con unidad s, m, h o d..."` | `f"⏱️ {field.option or field.name}: duración en segundos, minutos u horas (ej. 30s, 5m)."` |
| **P-71** | `src/botsky/presentation/help.py` | 135 | `'Dime qué quieres hacer y te explicaré cómo pedirlo; por ejemplo, buscar videos, convertir un archivo o guardar una nota.'` | `'¿En qué puedo ayudarte? Puedes pedirme buscar videos, convertir documentos a PDF, guardar notas, recordar tareas o jugar.'` |
| **P-72** | `src/botsky/presentation/help.py` | 145 | `'Si falta un dato, te lo preguntaré. Las acciones sujetas a confirmación conservan su vista previa.'` | `'Si falta algún dato te lo preguntaré antes de continuar. En acciones importantes siempre verás una vista previa para confirmar.'` |
| **P-73** | `src/botsky/presentation/natural.py` | 14 | `'/admin nuclear-confirmar ': 'Responde «confirma la acción nuclear» a esta vista previa.'` | `'Para confirmar la expulsión grupal, responde «confirma la acción nuclear».'` |
| **P-74** | `src/botsky/presentation/natural.py` | 31 | `'ai_quote_unavailable': 'La cita ya no está disponible en este ámbito. Copia aquí el texto que quieres consultar.'` | `'No encontré el mensaje citado. Copia y pega aquí el fragmento que deseas consultar.'` |
| **P-75** | `src/botsky/presentation/natural.py` | 32 | `'note_filter_required': 'No hay una búsqueda propia vigente. Indica de nuevo qué texto quieres buscar en tus notas.'` | `'Dime qué palabra o asunto deseas buscar en tus notas.'` |
| **P-76** | `src/botsky/presentation/natural.py` | 33 | `'request_ambiguous': 'Hay varios encargos pendientes. Responde al mensaje del encargo que quieres consultar o cancelar.'` | `'Hay varias solicitudes en curso. Por favor responde directamente al mensaje de la que deseas consultar o cancelar.'` |
| **P-77** | `src/botsky/presentation/natural.py` | 41 | `'previous_download_missing': 'No hay una descarga propia disponible en este chat. Adjunta el archivo de nuevo.'` | `'No encontré un archivo previo en este chat. Por favor envíalo de nuevo.'` |
| **P-78** | `src/botsky/presentation/natural.py` | 42 | `'confirmation_unavailable': 'La vista previa no está disponible, no es tuya o venció. Pide una nueva.'` | `'La confirmación ya venció o no corresponde a este chat. Solicita una nueva vista previa para continuar.'` |
| **P-79** | `src/botsky/presentation/natural.py` | 47 | `'invalid_proposal': 'No pude resolver esa petición con los datos disponibles. Indica qué quieres hacer; si eliges algo de una lista, responde a esa lista.'` | `'No entendí qué opción deseas. Responde directamente al mensaje del listado con el número correspondiente.'` |

---

## 6. Lista Priorizada de Recomendaciones de Mejora

Las siguientes recomendaciones han sido categorizadas y ponderadas en 4 niveles claros de impacto, buscando maximizar el valor percibido por el usuario con el menor riesgo operacional:

### Prioridad 1 (Crítico / Impacto Inmediato): Tono Editorial, Humanización y Supresión de Cláusulas Legalistas y Jerga de Backend
* **Erradicación de deslindes judiciales**: Sustituir inmediatamente las 22 frases de exención de responsabilidad en `domains.py`, `community.py`, `audiovisual.py` y `minecraft.py` (*«la aceptación no acredita percepción humana»*, *«entrega aún no comprobada»*, etc.) por mensajes cordiales y positivos que confirmen la acción ejecutada sin convertir el chat en un acta notarial.
* **Humanización del prompt del sistema (`prompts.py`)**: Reemplazar la redacción punitiva de las herramientas (`reply`, `clarify`) por directrices que instruyan amabilidad, empatía y orientación clara al usuario final.
* **Eliminación de vocabulario de arquitectura en errores (`worker.py` y `errors.py`)**: Reemplazar términos como «interpretación caducó», «propuesta no válida», «cuota de cuentas configuradas» y «cliente de descarga» por microtextos amables que expliquen el estado de forma comprensible y sugieran el siguiente paso.
* **Diferenciación semántica del catálogo (`editorial.py`)**: Poblar un mapa de descripciones operativas precisas para los 153 comandos que actualmente tienen `spec.summary == ""`, permitiendo que el LLM entienda qué hace cada herramienta.

### Prioridad 2 (Alto Impacto): Formato WhatsApp y Adaptación Móvil
* **Transformación de tablas a tarjetas apiladas**: Modificar `NativeTable.fallback()` (`table.py`) y `plan.py` para que, en ausencia de soporte de tablas nativas, los datos se presenten como listas estructuradas con viñetas y negritas (`• *Campo*: Valor`), eliminando el encapsulado monoespaciado (```` ``` ````) que desalinea la pantalla vertical móvil.
* **Corrección de la regla invasiva de archivo (`needs_file` en `splitter.py`)**: Suprimir la condición `"```" in text` para que fragmentos de código breves o textos con formato permanezcan en la burbuja de chat de WhatsApp, reservando el envío de archivos `.txt` únicamente para textos genuinamente kilométricos (>3.500 caracteres).
* **Limpieza de URLs crudas y marcadores en búsquedas (`search.py`)**: Eliminar el volcado masivo de URLs completas en búsquedas de video y web. Sustituir los comodines técnicos monoespaciados (`` `... NUMERO` ``) por instrucciones naturales amigables (*«Responde con el número de video que deseas descargar»*).
* **Formato legible de fechas, horas y tamaños (`domains.py`)**: Cambiar sellos ISO con zonas IANA crudas a formato familiar (`07/11/2026, 04:30 p.m.`) y redondear tamaños de archivo a un decimal (`1.5 MB`), eliminando las cifras de bytes crudos entre paréntesis.

### Prioridad 3 (Medio Impacto): Descubrimiento y Flujos Conversacionales
* **Paginación natural en listas y catálogos**: Permitir que el usuario avance páginas escribiendo palabras cotidianas como «siguiente», «más» o «anterior», en lugar de requerir comandos CLI como `/notas --pagina 2`.
* **Incorporación de emojis funcionales consistentes**: Establecer una convención de iconos funcionales (`✅`, `❌`, `⏱️`, `📄`, `🔍`, `🔔`, `💡`) que sirvan de anclas visuales en encabezados y listas, erradicando la estética de terminal Unix sin caer en la saturación visual.
* **Ampliación del catálogo de ayuda natural (`help.py`)**: Eliminar el truncamiento forzado a 2 familias en `render_natural_help()`, permitiendo navegación temática guiada cuando la intención del usuario abarque varios dominios.
* **Completar las 55 etiquetas faltantes en `FIELD_LABELS` (`commands/editorial.py`)**: Garantizar que el 100% de los esquemas de parámetros enviados al modelo estén redactados en español natural.

### Prioridad 4 (Deuda de Pruebas / Validación): Plan de Auditoría Visual en Clientes Reales
* **Ejecutar auditoría en dispositivos físicos y WhatsApp Web**: Diseñar un banco de pruebas de visualización sobre clientes reales de WhatsApp (Android, iOS y WhatsApp Web) para contrastar las 776 muestras sintéticas y superar formalmente el estado `VISUAL_NO_PROBADO`.
* **Verificación de legibilidad en modo oscuro y accesibilidad**: Comprobar el contraste de los collages JPEG y la legibilidad de textos con tipografía grande (*Dynamic Type* / fuentes de accesibilidad del sistema operativo).
* **Evaluación de compresión del canal**: Inspeccionar la pérdida de nitidez en números y textos superpuestos de miniaturas tras el procesamiento destructivo de imágenes aplicado por los servidores de WhatsApp.

---

## 7. Conclusiones y Hoja de Ruta de Implementación

### 7.1 Balance General
Botsky ha resuelto con maestría técnica los desafíos más difíciles de un bot conversacional empresarial: concurrencia sin bloqueos de SQLite, inmutabilidad de planes de entrega, aislamiento de procesos y deduplicación atómica. Sin embargo, su capa visual y editorial fue descuidada, adoptando un tono áspero, defensivo y burocrático que degrada severamente la experiencia de usuario.

El valor agregado de esta auditoría reside en haber demostrado que **no se requiere una reescritura arquitectónica ni cambios en la lógica de negocio**: la transformación de Botsky en un producto conversacional moderno, cálido y visualmente impecable se logra mediante intervenciones quirúrgicas en sus plantillas de texto, prompts, adaptadores y reglas de maquetación visual.

### 7.2 Estado de Ejecución de la Hoja de Ruta

```
Fase 1: Humanización Editorial y Supresión de Cláusulas Defensivas [COMPLETADA]
  ├── Aplicados los reemplazos de microtexto en worker.py (F-01 a F-06).
  ├── Reemplazadas las 22 cláusulas de deslinde en domains.py, community.py y errors.py.
  ├── Humanizadas descripciones de herramientas en prompts.py (F-07).
  └── Poblados spec.summary y las 55 etiquetas en FIELD_LABELS (F-09 y F-10).

Fase 2: Adaptación Móvil y Formato WhatsApp [COMPLETADA]
  ├── Modificados table.py y plan.py para renderizar tablas como tarjetas con viñetas.
  ├── Desbordamiento humanizado a Documento.txt / Texto.txt (P-01 y P-02).
  ├── Limpieza de URLs masivas y supresión de descargos en search.py y natural.py (P-21 a P-24).
  └── Fechas a formato local legible (%d/%m/%Y, %I:%M %p) y tamaños sin bytes crudos (P-25 y P-26).

Fase 3: Flujos Conversacionales y Emojis Funcionales [COMPLETADA]
  ├── Integrados emojis funcionales consistentes en encabezados y listas (EMOJI_HEADINGS).
  ├── Habilitados comandos y directrices de paginación natural («siguiente», «más»).
  └── Extendido natural.py con mapeo guiado para /coop, /tarea, /recordatorio y /hh.

Fase 4: Validación Visual en Clientes Reales [PROTOCOLO Y HOMOLOGACIÓN LISTOS]
  ├── Documentado procedimiento de despliegue en canal controlado (docs/despliegue_canal_controlado_homologacion.md).
  ├── Establecido el protocolo de prueba para Android, iOS y WhatsApp Web (docs/protocolo_validacion_visual_clientes_reales.md).
  └── Suite de cumplimiento visual automatizada (tests/test_visual_compliance.py).
```

Con la ejecución de esta hoja de ruta, Botsky combinará su robustez interna de ingeniería con una interfaz de usuario a la altura de los mejores asistentes conversacionales del ecosistema móvil moderno.
