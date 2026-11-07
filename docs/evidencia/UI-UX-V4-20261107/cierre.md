# V4 · organización y archivos, primer cierre

Presentación desde hechos: recordatorios(fecha/segundos/zona/estado/texto), tareas
(ref/estado/entrega/materia/texto/archivo), horario4columnas, pregunta/resultados/
total/estadoencuesta, Drive5opciones+nombre+tamaño y cuota decimal compartida.
Tablas se dividen por20filas sin quitar campos; fallback equivalente sin soporte.
Celdas excesivas conservan TODOS los campos en texto, sin truncarlas para forzar
el protocolo. Notas/memoria separan referencias y contenido; OCR/transcripción
con encabezado y contenido literal. Sin regex/parseo de mensajes terminados.

Nombres de archivo derivados del título/nombre verificados, sin rutas/control/
UUID como nombre principal; extensión final real de artefacto. Caption durable,
preview marcada cuando supera límite; voz/sticker conservan endpoint/tipo.
Recado conserva destinatario/texto/adjunto/confirmación y quitaSHAintrusivo del
mensaje; verificación SHA sigue en dominio. Recordatorio creado ya no afirma que
WhatsApp esté desactivado; avisa entrega pendiente, sin prometer recepción.

3tests nuevosPASS (SQLite real→tabla, encuesta pregunta/literal/votos, Drive/unidades,
celdasexcesivas, nombres), 11organización/16medios/15integracionesPASS. Ensayos
anteriores de la prueba nueva usaron raízhorario incompleta y actor sin permiso;
se corrige fixture a /horario listar y dueño; guards del producto intactos.
Ruff check/format en archivos afectados y base previa, sin código/runtime Zhana.
VISUALcliente/recepciónNO_PROBADO, sin envíos/llamadas. Producción aún sin recargar.

V4 EN_CURSO: falta catálogo por todas sus54rutas, revisión minuciosa PDF/voz/QR/
recados y literalidad visual con marcadores; los motores reales previos no prueban
renderizado de captions en el cliente. Continuar independientemente y no cerrar
la fase ni el plan solo por estos presentadores.
