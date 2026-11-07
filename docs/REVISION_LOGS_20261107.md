# Revisión de uso productivo · 07/11/2026,20:24UTC

Revisión solicitada por el propietario. Solo lectura de logs del runtime propio,
recibos y tareas de SQLite propia. Sin inferencias nuevas, envíos, descarga repetida,
reinicio ni cambios productivos. Evidencia saneada sin consultas personales,
identificadores de chat, títulos de resultados ni URLs.

Cinco entradas naturales entre20:20:49y20:22:13UTC: saludo,dos aclaraciones,búsqueda
y selección de un resultado. Todas tuvieron salidas aceptadas por el transporte;
esto no acredita lectura humana. El usuario confirmó que observa respuestas.
La búsqueda terminó correctamente con opciones/collage;la descarga seleccionada
falló. No contar la entrega del aviso de error como éxito de descarga.

| Turno | Interpretación y espera frontend,s | Hasta último ACK de salida,s |
| --- | --- | --- |
| Saludo | 5,543 | 6,692 |
| Primera aclaración | 6,892 | 8,322 |
| Segunda aclaración | 14,887 | 16,501 |
| Búsqueda | 7,611 | 12,731 |
| Elegir resultado | 16,065 | 60,885 |

Mediana frontend7,611s. Estas duraciones parten de creación de tarea,por lo que
incluyen cola/poll y validación;no son una medición aislada de inferencia Qwen.
La búsqueda del backend duró2,821s. Preparación de descarga:44,127s,estadofailed,
códigosource_failed. Los16,065sdel frontend más preparación y entrega explican
aproximadamente61sdel último turno. No hubo fallo registrado de interpretación
ni cuota en estas cinco tareas.

Hallazgos por prioridad:

1. **Descarga fallida y diagnóstico insuficiente.** Se seleccionó correctamente el
   elemento y se creó download_media.url,pero el motor devolviósource_failed.
   Para esta familia de fuentes,el extractor no tiene mapeo de fallo específico
   en engines/downloads.py:1328–1341 y process_failed queda reducido a ese código.
   El recibo productivo no conserva la causa detallada. No se puede afirmar si fue
   bloqueo del origen,formato,extractor o conectividad con esta evidencia. No se
   repitió la descarga. Prioridad:diagnóstico acotado y saneado por etapa/código,
   conservando garantías de secretos/URLs;después reproducción sintética del error
   identificado y corrección demostrada,no reintentos ciegos.
2. **Aclaración de fuente innecesaria.** La petición señalaba explícitamente el
   tipo de contenido y las fuentes pertinentes estaban habilitadas;el frontend
   volvió a pedir elegir fuente. Prompts propios ya distinguen petición explícita
   de término ambiguo. Es un fallo observado de interpretación/contenido de IA,
   no evidencia de fallo del parser o de permisos. Revisar instrucciones y ejemplos
   con oracles específicos. La segunda aclaración fue por formato requerido del
   contrato;no llamarla bug confirmado. Se puede diseñar un formato predeterminado
   para video,pero sería una decisión de experiencia/contrato que requiere pruebas.
3. **Espera larga sin progreso en las salidas registradas.** El último turno tiene
   únicamente el aviso final tras60,885s,no una salida previa de estado en outbox.
   Mejorar feedback de cola/preparación y etapa actual sin afirmar éxito anticipado
   ni crear consultas IA adicionales. No se observó render o indicadores del cliente.
4. **Telemetría insuficiente para atribuir segundos y neuronas.** El log stderr
   propio está vacío y stdout solo contiene arranquesready. Los fallos de dominio
   viven en SQLite. No existe aquí una traza persistida por turno con alias del pool,
   tokens,neuronas,duración de proveedor y cola separadas. El atributo last_metrics
   del adaptador no equivale a observabilidad persistente. Registrar métricas
   saneadas permitiría atribuir latencia y coste reales,evitando copiar mensajes.

No se modificó ni desplegó ninguna de estas mejoras en este cierre de revisión.
La prioridad inmediata es hacer diagnosticable el fallo de descarga y corregirlo
cuando se pueda demostrar la causa;después reducir la fricción de aclaraciones y
mostrar progreso. Evidencia:docs/evidencia/REVISION_LOGS_20261107/summary.json.
