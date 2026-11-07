# Compacto íntegro activo · 07/11/2026

Por encargo expreso del propietario se desplegó el catálogo compacto íntegro.
FrontendService utiliza LosslessCatalog por defecto: 155 acciones en tabla directa,
con schemas de campo compartidos. Mantiene todos los valores del catálogo original,
incluidos descripciones, permisos, efectos, referencias, constantes y restricciones.
No introduce otra selección, clasificador ni consulta posterior al resultado.
El backend sigue validando y ejecutando. Los catálogos explícitos de experimentos
anteriores siguen disponibles; sus evidencias y cancelaciones se conservan.

Validación local: 61 pruebas pertinentes aprobadas, incluyendo frontend, contratos,
pool e integraciones. La expansión JSON exacta se comprueba con descargas adultas
activadas/desactivadas, descargas deshabilitadas y disponibilidad sintética.

Aceptación nueva con cf04 y Qwen3.8-27B low: seis casos únicos correctos en siete
intentos. Nota Markdown literal, nota hostil, aclaración por formato, continuación,
confirmación verificada y delegación a Gemini. Confirmación agotó 40 segundos en
la primera corrida; no hubo respuesta ni usage, y ese intento sigue fallido. Un
suplemento explícito obtuvo confirmación correcta en 8,769 segundos y delegación
en 4,518 segundos. No es una garantía de ausencia de timeouts ni cobertura semántica
de las 155 acciones. Inferencias capturadas, sin ejecutar ninguna herramienta.

Comparando los tres casos comunes con el baseline de la campaña anterior:

| Medida, suma de tres casos | Original | Íntegro desplegado |
| --- | --- | --- |
| Tokens de entrada | 67.320 | 51.093 |
| Neuronas reportadas | 2.831,96 | 2.168,13 |

Ahorro observado: 24,10 % de tokens de entrada y 23,44 % de neuronas. La mediana de
las seis respuestas exitosas nuevas es 4,886 segundos; el timeout de 40,042 segundos
se informa aparte. No comparación aleatorizada ni promesa universal de latencia.
Cached_tokens permanece en cero. Se comunicó al propietario que este resultado
sustituye la estimación del prototipo anterior: el ahorro de 45,7 % y casi cien
consultas diarias no corresponde a esta implementación íntegra.

Con el promedio de estas seis respuestas, cinco cuentas con sus 50.000 neuronas
completas permitirían aproximadamente 68 consultas similares al día. Es capacidad
estimada, no saldo actual: cf05 ya se utilizó en la campaña anterior y cf04 reportó
4.416,56 neuronas en esta aceptación, más un intento de uso desconocido por timeout.
El modelo puede gastar más o menos según entrada y salida.

Corte productivo: fuente e8b98f4, código funcional 6f54942, nuevo PID 3880318.
Backup privado deploy-compact-20261107* con SQLite consistente e integridad/FK,
perfil, configuración, registro/credenciales de las cinco cuentas y archivos de
fuente anterior 3c29a21 y actual. DB idéntica al respaldo mientras se encontraba
parado; esquema 20 sin migración. Perfil, Qwen low y pool sin cambios. Runtime y
servicio de llamadas ready, sin llamadas activas; demás supervisores conservaron
PID/estado. No envíos ni inferencias durante el corte. Recepción humana NO_PROBADA.

Reversión implementada: parada del runtime propio, recuperación únicamente de
service.py de la fuente anterior y arranque comprobado, conservando DB y perfil.
No se activó. El respaldo conserva la fuente completa anterior y credenciales
privadas, fuera de Git. No se modificaron servicios ajenos.

Evidencia: docs/evidencia/DESPLIEGUE_COMPACTO_20261107, con manifiestos congelados,
aceptación fallida parcial, suplemento, métricas y recibo de despliegue separados.
Sin reanudación automática de esta aceptación ni campañas históricas.
