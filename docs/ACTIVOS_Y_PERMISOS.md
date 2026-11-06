# Galería, Kazumi y configuración operativa

Encargo posterior: conectar galería/avatar y completar permisos por integración y
chat. El propietario pidió conservar los activos de Zhana y profundizar la búsqueda
del VRM; si no aparecía, permitía dejarlo pendiente. Se encontró y recuperó el mismo
archivo, por lo que no quedó pendiente el modelo. Se mantiene rebuildbotsky.md.

## Activos conservados

La galería de referencia contiene **tres álbumes, cero fotos y cero álbumes
publicados**. Se copió a `private/gallery` relativo a Settings.root con índice
propio y originales propios. Los tres álbumes conservan ID/nombre/slug/publicación;
metadatos de curación se guardan en un sidecar privado. No se publica un álbum ni
se inventan imágenes para llenar la biblioteca. `/pack catalogo` funciona con una
biblioteca vacía; para entregar fotos tendrá que existir contenido publicado.

El enlace del avatar activo de Zhana estaba roto. La búsqueda por nombre/extensión
en archivos locales y respaldos encontró **dos copias regulares de Kazumi** en un
respaldo antiguo. Ambas tienen exactamente el SHA256 declarado por Zhana:
`7f216a0d81f0933d3c3b9a9508cacd254fa4a54570d0b9fd323a6ddac332f683`.
No se abrieron sesiones/perfiles, no se leyó el contenido de archivos NLP/AGY ni
se ejecutaron sus planes. Tampoco se cambió el enlace roto de la instalación activa.

Se recuperaron18.433.312bytes a `private/calls/avatar/botsky.vrm`, archivo regular
0600, con manifiesto propio, metadatos originales y procedencia privada. En el GLB
constan título **Kazumi**, versión2.0, autor **SashTheDee**, uso `Everyone` y licencia
`Redistribution_Prohibited`. Se conserva esa declaración; modelo y galería quedan
ignorados por Git, en copia privada para el uso solicitado. No se presentan como
activos abiertos ni se redistribuye el VRM. Su hash coincide tras la copia.

Para la configuración actual, Settings.root es `/home/petrov/botsky/private`;
las rutas anteriores quedan en `/home/petrov/botsky/private/private/`. Se conserva
la ubicación previa para no migrar almacenamiento de forma implícita.

`assets_import.py` y `ops/importar_activos.py` implementan una importación explícita
con rutas de operador. No se invoca al arrancar el bot, ni contiene rutas antiguas
por defecto. Lee el índice en modo ro, selecciona únicamente álbumes/fotos y sus
relaciones, copia imágenes estáticas validadas a IDs/rutas propios y conserva la
publicación. Prepara antes de mover, rechaza destinos con datos, symlinks, hashes
incorrectos, licencia incongruente y recursos externos en GLB. No importa DB31,
notas, XP, compras, conversaciones ni tablas ajenas a esos activos.

El loader Node comprueba propiedad local, permisos0600, tamaño, formato GLB,
recursos autocontenidos, SHA256 y concordancia de licencia/manifiesto. Compila los
renderizadores ya portados de Zhana y suministra la copia al BrowserDriver propio
cuando se autorice su arranque. Consultar estado no arranca Node o navegador.

## Permisos independientes

El perfil privado tiene tabla `permissions`, versión1. Cada integración usa su
permiso; se elimina el interruptor global para habilitar mutaciones. Por
compatibilidad, el antiguo `mutations_enabled=false` se puede leer; `true` se
rechaza. Listas explícitas, sin comodines y sin ampliar amigos/grupos/contactos
configurados. Las acciones mantienen identidad, dueño, roles, consentimiento,
vistas, confirmación y recibos existentes.

| Bloque | Campos | Preparación propia actual |
| --- | --- | --- |
| messages | send, targets | envío false; contactos explícitos como posibles destinos |
| drive | read, write | lectura true; escritura false |
| groups | read, write, chats | lectura true en grupos ya permitidos; mutación false |
| minecraft | read, write | lectura true; cambio false |
| gallery | enabled, send, chats | biblioteca true en ámbitos permitidos; fotos false |
| roulette | chats, allow_admins | lista vacía; administradores protegidos |
| nuclear | enabled, chats | false; lista vacía |
| delivery | send, chats | envío false; ámbitos explícitos preparados |

Galería y recados usan fronteras de envío distintas: habilitar fotos no habilita
recados ni entrega general, y viceversa. El catálogo se consulta sin permiso de
enviar. Mensajero valida destino, grupos validan chat y método, Drive comprueba
lectura/escritura antes de OAuth y Minecraft antes de SSH. La escritura exige
lectura en estas tres últimas integraciones. Una ruleta habilitada requiere las
capacidades de grupo/mensajero que utiliza; nuclear exige grupos escritos y ámbito
explícito. La política central vuelve a revisar operación/chat al admitir y
procesar. Un job pendiente que pierde permiso se retira por los mecanismos de
cancelación existentes antes del motor/proveedor, conservando saldos y recibos.
Las entregas fuera de permiso permanecen pendientes sin POST ni ejecución repetida.

Los permisos se leen como una instantánea inmutable del perfil; su cambio requiere
reiniciar el proceso para cargar una política nueva. No hay autoampliación por
mensajes ni recarga silenciosa del entorno. `Settings.owner/friends/allowed_groups`
conserva autoridad general. Llamadas mantienen además la política `calls` autenticada
por revisión y los controles `call_service`; no se habilitan al tocar `groups`.

Si permanece el campo antiguo `evolution.delivery_enabled`, debe coincidir con
`permissions.delivery.send`; se rechaza una discrepancia. El perfil propio ya
prescinde de ese campo duplicado y del interruptor global.

El perfil propio0600 ya se migró a los campos explícitos y se guardó copia previa
mecánica en `private/integration-checks`. Transporte local, delivery, mutaciones,
fotos, ruleta/nuclear, scheduler, avisos, agenda y navegador continúan apagados.
Los proveedores de contenido conservan la configuración previamente validada;
no se invocaron proveedores del bot ni se hicieron pruebas remotas en este cierre.

## Evidencia y límite

`docs/evidencia/ACTIVOS-*` conserva comprobaciones nuevas sin reescribir las de
R9/R10/RUNTIME. El VRM real carga offline con el GLTFLoader/VRMLoaderPlugin actual:
97mallas,1.264.796vértices,10mallas con morphs, siete expresiones con influencias
aplicadas y cuatro gestos con movimiento de huesos. Bundle781.976bytes. La auditoría
usa **texturas de reemplazo**, sin GPU/navegador: acredita carga/estructura/efecto CPU,
no render, frame ACK visual ni recepción humana. Los bytes originales no se alteran.

Fixtures sintéticos comprueban copia de fotos, álbum no publicado, tabla privada
omitida, symlinks/hash/licencia/URL externa y destino ocupado. Composición real con
HTTP simulado verifica catálogo y compra/confirmación/liquidación de pack, permiso
por destino, separación entre integraciones y revocación antes del cargo/envío.
Regresión completa:202Python y286Node PASS, sin omisiones; cero intentos fuera de
loopback en el harness Python. Ruff/format/pipcheck/diffcheck correctos y SQLite18
propia integrityok. Se conservan las evidencias previas sin reescribirlas.

No se instaló/activó servicio, modificó Zhana activa, abrió navegador, envió mensaje,
realizó llamada, cambió grupo/servidor o publicó GitHub. Activación, campaña remota
de R10 y transición R11 siguen requiriendo encargo posterior. El contenido fotográfico
no es un pendiente de programación: se ha conservado la galería vacía que existía.
