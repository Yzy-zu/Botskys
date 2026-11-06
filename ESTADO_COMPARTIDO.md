# Relevo Botsky

## 06/11/2026 19:07 UTC · Contraste terminado; cinco causas confirmadas corregidas

Encargo posterior del propietario: el principal es el agente de contraste y puede
apoyarse en subagentes Luna. Tres revisiones delegadas, análisis propio de IA/voz
y cancelación, revisión final del principal de adjudicaciones/código. AGENTS recoge
esta autorización posterior; no se reabrió la campaña ni se hicieron pruebas
remotas/envíos. Producto base b34db69, HEAD documental inicial3f6f3d6.

50/50claims adjudicados:5defectos confirmados,21límites/denegaciones correctos,
14errores de expectativa,8problemas de fixture/setup/harness y2sin reproducir.
Tres observaciones revisadas:1defecto,1incidente de harness y1dependencia externa.
Los5claims y1observación corresponden a5causas distintas, todas corregidas:
bucle de shield sobre launch ya cancelada; contenedor de audio/media sin validar
antes de análisis IA; metadata de búsqueda10vs8; diagnóstico «decimal» en enteros
(compartido ruleta/admin); oferta de pack para categoría inexistente.

Cancelación terminal se propaga sin bucle; la del padre conserva shield y retira
el hijo. Watchdog externo3s confirma atasco previo y salida corregida; regresiones
con hijo real, cancelaciones repetidas y OSError. IA verifica contenedor/pistas/
duración antes del dispatch: Ogg sintético roto pasa de aceptado a invalid_audio,
cero llamadas Gemini. WAV/MP4 válidos se conservan. No se promete decodificación
completa ni semántica remota. Registry/catálogo exportan ocho términos, parser
usa ese límite; diagnóstico entero/rango corregido. Packs verifican existencia
publicada con normalización/techo10000 de selección, sin imponer stock preoferta;
azar, nombres acentuados y catálogo>100 preservados, sin cargo por rechazo.

Falsos positivos contrastados: spoken_text completo2722caracteres frente al
feedback JSON truncado1700; literalidad de /voz ultima y duración orientativa;
OCR azul uniforme, ASR con tonos sin habla, PDF501páginas/imagen4097px; outputs
inyectados como adjuntos actuales por harness en vez de citas exactas. Adjuntos
opacos escuela/recados e idempotencia terminal cumplen sus contratos.

Sin reproducir: conversation-02, respuesta del modelo que negó adjuntos aunque
DB/SDK contienen archivos; regresión demuestra contenido PPTX/JSON enviado, no
interpretación remota. search_web-02, sin oracle determinista/RSS que demuestre
coincidencia descartada. No se modifican esas funciones por sospecha. Informe AGY
de descargas rechazado por proveedor sigue ausente; sus25resultados conservados.
No se reescriben los783resultados ni50claims originales; manifiesto SHA256 nuevo.

219Python distintos y286Node PASS:218en suite completa y1test adicional de
>100álbumes tras discovery, con red bloqueada. Cero fallos/omisiones; guardias
de red locales, cero intentos Python fuera de loopback. SQLite/motores/archivos sintéticos reales y
proveedores dobles. Ruff check/format132archivos, pip check y diffcheck correctos.
Informe docs/RESULTADO_CONTRASTE_20261106.md; adjudicación final y evidencia nueva
docs/evidencia/CONTRASTE-20261106/ (summary/adjudications, antes/después, guion,
logs y manifiesto). El principal revisó y corrigió normalización/límites de patches
delegados antes del cierre. Commit selectivo local con código, pruebas y relevo.

Campañas siguen CERRADAS, perfiles operativos/apagados intactos. R10 global y
fronteras remotas/humanas pendientes; R11 no iniciado. Sin servicios, webhook,
mensajes, llamadas, navegador, mutaciones grupo/servidor, GitHub, transición,
NLP, DB31 o perfiles/sesiones de Zhana. Cuota80%primaria/30%semanal al cierre;
umbral5% sigue vigente, guardar y parar sin reanudación automática.

## 06/11/2026 18:35 UTC · Descubrimiento10+10+10 terminado; paquete listo para contraste

Nuevo encargo del dueño: tres tandas de diez agentes AGY CLI, una herramienta por
sesión y modelo gemini-3.8-flash-medium. Aclaración posterior: recopilar resultados
sin corregir producto; el dueño elegirá otro agente de alto calibre para contrastar.
Cumplido: no cambios src/calls/dependencias ni contraste de otro modelo. AGENTS
actualizado con este alcance, sin reanudar automáticamente la campaña anterior.

30testers lógicos en tandas10+10+10,31arranques CLI (una reapertura técnica del
informe de notas tras propuesta JSON malformada), máximo10concurrentes. Todas las
invocaciones con modelo solicitado.29informes AGY completos; el reporte final de
descargas fue rechazado por el proveedor. Conserva propuesta/25casos/resultados;
no se reformuló para eludir el rechazo ni cambió modelo. Notas contenía3repeticiones
de literales dentro de JSON: expansión mecánica acotada, sin eval/JavaScript;
original/repair/hashes guardados. Reapertura recibió conversación nueva: no afirmar
que el historial anterior se recuperó.

783casos:319PASS (202positivos+117negativos),379SUSPECTED,83BLOCKED,2REVIEW. Tandas
252/262/269casos. 50claims de AGY pendientes de contraste, no50bugs confirmados.
256discrepancias son de pruebas negativas;326del estado esperado frente al observado.
No borrar ni adjudicar automáticamente esas discrepancias.134/152rutas observadas;
18NOT_TESTED y campos no observados explícitos.310checks adicionales de parser puro:
303PASS/7REVIEW de constructor por opciones incompatibles; separados de motores.

Backend real de Botsky, DB por herramienta, fixtures sintéticos propios y proveedores
reales según disponibilidad. Artefactos abiertos/hash/tamaño, PDF/páginas/texto,
ffprobe, ZIP/CRC/XML. DOCX/XLSX/CSV/JSON/HTML/MD/PPTX, PDFs escaneados/cifrados/corruptos/
501páginas, audio350s, video12s, TXT8MiB y archivo sparse1.000.000.001B para rechazo
antes de copia (no transferencia real1GB), imágenes grandes/animadas/corruptas.
Cadenas usan resultados previos; dependencias inexistentes bloqueadas. Actor propio
simulado, no teléfono/webhook real. XP/fotos de setup propios, no DB31/historial.

