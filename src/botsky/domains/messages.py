"""Recados explícitos del dueño en privado; preparación y envío son pasos distintos."""

import asyncio
import json
from uuid import uuid4

from .. import access
from ..artifacts import ArtifactProblem
from ..contracts import Result, canonical
from .ai import literal_source
from .notes import SCOPE_SQL

TTL = 300000


def state_result(db, draft):
    parts = [
        dict(r)
        for r in db.execute(
            "SELECT position,contact_name,kind,state,error_code FROM message_parts WHERE draft_id=? ORDER BY position",
            (draft["id"],),
        )
    ]
    lines = [f"Recado {draft['id']}: {draft['state']}."]
    lines.extend(f"{p['contact_name']} · {p['kind']}: {p['state']}" for p in parts)
    return Result(
        "uncertain" if any(p["state"] == "uncertain" for p in parts) else "ok",
        "message_status",
        "\n".join(lines),
        {"draft_id": draft["id"], "state": draft["state"], "parts": parts},
    )


def withdraw(db, identifier, now, state="cancelled"):
    db.execute(
        "UPDATE message_parts SET state='uncertain',error_code='interrupted',revision=revision+1,updated_ms=? WHERE draft_id=? AND state='sending'",
        (now, identifier),
    )
    db.execute(
        "UPDATE message_parts SET state='cancelled',revision=revision+1,updated_ms=? WHERE draft_id=? AND state='pending'",
        (now, identifier),
    )
    db.execute(
        "UPDATE message_drafts SET state=?,revision=revision+1 WHERE id=? AND state IN ('draft','sending')",
        (state, identifier),
    )
    db.execute("DELETE FROM artifact_leases WHERE holder=?", ("message-" + identifier,))


def retire_job(db, receipt_id, now):
    for draft in db.execute(
        "SELECT id FROM message_drafts WHERE send_receipt_id=?", (receipt_id,)
    ).fetchall():
        withdraw(db, draft["id"], now, "partial")


