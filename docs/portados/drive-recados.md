# Drive y recados · R6 en curso, sin cierre

Referencia técnica Zhana fijada en R0:7e12d54; hashes de archivos consultados en
drive-origen.json. No se consulta configuración, OAuth, directorio o datos antiguos.

Cliente Drive adaptado únicamente: HTTPX, carpeta única, metadatos/identificadores,
query escapada, cuota, ID previo, multipart/streaming/resumable, conciliación por
GET del ID reservado después de resultado incierto; nunca segunda subida propia.
Ubicación resumable solo https://www.googleapis.com/upload/drive/v3/files.
No sigue redirecciones. Scope obligatorio con propiedad nueva botsky_scope; rechaza
archivos ajenos/borrados. Descarga verifica metadata previa, tamaño16MiB y bytes.
Subida técnica hasta2GB por Path (límite fuente vigente, no2GB cargados en memoria).

Se excluyeron Args antiguos, lectura de private/, carga de configuración y refresh/
persistencia antiguos. Constructor exige folder_id y función async de token
explícitos, deshabilitado sin ambos. Autorización OAuth y almacenamiento propios
seguirán pendientes de R6. Cliente no conectado al Application ni al executor.
Ningún comando Drive se anuncia como implementado por existir este archivo.

Directorio de recados propio: nombres/alias configurados, normalización técnica
NFKC/casefold, coincidencia exacta, límites y colisiones; lista completa o error,
nunca lista parcial. Hash liga nombres y destinos para verificar futuras vistas.
No extrae destinatarios del texto ni infiere teléfonos. Contact.target oculto en
repr. Fixture sintética; no directorio ni datos de usuario copiados.

Evidencia: siete pruebas Drive con cliente HTTPX real y MockTransport; subida de
archivo por stream real local, URL ajena, cuerpo acotado, scope/redirecciones,
conciliación sin segundo POST. Dos pruebas de directorio/resolución/colisiones/hash.
No cliente Google remoto ni transporte de mensajes; no aceptación humana.

Falta completar R6: tablas y recibos de Drive/vistas/selección, lease propio y
trabajos bajo contratos de Botsky; OAuth propio; borrador de recado con fuente/cita
verificada, adjunto y vista entregada, confirmación de dueño privado con frescura;
reserva por destinatario/parte, cancelación y conciliación incierta sin repetición;
cliente de envío acotado y pruebas locales. Ni R6 cerrado ni transición autorizada.
