"""Esperas y vistas propias, vigentes y entregadas. Ningún sí/número suelto ejecuta."""

import json
from types import MappingProxyType
from uuid import uuid4

from .artifacts import ArtifactProblem
from .commands.router import ParsedCommand
from .contracts import Result, canonical
from .domains.notes import SCOPE_SQL

TTL_MS = 900000


def wait_file(db, context, spec, command, now):
    identifier = uuid4().hex
    db.execute(
        "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending_delivery',?)",
        (
            identifier,
            context.receipt_id,
            *context.scope_key,
            "file",
            canonical(command),
            canonical(spec.path),
            now + TTL_MS,
        ),
    )
    return Result(
        "needs_input",
        "attachment_required",
        "Adjunta el archivo aquí o responde al mensaje exacto que lo contiene. Esta espera dura 15 minutos.\nEjemplo: "
        + spec.sample,
        {"interaction_id": identifier},
    )


def resume_file(db, context, incoming, registry, now):
    if not incoming.attachments:
        return None
    row = db.execute(
        f"SELECT * FROM interactions WHERE {SCOPE_SQL} AND kind='file' AND state='active' AND expires_ms>? ORDER BY rowid DESC LIMIT 1",
        (*context.scope_key, now),
    ).fetchone()
    if not row:
        return None
    command = json.loads(row["command_json"])
    spec = registry.paths.get(tuple(json.loads(row["path_json"])))
    if command["version"] != 1 or spec is None or spec.operation != command["operation"]:
        return None
    changed = db.execute(
        "UPDATE interactions SET state='consumed',revision=revision+1,data_json=? WHERE id=? AND revision=? AND state='active'",
        (canonical({"continuation_receipt": context.receipt_id}), row["id"], row["revision"]),
    ).rowcount
    if changed != 1:
        return None
    return ParsedCommand(spec, MappingProxyType(command["arguments"]), MappingProxyType({}))


def replace_file_waits(db, context):
    rows = db.execute(
        f"SELECT id,receipt_id FROM interactions WHERE {SCOPE_SQL} AND kind='file' AND state IN ('active','pending_delivery')",
        context.scope_key,
    ).fetchall()
    for row in rows:
        db.execute(
            "UPDATE interactions SET state='cancelled',revision=revision+1 WHERE id=?", (row["id"],)
        )
        db.execute(
            "UPDATE outbox SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state='pending'",
            (row["receipt_id"],),
        )
        result = Result(
            "cancelled",
            "file_wait_replaced",
            "La espera de archivo fue reemplazada por otra orden.",
        )
        db.execute(
            "UPDATE inbox SET state='cancelled',result_json=?,revision=revision+1 WHERE id=?",
            (result.to_json(), row["receipt_id"]),
        )
        db.execute(
            "UPDATE effects SET result_json=? WHERE receipt_id=?",
            (result.to_json(), row["receipt_id"]),
        )
    return "Reemplacé la espera anterior de archivo.\n" if rows else ""


def retry_snapshot(db, target):
    return [
        dict(row)
        for row in db.execute(
            "SELECT position,revision,state,artifacts_json FROM outbox WHERE receipt_id=? AND state IN ('failed','uncertain') ORDER BY position",
            (target,),
        )
    ]


def preview_retry(db, context, target, now, artifacts, *, confirm_uncertain=False):
    parent = db.execute(
        f"SELECT * FROM inbox WHERE id=? AND {SCOPE_SQL}", (target, *context.scope_key)
    ).fetchone()
    if not parent:
        return Result(
            "empty", "receipt_not_found", "No hay un encargo propio con ese ID en este chat."
        )
    rows = retry_snapshot(db, target)
    if not rows:
        return Result(
            "empty", "no_retryable_delivery", "No hay partes fallidas o inciertas que reintentar."
        )
    if confirm_uncertain:
        views = db.execute(
            f"SELECT id FROM interactions WHERE {SCOPE_SQL} AND kind='delivery_retry' AND state='active' AND expires_ms>? AND json_extract(data_json,'$.target')=?",
            (*context.scope_key, now, target),
        ).fetchall()
        if len(views) != 1:
            return Result(
                "needs_input",
                "retry_preview_required",
                "Primero solicita y recibe la vista previa con /pdf reintentar " + target,
            )
        return confirm(db, context, views[0]["id"], now)
    artifact_ids = (
        json.loads(parent["result_json"])["data"].get("artifacts", [])
        if parent["result_json"]
        else []
    )
    if not artifact_ids:
        return Result(
            "failed",
            "pdf_result_unavailable",
            "No hay un PDF retenido para volver a entregar; no repetí el motor.",
        )
    try:
        metadata = [artifacts.owned(db, identifier, context, now) for identifier in artifact_ids]
    except ArtifactProblem as exc:
        return Result(
            "failed", exc.code, "El PDF ya no está disponible; adjunta los archivos de nuevo."
        )
    if any(row["format"] != "pdf" for row in metadata):
        return Result("failed", "pdf_result_unavailable", "Ese resultado no es un PDF.")
    identifier = uuid4().hex
    db.execute(
        f"UPDATE interactions SET state='cancelled',revision=revision+1 WHERE {SCOPE_SQL} AND kind='delivery_retry' AND state IN ('active','pending_delivery') AND json_extract(data_json,'$.target')=?",
        (*context.scope_key, target),
    )
    data = {
        "target": target,
        "parts": rows,
        "artifact_ids": artifact_ids,
        "sha256": {row["id"]: row["sha256"] for row in metadata},
    }
    db.execute(
        "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,'{}','[]',?,'pending_delivery',?)",
        (
            identifier,
            context.receipt_id,
            *context.scope_key,
            "delivery_retry",
            canonical(data),
            now + TTL_MS,
        ),
    )
    return Result(
        "needs_input",
        "delivery_retry_preview",
        f"Voy a reenviar {len(rows)} partes fallidas o inciertas del PDF {target}. Un reenvío de una parte incierta podría duplicarla. No repetiré el motor.\n/confirmar {identifier}",
        {"confirmation_id": identifier, "target": target},
    )


