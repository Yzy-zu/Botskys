"""Canal de contenido explícito, contexto propio y voz sin acceso al dispatcher."""

import hashlib
import json
import re
from types import MappingProxyType

from .. import interactions
from ..artifacts import ArtifactProblem
from ..commands.router import ParsedCommand
from ..contracts import Result, canonical
from ..domains.notes import SCOPE_SQL

HISTORY_MS = 1800000


def named(text):
    # Solo metadatos y delimitadores de sintaxis, sin diccionario de apodos ni modelos.
    text = re.sub(r"```.*?(?:```|$)", " ", text, flags=re.S)
    text = re.sub(
        r'`[^`]*(?:`|$)|"[^"]*(?:"|$)|“[^”]*(?:”|$)|«[^»]*(?:»|$)|‘[^’]*(?:’|$)|(?<!\w)\x27[^\x27]*(?:\x27|$)',
        " ",
        text,
    )
    text = re.sub(r"https?://\S+|\S+@\S+\.\S+", " ", text)
    visible = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return bool(re.search(r"(?<![\w@./])@?Botsky(?![\w@./])", "\n".join(visible), re.IGNORECASE))


def own_ai_quote(db, context, quote, now):
    if not quote:
        return False
    return bool(
        db.execute(
            "SELECT 1 FROM ai_history h JOIN outbox o ON h.receipt_id=o.receipt_id WHERE o.provider_message_id=? AND o.state='accepted' AND h.instance=? AND h.account=? AND h.actor=? AND h.chat=? AND h.is_group=? AND h.epoch=? AND h.accepted=1 AND h.expires_ms>?",
            (quote, *context.scope_key, now),
        ).fetchone()
    )


def invoked(db, context, incoming, settings, registry, now):
    if not (
        set(incoming.mentioned_ids) & settings.bot_ids
        or named(incoming.text)
        or own_ai_quote(db, context, incoming.quoted_message_id, now)
    ):
        return None
    spec = registry.paths[("ia",)]
    return ParsedCommand(
        spec,
        MappingProxyType({"text": incoming.text or "Botsky"}),
        MappingProxyType({"text": ((0, len(incoming.text)),)}),
    )


def history(db, context, now):
    rows = db.execute(
        f"SELECT user_text,assistant_text FROM ai_history WHERE {SCOPE_SQL} AND accepted=1 AND expires_ms>? ORDER BY created_ms DESC,rowid DESC LIMIT 6",
        (*context.scope_key, now),
    ).fetchall()
    result = []
    size = 0
    selected = []
    for row in rows:
        size += len(row["user_text"]) + len(row["assistant_text"])
        if size > 16000:
            break
        selected.append(row)
    for row in reversed(selected):
        result.extend(
            [
                {"role": "user", "text": row["user_text"]},
                {"role": "assistant", "text": row["assistant_text"]},
            ]
        )
    return result


def literal_source(db, context, row, source, now):
    if source == "quote":
        quote = row["quoted_message_id"]
        if not quote:
            return None
        incoming = db.execute(
            f"SELECT text FROM inbox WHERE message_id=? AND {SCOPE_SQL} AND received_ms>?",
            (quote, *context.scope_key, now - 86400000),
        ).fetchone()
        if incoming:
            return incoming["text"]
        own = db.execute(
            "SELECT o.payload FROM outbox o JOIN inbox i ON o.receipt_id=i.id WHERE o.provider_message_id=? AND o.state='accepted' AND i.instance=? AND i.account=? AND i.actor=? AND i.chat=? AND i.is_group=? AND i.epoch=? AND o.updated_ms>?",
            (quote, *context.scope_key, now - 86400000),
        ).fetchone()
        return own["payload"] if own else None
    prior = db.execute(
        "SELECT o.payload FROM outbox o JOIN inbox i ON o.receipt_id=i.id WHERE o.state='accepted' AND length(o.payload)>0 AND i.instance=? AND i.account=? AND i.actor=? AND i.chat=? AND i.is_group=? AND i.epoch=? AND o.updated_ms>? ORDER BY o.rowid DESC LIMIT 1",
        (*context.scope_key, now - 86400000),
    ).fetchone()
    return prior["payload"] if prior else None


