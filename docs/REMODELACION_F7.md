# F7 · GLM real, correcciones y límites

Cierre local del 07/11/2026. Código de protocolo final: `f7e9567`.
Sin activación productiva, envíos, llamadas, cambios de servicios ni efectos
remotos de herramientas. Cloudflare recibió exclusivamente fixtures sintéticos.
Modelo conservado: `@cf/zai-org/glm-4.7-flash`, una cuenta y una consulta por turno.

## Evidencia real y evolución

Los 25 casos iniciales y sus oracles se congelaron en `75ab33d` antes de inferir.
Cubren saludo, ayuda, literales/hostilidad citada, notas, conversión y continuación,
enlaces, fuentes, listas, recados/confirmación, recordatorios, cancelación,
negación, varias tareas, typo, cambio de tema, contenido Gemini y volumen de clip.
V2 añadió un grupo y precisó los requisitos de borrador y volumen, antes de las
inferencias nuevas. No se alteró el corpus inicial ni se reabrieron campañas.

| Etapa | Intentos | Coincidencias automáticas | Mediana | Máximo |
| --- | ---: | ---: | ---: | ---: |
| Inicial | 25 | 15 | 7,655 s | 40,043 s |
| Ajuste de instrucciones/protocolo de herramientas | 20 | 16 | 5,925 s | 23,730 s |
| Ajuste temporal | 6 | 5 | 8,547 s | 14,421 s |
| Separación de roles | 7 | 5 | 4,458 s | 7,911 s |
| JSON con sobre anidado | 9 | 7 | 10,839 s | 23,727 s |
| JSON plano | 5 | 4 | 23,138 s | 30,103 s |

Hubo además una inferencia diagnóstica de JSON. Total: **73 intentos**, incluyendo
repeticiones de casos afectados y muestras de regresión. No son 73 casos únicos
ni una campaña de cobertura exhaustiva. Consumo sumado de `usage.neurons`:
**9.524,9528**, solo lo reportado; errores pueden carecer de usage. No representa
saldo, facturación ni consumo total de la cuenta. No se lanzarán más pruebas
por iniciativa de un script ni se reanudará esta comprobación automáticamente.

Las cifras de coincidencia no equivalen a éxito de herramientas. La revisión
manual detectó además en el primer oracle dos debilidades: no exigía conservar
`action_key` al aclarar una conversión ni el valor exacto de volumen. V2 los
precisó, manteniendo V1. También se revisaron preguntas incompletas, referencias
internas expuestas y opciones de ejecutar ambas tareas. Se corrigieron instrucciones
sin añadir reglas léxicas de clasificación.

El contador inicial contaba respuestas, no peticiones: el timeout del caso17
aparece con calls=0 en su histórico. Eso NO demuestra cero peticiones enviadas.
Desde el ajuste se cuentan eventos de petición HTTP separados de las respuestas;
no se oculta ese defecto del primer evaluador. No hay reintentos en el adaptador.

## Correcciones demostradas

- Respuestas que afirmaban haber guardado/programado sin seleccionar acción:
  reglas de separación de responsabilidades y definiciones de decisiones explícitas.
  Nota literal hostil del piloto conservada como dato; no se ejecuta su contenido.
- Texto del recado con prefijo añadido y frase temporal dentro del recordatorio:
  instrucciones de extracción literal, separación del momento y contenido.
- Continuación confundida con formato de origen: mensaje actual como último turno
  real, contexto del host separado y pregunta previa como turno de asistente.
- Admisión conforme al contrato: comando inválido puede entrar al frontend;
  vocativo solo al inicio; continuación propia de grupo; adjunto sin caption.
  Comandos con frontend apagado conservan sus errores originales.
- Cloudflare devolvió3030 al validar salidas de función como XML contra JSON. Se
  conservan diagnósticos privados. No se convirtió el error en PASS ni se volvió
  a consultar automáticamente. El adaptador usa ahora una salida JSON fija, con
  las definiciones cerradas en el prompt y todo el catálogo. Sigue seleccionando
  directamente acción/argumentos en una consulta; no añade etapas ni selector.
- Se observó truncación con1024tokens. Se amplió a2048, manteniendo40s de plazo.
  Búsqueda afectada pasó con1170tokens. Cualquier truncación sigue rechazándose.

Sobre de transporte normal:

```json
{"name":"select_action","action_key":"ia","arguments":{"text":"Explica las fases lunares"}}
```

Reply, clarify y no_action colocan sus campos junto a name según su schema. No
hay un segundo envoltorio arguments. El adaptador valida forma/claves y el servicio
valida de nuevo el contrato exacto; el backend conserva autoridad y efectos.

En la última muestra GLM emitió también esta forma:

```json
{"name":"ia","arguments":{"text":"Explícame por qué la luna tiene fases"}}
```

El decodificador estricto la rechazó: por eso el histórico final permanece4/5.
Se añadió una equivalencia **solo para nombres que sean claves exactas del enum
del catálogo**, con forma cerrada name/arguments. No se resuelven nombres de
handlers ni se adivinan comandos. Las cinco respuestas HTTP capturadas pasan con
el decodificador corregido en reproducción local (`F7-wire-replay.json`), **sin
nuevas inferencias**. No se presenta esa reproducción como otra corrida real5/5.

Las descripciones de parámetros del [modelo oficial](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/)
incluyen response_format. Se consultaron [compatibilidad del endpoint](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
y [modo JSON](https://developers.cloudflare.com/workers-ai/features/json-mode/).
La lista general de modelos de esta última página no enumera GLM; el soporte de
json_object aquí se acredita por HTTP200 observado en esta cuenta/modelo, no por
inferir una garantía de aquella lista.3030 no figura en la [tabla de errores](https://developers.cloudflare.com/workers-ai/platform/errors/):
el diagnóstico concreto procede del payload observado, no de atribuirle un nombre
oficial no documentado.

## Backend y comprobaciones locales

192 pruebas de regresión pertinentes pasaron tras los primeros ajustes. Después
del cambio final de protocolo pasaron52pruebas enfocadas (frontend, presentación
natural e integraciones), y dos pruebas adicionales de extremo a extremo:

- Respuesta GLM capturada → HTTP doble → servicio → worker → nota literal enSQLite.
- Pregunta propia sintética → entrega local doblada → reinicio → respuesta GLM
  capturada «a PDF» → archivo retenido → PDF válido de una página. Duplicado no
  convierte de nuevo. Dos turnos, dos consultas dobladas, ninguna tras el efecto.

Además se adoptaron cuatro propuestas reales capturadas con DB/fixtures propios:
notas Markdown/hostil, PNG→PDF y recordatorio con600segundos exactos. Outbox local;
ningún ACK de proveedor real. Evidencia `F7-replay-local.json` y `F7-e2e.txt`.

## Límites y siguiente fase

Se completa F7 como comprobación y corrección acotadas. No se afirma fiabilidad
universal ni que las155variantes hayan pasado por el modelo real. La muestra
final mantuvo latencia de7,827–30,103s, elevada para algunas peticiones, aunque
bajo el plazo elegido. Pueden ocurrir errores o truncación; se avisa sin ejecutar
ni repetir efectos. No hay fallback de modelo, cuentas o inferencias de reparación.
Recepción humana y render de WhatsApp permanecen NO_PROBADO.

F8 sigue pendiente de encargo de despliegue: respaldo propio, esquema20 compatible,
frontend inicialmente apagado, activación reversible y salud observada. Nada de
este cierre reinició producción ni modificó el perfil operativo.
