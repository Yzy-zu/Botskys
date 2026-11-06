"""Aviso privado consentido de retorno: reserva única y resultado incierto durable."""

from ..contracts import CommandContext, Scope, canonical


def tick(scheduler, db, now, remaining):
    app = scheduler.app
    settings = app.settings
    receipts = []
    rows = db.execute(
        "SELECT r.*,p.actor,p.join_receipt_id FROM roulette_rooms r JOIN roulette_players p ON p.room_id=r.id AND p.actor=r.target_actor WHERE r.instance=? AND r.account=? AND r.epoch=? AND r.state='completed' AND r.return_state='pending' AND r.return_due_ms<=?",
        (settings.instance, settings.account, settings.epoch, now),
    ).fetchall()
    for item in rows:
        if len(receipts) >= remaining:
            break
        row = dict(item)
        row["receipt_id"] = row["join_receipt_id"]
        if not scheduler.allowed(db, row, now):
            continue
        key = canonical(["roulette_return", row["id"]])
        if db.execute("SELECT 1 FROM organization_events WHERE event_key=?", (key,)).fetchone():
            continue
        receipt = scheduler.emit(db, row, "roulette_return", key, "", now)
        context = CommandContext(
            receipt,
            row["instance"],
            row["account"],
            Scope(row["actor"], row["chat"], True),
            row["epoch"],
            0,
        )
        result = app.jobs.reserve(
            db,
            context,
            "manage_roulette.return",
            {"room_id": row["id"]},
            [],
            now,
            resource="roulette-return-" + row["id"],
        )
        db.execute(
            "UPDATE inbox SET result_json=?,revision=revision+1 WHERE id=?",
            (result.to_json(), receipt),
        )
        db.execute(
            "UPDATE effects SET result_json=? WHERE receipt_id=?", (result.to_json(), receipt)
        )
        db.execute(
            "UPDATE roulette_rooms SET return_receipt_id=?,return_state=? WHERE id=?",
            (receipt, "queued" if result.code == "job_queued" else "failed", row["id"]),
        )
        db.execute(
            "INSERT INTO organization_events VALUES(?,?,?,?,'emitted',?,?)",
            (key, "roulette_return", row["id"], receipt, now, now + 600000),
        )
        receipts.append(receipt)
    return receipts


async def run(job, directory, manager):
    from ..adapters.messenger import MessageError
    from ..contracts import Result
    from ..jobs import EngineOutput
    from .roulette import room

    identifier = job["arguments"]["room_id"]
    dispatched = False
    try:
        backend = manager.messages()[0]
        with manager.store.transaction() as db:
            row = room(db, identifier)
            if (
                not row
                or row["return_state"] != "queued"
                or row["target_actor"] != job["context"].scope.actor
                or row["return_due_ms"] > manager.clock()
                or manager.clock() > row["return_due_ms"] + 600000
                or backend is None
                or not backend.available
            ):
                raise ValueError("return_unavailable")
        manager.mark_provider(job)
        with manager.store.transaction() as db:
            if not manager.current(job):
                raise ValueError("job_retired")
            db.execute(
                "UPDATE roulette_rooms SET return_state='sending' WHERE id=? AND return_state='queued'",
                (identifier,),
            )
        dispatched = True
        provider = await backend.send(
            row["phone_id"],
            "text",
            text="Pasaron20 minutos de la ruleta. Puedes solicitar volver con esta invitación:\n"
            + row["invite_link"],
        )
        if not isinstance(provider, str) or not provider:
            raise ValueError("return_invalid_ack")
        state = "accepted"
    except BaseException as exc:
        state = (
            "uncertain"
            if dispatched and (not isinstance(exc, MessageError) or exc.uncertain)
            else "failed"
        )
        with manager.store.transaction() as db:
            db.execute("UPDATE roulette_rooms SET return_state=? WHERE id=?", (state, identifier))
        if not isinstance(exc, Exception):
            raise
    else:
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE roulette_rooms SET return_state=?,return_provider_id=? WHERE id=?",
                (state, provider, identifier),
            )
    return EngineOutput(
        Result(
            "uncertain" if state == "uncertain" else "ok" if state == "accepted" else "failed",
            "roulette_return_" + state,
            "Aviso de retorno: " + state + ". No se repetirá automáticamente.",
            {"room_id": identifier, "state": state},
        )
    )
