# Reversión del corte visual

Respaldo privado independiente: `private/deploy-ui-cont-20261107/`, directorio0700,
ficheros0600. Contiene SQLite consistente comprobado, configuración propia y dos
archivos de código: versión cargada anterior4482c46 y versión verificada nueva.
No contiene perfiles de navegador ni modifica servicios ajenos.

No hay migración: se conserva esquema19. El nuevo lector admite planes0/1/2;
el anterior no conoce el hash ampliado del plan2. Por tanto, no arrancar código
anterior con planes2 pendientes/sending/uncertain ni con jobs activos. Una entrega
incierta exige adjudicación explícita; no se fuerza aaccepted ni se reenvía.

Procedimiento de operador, autorizado dentro de este corte, solo si es necesario:

1. Consultar salud propia y confirmar sin llamada activa/externa, medios liberados,
   agenda sin reservas. Comprobar cero jobsqueued/running y outboxpending/sending/
   uncertain. Si no se cumple, no interrumpir ni degradar planes pendientes.
2. Parar exclusivamente `botsky-production-runtime` con PM2. Repetir comprobación
   SQLite y guardar una nueva copia consistente del estado vivo antes de tocar código.
3. Extraer del archivo propio `previous-code-4482c46.tar` solamente `src/` y `calls/`
   sobre el checkout. Conservar private/, base viva, node_modules, perfiles y PM2.
   No usar gitreset/clean ni restaurar el SQLite antiguo sobre efectos nuevos.
4. Arrancar exclusivamente el runtime propio y comprobar healthzready, llamadas
   inactivas, integridad/FK y supervisores ajenos sin cambios. Si falla el código
   previo, restaurar src/calls del archivo `verified-code.tar` y diagnosticar.
5. Registrar la reversión y el código efectivo en relevo. Conservar ambos respaldos.

Respaldo leído con SQLite integrity_check y foreign_key_check; archivo de código
legible mediante tar y hashes registrados en el resumen de despliegue. La reversión
productiva NO se ejecuta como prueba: provocaría un segundo corte innecesario.
La salud de procesos no acredita render ni aceptación humana.
