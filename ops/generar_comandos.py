#!/usr/bin/env python3
"""Genera ayuda y conciliación acción/campo desde el registro y el inventario R0.

No importa Zhana. NOT_TESTED siempre refiere aceptación del dominio, no sintaxis.
"""

import csv
import json
from dataclasses import asdict
from pathlib import Path

from botsky.commands.registry import Registry

ROOT = Path(__file__).resolve().parents[1]

APPLIES = {
    "manage_conversation": {"value": {"mode", "pause"}},
    "manage_school": {
        "text": {"add_task"},
        "subject": {"add_task", "set_lesson"},
        "due_date": {"add_task"},
        "due_time": {"add_task"},
        "time_text": {"add_task", "set_lesson", "configure_digest"},
        "task_id": {"complete_task", "delete_task", "get_attachment"},
        "weekday": {"set_lesson", "list_schedule"},
        "start_time": {"set_lesson"},
        "end_time": {"set_lesson"},
        "lesson_id": {"delete_lesson"},
        "enabled": {"configure_digest"},
        "digest_time": {"configure_digest"},
        "page": {"list_tasks"},
        "include_closed": {"list_tasks"},
        "attach": {"add_task"},
        "attachment_id": {"add_task"},
    },
    "manage_poll": {
        "question": {"create"},
        "options": {"create"},
        "poll_id": {"vote", "results", "close"},
        "choice": {"vote"},
    },
    "manage_messages": {
        "draft_id": {"status", "send", "cancel"},
        **{f: {"prepare"} for f in ("recipients", "text", "source", "attach")},
    },
    "manage_pack": {
        "category": {"catalog", "buy"},
        "purchase_id": {"buy", "status"},
        "page": {"catalog"},
    },
    "manage_cooperacha": {
        "category": {"start"},
        "target_xp": {"start"},
        "challenge_id": {"contribute", "status", "cancel"},
        "amount": {"contribute"},
    },
    "manage_happy_hour": {
        "duration_minutes": {"start"},
        "event_id": {"stop", "status", "rain", "airdrop", "claim"},
    },
    "manage_memory": {
        "memory_id": {"correct", "forget"},
        "kind": {"remember", "list"},
        "text": {"remember", "correct"},
        "page": {"list"},
    },
    "manage_minecraft": {"name": {"enable_mod", "disable_mod"}, "command": {"console"}},
    "manage_admin": {
        "target": {
            "warn",
            "unwarn",
            "warnings",
            "kick",
            "ban",
            "unban",
            "promote",
            "demote",
            "xp_grant",
            "xp_remove",
        },
        "warning_id": {"unwarn"},
        "account_id": {"xp_grant", "xp_remove"},
        "amount": {"xp_grant", "xp_remove"},
        "draft_id": {"nuclear_confirm", "nuclear_cancel"},
    },
    "manage_blackjack": {
        "bet": {"start", "table"},
        "game_id": {"start", "table", "join", "deal", "hit", "stand", "double", "status", "cancel"},
    },
    "manage_roulette": {
        "bet": {"create"},
        "room_id": {"create", "join", "play", "status", "cancel"},
    },
    "manage_reminder": {
        "text": {"create"},
        "time_text": {"create"},
        "at": {"create"},
        "after_seconds": {"create"},
        "reminder_id": {"cancel", "archive"},
        "include_closed": {"list"},
        "page": {"list"},
    },
    "manage_drive": {"query": {"search"}, "choice": {"choose"}, "attachment_id": {"save"}},
    "control_call": {"topic": {"start"}, "max_seconds": {"start"}, "video": {"start"}},
    "manage_pdf": {
        "attachment_ids": {"start", "add", "extract"},
        "pages": {"extract"},
        "confirm_uncertain": {"retry"},
    },
}

INTERNAL = {
    "interpretation": "Sustituido por comando canónico, spans y recibo de Botsky. Sin intérprete.",
    "literal_span": "Texto final literal y posiciones en mensaje original; nunca anclas inventadas.",
    "attachment_id": "Resolución backend: adjunto actual → cita exacta admisible; identidad/lease por ámbito.",
    "attachment_ids": "Referencias backend de la sesión PDF (máximo 20), sin rutas públicas.",
    "time_text": "Spans de fecha/hora técnica explícita; no se interpreta tiempo natural.",
    "summarize": "Derivado de output_mode: texto/resumen/ambos; sin dos fuentes contradictorias.",
    "format": "Derivado de container mp3/mp4/webm/srt; no se pide una segunda clasificación audio/video.",
    "options": "Campos quality/start_seconds/end_seconds/subtitle_language y container tipados en registro.",
    "requested": "Siempre True para /reaccion explícita; no espontaneidad.",
}


