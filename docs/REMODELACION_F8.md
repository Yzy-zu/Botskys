# F8 · Despliegue y activación · 07/11/2026

Encargo posterior expreso del propietario: desplegar y dejar activo. Código
`641844a` cargado por el supervisor propio `botsky-production-runtime`; PID3801640.
Intérprete Cloudflare/GLM4.7Flash habilitado con modelo fijo,deadline40s y concurrencia2.
La activación no habilita capacidades que el perfil operativo tuviera desactivadas.

Preflight: esquema19,cero jobs activos y cero entregas pendientes/inciertas,sin
llamadas activas/externas ni agenda reservada. Parada propia observada; respaldo
SQLite consistente,integridad yFK correctas. Archivo privado de fuente anterior
4482c46 y fuente instalada,perfil yconfiguración propios conservados en
`private/deploy-frontend-20261107T171813Z/` con manifiesto de hashes privado.
Sin copia de perfiles de navegador,sesiones o datos de Zhana.

Migración19→20: comparados hashes de todas las columnas/filas previas de54tablas,
sin cambios de datos;solo esquema_version añade20. Integridad yFK vuelven a pasar.
Primer arranque con frontend apagado listo;parada observada,credencial propia
copiada0600 a la ruta privada relativa a settings.root y activación explícita.
Segundo arranque listo:runtime/calls ready,sin llamadas ni advertencias,sin jobs
activos o entregas pendientes. Otros supervisores conservanPID/estado. Salud del
puente172.18.0.1:3000 comprobada porGET autenticado. Perfil idéntico salvo bloque
interpreter;no cambian permisos,webhook ni configuración ajena.

No se enviaron mensajes,no hubo inferencias nuevas ni llamadas de prueba. No se
observó el recorrido humano de WhatsApp: permanece NO_PROBADO. La comprobación de
salud no sustituye aceptación del cliente ni garantiza disponibilidad de cuota de
Cloudflare. Se conservan los límites reales de F7,incluida latencia elevada.
La métrica idle_media_released devolvió null en estas muestras;no se presenta como
liberación de medios comprobada. La salud ready y ausencia de llamada sí se observaron.

Reversión principal:conservar esquema20 y datos actuales,desactivar exclusivamente
interpreter.enabled bajo parada/arranque observados y retirar interpretaciones
pendientes conforme al estado real. Mantener código compatible20. No ejecutar
binario19 contra esta base ni restaurar automáticamente el backup sobre efectos
nuevos. Fuente anterior archivada para recuperación técnica,no para downgradeciego.

Evidencia saneada: docs/evidencia/REMODELACION/F8-despliegue.json.
Procedimiento ejecutado: ops/desplegar_frontend_f8.py --live. No reejecutar para
reabrir este corte;su preflight exige esquema19 ypor defecto no modifica nada.
