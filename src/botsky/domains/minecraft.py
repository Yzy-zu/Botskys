"""Minecraft solo por cliente cerrado; consola no es shell del host."""

import json

from ..contracts import Result, canonical

READS = {"status", "players", "worlds", "mods", "config"}


def execute(db, context, spec, args, now, app):
    backend = app.minecraft
    if backend is None:
        return Result(
            "failed",
            "minecraft_not_configured",
            "El servidor Minecraft no está configurado para Botsky.",
        )
    action = spec.original_action
    if action not in READS:
        from ..adapters.minecraft import MinecraftLocalValidationError

        params = {k: v for k, v in args.items() if v is not None}
        try:
            params = backend.validate_change(action, params)
        except ValueError, MinecraftLocalValidationError:
            return Result(
                "needs_input",
                "minecraft_local_validation",
                "El cambio no es admisible. Consola: list, save, time query daytime o weather query; no comandos del host.",
            )
        if db.execute(
            "SELECT 1 FROM external_operations WHERE domain='minecraft' AND resource=? AND state IN ('reserved','sending','uncertain')",
            (backend.server_id,),
        ).fetchone():
            return Result(
                "needs_input",
                "minecraft_resource_busy",
                "Hay un cambio pendiente o incierto en el servidor. Consulta estado y pide revisión antes de otro cambio.",
            )
    else:
        params = {}
    result = app.jobs.reserve(
        db,
        context,
        spec.operation,
        {"server_id": backend.server_id, "params": params},
        [],
        now,
        resource="minecraft-" + backend.server_id,
    )
    if result.code == "job_queued" and action not in READS:
        db.execute(
            "INSERT INTO external_operations(receipt_id,domain,resource,action,args_json) VALUES(?,?,?,?,?)",
            (context.receipt_id, "minecraft", backend.server_id, action, canonical(params)),
        )
    return result


def retire_job(db, receipt_id, now):
    db.execute(
        "UPDATE external_operations SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END WHERE receipt_id=? AND state IN ('reserved','sending')",
        (receipt_id,),
    )


def public(value, depth=0):
    if depth > 4:
        return "[recortado]"
    if isinstance(value, dict):
        return {
            k: public(v, depth + 1)
            for k, v in list(value.items())[:100]
            if isinstance(k, str)
            and not any(
                word in k.casefold()
                for word in (
                    "token",
                    "password",
                    "secret",
                    "key",
                    "credential",
                    "authorization",
                    "path",
                    "host",
                )
            )
        }
    if isinstance(value, list):
        return [public(v, depth + 1) for v in value[:100]]
    if isinstance(value, str):
        return value[:500]
    if value is None or type(value) in (int, float, bool):
        return value
    return "[omitido]"


def render(data, action):
    if action == "console":
        return "Comando enviado al puente Minecraft; no hay confirmación de ejecución dentro del juego."
    if action == "players":
        if data.get("online") is not True or data.get("players_known") is not True:
            return "No hay una lista actual verificada de jugadores."
        return "Jugadores: " + ", ".join(str(v)[:80] for v in data.get("players", [])[:100])
    if action == "mods":
        return (
            "Paquetes instalados/configurados (no confirma carga dentro del juego):\n"
            + json.dumps(data, ensure_ascii=False)[:5000]
        )
    if action == "status":
        return (
            "Minecraft: "
            + (
                "en línea"
                if data.get("online") is True
                else "apagado"
                if data.get("online") is False
                else "estado desconocido"
            )
            + "."
        )
    return "Minecraft " + action + ":\n" + json.dumps(data, ensure_ascii=False)[:5000]


async def run(job, directory, manager):
    from ..jobs import EngineOutput

    backend = manager.minecraft()
    action = job["operation"].split(".")[-1]
    mutating = action not in READS
    dispatched = False
    state = "failed"
    try:
        if backend is None or backend.server_id != job["arguments"]["server_id"]:
            raise ValueError("minecraft_configuration_changed")
        if mutating:
            clean = backend.validate_change(action, job["arguments"]["params"])
            manager.mark_provider(job)
            with manager.store.transaction() as db:
                if not manager.current(job):
                    raise ValueError("job_retired")
                changed = db.execute(
                    "UPDATE external_operations SET state='sending' WHERE receipt_id=? AND state='reserved'",
                    (job["id"],),
                ).rowcount
                if changed != 1:
                    raise ValueError("operation_retired")
            dispatched = True
            data = await backend.change_validated(action, clean)
        else:
            data = await backend.query(action)
        if not isinstance(data, dict) or not isinstance(data.get("status"), str):
            raise ValueError("minecraft_invalid_response")
        status = data["status"]
        state = (
            "completed"
            if status in ("ok", "completed", "accepted", "online", "offline", "unknown")
            else "failed"
            if data.get("dispatched") is False
            else "uncertain"
            if mutating
            else "failed"
        )
        safe = public(data)
        result = Result(
            "ok" if state == "completed" else "uncertain" if state == "uncertain" else "failed",
            "minecraft_" + state,
            render(safe, action)
            if state == "completed"
            else "Minecraft: resultado " + state + ". No se repetirá automáticamente.",
            {"action": action, "response": safe},
        )
    except BaseException as exc:
        state = "uncertain" if mutating and dispatched else "failed"
        result = Result(
            "uncertain" if state == "uncertain" else "failed",
            "minecraft_" + state,
            "No pude confirmar la operación Minecraft. No la repetiré automáticamente.",
        )
        if not isinstance(exc, Exception):
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
                    (state, result.to_json(), job["id"]),
                )
            raise
    if mutating:
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
                (state, result.to_json(), job["id"]),
            )
    return EngineOutput(result)
