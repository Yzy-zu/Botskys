"""Eventos explícitos ligados a publicación; premios monetarios y fotográficos separados."""

from uuid import uuid4

from ..contracts import Result
from . import economy as xp
from .blackjack import CHAT, chat_key


def active(db, context, now, source_ms=None):
    return db.execute(
        "SELECT * FROM happy_events WHERE "
        + CHAT
        + " AND state='active' AND expires_ms>? AND published_ms<?",
        (*chat_key(context), now, min(now, source_ms or now)),
    ).fetchone()


def expire(db, now, settings):
    db.execute(
        "UPDATE happy_drops SET state='closed' WHERE state IN ('publishing','open') AND event_id IN (SELECT id FROM happy_events WHERE instance=? AND account=? AND epoch=? AND (expires_ms<=? OR state='closed'))",
        (settings.instance, settings.account, settings.epoch, now),
    )
    db.execute(
        "UPDATE happy_events SET state='closed' WHERE instance=? AND account=? AND epoch=? AND state='active' AND expires_ms<=?",
        (settings.instance, settings.account, settings.epoch, now),
    )
    db.execute(
        "UPDATE happy_events SET state='closed' WHERE instance=? AND account=? AND epoch=? AND state='preparing' AND receipt_id IN (SELECT id FROM inbox WHERE received_ms<?)",
        (settings.instance, settings.account, settings.epoch, now - 300000),
    )


