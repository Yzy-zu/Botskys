"""HH en tick explícito: claves de evento durables, sin recuperar lluvias pasadas."""

from uuid import uuid4

from ..contracts import CommandContext, Scope, canonical
from .happy_media import reserve


def tick(scheduler, db, now, remaining):
    app = scheduler.app
    settings = app.settings
    emitted = []
    events = db.execute(
        "SELECT * FROM happy_events WHERE instance=? AND account=? AND epoch=? AND state='active' AND expires_ms>?",
        (settings.instance, settings.account, settings.epoch, now),
    ).fetchall()
    for event in events:
        row = dict(event)
        row["actor"] = event["owner"]
        if row["actor"] != settings.owner or not scheduler.allowed(db, row, now):
            continue
        due = event["published_ms"] + min(60000, max(10000, event["duration_seconds"] * 50))
        if (
            now >= due
            and not db.execute(
                "SELECT 1 FROM happy_drops WHERE event_id=?", (event["id"],)
            ).fetchone()
            and len(emitted) < remaining
        ):
            key = canonical(["happy_drop", event["id"]])
            identifier = uuid4().hex
            receipt = scheduler.emit(
                db,
                row,
                "happy_drop",
                key,
                f"AirDrop {identifier}: primera reclamación posterior al anuncio gana500 XP y premio fotográfico privado sujeto a biblioteca y destino verificado.\n/hh reclamar {identifier}",
                now,
            )
            db.execute(
                "INSERT INTO organization_events VALUES(?,?,?,?,'emitted',?,?)",
                (key, "happy_drop", event["id"], receipt, now, event["expires_ms"]),
            )
            db.execute(
                "INSERT INTO happy_drops(id,event_id,receipt_id) VALUES(?,?,?)",
                (identifier, event["id"], receipt),
            )
            emitted.append(receipt)
        photo_due = (
            event["published_ms"] + 10000
            if event["last_rain_ms"] is None
            else event["last_rain_ms"] + 240000
        )
        if event["activity"] >= 5 and event["last_rain_ms"] is not None:
            photo_due = min(photo_due, event["last_rain_ms"] + 90000)
        if (
            now < photo_due
            or app.gallery is None
            or app.photo_transport is None
            or event["chat"] not in app.gallery_chats
            or len(emitted) >= remaining
        ):
            continue
        slot = max(0, (now - event["published_ms"] - 10000) // 240000)
        key = canonical(["happy_rain", event["id"], slot])
        if db.execute("SELECT 1 FROM organization_events WHERE event_key=?", (key,)).fetchone():
            continue
        if db.execute(
            "SELECT 1 FROM happy_photo_jobs WHERE event_id=? AND kind='rain' AND state IN ('queued','running')",
            (event["id"],),
        ).fetchone():
            continue
        receipt = scheduler.emit(db, row, "happy_rain", key, "", now)
        context = CommandContext(
            receipt,
            row["instance"],
            row["account"],
            Scope(row["actor"], row["chat"], True),
            row["epoch"],
            0,
        )
        result = reserve(db, context, event["id"], "rain", row["chat"], now, app.jobs)
        db.execute(
            "UPDATE inbox SET result_json=?,revision=revision+1 WHERE id=?",
            (result.to_json(), receipt),
        )
        db.execute(
            "UPDATE effects SET result_json=? WHERE receipt_id=?", (result.to_json(), receipt)
        )
        db.execute(
            "INSERT INTO organization_events VALUES(?,?,?,?,'emitted',?,?)",
            (key, "happy_rain", event["id"], receipt, now, event["expires_ms"]),
        )
        if result.code == "job_queued":
            db.execute(
                "UPDATE happy_events SET last_rain_ms=?,activity=0 WHERE id=?", (now, event["id"])
            )
        emitted.append(receipt)
    return emitted
