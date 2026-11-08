"""Resumen de telemetría tipada propia; nunca JSON truncado en el chat."""

from . import Block, Document, attach_document


def present_minecraft(result):
    from .domains import size, tabular

    data = result.data["response"]
    action = result.data["action"]
    if action == "config":
        labels = {
            "level-name": "Mundo",
            "gamemode": "Modo de juego",
            "difficulty": "Dificultad",
            "allow-cheats": "Trucos permitidos",
            "server-port": "Puerto de juego",
            "server-name": "Nombre del servidor",
            "online-mode": "Verificación de cuenta",
            "max-players": "Máximo de jugadores",
        }
        properties = data.get("properties")
        if not isinstance(properties, dict):
            return attach_document(
                result,
                Document(
                    (
                        Block("heading", "Configuración Minecraft"),
                        Block("notice", "No fue posible consultar la configuración del servidor en este momento."),
                    )
                ),
            )
        return tabular(
            result,
            "Configuración Minecraft",
            ("Propiedad", "Valor"),
            [
                (labels.get(k, k), v if isinstance(v, (str, int, bool, float)) else "No informado")
                for k, v in properties.items()
            ],
        )
    if action == "worlds":
        worlds = data.get("worlds")
        if not isinstance(worlds, list):
            return attach_document(
                result,
                Document(
                    (
                        Block("heading", "Mundos de Minecraft"),
                        Block("notice", "No hay información de mundos disponible."),
                    )
                ),
            )
        return tabular(
            result,
            "Mundos de Minecraft",
            ("Mundo", "Selección configurada"),
            [
                (
                    world.get("name") or "Nombre no informado",
                    "Sí"
                    if world.get("active") is True
                    else "No"
                    if world.get("active") is False
                    else "Desconocida",
                )
                for world in worlds
                if isinstance(world, dict)
            ],
            footer="Mundo establecido en la configuración.",
        )
    if action == "backup":
        blocks = [Block("heading", "Respaldo Minecraft")]
        reference = data.get("backup") or data.get("backup_id")
        if reference:
            blocks.append(Block("literal", str(reference)))
        if type(data.get("bytes")) is int:
            blocks.append(Block("paragraph", "Datos incluidos: " + size(data["bytes"])))
        if type(data.get("files")) is int:
            blocks.append(Block("paragraph", f"Entradas informadas: {data['files']}"))
        blocks.append(
            Block(
                "notice",
                "Respaldo creado correctamente en el servidor.",
            )
        )
        return attach_document(result, Document(tuple(blocks)))
    if action == "players":
        if data.get("online") is not True or data.get("players_known") is not True:
            return attach_document(
                result,
                Document(
                    (
                        Block("heading", "Jugadores"),
                        Block("notice", "No se pudo obtener la lista de jugadores conectados."),
                    )
                ),
            )
        blocks = [Block("heading", "Jugadores")]
        if type(data.get("count")) is int:
            blocks.append(
                Block(
                    "paragraph",
                    f"Conectados: {data['count']}"
                    + (f" / {data['max']}" if type(data.get("max")) is int else ""),
                )
            )
        players = data.get("players")
        if isinstance(players, list):
            blocks.extend(Block("literal", str(player)) for player in players)
            if not players:
                blocks.append(Block("notice", "No hay jugadores conectados actualmente."))
        return attach_document(result, Document(tuple(blocks)))
    if action == "status":
        blocks = [Block("heading", "Estado de Minecraft"), Block("notice", result.text)]
        world = data.get("active_world") or data.get("world")
        if world:
            blocks.extend((Block("paragraph", "Mundo configurado:"), Block("literal", world)))
        if data.get("container_status"):
            labels = {
                "running": "Activo",
                "exited": "Detenido",
                "created": "Creado, sin arrancar",
                "paused": "En pausa",
                "unknown": "Desconocido",
                "restarting": "Reiniciando",
            }
            blocks.append(
                Block(
                    "paragraph",
                    "Contenedor: " + labels.get(data["container_status"], "Estado no reconocido"),
                )
            )
        blocks.append(
            Block(
                "notice", "El servidor se encuentra activo."
            )
        )
        return attach_document(result, Document(tuple(blocks)))
    if action == "diagnostics":
        labels = {
            "python_available": "Python",
            "docker_available": "Docker",
            "data_available": "Almacenamiento",
            "configured_container_found": "Contenedor configurado",
        }
        return tabular(
            result,
            "Diagnóstico Minecraft",
            ("Recurso", "Estado"),
            [
                (
                    label,
                    "Disponible"
                    if data.get(key) is True
                    else "No disponible"
                    if data.get(key) is False
                    else "Desconocido",
                )
                for key, label in labels.items()
            ],
        )
    if action in ("start", "stop"):
        if action == "start":
            text = (
                "El servidor de Minecraft está listo y disponible."
                if data.get("verified") is True
                else "Iniciando el servidor de Minecraft. Estará listo en unos momentos."
            )
        else:
            text = (
                "El servidor de Minecraft se ha detenido correctamente."
                if data.get("status") == "ok"
                else "Deteniendo el servidor de Minecraft..."
            )
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Minecraft"),
                    Block("notice", text),
                    Block("next_action", "/mc estado"),
                )
            ),
        )
    return result
