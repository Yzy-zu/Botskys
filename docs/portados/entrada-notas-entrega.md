# Entrada, notas y entrega · R2

Origen técnico: Zhana 7e12d54; inbox.py, group_access.py, contracts.py,
tools/notes.py, store.py y rich_delivery.py (SHA256 en inventario/reference.json).
Referencias de pruebas de origen: tests/test_notes.py y pruebas de inbox/entrega;
se consultan contratos, no se reutiliza su resultado como aceptación de Botsky.

Problemas resueltos de origen: identidad normalizada, allowlist explícita, recibo
durable, literalidad de notas, filtro escapado, vista confirmada por entrega y
partes inciertas que no se repiten. No se traslada su bucle ni anclas lingüísticas.

Decisión: reescritura propia con biblioteca estándar Python y SQLite. El adaptador
local produce metadatos sintéticos de operador (no identidad WhatsApp); la frontera
Evolution futura deberá verificar sus propios eventos, timestamps y aliases.
La aplicación no obtiene actor, chat, epoch ni permiso del texto de un comando.

Diferencias: notas aisladas también por actor, cuenta y época; búsqueda mediante
instr sobre texto casefold (%, _ y barra son literales). No se importa información
anterior. Filtro omitido en página >1 exige vista propia aceptada y vigente; una
vista nueva sin entrega no reemplaza la última aceptada. TTL 15 minutos.

Recibos únicos por instancia/cuenta/mensaje; fingerprint de identidad/contenido
detecta conflicto. El duplicado no pasa otra vez por el parser. Comando canónico
y ruta admitidos se conservan para recuperación. Transacción local abarca nota,
recibo de efecto, resultado e intención de entrega. Cancelación exacta antes del
efecto y control de revisión. Sin transacción durante send; CAS por parte.

Nuevo esquema propio v2 (v1 fue bootstrap vacío de R0). application_id propio;
rechaza DB ajena o versión incompatible. No hay lector de DB31 ni de private/ de
Zhana. Prueba de DB31 sintética verifica rechazo sin cambiar bytes.

Evidencia nueva: tests/test_core.py y docs/evidencia/R2.json. SQLite temporal real,
reinicio, carreras, fallo entre nota/recibo y entrega incierta. No proveedor real,
WhatsApp, escucha ni recepción humana. No promesa exactamente una vez externa.

Límites: sin transportes remotos, scheduler ni trabajos de motor todavía. R3
introducirá leases/artefactos y cancelación durante motor. No se podan recibos de
efectos ni notas por edad. Recuperar sending como uncertain exige propiedad
exclusiva del proceso; no se invoca al crear otro objeto Application.