Hasta2muestras naturales por herramienta y resúmenes al Lab verificado.95POST reales
con HTTP201 incluido cierre;4mensajes internos de batería con ACKfixture; outboxdel
resto capturado localmente. Nivel de evidencia explícito, sin convertir ACKfixture
en proveedor ni ACK201 en render/recepción humana. Reportes conservan qué funcionó,
sospechas, argumentos/comandos, límites y huecos. No se encargó testeo manual al dueño.

Incidente de harness: helper de cuota agotó20s y canceló runner compartido de tanda1.
Al cerrar, conversor quedó en bucle de cancelación de creación de subproceso;
traza/private snapshots preservados. Se detuvo solo proceso de laboratorio y se
continuó esta campaña abierta con workers OSaislados, dos a la vez y watchdog.
Casos completados/partes aceptadas no repetidos; dos en curso retirados y REVIEW.
Repro mínima de cancelación, sin hijo real, no termina en3s y deja traza del bucle
en engines/process.py: observación reproducida para contrastar alcance/gravedad,
sin parche de producto. Datos temporales/resultados originales conservados.

Informe docs/STRESS_20261106.md; entrega docs/CONTRASTE_STRESS_20261106.md; paquete
público saneado docs/evidencia/STRESS-20261106 con50claims UNREVIEWED_AGENT_CLAIM,
783resultados/oracles,29informes,30dominios, cobertura, fixtures/hashes y observaciones
del orquestador. Evidencia completa privada0600 en private/stress-20261106/.
6pruebas focales de harness/guardias PASS, Ruff/formato131/pipcheck/diffcheck correctos.
No regresión histórica completa repetida sin cambio de producto. Revisión posterior
no debe lanzar campañas o correcciones por leer el paquete; decisión del dueño.

Campaña CERRADA, resumen enviado al Lab; efectos retirados de31perfiles (base+30tools),
copias de auth AGY eliminadas, sin procesos de campaña pendientes. Perfil operativo
anterior intacto/apagado. Drive requiere reconectar OAuth; audiovisual real y efectos
ruleta/grupo/servidor sin aceptación. R10 global ABIERTO, R11 no iniciado. No navegador,
llamada, sesión copiada/vinculada, cambio webhook/servicios/Zhana activa/NLP/DB31,
GitHub o transición. Cuota28%primaria/67%semanal; al5%guardar y parar sin reanudación.

## 06/11/2026 16:40 UTC · Campaña R10 real automática terminada; efectos del Lab retirados

Encargo posterior expreso: 1–10 sesiones AGY CLI, entrada simulada del propietario,
backend Botsky real y resultados al grupo WhatsApp Botsky Lab. Se verificó grupo
por metadata y se documentó excepción en AGENTS.md. Ocho sesiones en total: cuatro
propuestas iniciales, dos reemplazos por timeout240s y dos revisiones de evidencia;
seis SUCCESS/dos timeout conservados. AGY aislado bwrap, solo autenticación nativa
copiada temporalmente, sin tools/archivos/MCP, secretos de proveedores ni historia;
copias retiradas. Nunca parser/runtime de Botsky ni NLP. 46 comandos de la primera
tanda usados literalmente de propuestas; oracles revisados y congelados antes.

116casos,30herramientas representadas y controles AV adicionales. 96PASS (87positivos,
9negativos),6FAIL originales,14BLOCKED. 27herramientas tuvieron recorridos positivos;
no equivalen a aceptación completa de todas sus acciones. 77/152rutas parseadas;
75rutas y campos no observados publicados NOT_TESTED en route-coverage.json. Matriz
local anterior no se convierte en evidencia remota. R10 global sigue ABIERTO.

Se enviaron150POST con HTTP201 al Lab incluyendo avisos/cierre. Recibos producto
validan ACK/ID; no acreditan render Android/recepción humana. Entrada de operador
simulada, no teléfono/webhook real. Ámbitos privados conservados en backend; solo
frontera HTTP de pruebas redirige su salida al grupo verificado. Recados solo al
contacto Lab. DB SQLite18/artefactos propios en private/lab-20261106-run1/app; tandas
posteriores explícitas con snapshot SQLite/perfil previos. Preservados resultados,
ledgers privados0600, oracles y hashes saneados públicos.

Hallazgo producto corregido: /tareas omitía materia/vencimiento del texto. Ahora
muestra materia, fecha/hora de México, estado, página y comando de adjunto; dos
retest reales PASS. Drive cuotas/subida/búsqueda fallaron: Google HTTP400 invalid_grant,
token caducado o revocado; token fuente autorizado coincide y acceso fuente caducó.
REQUIERE RECONECTAR GOOGLE; no hubo subida exitosa ni cambio fuente. Presentación
del error ahora pide reconectar, comprobada realmente (PASS del error, no de Drive).
Drive elegir dependía de vista inexistente: KeyError del runner sin comando ejecutado;
corregido a BLOCKED antes de parser/red y prueba focal. Cancelar mano blackjack ya
repartida fue oracle erróneo: rechazo contractual correcto, revisión separada; mano
terminada normalmente. No se borran/reclasifican los seis FAIL de la tanda original.

Galería conservada (3álbumes/0fotos/0publicados) intacta. Seis PNG sintéticos publicados
solo en copia de laboratorio permiten pack compra/confirmación/entrega, cooperacha
con dos aportes/entrega, lluvia, AirDrop/reclamo y liquidación: tanda19/19PASS. Segundo
archivo para sticker y mensaje OAuth:2/2PASS. Notas/filtros, memoria, fechas/escuela/
encuestas, OCR/QR, conversión/PDF, edición/descarga W3C, búsqueda, Gemini texto/imagen,
voz literal/compuesta, ASR/resumen, recados, economía/BJ, avisos/XP y Minecraft consultas
con recorridos positivos. Solo fixtures sintéticos, sin usuarios/DB31/historial.

Quince controles semánticos PASS: páginas/contenido PDF, TXT/DOCX, ffprobe de cuatro
recortes, literalidad, AI /daily sin efecto, daily único, duplicado tras nueva app,
SQLite integrityok y cero reservas XP/partes packs-recados inciertas. 30pruebas
focales locales PASS (11org+15integración+4harness), Ruff/formato126/pipcheck/diffcheck
correctos. No se repitió suite histórica completa sin necesidad. Error inicial de
fuente tipográfica del harness y dos timeouts AGY conservados, no fallos Botsky.

Informe docs/LAB_20261106.md, paquete docs/evidencia/LAB-20261106/. Revisión AGY es
advisory, no juez. Pendiente UI menor: espaciado packs y estados técnicos en inglés.
Llamadas/Live/clip/avatar/agenda reales BLOCKED, sin sesión/navegador exclusivo;
ruleta y mutaciones grupo/servidor no efectuadas. No atribuir éxito a esas guardias.

