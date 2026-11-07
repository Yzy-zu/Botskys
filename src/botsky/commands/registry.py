"""Registro v1: sintaxis, campos, autoridad requerida y ayuda en una definición.

Construir una petición tipada no habilita ni ejecuta un handler.
"""

import re
from dataclasses import replace

from .types import CommandSpec, Field

ALIASES = {"descargar": "dl", "conv": "convertir", "web": "buscar"}
FORMATS = (
    "pdf",
    "docx",
    "doc",
    "odt",
    "rtf",
    "xlsx",
    "xls",
    "ods",
    "csv",
    "pptx",
    "ppt",
    "odp",
    "txt",
    "png",
    "jpg",
    "webp",
    "json",
    "html",
    "md",
)
VOICES = (
    "botsky",
    "mexicana",
    "colombiana",
    "argentina",
    "espanola",
    "mexicano",
    "colombiano",
    "argentino",
    "espanol",
    "chileno",
    "venezolano",
    "peruano",
    "anime",
)


def text(name="text", *, limit=8000, tail=False, required=True, original=None, example="ejemplo"):
    return Field(
        name,
        max_length=limit,
        tail=tail,
        required=required,
        original=original or name,
        example=example,
    )


def integer(
    name, minimum=1, maximum=10000, *, required=True, default=None, option=None, original=None
):
    return Field(
        name,
        "int",
        minimum=minimum,
        maximum=maximum,
        required=required,
        default=default,
        option=option,
        original=original or name,
        example=str(minimum),
    )


def identity(name, *, required=True, original=None):
    return Field(name, "id", required=required, original=original or name, example="ID_REAL")


def enum(name, values, *, option=None, required=True, default=None, original=None):
    return Field(
        name,
        "enum",
        choices=tuple(values),
        option=option,
        required=required,
        default=default,
        original=original or name,
        example=values[0],
    )


def flag(name, option, *, original=None):
    return Field(
        name, "flag", required=False, default=False, option=option, original=original or name
    )


def option(field, name, default=None, *, required=False):
    return replace(field, option=name, required=required, default=default)


PAGE = integer("page", required=False, default=1, option="--pagina")
CLOSED = flag("include_closed", "--cerradas")
DURATION = Field(
    "duration_seconds",
    "duration",
    minimum=1,
    maximum=31536000,
    example="10m",
    original="after_seconds",
)
DATE = Field("date", "date", example="2026-12-01", original="at")
CLOCK = Field("time", "clock", example="12:00", original="at")


def media_options():
    return (
        enum(
            "quality",
            ("small", "standard", "high"),
            option="--calidad",
            required=False,
            default="standard",
            original="options.quality",
        ),
        Field(
            "start_seconds",
            "seconds",
            required=False,
            default=0.0,
            minimum=0,
            maximum=10800,
            option="--desde",
            original="options.start_seconds",
            example="0",
        ),
        Field(
            "end_seconds",
            "seconds",
            required=False,
            minimum=0,
            maximum=10800,
            option="--hasta",
            original="options.end_seconds",
            example="5",
        ),
        enum(
            "subtitle_language",
            ("es", "en"),
            option="--idioma",
            required=False,
            original="options.subtitle_language",
        ),
    )


