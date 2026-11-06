"""Lluvias y premio fotográfico de HH; partes durables sin volver a enviar inciertas."""

import asyncio
import secrets

from ..contracts import Result


def reserve(db, context, event_id, kind, target, now, jobs):
    if (
        kind == "rain"
        and db.execute(
            "SELECT 1 FROM happy_photo_jobs WHERE event_id=? AND kind='rain' AND state IN ('queued','running')",
            (event_id,),
        ).fetchone()
    ):
        return Result("empty", "happy_rain_busy", "Ya hay una lluvia pendiente para este evento.")
    queued = jobs.reserve(
        db,
        context,
        "manage_happy_hour." + kind,
        {"event_id": event_id, "kind": kind},
        [],
        now,
        resource="happy-media-" + event_id,
    )
    if queued.code == "job_queued":
        db.execute(
            "INSERT INTO happy_photo_jobs VALUES(?,?,?,?,?)",
            (context.receipt_id, event_id, kind, target, "queued"),
        )
    return queued


def retire_job(db, receipt_id, now):
    db.execute(
        "UPDATE happy_photo_parts SET state='uncertain' WHERE receipt_id=? AND state='sending'",
        (receipt_id,),
    )
    db.execute(
        "UPDATE happy_photo_parts SET state='cancelled' WHERE receipt_id=? AND state='pending'",
        (receipt_id,),
    )
    db.execute(
        "UPDATE happy_photo_jobs SET state=CASE WHEN EXISTS(SELECT 1 FROM happy_photo_parts WHERE receipt_id=? AND state='uncertain') THEN 'uncertain' ELSE 'cancelled' END WHERE receipt_id=? AND state IN ('queued','running')",
        (receipt_id, receipt_id),
    )


async def run(job, directory, manager):
    from ..adapters.messenger import MessageError
    from ..jobs import EngineOutput

    library, backend, chats = manager.gallery()
    with manager.store.transaction() as db:
        row = db.execute(
            "SELECT j.*,e.chat,e.state AS event_state,e.expires_ms FROM happy_photo_jobs j JOIN happy_events e ON j.event_id=e.id WHERE j.receipt_id=?",
            (job["id"],),
        ).fetchone()
    count = secrets.randbelow(2) + 1 if row["kind"] == "rain" else secrets.randbelow(3) + 4
    sent = 0
    try:
        if (
            library is None
            or backend is None
            or row["chat"] not in chats
            or row["event_state"] != "active"
            or row["expires_ms"] <= manager.clock()
        ):
            raise ValueError("happy_photos_unavailable")
        photos = await asyncio.to_thread(library.select, None, count, set())
        if not photos or row["kind"] == "reward" and len(photos) < 3:
            raise ValueError("happy_stock_insufficient")
        with manager.store.transaction() as db:
            if not manager.current(job):
                raise ValueError("job_retired")
            db.execute(
                "UPDATE happy_photo_jobs SET state='running' WHERE receipt_id=? AND state='queued'",
                (job["id"],),
            )
            for i, photo in enumerate(photos):
                db.execute(
                    "INSERT INTO happy_photo_parts(receipt_id,position,photo_id) VALUES(?,?,?)",
                    (job["id"], i, photo.id),
                )
        for i, photo in enumerate(photos):
            if not manager.current(job):
                break
            with manager.store.transaction() as db:
                event = db.execute(
                    "SELECT * FROM happy_events WHERE id=?", (row["event_id"],)
                ).fetchone()
                if (
                    not event
                    or event["state"] != "active"
                    or event["expires_ms"] <= manager.clock()
                ):
                    break
                db.execute(
                    "UPDATE happy_photo_parts SET state='sending' WHERE receipt_id=? AND position=? AND state='pending'",
                    (job["id"], i),
                )
            state, provider = "uncertain", None
            try:
                manager.mark_provider(job)
                _, current_backend, current_chats = manager.gallery()
                if current_backend is not backend or row["chat"] not in current_chats:
                    raise MessageError("happy_configuration_changed", False)
                provider = await backend.send_photo(
                    row["target"], photo.data, photo.mime, view_once=row["kind"] == "reward"
                )
                if not isinstance(provider, str) or not provider:
                    raise ValueError("invalid_ack")
                state = "accepted"
                sent += 1
            except MessageError as exc:
                state = "uncertain" if exc.uncertain else "failed"
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE happy_photo_parts SET state=?,provider_message_id=? WHERE receipt_id=? AND position=?",
                    (state, provider, job["id"], i),
                )
            if state != "accepted":
                break
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    finally:
        with manager.store.transaction() as db:
            retire_job(db, job["id"], manager.clock())
            states = [
                r[0]
                for r in db.execute(
                    "SELECT state FROM happy_photo_parts WHERE receipt_id=?", (job["id"],)
                )
            ]
            if states and all(s == "accepted" for s in states):
                db.execute(
                    "UPDATE happy_photo_jobs SET state='completed' WHERE receipt_id=?", (job["id"],)
                )
    uncertain = "uncertain" in states
    return EngineOutput(
        Result(
            "uncertain" if uncertain else "ok" if sent else "empty",
            "happy_photos_result",
            f"Fotos aceptadas: {sent}. "
            + (
                "Hay una entrega incierta; no se repetirá."
                if uncertain
                else "No se usó una fuente web."
            ),
            {"accepted": sent, "states": states, "event_id": row["event_id"]},
        )
    )
