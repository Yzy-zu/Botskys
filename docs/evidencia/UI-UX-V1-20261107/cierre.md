# V1 · primer cierre local

Implementado: presentador determinista Block/Document v1; sin reescritura global
Markdown; sufijo de estado retirado en enqueue; división exacta preferentemente
por párrafo/línea/espacio. Ayuda por categorías y llamadas agrupadas; autoridad
humana, sin R9/call_authorized/LIVE_REQUEST. /estado y /cancelar sin ID resuelven
solo candidato propio por ámbito completo; varios requieren referencia explícita.
Datos canónicos y formas con ID conservados. Estado humano distingue incertidumbre,
rechazo y aceptación del servicio sin afirmar lectura.

3 pruebas nuevas de presentación, 14 de núcleo y 13 de comandos pasan localmente.
Primer ensayo detectó LIVE_REQUEST: corregido en placeholder del registro; no en
el contenido de usuario. No hay llamadas, envíos de prueba o pruebas de cliente.
VISUAL_OBSERVADO=NO_PROBADO. Sin despliegue en este cierre.

V1 sigue EN_CURSO: tokens indivisibles grandes necesitan alternativa de archivo,
revisión general de errores, citas y seguimiento de esperas. V2 puede construir
sobre la base de presentación/listas existente; cierre global exige esos pendientes.
Fuentes: Zhana rich_text.py y GUIA_UI_UX_Y_PERSONALIDAD (referencias V0); reescritura
propia, sin importar runtime. Matriz conserva las rutas no verificadas.

El propietario aclaró en este turno que el umbral 5% aplica a la ventana de cinco
horas y que la semanal no impide continuar; sustituye el criterio previo.

## Segundo corte V1

Añadida alternativa de archivo UTF-8 íntegro para token indivisible/código largo,
0600, registrado como artefacto propio con lease/retención y plan outbox. Seguimiento
por cita indexa partes intermedias aceptadas existentes; ámbito/24h verificados.
Aviso job_queued y cancelación ya no exponen HASH. Cinco pruebas nuevas PASS.
Base V1 habilita V2/V3; revisión visual cliente y todos los errores de dominios
se continúa en sus fases/V7; no se considera aceptación de cliente.
