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
