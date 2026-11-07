# Correcciones del pool activas · 07/11/2026

Se corrigieron y desplegaron los tres hallazgos reproducidos de la auditoría.
La evidencia histórica en AUDITORIA_POOL_20261107 se conserva. No se gastaron
inferencias ni se alteraron las campañas anteriores.

## Resultado

- Una entrada deshabilitada no abre su credencial. Archivos ausentes, JSON inválido,
  permisos inseguros y rutas rechazadas de una entrada activa se aíslan por alias;
  las cuentas sanas siguen funcionando. Al reparar el archivo, la siguiente carga
  lo reevalúa. Registro global inválido, duplicados de cuentas activas y estado
  compartido corrupto siguen fallando de forma cerrada.
- HTTP401/403 genera cuarentena persistente de esa credencial, no de su AccountID.
  No certifica que el token esté revocado: también puede ser falta de permisos.
  Se guarda código saneado y fingerprint SHA256 en authentication-state.json0600;
  nunca el token en el diagnóstico. Nuevos mensajes omiten esa credencial, incluso
  después de reiniciar. Renovar el token produce otro fingerprint y se reevalúa;
  usar otra clave de la misma cuenta no borra su pausa de cuota. Un fallo tardío de
  una petición con el token antiguo no pone en cuarentena la clave renovada.
- Pausas de cuota y cuarentena se actualizan con flock sobre un archivo privado,
  recargando y fusionando el estado dentro del bloqueo. os.replace conserva la
  escritura atómica del JSON. Una actualización de cuota no acorta un vencimiento
  posterior existente. Dos instancias y dos procesos reales conservaron ambas pausas.
  No se mantiene el bloqueo durante la inferencia.

El mensaje que recibe401/403 o cuota agotada sigue fallando sin reintento con otra
cuenta. La recuperación se aplica al mensaje siguiente. Si todas las credenciales
están dañadas o bloqueadas se informa indisponibilidad, no se inventa cuota agotada.
El diagnóstico local por alias queda disponible en credential_errors del pool.
El alta de cuentas rechaza alias que sobrescribirían los archivos de estado.

Este cambio no convierte el reparto ni la concurrencia en globales entre procesos:
el cursor sigue siendo local y el runtime conserva sus dos solicitudes por lote.
El bloqueo resuelve la pérdida de actualizaciones del estado; no es una promesa
de reparto global uniforme. Las escrituras manuales externas al protocolo de lock
no están protegidas. No se corrompieron ni revocaron claves reales para probarlo.

## Validación y despliegue

54 pruebas locales pasan:20 del pool, incluida recuperación y procesos reales,
y34 del frontend. Las pruebas nuevas contrastan los antiguos comportamientos
incorrectos con el resultado corregido. Sin repetir pruebas remotas de proveedor.

Desplegado7e98bf0,PID3890974. Runtime y servicio de llamadas ready, sin llamada
activa. Perfil, Qwen3.8-27B low, catálogo compacto íntegro y cinco cuentas preservados.
Postflight de composición:5cuentas cargan,0incidencias locales,0cuarentenas observadas;
las2pausas de cuota anteriores se conservan. Es lectura local, no vigencia remota
ni saldo disponible.

Respaldo privado deploy-pool-recovery-20261107* con DB SQLite consistente,
integridad/FK,perfil/configuración,pool completo y fuentes anterior0448e21 y actual.
Esquema20 sin migración;datos idénticos al backup mientras estaba parado. No se
modificaron otros servicios, que conservaron PID/estado. Sin envíos, llamadas o
inferencias durante el corte. Reversión preparada del módulo del pool a la fuente
anterior, sin restaurar DB ni borrar datos posteriores; no se activó.

Evidencia separada en docs/evidencia/CORRECCION_POOL_20261107: pruebas, hashes de
fuente validada, recibo de despliegue y composición posterior. Código principal:
src/botsky/adapters/cloudflare_pool.py. No reanudación automática de campañas.
