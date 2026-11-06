# Punto2 · adjuntos Gemini y búsqueda

El propietario encargó resolver las dos sospechas restantes. Se hicieron
comprobaciones nuevas acotadas con la clave/modelo Gemini ya configurados y dos
consultas al RSS fijo de Bing. Solo documentos sintéticos, sin entregas a WhatsApp,
llamadas, navegador, archivos de usuarios o cambios de servicios. La campaña
anterior y sus resultados permanecen cerrados e intactos.

**No se reprodujo un defecto del backend en ninguna de las dos sospechas.**
El punto2 queda contrastado con evidencia de contenido y respuestas remotas;
no se cambió producto para forzar resultados positivos.

| Sospecha | Comprobación | Conclusión |
| --- | --- | --- |
| `conversation-02`: Gemini negó recibir PPTX/JSON | Se generó un identificador aleatorio distinto dentro de cada archivo, ausente del prompt y del historial. El PPTX se transformó a texto; el JSON malformado se conservó como texto. Gemini devolvió los dos identificadores completos. Sin adjunto devolvió `AUSENTE`. Se capturaron tres payloads del SDK y se verificó hash/contenido de los dos archivos. | El camino de adjuntos funciona en los controles actuales. La declaración anterior del modelo no demuestra omisión del backend; falta la captura remota original para explicar retrospectivamente aquella respuesta. |
| `search_web-02`: búsquedas con términos obligatorios devolvieron vacío | Se repitieron únicamente las dos consultas originales y se guardaron las respuestas HTTP200. En los diez candidatos de c02 no aparecen Python/tutorial; en los diez de c03 falta W3C. Una revisión de los candidatos y un replay local por HTTP doble confirman cero coincidencias ALLterms. | Vacío correcto para esos RSS: el proveedor no entregó candidatos que cumplieran las restricciones. No se elimina el filtro ni se atribuye relevancia por probabilidad. |

Gemini recibió cinco invocaciones de generación: dos controles positivos iniciales
y tres controles finales (dos positivos y uno negativo). La primera instrumentación
HTTPX no capturó el transporte aiohttp usado por el SDK; esos primeros resultados
no se presentan como capturas de requests. Se ajustó la instrumentación del operador
a la frontera del payload SDK anterior al transporte. Dos errores intermedios del
hook ocurrieron antes de la llamada al transporte, sin peticiones al proveedor.
Se conservan en `development-notes.json`. No se tocaron adaptadores de producto.

Los tres controles finales están en
[gemini.json](evidencia/SOSPECHAS-20261106/20261106T211329Z/gemini.json).
El hash del texto preparado coincide con el de la carga; el identificador solo
aparece en el adjunto y la respuesta esperada se fijó antes de la generación.
La respuesta exacta corrobora lectura del contenido por el proveedor, sin usar
la afirmación del modelo «sí recibí un archivo» como prueba. No se subieron
archivos por Files API: los textos pequeños viajaron inline. No se registraron
cabeceras de autenticación, claves o URLs con secretos.

Capturas RSS y resultados:
[c02](evidencia/SOSPECHAS-20261106/20261106T211144Z/c02.rss),
[c03](evidencia/SOSPECHAS-20261106/20261106T211144Z/c03.rss),
[análisis independiente](evidencia/SOSPECHAS-20261106/search-review.json).
No se siguieron los enlaces de resultados ni se abrió navegador.

Cuatro regresiones nuevas comprueban coincidencias distribuidas entre título y
fragmento, limpieza HTML/entidades, `site:`, términos ausentes, límite de candidatos
y replay de ambas respuestas capturadas por `MockTransport`. Pasan26pruebas
focales de IA, descargas/búsqueda y estos casos: cero fallos, errores u omisiones;
cero intentos fuera de loopback durante las pruebas locales. La comprobación real
de proveedores se registra por separado. Ruff, formato, pip check y diffcheck
correctos. La regresión completa224 del punto1 conserva su evidencia; no se
repitió sin cambios de producto.

Reproducción local sin red de proveedores:

```text
PYTHONPATH=tests .venv/bin/python -m unittest test_ai test_downloads test_search_suspicion -v
```

`ops/resolver_sospechas.py` es exclusivamente una herramienta de operador que
**hace consultas reales** y genera fixtures nuevos; no forma parte del runtime,
de las pruebas automáticas o de una reanudación de campaña. `--skip-rss` omite las
consultas Bing, pero conserva los tres controles Gemini. No ejecutarlo por leer
este informe.

La generación puede equivocarse y el RSS puede cambiar o ser poco útil. Estos
resultados no garantizan semántica universal ni explican una respuesta histórica
sin su request. Cierran la investigación acotada sin defecto demostrado. R10
remoto global, audiovisual real y transición mantienen sus pendientes.
