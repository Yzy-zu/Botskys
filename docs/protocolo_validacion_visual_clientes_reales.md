# Protocolo de Validación Visual en Clientes Reales de WhatsApp (Fase 4)

## 1. Objetivo y Alcance

Este protocolo define el procedimiento riguroso para contrastar y homologar las mejoras de frontend UI/UX (Fases 1, 2 y 3) directamente en clientes físicos de WhatsApp, cerrando la brecha entre la verificación de pruebas locales automatizadas y la experiencia real del usuario final.

### Dispositivos y Plataformas Objetivo:
1. **Android**: Dispositivo físico con WhatsApp versión estable reciente (Android 13+).
2. **iOS**: iPhone físico con WhatsApp versión estable reciente (iOS 17+).
3. **WhatsApp Web / Desktop**: Navegador Chrome/Safari/Edge en monitor estándar (1080p y 4K).

---

## 2. Matriz de Invariantes y Criterios de Aceptación Visual

| Componente | Estado Anterior (Fase 0) | Estado Implementado (Fases 1–3) | Criterio de Aceptación en Cliente Real |
|---|---|---|---|
| **Collage de Videos** | Enviado en 2 mensajes separados (`media` + `text`). | Mensaje único con imagen JPEG y selección en subtítulo (`caption`). | La imagen y las opciones de video se reciben en una sola burbuja sin desfasarse. Miniaturas nítidas en pantalla pequeña. |
| **Tablas y Listados** | Tablas de texto plano envueltas en monoespacio (```` ``` ````) con saltos forzados. | Tarjetas apiladas móviles con viñetas (`• *Campo*: Valor`) y encabezado en negrita. | No se muestra fondo gris oscuro de código; el texto se ajusta fluidamente al ancho de 320 px a 420 px en móvil. |
| **Microtextos de Error** | Jerga técnica de backend (*«interpretación caducó»*, *«propuesta no válida»*). | Mensajes amables y orientativos con instrucciones claras. | El usuario comprende el estado sin ver vocabulario de bases de datos o arquitectura. |
| **Fechas y Horas** | Formato ISO con zona IANA cruda (`2026-11-08 15:30:00 · America/Mexico_City`). | Formato familiar natural (`08/11/2026, 03:30 p.m.`). | Legible de un vistazo, sin exponer nombres de servidor ni segundos irrelevantes. |
| **Tamaños de Archivo** | Cifras dobles con bytes crudos (`1.00 KiB (1024 bytes)`). | Formato limpio redondeado (`1.00 KiB` o `2.5 MB`). | Sin cadenas de números crudos entre paréntesis. |
| **Desbordamiento a Texto** | Archivo llamado `Contenido literal.txt` con aviso técnico UTF-8. | Mensaje cordial adjuntando `Documento.txt` o `Texto.txt` con emoji 📄. | El usuario recibe un mensaje explicativo y un archivo claramente etiquetado. |
| **Paginación** | Requería comando CLI (`/notas --pagina 2`). | Paginación natural («siguiente», «más», «avanzar»). | Escribir «siguiente» o «más» muestra la siguiente página sin escribir comandos. |
| **Anclas Visuales** | Texto monocromático tipo terminal Unix. | Encabezados consistentes con emojis funcionales (`🎬`, `📝`, `🔔`, `📋`, etc.). | Encabezados visualmente estructurados y diferenciables en el historial del chat. |

---

## 3. Banco de Pruebas Focales (6 Escenarios Críticos)

### Escenario 1: Búsqueda y Collage Multimedia
- **Entrada natural**: *«Busca videos de gatos divertidos»*
- **Observación esperada**:
  - Recepción de **un solo mensaje**.
  - Imagen JPEG compuesta (1280×720 px) con miniaturas y numeración 1–N.
  - Subtítulo del mensaje conteniendo los títulos, duraciones, canales y la instrucción: *«Responde con el número del video que quieres descargar»*.
  - Sin desbordamiento a segundo mensaje cuando la selección sea $\le$ 4 opciones.

### Escenario 2: Consulta de Datos Tabulares (Top XP / Horarios)
- **Entrada natural**: *«Cómo está el top de jugadores»* o *«Ver mis tareas»*
- **Observación esperada**:
  - Encabezado destacado (`*🏆 Top de XP*` o `*📋 Tareas*`).
  - Cada registro formateado en bloque vertical:
    ```text
    *Tú · #1*
    • *Puesto*: 1
    • *XP*: 500
    • *Nivel*: 2
    ```
  - Sin caracteres de código ```` ``` ```` ni fuentes monoespaciadas.

### Escenario 3: Paginación Conversacional
- **Entrada natural**: *«Ver mis notas»* $\rightarrow$ Respuesta: muestra página 1.
- **Entrada de seguimiento**: *«siguiente»* o *«más»*.
- **Observación esperada**:
  - El bot reconoce el contexto y entrega automáticamente la página 2 de notas.
  - No requiere que el usuario conozca o escriba `/notas --pagina 2`.

### Escenario 4: Recordatorios y Avisos Temporales
- **Entrada natural**: *«Recuérdame sacar la pizza del horno en 15 minutos»*
- **Observación esperada**:
  - Encabezado `*🔔 Recordatorio guardado*`.
  - Fecha y hora formateada en estándar local (`08/11/2026, 03:45 p.m.`).
  - Nota cordial: `Te avisaré puntualmente en la fecha programada.`

### Escenario 5: Manejo de Errores y Aclaraciones
- **Entrada natural**: *«Convierte este archivo»* (sin adjuntar nada).
- **Observación esperada**:
  - Mensaje empático: `📎 Falta el archivo. Adjunta el archivo aquí o responde al mensaje exacto que lo contiene.`
  - Ausencia total de términos como `invalid_draft`, `action_key` o `NoneType`.

### Escenario 6: Desbordamiento de Texto Extenso
- **Entrada**: Envío de un texto superior a 3.500 caracteres o con delimitadores especiales.
- **Observación esperada**:
  - Mensaje cordial: `📄 El texto es muy extenso o contiene caracteres especiales. Te lo comparto en este archivo adjunto:`
  - Documento adjunto nombrado `Documento.txt` con leyenda `📄 Archivo de texto adjunto`.

---

## 4. Pruebas de Accesibilidad y Modo Oscuro

1. **Modo Oscuro (*Dark Mode*)**:
   - Comprobar legibilidad de texto en negrita y cursiva sobre fondo oscuro de WhatsApp.
   - Comprobar que los textos superpuestos en los collages JPEG (números amarillos y títulos sobre franja oscura) mantienen contraste WCAG AA (ratio $\ge$ 4.5:1).
2. **Tipografía Dinámica (*Dynamic Type*)**:
   - Ajustar el tamaño de fuente del sistema operativo en el teléfono móvil al nivel máximo (accesibilidad para debilidad visual).
   - Verificar que las viñetas y saltos de línea de las tarjetas no se cortan ni solapan.
3. **Compresión del Canal de WhatsApp**:
   - Verificar que la compresión destructiva de imágenes de WhatsApp no vuelve ilegibles los números de opción en las miniaturas del collage.

---

## 5. Criterio de Levantamiento de `VISUAL_NO_PROBADO`

Para que una ruta en `docs/UI_UX_MATRIZ_RUTAS.csv` pase al estado final `HOMOLOGADO_CLIENTE_REAL`:
1. Debe haber sido ejecutada en el canal de staging/homologación.
2. Debe haber sido capturada visualmente en al menos un dispositivo Android o iOS y en WhatsApp Web.
3. Las capturas de pantalla deben archivarse en `docs/evidencia/homologacion_visual/`.
4. La columna `observacion_cliente` de la matriz debe consignar la fecha, dispositivo y versión probada.
