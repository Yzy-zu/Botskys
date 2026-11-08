# Botsky

**Producción activa06/11:** Botsky reemplazó a Zhana por instrucción expresa del propietario y dispensa del gateR10. [Estado, alcance y reversión](docs/R11_PRODUCCION_20261106.md). Zhana archivada recuperable; datos nuevos, sin migrar DB31. Los apartados siguientes conservan cierres históricos.

Reconstrucción independiente por comandos explícitos y lenguaje natural acotado.
Documentación de uso y referencia: [docs/GUIA_BOTSKY.md](docs/GUIA_BOTSKY.md) y [docs/commands.md](docs/commands.md).
Estado real y siguiente trabajo en [ESTADO_COMPARTIDO.md](ESTADO_COMPARTIDO.md).

### Ejemplos actuales y uso de **Responder**

- «Guarda una nota: comprar pan» o `/nota guardar pan`
- «Busca videos de recetas rusas» o `/dl buscar mp4 recetas rusas`
- «Pasa este archivo a PDF» o `/convertir pdf` adjuntando el documento

Para elegir una opción de un listado (videos o archivos de Drive), avanzar de página sobre una búsqueda concreta o confirmar una vista previa, usa **Responder** sobre el mensaje de esa lista en WhatsApp y escribe el número o la instrucción («2», «siguiente», «sí, envíalo»). En grupos, los números sueltos sin **Responder** se ignoran; en privado, si solo hay una lista vigente, también puedes escribir el número directamente.

## Estado actual y operación

Python 3.14 y SQLite propios. El núcleo arranca sin IA ni clasificador. No hay
dependencia del runtime de Zhana ni acceso a sus datos privados. Transporte productivo
y sesión exclusiva activos; Zhana archivada recuperable.
Integraciones optativas propias validadas por encargo posterior: [estado](docs/INTEGRACIONES.md).
Transporte WhatsApp, proceso continuo y composición de llamadas implementados:
[configuración y límites](docs/RUNTIME.md). Activación y reversión en [R11](docs/R11_PRODUCCION_20261106.md).
Galería conservada, Kazumi recuperado y permisos por integración/chat conectados:
[activos y permisos](docs/ACTIVOS_Y_PERMISOS.md). Tres álbumes originales sin fotos.

Inventario técnico en [docs/inventario](docs/inventario/README.md), con contratos,
hashes, límites, formatos, dependencias y superficie audiovisual. Tener una
capacidad en el registro no acredita que su handler esté construido.

Comprobaciones locales: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`.
Pruebas Node locales: `node --test calls/test/*.test.cjs` (sin navegador).
Configuración de ejemplo sin secretos en config.example.toml. Los datos propios
de laboratorio están en private/ (ignorado); nunca se importa private/ de Zhana.
Ayuda de todas las rutas: [docs/commands.md](docs/commands.md). Permisos y recepción
humana conservan los alcances documentados; presencia de ruta no acredita aceptación remota.

## Historial de fases y campañas (evidencia histórica)

Campaña automática real encargada, con resultados en Botsky Lab y laboratorio
detenido: [116 casos, hallazgos y bloqueos](docs/LAB_20261106.md).
Nueva campaña de descubrimiento10+10+10: [783casos y29informes](docs/STRESS_20261106.md).
[Paquete original de contraste](docs/CONTRASTE_STRESS_20261106.md); correcciones y evidencia posterior en el relevo.

R0–R9 cerrados localmente. Recorrido mínimo: [docs/R2.md](docs/R2.md).
Archivos, motores y CLI de trabajos: [docs/R3.md](docs/R3.md).
Contenido y voz sin despacho desde IA: [docs/R4.md](docs/R4.md).
Organización y scheduler local: [docs/R5.md](docs/R5.md).
Drive y recados explícitos: [docs/R6.md](docs/R6.md).
Economía y juegos: [docs/R7.md](docs/R7.md).
Administración y Minecraft: [docs/R8.md](docs/R8.md).
Audiovisual portado y límites: [docs/R9.md](docs/R9.md).
Integración local, matriz y límites de aceptación: [docs/R10.md](docs/R10.md). La fase R10 conserva su registro con cierre global formal abierto; este gate fue dispensado expresamente por el dueño para ejecutar el corte a producción en R11 ([docs/R11_PRODUCCION_20261106.md](docs/R11_PRODUCCION_20261106.md)), sin transformar pruebas pendientes en PASS ficticios.
Guía de uso: [docs/GUIA_BOTSKY.md](docs/GUIA_BOTSKY.md).