Campaña TERMINADA y cierre enviado al Lab. Permisos messages/delivery/gallery send
y Drive write del perfil desechable retirados; perfil operativo anterior intacto y
efectos apagados. Ningún servicio instalado, webhook modificado, sesión copiada,
navegador/llamada, transición/R11 o GitHub. Zhana activa/código/config/DB31/servicios/
NLP/cambios/auditorías anteriores intactos; allí solo relevo posterior selectivo.
No repetir campaña ni reanudar envíos automáticamente. Cuota64%primaria/73%semanal;
al5%guardar y detenerse sin reanudación. Futuro R10 requiere concretar fronteras
pendientes; R11 sigue requiriendo aceptación y encargo de transición.

## 06/11/2026 15:50 UTC · Galería/VRM conservados; permisos por integración/chat completos

Encargo posterior de programar activos y configuración operativa. El propietario
eligió conservar activos de Zhana y profundizar búsqueda del VRM (pendiente solo si
no aparecía). Encontrado: dos copias regulares offline de Kazumi coinciden con
SHA2567f216a0d…332f683 declarado por Zhana. Copia propia18.433.312B, regular0600;
manifiesto/licencia/metadatos/procedencia privados. AutorSashTheDee, licencia
Redistribution_Prohibited conservada; modelo fuera de Git. No se arregló el enlace
roto de Zhana ni se abrió/copió perfil o sesión.

Galería original conservada: tres álbumes exactos, cero fotos, cero publicados.
Índice/álbumes/metadata propios; sin cambiar publicación o inventar imágenes.
Importación explícita por rutas de operador, sin fuentes antiguas al arrancar,
DB31/XP/compras/historial/tablas ajenas. Catálogo conectado y consultable con envío
apagado. Photo transport separado de recados; se inyecta biblioteca/configuración,
además de ámbitos de ruleta, admins optativos y nuclear con política.

Permisos cerrados versión1 por messages/drive/groups/minecraft/gallery/roulette/
nuclear/delivery. Listas explícitas sin comodines o ampliación de autoridad.
Switch global true rechazado; false solo compatibilidad. Perfil propio migrado y
copia previa mecánica. Validación antes de OAuth/HTTP/SSH, al admitir/procesar y
antes del motor. Job pendiente revocado se retira por cancelación existente sin
cargo/envío. Entregas fuera de permiso quedan pendientes. Instantánea inmutable
por proceso: cambios requieren reinicio, sin hot reload implícito.

Loader AV valida ruta propia0600/hash/GLB/licencia y recursos autocontenidos. VRM
real cargado offline:97mallas/1.264.796vértices,10mallas morph, siete expresiones
aplicadas y cuatro gestos/huesos. Texturas placeholder; noGPU/render/frameACK ni
recepción Android acreditados. Bundle781.976B. No navegador o proveedor iniciado.

202Python completos y286Node completos PASS, cero omisiones. Cero intentos fuera
de loopback en harness Python. Nuevas pruebas de copia/privacidad/paths/licencias,
catálogo, compra con confirmación/XP/duplicados, separación de permisos y revocación.
Ruff/format/pipcheck/diffcheck, SQLite18/integrityok, fuente/álbumes/hash conservados.
Evidencia docs/evidencia/ACTIVOS*; docs/ACTIVOS_Y_PERMISOS.md. RUNTIME/R9/R10 previos
intactos. CLI status propio reconoce VRM/biblioteca sin Node o proveedores. Catálogo
real local vacío coincide con origen, sin compra; DB de check separada.

Puntos de programación1y2 cerrados LOCAL. Permisos preparados; envíos/escritura/
galería-send/ruleta/nuclear/scheduler/avisos/agenda/AV/navegador apagados. Transporte
sigue local. Nada instalado/activado: sin pruebas remotas, mensajes/llamadas/cambios
de grupo/servidor, transición o GitHub. Zhana activa/código/config/DB31/datos y
cambios anteriores intactos; allí solo relevo documental posterior. Modelo/galería
propios privados ignorados. R10 remoto/Android/aceptación humana y R11 necesitan
encargo posterior. No falta programar contenido fotográfico: se conservó la galería
vacía existente. Cuota94%primaria/78%semanal; al5%guardar/parar sin reanudación.

## 06/11/2026 15:23 UTC · Programados puntos 1, 2 y 3; transporte/proceso/servicio AV

Encargo posterior del propietario para implementar WhatsApp, proceso continuo y
unión del servicio de llamadas. Rebuildbotsky vigente; no ejecución de otros planes.
Transporte Evolution propio: normalización de identidad/contexto/citas/menciones,
recibo durable antes de HTTP202, cola128, frescura/corte/época, medios incrementales
por API autenticada y referencias propias. Entrega asíncrona por partes con CAS,
leases y ACK/uncertidumbre; no repite envíos inciertos ni bloquea otros encargos.
SQLite propia18; historial de construcción y evidencias previos conservados.

Proceso serve optativo con HTTP autenticado solo loopback y límites. Bucles de texto,
medios, jobs, scheduler/avisos y GC; un medio lento no retiene comandos de otros chats.
Exclusión propia, reinicio, SIGTERM/SIGINT, cierre de conexiones incompletas y
cancelación durante arranque AV. Plantilla systemd preparada sin instalar/activar.

Integrations inyecta CallsClient con política verificada; modo externo propio o
subproceso Node administrado por pipe secreto/ready/revisión y supervisión. Main
Node propio compone runtime/driver/Live/componentes portados; verifica cuenta,
inicia runtime dentro del lock antes de driver y libera recursos ante fallos.
Navegador/entrantes/vinculación cerrados por defecto. IA no decide comandos; sin NLP.

188Python regresión completa PASS, cero intentos fuera de loopback. Focales finales
14runtime+3composición+1CLI real PASS incluyen tres métodos adicionales:191distintos.
282Node completos PASS +4focales (uno nuevo):283distintos verificados. Ruff/format,
pipcheck, diffcheck, SQLite18/integrityok y hashes de cuatro fuentes consultadas
sin cambios. Fallos/oracles de desarrollo y primer timeout de clip bajo carga
paralela conservados; regresión Python repetida sin esa carga pasa sin ampliar5s.
Ver docs/RUNTIME.md, ficha portados/transporte-runtime.md y evidencia RUNTIME.json.

Configuración propia0600 prepara tokens independientes y policy de llamadas para
dueño, sin grupos/features. Copias previas guardadas mecánicamente. Se conservan
transporte local, corte previo y ubicación de DB/artefactos; delivery/scheduler/
notices/call_service/allow_browser_launch/agenda_timers false. Estado local CLI
verificado; no arranca servicios ni proveedores. No webhook del proveedor cambiado,
ningún envío/llamada real, navegador, transición, GitHub o instalación activa tocados.
Zhana/DB31/perfiles/datos y cambios anteriores intactos; aquí solo construcción propia.

