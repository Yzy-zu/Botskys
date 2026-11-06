# Botsky

Reconstrucción independiente por comandos explícitos. Plan vigente:
[/home/petrov/zhana/rebuildbotsky.md](/home/petrov/zhana/rebuildbotsky.md).
Estado real y siguiente trabajo en [ESTADO_COMPARTIDO.md](ESTADO_COMPARTIDO.md).

Python 3.14 y SQLite propios. El núcleo arranca sin IA ni clasificador. No hay
dependencia del runtime de Zhana ni acceso a sus datos privados. Repositorio solo
local: ningún transporte, proveedor, sesión ni transición activados.

Inventario técnico en [docs/inventario](docs/inventario/README.md), con contratos,
hashes, límites, formatos, dependencias y superficie audiovisual. Tener una
capacidad en el registro no acredita que su handler esté construido.

Comprobaciones locales: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`.
Configuración de ejemplo sin secretos en config.example.toml. Los datos propios
de laboratorio están en private/ (ignorado); nunca se importa private/ de Zhana.
