# Uso de Botsky · construcción local

Actualización posterior: [credenciales e integraciones validadas por encargo](INTEGRACIONES.md). Las evidencias locales siguientes conservan su fecha y alcance.

Botsky admite tanto comandos explícitos como peticiones en lenguaje natural cuando el intérprete conversacional está habilitado. Texto libre o texto que contenga comandos dentro de
una nota, documento, audio transcrito o respuesta de IA no ejecuta herramientas.
Los ejemplos usan IDs devueltos por Botsky; no son nombres visibles ni identidades
inferidas. La instalación activa de Zhana continúa separada.

### Tres ejemplos actuales y uso de **Responder**

1. **Guardar y consultar notas:** «Guarda una nota: comprar pan» (`/nota guardar pan`) y «Muéstrame mis notas» (`/notas`).
2. **Buscar y descargar videos:** «Busca videos de recetas rusas» (`/dl buscar mp4 recetas rusas`). Cuando aparezca el listado, usa **Responder** sobre esa lista y escribe el número de la opción (por ejemplo, `1` o `2`).
3. **Convertir documentos o guardar en Drive:** «Pasa este archivo a PDF» (`/convertir pdf`) o «Guarda esto en Drive» (`/drive guardar`) adjuntando el archivo.

**Uso de Responder en WhatsApp:** En listados de videos o Drive, búsquedas paginadas con varias listas y vistas previas de confirmación, usa **Responder** sobre el mensaje exacto del listado y escribe el número o «siguiente». En grupos, los números sueltos sin **Responder** se ignoran para no interferir en la conversación; en chat privado con una única lista vigente puedes enviar el número directamente. Referencia general en [README.md](../README.md).

`/ayuda` muestra familias; `/ayuda notas` muestra esa familia. La lista completa y
los tipos se generan desde [el registro](commands.md). Las opciones van antes del
texto literal final; `--` fuerza que el resto sea texto. Un valor de opción con
espacios lleva comillas, como `--tema "Tema literal"`. Las fechas son completas
(`2026-12-01 12:00`), con zona America/Mexico_City. Duraciones como `30s` o `5m`.

| Uso | Ejemplo |
| --- | --- |
| Nota literal y filtro | `/nota guardar -- Cable EXACTO; /daily` · `/notas Cable` |
| Trabajo por ID | `/estado ID` · `/cancelar ID` |
| Archivo | `/convertir pdf` con un adjunto propio, o una cita exacta de un archivo entregado |
| PDF por pasos | `/pdf iniciar`, adjuntos explícitos, `/pdf terminar`; usar los IDs y confirmaciones devueltos |
| Descarga | `/dl mp3 URL` · `/dl buscar mp4 consulta` · seleccionar con el ID de la vista entregada |
| Subtítulos existentes | `/dl srt --idioma es URL`; extrae subtítulos completos, no los inventa ni recorta |
| Voz | `/voz -- Texto literal` · `/voz crear -- Petición de contenido`; el segundo necesita Gemini |
| IA de contenido | `/ia Explica este tema`; no decide comandos ni llama al ejecutor |
| Organización | `/tarea crear --fecha 2026-12-01 --hora 12:00 Texto` · `/recordar en 5m Texto` |
| Encuesta | `/encuesta crear "¿Hora?" "10:00" "11:00"`; la publicación completa precede al voto |
| Recado | `/contactos` · `/recado preparar --para ALIAS -- Texto`; revisar vista entregada antes de enviar |
| Llamada habilitada | `/llamar --duracion 5m --tema Tema` · `/llamada estado` · `/llamada colgar` |
| Agenda habilitada | `/llamada programar 2026-12-01 13:00 --tema Tema` · `/llamada agenda` |
| Video habilitado | `/llamar --video` · `/clip lista` · `/clip poner ID` · `/avatar fondo neon` |

Los resultados largos y archivos se entregan por partes. «Trabajo en cola»,
«proveedor aceptó», «llamada conectada» y «recibido/escuchado por una persona» son
estados distintos. Una parte incierta se conserva para revisión; reenviar una
orden nueva puede crear otro encargo. Duplicar el mismo recibo no lo repite.

Los adjuntos requieren orden explícita vigente. Una espera/vista/confirmación solo
se activa tras su entrega completa y pertenece a su ámbito. No uses un ID de otra
persona, chat, cuenta o época. Las vistas caducadas requieren una consulta nueva.

Dueño verificado: administración, modos, servidor, destinos y confirmaciones
sensibles. Los amigos admitidos conservan sus operaciones ordinarias; los grupos
necesitan habilitación explícita. Nuclear está deshabilitado por defecto; tener
su sintaxis o una vista previa no habilita una expulsión. Ruleta/cooperacha/packs
mantienen consentimiento, publicación y saldo propios.

Esta construcción utiliza conectores optativos. Sin configuración propia, Botsky
devuelve un límite explícito; no toma claves, DB, contactos, sesiones ni catálogos
privados de Zhana. Live requiere una única credencial y modelo explícitos. Avatar
requiere modelo y licencia propios: actualmente no están configurados. El video
conserva la restricción de la solución original al privado del dueño o primer grupo.

Las comprobaciones actuales son locales: motores reales sobre fixtures, clientes
con fronteras locales/dobles, audio privado y WebRTC de loopback. Proveedores reales,
WhatsApp, Android y aceptación humana esperan una campaña expresamente encargada.
No hay cuenta, sesión, navegador o transporte productivo de Botsky activados.
