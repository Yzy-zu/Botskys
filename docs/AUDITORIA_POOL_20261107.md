# Auditoría local del pool · 07/11/2026

Veredicto: el pool sí funciona para el runtime único actual y admite pasar de cinco
a siete cuentas distintas. No es tolerante a todas las averías de credenciales ni
está preparado para varios procesos compartiendo el estado. No se modificó código
productivo ni se hicieron peticiones de proveedor; cero neuronas consumidas.

## Hallazgos reproducidos

1. **Prioridad media: credencial dañada bloquea el pool completo, incluso deshabilitada.**
   cloudflare_pool.py:69–74 lee y valida cada archivo antes de consultar enabled.
   Un archivo ausente, JSON inválido, permisos incorrectos o credencial de formato
   incorrecto impide load y por tanto cualquier selección. Reproductor: deshabilitar
   cf1 sintética, reemplazar su archivo por JSON inválido como credencial y mantener
   cf2 sana; composición falla credentials_invalid. La desactivación en el registro
   no permite aislarla. No ocurre en la inspección actual: los cinco archivos se
   cargan correctamente y están0600. Recomendación: comprobar enabled antes de abrir
   el secreto; aislar y registrar incidencias de una entrada sin ocultar errores
   globales del registro ni relajar protección de archivos.

2. **Prioridad media: token revocado no se aparta.**
   cloudflare_interpreter.py:85 y cloudflare_pool.py:104–110 solo persisten pausa
   por daily_quota. HTTP401/403 sigue como error genérico, sin cuarentena. Reproductor
   de cuatro turnos con dos cuentas: cf1 devuelve401, cf2 responde, cf1 vuelve a
   devolver401, cf2 responde. Dos errores repetidos mientras la otra cuenta funciona.
   No existe fallback del mismo mensaje por diseño; tampoco protección entre mensajes
   para ese fallo permanente. Recomendación: cuarentena por fallo de autenticación,
   diagnóstico saneado por alias y liberación explícita por operador al renovar clave.
   No confundir403 de falta de permiso específico con agotamiento diario.

3. **Prioridad media al escalar: dos instancias pueden perder una pausa de cuota.**
   cloudflare_pool.py:83–108 combina lectura/modificación/escritura sin lock compartido.
   os.replace evita JSON parcial pero no pérdida de actualizaciones. Reproductor:
   dos pools cargan estado vacío, uno recibe cuota agotada de cf1 y guarda su pausa;
   el otro recibe cuota agotada de cf2 y sobrescribe con su estado anterior más cf2.
   El archivo queda con una sola pausa. Dos solicitudes concurrentes dentro de la
   misma instancia sí preservaron las dos. Actualmente se inspeccionó un runtime
   PM2 online, PID3880318; no se acredita que no exista un proceso ajeno oculto.
   Recomendación para múltiples workers: SQLite transaccional o lock que cubra
   lectura/fusión/escritura. Mantener un único escritor hasta implementar eso.

## Comportamiento verificado

- Siete cuentas, setenta propuestas simuladas: diez por cuenta, setenta llamadas,
  sin repetición del mismo mensaje. Catálogo/ejecutor fuera de estas simulaciones.
- Agotamiento por3036 y4006 con mensaje daily free allocation: pausa por hash de
  AccountID, exclusión en mensajes siguientes, persistencia tras nueva instancia.
- Todas agotadas: no hay petición HTTP, error daily_quota_pool y cero efectos.
- Pausa vencida: cuenta disponible. Altas explícitas recargadas en el próximo turno.
- Duplicar cuenta no agrega capacidad; se rechaza. Límite de registro: diez cuentas.
- Perfil productivo compone Qwen3.8-27B low y cinco cuentas distintas con secretos
  0600. cf01/cf02 tenían pausa por cuota observada hasta el reset. No se midieron
  saldos actuales ni vigencia remota nueva; cf03/cf04/cf05 disponibles en el registro
  no significa que tengan sus10.000neuronas intactas.
- Dos inferencias concurrentes por lote en runtime.py:185–188. max_concurrency del
  adaptador es POR CUENTA, no global: otros consumidores que llamen al pool directamente
  no reciben una limitación global de dos. No es un fallo del runtime observado.
- El cursor vive en memoria y vuelve a cero al reiniciar. Las pausas persisten;
  el reparto histórico no. Con conjunto estable y sin reinicios es circular justo.
- Una cuota agotada se descubre por rechazo real. Ese mensaje no se reintenta y
  pide una petición nueva al usuario. No hay saldo preventivo ni garantía de reparto
  según neuronas consumidas: round-robin distribuye turnos, no coste uniforme.

## Tiempo de gestión local

Mil iteraciones por tamaño con archivos sintéticos600 y proveedor doble sin red.
Incluye load del registro y credenciales, selección y llamada al doble; excluye
creación del prompt, red, cola real, inferencia y entrega.

| Cuentas | Mediana ms | P95 ms |
| --- | --- | --- |
| 5 | 0,607 | 0,701 |
| 7 | 0,824 | 0,938 |
| 10 | 1,147 | 1,346 |

Medición de este servidor y caché de filesystem caliente, no SLA. El crecimiento
5→7 añade aproximadamente0,22ms en esta muestra; los segundos de Qwen dominan.
La latencia de respuestas de la aceptación anterior no se volvió a medir.

## Evidencia y alcance

Trece pruebas locales pasan: ocho existentes y cinco nuevas de auditoría. Algunas
pruebas nuevas verifican que el límite indeseado existe; pasar NO significa que
se haya corregido. Archivos en docs/evidencia/AUDITORIA_POOL_20261107 y
reproductores tests/test_cloudflare_pool_audit.py, ops/auditar_pool_local.py.
Revisión de código, simulaciones y lectura productiva saneada; no proveedor real,
cuotas nuevas, envío, llamada, reinicio o modificación productiva.

Conclusión operativa: se pueden registrar dos cuentas más con la instalación actual.
Primero conviene aislar credenciales dañadas y poner en cuarentena las revocadas;
el bloqueo compartido es necesario antes de ejecutar varios procesos de pool.
La auditoría no autoriza ni ejecuta esas correcciones por sí misma.