def execute(db, context, spec, command, now, app):
    args = dict(command["arguments"])
    row = db.execute("SELECT * FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
    if spec.family == "make_voice" and spec.original_action == "catalog":
        from ..commands.registry import VOICES

        return Result(
            "ok",
            "voice_catalog",
            "Voces: " + ", ".join(VOICES) + ".\n/voz --voz mexicana TEXTO",
            {"voices": list(VOICES)},
        )
    if spec.family == "make_voice":
        if app.tts is None or getattr(app.tts, "enabled", True) is not True:
            return Result(
                "failed", "tts_not_configured", "La voz no está configurada en este laboratorio."
            )
        if args["mode"] == "compose":
            if app.gemini is None or getattr(app.gemini, "available", True) is not True:
                return Result(
                    "failed",
                    "gemini_not_configured",
                    "La composición necesita Gemini; la voz literal sigue siendo independiente.",
                )
        elif args["source"] != "provided":
            value = literal_source(db, context, row, args["source"], now)
            if not value:
                return Result(
                    "needs_input",
                    "voice_source_unavailable",
                    "No hay texto propio exacto y disponible para leer. Usa /voz TEXTO.",
                )
            args["text"] = value
        if len(args["text"]) > 8000:
            return Result(
                "needs_input",
                "voice_text_too_long",
                "La lectura literal admite hasta 8000 caracteres; indica un texto más corto.",
            )
        return app.jobs.reserve(db, context, spec.operation, args, [], now)
    if spec.family == "transcribe_media":
        if app.asr is None or getattr(app.asr, "available", True) is not True:
            return Result(
                "failed",
                "asr_not_configured",
                "La transcripción no está configurada en este laboratorio.",
            )
        if args["output_mode"] in ("resumen", "ambos") and app.gemini is None:
            return Result(
                "failed",
                "gemini_not_configured",
                "El resumen necesita Gemini. Puedes pedir /transcribir --salida texto.",
            )
    elif app.gemini is None or getattr(app.gemini, "available", True) is not True:
        return Result(
            "failed",
            "gemini_not_configured",
            "Gemini no está configurado; los comandos locales siguen disponibles.",
        )
    try:
        # Una cita textual a IA propia es continuidad, no un archivo supuesto.
        inputs = (
            []
            if own_ai_quote(db, context, row["quoted_message_id"], now)
            and not json.loads(row["attachments_json"])
            else app.artifacts.resolve(db, context, row, now)
        )
        if spec.family == "transcribe_media":
            if not inputs:
                return interactions.wait_file(db, context, spec, command, now)
            if len(inputs) != 1:
                return Result(
                    "needs_input",
                    "one_attachment_required",
                    "La transcripción requiere exactamente un audio o video.",
                )
        else:
            args["history"] = history(db, context, now)
            args["memories"] = [
                {
                    "kind": r["kind"],
                    "text": r["text"],
                    "provenance": "explicit_user_command",
                    "revision": r["revision"],
                }
                for r in db.execute(
                    "SELECT kind,text,revision FROM memories WHERE "
                    + SCOPE_SQL
                    + " ORDER BY updated_ms DESC,id DESC LIMIT 8",
                    context.scope_key,
                )
            ]
            if row["quoted_message_id"] and not inputs:
                quoted = literal_source(db, context, row, "quote", now)
                if not quoted:
                    return Result(
                        "needs_input",
                        "ai_quote_unavailable",
                        "La cita textual ya no está disponible en este ámbito. Copia el texto en /ia.",
                    )
                args["quoted_text"] = quoted
        resource = (
            hashlib.sha256(canonical(["ai", context.scope_key]).encode()).hexdigest()
            if spec.family == "conversation"
            else None
        )
        return app.jobs.reserve(db, context, spec.operation, args, inputs, now, resource=resource)
    except ArtifactProblem as exc:
        return Result(
            "failed",
            exc.code,
            "No puedo usar esa referencia de archivo; adjunta uno propio y disponible.",
        )
