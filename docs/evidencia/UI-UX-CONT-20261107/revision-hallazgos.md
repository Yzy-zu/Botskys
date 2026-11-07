# Revisión de la captura global inicial

Corrida031805:311tests,3fallos,0errores/omisiones/conexionesexternas. Captura155rutas
pero146candidatossemánticos: NUNCA se presentó como aceptación/visuales155PASS.

1. Spotifyperdiónotademetadatosal separar encabezadoVideos: errorproducto confirmado
pororacleprevio; search_note explícito conservado sin convertir Spotify en fuente
alternativa deaudio. Selección requerida intacta.
2. Dosoraclesesperaban2partesparaPDF/tarea: se alinean a1archivo concaption;
contenidoPDF/propiedad/ámbito siguen comprobados por decodificación y campos.
3. Nuevos5oraclesdehuecos: tarea completar/borrar, Blackjackpedir conmano/puntaje
persistidos/cartacrupiéroculta,banconregistro/objetivodoble/unACK,discover/stop/restart
conrunnerdoble yconsultahealth posterior,clip siguientecon2videosreales sintéticos
normalizados/driverdoble. Loscapturadossolo como negativosno acreditabanestoscasos.
4. Eloracletarea detectó «Tarea completed» enpresentación; estadohumano corregido.
5. Digestescolar cortabaa6000sinaviso. Ahora materializabloquestipadossinrecortar
los20incluidos e informa20de21conprueba>6000caracteres; recordatorioliteral/zona
comprobados ysin ejecutarcomandos escritoscomo texto.
6. Citadeparteinternadebeleerrespuestacompleta: source_full canónicosefijaunahvez
enprimeraparteyhash; propia/TTL/completitudantesde voz/recado/IA. Dosoraclesnuevos:
citatablamedia ytextoentregadoenarchivo. Tipotablaexcluyesolometadatosv2delpayload
POST, conservavalidaciónestrictay partesv0/v1. Fuenteoriginal24h no se renueva por
reintentar entrega.
7. TTLmostrado: absoluteexpiry/zona paraVideos/Drive/esperas dearchivo evita que
unaentregaretrasadaprometa15/5min desde que llega. No se amplía caducidad real.
8. FichasVideos/Web: título,metadatoscitados yURLporbloques; URLs segurasquedan
separadasdelosbloquesliteralespara ser reconociblesporcliente. Nombrescontildes/
asteriscosno reescritos; bloque literal cuandohacefalta. Comandocopiadolargo va
íntegroaarchivoantesdecortarse. Cliente real sigueNO_PROBADO.

Métricasbenchmark.json miden40fixturesidénticosporcasoconfuente4482c46/current,
no latencia de proveedor. PDF ysticker bajan2→1parte;almacenamientopuedecrecerpor
conservarfuente canónica. No se promete menorlatenciauniversal ni menosbytesdered.
Se realizará una captura global final sobre fuente corregida y revisión por ruta.

9. Corrida033037:320tests,0fallos/1error por timeout IPC de5s al generar primer
clip sintético (doble ffmpeg),319correctos; fuentes sin cambios y0redexterna.
Se amplía SOLO espera del fixture a30s manteniendo oracle de video y sesión.
10. Catálogo Pack conservaba categoría al consultar pero perdía filtro en siguiente
página. Se conserva literal en datos y comando con quoting; nuevo test usa6álbumes
propios con mismo nombre, página2 contiene1 y no envía fotos.17packsPASS.