def _confirm_delivery(db, context, identifier, now):
    view = db.execute(
        f"SELECT * FROM interactions WHERE id=? AND {SCOPE_SQL} AND kind='delivery_retry' AND state='active' AND expires_ms>?",
        (identifier, *context.scope_key, now),
    ).fetchone()
    if not view:
        return Result(
            "needs_input",
            "confirmation_unavailable",
            "La confirmación no es propia, entregada y vigente.",
        )
    data = json.loads(view["data_json"])
    parent = db.execute(
        f"SELECT * FROM inbox WHERE id=? AND {SCOPE_SQL}", (data["target"], *context.scope_key)
    ).fetchone()
    if not parent or retry_snapshot(db, data["target"]) != data["parts"]:
        return Result(
            "needs_input",
            "confirmation_stale",
            "El estado de entrega cambió. Solicita otra vista previa.",
        )
    for artifact_id, sha256 in data["sha256"].items():
        row = db.execute(
            f"SELECT * FROM artifacts WHERE id=? AND {SCOPE_SQL} AND state='active' AND expires_ms>?",
            (artifact_id, *context.scope_key, now),
        ).fetchone()
        if not row or row["sha256"] != sha256:
            return Result(
                "needs_input",
                "confirmation_stale",
                "El archivo ya no coincide con la vista previa.",
            )
    db.execute(
        "UPDATE interactions SET state='consumed',revision=revision+1 WHERE id=? AND revision=? AND state='active'",
        (identifier, view["revision"]),
    )
    for part in data["parts"]:
        db.execute(
            "INSERT OR IGNORE INTO delivery_attempts VALUES(?,?,?,?,NULL,?,?)",
            (
                data["target"],
                part["position"],
                part["revision"],
                part["state"],
                "preserved_before_explicit_retry",
                now,
            ),
        )
        db.execute(
            "UPDATE outbox SET state='pending',revision=revision+1,error_code=NULL,updated_ms=? WHERE receipt_id=? AND position=? AND revision=? AND state=?",
            (now, data["target"], part["position"], part["revision"], part["state"]),
        )
    return Result(
        "ok",
        "delivery_retry_authorized",
        "Reintento de entrega autorizado. Se conservan las partes ya aceptadas y el resultado del motor.",
        {"target": data["target"]},
    )


def confirm(db, context, identifier, now):
    view = db.execute(
        f"SELECT * FROM interactions WHERE id=? AND {SCOPE_SQL} AND state='active' AND expires_ms>?",
        (identifier, *context.scope_key, now),
    ).fetchone()
    if not view:
        return Result(
            "needs_input",
            "confirmation_unavailable",
            "La confirmación no es propia, entregada y vigente.",
        )
    if view["kind"] == "delivery_retry":
        return _confirm_delivery(db, context, identifier, now)
    if view["kind"] == "memory_forget_all":
        from .domains.organization import confirm_memory

        return confirm_memory(db, context, view, now)
    return Result(
        "failed", "unsupported_confirmation", "Esta confirmación no tiene una acción admitida."
    )


def choose_view(db, context, kind, now, identifier=None):
    """Una forma corta solo es válida con una vista inequívoca ya entregada."""
    rows = db.execute(
        f"SELECT * FROM interactions WHERE {SCOPE_SQL} AND kind=? AND state='active' AND expires_ms>? "
        + ('AND id=?' if identifier else '') + ' ORDER BY rowid DESC LIMIT 2',
        (*context.scope_key, kind, now, *((identifier,) if identifier else ())),
    ).fetchall()
    if len(rows) == 1:
        return rows[0], None
    if len(rows) > 1:
        command = '/dl elegir' if kind == 'download' else '/drive elegir'
        return None, Result('needs_input', 'selection_ambiguous',
            'Hay varias listas vigentes. Usa la referencia de la lista que quieres:\n' +
            '\n'.join(command + ' ' + row['id'] + ' NUMERO' for row in rows))
    return None, None
