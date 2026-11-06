"""Sesiones PDF propias y persistentes. El motor solo recibe fuentes verificadas."""

import json
from uuid import uuid4

from .. import interactions
from ..artifacts import ArtifactProblem
from ..contracts import Result, canonical
from ..jobs import cancel_job
from .notes import SCOPE_SQL

FORMATS = {"pdf", "png", "jpg", "webp", "tiff"}


def execute(db, context, spec, command, now, artifacts, jobs):
    action = spec.original_action
    args = command["arguments"]
    session = db.execute(
        f"SELECT * FROM pdf_sessions WHERE {SCOPE_SQL} AND state IN ('open','processing')",
        context.scope_key,
    ).fetchone()
    incoming = db.execute("SELECT * FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
    if action == "retry":
        return interactions.preview_retry(
            db,
            context,
            args["id"],
            now,
            artifacts,
            confirm_uncertain=args.get("confirm_uncertain", False),
        )
    if action == "cancel":
        if not session:
            return Result(
                "empty", "pdf_session_missing", "No tienes una sesión PDF abierta en este chat."
            )
        for row in db.execute(
            "SELECT id FROM jobs WHERE resource_key=? AND state IN ('queued','running')",
            (session["id"],),
        ).fetchall():
            cancel_job(db, context, row["id"])
        db.execute(
            "UPDATE pdf_sessions SET state='cancelled',revision=revision+1,updated_ms=? WHERE id=?",
            (now, session["id"]),
        )
        db.execute("DELETE FROM artifact_leases WHERE holder=?", ("pdf-" + session["id"],))
        return Result("cancelled", "pdf_session_cancelled", "Sesión PDF cancelada.")
    if action == "finish":
        if not session:
            return Result(
                "needs_input",
                "pdf_session_missing",
                "Primero usa /pdf iniciar y /pdf agregar con archivos propios.",
            )
        if session["state"] != "open":
            return Result(
                "needs_input",
                "pdf_session_busy",
                "La sesión ya está procesándose. Usa /estado ID o cancela el encargo exacto.",
            )
        inputs = json.loads(session["inputs_json"])
        if not inputs:
            return Result(
                "needs_input",
                "pdf_session_empty",
                "La sesión está vacía. Usa /pdf agregar con un archivo.",
            )
        try:
            result = jobs.reserve(
                db,
                context,
                spec.operation,
                {"session_id": session["id"], "session_revision": session["revision"] + 1},
                inputs,
                now,
                resource=session["id"],
                source_holder="pdf-" + session["id"],
            )
        except ArtifactProblem as exc:
            return Result(
                "failed",
                exc.code,
                "Una fuente PDF venció. Adjunta de nuevo los archivos necesarios.",
            )
        if result.code == "job_queued":
            db.execute(
                "UPDATE pdf_sessions SET state='processing',revision=revision+1,updated_ms=? WHERE id=? AND revision=?",
                (now, session["id"], session["revision"]),
            )
        return result
    try:
        inputs = artifacts.resolve(db, context, incoming, now)
        if action == "extract":
            if not inputs:
                return interactions.wait_file(db, context, spec, command, now)
            if len(inputs) != 1:
                return Result(
                    "needs_input",
                    "one_attachment_required",
                    "La extracción requiere exactamente un PDF.",
                )
            row = artifacts.owned(db, inputs[0], context, now)
            if row["format"] != "pdf":
                return Result("failed", "pdf_required", "Adjunta un PDF para extraer páginas.")
            return jobs.reserve(db, context, spec.operation, args, inputs, now)
        if action == "start":
            if session:
                return Result(
                    "needs_input",
                    "pdf_session_exists",
                    "Ya tienes una sesión abierta. Usa /pdf agregar, /pdf terminar o /pdf cancelar.",
                )
            identifier = uuid4().hex
            session = {"id": identifier, "inputs_json": "[]", "revision": 0, "state": "open"}
        if not session:
            return Result("needs_input", "pdf_session_missing", "Primero usa /pdf iniciar.")
        if session["state"] != "open":
            return Result("needs_input", "pdf_session_busy", "La sesión ya está procesándose.")
        if not inputs and action == "add":
            return interactions.wait_file(db, context, spec, command, now)
        prior = json.loads(session["inputs_json"])
        if any(value in prior for value in inputs):
            return Result(
                "needs_input",
                "pdf_duplicate_source",
                "Ese archivo ya está en la sesión; no lo agregué otra vez.",
            )
        combined = prior + inputs
        if len(combined) > 20:
            return Result("failed", "pdf_source_count", "La sesión admite hasta 20 archivos.")
        total = 0
        for identifier in combined:
            row = artifacts.owned(db, identifier, context, now, holder="pdf-" + session["id"])
            if row["format"] not in FORMATS:
                return Result(
                    "failed",
                    "pdf_source_format",
                    "La sesión admite PDF e imágenes PNG/JPG/WebP/TIFF.",
                )
            if row["size"] > 100000000:
                return Result(
                    "failed", "input_size", "Cada fuente PDF admite hasta 100 MB decimales."
                )
            total += row["size"]
        if total > 2000000000:
            return Result("failed", "input_size", "La sesión supera 2 GB decimales.")
        artifacts.lease(
            db,
            combined,
            context,
            "pdf-" + session["id"],
            str(session["revision"] + 1),
            now + 86400000,
            now,
        )
        if action == "start":
            db.execute(
                "INSERT INTO pdf_sessions(id,instance,account,actor,chat,is_group,epoch,inputs_json,state,revision,created_ms,updated_ms) VALUES(?,?,?,?,?,?,?,?,'open',1,?,?)",
                (session["id"], *context.scope_key, canonical(combined), now, now),
            )
        else:
            db.execute(
                "UPDATE pdf_sessions SET inputs_json=?,revision=revision+1,updated_ms=? WHERE id=? AND revision=?",
                (canonical(combined), now, session["id"], session["revision"]),
            )
        return Result(
            "ok",
            "pdf_session_started" if action == "start" else "pdf_sources_added",
            f"Sesión PDF: {len(combined)} archivos.\n/pdf agregar\n/pdf terminar\n/pdf cancelar",
            {"session_id": session["id"], "sources": len(combined)},
        )
    except ArtifactProblem as exc:
        return Result(
            "failed", exc.code, "El archivo no está disponible o no tienes acceso en este ámbito."
        )
