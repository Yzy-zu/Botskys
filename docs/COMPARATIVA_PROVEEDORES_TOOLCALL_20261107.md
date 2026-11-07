# Proveedor gratuito para el intérprete de Botsky

Investigación: 07/11/2026. Fuentes primarias, código propio y medición local.
No se realizaron inferencias autenticadas, altas, compras, envíos ni despliegues.
Esta comparación sustituye la recomendación preliminar de probar únicamente
Groq contra Gemini. Distingue hechos publicados, cálculo y aspectos no medidos.

Suplemento posterior autorizado: `PILOTO_CLOUDFLARE_TOOLCALL_20261107.md` registra
12inferencias realesCloudflare,11oraclesPASS/1FAIL y consumo/latencia observados.
No modifica los límites documentales de esta comparación ni prueba otros proveedores.

## Decisión

Por presupuesto cero recurrente, volumen calculable y tratamiento de datos,
**Cloudflare Workers AI con GLM-4.7-Flash es la primera opción documental para
construir el candidato de Botsky**. Groq con GPT-OSS-120B es la referencia alternativa
con cuota explícita, pero su techo de tokens gratis es bajo para prompts extensos.
Z.ai con GLM-4.7-Flash es un candidato real a coste cero que merece una prueba:
sus límites efectivos no se pudieron verificar sin cuenta.

No hay ganador de precisión acreditado: no se ha medido comprensión de las
146 operaciones en español con estos endpoints. No desplegar el candidato por
esta recomendación documental ni convertir cifras comerciales en un benchmark.

Para elegir hoy un proveedor por condiciones verificables: Cloudflare. Para
afirmar cuál interpreta mejor: hace falta el ensayo comparativo descrito abajo.
Gemini sigue siendo válido, pero no se puede calcular su capacidad gratuita real
sin conocer la cuota del proyecto. No recomendar local en el servidor compartido
actual como primer paso: 2vCPU ARM, 11GiB RAM y swap4GiB ocupada al observar.
No se instaló ni ejecutó modelo local; esto es una decisión de infraestructura,
no una medida de su rendimiento.

## Ofertas actuales contrastadas

| Proveedor | Qué es gratis realmente | Datos/limitaciones relevantes | Decisión para Botsky |
| --- | --- | --- | --- |
| Cloudflare Workers AI | 10.000 neuronas/día renovables; Free corta al agotarse | Herramientas en GLM-4.7-Flash y Gemma4; modelos premium concretos requieren pago | Primer candidato por volumen calculable |
| Groq | Free con límites por modelo/organización | GPT-OSS20B/120B y Qwen3.8:30RPM,1.000RPD,8.000TPM,200.000TPD publicados | Alternativa; el límite de tokens suele dominar |
| Z.ai | GLM-4.7-Flash y4.5-Flash: entrada/salida/cache a precio cero | Límite efectivo en consola; no equivale a capacidad ilimitada | Candidato condicionado a cuota/acceso |
| Gemini Developer API | Hay nivel gratuito; comprobar oferta del modelo vigente | Límites activos por proyecto en AI Studio; no por clave | Mantener para comparación; capacidad desconocida |
| OpenRouter | Variantes `:free`:50RPD sin compra,20RPM | 1.000RPD requiere compra acumulada de créditos; otros modelos$0 tienen condiciones propias | Útil para evaluar; débil como base sin gasto |
| SambaNova | Free sin método de pago | 20RPD por modelo,20RPM,200.000TPD en modelos publicados | Demasiado poco para principal |
| Cerebras | Prueba$5/30d con método de pago verificado | La documentación actual niega nivel gratuito renovable | Excluir para presupuesto cero permanente |
| Mistral | Free para Vibe/Studio | Documentación actual: API requiere activar facturación/PAYG | Excluir API directa gratuita |
| Hugging Face Inference Providers | Cuenta Free sin créditos mensuales | Hace falta comprar créditos o suscripción | Excluir para este requisito |
| Cohere | Trial key gratis | Prohíbe uso productivo/comercial con trial key | Excluir para Botsky productivo |
| Together | API ordinaria con compra mínima$5 | Promociones con solicitud no son una cuota renovable garantizada | Excluir como solución gratis estable |
| NVIDIA hosted APIs | Presentadas como prueba/prototipado | No se acreditó una oferta recurrente gratuita para producción | No tratar como principal productivo |