def execute(db, context, action, args, now, app):
    if not context.scope.is_group:
        return Result("failed", "happy_group_required", "Hora feliz requiere un grupo habilitado.")
    expire(db, now, app.settings)
    if action == "start":
        if db.execute(
            "SELECT 1 FROM happy_events WHERE " + CHAT + " AND state IN ('preparing','active')",
            chat_key(context),
        ).fetchone():
            return Result(
                "needs_input",
                "happy_already_active",
                "Ya hay una hora feliz activa o pendiente de publicación.",
            )
        identifier = uuid4().hex
        db.execute(
            "INSERT INTO happy_events(id,instance,account,chat,is_group,epoch,owner,duration_seconds,receipt_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                *chat_key(context),
                context.scope.actor,
                args["duration_seconds"],
                context.receipt_id,
            ),
        )
        return Result(
            "ok",
            "happy_started",
            f"Hora feliz {identifier}: {args['duration_seconds']}s desde la entrega de este aviso. 20 XP por mensaje normal del grupo; packs a 75 XP cuando estén disponibles.\n/hh estado {identifier}",
            {"event_id": identifier, "duration_seconds": args["duration_seconds"]},
        )
    source_ms = db.execute(
        "SELECT min(source_ms,received_ms) FROM inbox WHERE id=?", (context.receipt_id,)
    ).fetchone()[0]
    if action == "claim":
        drop = db.execute(
            "SELECT d.*,e.expires_ms,e.state AS event_state FROM happy_drops d JOIN happy_events e ON e.id=d.event_id WHERE d.id=? AND e."
            + CHAT.replace(" AND ", " AND e."),
            (args["drop_id"], *chat_key(context)),
        ).fetchone()
        if (
            not drop
            or drop["event_state"] != "active"
            or drop["expires_ms"] <= now
            or drop["state"] != "open"
        ):
            return Result(
                "empty", "happy_drop_unavailable", "Ese AirDrop no está abierto en este grupo."
            )
        if source_ms <= drop["published_ms"]:
            return Result(
                "needs_input",
                "happy_drop_publication_required",
                "La reclamación debe ser posterior al anuncio entregado.",
            )
        own = xp.wallet(db, context)
        try:
            xp.move(db, own["id"], 500, "airdrop-" + drop["id"], "airdrop", now, context.receipt_id)
        except ValueError:
            return Result("failed", "xp_limit", "No hay margen para adjudicar el premio.")
        db.execute(
            "UPDATE happy_drops SET state='claimed',wallet_id=?,claim_receipt_id=? WHERE id=? AND state='open'",
            (own["id"], context.receipt_id, drop["id"]),
        )
        from .packs import configured

        if configured(context, app):
            from .happy_media import reserve

            queued = reserve(
                db, context, drop["event_id"], "reward", context.scope.actor, now, app.jobs
            )
            if queued.code == "job_queued":
                return Result(
                    "ok",
                    "job_queued",
                    "+500 XP adjudicados una vez. Premio fotográfico en preparación.",
                    {**queued.data, "gained": 500, "drop_id": drop["id"]},
                )
        return Result(
            "ok",
            "happy_drop_claimed",
            f"AirDrop {drop['id']}: +500 XP adjudicados una sola vez a cuenta #{own['id']}. El premio fotográfico se gestiona por separado.",
            {
                "event_id": drop["event_id"],
                "drop_id": drop["id"],
                "wallet_id": own["id"],
                "gained": 500,
            },
        )
    params = list(chat_key(context))
    query = "SELECT * FROM happy_events WHERE " + CHAT
    if args.get("event_id"):
        query += " AND id=?"
        params.append(args["event_id"])
    event = db.execute(query + " ORDER BY rowid DESC LIMIT 1", params).fetchone()
    if not event:
        return Result("empty", "happy_not_found", "No hay una hora feliz con ese ID en este grupo.")
    if action == "status":
        drop = db.execute(
            "SELECT id,state FROM happy_drops WHERE event_id=?", (event["id"],)
        ).fetchone()
        return Result(
            "ok",
            "happy_status",
            f"Hora feliz {event['id']}: {event['state']}."
            + (f" AirDrop {drop['id']}: {drop['state']}." if drop else ""),
            {
                "event_id": event["id"],
                "state": event["state"],
                "drop": dict(drop) if drop else None,
                "expires_ms": event["expires_ms"],
                "duration_seconds": event["duration_seconds"],
            },
        )
    if action == "stop":
        db.execute("UPDATE happy_events SET state='closed' WHERE id=?", (event["id"],))
        db.execute(
            "UPDATE happy_drops SET state='closed' WHERE event_id=? AND state IN ('open','publishing')",
            (event["id"],),
        )
        return Result(
            "ok",
            "happy_stopped",
            "Hora feliz cerrada; premios nuevos retirados.",
            {"event_id": event["id"]},
        )
    if event["state"] != "active" or event["expires_ms"] <= now:
        return Result("failed", "happy_not_active", "La hora feliz debe estar activa y vigente.")
    if action == "airdrop":
        if db.execute("SELECT 1 FROM happy_drops WHERE event_id=?", (event["id"],)).fetchone():
            return Result(
                "empty",
                "happy_drop_exists",
                "Ya hay un AirDrop adjudicado o publicado para este evento.",
            )
        identifier = uuid4().hex
        db.execute(
            "INSERT INTO happy_drops(id,event_id,receipt_id) VALUES(?,?,?)",
            (identifier, event["id"], context.receipt_id),
        )
        return Result(
            "ok",
            "happy_drop_announced",
            f"AirDrop {identifier}: la primera reclamación posterior a la entrega de este aviso gana500 XP.\n/hh reclamar {identifier}",
            {"event_id": event["id"], "drop_id": identifier},
        )
    from .packs import configured

    if configured(context, app):
        from .happy_media import reserve

        result = reserve(db, context, event["id"], "rain", context.scope.chat, now, app.jobs)
        if result.code == "job_queued":
            db.execute(
                "UPDATE happy_events SET last_rain_ms=?,activity=0 WHERE id=?", (now, event["id"])
            )
        return result
    return Result(
        "failed",
        "happy_photos_not_configured",
        "La lluvia de fotos requiere biblioteca publicada y transporte propios configurados; no se simuló un envío.",
    )


def delivered(db, receipt_id, now):
    db.execute(
        "UPDATE happy_events SET state='active',published_ms=?,expires_ms=?+duration_seconds*1000 WHERE receipt_id=? AND state='preparing'",
        (now, now, receipt_id),
    )
    db.execute(
        "UPDATE happy_drops SET state='open',published_ms=? WHERE receipt_id=? AND state='publishing' AND event_id IN (SELECT id FROM happy_events WHERE state='active' AND expires_ms>?)",
        (now, receipt_id, now),
    )
