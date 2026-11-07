# Modelos alternativos de Cloudflare · 07/11/2026

El propietario encargó probar otros modelos y dejar el mejor según evidencia.
La autorización incluye consumir la cuota disponible y,cuando exista un ganador
contrastado,configurarlo. No se elegirá por nombre,tamaño o rechazos de cuota.
Este experimento es nuevo;no reabre la comparación de catálogos cancelada.

## Candidatos comprobados en documentación oficial

Todos estos candidatos declaran selección de herramientas y contexto suficiente
para el catálogo completo de155variantes. Se conserva ese catálogo y el protocolo
JSON de Botsky;ningún handler ni herramienta de dominio se ejecuta en la prueba.

| Modelo | Perfil de prueba | Fuente |
| --- | --- | --- |
| Gemma4 26B A4B IT | Predeterminado | [Ficha oficial](https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/) |
| Llama4 Scout17B16E | Predeterminado,sin razonamiento anunciado | [Ficha oficial](https://developers.cloudflare.com/workers-ai/models/llama-4-scout-17b-16e-instruct/) |
| GPT-OSS20B | Predeterminado,razonamiento medio anunciado | [Ficha oficial](https://developers.cloudflare.com/workers-ai/models/gpt-oss-20b/) |
| Qwen3.8 27B | reasoning_effort=low,parámetro documentado | [Ficha oficial](https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/) |
| GLM4.7Flash | Control productivo actual | [Ficha oficial](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/) |

Otros modelos de selección de herramientas del catálogo incluyen GPT-OSS120B y
Llama3.3 70B FP8 Fast. No se incluyeron en este cribado:el primero consume más
cuota de entrada que20B según precios publicados;el segundo tiene contexto24k,
con margen muy estrecho para el catálogo/ctx/salida actuales. No se atribuye menor
calidad por ello. [GPT-OSS120B](https://developers.cloudflare.com/workers-ai/models/gpt-oss-120b/),
[Llama3.3](https://developers.cloudflare.com/workers-ai/models/llama-3.3-70b-instruct-fp8-fast/).

La gratuidad es una asignación compartida de10.000neuronas al día,no uso ilimitado
ni10.000por modelo. Algunos modelos,comoGLM5.3 oKimiK2.6,exigen facturación;no se
probaron ni se activaron planes/créditos. Reinicio oficial diario00:00UTC.
[Precios oficiales](https://developers.cloudflare.com/workers-ai/platform/pricing/).
No se pudo leer plan/saldo de esta cuenta:consulta de suscripciones403. No se
infiere saldo exacto a partir de nuestras métricas ni que todas las llamadas
históricas deban haber producido cargos.

## Diseño congelado y resultado observado

Manifest/oracles: docs/evidencia/MODELOS_CF_20261107/manifest.json,commitbee78cf.
Dos casos críticos por modelo (nota literal hostil y video general);ampliación a
cuatro casos adicionales solo de dos finalistas yGLMcontrol. Prioridad:aciertos;
desempate:mediana de latencia. Mismo catálogo completo,temperatura0,2048tokens,
plazo40s,cuenta única yorden rotado por caso. Qwen usa low explícito porque su
predeterminado anunciado es xhigh;se comparan perfiles declarados,no arquitecturas
a parámetros idénticos de razonamiento que algunos modelos no admiten.

Resultado:10peticiones de cribado rechazadas conHTTP429,código4006. Cero inferencias
exitosas,cero herramientas ejecutadas,cero finalistas. No es0/2de precisión para
cada modelo:es falta de cuota para poder evaluarlos.

Una petición diagnóstica mínima adicional confirmó el mensaje exacto del proveedor:
`you have used up your daily free allocation of 10,000 neurons`. No se enviaron
más inferencias después del diagnóstico. La petición diagnóstica no integra los
10intentos de cribado. No se conserva razonamiento,cabeceras o secretos públicos.

El adaptador base reconocía3036como cuota,pero4006salió como429genérico:por eso el
cribado no paró en el primer rechazo. Se corrigió la guardia solo del evaluador
para4006cuando el mensaje identifica daily free allocation. Dos pruebas locales
pasan;la segunda verifica una sola petición y pausa sin otra consulta. No se
modificó ni desplegó el runtime productivo para esta corrección.

El histórico del runner decía finished sin finalistas;se preservó. La adjudicación
correcta de esta comprobación es BLOCKED_BY_PROVIDER_DAILY_QUOTA,no una comparación
completada ni un rechazo por calidad de los modelos.

## Pendiente

Usar cuota cuando el proveedor vuelva a permitir inferencias,realizar una
comprobación nueva autorizada con el manifest/oracles preparados ycomparar
selección,literales,continuidad,confirmación,Gemini,latencia yuso. Después configurar
el ganador probado con respaldo yreversión propios,conservando catálogo directo
ypermisos. La autorización del propietario ya contempla esa elección/despliegue;
lo que falta es evidencia,no permiso para consumir neuronas.

No hay ganador observable que permita sustituirGLM ahora. Producción conserva
GLM ysu configuración;la cuota agotada también limita su frontend natural hasta
que el proveedor permita inferir. No se programó reanudación automática,no se
cambia de cuenta,no se habilita facturación yno se reabre el A/Bcancelado.