def render():
    registry = Registry()
    catalog = json.loads((ROOT / "docs/inventario/catalog.json").read_text())
    args = json.loads((ROOT / "docs/inventario/args.json").read_text())
    model_files = {v["file"] for v in args.values()}
    commands = []
    rows = []
    for spec in registry.specs:
        item = asdict(spec)
        item.update(usage=spec.usage, example=spec.sample, acceptance="NOT_TESTED")
        commands.append(item)
    for tool in catalog:
        family = tool["name"]
        props = tool["parameters"]["properties"]
        actions = props.get("action", {}).get("enum", [""])
        for action in actions:
            specs = [
                s
                for s in registry.specs
                if s.family == family and (not action or s.original_action == action)
            ]
            for field, schema in props.items():
                applies = field not in APPLIES.get(family, {}) or action in APPLIES[family][field]
                mapped = [
                    (s, f)
                    for s in specs
                    for f in s.fields
                    if f.original == field or f.name == field
                ]
                constant = [(s, v) for s in specs for k, v in s.constants if k == field]
                mapping = "; ".join(sorted({f.name for _, f in mapped}))
                decision = (
                    "Campo público tipado en registro; validar autoridad y negocio en su bloque."
                )
                if not applies:
                    mapping, decision = (
                        "no aplica",
                        "Rechazado para esta acción; no es una capacidad eliminada.",
                    )
                elif field == "action":
                    mapping, decision = (
                        "ruta explícita",
                        "La ruta determina la acción sin inferencia.",
                    )
                elif field in INTERNAL:
                    mapping, decision = mapping or "backend", INTERNAL[field]
                elif constant:
                    mapping, decision = (
                        "constante: " + repr(sorted({str(v) for _, v in constant})),
                        "Modo/fuente fijado por la ruta explícita.",
                    )
                elif family == "conversation":
                    mapping, decision = (
                        "Result/presentación",
                        "Salida de contenido: respond/ask/silent, tabla/footer/text_lines; no argumentos del ejecutor ni acciones desde IA.",
                    )
                elif (
                    family == "manage_blackjack"
                    and field == "game_id"
                    and action in ("start", "table")
                ):
                    mapping, decision = (
                        "backend",
                        "Al crear el backend emite ID propio; game_id de creación no selecciona otra partida.",
                    )
                elif family == "manage_roulette" and field == "room_id" and action == "create":
                    mapping, decision = (
                        "backend",
                        "Al crear el backend emite ID propio; no se permite sobrescribir salas.",
                    )
                elif not mapping:
                    raise ValueError(f"campo sin conciliar: {family}/{action}/{field}")
                command = "; ".join(s.command for s in specs)
                if family == "manage_conversation" and action == "cancel":
                    command, mapping, decision = (
                        "/cancelar ID",
                        "ID de encargo",
                        "Control de núcleo con ámbito y época; nunca cancelación implícita de la tarea más reciente.",
                    )
                if family == "conversation" and action in ("ask", "silent"):
                    command = "presentación de /ia o mención verificada"
                rows.append(
                    {
                        "family": family,
                        "original_action": action or "única",
                        "original_field": field,
                        "original_schema": json.dumps(
                            schema, ensure_ascii=False, separators=(",", ":")
                        ),
                        "command": command,
                        "new_field": mapping,
                        "type": "; ".join(sorted({f.kind for _, f in mapped})),
                        "required_conditional": "; ".join(
                            sorted({"requerido" if f.required else "opcional" for _, f in mapped})
                        ),
                        "default": "; ".join(sorted({repr(f.default) for _, f in mapped})),
                        "permission": "; ".join(sorted({s.permission for s in specs})),
                        "effect": "; ".join(sorted({s.effect for s in specs})),
                        "confirmation": "; ".join(sorted({s.confirmation for s in specs})),
                        "reference": "inventario/catalog.json; inventario/args.json; inventario/reference.json",
                        "decision": decision,
                        "test": "tests/test_commands.py",
                        "acceptance": "NOT_TESTED",
                    }
                )
    # Cada campo anidado multimedia tiene fila propia y límites explícitos.
    for field, value in args["MediaOptions"]["fields"].items():
        mapped = [(s, f) for s in registry.specs for f in s.fields if f.name == field]
        rows.append(
            {
                "family": "media_options",
                "original_action": "media",
                "original_field": field,
                "original_schema": json.dumps(value, ensure_ascii=False),
                "command": "; ".join(sorted({s.command for s, _ in mapped})),
                "new_field": field,
                "type": "; ".join(sorted({f.kind for _, f in mapped})),
                "required_conditional": "Según ruta; idioma solo srt; hasta > desde",
                "default": "; ".join(sorted({repr(f.default) for _, f in mapped})),
                "permission": "friend",
                "effect": "artifact",
                "confirmation": "none",
                "reference": "src/zhana/media_edit.py / MediaOptions; SHA en inventario/reference.json",
                "decision": "Container también puede ser constante de ruta /dl FORMATO.",
                "test": "tests/test_commands.py",
                "acceptance": "NOT_TESTED",
            }
        )
    for spec in registry.specs:
        if not spec.family.startswith("audiovisual."):
            continue
        for field in spec.fields:
            rows.append(
                {
                    "family": spec.family,
                    "original_action": spec.original_action,
                    "original_field": field.original or field.name,
                    "original_schema": "Contrato técnico R0 audiovisual; adaptado a chat con IDs propios.",
                    "command": spec.command,
                    "new_field": field.name,
                    "type": field.kind,
                    "required_conditional": "requerido"
                    if field.required
                    else "opcional/condicional",
                    "default": repr(field.default),
                    "permission": spec.permission,
                    "effect": spec.effect,
                    "confirmation": spec.confirmation,
                    "reference": "inventario/audiovisual.md; SHA en inventario/reference.json",
                    "decision": "Argumento público tipado. clip_id/audio_id son IDs Botsky, resueltos al proveedor por backend.",
                    "test": "tests/test_commands.py",
                    "acceptance": "NOT_TESTED",
                }
            )
    for family, fields in {
        "agenda": (
            "key",
            "targetJid",
            "origin.chatId",
            "origin.requesterId",
            "sourceReceipt",
            "revision",
            "timeZone",
            "live",
            "durationFromAnswer",
        ),
        "session": ("callId", "nativeId", "sessionId", "epoch", "signal", "key", "scope"),
        "presentation": (
            "firstFrame",
            "frameAck",
            "audioPlayback",
            "audience",
            "journal",
            "notices",
        ),
    }.items():
        for field in fields:
            rows.append(
                {
                    "family": "audiovisual." + family,
                    "original_action": "backend",
                    "original_field": field,
                    "original_schema": "Ver contrato R0; no argumento de chat.",
                    "command": "backend de llamada autorizada",
                    "new_field": "resuelto internamente",
                    "type": "backend",
                    "required_conditional": "revalidar en cada efecto y resultado tardío",
                    "default": "durationFromAnswer=true; zona America/Mexico_City; sin destino libre",
                    "permission": "call_authorized/owner",
                    "effect": "session",
                    "confirmation": "según sesión",
                    "reference": "inventario/audiovisual.md",
                    "decision": "No exponer autoridad, destino nativo ni recibos como texto del usuario.",
                    "test": "R9 tests focales pendientes",
                    "acceptance": "NOT_TESTED",
                }
            )
    out = ROOT / "docs"
    (out / "commands.json").write_text(
        json.dumps(
            {"parser_version": 1, "aliases": registry.aliases, "commands": commands},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    with (out / "command-matrix.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Comandos v1 · generado desde el registro",
        "",
        "Sintaxis disponible no acredita handler ni aceptación de dominio. Los bloques se consultan en el relevo.",
        "Alias: " + ", ".join("/" + a + " → /" + b for a, b in registry.aliases.items()),
        "",
        "Opciones antes del texto final. Desde su primer carácter se conserva el resto literalmente; -- fuerza texto literal.",
        "Comillas agrupan campos múltiples; dentro de comillas solo se escapan la comilla activa y la barra.",
        "No se interpreta shell. Mayúsculas de datos/IDs/URLs se conservan; nombres de comando/enum sin tildes no distinguen mayúsculas.",
        "IDs son los de resultados reales. Fechas completas y horas 00:00–23:59; America/Mexico_City, validación de futuro en backend.",
        "",
        "Cada campo, tipo, rango, valor por defecto, permiso y decisión de portado: [commands.json](commands.json) y [command-matrix.csv](command-matrix.csv).",
        "",
    ]
    for root in sorted({s.path[0] for s in registry.specs}):
        lines += ["## /" + root, "", "```text", registry.help(root), "```", ""]
    (out / "commands.md").write_text("\n".join(lines))
    print(
        f"{len(commands)} rutas; {len(rows)} filas acción/campo; {len(model_files)} archivos de modelos"
    )
    return len(commands), len(rows)


if __name__ == "__main__":
    render()
