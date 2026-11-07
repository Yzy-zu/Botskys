# Pool Cloudflare y modelo seleccionado · 07/11/2026

Pool instalado en producción con dos cuentas propias registradas,secretos0600 y
fuera deGit. Modelo único configurado: `@cf/qwen/qwen3.8-27b`,reasoning_effort=low.
Código desplegado3c29a21;runtimePID3842369. Selección directa del catálogo completo,
backend dueño de efectos ypresentación. Ninguna respuesta de herramienta vuelve
al intérprete. No se crean varios bots ni se duplica la cuenta de WhatsApp.

## Comparación nueva con cf02

La clave nueva verificó token activo ypermitió inferencias. AccountID/token solo
enprivate. Se congeló manifestnuevo en1600eec;se reutilizaron oracles previos,sin
reanudar la ronda bloqueada ni el A/Bcancelado. Dos casos por modelo;los dos
finalistas yGLMcontrol recibieron cuatro casos adicionales.22intentos en total,
fixtures sintéticos ypropuestas capturadas,sin ejecutar herramientas remotas.

| Perfil | Coincidencia estricta | Mediana | Máximo |
| --- | ---: | ---: | ---: |
| Qwen3.8-27B low | 6/6 | 9,628s | 39,704s |
| GLM4.7Flash | 5/6 | 8,298s | 40,041s(timeout) |
| Llama4Scout | 3/6 | 1,236s | 4,327s |
| GPT-OSS20B | 1/2(solo cribado) | 2,998s | 3,298s |
| Gemma4-26B | 1/2(solo cribado) | 12,489s | 17,870s |

Los conjuntos de2y6casos no equivalen en cobertura. No son porcentajes globales
de usabilidad ni garantizan calidad de las155variantes. Ganador de esta muestra
por prioridad de aciertos:Qwen. No es ganador en rapidez o consumo.

Scout conserva correctamente la intención de buscar videos pese a incluir
«videos de gatos» enquery en vez de«gatos»:el scoreestricto se conserva,pero la
adjudicación independiente no lo llama bug de dominio. Sí produjo dos fallos
reales:añadiópartial_arguments al sobre cerrado de conversión ycontestó la pregunta
sobre la Luna con contenido generado en lugar de delegar la pregunta original a
Gemini. No se aceptó como simple alias deJSON. Ver adjudicaciones separadas.

En los5casos conusage reportado enambos perfiles,Qwen sumóaprox6,4veces las
neuronas deGLM. A unos950–1.100reportadas por petición,un cupo de10.000se consume
con pocas consultas de este tamaño. Son métricas del proveedor,no saldo real ni
una promesa de cantidad exacta de mensajes. El pool no reduce coste por consulta.

La comprobación adicional prevista de saludo/aclaración no pudo completarse:
el saludo recibiódaily_quota yno se continuó. No se cuenta como prueba de modelo
fallada ni superada. La cuota deambas cuentas quedó registrada hasta00:00UTC.
No se ejecutó otra inferencia después de identificar ese agotamiento.

Evidencia:docs/evidencia/MODELOS_CF02_20261107 yPOOL_CLOUDFLARE_20261107.

## Operación del pool

Cada mensaje selecciona una cuenta registrada disponible antes de consultar.
Alternancia entre cuentas no pausadas;un modelo para todas. La cuota se identifica
por cuenta,no por token:se rechazan dos entradas con mismoAccountID. Los estados
se guardan privados ypersisten al reiniciar. Se reconocen3036 y4006 cuando el
mensaje del proveedor identifica agotamiento diario. Una petición incierta no se
repite con otra clave. Una cuenta nueva se lee al siguiente turno desde el registro
propio,publicado atómicamente por una operación explícita del operador.

Registro operativo:settings.root/private/cloudflare-pool/registry.json. Estado:
quota-state.json junto al registro. No lee claves del entorno ni deZhana;solo
rutas privadas propias explícitas. Cf01ycf02son alias;no se muestran credenciales.

Alta futura,una vez guardada la credencial nueva en archivo0600propio:

```bash
.venv/bin/python ops/registrar_cuenta_cloudflare.py \
  --root /home/petrov/botsky/private/production \
  --pool-file private/cloudflare-pool/registry.json \
  --alias cf03 \
  --credentials-file /RUTA/PRIVADA/EXPLICITA/cf03.json
```

El archivo contieneaccount_id/api_token. El comando copia de forma privada y
publica el registro,sin poner secretos en argumentos niGit. --replace solo rota
una clave del mismoAccountID;no borra su cuota observada. Nunca volver a registrar
cf02como alta nueva para repetir el cierre actual.

## Despliegue y reversión

Parada propia observada,sin jobs,frontend pendiente o entregas inciertas. Backup
SQLite consistente,configuración yperfil anteriores yfuente641844a/código nuevo
archivados enprivate/deploy-cloudflare-pool-20261107T184053Z/. Esquema20sin migración. Integridad/FK correctas.
Perfil idéntico salvointerpreter. Copias de claves0600 verificadas contra fuentes
propias. Arranque listo,runtime/calls/puente autenticado ready. Supervisores ajenos
sin cambios dePID/estado. Sin llamadas,mensajes o inferencias durante el corte.

78pruebas locales pertinentes pasan:pool/cuotas/reinicio/alta/duplicados,composición,
frontend/runtime/integraciones ypresentación natural. Métodos de alta ylectura
pueden añadir cuentas sin reiniciar. No acredita render/recepción humanaWhatsApp.

Estado al cerrar:pool yQwen habilitados,pero proveedor sin cuota disponible en
ambas cuentas. La renovación permite seleccionar cuenta en mensajes nuevos;no
resucita recibos fallidos ni pruebas cerradas. Saludo/aclaración reales conQwen
siguen NO_PROBADO por cuota. No se programa una nueva campaña automática.

Reversión:parada observada,restaurar exclusivamente el perfil anterior guardado y
arrancar código compatible20. ConservarDB/efectos nuevos;no restaurar baseantigua
sobre datos nuevos. Se puede volver aGLMcon el mismo pool por decisión de operador;
no hay fallback automático de modelos ni activación de facturación.
