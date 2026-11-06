"""Adaptación de contratos de llamadas a recibos propios; ningún destino libre."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from ..adapters.calls import CallRequest, CallsError
from ..contracts import Result

PREFIXES = ("control_call.", "audiovisual.")
TERMINAL = {"ended", "failed", "interrupted", "cancelled"}


def permitted(backend, settings, context):
    return (
        backend is not None
        and settings.calls is not None
        and settings.calls.allows(context)
        and (settings.transport != "local" or backend.is_fixture)
    )


def current_binding(db, context):
    return db.execute(
        "SELECT * FROM call_bindings WHERE instance=? AND account=? AND chat=? AND is_group=? AND epoch=? AND (is_group=1 OR actor=?) ORDER BY CASE WHEN state NOT IN ('ended','failed','interrupted','cancelled','scheduled') THEN 0 WHEN state='scheduled' THEN 1 ELSE 2 END,updated_ms DESC,receipt_id DESC LIMIT 1",
        (
            context.instance,
            context.account,
            context.scope.chat,
            int(context.scope.is_group),
            context.epoch,
            context.scope.actor,
        ),
    ).fetchone()


def execute(db, context, spec, args, now, app):
    if not permitted(app.calls, app.settings, context):
        return Result(
            "failed",
            "calls_not_configured",
            "La llamada no está habilitada para este ámbito y transporte.",
        )
    action = spec.original_action
    features = app.settings.calls.document["features"]
    if (spec.family == "control_call" and action == "start") or (
        spec.family == "audiovisual.agenda" and action == "create"
    ):
        if not features["outgoing"] or (not args.get("audio_id") and not features["live"]):
            return Result(
                "failed", "calls_disabled", "Las llamadas solicitadas están desactivadas."
            )
        if app.calls.policy_revision != app.settings.calls.revision:
            return Result(
                "failed",
                "calls_policy_changed",
                "La política audiovisual debe conciliarse antes de iniciar.",
            )
    if spec.family == "control_call" and action == "start":
        if db.execute(
            "SELECT 1 FROM call_bindings WHERE instance=? AND account=? AND state NOT IN ('ended','failed','interrupted','cancelled','scheduled')",
            (context.instance, context.account),
        ).fetchone():
            return Result(
                "needs_input",
                "call_busy",
                "Hay una llamada pendiente o incierta. Consulta /llamada estado o cancélala antes de otra.",
            )
    if (
        spec.family == "audiovisual.agenda"
        and not features["agenda"]
        and action in {"create", "update"}
    ):
        return Result("failed", "agenda_disabled", "La agenda de llamadas está desactivada.")
    if spec.family == "audiovisual.agenda" and args.get("audio_id"):
        # Assets belong to the independent calls store, are content addressed and are
        # selected operationally by the verified owner, never loaded from an old path.
        if args.get("live_request"):
            return Result(
                "needs_input", "incompatible_call_mode", "Elige audio preparado o tema Live."
            )
    if (
        spec.family == "audiovisual.agenda"
        and args.get("end_after_audio")
        and not args.get("audio_id")
    ):
        return Result("needs_input", "audio_required", "--terminar-audio requiere --audio.")
    result = app.jobs.reserve(
        db, context, spec.operation, args, [], now, resource="call-control-" + context.receipt_id
    )
    if result.code == "job_queued" and (
        (spec.family == "control_call" and action == "start")
        or (spec.family == "audiovisual.agenda" and action == "create")
    ):
        db.execute(
            "INSERT INTO call_bindings(receipt_id,instance,account,actor,chat,is_group,epoch,policy_revision,updated_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            (context.receipt_id, *context.scope_key, app.settings.calls.revision, now),
        )
        if spec.family == "audiovisual.agenda":
            db.execute(
                "UPDATE call_bindings SET state='scheduled' WHERE receipt_id=?",
                (context.receipt_id,),
            )
    return result


def retire_job(db, receipt_id, now):
    row = db.execute("SELECT * FROM call_bindings WHERE receipt_id=?", (receipt_id,)).fetchone()
    if row and row["state"] not in TERMINAL:
        db.execute(
            "INSERT INTO call_cancellations(receipt_id,updated_ms) VALUES(?,?) ON CONFLICT(receipt_id) DO UPDATE SET state='pending',updated_ms=excluded.updated_ms",
            (receipt_id, now),
        )
        db.execute(
            "UPDATE call_bindings SET state='cancelling',updated_ms=? WHERE receipt_id=?",
            (now, receipt_id),
        )


async def drain_cancellations(manager, backend):
    if backend is None:
        return
    with manager.store.transaction() as db:
        pending = db.execute(
            "SELECT c.receipt_id FROM call_cancellations c JOIN call_bindings b USING(receipt_id) WHERE c.state='pending' AND b.instance=? AND b.account=? LIMIT 100",
            (manager.settings.instance, manager.settings.account),
        ).fetchall()
    for row in pending:
        try:
            await backend.cancel_preparation(row["receipt_id"])
            observed = await backend.operation(row["receipt_id"])
            call = observed.get("call")
            if call:
                with manager.store.transaction() as db:
                    binding = db.execute(
                        "SELECT * FROM call_bindings WHERE receipt_id=?", (row["receipt_id"],)
                    ).fetchone()
                validate_owned_call(call, binding)
            settled = (call is None and observed.get("cancelled") is True) or (
                call is not None
                and call.get("state") in TERMINAL
                and call.get("cleanup", {}).get("state") in {"released", "browser_closed"}
            )
        except CallsError:
            continue
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE call_cancellations SET state='confirmed',updated_ms=? WHERE receipt_id=?",
                (manager.clock(), row["receipt_id"]),
            )
            db.execute(
                "UPDATE call_bindings SET state=?,updated_ms=? WHERE receipt_id=?",
                ("cancelled" if settled else "cancelling", manager.clock(), row["receipt_id"]),
            )


def source_receipt(db, context):
    row = db.execute("SELECT message_id FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
    key = {"id": row["message_id"], "remoteJid": context.scope.chat, "fromMe": False}
    if context.scope.is_group:
        key["participant"] = context.scope.actor
    return {"chatId": context.scope.chat, "messageKey": key}


def validate_owned_call(value, binding):
    if (
        not isinstance(value, dict)
        or value.get("targetJid", value.get("groupId")) != binding["chat"]
        or value.get("origin") != {"chatId": binding["chat"], "requesterId": binding["actor"]}
    ):
        raise CallsError("foreign_call")
    return value


def notice(value):
    return {
        k: value[k]
        for k in ("id", "state", "reason", "requestedAt", "connectedAt", "endedAt", "video")
        if k in value
    }


async def run(job, directory, manager):
    from ..jobs import EngineOutput

    context, args, backend = job["context"], job["arguments"], manager.calls()
    op = job["operation"]
    action = op.split(".")[-1]
    start = op == "control_call.start"
    creating = start or op == "audiovisual.agenda.create"
    dispatched = False
    try:
        if not permitted(backend, manager.settings, context):
            raise CallsError("not_configured")
        await drain_cancellations(manager, backend)
        if not manager.current(job):
            raise CallsError("job_retired")
        with manager.store.transaction() as db:
            binding = current_binding(db, context)
            receipt = source_receipt(db, context)
        origin = {"chatId": context.scope.chat, "requesterId": context.scope.actor}
        if start:
            if backend.policy_revision != manager.settings.calls.revision:
                raise CallsError("policy_mismatch")
            manager.mark_provider(job)
            dispatched = True
            request = CallRequest(
                job["id"],
                context.scope,
                context.scope.chat,
                "live",
                video=args["video"],
                topic=args.get("topic"),
                max_seconds=args["max_seconds"],
                source_receipt=receipt,
            )
            response = await backend.start(request)
            call = response.get("call")
            if response.get("cancelled"):
                raise CallsError("cancelled")
            call = validate_owned_call(call, binding)
            if not manager.current(job) or not permitted(backend, manager.settings, context):
                raise CallsError("job_retired")
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE call_bindings SET call_id=?,state=?,updated_ms=? WHERE receipt_id=? AND state='reserved'",
                    (call["id"], call["state"], manager.clock(), job["id"]),
                )
            return EngineOutput(
                Result(
                    "ok",
                    "call_requested",
                    "Llamada solicitada; aún no confirma conexión ni escucha.",
                    {"call": notice(call)},
                )
            )
        if op.startswith("audiovisual.agenda."):
            payload = {"origin": origin}
            if action in {"create", "update"}:
                due = datetime.fromisoformat(args["date"] + "T" + args["time"]).replace(
                    tzinfo=ZoneInfo(manager.settings.timezone)
                )
                payload.update(
                    dueAt=int(due.timestamp() * 1000), timeZone=manager.settings.timezone
                )
            if action in {"cancel", "update"}:
                payload["id"] = args["id"]
            if action == "create":
                payload.update(
                    targetJid=context.scope.chat,
                    maxSeconds=args["max_seconds"],
                    volume=args["volume"],
                    endAfterAudio=args["end_after_audio"],
                    durationFromAnswer=True,
                    live=not bool(args.get("audio_id")),
                    sourceReceipt=receipt,
                )
                if args.get("audio_id"):
                    payload["audioId"] = args["audio_id"]
                if args.get("live_request"):
                    payload["liveRequest"] = args["live_request"]
            if action != "list":
                manager.mark_provider(job)
                dispatched = True
            response = await backend.command("agenda." + action, payload, key=job["id"])
            if not manager.current(job) or not permitted(backend, manager.settings, context):
                raise CallsError("job_retired")
            if action == "create":
                schedule = response.get("schedule")
                if not isinstance(schedule, dict) or not isinstance(schedule.get("id"), str):
                    raise CallsError("invalid_provider_result")
                with manager.store.transaction() as db:
                    db.execute(
                        "UPDATE call_bindings SET schedule_id=? WHERE receipt_id=?",
                        (schedule["id"], job["id"]),
                    )
            if action == "cancel":
                with manager.store.transaction() as db:
                    db.execute(
                        "UPDATE call_bindings SET state='cancelled',updated_ms=? WHERE instance=? AND account=? AND actor=? AND chat=? AND epoch=? AND schedule_id=? AND state='scheduled'",
                        (
                            manager.clock(),
                            context.instance,
                            context.account,
                            context.scope.actor,
                            context.scope.chat,
                            context.epoch,
                            args["id"],
                        ),
                    )
            schedules = (
                response.get("schedules") if action == "list" else [response.get("schedule")]
            )
            if not isinstance(schedules, list) or any(
                not isinstance(v, dict)
                or not isinstance(v.get("id"), str)
                or type(v.get("dueAt")) is not int
                or not isinstance(v.get("state"), str)
                for v in schedules
            ):
                raise CallsError("invalid_provider_result")
            lines = []
            for value in schedules:
                due = datetime.fromtimestamp(
                    value["dueAt"] / 1000, ZoneInfo(manager.settings.timezone)
                ).strftime("%Y-%m-%d %H:%M")
                lines.append(value["id"] + " · " + due + " · " + value["state"])
            text = (
                "Agenda vacía."
                if not lines
                else "Agenda (America/Mexico_City):\n" + "\n".join(lines)
            )
            return EngineOutput(Result("ok", "agenda_" + action, text, response))
        if not binding:
            return EngineOutput(
                Result("empty", "no_current_call", "No hay una llamada vigente en este chat.")
            )
        observed = await backend.operation(binding["receipt_id"])
        call = observed.get("call")
        if observed.get("cancelled") and not call:
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE call_bindings SET state='cancelled',updated_ms=? WHERE receipt_id=?",
                    (manager.clock(), binding["receipt_id"]),
                )
            return EngineOutput(Result("cancelled", "call_cancelled", "Encargo cancelado."))
        if not call:
            if binding["state"] == "scheduled" and op == "control_call.status":
                return EngineOutput(
                    Result(
                        "ok",
                        "call_scheduled",
                        "El encargo está programado; todavía no hay una llamada registrada.",
                    )
                )
            if op == "control_call.cancel":
                manager.mark_provider(job)
                dispatched = True
                await backend.cancel_preparation(binding["receipt_id"])
                with manager.store.transaction() as db:
                    db.execute(
                        "UPDATE call_bindings SET state='cancelled',updated_ms=? WHERE receipt_id=?",
                        (manager.clock(), binding["receipt_id"]),
                    )
                return EngineOutput(Result("cancelled", "call_cancelled", "Encargo cancelado."))
            raise CallsError("delivery_uncertain")
        call = validate_owned_call(call, binding)
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE call_bindings SET call_id=?,state=?,updated_ms=? WHERE receipt_id=? AND state<>'cancelling'",
                (call["id"], call["state"], manager.clock(), binding["receipt_id"]),
            )
        if action == "status" and op.startswith("control_call."):
            return EngineOutput(
                Result(
                    "ok", "call_status", "Llamada: " + call["state"] + ".", {"call": notice(call)}
                )
            )
        if call["state"] in TERMINAL:
            return EngineOutput(Result("empty", "call_ended", "La llamada ya terminó."))
        checked = await backend.call_by_id(call["id"])
        if checked["key"] != binding["receipt_id"]:
            raise CallsError("foreign_call")
        validate_owned_call(checked["call"], binding)
        manager.mark_provider(job)
        dispatched = True
        if op in {"control_call.hangup", "control_call.cancel"}:
            if action == "cancel":
                await backend.cancel_preparation(binding["receipt_id"])
                response = await backend.operation(binding["receipt_id"])
            else:
                response = await backend.hangup(call["id"])
            returned = response.get("call")
            if returned is not None:
                validate_owned_call(returned, binding)
            state = (
                returned["state"]
                if returned
                and returned.get("state") in TERMINAL
                and returned.get("cleanup", {}).get("state") in {"released", "browser_closed"}
                else "ending"
            )
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE call_bindings SET state=?,updated_ms=? WHERE receipt_id=?",
                    (state, manager.clock(), binding["receipt_id"]),
                )
            return EngineOutput(
                Result(
                    "ok",
                    "call_end_requested",
                    "Cierre solicitado a la llamada exacta; consulta /llamada estado para confirmar.",
                )
            )
        if op == "audiovisual.clip.list":
            response = await backend.command("clip.list")
            clips = response.get("clips")
            if not isinstance(clips, list) or any(
                not isinstance(c, dict)
                or not isinstance(c.get("id"), str)
                or not isinstance(c.get("label"), str)
                for c in clips
            ):
                raise CallsError("invalid_provider_result")
            safe = [{"id": c["id"], "name": c["label"][:120]} for c in clips]
            text = (
                "Catálogo vacío."
                if not safe
                else "Clips disponibles:\n" + "\n".join(c["id"] + " · " + c["name"] for c in safe)
            )
            return EngineOutput(Result("ok", "av_control_applied", text, {"clips": safe}))
        if op.startswith("audiovisual.avatar."):
            payload = {
                "callId": call["id"],
                "action": action,
                "name": "soft" if args["name"] == "suave" else args["name"],
            }
            if action != "background":
                payload["duration"] = args["duration"]
            response = await backend.command("avatar.control", payload, key=job["id"])
        elif action == "play" and args.get("clip_id"):
            if args.get("query"):
                raise CallsError("ambiguous_clip")
            response = await backend.command(
                "clip.play", {"callId": call["id"], "clipId": args["clip_id"]}, key=job["id"]
            )
            if (
                response.get("callId") != call["id"]
                or not isinstance(response.get("clip"), dict)
                or response["clip"].get("state") not in {"playing", "paused"}
            ):
                raise CallsError("invalid_provider_result")
            response["success"] = True
            response["message"] = (
                "Clip solicitado: "
                + args["clip_id"]
                + ". Estado del servicio: "
                + str(response["clip"].get("state", "desconocido"))
                + "."
            )
        else:
            request = {"action": action}
            if args.get("query"):
                request["query"] = args["query"]
            if "volume" in args:
                request["volume"] = args["volume"]
            if args.get("direction"):
                request["adjustment"] = args["adjustment"] * (
                    -1 if args["direction"] == "bajar" else 1
                )
            response = await backend.command(
                "clip.command",
                {
                    "callId": call["id"],
                    "scope": context.receipt_id if action != "play" else str(context.scope_key),
                    "request": request,
                },
                key=job["id"],
            )
        return EngineOutput(
            Result(
                "ok" if response.get("success") is True else "needs_input",
                "av_control_applied"
                if response.get("success") is True
                else "av_control_unconfirmed",
                response.get("message", "Control audiovisual solicitado; consulta estado."),
                response,
            )
        )
    except BaseException as exc:
        uncertain = dispatched and (
            not isinstance(exc, CallsError)
            or exc.code
            in {
                "delivery_uncertain",
                "provider_unavailable",
                "invalid_provider_result",
                "foreign_call",
                "job_retired",
            }
        )
        if creating:
            with manager.store.transaction() as db:
                if (
                    isinstance(exc, asyncio.CancelledError)
                    or not manager.current(job)
                    or not permitted(backend, manager.settings, context)
                ):
                    retire_job(db, job["id"], manager.clock())
                else:
                    db.execute(
                        "UPDATE call_bindings SET state=?,updated_ms=? WHERE receipt_id=? AND state IN ('reserved','scheduled')",
                        ("uncertain" if uncertain else "failed", manager.clock(), job["id"]),
                    )
            if not manager.current(job) or not permitted(backend, manager.settings, context):
                try:
                    await asyncio.shield(drain_cancellations(manager, backend))
                except CallsError, asyncio.CancelledError:
                    pass
        if not isinstance(exc, Exception):
            raise
        code = exc.code if isinstance(exc, CallsError) else "audiovisual_failed"
        return EngineOutput(
            Result(
                "uncertain" if uncertain else "failed",
                "calls_" + code,
                "No pude confirmar la operación audiovisual. No la repetiré automáticamente.",
            )
        )
