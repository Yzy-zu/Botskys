# Botsky

Reconstrucción independiente por comandos explícitos. Plan vigente:
[/home/petrov/zhana/rebuildbotsky.md](/home/petrov/zhana/rebuildbotsky.md).
Estado real y siguiente trabajo en [ESTADO_COMPARTIDO.md](ESTADO_COMPARTIDO.md).

Python 3.14 y SQLite propios. El núcleo arranca sin IA ni clasificador. No hay
dependencia del runtime de Zhana ni acceso a sus datos privados. Repositorio solo
local. Transporte productivo, sesiones y transición siguen apagados.
Integraciones optativas propias validadas por encargo posterior: [estado](docs/INTEGRACIONES.md).

Inventario técnico en [docs/inventario](docs/inventario/README.md), con contratos,
hashes, límites, formatos, dependencias y superficie audiovisual. Tener una
capacidad en el registro no acredita que su handler esté construido.

Comprobaciones locales: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`.
Configuración de ejemplo sin secretos en config.example.toml. Los datos propios
de laboratorio están en private/ (ignorado); nunca se importa private/ de Zhana.

R0–R9 cerrados localmente. Recorrido mínimo: [docs/R2.md](docs/R2.md).
Archivos, motores y CLI de trabajos: [docs/R3.md](docs/R3.md).
Contenido y voz sin despacho desde IA: [docs/R4.md](docs/R4.md).
Organización y scheduler local: [docs/R5.md](docs/R5.md).
Drive y recados explícitos: [docs/R6.md](docs/R6.md).
Economía y juegos: [docs/R7.md](docs/R7.md).
Administración y Minecraft: [docs/R8.md](docs/R8.md).
Audiovisual portado y límites: [docs/R9.md](docs/R9.md).
Integración local, matriz y límites de aceptación: [docs/R10.md](docs/R10.md).
Guía breve: [docs/GUIA_BOTSKY.md](docs/GUIA_BOTSKY.md). R10 global/R11 pendientes.
Pruebas Node locales: `node --test calls/test/*.test.cjs` (sin navegador).
Ayuda de todas las rutas: [docs/commands.md](docs/commands.md). Los handlers de
bloques posteriores dan un límite explícito hasta que se construyan y comprueben.
