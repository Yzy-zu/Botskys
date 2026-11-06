# Organización · R5

Referencia Zhana fijada en R0:7e12d54; archivos y hashes de trabajo consultados en
organizacion-origen.json. No se importa su runtime ni se consulta su almacenamiento.

Se recuperan contratos técnicos de memory_store (ámbito/IDs), reminder_time/store/
scheduler (fecha local,600s de tolerancia, reserva durable), school/store/attachments/
scheduler (ownership, límites de adjuntos, horario y digest de dueño) y polls/store
(publicación antes del voto y revisión del voto). Sus pruebas y niveles antiguos
no se convierten en aceptación de Botsky. Se reescriben dominio, persistencia y
scheduler con recibos/contratos propios; no se trasladan modelos de interpretación.

Diferencias deliberadas: sintaxis de fechas y opciones explícita, memoria literal
sin extracción automática, confirmación de borrado ligada a snapshot y entrega,
identidad sintética en frontera local, capabilities escolares revocables, avisos
internos separados de entradas del transporte y caducidad revalidada al entregar.
El resumen escolar es determinista y no necesita IA. Gemini solo recibe datos de
memoria del solicitante en su ámbito, sin herramientas ni ejecución de comandos.

Comprobación nueva: SQLite temporal real, carreras de tick, reinicio, fallo incierto,
pausa/caducidad, publicación/voto reordenado, propiedad, concesión/revocación de
adjuntos, horario/solapamiento, filtros/paginación y aislamiento del contexto IA.
No prueba WhatsApp, recepción humana, proveedor remoto ni servicio continuo.