Puntos 1–3 cerrados a nivel programación/integración LOCAL. R10 remoto/R11 abiertos;
recepción WhatsApp/Android humana y activación necesitan encargo posterior. Galería,
VRM/licencias y permisos operativos restantes mantienen pendientes de producto previos.
Última cuota74%primaria/81%semanal; al5%guardar y parar sin reanudación automática.

## 06/11/2026 10:41 UTC · Punto1: credenciales válidas e integraciones propias

Permiso expreso posterior para leer/reutilizar credenciales/env Zhana, validar e
integrar proveedores. Se aplica solo a ese ámbito; no transición ni mensajes/
llamadas/mutaciones de grupo/servidor. Se leyó configuración/JSON de credenciales,
OAuth y variables Gemini seleccionadas de metadatos PM2, sin arrancar procesos,
importar runtime, NLP/AGY, DB31, historiales, perfiles/cookies o datos de usuario.

Siete claves Gemini autentican; modelo3.5flashlite válido y generación real correcta.
Runtime usa solo primera clave explícita, sin pool/rotación. Live3.8 autenticó setup
WebSocket sin llamar/capturar/saludar/enviar audio. Groq Whisper autentica y transcribe
un audio sintético generado por EdgeTTS. Evolution autentica y permite consulta de
estado/metadata de grupo; Minecraft consulta status real vía SSH sin cambios.
Drive OAuth refresca en copia propia; carpeta Botsky vacía independiente creada y
verificada, cuota consultada. CLI configurado /ia y /drive cuota funcionan de extremo
a extremo sin entrega externa. Todos los checks finales pasan. Sin afirmar recepción
humana ni campaña completa de funciones por comprobar credenciales.

Copias0600 ignoradas: private/integrations.json, private/config.integrations.toml,
private/drive/{client,token,folder}.json. Datos/SQLite/artefactos propios separados.
Composición optativa src/botsky/integrations.py y entrada python -m botsky.connected;
requiere rutas explícitas, no autodetecta fuentes. Envíos/mutaciones remotas bloqueados
por defecto; no webhook, navegador o servicio de llamadas iniciado. Live key/modelo
preparados en perfil propio; no se conecta al servicio activo de Zhana.

Tres pruebas de configuración/permissions/clave única/symlinks/denegación antes de
red y14pruebas de núcleo pasan. Evidencia pública saneada INTEGRACIONES-CREDENCIALES-
20261106.json y docs/INTEGRACIONES.md. Probes y audios sintéticos privados conservados.
Ningún secreto en Git. Zhana activa intacta; solo relevo documental adicional.

Punto1 completado en su ámbito. Quedan activos/licencias y campaña real de herramientas/
WhatsApp/Android/aceptación humana, y transición posterior; no avanzarlos sin encargo.
Cuota última9%primaria/34%semanal: conservar umbral5% con guardado y parada sin
reanudación automática si se alcanza. Este cierre no activa producción.

## 06/11/2026 10:29 UTC · Construcción autorizada local completa; R10 global abierto

R9 commits3a19e03/7ef1259; relevo documental Zhana7591fd3. R0–R9 mantienen su
cierre local. R10 etapa LOCAL terminada: inventario30herramientas/48componentes AV,
152rutas y190campos públicos;794filas originales conciliadas. Cada ruta tiene
observaciones de dominio y cada campo evidencia sintáctica explícita/canónica y
observaciones de dominio. Esto no convierte observaciones/denegaciones en PASS
semántico universal; se enlazan los oracles y límites concretos por acción/campo.
Metacampos del intérprete cancelado fuera del alcance, sin investigar ni ejecutar NLP.

169tests Python completos pasan;5focales finales de transporte añaden una prueba
nueva:170métodos distintos verificados. 279Node completos pasan sin omisiones.
Guardias de red loopback en harness Python/Node; cero intentos externos en regresión.
Transporte local durable independiente: ACK/duplicado/conflicto/época, copias de
bytes con ownership/lease/tamaño/SHA256; imagen→PDF recibido y abierto en laboratorio.
Ruff, pipcheck, diffcheck, CLI y DB propia17/integrityok comprobados. Los45hashes
AV de referencia consultados en Zhana permanecen intactos.

Corregidos en R10: opciones de subtítulos/recorte aplicables; IDs y fechas de agenda
visibles en texto; catálogo de clips con IDs reales; agenda no oculta llamada activa;
estado posterior al cierre y cancelación durable separado de liberación de medios;
backend retirado tras admisión conserva lápida; política Node congelada; callback
Live antiguo no puede sobrescribir el ID backend del control de avatar. Regresiones
de clips/avatar/agenda/audio preparado, grupos/XP/nuclear/ruleta, lecturas y archivos
reales añadidas con fixtures. Desarrollo y errores de oracle conservados aparte.

Evidencia docs/evidencia/R10.json, R10-inventory.json, R10-route-observations.json,
acceptance-matrix.csv y logs. Guía docs/GUIA_BOTSKY.md y procedimiento DOCUMENTAL
docs/TRANSICION_Y_REVERSION.md. Este procedimiento no se ha ejecutado.

R10 GLOBAL NO aceptado: faltan configuración propia/licencias/activos y campaña
real de proveedores/WhatsApp/Android/recepción humana. VRM y clave/modelo Live no
configurados, ni cuenta/sesión/perfil/transporte productivo de Botsky activados.
No se acordó recorte de capacidades. R10 remoto y R11 necesitan encargo posterior;
NO continuar automáticamente con ellos. Trabajo local autorizado completado.

Zhana activa, DB31/configuración/servicios/sesiones/transportes y cambios/auditorías
anteriores intactos; en Zhana solo relevo documental. Sin GitHub, pruebas remotas,
mensajes/llamadas reales o navegador. Última cuota33%primaria/38%semanal; no se
alcanzó el umbral5%. Mantener guardado y parada sin reanudación automática al5%.

## 06/11/2026 10:00 UTC · R9 cerrado localmente; avanza R10 local

Reanudación expresa del propietario; además pide portado audiovisual casi literal.
R0–R8 mantienen sus cierres previos. R9 ahora cerrado en construcción LOCAL: 36
componentes idénticos a Zhana y nueve adaptados; configuración/main/credenciales
sustituidos por composición propia explícita y única clave/modelo, sin pool.
Cliente HTTP Python técnico recuperado. Inventario audiovisual48archivos conciliado.
No se importa runtime ni datos privados de Zhana; fixtures, SQLite17 y almacenes propios.

