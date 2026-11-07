"""Drive bajo recibos y vistas propios; jamás IDs o rutas inventados por texto."""

import hashlib
import json
from dataclasses import asdict
from uuid import uuid4

from .. import interactions
from ..artifacts import ArtifactProblem
from ..contracts import Result, canonical


def scope_hash(context, folder):
    return hashlib.sha256(canonical([*context.scope_key, folder]).encode()).hexdigest()


def execute(db, context, spec, command, now, app):
    backend = app.drive
    if backend is None or not backend.available:
        return Result("failed", "drive_not_configured", "Drive no está configurado para Botsky.")
    args = dict(command["arguments"])
    args["folder_id"] = backend.folder_id
    args["scope_hash"] = scope_hash(context, backend.folder_id)
    inputs = []
    if spec.original_action == "save":
        row = db.execute("SELECT * FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
        try:
            inputs = app.artifacts.resolve(db, context, row, now)
            if not inputs:
                return interactions.wait_file(db, context, spec, command, now)
            if len(inputs) != 1:
                return Result(
                    "needs_input",
                    "one_attachment_required",
                    "Adjunta exactamente un archivo propio.",
                )
            metadata = app.artifacts.owned(db, inputs[0], context, now)
            if metadata["size"] > 2_000_000_000:
                return Result("failed", "drive_upload_too_large", "El archivo supera 2 GB.")
            args.update(format=metadata["format"], sha256=metadata["sha256"])
        except ArtifactProblem as exc:
            return Result("failed", exc.code, "El archivo propio no está disponible.")
    if spec.original_action == "choose":
        view, ambiguity = interactions.choose_view(db, context, "drive", now, args.get("view_id"))
        if ambiguity:
            return ambiguity
        if not view:
            return Result(
                "needs_input",
                "drive_view_unavailable",
                "La vista debe ser propia, entregada y vigente. Busca de nuevo.",
            )
        data = json.loads(view["data_json"])
        if data["folder_id"] != backend.folder_id or data["scope_hash"] != args["scope_hash"]:
            return Result(
                "failed",
                "drive_configuration_changed",
                "Cambió la carpeta o el ámbito; busca de nuevo.",
            )
        if args["choice"] > len(data["choices"]):
            return Result(
                "needs_input", "drive_choice_out_of_range", "Esa opción no pertenece a la vista."
            )
        args["selected"] = data["choices"][args["choice"] - 1]
    return app.jobs.reserve(
        db, context, spec.operation, args, inputs, now, resource="drive-" + args["scope_hash"]
    )


def finish_choices(db, context, parent, result, now):
    identifier = uuid4().hex
    data = dict(result.data)
    db.execute(
        "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,'{}','[]',?,'pending_delivery',?)",
        (
            identifier,
            context.receipt_id,
            *context.scope_key,
            "drive",
            canonical(data),
            now + 300000,
        ),
    )
    lines = ["Archivos de tu ámbito:"]
    for i, item in enumerate(data["choices"], 1):
        lines.extend([f"{i}. {item['name']}", f"/drive elegir {identifier} {i}"])
    return Result(
        "needs_input",
        "drive_choices",
        "\n".join(lines),
        {"view_id": identifier, "choices": data["choices"]},
    )


async def run(job, directory, paths, manager, backend):
    from ..adapters.drive import DriveError
    from ..engines.process import MediaError
    from ..jobs import EngineOutput

    args = job["arguments"]
    if backend is None or not backend.available or backend.folder_id != args["folder_id"]:
        raise MediaError("drive_configuration_changed")
    scope = args["scope_hash"]
    try:
        if job["operation"] == "manage_drive.capacity":
            quota = await backend.storage_quota()
            return EngineOutput(
                Result(
                    "ok",
                    "drive_capacity",
                    "Espacio de la cuenta Google (bytes):\n"
                    + "\n".join(f"{k}: {v}" for k, v in quota.items()),
                    {"quota": quota},
                )
            )
        if job["operation"] == "manage_drive.search":
            choices = await backend.search(args.get("query"), scope_key=scope)
            if not choices:
                return EngineOutput(
                    Result("empty", "drive_empty", "No hay archivos que coincidan en tu ámbito.")
                )
            return EngineOutput(
                Result(
                    "needs_input",
                    "drive_choices",
                    data={
                        "choices": [asdict(c) for c in choices],
                        "folder_id": backend.folder_id,
                        "scope_hash": scope,
                    },
                )
            )
        if job["operation"] == "manage_drive.choose":
            selected = args["selected"]
            metadata = await backend.metadata(selected["id"], scope_key=scope)
            if asdict(metadata) != selected:
                raise MediaError("drive_selection_changed")
            content = await backend.download(metadata.id, scope_key=scope)
            output = directory / "download.bin"
            output.write_bytes(content)
            return EngineOutput(
                Result(
                    "ok",
                    "drive_downloaded",
                    "Archivo recuperado de Drive.",
                    {"remote_id": metadata.id, "name": metadata.name},
                ),
                (output,),
            )
        with manager.store.transaction() as db:
            prior = db.execute(
                "SELECT * FROM drive_uploads WHERE receipt_id=?", (job["id"],)
            ).fetchone()
        if prior:
            remote_id = prior["remote_id"]
        else:
            remote_id = await backend.generate_id()
            if not manager.current(job):
                raise MediaError("job_retired")
            with manager.store.transaction() as db:
                db.execute(
                    "INSERT INTO drive_uploads VALUES(?,?,?,?,?,?,?)",
                    (
                        job["id"],
                        remote_id,
                        backend.folder_id,
                        scope,
                        args["sha256"],
                        "reserved",
                        manager.clock(),
                    ),
                )
        await backend.folder()
        manager.mark_provider(job)
        result = await backend.upload_file(
            remote_id,
            "archivo-" + job["inputs"][0] + "." + args["format"],
            "application/octet-stream",
            paths[0],
            scope_key=scope,
        )
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE drive_uploads SET state='uploaded',updated_ms=? WHERE receipt_id=?",
                (manager.clock(), job["id"]),
            )
        return EngineOutput(
            Result(
                "ok",
                "drive_saved",
                "Archivo guardado en tu ámbito de Drive.\n" + result.web_view_link,
                {"remote_id": result.id, "name": result.name},
            )
        )
    except DriveError as exc:
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE drive_uploads SET state=?,updated_ms=? WHERE receipt_id=?",
                ("uncertain" if exc.uncertain else "failed", manager.clock(), job["id"]),
            )
        if exc.code == "oauth_refresh_rejected":
            message = (
                "No pude renovar la autorización de Drive. Es necesario volver a conectar "
                "la cuenta de Google para usar Drive. No repetí la operación."
            )
        elif exc.uncertain:
            message = "Drive no confirmó la subida. Su estado es incierto; no la repetí."
        else:
            message = "No pude completar la operación de Drive. No la repetí."
        return EngineOutput(
            Result(
                "uncertain" if exc.uncertain else "failed",
                exc.code,
                message,
            )
        )
