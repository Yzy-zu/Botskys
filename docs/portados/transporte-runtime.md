# Transporte y arranque · referencia técnica

Referencia fijada por archivo y SHA256 en `transporte-runtime-origen.json`.
Solo `inbox.py`, `media_stream.py`, `providers/evolution.py` y
`calls/service/main.cjs` de Zhana: normalización de identidad/contexto, codec
incremental JSON/base64, endpoints técnicos y orden runtime→driver. No se consultó
su runtime conversacional, NLP ni planes históricos para este trabajo.

Se adaptan casi literalmente helpers `_jid`, `_timestamp`, `_content`, `_context`,
`_declared_size` y codec base64. Los contratos Incoming/Scope y su recepción durable
son propios: instancia lógica distinta de instancia Evolution, cuenta/época propias,
SQLite18 y referencias de artefactos opacas. Se excluyen del portado entradas de
reacciones y enrutado conversacional, y no se atribuyen permisos por nombre visible.

El arranque Node compone el runtime/driver ya portados. A diferencia de la fuente,
recibe configuración explícita por pipe, clave Live única y política inmutable,
comprueba cuenta y bloquea navegador/vinculación por defecto. Los workers y entrega
usan los recibos y CAS de Botsky. No usa Zhana como backend ni copia perfiles.

Se verifica el recorrido en `test_runtime.py`, `test_call_service_composition.py`
y `calls/test/configured-start.test.cjs`. Evidencia y límites: `../RUNTIME.md`.