Comandos explícitos de llamadas/estado/cierre/cancelación, agenda, clips y avatar;
permisos/binding por cuenta/actor/chat/época, journal y cancelación durable antes y
después de dispatch. Reinicio de worker incierto se concilia/cancela sin otra oferta.
Avisos de fallo a outbox propia, sin repetir la llamada ni entregar partes inciertas.
Gemini tiene solo los controles cerrados de la sesión que permite §8; nunca ejecutor
general, clasificador ni NLP. Entrantes, vinculación y navegador cerrados por defecto.

146tests Python de regresión pasan;14focales posteriores y dos carreras finales.
277tests Node pasan sin omisiones: regresión técnica portada + fronteras nuevas.
WebRTC real solo127.0.0.1: Opus/VP8/SRTP, energía y frames nuevos, peers/tracks cerrados.
Pulse/D-Bus/Xvfb efímeros propios: coexistencia, tono reproducido/capturado, energía,
procesos retirados por identidad y sockets eliminados. Ningún navegador abierto.
No confundir esto con WPP/compositor/escucha/render de VRM ni recepción Android.

VRM/licencia, credencial/modelo Live y proveedor/transporte reales NOT_CONFIGURED;
capacidad y ACK de avatar probados con fixtures y bundle compilado. Video conserva
el límite original dueño privado/primer grupo. Evidencia docs/evidencia/R9.json,
docs/R9.md y docs/portados/audiovisual-origen.json; checkpoints anteriores intactos.

Siguiente R10 LOCAL: conciliación de cada acción/campo, laboratorio aislado, matriz,
bloqueos visibles, guía del dueño y procedimiento documental de transición/reversión.
R10 remoto/aceptación humana y R11 requieren encargo posterior; no transición aún.
Ningún servicio productivo/DB31/configuración/sesión/transporte de Zhana modificado;
no GitHub ni pruebas remotas. Cuota64% primaria/42% semanal; guardar/parar al5%.

## 06/11/2026 04:30 UTC · PARADA al5%, sin reanudación automática

Consulta oficial5% primaria/48% semanal. Se guarda y se detiene por instrucción del
propietario; no continuar automáticamente. R6 cerrado353d57c, R7 cerrado1c08f1a,
R8 cerrado c9fda0d, siempre nivel LOCAL. Regresión R8:134tests;11focales posteriores
pasan. No APIs/proveedores/servicios activos ni recepción humana comprobados.

R9 INICIADO, NO cerrado: calls/pcm-queue.cjs con callId/sessionId/epoch, secuencia,
PCM s16le24k mono, paquete96000B, presión10s, copia/drain/clear/cierre. Dos pruebas
Node20.20.2 de muestras/identidad/epoch/presión/liberación pasan. Es una cola PCM
sintética, NO una llamada ni WebRTC/escucha. Sin navegador ni dependencia Node
remota/antigua instalada. Fuente audio-bridge técnica con hash en R9-partial.json.

Reanudar R9 leyendo ficha docs/portados/audiovisual.md y evidencia R9-partial.json;
completar control durable/agenda/recados/audio/Live/audiencia/video/clips/avatar,
servicio autenticado nuevo y WebRTC local real sin abrir navegador ni usar perfiles
activos. R10 local espera cierre de R9; R10 remoto/R11 requieren otro encargo.
No ejecutar fases de otros planes ni continuar NLP. Zhana activa/DB31/config/
servicios/sesiones/transportes y cambios/evidencias/auditorías previos intactos.
Solo commits locales selectivos. STOP-20261106-0430.json conserva punto de parada.

## 06/11/2026 · R8 cerrado localmente; siguiente R9 audiovisual

R6 commit353d57c; R7 commit1c08f1a. R8 esquema propio16, administración de dueño,
objetivos y roles verificados, avisos propios por persona/ID, ajustes XP de cuenta
verificada con límites/reservas. Mutación local y recibo atómicos; crash entre
escritura y publicación no duplica aviso. Ban previo al POST con aliases probados;
unban revoca registro sin añadir miembro. Incertidumbre bloquea nuevas mutaciones.

Nuclear implementado pero DESHABILITADO por defecto. Snapshot cerrado excluye
dueño/bots/admins, preview completo aceptado5min y confirmación posterior a entrega.
Reserva5000XP única; revalidación por objetivo; partes aceptadas/inciertas no se
repiten, restantes omitidas. Sin aceptados/inciertos devuelve coste completo;
algunos aceptados/inciertos conservan coste. Cancelación/crash preservan estado.

Cliente Groups nuevo HTTPX acotado y solución Minecraft SSH JSON/worker técnico
adaptados sin configurar servicios ni copiar claves. Minecraft controles cerrados,
consola allowlist, nombre de mod fuera de argv SSH; queries de amigos, mutaciones
de dueño y recibo/server_id que impide repetir cambio incierto. Worker trasladado,
no instalado ni ejecutado en servidor. Ningún import/runtime/configuración Zhana.

134tests completos y11focales finales de administración pasan; HTTPX MockTransport,
miembros/acciones dobles, SQLite real y proceso Python local real para IPC/timeout.
No SSH/grupos/servidor reales, recepción humana ni proveedor remoto. Ruff ydiffcheck
correctos; docs/R8.md y fichas/hashes/evidencia R8.json. Oracles/logs de desarrollo
anteriores preservados. Nuclear/conectores optativos apagados, sin datos activos.

Siguiente R9 (dependeR2–R4): frontera audiovisual nueva, contratos/agenda/audio/Live/
audiencia/video/clips/avatar. No abrir navegador ni copiar perfiles activos; buscar
frontera WebRTC local sin navegador si permite cumplir comprobaciones autorizadas.
R10 local espera R3–R9; remoto/R11 necesitan encargo posterior. No activar producción,
DB31/servicios/sesiones/transporte ni GitHub. Cuota última9% primaria/49% semanal;
al5%guardar y parar sin reanudación automática. Construcción autónoma vigente.

## 06/11/2026 · R7 cerrado localmente; sigue R8

R6 commit353d57c. R7 incorpora wallets por identidad verificada/cuenta/época,
ledger y reservas de margen, XP grupo normal1/HH20, daily24h/racha hasta48h.
Blackjack individual/mesa6, límites/pagos/natural/doble, tablero entregado vigente,
plazos y reembolso/liquidación única; reinicio continúa baraja persistida sin
sortear otra. Default de apuesta adaptativo20/50, corrige constante50 de R1.

