# Medios, archivos y documentos · R3

Origen técnico: Zhana 7e12d54. Ficheros exactos, hashes y decisión de adaptación
en motores-origen.json (media.py, media_edit.py, document_formats.py,
documents.py, document_worker.py, variety_worker.py, pdf_operations.py,
pdf_ops_worker.py, downloads.py, remote_subtitles.py y helpers RSS de web_search.py).
Pruebas de origen son referencia de contrato, no aceptación nueva.

Se trasladan componentes técnicos acotados de motores/formatos/extractores.
No se trasladan los Args/Pydantic de herramientas, la entrada antigua, su Store,
executor, conversación, clasificador ni acceso a datos. Botsky reserva trabajos,
comprueba autoridad y referencias, gestiona leases, sesiones y resultados con sus
contratos propios. Los motores reciben rutas/bytes del backend, nunca rutas del chat.

FFmpeg conserva demuxers y protocolos cerrados (file/pipe), rangos, dimensiones,
duración y verificación del codec real. El runner acota CPU/memoria/salida y retira
el grupo al cancelar; se añadió un supervisor Linux mínimo con PDEATHSIG para
retirar también descendientes al morir el padre. Se probó muerte real de un padre
Python sintético y exclusión del worker mediante flock, sin servicios externos.

Documentos conserva sandbox bwrap sin red, entorno limpio, solo /usr, paquetes
propios y directorio del trabajo. Perfil LibreOffice por trabajo, macros/enlaces
deshabilitados, firma/ZIP/DOCTYPE y límites antes de convertir. Python de sandbox
ve los paquetes de Botsky montados de solo lectura; no ve home/private del host.

Comprobaciones nuevas: PDF→DOCX con dos páginas, escaneo sin OCR con código
document_no_text, varias hojas→CSV en ZIP, imagen→PDF, 19 destinos reales con
inspección de formato (y texto recuperado de las familias Office), MP3/MP4/WebM/SRT,
sticker 512×512, OCR y QR sintéticos. No equivale a todas las parejas de formatos
ni a carga de archivos máximos; la matriz completa de aceptación corresponde a R10.

Fuentes de descarga: se conserva normalización, allowlist por fuente, proxy CONNECT
que fija direcciones públicas verificadas por DNS y límites de red/extractor.
Sin cookies/perfiles/plugins/componentes remotos ni configuración implícita de
yt-dlp. El adaptador nuevo está deshabilitado por defecto. Búsqueda solo en las
fuentes que la implementan; otras dan source_search_unavailable, sin fallback a
YouTube. Spotify exige coincidencia real elegida por el usuario.

Pruebas de red: dobles de cliente, HTTPX MockTransport y proxy loopback con DNS y
salida remota sustituidos. Cero conexiones de prueba a fuentes/proveedores.
Los motores del flujo de descarga sí procesan un video local real. La disponibilidad
de YouTube/W3C/SoundCloud/Dailymotion/Vimeo/Facebook/Instagram/TikTok/Spotify y adultas
sigue NOT_TESTED en Botsky. Adultas optativas y apagadas; no confundir validación
de URL con descarga real del sitio. yt-dlp del host solo se comprobó como dependencia.

RSS: parser técnico recuperado; argumentos del registro, cliente nuevo a endpoint
fijo y respuesta acotada. site: y términos explícitos se filtran sin afirmar que
los candidatos sean relevantes, oficiales o actuales. No se abren páginas sugeridas.

Activos: cuatro reacciones WebP y catálogo originales de Zhana (ilustraciones
generadas el 27/10, origen declarado en catalog.json, sin chats). Se conservan sus
hashes y créditos. No se trasladan personalidad antigua, VRM, perfiles ni activos
privados. No hay publicación ni se inventa una licencia pública del código propio.

Dependencias de media fijadas tras instalar y probar en .venv propio. Se reconstruyeron
ruedas locales desde dependencias instaladas y sus metadatos/licencias, sin red ni
mutar la instalación de referencia. No son ruedas originales firmadas upstream.
Manifiestos/versiones/SHA256 en evidencia R3-dependencies.json; ruedas privadas
ignoradas. El núcleo de notas/parser sigue usando solo biblioteca estándar.
