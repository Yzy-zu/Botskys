# IA y voz · R4

Referencia técnica: Zhana 7e12d54, providers/gemini.py (solo cliente, errores/cuota,
plazos y resumen de contenido), providers/whisper.py, audio.py y speech.py.
Hashes de los tres componentes trasladados en motores-origen.json. No se adapta
su intérprete, bucle conversacional, catálogo de herramientas para modelo ni NLP.

GeminiContent es nuevo y recibe solo prompt, historial propio acotado, cita textual
verificada y archivos propios. SDK google-genai 2.33.0 instalado offline en .venv
propio; API key/modelo deben inyectarse explícitamente. No consulta configuraciones
antiguas, entorno secreto, proveedores alternativos, pools ni claves adicionales.
Configuración tools vacía, automatic_function_calling.disable=True, un intento
SDK por solicitud; rechaza function_call/function_response/código/thought/salida
no textual. Un texto con /admin o /nota no vuelve al router.

Adjuntos: firma/formato, propiedad, retención y lease de Botsky. Imágenes se
comprueban por decoder; PDF por sandbox; documentos Office se transforman a texto
en sandbox antes del análisis. Partes inline acotadas; archivos mayores se suben
por files API y se intenta borrarlos al cerrar. Fallo/timeout del upload puede
dejar un archivo cuyo ID no llegó: no se promete borrado de un recurso desconocido.
Pruebas con tipos SDK reales y cliente doble (incluidos upload/delete), sin API real.

ASR conserva Groq Whisper, modelo de referencia whisper-large-v3-turbo, cliente
HTTPX acotado, Retry-After/cooldown y respuesta validada. Audio se normaliza de
verdad a FLAC mono16k; límite de origen10MiB, duración1200s y salida25MB. Silencio
medido no se envía; no se interpreta transcripción como comando. Proveedor real
y calidad de reconocimiento NOT_TESTED. Un resumen fallido conserva el transcript
y se presenta como fallo parcial, sin afirmar que se consiguió el resumen.

TTS conserva Edge7.3.1 y perfiles/efectos fijos de speech.py; `zhana` se renombra
`botsky` sin cambiar la voz técnica Dalia. CLI propia en .venv, no la del servicio
activo. Literal no consulta Gemini; cita/última son fuentes exactas propias con
entrega comprobada para salidas del bot. Composición llama Gemini para guion y
después TTS. Duración orientativa, máximo de audio600s, texto8000caracteres.

La frontera CLI fue sustituida por una fixture local que registra texto/voz exactos
y produce tono MP3; el pipeline real verifica y convierte a Ogg/Opus mono48k.
Esto prueba argumentos, filtros y artefacto, no habla real ni pronunciación de
Edge. Escucha humana, disponibilidad de voces y proveedores quedan para R10.

Persistencia propia v4: contexto AI aceptado por ámbito/época y TTL30min, máximo
seis intercambios/16000caracteres; texto fuente literal24h. Poda del contexto
vencido sin borrar recibos/canonical/entregas que protegen efectos. No importar
historial, memoria ni corpus anteriores. Datos sintéticos únicamente en pruebas.

Se marca dispatch de proveedor antes de invocarlo: si el proceso cae y vence el
lease, se publica provider_interrupted/uncertain sin repetir la petición. Es una
simulación local de corte, no prueba remota de exactamente una vez. Fallos/cuota
solo afectan a esa función; notas/conversiones locales permanecen independientes.