Packs optativos: biblioteca publicada propia nueva, stock real sintético en pruebas,
oferta entregada5min, confirmación, fotos viewOnce al privado verificado, cargo
por partes y devoluciones; inciertas retenidas sin repetir. Cooperacha con vista
censurada real, aportes explícitos propios, original por ID/hash al completar,
80% al vencer agregado por persona,100% al cancelar/fallar conocido, incierto
retenido sin reenvío. Biblioteca técnica acotada adaptada de Zhana, sin ruta vieja
predeterminada ni copia de originales privados. Marca de vistos por ámbito.

HH: activación tras aviso, dueño para mutaciones, AirDrop500XP único, lluvia1–2
y premio privado4–6 (mínimo3), scheduler tick optativo con claves durables y partes;
cierre retira futuros efectos. Ruleta reglas/roster aceptados, apuesta propia,
miembros/roles/número verificados por frontera doble, protecciones, elección y
mutación reservada una vez. Fallo devuelve; incierto retiene sin repetir; pozo y
aviso privado de retorno20min con recibo. Broma ficticia sin lookup ni terceros.

Regresión116tests y12focales de fotos pasan; cierre completo117tests en log
R7-closure-final-tests.txt. Ruff/pipcheck/diffcheck y CLI init propios. Evidencia
R7.json, decisiones docs/R7.md, ficha/hashes en docs/portados/economia-juegos.md.
Proveedores/fotos/efectos de grupo reales, viewOnce recibido y recepción humana
NOT_TESTED. Conectores optativos apagados por defecto, sin datos anteriores/NLP.

Siguiente R8: acciones de dueño, objetivos verificados, advertencias/ban/nuclear
con preview+confirmación y cliente Minecraft acotado. R9 audiovisual después de
R2–R4; R10 local tras R3–R9, remoto/R11 requieren encargo posterior. Instalación
activa, DB31, servicios/sesiones/configuración y auditorías previas intactos. Solo
commits locales, nada GitHub. Cuota última23% primaria/51% semanal; al5% guardar
y detener sin reanudación automática. Continuación autónoma autorizada vigente.

## 06/11/2026 · Reanudación expresa; R6 cerrado localmente, sigue R7

«Prosigue» del propietario revoca parada anterior; consulta nueva56% primaria y
56% semanal. R6 completa migración6, Drive trabajos/leases y vistas propias,
selección solo después de entrega, ID remoto durable antes de subir, conciliación
por GET y corte incierto sin repetir POST/PUT. OAuth propio explícito0600, refresh
con lock y persistencia atómica, sin leer claves/configuración antiguas.

Recados: directorio exacto, dueño en privado, literal/cita/adjunto propio, borrador
y vista entregada5min, confirmación posterior y reserva atómica por destinatario/
parte. Revalidación de permiso/modo/directorio antes de cada parte, historial de
ACK, fallo incierto/cancelación/reinicio sin repetir. Cliente HTTPX nuevo probado
con MockTransport y HTTP loopback efímero real; ningún Evolution/Google remoto.
Todos los proveedores siguen sin configurar por defecto, sin secretos reales.

89tests completos pasan, Ruff/pipcheck/diffcheck correctos. Evidencia R6.json y
R6-closure-tests.txt; docs/R6.md y ficha de portado con hashes/créditos técnicos.
Los checkpoints R6-partial y logs de desarrollo se conservan sin convertirlos en
aceptación externa. Activación/WhatsApp/recepción humana NOT_TESTED.

Siguiente R7 economía/juegos: reglas, liquidación única, cooldowns, consentimiento
ruleta y packs. R8/R9 después de dependencias; R10 local tras todos. R10 remoto/R11
requieren otro encargo. Solo repo propio y fixtures; Zhana activa y cambios/NLP/
auditorías previos intactos, sin GitHub. Cuota última50% primaria/55% semanal;
al5% guardar, commits y parar sin reanudación automática.

## 06/11/2026 03:31 UTC · PARADA POR CUOTA5%, sin reanudación automática

Consulta oficial:5% primaria restante/40% semanal. Encargo detenido conforme al
umbral del propietario. R0–R5 cerrados localmente; R6 PARCIAL en06a2cef, sin cierre.
Evidencia y siguiente paso detallados abajo, STOP-20261106.json y R6-partial.json.
Revisión documental Zhana1f25dfc. Todo guardado con commits locales selectivos;
no iniciar más trabajo ni reanudar automáticamente. R10 remoto/R11 sin encargo.

## 06/11/2026 · R6 parcial guardado; R0–R5 cerrados localmente

R5 cierre9beff13 y corrección78cdbc6. Diez pruebas focales posteriores pasan:
revalidación del dueño de digest, revocación de amigo antes de entregar y retirada
de aviso reservado por cancelación. Logs R5-owner-revalidation.txt y
R5-cancel-access-revalidation.txt; regresión completa previa65tests preservada.

R6 iniciado, NO cerrado: cliente técnico Drive adaptado, sin importar Zhana ni
leer OAuth/config/private antiguos. Scope obligatorio botsky_scope, carpeta
única, ID reservado por futuro llamador, streaming/resumable hasta2GB, descarga
16MiB, conciliación por GET sin segundo POST; URL de upload restringida, sin
redirecciones. Función de token y carpeta explícitas; no configurado por defecto.
Directorio nuevo de recados, aliases exactos normalizados, colisiones rechazadas,
sin lista parcial ni destinatario inferido; hash para ligar futuras vistas.

Siete pruebas de cliente HTTPX con MockTransport y archivos temporales reales;
dos de directorio pasan. Esto no es Google remoto ni entrega de mensajes.
R6 sigue SIN handlers integrados: las rutas continúan indicando no construido.
Faltan OAuth/almacenamiento propio, vistas/selecciones Drive, trabajos/leases,
borradores de recados, confirmación privada de dueño con preview entregado,
reserva por destino/parte, cancelación, cliente y conciliación sin duplicados.
Ficha docs/portados/drive-recados.md; estado docs/evidencia/R6-partial.json.

Retomar R6 por esos contratos del único plan rebuildbotsky.md; no ejecutar otros
planes. R7–R9 pendientes. R10 local espera cierreR3–R9; remoto/R11 requieren otro
encargo. Instalación activa, DB31, configuración, sesiones, transportes, cambios y
auditorías anteriores intactos; solo laboratorio sintético. Sin NLP, GitHub,
navegador ni envíos remotos. Última cuota6% primaria/40% semanal; al5% guardar y
parar sin reanudación automática.

## 06/11/2026 · R5 cerrado localmente; sigue R6

R4 commit30aad3f; R5 commit9beff13. R5 esquema propio v5: memoria explícita literal, filtros/páginas,
corrección/olvido y borrado total con vista entregada ligada a snapshot/revisión.
IDs monotónicos. Contexto Gemini recibe solo ocho hechos propios como datos, sin
clasificador ni acceso al ejecutor. No se importó memoria ni dato anterior.

