# Contraste y correcciones · 06/11/2026

Encargo posterior del propietario: el agente principal contrasta los hallazgos de
la campaña terminada y corrige los confirmados, con apoyo de tres subagentes Luna.
El principal revisó las adjudicaciones y los cambios. Referencia de producto
`b34db69`; HEAD documental inicial `3f6f3d6`. No se reanudó la campaña ni se hicieron
peticiones remotas, envíos o cambios de servicios/permisos.

**50/50 claims adjudicados y tres observaciones del orquestador revisadas.** Cinco
claims y una observación demuestran **cinco causas distintas**, todas corregidas:
los claims de ruleta y administración comparten el mismo diagnóstico de enteros.
Los 783 resultados originales y sus expectativas permanecen intactos.

| Causa confirmada | Hallazgos | Corrección y comprobación |
| --- | --- | --- |
| Bucle al cancelarse la tarea de creación de un subproceso | ORCH-CANCEL-01 | Se propaga la cancelación terminal del lanzamiento. Antes agotaba el watchdog externo de 3s; ahora termina. Tres regresiones cubren el atasco, fallos de creación y cancelación repetida con retirada de un hijo real. |
| Firma de audio aceptada sin verificar el contenedor para análisis IA | conversation-01 | Se comprueban contenedor, pistas y duración antes del dispatch de Gemini. El Ogg corrupto de 184bytes devuelve `invalid_audio` con cero llamadas al modelo. WAV/MP4 válidos conservan bytes y MIME. El código anterior del proveedor era controlado: no se confirma la supuesta fuga de excepción cruda. |
| Metadatos que publicaban diez términos aunque el contrato admite ocho | search_web-01 | `max_items=8` explícito, conversión ligada a ese valor y catálogo generado actualizado. Se aceptan ocho y se rechazan nueve; no se amplía el límite de negocio para satisfacer al tester. |
| Error de enteros que pedía un «número decimal» | manage_roulette-01, manage_admin-01 | El mensaje especifica entero y rango. Se mantiene el rechazo de entradas inválidas. |
| Oferta de pack para una categoría inexistente | manage_pack-01 | Se verifica existencia publicada antes de crear la oferta, sin cargo. Se conserva normalización, `azar` y comprobación de stock durante la compra. La consulta usa el techo de selección de 10000 álbumes, no el del catálogo de 100. |

El resto de claims se distribuye en 21 límites/denegaciones correctos, 14 errores
de expectativa, ocho problemas de fixture/setup/harness y dos sin reproducir.
La adjudicación completa, revisada por el principal y con referencias por caso,
está en [adjudications.json](evidencia/CONTRASTE-20261106/adjudications.json).
Los informes auxiliares conservan el detalle de cada revisión; esta adjudicación
consolidada fija la clasificación final.

Entre los falsos positivos: el guion de voz supuestamente truncado conserva
2722caracteres y una frase final completa. El feedback al tester cortó el JSON a
1700caracteres precisamente a mitad de palabra. `/voz ultima` lee su fuente exacta,
incluido el pie de seguimiento; no se contrató sanitizarla. La composición y su
duración orientativa no son lectura literal ni ajuste temporal exacto.

La imagen de OCR de 4000×4000 es azul uniforme, sin texto. Los videos de ASR tienen
tonos sintéticos, sin el habla que el tester esperaba. El PDF de 501 páginas y la
imagen de 4097px exceden sus límites vigentes. Las cadenas `output:...` inyectaron
salidas como adjuntos actuales de otro mensaje: `attachment_source_mismatch`
protege esa vía; la reutilización contratada es mediante cita exacta aceptada.
Los adjuntos de escuela/recados se conservan como archivos opacos y no se anuncian
como documentos/imágenes decodificados. Las respuestas terminales idempotentes
conservan el estado real y no repiten envíos, cargos o liquidaciones.

`conversation-02` permanece sin reproducir como omisión del backend: la DB original
contiene las referencias de ambos archivos; nuevas pruebas inspeccionan los tipos
SDK reales y confirman el texto del PPTX y los bytes del JSON malformado en la carga.
Esto no acredita la interpretación del proveedor remoto. `search_web-02` no aporta
una respuesta RSS original que pruebe una coincidencia descartada; una expectativa
de «alta probabilidad» no demuestra un filtro defectuoso. No se cambiaron esas
funciones ni se efectuó otra prueba remota para resolver esas incertidumbres.

El timeout del helper de cuota fue un incidente de harness; su atasco secundario
se cuenta únicamente en ORCH-CANCEL-01. El rechazo del informe AGY de descargas es
una dependencia externa: se conservan sus 25 resultados y la ausencia del informe.
No se inventan claims ni se atribuye aceptación a fronteras sin probar.

Validación final: **219 pruebas Python y 286 Node pasan**, cero fallos, omisiones
o cancelaciones. La suite completa de 218 pruebas Python se ejecutó con guardia de sockets y registró
cero intentos fuera de loopback; una prueba adicional de categorías con más de
100 álbumes, añadida después de descubrir la suite, pasó por separado con red
bloqueada. No hubo cambios funcionales posteriores. Node usó la guardia local
existente. Incluye
SQLite, motores y archivos reales sintéticos, proveedores dobles y las regresiones
nuevas. Ruff comprueba estilo y formato de 132 archivos; `pip check` y
`git diff --check` pasan. La inspección nueva de medios valida el contenedor y sus
metadatos, sin prometer decodificación completa o calidad semántica del proveedor.

Evidencia nueva en [CONTRASTE-20261106](evidencia/CONTRASTE-20261106/summary.json):
adjudicaciones, reproducciones antes/después, comparación del guion completo,
logs de pruebas/comprobaciones y manifiesto SHA256 de la evidencia histórica.
R10 global y las fronteras remotas/humanas pendientes conservan sus límites;
R11 no se inició. No se tocaron NLP, DB31, perfiles, sesiones, servicios de Zhana,
llamadas, navegador, mutaciones de grupo/servidor o GitHub.
