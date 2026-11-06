# Integraciones propias · permiso posterior del propietario

El06/11 el propietario autorizó expresamente reutilizar credenciales/env de Zhana,
comprobar su vigencia e integrarlos en Botsky. Se completó ese punto de configuración;
no es una transición ni aceptación de todas las herramientas en servicios reales.

| Proveedor | Comprobación real |
| --- | --- |
| Gemini | Las7claves autentican; modelo configurado disponible y generación de contenido correcta. Solo una clave explícita se integra en runtime, sin pool/fallback. |
| Gemini Live | Modelo configurado disponible y setup WebSocket autenticado; cerrado sin llamada, captura, saludo o audio. |
| Groq Whisper | Autenticación/modelo y transcripción real de audio sintético correctos. |
| Edge TTS | Generó audio sintético Ogg/Opus local, convertido a FLAC para probar ASR. No se envió a nadie. |
| Evolution | Autenticación, estado y lectura de metadata de grupo correctos. No mensajes ni mutaciones. |
| Drive | OAuth refrescado en almacenamiento propio; carpeta vacía Botsky propia creada/verificada y cuota consultada. No se importaron archivos anteriores. |
| Minecraft | Consulta real de estado mediante alias SSH/worker ya configurados; sin despliegue ni cambios. |

`/ia` y `/drive cuota` pasaron también entrada local → parser → recibo/trabajo →
proveedor real → resultado, usando el CLI configurado. La vigencia indicada es la
de esta comprobación, no una garantía de cuota o acceso futuro.

Configuración privada fuera de Git, permisos0600:

- `private/integrations.json`: proveedor/modelos y una clave por función; contactos
  configurados, referencias Minecraft y carpeta propia. Sin flags NLP/AGY/pools.
- `private/config.integrations.toml`: identidad/permisos y SQLite de laboratorio
  propios. Su transporte sigue siendo local.
- `private/drive/client.json`, `token.json`, `folder.json`: OAuth y destino propios.
  La renovación modifica únicamente la copia de tokens de Botsky.

Composición `Integrations` optativa, sin leer Zhana ni descubrir env global al iniciar.
El entrypoint habitual permanece sin proveedores implícitos. Entrada explícita:

```text
.venv/bin/python -m botsky.connected --config private/config.integrations.toml --providers private/integrations.json status
```

El subcomando `local` recibe una orden de operador con actor/chat explícitos y `work`
procesa su cola. No instala webhook ni admite mensajes de la cuenta activa. Los
adaptadores de envíos, grupos, Minecraft y subidas Drive rechazan mutaciones por
defecto antes de hacer red; el perfil mantiene `mutations_enabled=false`.

Live tiene credencial/modelo propios preparados; el servicio de llamadas permanece
apagado. No se copió perfil, cookie, sesión ni token del servicio activo de llamadas.
No se abrió navegador ni se llamó a nadie. Descargas/buscador quedan configurados,
sin una campaña de fuentes reales en este punto. Biblioteca y avatar/licencias
pertenecen al punto de activos pendiente y no se importaron.

Evidencia saneada: [resultados](evidencia/INTEGRACIONES-CREDENCIALES-20261106.json).
Tres pruebas focales de composición/secretos/symlinks/bloqueo antes de red y14 de
núcleo pasan. Los dos fallos iniciales del runner (atributo MIME y extensión de
audio esperada) eran oracles; se corrigieron y conservaron las trazas privadas.
No se modificó instalación/configuración/servicios activos de Zhana, DB31 ni NLP.
Solo se añade su relevo documental. No GitHub ni transición.
# Ampliación posterior: transporte y ciclo de servicio

Los puntos 1–3 de programación del encargo posterior incorporan webhook Evolution,
entrega asíncrona durable, proceso continuo y composición del servicio AV propio.
Ver [RUNTIME.md](RUNTIME.md) para configuración, evidencias y límites actuales.
Perfil propio actualizado con tokens independientes y política restringida;
transporte continúa local, envíos y automatismos apagados, servicio/navegador sin
activar. El estado siguiente conserva la validación previa de proveedores.
# Cierre posterior de activos y permisos

Galería y avatar conservados por instrucción expresa; Kazumi recuperado de respaldo
con SHA256 exacto y licencia privada preservada. Galería original de tres álbumes,
sin fotos y sin publicación. Composición conectada y permisos explícitos por
integración/chat sustituyen el interruptor global. Estado actualizado y evidencia
en [ACTIVOS_Y_PERMISOS.md](ACTIVOS_Y_PERMISOS.md). Ninguna activación o efecto remoto.

# Campaña real posterior · 06/11 16:38 UTC