Recordatorios técnicos por fecha/hora México o intervalo de entrada. Scheduler
optativo CLI tick reserva origen interno autorizado + efecto + outbox atómicamente;
concurrencia/reinicio sin segunda reserva. Avisos vencidos600s se descartan también
al reclamar entrega, con revalidación de permisos/modo/pausa. Estado incierto no se
reenvía automáticamente. No hay servicio ni transporte real activado.

Escuela: tareas por ámbito, mutaciones de autor, adjunto propio compartido solo por
petición explícita en ese grupo, límites10MiB/32MiB, lease396d y revocación al borrar.
Horarios y digest solo dueño, rechazo de solapamientos y reserva diaria única.
Encuestas de texto: opciones completas, publicación aceptada antes del voto,
actualización monótona por origen/orden de admisión, cierre por autor/dueño.

65tests de regresión completa pasan, fixtures/SQLite/motores reales locales y
proveedores dobles. Nuevos casos: filtros/paginación, pausa/caducidad, memoria
propia en contexto IA y cero efectos desde contenido. Ruff/pip check/diffcheck,
CLI init/tick e integridad/FK de SQLite correctos. Evidencia docs/evidencia/R5.json,
R5-final-tests.txt; decisiones y límites docs/R5.md y docs/portados/organizacion.md.
Revisión posterior: nueve pruebas focales pasan; el aviso digest conserva permiso
owner y se deniega antes de transporte si cambia el dueño configurado. Evidencia
R5-owner-revalidation.txt. Poda general/operación prolongada pendientes de R10.

Siguiente R6: Drive/recados con destinos configurados, vistas/confirmación y clientes
acotados; R7–R9 por dependencias. Integración local R10 tras R3–R9. R10 remoto y R11
requieren otro encargo. Zhana activa/NLP/evidencias previas intactos. Sin GitHub,
mensajes externos ni navegador. Cuota comprobada9% primaria/41% semanal; umbral5%
guardar y parar sin reanudación automática. Continúa el encargo de construcción.

## 06/11/2026 · R4 cerrado localmente; sigue R5

R3 commit670bd73. R4 esquema propio v4, SDK Gemini de contenido nuevo (sin tools,
sin clasificador ni dispatcher), análisis de archivos propios, menciones exactas
fuera de citas/código/URL y continuidad solo sobre respuesta AI propia aceptada.
Contexto actor/chat/cuenta/época, TTL30min/6intercambios/16000caracteres; fuentes
literales24h. Fallo/cuota de IA no impide notas y medios locales.

Groq Whisper y Edge TTS conservan sus soluciones técnicas y proveedores. Literal
no consulta Gemini; composición genera guion y después voz. Cita/última exactas
con propiedad/entrega. Audio normalizado real y Opus48k mono verificado; proveedor
ASR mediante HTTPX MockTransport y TTS con CLI de fixture, no voz escuchada ni
calidad de proveedor aceptada. Todos los proveedores reales siguen apagados.

Marca durable antes de dispatch de proveedor: reinicio tras corte incierto no
repite generación/ASR/TTS. Resultado provider_interrupted/uncertain y recibos
conservados. /bot estado/modo/pausa/reanudar implementados; mutaciones de dueño,
apagado/pausa retiran trabajos y esperas y bloquean nuevas herramientas. Controles
de ayuda/estado/cancelación disponibles; activo/discreto sin espontaneidad.

56tests en regresión completa pasan, diez focales R4 después de cita verificada.
SDK real con cliente doble rechaza function_call y nunca ejecuta texto generado;
quota429/cooldown, deadline/close, scope/contexto/entrega, uploads/delete, audio y
resumen parcial comprobados. Fuente de «Botsky descarga...» de R2 pasa a conversación
por mención en R4, explícitamente documentado con prueba de cero herramientas.
Evidencia docs/evidencia/R4*. Sin llamadas remotas ni recepción humana.

Gemini requiere clave/modelo explícitos; no lee secretos/env privado ni hereda
configuración. Dependencias google-genai2.33.0/Edge7.3.1 instaladas offline en .venv
propio. Fuente/codecs/perfiles trasladados con hashes/créditos, sin NLP ni persona
antigua. Zhana activa y cambios/evidencias anteriores intactos; solo commits locales.

Siguiente R5: memoria explícita, recordatorios/scheduler propio, escuela/adjuntos/
horarios/resúmenes y encuestas. R6–R9 continúan tras dependencias; R10 remoto y R11
siguen sin autorizar. Cuota última26% primaria/43% semanal. Guardar y parar al5%
de cualquier ventana, sin reanudación automática. Construcción autónoma vigente.

## 06/11/2026 · R3 cerrado localmente; siguiente R4

R2 commit 7c8d0c1. R3 añade esquema propio v3, artefactos con hash/origen/ámbito,
leases y GC, trabajos durables con revisiones, dos motores concurrentes y exclusión
del worker, cancelación en ejecución y bloqueo de resultados tardíos. Directorios
propios 0700, archivos 0600, sin symlinks. Supervisor de grupo retirado si muere el
padre; scratch huérfano se retira solo bajo exclusión. Motor fuera de transacciones.

Comandos implementados: reacción de catálogo (4 activos con créditos/hash), sticker,
OCR/QR, edición MP3/MP4/WebM/SRT, documentos (19 destinos reales), sesiones PDF
persistentes y selección de páginas. Espera de archivo solo tras prompt propio
aceptado; nueva orden la reemplaza con aviso visible. PDF incierto se reenvía solo
con vista previa entregada y confirmación ligada a estado/revisión/hash/ámbito;
motor no se repite y se conserva historial de intentos.

Descargas: clientes técnicos de referencia adaptados sin Args/runtime antiguos,
activación explícita, fuentes/host/DNS/redirecciones acotadas, sin cookies/perfiles
ni plugins. Lista con ID real, selección propia tras entrega, Spotify exige elección,
anterior usa archivo retenido sin redescarga implícita. Buscador RSS nuevo con site:
y términos literales y sin atribuir relevancia no comprobada. Ambos remotos están
apagados por defecto. Pruebas solo con dobles/HTTPX MockTransport/proxy loopback,
salidas reales del flujo obtenidas de video sintético. Fuentes externas NOT_TESTED.

