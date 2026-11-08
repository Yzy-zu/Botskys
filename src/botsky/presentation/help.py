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
        return "No reconozco esa opción. Escribe /ayuda o pídeme lo que necesitas con tus palabras."
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
                    f"⏱️ {field.option or field.name}: duración en segundos, minutos u horas (ej. {field.example}). "
                    f"Rango: {field.minimum:g}–{field.maximum:g} segundos."
                )
                if field.default is not None:
                    detail += f" Por defecto: {field.default:g} segundos."
                lines.append(detail)
        if spec.summary:
            lines.append(spec.summary)
        blocks.append(Block("paragraph", "\n".join(lines)))
    return Document(tuple(blocks)).text()


NATURAL_EXAMPLES = {
    'download_media': ('Busca videos de gatos', 'Descarga este enlace como audio', 'Dime más del segundo video'),
    'convert_document': ('Pasa este archivo a PDF', 'Convierte este documento a Word'),
    'save_note': ('Guarda una nota: comprar pan',),
    'find_notes': ('Busca mis notas de tortillas',),
    'manage_messages': ('Prepara un recado para Ana: llego a las cinco', 'Sí, envíalo'),
    'manage_reminder': ('Recuérdame entregar la tarea mañana a las ocho',),
    'conversation': ('Explícame este ejercicio',),
    'control_call': ('Llama al contacto autorizado', 'Cuelga la llamada'),
    'manage_conversation': ('Cómo está Botsky', 'Pausa Botsky diez minutos', 'Reanuda Botsky'),
}


def render_natural_help(registry, topic=''):
    topic = topic.strip().casefold()
    if not topic:
        return ('Pídeme lo que necesitas con tus palabras. Por ejemplo:\n\n'
                '• «Guarda una nota: comprar pan»\n'
                '• «Busca videos de gatos»\n'
                '• «Pasa este archivo a PDF» y adjunta el documento\n'
                '• «Recuérdame entregar la tarea mañana a las ocho»\n'
                '• «Explícame este ejercicio»\n\n'
                'Si falta un dato, te lo preguntaré. Usa Responder sobre esta lista y escribe el número para elegir una opción. '
                'También puedes pedirme ayuda con una herramienta concreta.')
    families = [family for family, (title, _) in FAMILIES.items()
                if topic in title.casefold() or any(s.family == family and topic in ' '.join(s.path) for s in registry.specs)]
    if not families:
        return '¿En qué puedo ayudarte? Puedes pedirme buscar videos, convertir documentos a PDF, guardar notas, recordar tareas o jugar.'
    blocks = []
    for family in families[:2]:
        title, purpose = FAMILIES[family]
        blocks.extend((Block('heading', title), Block('paragraph', purpose)))
        examples = NATURAL_EXAMPLES.get(family, ())
        if examples:
            blocks.append(Block('paragraph', '\n'.join('• «'+example+'»' for example in examples)))
    if any(s.permission == 'call_authorized' for s in registry.specs if s.family in families):
        blocks.append(Block('notice', 'Requiere llamadas habilitadas y autorización en este chat.'))
    blocks.append(Block('paragraph', 'Si falta algún dato te lo preguntaré antes de continuar. En acciones importantes siempre verás una vista previa para confirmar.'))
    return Document(tuple(blocks)).text()