El propietario encargó pruebas automáticas y envíos a Botsky Lab. Se ejecutaron
116casos con DB propia/entrada simulada y salidas reales exclusivas al grupo. Ocho
sesiones AGY de apoyo, sin integración en runtime. Estado/evidencia y límites:
[LAB_20261106.md](LAB_20261106.md). Se conservan las comprobaciones previas con
su fecha: **Drive ahora devuelve HTTP400 invalid_grant**, token caducado o revocado;
requiere reconectar Google. El token fuente autorizado coincide, no resuelve el
fallo copiarlo otra vez. Mensaje de error corregido y comprobado, sin subida exitosa.

Galería conservada vacía intacta; packs/cooperacha/HH usaron seis PNG sintéticos en
una copia propia de laboratorio. 150POST con HTTP201 al Lab incluyendo avisos/cierre,
sin atribuirles recepción humana. Perfil operativo anterior sin cambios; efectos
del perfil desechable también deshabilitados al terminar. Sin servicio/webhook,
sesión/navegador/llamada, mutación de grupo/servidor, transición o GitHub.

# Nueva campaña de profundidad · 06/11 18:35 UTC

Tres tandas de diez testers AGY, modelo gemini-3.8-flash-medium:783casos y29informes.
Descubrimiento sin cambiar producto;50claims para contraste posterior, no50defectos
confirmados. Balance y evidencia en [STRESS_20261106.md](STRESS_20261106.md).
95POST reales con HTTP201 al Lab contando cierre; resto de entregas de batería
capturadas como fixtures y etiquetadas. No recepción Android/humana acreditada.

Drive mantiene bloqueo OAuth; no se intentó reconectar por cuenta propia. Perfiles
base y30herramientas con efectos retirados al cerrar, autenticación AGY temporal
eliminada. Perfil operativo anterior intacto; no sesiones/navegador/llamadas,
mutaciones grupo/servidor, servicio/webhook, transición o GitHub. R10 global abierto.

# Revisión OAuth posterior · 06/11 19:53 UTC

Búsqueda explícita del propietario: token vigente/candidato31oct coincide con
Botsky y devuelve400 invalid_grant. Respaldo before31oct:401 invalid_client.
Respaldo27oct: renovación200 y consulta de cuota200, pero carpeta propia Botsky
devuelve404 con esa identidad/aplicación. No prueba borrado: puede ser acceso
limitado por cuenta/aplicación/scopes. Copia alternativa conservada privada0600
en private/drive/recovered-20261027; no sustituye runtime ni carpeta por falta
de acceso. No escritura remota ni cambios en Zhana. Evidencia OAUTH-REVISION y
OAUTH-RECUPERACION-20261106.json. Pendiente resolver acceso a carpeta con OAuth
compatible; no es correcto afirmar que todas las credenciales estén caducadas.

## Cuota verificada y aclaración del propietario · 06/11

El propietario aclara que usa almacenamiento general, no una carpeta Botsky
como requisito funcional. Consulta about/storageQuota con OAuth recuperado:
429.497GB totales,267.263GB usados,162.234GB libres;252.156GB usados en Drive,
papelera0. Scope confirmado drive.file: cuota global consultable, pero no otorga
acceso general a todos los archivos. El404 previo no invalida el OAuth.
No se modificó runtime/destino ni se escribieron archivos remotos. Evidencia
OAUTH-CUOTA-20261106.json.

## Búsqueda cuenta5TiB · 06/11 20:16 UTC

El propietario confirma que busca5TB, no la cuenta400GiB recuperada. Encontrada
evidencia histórica en Zhana private/three-repairs-20261101/google-quota.json:
5497558138880B (5TiB),59833432609B usados (55.724GiB); es evidencia histórica,
no cuota actual. Conexión cifrada Petrovsky examinada solo para OAuth Drive,
sin importar runtime/perfiles/sesiones: token coincide con Zhana actual y también
devuelve invalid_grant. Cruces de tokens31oct/anterior con secretos del mismo
client_id tampoco recuperan acceso; respaldo27oct válido sigue siendo400GiB.
Búsqueda ampliada JSON anidados/nombres alternativos y respaldos no encontró
otro token Drive distinto utilizable. Candidatos privados0600; fuentes intactas.
Sin sustitución runtime ni escrituras remotas. Evidencia OAUTH-BUSQUEDA-5TB*.json.

## OAuth5TiB renovado e integrado · 06/11 20:20 UTC

Tras reconexión del propietario en Petrovsky: renovación200, cuota200 confirma
5497558138880B (5TiB),90347137366B usados (84.142GiB),5035.858GiB libres.
Scope drive completo. Copia explícita client/token a private/drive propios0600,
previos conservados en before-renewal-20261106; fuente Petrovsky intacta.
Verificado mediante OAuthToken + DriveClient.storage_quota de Botsky; carpeta
previamente configurada también accesible. No crea carpeta ni cambia el destino,
permisos operativos, servicios o campañas. Cero escrituras remotas. Bloqueo
invalid_grant resuelto en perfil propio principal; copias de laboratorios cerrados
no se actualizan ni reactivan. Evidencia OAUTH-RENOVADO-5TB-20261106.json.