def execute(db, context, spec, command, now, app):
    if context.scope.is_group:
        return Result(
            "failed",
            "message_private_required",
            "Prepara y confirma recados en el privado del dueño.",
        )
    directory = app.directory
    args = command["arguments"]
    action = spec.original_action
    if action == "contacts":
        names = [c.name for c in directory.contacts]
        return Result(
            "ok" if names else "empty",
            "message_contacts",
            "Contactos configurados:\n" + "\n".join(names)
            if names
            else "No hay contactos configurados.",
            {"names": names},
        )
    if action == "prepare":
        try:
            selected = directory.resolve(tuple(args["recipients"]))
        except ValueError:
            return Result(
                "needs_input",
                "message_recipient_unknown",
                "Uno o más destinatarios no son contactos configurados. No seleccioné una lista parcial.",
            )
        row = db.execute("SELECT * FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
        content = args.get("text") or ""
        sources = []
        if args["source"] == "cita":
            if content:
                return Result(
                    "needs_input",
                    "message_source_conflict",
                    "Con --fuente cita usa el texto de la cita, sin otro texto final.",
                )
            content = literal_source(db, context, row, "quote", now) or ""
            if not row["quoted_message_id"] or not content and not args["attach"]:
                return Result(
                    "needs_input",
                    "message_quote_unavailable",
                    "Responde a una fuente propia y disponible de este privado.",
                )
            sources.append(row["quoted_message_id"])
        if len(content) > 4000:
            return Result(
                "failed", "message_text_too_long", "El texto del recado supera 4000 caracteres."
            )
        artifact = None
        if args["attach"]:
            try:
                inputs = app.artifacts.resolve(db, context, row, now)
                if len(inputs) != 1:
                    return Result(
                        "needs_input",
                        "message_one_attachment",
                        "Adjunta o cita exactamente un archivo propio para el recado.",
                    )
                artifact = app.artifacts.owned(db, inputs[0], context, now)
                if artifact["size"] > 10 * 1024 * 1024:
                    return Result("failed", "message_asset_too_large", "El adjunto supera 10 MiB.")
            except ArtifactProblem as exc:
                return Result(
                    "failed", exc.code, "El adjunto no es propio y disponible en este privado."
                )
        if not content and not artifact:
            return Result(
                "needs_input",
                "message_content_required",
                "Escribe el texto literal o adjunta un archivo con --adjunto.",
            )
        for old in db.execute(
            f"SELECT * FROM message_drafts WHERE {SCOPE_SQL} AND state='draft'", context.scope_key
        ).fetchall():
            withdraw(db, old["id"], now)
        identifier = uuid4().hex
        data = {"draft_id": identifier, "revision": 1}
        db.execute(
            "INSERT INTO message_drafts(id,instance,account,actor,chat,is_group,epoch,names_json,recipients_json,directory_hash,content,artifact_id,artifact_sha256,source_json,preview_receipt_id,state,created_ms,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)",
            (
                identifier,
                *context.scope_key,
                canonical([c.name for c in selected]),
                canonical([{"name": c.name, "target": c.target} for c in selected]),
                directory.fingerprint(tuple(c.name for c in selected)),
                content,
                artifact["id"] if artifact else None,
                artifact["sha256"] if artifact else None,
                canonical(sources),
                context.receipt_id,
                now,
                now + TTL,
            ),
        )
        if artifact:
            app.artifacts.lease(
                db, [artifact["id"]], context, "message-" + identifier, "preview", now + TTL, now
            )
        db.execute(
            "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,'{}','[]',?,'pending_delivery',?)",
            (
                identifier,
                context.receipt_id,
                *context.scope_key,
                "message_preview",
                canonical(data),
                now + TTL,
            ),
        )
        preview = "Recado para: " + ", ".join(c.name for c in selected) + "\n" + content
        if artifact:
            preview += f"\nAdjunto: {artifact['format']}, {artifact['size']} bytes."
        return Result(
            "needs_input",
            "message_preview",
            preview + f"\nCaduca en 5 minutos. Para enviarlo:\n/recado enviar {identifier}",
            {"draft_id": identifier, "artifact_id": artifact["id"] if artifact else None},
        )
    draft = db.execute(
        f"SELECT * FROM message_drafts WHERE id=? AND {SCOPE_SQL}",
        (args["draft_id"], *context.scope_key),
    ).fetchone()
    if not draft:
        return Result(
            "empty",
            "message_draft_not_found",
            "No hay un recado propio con ese ID en este privado.",
        )
    if action == "status":
        return state_result(db, draft)
    if action == "cancel":
        withdraw(db, draft["id"], now, "partial" if draft["state"] == "sending" else "cancelled")
        return state_result(
            db, db.execute("SELECT * FROM message_drafts WHERE id=?", (draft["id"],)).fetchone()
        )
    if draft["state"] != "draft":
        return state_result(db, draft)
    if draft["expires_ms"] <= now:
        withdraw(db, draft["id"], now, "expired")
        return Result("failed", "message_preview_expired", "El borrador caducó. Prepara otro.")
    view = db.execute(
        "SELECT * FROM interactions WHERE id=? AND kind='message_preview' AND state='active'",
        (draft["id"],),
    ).fetchone()
    delivery = db.execute(
        "SELECT count(*) AS n,sum(state!='accepted') AS pending,max(updated_ms) AS accepted_ms FROM outbox WHERE receipt_id=?",
        (draft["preview_receipt_id"],),
    ).fetchone()
    row = db.execute("SELECT * FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
    if (
        not view
        or not delivery["n"]
        or delivery["pending"]
        or row["source_ms"] <= delivery["accepted_ms"]
        or row["received_ms"] <= delivery["accepted_ms"]
    ):
        return Result(
            "needs_input",
            "message_preview_required",
            "Recibe la vista completa y después confirma su ID desde este privado.",
        )
    try:
        names = tuple(json.loads(draft["names_json"]))
        if directory.fingerprint(names) != draft["directory_hash"]:
            raise ValueError()
    except ValueError:
        return Result(
            "failed", "message_directory_changed", "Cambió el directorio; prepara otra vista."
        )
    if app.messenger is None or not app.messenger.available:
        return Result(
            "failed",
            "messenger_not_configured",
            "El transporte de recados no está configurado; no se reservó envío.",
        )
    inputs = [draft["artifact_id"]] if draft["artifact_id"] else []
    try:
        queued = app.jobs.reserve(
            db,
            context,
            spec.operation,
            {"draft_id": draft["id"], "directory_hash": draft["directory_hash"]},
            inputs,
            now,
            source_holder="message-" + draft["id"],
            resource="message-" + draft["id"],
        )
    except ArtifactProblem as exc:
        return Result("failed", exc.code, "El adjunto ya no coincide con la vista.")
    if queued.code != "job_queued":
        return queued
    position = 0
    for recipient in json.loads(draft["recipients_json"]):
        for kind in (["asset"] if inputs else []) + (["text"] if draft["content"] else []):
            db.execute(
                "INSERT INTO message_parts(draft_id,position,target,contact_name,kind,updated_ms) VALUES(?,?,?,?,?,?)",
                (draft["id"], position, recipient["target"], recipient["name"], kind, now),
            )
            position += 1
    db.execute(
        "UPDATE message_drafts SET state='sending',send_receipt_id=?,revision=revision+1 WHERE id=?",
        (context.receipt_id, draft["id"]),
    )
    db.execute(
        "UPDATE interactions SET state='consumed',revision=revision+1 WHERE id=?", (draft["id"],)
    )
    return queued


def permitted(manager, job, db, draft, directory):
    from .bot import current

    context = job["context"]
    if (
        not manager.current(job)
        or access.authorize("owner", context, manager.settings)
        or context.scope.is_group
    ):
        return False
    mode = current(db, context)
    if mode["mode"] == "apagado" or mode["paused_until_ms"] > manager.clock():
        return False
    try:
        return (
            directory.fingerprint(tuple(json.loads(draft["names_json"]))) == draft["directory_hash"]
        )
    except ValueError:
        return False


async def run(job, directory_path, paths, manager, backend, directory):
    from ..adapters.messenger import MessageError
    from ..jobs import EngineOutput

    identifier = job["arguments"]["draft_id"]
    try:
        while True:
            backend, directory = manager.messages()
            with manager.store.transaction() as db:
                draft = db.execute(
                    "SELECT * FROM message_drafts WHERE id=?", (identifier,)
                ).fetchone()
                if (
                    not draft
                    or draft["state"] != "sending"
                    or not permitted(manager, job, db, draft, directory)
                    or backend is None
                    or not backend.available
                ):
                    break
                part = db.execute(
                    "SELECT * FROM message_parts WHERE draft_id=? AND state!='accepted' ORDER BY position LIMIT 1",
                    (identifier,),
                ).fetchone()
                if not part or part["state"] != "pending":
                    break
                db.execute(
                    "UPDATE message_parts SET state='sending',revision=revision+1,updated_ms=? WHERE draft_id=? AND position=? AND state='pending'",
                    (manager.clock(), identifier, part["position"]),
                )
            state, code, provider_id = "uncertain", "message_uncertain", None
            try:
                manager.mark_provider(job)
                provider_id = await backend.send(
                    part["target"],
                    part["kind"],
                    text=draft["content"],
                    path=paths[0] if paths else None,
                )
                if not isinstance(provider_id, str) or not provider_id:
                    raise ValueError("ambiguous ACK")
                state, code = "accepted", None
            except MessageError as exc:
                state, code = ("uncertain" if exc.uncertain else "failed"), exc.code
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            with manager.store.transaction() as db:
                db.execute(
                    "INSERT OR IGNORE INTO message_attempts VALUES(?,?,?,?,?,?,?)",
                    (
                        identifier,
                        part["position"],
                        part["revision"] + 1,
                        state,
                        provider_id,
                        code,
                        manager.clock(),
                    ),
                )
                db.execute(
                    "UPDATE message_parts SET state=?,provider_message_id=?,error_code=?,revision=revision+1,updated_ms=? WHERE draft_id=? AND position=? AND state IN ('sending','uncertain')",
                    (state, provider_id, code, manager.clock(), identifier, part["position"]),
                )
            if state != "accepted":
                break
    finally:
        with manager.store.transaction() as db:
            withdraw(db, identifier, manager.clock(), "partial")
            rows = db.execute(
                "SELECT state FROM message_parts WHERE draft_id=?", (identifier,)
            ).fetchall()
            if rows and all(r["state"] == "accepted" for r in rows):
                db.execute("UPDATE message_drafts SET state='completed' WHERE id=?", (identifier,))
    with manager.store.transaction() as db:
        result = state_result(
            db, db.execute("SELECT * FROM message_drafts WHERE id=?", (identifier,)).fetchone()
        )
    return EngineOutput(result)