46 pruebas locales pasan: 25 de R1/R2 +15 de medios/archivos +6 de clientes/vistas.
19 formatos inspeccionados y texto Office recuperado; imagen→PDF, escaneo error
específico, dos páginas→DOCX, varias hojas→ZIP CSV, MP3/WebM/SRT y tiempos reales,
OCR/QR, cancelación, reinicio/lease, retiro del padre y confirmaciones. Evidencia
docs/evidencia/R3.json y R3-final-tests.txt; logs anteriores conservados. Ruff,
pip check, integridad SQLite y diffcheck del índice correctos. Datos sintéticos;
cargas máximas, pares completos de formato y recepción humana pendientes de R10.

Instalación editable en .venv propio desde build local, dependencias media fijadas
e instaladas offline desde distribuciones locales (con licencias/metadatos). No
import de Zhana/NLP en runtime, ningún acceso a su private/ ni modelo/corpus.
Créditos/hashes en docs/portados; no se trasladaron VRM/persona privada/perfiles.
DB de laboratorio propia v3 con cero notas, un recibo antiguo de ayuda sintético;
no se usará al transicionar. Zhana productiva y sus cambios/evidencias intactos.

Siguiente R4: Gemini con salida solo contenido, menciones verificadas, ASR/TTS,
voz literal vs composición, cuota/fallo aislados y adjuntos bajo contratos R3.
Después R5–R9 conforme dependencias. No R10 remoto/R11 ni GitHub sin encargo.
Cuota comprobada 47% primaria /47% semanal; continuar autónomamente, guardar y
parar al5% de cualquier ventana sin reanudación automática.

## 06/11/2026 · R2 cerrado; siguiente R3 y R4 según dependencias

R1 commits 6c33f10/ac6c0d6 (CSV LF corregido y comprobado en índice). Relevo de
Zhana actualizado documentalmente en d3953cd; cambios anteriores intactos.

R2: aplicación y CLI local funcionales sin IA/clasificador ni proveedores. Ingreso
sintético explícito con fuente/corte/frescura, identidad de adaptador y permisos
revalidados antes de efecto. DB propia esquema v2/application_id, inbox con
fingerprint por instancia/cuenta/mensaje, canonical v1 sin reinterpretación al
recuperar. /ayuda, /estado ID, /cancelar ID, notas literales y búsqueda con filtro.
Nota/recibo/efecto/resultado/outbox en transacción local; CAS por parte de entrega,
sin transacción durante send. Incertidumbre no se reenvía. Vista de notas se
habilita solo tras aceptación completa; TTL 15min, ámbito actor/chat/cuenta/época.

25 pruebas locales pasan (11 sintaxis +14 núcleo), SQLite temporal real, carreras,
reinicio, rollback con crash, identidad, cancelación, filtros y entregas. CLI parse,
init y ayuda comprobados en entorno propio; DB de laboratorio tiene solo recibo de
ayuda sintético, cero notas. Ruff/diffcheck e integridad SQLite correctos. Evidencia
docs/evidencia/R2.json y R2-tests.txt; decisiones en docs/R2.md y ficha de portado.

La DB de laboratorio no se usará al transicionar: R11 requiere datos vacíos nuevos.
R3 siguiente: artefactos/jobs/leases/cancelación en motor, medios/documentos/PDF,
descargas/selecciones y fronteras de red probadas sin llamadas remotas. R4 puede
avanzar sin adjuntos desde R2; R3 se requiere para adjuntos. R5–R9 respetan sus
dependencias. No dar por cerrados dominios que solo tienen sintaxis.

Producción, DB31, configuración, servicios, sesiones y transporte de Zhana no
tocados. Ningún envío remoto, navegador, llamada, compra ni GitHub. Cuota última
84% primaria /52% semanal; umbral5% de cualquier ventana, guardar y detener sin
reanudación automática. Continuación autónoma vigente, solo construcción local.

## 06/11/2026 · R1 cerrado; avanza R2

R0 commit ee22c2e. R1 implementa lexer incremental, registro de 152 rutas / tres
alias sin colisiones, argumentos tipados inmutables, spans y forma canónica v1,
errores por campo con uso/ejemplo y ayuda generada. Matriz 794 filas de acciones y
campos (30 familias más audiovisual). No clasificador, IA ni efectos en el parser.

11 pruebas contractuales pasan; incluyen todos los ejemplos de registro con I/O
prohibido, literalidad, opciones duplicadas/incompatibles, fechas/horas y selección
explícita. Ruff y diffcheck correctos; ayuda/matriz reproducibles. Evidencia:
docs/evidencia/R1.json y R1-tests.txt. Decisiones y límites en docs/R1.md.
No contar parsing como aceptación de negocio: matriz mantiene NOT_TESTED.

Siguiente R2: ingreso local verificado, configuración, ámbito/época/frescura,
recibos SQLite propios, permisos, estado/cancelación exactos, notas/búsqueda con
filtro; recuperación y duplicados sin repetir escrituras. Proveedores y transporte
real deshabilitados. Continuar autónomamente conforme a dependencias del plan.
Cuota comprobada 89 % primaria / 53 % semanal; umbral de parada 5 % sin reanudación.
Instalación activa y evidencia anterior intactas. Solo pruebas y commits locales.

## 06/11/2026 · R0 cerrado; R1 siguiente

Construcción autorizada en /home/petrov/botsky por encargo expreso. Único plan:
rebuildbotsky.md. La restricción documental inicial de ese archivo queda superada
por el encargo de ejecución; R10 remoto/R11 siguen sin autorizar.

R0: Git nuevo, entorno virtual propio, configuración sin secretos, DB SQLite propia
vacía con user_version=1 (solo metadatos de esquema). Inventario 30 declaraciones,
29 modelos con campos/validadores y 48 archivos audiovisuales. Dependencias,
activos/licencias y discrepancias documentados. No runtime prestado ni NLP.

Checkpoint mecánico previo separado: Zhana ref refs/checkpoints/botsky-r0-nlp-20261106,
commit 4efd99a. Patch y archivo de evidencia privados con manifiesto SHA256.
Conservados HEAD/index/worktree y auditorías ajenas. No se ha ejecutado ni
investigado NLP, ni instalado candidata alguna.

Comprobación de cierre: docs/evidencia/R0.json. No pruebas de motor, proveedor,
WhatsApp, navegador o recepción humana. Instalación activa no tocada; DB31,
servicios, configuración, sesiones y transportes intactos. Sin GitHub.

Siguiente: R1 matriz de cada acción/campo, lexer determinista con spans, registro
sin colisiones, argumentos tipados, ayuda y errores específicos. Cero efectos
en parser. Tras cierre, R2 según dependencias. R3–R11 aún pendientes.

Cuota inicial 99 % primaria / 55 % semanal. Consultar periódicamente; al 5 % de
cualquier ventana guardar y parar sin reanudación automática.