Fuentes: [Cloudflare precios](https://developers.cloudflare.com/workers-ai/platform/pricing/),
[Groq cuotas](https://console.groq.com/docs/rate-limits),
[Z.ai precios](https://docs.z.ai/guides/overview/pricing),
[Gemini cuotas](https://ai.google.dev/gemini-api/docs/rate-limits?authuser=2),
[OpenRouter límites](https://openrouter.ai/docs/api_reference/limits),
[SambaNova](https://docs.sambanova.ai/docs/en/models/rate-limits),
[Cerebras](https://inference-docs.cerebras.ai/support/rate-limits),
[Mistral](https://docs.mistral.ai/admin/billing-usage/usage-limits),
[Hugging Face](https://huggingface.co/docs/inference-providers/en/pricing),
[Cohere](https://cohere.com/pricing),
[Together](https://support.together.ai/articles/1862638756-changes-to-free-tier-and-billing-july-2025),
[NVIDIA](https://www.nvidia.com/en-us/data-center/products/ai-enterprise/get-started/).

## Modelos concretos y compatibilidad

**Cloudflare:** GLM-4.7-Flash declara function calling,131.072tokens y ZDR.
Gemma4-26B-A4B declara function calling,256.000tokens y ZDR; alternativa si GLM
falla en español/contexto. GPT-OSS120B también existe, con mayor consumo por tarea.
El Qwen3-30B económico tiene retirada prevista20/11/2026: no empezar ahí.
Usar REST desde Botsky: no hace falta mudar su runtime a Workers.
Fuentes: [GLM](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/),
[Gemma](https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/),
[GPT-OSS](https://developers.cloudflare.com/workers-ai/models/gpt-oss-120b/),
[Qwen/deprecación](https://developers.cloudflare.com/workers-ai/models/qwen3-30b-a3b-fp8/).

**Groq:** usar funciones locales; no Compound, herramientas integradas o MCP remoto
con ejecución del proveedor. GPT-OSS120B y20B admiten tools; Qwen3.8 también y puede
desactivar thinking (`reasoning_effort=none`), pero figura Preview.
No usar el modelo safeguard como intérprete general. Llama3.3 figura Enterprise:
no asumir acceso gratis por tutoriales viejos. El soporte anunciado de JSON
estricto es de `response_format`; la documentación excluye combinar Structured
Outputs con tools. Hay dos contratos posibles: function call validada localmente,
o decisión estructurada estricta sin `tools`; comparar ambos si hace falta.
Fuentes: [herramientas](https://console.groq.com/docs/tool-use/overview),
[JSON estructurado](https://console.groq.com/docs/structured-outputs),
[Qwen](https://console.groq.com/docs/model/qwen/qwen3.8-27b),
[Llama](https://console.groq.com/docs/model/llama-3.3-70b-versatile).

**Z.ai:** la página de la serie incluye Flash gratis y Function Call. La referencia
genérica expone128funciones y solo `tool_choice=auto`; no asumir `required`.
Además el enum del esquema de chat omite Flash aunque la tabla de precios lo
ofrece: discrepancia documental que exige comprobar el modelo exacto por API.
La página de límites redirige a consola; no verificamos RPM/RPD/concurrencia.
Fuentes: [serie4.7](https://docs.z.ai/guides/llm/glm-4.7),
[referencia](https://docs.z.ai/api-reference/llm/chat-completion),
[límites](https://docs.z.ai/api-reference/rate-limit).

**Gemini:** el SDK instalado sirve para este diseño. La página de precios se
consultó mediante búsqueda oficial/indexada; varias aperturas directas fallaron
por redirección/formato. No fijar modelo nuevo ni cuota basándose en ese extracto:
observar catálogo/acceso actual del proyecto. No confundir API con suscripción
de chat o AGY. [Precios oficiales](https://ai.google.dev/gemini-api/docs/pricing),
[cuotas](https://ai.google.dev/gemini-api/docs/rate-limits?authuser=2).

## Cálculo de capacidad útil, no benchmark

Escenario ilustrativo: **4.000tokens entrada +200salida por tarea, sumando los dos
pases**, sin caché, errores, más razonamiento u otros usuarios de la cuenta.
Los tokens son supuestos, no mediciones del prompt final ni previsión de tráfico.

| Opción | Techo diario calculado para ese escenario |
| --- | --- |
| Cloudflare GLM4.7Flash | 341tareas |
| Cloudflare Gemma4-26B | 239tareas |
| Groq GPT-OSS120B/20B o Qwen3.8 | 47tareas por presupuesto de tokens |
| OpenRouter variantes`:free` sin compra | 25tareas por presupuesto de solicitudes |
| SambaNova un modelo Free | 10tareas por presupuesto de solicitudes |
| Z.ai / Gemini | No calculable sin cuota efectiva |

Fórmulas: Groq `min(floor(1000/2),floor(200000/4200))`.
Cloudflare GLM `floor(10000/(4000*5500/1e6 +200*36400/1e6))`.
Gemma usa9091/27273neuronas por millón de tokens entrada/salida. Tasas de la tabla
de precios, que redondea ligeramente distinto de algunas fichas de modelo.
Estos techos omiten límites por minuto, saturación y uso compartido. Reasoning
adicional baja el techo. Caché se mide aparte, no se cuenta como ahorro garantizado.

La cifra anunciada de1000solicitudes/día de Groq no implica1000peticiones útiles
de Botsky. Para un pase de2000+100tokens, el cálculo da95; para3000+200,62.
La doble inferencia añade consumo, pero importa el total de tokens, no solo el
número de pases. Un solo pase con un catálogo enorme también puede salir peor.

## Qué implica el catálogo de146operaciones

Medición offline reproducible:155rutas,146operaciones,34familias. Una declaración
mínima por ruta ocupa40.428bytesUTF8; la familia mayor tiene17rutas/4.110bytes.
No se convirtieron caracteres a tokens. Son schemas de sondeo, sin todas las
descripciones semánticas o restricciones cruzadas; no son una implementación.
Ver `evidencia/PROVEEDORES-TOOLCALL-20261107/analisis_local.py` y su JSON.

Groq admite un máximo128funciones por petición:
[referencia](https://console.groq.com/docs/api-reference). El catálogo entero
no cabe como146declaraciones distintas. Recomiendo selección de dominio y después
funciones específicas, con posibilidad de aclarar/seleccionar otro dominio antes
de ejecutar. Con el inventario actual cada familia tiene17o menos rutas; revisar
agrupaciones semánticas para no confundir nota/agenda/escuela/archivos.

Al añadir una operación: registrar schema/descripcion, familia, autorización y
efecto; generar catálogo versionado y añadir ejemplos positivos/negativos al
corpus. Sin reentrenamiento. Al crecer un dominio, subdividir y medir errores de
selección; no permitir que la reducción del catálogo oculte capacidades sin avisar.

## Datos, privacidad y límites del contenido

Groq: no retiene contenido por defecto; excepciones de fiabilidad/abuso hasta30d
y ZDR configurable. [Datos](https://console.groq.com/docs/your-data).
Cloudflare: no entrenamiento con contenido; inferencia ordinaria sin retención,
con excepciones legales/seguridad y almacenamiento elegido por cliente.
[Datos](https://developers.cloudflare.com/workers-ai/platform/data-usage/).
Z.ai: distinguir política del chat y DPA API; el DPA afirma procesamiento como
encargado y ausencia de almacenamiento de contenidos de API. No adjudicar a la
API las condiciones del chat individual.
[DPA en política](https://docs.z.ai/legal-agreement/privacy-policy).
Gemini: servicios gratuitos pueden usar entradas/salidas para mejora y revisión;
hay condiciones regionales específicasEEE/Suiza/ReinoUnido. No inferir región del
propietario por idioma o ruta del servidor.
[Términos](https://ai.google.dev/gemini-api/terms?authuser=00).

Para todos: enviar mensaje y contexto mínimo con referencias opacas propias,
sin secretos ni historial completo del grupo. Una clave deASR válida no demuestra
plan/gratuidad/acceso del mismo proveedor para interpretación. No asumir que un
modelo abierto hospedado permite cualquier contenido: servicio y modelo conservan
sus términos/filtros. Peticiones adultas permitidas por el backend se incluyen
como categoría de evaluación de rechazos, sin intentar eludir filtros.

## Calidad: lo que la búsqueda permite concluir

La [fuente originalBFCL](https://gorilla.cs.berkeley.edu/leaderboard.html) tiene
fecha12/04/2026 en la consulta y evalúa varias categorías; no demuestra precisión
de un endpoint gratis actual en146operaciones propias, español coloquial, permisos
y referencias de WhatsApp. No copiar un ranking de agregadores más recientes como
si fuera evidencia de nuestros candidatos. Los tokens/segundo anunciados por
proveedores tampoco son latencia finalp95 desde este servidor.

Investigación documental descarta ofertas y descubre incompatibilidades. Ganador
semántico/latencia/disponibilidad real queda NO_MEDIDO, no «todos equivalentes».

## Comprobación concreta que cerraría la elección

1. Credenciales propias y plan/gratuidad verificados para Cloudflare y Groq;
   acceso/cuotas paraZ.ai yGemini. SoloAPI, sin cuentas nuevas ni facturación por
   automatismo. Perfil de evaluación separado, cero herramientas reales ejecutables.
2. Congelar corpus: al menos3paráfrasis por146operaciones, más negaciones,
   faltantes, contexto ambiguo, grupos sin invocación, citas hostiles y rechazo de
   proveedor. Etiquetas humanas o contratos fijos, nunca modelo como único juez.
3. Mismos schemas, contexto y política de aclaración. Capturar selección/argumentos
   contra oracles; medir latencias end-to-end y tokens reales, no streams parciales.
4. Usar corpus pequeño común en varios días: las cuotas gratis no permiten
   garantizar una campaña grande en una tanda. Respetar límites y no crear claves
   para evadirlos. Registrar errores/cuota por separado de errores semánticos.
5. Elegir por exactitud y activaciones falsas, después p95 y volumen útil gratuito.
   Cero bypass, identidad inventada o efecto duplicado. Un schema correcto no
   certifica que el usuario pidió la acción.

Esta investigación no ejecutó esa comparación autenticada: quedan pendientes el
acceso de cuentas y la medición semántica. Sí completó la investigación pública,
inventario local y aritmética reproducible que sustentan el candidato recomendado.
