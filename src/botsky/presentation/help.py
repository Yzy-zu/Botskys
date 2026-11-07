"""Ayuda humana derivada del registro; autoridad y sintaxis quedan en el registro."""

from ..commands.editorial import FAMILIES
from . import Block, Document

CATEGORIES = (
    ("Buscar y crear", ("buscar", "dl", "ia", "voz", "transcribir", "ocr", "qr")),
    ("Archivos", ("sticker", "reaccion", "editar", "convertir", "pdf", "drive")),
    (
        "Organizar",
        (
            "nota",
            "notas",
            "mem",
            "recordar",
            "recordatorios",
            "escuela",
            "horario",
            "encuesta",
            "recado",
            "contactos",
        ),
    ),
    ("Jugar", ("saldo", "daily", "top", "bj", "ruleta", "pack", "coop", "hh", "broma")),
    ("Llamadas y video", ("llamar", "llamada", "clip", "avatar")),
    ("Control", ("bot", "admin", "mc", "estado", "cancelar", "confirmar", "ayuda")),
)

CALL_GROUPS = (
    ("Iniciar", ("llamar",)),
    ("Controlar", ("llamada estado", "llamada colgar", "llamada cancelar")),
    (
        "Agendar · solo el dueño",
        ("llamada programar", "llamada agenda", "llamada reprogramar", "llamada cancelar-agenda"),
    ),
)


def render_help(registry, topic=""):
    parts = topic.strip().lower().removeprefix("/").split()
    if parts:
        parts[0] = registry.aliases.get(parts[0], parts[0])
    selected = [s for s in registry.specs if s.path[: len(parts)] == tuple(parts)]
    if not selected:
        return "Comando desconocido. Usa /ayuda."
    if not parts:
        roots = {s.path[0] for s in registry.specs}
        blocks = [Block("heading", "Botsky · ayuda")]
        for label, names in CATEGORIES:
            commands = ["/" + name for name in names if name in roots]
            if commands:
                blocks.extend((Block("heading", label), Block("paragraph", " · ".join(commands))))
        covered = {name for _, names in CATEGORIES for name in names}
        if roots - covered:
            blocks.append(Block("paragraph", " · ".join("/" + n for n in sorted(roots - covered))))
        blocks.append(
            Block(
                "next_action",
                "Usa /ayuda COMANDO o /ayuda COMANDO ACCION para ver ejemplos y límites.",
            )
        )
        return Document(tuple(blocks)).text()
    if parts == ["llamada"]:
        blocks = [
            Block("heading", "Llamadas"),
            Block("paragraph", "Requieren llamadas habilitadas y autorización en este chat."),
        ]
        for label, names in CALL_GROUPS:
            blocks.extend(
                (Block("heading", label), Block("paragraph", "\n".join("/" + n for n in names)))
            )
        blocks.append(Block("next_action", "Ejemplo de ayuda: /ayuda llamada programar"))
        return Document(tuple(blocks)).text()
    families = list(dict.fromkeys(spec.family for spec in selected))
    blocks = []
    for family in families:
        title, description = FAMILIES[family]
        blocks.extend((Block("heading", title), Block("paragraph", description)))
    for spec in selected:
        lines = [spec.usage, "Ejemplo: " + spec.sample]
        if spec.permission == "owner":
            lines.append("Solo el dueño.")
        if spec.permission == "call_authorized":
            lines.append("Requiere llamadas habilitadas y autorización en este chat.")
            if spec.family.startswith("audiovisual"):
                lines.append("Durante una llamada autorizada.")
        if spec.confirmation != "none":
            lines.append("Requiere recibir la vista previa y confirmar con su comando vigente.")
        if spec.attachment:
            lines.append(
                "Adjunta el archivo al comando o responde al mensaje exacto que lo contiene; se verifican tipo y acceso."
            )
        for field in spec.fields:
            if field.kind == "duration":
                detail = (
                    f"{field.option or field.name}: entero con unidad s, m, h o d; ejemplo {field.example}. "
                    f"Rango: {field.minimum:g}–{field.maximum:g} segundos."
                )
                if field.default is not None:
                    detail += f" Por defecto: {field.default:g} segundos."
                lines.append(detail)
        if spec.summary:
            lines.append(spec.summary)
        blocks.append(Block("paragraph", "\n".join(lines)))
    return Document(tuple(blocks)).text()