def build_specs():
    specs = []

    def add(path, family, action="", fields=(), *, operation=None, **kw):
        specs.append(
            CommandSpec(
                tuple(path.split()),
                operation or f"{family}.{action or 'run'}",
                family,
                action,
                tuple(fields),
                **kw,
            )
        )

    add(
        "ayuda",
        "core",
        "help",
        [text("topic", limit=64, tail=True, required=False)],
        permission="public",
        summary="Lista familias o detalla un comando.",
    )
    for command in ("estado", "cancelar", "confirmar"):
        add(
            command,
            "core",
            command,
            [identity("id", required=command == "confirmar")],
            effect="write" if command != "estado" else "read",
            confirmation="delivered_preview" if command == "confirmar" else "none",
        )
    add("bot estado", "manage_conversation", "status")
    add(
        "bot modo",
        "manage_conversation",
        "mode",
        [enum("mode", ("apagado", "discreto", "activo"), original="value")],
        permission="owner",
        effect="write",
    )
    add(
        "bot pausa",
        "manage_conversation",
        "pause",
        [enum("minutes", ("15", "30", "60"), original="value")],
        permission="owner",
        effect="write",
    )
    add("bot reanudar", "manage_conversation", "resume", permission="owner", effect="write")
    add(
        "reaccion",
        "send_sticker",
        fields=[enum("sticker_id", ("saludo", "risa", "pensando", "sonrojo"))],
        constants=(("requested", True),),
        effect="deliver",
        block="R3",
    )
    add("sticker", "make_sticker", attachment=True, effect="artifact", block="R3")
    add(
        "ia",
        "conversation",
        "respond",
        [text("text", tail=True)],
        attachment=False,
        effect="generate",
        block="R4",
    )
    add(
        "nota guardar", "save_note", fields=[text(tail=True, original="text_lines")], effect="write"
    )
    add("notas", "find_notes", fields=[PAGE, text("query", limit=200, tail=True, required=False)])
    for path, mode in [("ocr", "text"), ("qr", "qr")]:
        add(
            path,
            "read_image",
            constants=(("mode", mode),),
            attachment=True,
            effect="artifact",
            block="R3",
        )
    add(
        "transcribir",
        "transcribe_media",
        fields=[
            enum(
                "output_mode",
                ("texto", "resumen", "ambos"),
                option="--salida",
                required=False,
                default="texto",
            )
        ],
        attachment=True,
        effect="artifact",
        block="R4",
    )
    for container in ("mp3", "mp4", "webm", "srt"):
        add(
            "dl " + container,
            "download_media",
            "url",
            [
                *(
                    f
                    for f in media_options()
                    if (container == "srt" and f.name == "subtitle_language")
                    or (container != "srt" and f.name != "subtitle_language")
                ),
                Field(
                    "url",
                    "url",
                    max_length=2000,
                    original="url",
                    example="https://media.w3.org/2010/05/bunny/trailer.mp4",
                ),
            ],
            constants=(("container", container),),
            effect="artifact",
            block="R3",
        )
    source = enum(
        "source",
        (
            "youtube",
            "dailymotion",
            "vimeo",
            "facebook",
            "instagram",
            "tiktok",
            "spotify",
            "pornhub",
            "xnxx",
            "adult",
        ),
        option="--fuente",
        required=False,
        default="youtube",
    )
    container = enum("container", ("mp3", "mp4", "webm", "srt"), original="options.container")
    add(
        "dl buscar",
        "download_media",
        "search",
        [container, source, *media_options(), text("query", limit=300, tail=True)],
        effect="search",
        block="R3",
    )
    add(
        "dl elegir",
        "download_media",
        "choose",
        [identity("view_id", original="choice_view"), integer("choice", 1, 6, required=False)],
        effect="artifact",
        block="R3",
    )
    add(
        "dl detalle",
        "download_media",
        "inspect",
        [identity("view_id", original="choice_view"), integer("choice", 1, 6, required=False)],
        effect="read",
        block="R3",
        summary="Muestra título, autor, duración y enlace completos de una lista propia vigente.",
    )
    add(
        "dl anterior",
        "download_media",
        "previous",
        [container, *media_options()],
        constants=(("previous", True),),
        effect="artifact",
        block="R3",
    )
    add(
        "editar",
        "edit_media",
        fields=[container, *media_options()],
        attachment=True,
        effect="artifact",
        block="R3",
    )
    voice_opts = [
        enum("voice", VOICES, option="--voz", required=False, default="botsky"),
        enum(
            "effect",
            ("none", "robot", "radio", "ardilla", "demonio"),
            option="--efecto",
            required=False,
            default="none",
        ),
    ]
    add(
        "voz",
        "make_voice",
        "verbatim",
        [*voice_opts, text(tail=True)],
        constants=(("mode", "verbatim"), ("source", "provided")),
        effect="artifact",
        block="R4",
    )
    add(
        "voz crear",
        "make_voice",
        "compose",
        [
            *voice_opts,
            Field(
                "requested_seconds",
                "seconds",
                minimum=0.01,
                maximum=600,
                option="--duracion",
                required=False,
                example="10",
            ),
            text(tail=True),
        ],
        constants=(("mode", "compose"), ("source", "provided")),
        effect="artifact",
        block="R4",
    )
    for p, src in [("cita", "quote"), ("ultima", "last_reply")]:
        add(
            "voz " + p,
            "make_voice",
            "verbatim",
            voice_opts,
            constants=(("mode", "verbatim"), ("source", src)),
            effect="artifact",
            block="R4",
        )
    add("voces", "make_voice", "catalog", block="R4")
    add(
        "llamar",
        "control_call",
        "start",
        [
            flag("video", "--video"),
            option(
                replace(
                    DURATION, name="max_seconds", minimum=5, maximum=3600, original="max_seconds"
                ),
                "--duracion",
                300,
            ),
            option(text("topic"), "--tema"),
        ],
        permission="call_authorized",
        effect="call",
        block="R9",
    )
    for p, action in [("estado", "status"), ("colgar", "hangup"), ("cancelar", "cancel")]:
        add(
            "llamada " + p,
            "control_call",
            action,
            permission="call_authorized",
            effect="call_control" if action != "status" else "read",
            block="R9",
        )
    for p, action in [
        ("iniciar", "start"),
        ("agregar", "add"),
        ("terminar", "finish"),
        ("cancelar", "cancel"),
    ]:
        add(
            "pdf " + p,
            "manage_pdf",
            action,
            attachment=action in ("start", "add"),
            effect="artifact",
            block="R3",
        )
    add(
        "pdf extraer",
        "manage_pdf",
        "extract",
        [Field("pages", "pages", max_length=1000, original="pages", example="1,3-5")],
        attachment=True,
        effect="artifact",
        block="R3",
    )
    add(
        "pdf reintentar",
        "manage_pdf",
        "retry",
        [identity("id"), flag("confirm_uncertain", "--confirmar-incierto")],
        effect="artifact",
        confirmation="explicit_uncertain_retry",
        block="R3",
    )
    add(
        "convertir",
        "convert_document",
        fields=[enum("target", FORMATS)],
        attachment=True,
        effect="artifact",
        block="R3",
    )
    add(
        "tarea crear",
        "manage_school",
        "add_task",
        [
            option(text("subject", limit=100), "--materia"),
            option(replace(DATE, name="due_date", original="due_date"), "--fecha", required=True),
            option(replace(CLOCK, name="due_time", original="due_time"), "--hora"),
            flag("attach", "--adjunto"),
            text(limit=1000, tail=True),
        ],
        effect="write",
        block="R5",
    )
    add("tareas", "manage_school", "list_tasks", [PAGE, CLOSED], block="R5")
    for p, action in [
        ("completar", "complete_task"),
        ("borrar", "delete_task"),
        ("archivo", "get_attachment"),
    ]:
        add(
            "tarea " + p,
            "manage_school",
            action,
            [integer("task_id", maximum=9223372036854775807)],
            effect="read" if p == "archivo" else "write",
            block="R5",
        )
    day = integer("weekday", 1, 7, option="--dia")
    add(
        "horario agregar",
        "manage_school",
        "set_lesson",
        [
            option(text("subject", limit=100), "--materia", required=True),
            day,
            option(
                replace(CLOCK, name="start_time", original="start_time"), "--inicio", required=True
            ),
            option(
                replace(CLOCK, name="end_time", original="end_time", example="13:00"),
                "--fin",
                required=True,
            ),
        ],
        effect="write",
        permission="owner",
        block="R5",
    )
    add(
        "horario listar",
        "manage_school",
        "list_schedule",
        [replace(day, required=False)],
        block="R5",
    )
    add(
        "horario borrar",
        "manage_school",
        "delete_lesson",
        [integer("lesson_id", maximum=9223372036854775807)],
        effect="write",
        permission="owner",
        block="R5",
    )
    add(
        "escuela resumen configurar",
        "manage_school",
        "configure_digest",
        [
            Field("enabled", "bool", example="si", original="enabled"),
            option(replace(CLOCK, name="digest_time", original="digest_time"), "--hora"),
        ],
        effect="write",
        permission="owner",
        block="R5",
        example="/escuela resumen configurar si --hora 18:00",
    )
    add("escuela resumen estado", "manage_school", "status_digest", block="R5")
    add(
        "encuesta crear",
        "manage_poll",
        "create",
        [
            text("question", limit=300, example='"¿Hora?"'),
            replace(
                text("options", limit=100, example='"Opción 1" "Opción 2"'),
                repeated=True,
                min_items=2,
                max_items=10,
            ),
        ],
        effect="write",
        block="R5",
    )
    for p, action in [("votar", "vote"), ("resultados", "results"), ("cerrar", "close")]:
        fields = [integer("poll_id", maximum=9223372036854775807)]
        if action == "vote":
            fields.append(integer("choice", 1, 10))
        add(
            "encuesta " + p,
            "manage_poll",
            action,
            fields,
            effect="read" if action == "results" else "write",
            block="R5",
        )
    add(
        "recado preparar",
        "manage_messages",
        "prepare",
        [
            Field(
                "recipients", "contacts", option="--para", original="recipients", example="Amiga"
            ),
            enum("source", ("actual", "cita"), option="--fuente", required=False, default="actual"),
            flag("attach", "--adjunto"),
            text(limit=4000, tail=True, required=False),
        ],
        permission="owner",
        effect="preview",
        block="R6",
        example="/recado preparar --para Amiga -- hola",
    )
    for p, action in [("estado", "status"), ("enviar", "send"), ("cancelar", "cancel")]:
        add(
            "recado " + p,
            "manage_messages",
            action,
            [identity("draft_id")],
            permission="owner",
            effect="deliver" if action == "send" else "read" if action == "status" else "write",
            confirmation="delivered_preview" if action == "send" else "none",
            block="R6",
        )
    add("contactos", "manage_messages", "contacts", permission="owner", block="R6")
    add(
        "pack catalogo",
        "manage_pack",
        "catalog",
        [option(text("category", limit=120), "--categoria"), replace(PAGE, maximum=20)],
        block="R7",
    )
    add(
        "pack comprar",
        "manage_pack",
        "buy",
        [text("category", limit=120)],
        effect="purchase",
        confirmation="delivered_preview",
        block="R7",
    )
    add(
        "pack confirmar",
        "manage_pack",
        "buy",
        [identity("purchase_id")],
        effect="purchase",
        confirmation="delivered_preview",
        block="R7",
    )
    add("pack estado", "manage_pack", "status", [identity("purchase_id")], block="R7")
    add(
        "coop crear",
        "manage_cooperacha",
        "start",
        [text("category", limit=120), integer("target_xp", 50, 50000)],
        effect="write",
        block="R7",
    )
    add(
        "coop aportar",
        "manage_cooperacha",
        "contribute",
        [identity("challenge_id"), integer("amount", 1, 50000)],
        effect="spend_own_xp",
        block="R7",
    )
    for p, action in [("estado", "status"), ("cancelar", "cancel")]:
        add(
            "coop " + p,
            "manage_cooperacha",
            action,
            [identity("challenge_id", required=action != "status")],
            effect="read" if action == "status" else "write",
            block="R7",
        )
    for p, action in [
        ("iniciar", "start"),
        ("parar", "stop"),
        ("estado", "status"),
        ("lluvia", "rain"),
        ("airdrop", "airdrop"),
        ("reclamar", "claim"),
    ]:
        fields = (
            [
                option(
                    replace(
                        DURATION,
                        name="duration_seconds",
                        minimum=60,
                        maximum=86400,
                        original="duration_minutes",
                    ),
                    "--duracion",
                    3600,
                )
            ]
            if action == "start"
            else [
                identity(
                    "drop_id" if action == "claim" else "event_id",
                    required=action == "claim",
                    original="event_id",
                )
            ]
        )
        add(
            "hh " + p,
            "manage_happy_hour",
            action,
            fields,
            permission="friend" if action in ("status", "claim") else "owner",
            effect="read" if action == "status" else "write",
            block="R7",
        )
    kind = enum(
        "kind", ("preferencia", "dato"), option="--tipo", required=False, default="preferencia"
    )
    add(
        "mem guardar",
        "manage_memory",
        "remember",
        [kind, text(limit=1000, tail=True)],
        effect="write",
        block="R5",
    )
    add("mem listar", "manage_memory", "list", [replace(kind, default=None), PAGE], block="R5")
    add(
        "mem corregir",
        "manage_memory",
        "correct",
        [integer("memory_id", maximum=9223372036854775807), text(limit=1000, tail=True)],
        effect="write",
        block="R5",
    )
    add(
        "mem olvidar",
        "manage_memory",
        "forget",
        [integer("memory_id", maximum=9223372036854775807)],
        effect="write",
        block="R5",
    )
    add(
        "mem borrar-todo",
        "manage_memory",
        "forget_all",
        effect="preview",
        confirmation="delivered_preview",
        block="R5",
    )
    for p, action in [
        ("estado", "status"),
        ("jugadores", "players"),
        ("mundos", "worlds"),
        ("mods", "mods"),
        ("config", "config"),
        ("diagnostico", "discover"),
        ("iniciar", "start"),
        ("parar", "stop"),
        ("reiniciar", "restart"),
        ("backup", "backup"),
        ("recuperar", "recover"),
    ]:
        add(
            "mc " + p,
            "manage_minecraft",
            action,
            permission="friend"
            if action in ("status", "players", "worlds", "mods", "config", "discover")
            else "owner",
            effect="read"
            if action in ("status", "players", "worlds", "mods", "config", "discover")
            else "server_mutation",
            block="R8",
        )
    for p, action in [("activar", "enable_mod"), ("desactivar", "disable_mod")]:
        add(
            "mc mod " + p,
            "manage_minecraft",
            action,
            [text("name", limit=100)],
            permission="owner",
            effect="server_mutation",
            block="R8",
        )
    add(
        "mc consola",
        "manage_minecraft",
        "console",
        [text("command", limit=1000, tail=True)],
        permission="owner",
        effect="server_console",
        block="R8",
    )
    admin = [
        ("advertir", "warn"),
        ("quitar-aviso", "unwarn"),
        ("avisos", "warnings"),
        ("expulsar", "kick"),
        ("ban", "ban"),
        ("unban", "unban"),
        ("promover", "promote"),
        ("degradar", "demote"),
        ("silenciar", "mute"),
        ("desilenciar", "unmute"),
        ("cerrar", "lock"),
        ("abrir", "unlock"),
        ("xp-dar", "xp_grant"),
        ("xp-quitar", "xp_remove"),
        ("nuclear-preparar", "nuclear_prepare"),
        ("nuclear-confirmar", "nuclear_confirm"),
        ("nuclear-cancelar", "nuclear_cancel"),
    ]
    for p, action in admin:
        fields = []
        if action in ("warn", "unwarn", "warnings", "kick", "ban", "unban", "promote", "demote"):
            fields.append(identity("target", required=action != "warnings"))
        if action == "unwarn":
            fields.append(integer("warning_id", maximum=9223372036854775807))
        if action in ("xp_grant", "xp_remove"):
            fields = [
                option(identity("target"), "--objetivo"),
                integer(
                    "account_id", maximum=9223372036854775807, required=False, option="--cuenta"
                ),
                integer("amount", 1, 50000),
            ]
        if action in ("nuclear_confirm", "nuclear_cancel"):
            fields = [identity("draft_id")]
        add(
            "admin " + p,
            "manage_admin",
            action,
            fields,
            permission="owner",
            effect="read"
            if action == "warnings"
            else "preview"
            if action == "nuclear_prepare"
            else "group_mutation",
            confirmation="delivered_preview" if action == "nuclear_confirm" else "none",
            block="R8",
            example=("/admin " + p + " --cuenta 1 1")
            if action in ("xp_grant", "xp_remove")
            else "",
        )
    for p, action in [
        ("iniciar", "start"),
        ("mesa", "table"),
        ("entrar", "join"),
        ("repartir", "deal"),
        ("pedir", "hit"),
        ("plantarse", "stand"),
        ("doblar", "double"),
        ("estado", "status"),
        ("cancelar", "cancel"),
    ]:
        fields = (
            [integer("bet", 20, 1000, required=False, default=None)]
            if action in ("start", "table")
            else [identity("game_id", required=False)]
        )
        add(
            "bj " + p,
            "manage_blackjack",
            action,
            fields,
            effect="read" if action == "status" else "game",
            block="R7",
        )
    for p, action in [
        ("crear", "create"),
        ("entrar", "join"),
        ("jugar", "play"),
        ("estado", "status"),
        ("cancelar", "cancel"),
    ]:
        fields = (
            [integer("bet", 1, 1000, required=False, default=50)]
            if action == "create"
            else [identity("room_id", required=action != "status")]
        )
        add(
            "ruleta " + p,
            "manage_roulette",
            action,
            fields,
            effect="read" if action == "status" else "game",
            confirmation="rules_acceptance" if action in ("join", "play") else "none",
            block="R7",
        )
    add(
        "broma",
        "make_prank",
        fields=[text("label", limit=40, tail=True, required=False)],
        effect="fiction",
        block="R7",
    )
    for p, action in [("daily", "daily"), ("saldo", "balance"), ("top", "top")]:
        add(
            p, "manage_economy", action, effect="write" if action == "daily" else "read", block="R7"
        )
    add(
        "recordar en",
        "manage_reminder",
        "create",
        [DURATION, text(limit=1000, tail=True)],
        effect="schedule",
        block="R5",
    )
    add(
        "recordar el",
        "manage_reminder",
        "create",
        [DATE, CLOCK, text(limit=1000, tail=True)],
        effect="schedule",
        block="R5",
    )
    add("recordatorios", "manage_reminder", "list", [PAGE, CLOSED], block="R5")
    for p, action in [("cancelar", "cancel"), ("archivar", "archive")]:
        add(
            "recordatorio " + p,
            "manage_reminder",
            action,
            [integer("reminder_id", maximum=9223372036854775807)],
            effect="write",
            block="R5",
        )
    add(
        "buscar",
        "search_web",
        fields=[
            Field(
                "required_terms",
                "terms",
                required=False,
                max_length=800,
                option="--terminos",
                max_items=8,
                original="required_terms",
                example="Python,docs",
            ),
            text("query", limit=300, tail=True),
        ],
        effect="search",
        block="R3",
    )
    add("drive guardar", "manage_drive", "save", attachment=True, effect="remote_write", block="R6")
    add(
        "drive buscar",
        "manage_drive",
        "search",
        [text("query", limit=200, tail=True, required=False)],
        effect="search",
        block="R6",
    )
    add(
        "drive elegir",
        "manage_drive",
        "choose",
        [identity("view_id"), integer("choice", 1, 5, required=False)],
        effect="remote_read",
        block="R6",
    )
    add("drive cuota", "manage_drive", "capacity", permission="owner", block="R6")
    # Ampliación audiovisual: contratos internos inventariados en R0, adaptados a chat.
    for p, action in [
        ("lista", "list"),
        ("poner", "play"),
        ("pausa", "pause"),
        ("seguir", "resume"),
        ("repetir", "replay"),
        ("siguiente", "next"),
        ("parar", "stop"),
        ("volumen", "volume"),
    ]:
        fields = (
            [
                identity("clip_id", original="selection", required=False),
                option(text("query", limit=200), "--nombre"),
            ]
            if action == "play"
            else [Field("volume", "float", minimum=0, maximum=1, original="volume", example="0.7")]
            if action == "volume"
            else []
        )
        add(
            "clip " + p,
            "audiovisual.clip",
            action,
            fields,
            permission="call_authorized",
            effect="call_control",
            block="R9",
            example="/clip poner ID_REAL" if action == "play" else "",
        )
    add(
        "clip ajustar",
        "audiovisual.clip",
        "volume",
        [
            enum("direction", ("subir", "bajar")),
            Field(
                "adjustment", "float", minimum=0.01, maximum=1, original="adjustment", example="0.1"
            ),
        ],
        permission="call_authorized",
        effect="call_control",
        block="R9",
    )
    for p, action, values in [
        ("fondo", "background", ("studio", "neon", "sunset", "night")),
        (
            "expresion",
            "expression",
            ("neutral", "relaxed", "happy", "angry", "sad", "surprised", "wink", "laugh"),
        ),
        ("gesto", "gesture", ("wave", "nod", "shake_head", "hand_to_chest")),
        ("rubor", "blush", ("suave",)),
    ]:
        fields = [enum("name", values)]
        if action != "background":
            fields.append(
                Field(
                    "duration",
                    "seconds",
                    minimum=1,
                    maximum=15,
                    required=False,
                    default=3.0,
                    option="--duracion",
                    original="duration",
                    example="3",
                )
            )
        add(
            "avatar " + p,
            "audiovisual.avatar",
            action,
            fields,
            permission="call_authorized",
            effect="call_control",
            block="R9",
        )
    schedule_opts = [
        option(
            replace(DURATION, name="max_seconds", minimum=5, maximum=3600, original="maxSeconds"),
            "--duracion",
            300,
        ),
        option(text("live_request", original="liveRequest"), "--tema"),
        option(identity("audio_id", original="audioId"), "--audio"),
        flag("end_after_audio", "--terminar-audio", original="endAfterAudio"),
        option(
            Field("volume", "float", minimum=0, maximum=1, original="volume", example="0.7"),
            "--volumen",
            0.7,
        ),
    ]
    add(
        "llamada programar",
        "audiovisual.agenda",
        "create",
        [DATE, CLOCK, *schedule_opts],
        permission="owner",
        effect="schedule",
        block="R9",
    )
    add("llamada agenda", "audiovisual.agenda", "list", permission="owner", block="R9")
    add(
        "llamada reprogramar",
        "audiovisual.agenda",
        "update",
        [identity("id"), DATE, CLOCK],
        permission="owner",
        effect="schedule",
        block="R9",
    )
    add(
        "llamada cancelar-agenda",
        "audiovisual.agenda",
        "cancel",
        [identity("id")],
        permission="owner",
        effect="write",
        block="R9",
    )
    return tuple(specs)


