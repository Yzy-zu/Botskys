# Nueva campaña AGY · 07/11/2026

Encargo del propietario: volver a probar Botsky herramienta por herramienta con
agentes AGY CLI, usando explícitamente `gemini-3.8-flash-medium`.
Campaña independiente de las cerradas el 06/11; producto de referencia `d5cef30`.

Una sesión independiente por cada una de las 30 herramientas; máximo tres sesiones
simultáneas para limitar consumo y contención de motores. Cada agente propone
comandos y expectativas antes de su ejecución y recibe evidencia para su informe.
AGY no dispone de herramientas nativas, shell, archivos del repositorio, secretos
de Botsky, perfiles activos ni acceso al ejecutor. Su autenticación nativa existe
solo dentro de su sandbox y se retira al cerrar.

El backend usa SQLite por herramienta, datos sintéticos y los adaptadores del
producto. Las respuestas y los archivos se capturan localmente; no se envían
mensajes a personas ni se altera el webhook o el runtime productivo. Consultas y
proveedores de contenido pueden ser reales. Drive, grupos y Minecraft no admiten
escrituras en esta campaña; llamadas y navegador no se activan. Sus guardias se
registran aparte de una prueba exitosa de esas capacidades.

Los agentes pueden revisar exactitud contra contenido sintético, formato, claridad
y continuidad de las respuestas. Esto reduce el trabajo manual; no sustituye la
observación de recepción, reproducción o interacción humana en el teléfono.
No se corrige producto durante el descubrimiento. Una discrepancia `SUSPECTED`
requiere contraste: no es automáticamente un bug confirmado.

El directorio privado nuevo guarda prompts, eventos, casos originales, resultados,
artefactos y reportes. El resumen saneado vive en `docs/evidencia/AGY-20261107/`.
Los históricos siguen intactos. El ejecutor exige `--run` y un directorio nuevo;
no reanuda efectos o campañas automáticamente. Se conserva el umbral de cuota5%.

## Resultado de cierre

Campaña terminada, sin reanudación automática. **30 sesiones, 30 informes y
378 casos registrados**, todos con `gemini-3.8-flash-medium` confirmado en el evento
nativo de inicio. Tres tandas con máximo tres testers simultáneos. Directorio
privado: `private/retest-agy-20261107/`.

| Tipo de caso propuesto | PASS | SUSPECTED | BLOCKED |
| --- | ---: | ---: | ---: |
| Positivo | 165 | 61 | 18 |
| Negativo | 43 | 76 | 6 |
| Guardia/bloqueado | 0 | 4 | 5 |
| Total | 208 | 141 | 29 |

PASS significa cumplimiento del oráculo congelado y comprobaciones disponibles;
no garantiza calidad semántica universal. Las **141 discrepancias no son141bugs**.
Los agentes propusieron35claims sin adjudicar; algunos describen expectativas
incompatibles con contratos o incluso ausencia de fallo. No se presentan como
35defectos. Se conservan en el índice para contraste posterior.

Se inspeccionaron39artefactos: WebP12, WebM1, MP4 2, MP3 4, Ogg8, PDF7, DOCX1,
TXT2, XLSX1 y ZIP1. Se observaron109/154rutas con recibo y resultado; quedan
45rutas y56campos sin observar. Una ruta observada puede terminar en guardia:
ese recuento no acredita el efecto de negocio. Hay listado por ruta/campo.

**Cierre operativo verificado:**30SQLite con integridad/FK correctas y cero jobs
running; permisos de efectos retirados de los perfiles efímeros; autenticación
copiada de los sandboxes eliminada. Los32POST de mensajería registrados son
fixtures capturados: **ceroPOST al proveedor WhatsApp**. Producción mantiene salud,
PID y cero reinicios de ambos supervisores igual que al inicio. Sin cambios de
producto, webhook, servicios o perfiles activos; solo arnés, documentación/evidencia.

Ajustes propios del arnés: usar referencias de integración actuales sobre DB nueva,
forzar captura aun si un agente pide publicar, retirar supuestos históricos de OAuth,
guardar propuesta original antes de aplicar restricciones y entregar al revisor un
suplemento de resultado más amplio. Las cadenas `output:cNN` se excluyen porque el
arnés anterior no implementaba la cita requerida; quedan NOT_TESTED. El feedback
base conserva su recorte histórico a1700caracteres; el suplemento admite12000 por
resultado y no acredita contenido omitido. No se cambió el runner histórico.

Limitaciones adicionales: el evaluador heredado puede clasificar un rechazo de
adjunto como PASS negativo sin comparar cada detalle del código esperado. Las
comparaciones finas deben contrastarse con resultado/oráculo original. Las duraciones
del estado de herramienta empiezan de nuevo al lanzar el backend: no son latencia
completa de AGY. Ningún oráculo de IA acredita percepción o recepción humana.

Índice: [resumen](evidencia/AGY-20261107/results/summary.json),
[herramientas](evidencia/AGY-20261107/results/tools.json),
[resultados](evidencia/AGY-20261107/results/results.json),
[informes AGY](evidencia/AGY-20261107/results/reports.json),
[claims](evidencia/AGY-20261107/results/claims-for-contrast.json),
[cobertura](evidencia/AGY-20261107/results/route-coverage.json) y
[comprobaciones de cierre](evidencia/AGY-20261107/closure-checks.json).
Manifiesto SHA de182archivos privados conservado. Dos pruebas del arnés pasan;
compilación, Ruff y formato correctos. No se repitió regresión de producto sin
cambios funcionales. Cuota final00:43UTC:8%/52%restante; umbral5% vigente.
