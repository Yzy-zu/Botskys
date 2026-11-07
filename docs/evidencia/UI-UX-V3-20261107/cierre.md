# V3 · base técnica local verificada

Esquema propio19 amplía outbox (tipo/payload/version/hash) e índice de mensajes
aceptados. No segundo journal. Plan inmutable antes del envío; partes antiguas
v0 conservadas. Validación rectangular/UTF16/celdas/presupuesto60KiB, tipo nativo
sendNativeTable en transporte propio; configuración explícita native_tables_enabled.
Sin soporte habilitado se conserva el texto completo antes del primer despacho.
Tras timeout/rechazo no cambia el plan ni envía fallback duplicado. Hash adulterado
falla antes de enviar. Citas resuelven el padre desde las partes aceptadas.

Instalación Evolution leída sin POST ni cambios: dist/main.js contiene ruta
sendNativeTable → handler ya instalado. SHA256main
7d63bceb13e6c6253cefc798f7e0aa378908ae9ac632960b41a175d501d3dea0;
handler3cb433568f1867aeacf36e7d8c6b9eb4a3ce801bf08ea8e6f0790a35c013e3d7.
Límites instalados20columnas/100filas/3500UTF16/64KiB; los locales son más
conservadores en título/presupuesto. Referencia Zhana rich_text/provider solo código.

5testsPASS: migración18→19 con fuente/plan previo idénticos/integridad/FK;
partes intro aceptada+tabla incierta+pie bloqueado; hash; malformed/suplementarios;
contratoHTTP201/400tipado/400genérico/404/409/500/ACKausente; Evolution→ruta tabla
con payload exacto y sin duplicados. HTTP es DOBLE, no prueba visual/proveedor.
14runtimePASS. Sin nuevos mensajes, llamadas ni cambios en Evolution. Activación
productiva y observación Android/Web NO_PROBADO, despliegue pendiente.