class Registry:
    def __init__(self, specs=None, aliases=None):
        self.specs = tuple(build_specs() if specs is None else specs)
        self.aliases = dict(ALIASES if aliases is None else aliases)
        self.paths = {}
        for spec in self.specs:
            if (
                spec.path in self.paths
                or not spec.path
                or any(not re.fullmatch(r"[a-z][a-z0-9-]*", p) for p in spec.path)
            ):
                raise ValueError(f"colisión o ruta inválida: {spec.path}")
            names, options = set(), set()
            positional = [f for f in spec.fields if not f.option]
            for i, field in enumerate(positional):
                if (field.tail or field.repeated) and i != len(positional) - 1:
                    raise ValueError("texto final/lista debe ser el último posicional")
                if not field.required and any(f.required for f in positional[i + 1 :]):
                    raise ValueError("posicional requerido después de uno opcional")
            for field in spec.fields:
                if field.name in names or field.option and field.option in options:
                    raise ValueError("campo u opción duplicados")
                if field.name in dict(spec.constants):
                    raise ValueError("constante y campo colisionan")
                names.add(field.name)
                if field.option:
                    options.add(field.option)
            self.paths[spec.path] = spec
        roots = {p[0] for p in self.paths}
        if any(
            alias in roots or target not in roots or alias in self.aliases.values()
            for alias, target in self.aliases.items()
        ):
            raise ValueError("alias colisiona, forma cadena o apunta a comando inexistente")

    def help(self, topic=""):
        from ..presentation.help import render_help

        return render_help(self, topic)
