# Medición nueva de ahorro Qwen · 07/11/2026

El propietario autorizó investigar y gastar una sola API. Se usó exclusivamente
cf05, Qwen3.8-27B reasoning_effort=low, catálogo completo de155variantes, fixtures
sintéticos, propuestas sin ejecutor. Producción y las otras cuentas no se alteraron.
No se reanudaron las campañas canceladas. Manifiestos y expectativas se congelaron
antes de cada iteración; commits4b94052 y39bb1e8. Una respuesta correcta no acredita
un efecto de backend ni recepción humana.

## Resultado observado

Tres casos emparejados: nota Markdown literal, continuación de conversión y
pregunta de contenido que debe delegarse a Gemini. Los oracles proceden del corpus
F7 anterior. Misma cuenta/modelo/temperatura/límite2048/deadline40s. Orden secuencial
actual→prefijo con afinidad→compacto; no aleatorizado y sin réplicas suficientes
para inferencia estadística de latencia. El baseline precede a la segunda iteración.

| Variante | Aciertos pares | Tokens entrada, suma | Neuronas, suma | Mediana segundos |
| --- | --- | --- | --- | --- |
| Actual | 3/3 | 67.320 | 2.831,96 | 7,014 |
| Prefijo fijo y afinidad | 3/3 | 67.320 | 2.856,98 | 5,275 |
| Compacto y afinidad | 3/3 | 35.157 | 1.536,57 | 3,271 |

Compacto frente actual:47,78%menos tokens de entrada y45,74%menos neuronas.
Eso equivale a1,84veces consultas del mismo tipo por igual presupuesto, no una
promesa universal de mensajes diarios. El compacto recibió también nota hostil,
conversión sin formato y confirmación verificada:6/6casos únicos correctos en total.
No se evaluaron semánticamente las155acciones. Tampoco fue más rápido en todos
los casos:continuación12,658scompacto frente15,107sactual y6,806sprefijo.

Todas las13inferencias exitosas devolvieron cached_tokens=0, incluida una repetición
idéntica con afinidad. No hay ahorro de caché demostrado en este endpoint/modelo.
No se demuestra que la caché no pueda funcionar en otras rutas o condiciones.
La afinidad por sí sola no reduce los tokens enviados ni garantizó ahorro.

## Hallazgos de ingeniería y límites

El frontend actual ya envía contexto acotado; no reenvía un historial completo.
El catálogo y protocolo dominan el gasto:una nota sencilla demanda22.424tokens
entrada y940,33neuronas. La salida es pequeña,79tokens en esa consulta; reducir
solo su límite no elimina el coste del catálogo y puede truncar decisiones.
El modelo ya usa el nivel documentado más bajo de razonamiento,low.

En el actual,el protocolo JSON se concatena después del contexto dinámico.
El experimento mueve ese protocolo antes de los datos variables y añade
x-session-affinity. La primera implementación separó el contexto en otro mensaje
system:Cloudflare lo rechazó con8007,System message must be at the beginning.
Once rechazos en la primera iteración y un diagnóstico mínimo separado; no son
fallos de interpretación del modelo ni observaciones de ahorro. Iteración2 usa
un único system y conserva los rechazos como evidencia histórica.

El compacto previo conserva acciones,campos,tipos,enum,constantes y validación
nativa,pero omite metadatos permission/effect/references y mezcla notas de campos
homónimos target/name. Aunque el backend conserva autoridad,no se promueve ese
prototipo a producción ni se lo presenta como codificación íntegra del catálogo.

Nuevo candidato ops/catalogo_qwen_sin_perdidas.py: tabla de acciones directas y
schemas compartidos. Una expansión determinista recupera exactamente todo el JSON
original:descripciones,referencias,permisos,efectos,disponibilidad y restricciones.
Prueba local en3configuraciones de descargas,con fixture de indisponibilidad.
Catálogo original90.159bytes,candidato58.701bytes:34,89%menos bytes. Esto NO es
una medición de tokens o neuronas ni acredita selección correcta por Qwen.
No recibió inferencias; la cuota autorizada de esta campaña ya se consumió.

## Presupuesto y cierre

Gasto reportado acumulado cf05:9.732,9633neuronas. No se conoce el saldo total de
la cuenta ni consumo concurrente del runtime. No se consultaron otras claves ni
se habilitaron cobros. Guardia de presupuesto comprobada después de cada respuesta:
la iteración2 alcanzó6.900,9998neurona al ejecutar la repetición,por encima del
umbral6.000 por una petición; con la primera iteración total9.732,9633. No es un
límite duro preventivo. Segunda repetición compacta quedó NOT_TESTED y no se reanuda.
No hubo error de cuota que autorice etiquetar la cuenta como agotada.

Recomendación:compactar conservando todo el contrato. El ahorro de aproximadamente
46%está medido en el prototipo anterior; la versión sin pérdidas requiere una
comprobación nueva antes de desplegar. No usar el descuento teórico de caché como
ahorro real hasta observar cached_tokens>0 y neuronas correspondientes.

Evidencia:docs/evidencia/AHORRO_QWEN_20261107/{manifest,results,diagnostic,summary}.json,
subdirectorio v2 y lossless-local.json. Scripts soloops; sin cambios de runtime,
reinicio,envíos,ejecutor ni modelos locales.

Fuentes oficiales consultadas:
- https://developers.cloudflare.com/workers-ai/features/prompt-caching/
- https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/

Cloudflare documenta afinidad y prefijos estáticos para aumentar la probabilidad
de reutilización,con métricas usage para comprobarla. Qwen publica entrada$0,45/M,
entrada en caché$0,05/M y salida$3,20/M; son tarifas,no resultados de esta campaña.
