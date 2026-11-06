# Administración y Minecraft · R8

Referencia técnica Zhana7e12d54 fijada en R0; hashes consultados en admin-origen.json.
Se recuperan permisos/roles, protección de objetivos, warnings/ban/XP, snapshot y
coste5000 nuclear con devolución solo sin aceptados/inciertos, cliente Evolution
y solución SSH JSON del worker Bedrock. No se usa intérprete, modelos Args,
configuración, sesiones, servicios, credenciales ni datos de usuario antiguos.

Nuevos dominio/recibos/operaciones/tablas y cliente de grupos bajo contratos Botsky.
Objetivos vienen de IDs explícitos y miembros comprobados; sin heurística de nombres.
El ban conserva aliases del snapshot y se registra antes del POST. Reejecución local
tras crash retorna resultado propio durable. Nuclear usa partes y coste de ledger/
reserva, siempre deshabilitado por defecto. Snapshot no se ensancha al confirmar.

Componentes acotados adaptados: minecraft_remote.py → adapters/minecraft.py, con
runner inyectable; minecraft_worker.py → ops/minecraft_worker.py (stdlib, fmt off
para conservar compatibilidad sintáctica del worker). Créditos de origen Zhana y
hash conservados. No imports del paquete Zhana ni lectura de runtime/configuración.
Cliente de transporte de grupos nuevo, toma solo endpoint y credenciales explícitos.

Comprobación propia: SQLite, clientes HTTPX reales con MockTransport, proceso local
Python para IPC/timeouts, barajas/grupos y datos sintéticos. Source de worker está
trasladado, sin despliegue ni ejecución contra Docker/Bedrock. El primer oracle de
prueba de nuclear marcaba su implementación pendiente; se conserva el log de ese
checkpoint y se reemplaza al construirlo por preview/coste/roles/confirmación/
cancelación/incertidumbre, no por un PASS remoto. R8-final-tests.txt y R8.json.

Límites: todo proveedor real NOT_TESTED; no garantía CAS de roles externos ni
recepción humana. No se abre navegador, no se llama ni envía a usuarios reales.
R9/R10 deben completar sus propias condiciones; R11 sin encargo de transición.
