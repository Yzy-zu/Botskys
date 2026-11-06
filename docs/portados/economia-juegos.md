# Economía y juegos · R7

Referencia técnica fijada R0:Zhana7e12d54, con hashes de los ficheros consultados en
juegos-origen.json. Solo reglas y soluciones de biblioteca/entrega; no import de
runtime, modelos de interpretación, configuración, XP, biblioteca privada ni DB.

Reescritos ledger/reservas y reglas bajo contextos, recibos y esquema de Botsky.
Se conservan premios daily/racha, límites/turnos/pagos de blackjack, protección y
consentimiento en ruleta, porcentajes de devolución de cooperacha, precio/cantidad
y viewOnce de packs y temporizadores/premios de HH. Los controles lingüísticos
antiguos se sustituyen por sintaxis explícita y scopes del backend; ningún NLP.
No se usa contenido Gemini para decidir juegos, cantidades, miembros o acciones.

Componente acotado trasladado: rikolino.py, ahora adapters/gallery.py, con crédito
al proyecto Zhana. Se elimina root privado predeterminado: solo private/gallery
del root propio explícito, archivos publicados leídos sin symlinks, tipos/imágenes
estáticas/tamaños/plazos verificados. Constructor no accede a biblioteca antigua.
Fixtures nuevas con formas geométricas, IDs aleatorios y SQLite temporal propia.
No se importa, lee ni copia ningún original restringido o biblioteca real.

Diferencias: Botsky continúa la baraja/estado durables al reiniciar y concilia los
plazos; no reembolsa todas las partidas por un segundo objeto Application. La
frescura de aceptación usa tanto tiempo de origen como admisión. Precio/recursos
optativos requieren configuración explícita; el estado local no acredita una API.

Prueba nueva: ledger/hold y liquidaciones únicas, carreras de daily/AirDrop, juego
individual/mesa/natural/doble/timeouts, vistas entregadas, aportes propios con
redondeo agregado, foto real censurada, fallo/cancelación/incertidumbre sin repeat,
ruleta con miembros dobles y retorno único. Proveedor Evolution/miembros reales,
viewOnce recibido y recepción humana NOT_TESTED. Plan vigente únicamente rebuildbotsky.
