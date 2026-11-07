# Entrada natural con tool calling · investigación y propuesta

Fecha: 07/11/2026. Encargo: investigar a profundidad una entrada donde un LLM
interpreta lenguaje natural, propone una herramienta fija y deja de intervenir;
el backend valida, ejecuta y presenta. Investigación completada; implementación,
calidad de interpretación con proveedor y despliegue NO_PROBADOS.

Este encargo sustituye la decisión anterior de investigar únicamente sintaxis
explícita para esta propuesta. No reactiva el clasificador antiguo ni importa
runtime, datos, modelos entrenados o historial de Zhana. No modifica producción.

## Resultado recomendado

```text
Mensaje dirigido a Botsky
  → identidad/frescura/permisos básicos y deduplicación
  → interpretación Gemini con declaraciones de funciones
  → propuesta estructurada durable
  → validación local de argumentos y referencias
  → permisos/confirmaciones y resolución de contexto
  → operación fija del backend
  → presentador WhatsApp + outbox existentes
```

El intérprete acaba al entregar la propuesta. No recibe resultados de herramientas,
no redacta el mensaje de éxito y no decide reintentos. Los comandos pueden seguir
como compatibilidad y operación técnica; la experiencia cotidiana será natural.

## Fuentes primarias y qué verifican

1. [SDK Python Google Gen AI](https://googleapis.github.io/python-genai/): permite
   declarar funciones manualmente, recibir `response.function_calls` y desactivar
   ejecución automática mediante `AutomaticFunctionCallingConfig(disable=True)`.
   Su ejemplo realiza otra consulta para redactar la respuesta; nuestra aplicación
   terminará antes de ese paso. No hace falta un ciclo de agente.
2. [Function calling de Google](https://ai.google.dev/gemini-api/docs/function-calling):
   funciones con nombres, descripciones y parámetros tipados; la aplicación debe
   validar la propuesta. Distinguir GenerateContent e Interactions: sus ejemplos
   y configuración no se copian intercambiablemente.
3. [Guía de Google Cloud](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tools/function-calling):
   `ANY` puede devolver una o varias llamadas; limitar a una es responsabilidad
   nuestra. Recomienda herramientas relevantes, idealmente 10–20 activas; no es
   un límite duro del protocolo. También recomienda enums y contexto temporal.
4. [Diseño de herramientas, Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents):
   descripciones precisas, separación por dominios y evaluación con resultados
   verificables. Una descripción del propósito no sustituye un contrato.
5. [Workflows y agentes, Anthropic](https://www.anthropic.com/research/building-effective-agents):
   distingue orquestación fija y autonomía; aconseja empezar con APIs directas y
   aumentar complejidad cuando los resultados medidos la justifiquen.

Consultadas el 07/11. Las recomendaciones siguientes son diseño para Botsky,
no garantías de precisión o latencia de esos proveedores.

## Hallazgos del código propio

Inspección local, sin invocaciones de proveedores ni datos productivos:

- `commands/registry.py`: 155 rutas, 146 operaciones distintas y 34 familias.
  Las rutas ya declaran campos, constantes, permisos, efectos y confirmaciones.
- `commands/types.py`: tipos, enums, límites y conversión desde tokens; no es
  todavía un validador de objetos JSON nativos. Debe conservar booleanos,
  enteros, arrays y literales sin convertir todo a cadenas.
- `commands/router.py`: `ParsedCommand.canonical()` guarda versión, operación y
  argumentos; `_validate()` añade incompatibilidades entre campos.
- `app.py:admit`: primero parser; después mención/conversación y espera de archivo.
  Autoriza operación/permisos y consulta el modo del bot antes de encolar.
- `store.py:admit`: `prepare()` corre dentro de `BEGIN IMMEDIATE`. Consultar al
  proveedor ahí bloquearía escritores SQLite durante la latencia de red.
- `domains/ai.py`: menciones y citas propias activan hoy conversación. Su historial
  contiene texto; no debe ser la autoridad para resolver selecciones o confirmar.
- `adapters/gemini.py`: contenido exclusivamente; `tools=[]`, ejecución automática
  apagada y rechazo expreso de function calls. Conviene un adaptador intérprete
  independiente, con otro contrato y sin acceso a objetos ejecutables.
- `domains/downloads.py` y `adapters/downloads.py`: búsqueda implementada en
  `youtube`, `pornhub`, `xnxx`, `adult`; fuentes adultas tienen guardia explícita.
  Otros proveedores admitidos como URL no implican búsqueda textual disponible.
  El campo `source` del registro usa `youtube` por defecto.
- Entorno propio: `google-genai==2.33.0`. Inspección de tipos instalada confirma
  `FunctionDeclaration.parameters_json_schema`, `FunctionCallingConfig.mode`,
  `allowed_function_names` y `AutomaticFunctionCallingConfig.disable`.
  Eso acredita interfaz local; no compatibilidad remota del modelo configurado.

## Contrato del intérprete

Propuesta: `GeminiInterpreter.interpret(message, context, declarations)` devuelve
una de estas decisiones validadas por el host:

| Decisión | Comportamiento del backend |
| --- | --- |
| Función de dominio conocida + argumentos | Construye petición tipada y valida |
| `request_details` | Guarda borrador sin efectos y pregunta por el dato faltante |
| `route_conversation` | Deriva al canal de contenido cuando el usuario pide conversación |
| `no_action` | No ejecuta; silencio o explicación breve según contexto |

Las tres últimas son declaraciones de control, no acceso genérico al ejecutor.
`request_details` identifica dominio/campos y opciones válidas; el host compone la
pregunta. No dejar que un texto libre invente botones, fuentes o capacidades.

Configuración inicial propuesta: GenerateContent con declaraciones manuales,
`ANY`, ejecución automática deshabilitada y una sola llamada aceptada por el host.
Rechazar múltiples propuestas antes de cualquier efecto, funciones desconocidas,
argumentos extra, salida truncada o bloqueada y tipos incompatibles. No ejecutar
la primera llamada y descubrir después que había otras.

No dar `eval`, shell, Python, SQL, HTTP arbitrario ni una función genérica
`execute(command)`. Tampoco producir `/comandos` y volver a parsearlos: introduciría
comillas, escapes y ambigüedades innecesarias. Extraer un validador común para
objetos nativos y parser, incluyendo constantes y restricciones cruzadas.

Identidad, cuenta, chat, permisos, época y recibo los añade el host. El modelo no
puede elegirlos. Destinatarios, archivos y selecciones serán referencias a objetos
propios comprobables; una cadena inventada nunca concede autoridad.

## Catálogo amplio: decisión que requiere medición

Comparar dos candidatos antes de fijar arquitectura:

A. Una inferencia con catálogo compacto de funciones semánticas agrupadas por
dominio, acciones y schemas específicos. Evitar una bolsa de argumentos libre.

B. Selección de dominio en una primera inferencia, seguida por una inferencia con
sus funciones concretas. El modelo interviene dos veces antes de ejecutar y cero
veces después. La selección inicial debe admitir varios dominios candidatos o
aclaración; un filtro equivocado no puede ocultar silenciosamente la herramienta.

Recomendación: probar A como objetivo de menor latencia y B como alternativa si
la confusión del catálogo lo justifica. No enviar 155 declaraciones extensas sin
medir, ni reemplazar comprensión por un diccionario de palabras clave. La selección
por permisos/capacidades reduce exposición, pero no sustituye autorización final.

No hace falta incorporar MCP, LangChain o un framework de agentes para este flujo.
Un catálogo propio y el SDK existente son suficientes como punto de partida.

## Contexto y experiencia cotidiana

- Privado: procesar mensajes de usuarios autorizados según modo. Grupo: mención,
  respuesta a Botsky o interacción propia pendiente; no actuar ante charla ajena.
- Contexto acotado por actor/chat/cuenta/época y TTL: vistas entregadas, borrador,
  adjuntos disponibles y fecha/zona configurada. Nunca IDs de otros usuarios.
- «Baja el segundo»: intérprete propone elegir opción 2; backend resuelve la vista
  propia entregada. Con dos listas posibles, pregunta cuál. No vuelve a buscar.
- «Hazlo PDF» como respuesta a un archivo: backend comprueba adjunto/cita y formato.
- «Recuérdame mañana a las ocho»: resolver fecha con reloj y zona propios; preguntar
  si la hora resulta ambigua. No fijar zona por idioma.
- «Sí»: solo puede confirmar una propuesta propia vigente y ligada a su revisión;
  nunca aceptar consentimiento porque un LLM lo declaró. Si hay varias, aclarar.
- Una petición de búsqueda puede proponer fuente según intención y contexto entre
  las fuentes realmente disponibles. Si una distinción cambia sustancialmente el
  contenido y sigue ambigua, una pregunta breve. Las guardias del proveedor mandan.
- Resultados por presentadores propios: archivo, collage, lista o texto breve.
  Quitar ruido visual es trabajo adicional del presentador; tool calling por sí
  solo no arregla formato, verbosidad o metadatos inútiles.

Las operaciones cuyo propósito es IA (resumir, responder, componer voz) conservan
su proveedor dentro del dominio. «El intérprete no vuelve a intervenir» no elimina
la generación que constituye el resultado solicitado. Separar ambos roles.

## Durabilidad e integración concreta

1. Preflight local y registro único de entrada antes de inferencia; limitar
   concurrencia, presupuesto y longitud por actor/chat.
2. Trabajo durable de interpretación con claim/lease, versión de catálogo/modelo
   y snapshot de contexto. Hacer red fuera de transacciones y fuera de la cola
   serial de ingreso; un chat lento no detiene todos los demás.
3. Guardar propuesta y validación; CAS contra revisión del borrador/contexto.
   No regenerar una propuesta ya fijada cuando se recupera un recibo.
4. Justo antes del efecto, revalidar permisos, modo, referencias, TTL y confirmación.
   Reutilizar reserva de jobs y recibos de efecto existentes.
5. Backend ejecuta y genera el plan de presentación durable. No devuelve resultados
   al intérprete. Timeout de entrega sigue incierto, sin reintentos automáticos.
6. Timeout de inferencia sin propuesta: mensaje breve sin efectos. Una nueva
   inferencia, si se permite, solo antes del efecto y con política acotada; nunca
   confundir ese reintento con repetir una descarga, compra o envío.

Separar texto actual de citas, OCR, QR y archivos como datos no confiables. No
atribuir a una orden dentro de un PDF el consentimiento del remitente. Limitar el
contexto expuesto y mantener permisos deterministas aunque la propuesta parezca
correcta. El schema válido no demuestra que se entendió la intención.

## Plan comprobable de construcción

| Bloque | Entrega y criterio |
| --- | --- |
| T0 · Contratos | Inventario completo, schema común y corpus de expectativas congelado |
| T1 · Adaptador | SDK con doble; una propuesta, cero ejecuciones automáticas, cero vueltas posteriores |
| T2 · Flujo durable | SQLite propia; duplicados, cortes, cancelación, orden y permisos revocados |
| T3 · UX contextual | Selecciones, adjuntos, datos faltantes y confirmaciones naturales sin hashes visibles |
| T4 · Evaluación | Comparación A/B con modelo configurado, fixtures propios y efectos capturados |
| T5 · Integración | Activación reversible por perfil; respaldo y despliegue bajo encargo de ejecución |

T4 requiere concretar una comprobación nueva de proveedor; esta investigación no
la ha ejecutado. T5 no se activa por redactar el documento. No reutilizar campañas
históricas como resultado de este intérprete.

Corpus: cubrir todas las operaciones; incluir paráfrasis mexicanas, faltas,
negaciones, bromas, charla sin petición, órdenes compuestas, fechas, referencias
ambiguas, texto literal, fuentes no soportadas, permisos y datos hostiles en citas.
Separar ejemplos de ajuste de un conjunto reservado de evaluación.

Medir selección de operación, argumentos por campo, fidelidad literal, resoluciones
de contexto, aclaraciones necesarias/innecesarias, activaciones falsas, latencias
p50/p95 y tokens/coste. Validar efectos con backend/dobles y estados observados;
el modelo no se califica a sí mismo. Registrar bloqueos de proveedor separados.

Puertas propuestas: cero bypass de permisos o confirmación, cero efectos duplicados,
cero llamada ejecutada ante propuesta inválida/múltiple y cero consulta al intérprete
después de ejecutar. Fijar umbrales semánticos por riesgo antes del benchmark;
no prometer una precisión global sin medirla. Persistir catálogo, modelo, parámetros
y adjudicaciones saneadas; no almacenar secretos en evidencia.

## Alcance real del cierre

Se revisaron contratos, código y tipos instalados y se consultaron fuentes oficiales.
No se implementó el intérprete, no se evaluó precisión con Gemini, no hubo entregas,
llamadas o cambios de servicios. Producción conserva su comportamiento anterior.
