# QR en análisis y términos de búsqueda · 07/11/2026

Encargo del propietario: corregir los puntos1y3 del contraste AGY. Cambios nuevos,
conservando las campañas, resultados y adjudicaciones históricas. Sin NLP ni
interpretación de intenciones para ejecutar comandos.

## Lectura QR independiente del generador

Antes de enviar imágenes de `/ia` a Gemini, Botsky intenta decodificar sus QR con
el mismo motor local de `/qr`. Conserva la imagen para el análisis visual general.
Las lecturas se pasan como datos estructurados al modelo y se publican en un bloque
**Contenido QR verificado**, construido por Botsky, anterior al análisis generado.
El modelo tiene instrucción de no volver a transcribir ni adivinar los QR; su texto
queda identificado como análisis de IA. No se garantiza que todo lo generado sea
correcto: el valor del bloque verificado y `data.qr_readings` son independientes
de esa generación y no pueden ser reemplazados por ella.

No se clasifica si la persona pretendía usar QR; se extrae contenido de todas las
imágenes admisibles. No se ejecutan comandos contenidos en el QR ni se abren URLs.
Un fallo del lector no impide el análisis de la imagen y se avisa que no se pudo
verificar; ninguna lectura se interpreta como prueba de que no exista QR.

Se limita el texto acumulado de lecturas a6000caracteres y se señala truncamiento.
Si Gemini falla después de una lectura correcta, el resultado conserva ese
contenido y declara el fallo del análisis, sin anunciar éxito completo. Los
controles nuevos incluyen un doble de Gemini que responde con un QR falso: el
bloque verificado conserva exactamente el valor decodificado, se mantiene el PNG
original en el payload y ningún texto del QR entra al ejecutor.

## Términos obligatorios en la solicitud de búsqueda

Antes, `--terminos` solo intervenía en el filtro local. Ahora todos sus términos
se incluyen también entre comillas en la consulta enviada a Bing; se conserva el
query original, incluido `site:`. El filtro ALL sobre título/fragmento sigue
exigiendo todas las restricciones, con los mismos límites y sin aceptar resultados
irrelevantes para forzar una respuesta positiva. El escapado en la construcción
de la consulta no sustituye la validación local del resultado.

Una prueba con HTTP doble entrega una coincidencia solo cuando la petición contiene
los términos; comprueba que la respuesta final conserva exclusivamente el candidato
que cumple todas las restricciones. Otras pruebas cubren comillas, query original,
filtro y replay de RSS conservados.

La comprobación nueva real del cliente hizo3GET para las combinaciones de consulta
y términos de la campaña original. HTTP200 en los3; RSS crudo guardado sin cabeceras,
con hashes y oráculo previo. Sus candidatos no cumplen los términos y el cliente
retorna vacío correctamente. Esto prueba envío y filtrado, **no** garantiza que
Bing entregue resultados útiles ni reconstruye el RSS histórico ausente.

Hubo otras3consultas sintéticas previas con términos distintos, construidas por
operador. Se conservan como tales. Una etiqueta posterior atribuyó erróneamente
barras extra al escapado JSON; la revisión principal comprobó que no existen en
ninguna consulta y lo dejó corregido en `evidence-review.json`. La captura
`verified-client/` es la referencia de ejecución directa del cliente de producto.
No se repitieron mensajes, campañas o efectos inciertos.

## Validación y alcance operativo

47pruebas focales: IA17, búsqueda6, medios16 y descargas8, con guardia de conexiones
externas. La primera pasada falló en una expectativa antigua del request de búsqueda
que aún exigía omitir los términos; se conserva ese log y se actualizó la expectativa
al contrato nuevo. La segunda pasada y Ruff/formato/diffcheck quedan en evidencia.

Cambios en cliente Gemini, composición de análisis, metadatos del lector QR y
cliente de búsqueda; sin migraciones, cambios de credenciales, perfiles o servicios.
**No se reinició producción**: el proceso ya cargado adoptará estos cambios al
reiniciarse. No hubo llamadas ni entregas remotas. Recepción humana no probada.

Evidencia: [resumen](evidencia/QR-BUSQUEDA-20261107/summary.json),
[pruebas](evidencia/QR-BUSQUEDA-20261107/local-tests.txt),
[captura del cliente real](evidencia/QR-BUSQUEDA-20261107/verified-client/report.json) y
[revisión de capturas](evidencia/QR-BUSQUEDA-20261107/evidence-review.json).
