"""Cooperacha por aportes explícitos propios; escrow, publicación y liquidación única."""

import asyncio
import hashlib
import json
from io import BytesIO
from uuid import uuid4

from ..contracts import Result, canonical
from . import economy as xp
from .blackjack import CHAT, chat_key
from .packs import configured


def summary(row):
    return Result(
        "uncertain" if row["state"] == "uncertain" else "ok",
        "coop_status",
        f"Cooperacha {row['id']}: {row['state']} · {row['total']}/{row['target']} XP · devuelto {row['refund']} XP.",
        {
            "challenge_id": row["id"],
            "state": row["state"],
            "total": row["total"],
            "target": row["target"],
            "refund": row["refund"],
            "category": row["category"],
            "expires_ms": row["expires_ms"],
        },
    )


def settle(db, identifier, state, now):
    row = db.execute("SELECT * FROM cooperachas WHERE id=?", (identifier,)).fetchone()
    if not row or row["state"] in ("completed", "cancelled", "expired", "failed"):
        return
    if state in ("completed", "uncertain") and row["photo_json"]:
        manifest = json.loads(row["photo_json"])
        db.execute(
            "INSERT OR IGNORE INTO coop_seen VALUES(?,?,?,?,?)",
            (row["instance"], row["account"], row["chat"], row["epoch"], manifest["id"]),
        )
    if state == "uncertain":
        db.execute("UPDATE cooperachas SET state='uncertain' WHERE id=?", (identifier,))
        return
    ratio = 80 if state == "expired" else 100 if state in ("cancelled", "failed") else 0
    refund = 0
    for group in db.execute(
        "SELECT wallet_id,sum(amount) AS total FROM coop_contributions WHERE challenge_id=? GROUP BY wallet_id",
        (identifier,),
    ).fetchall():
        amount = group["total"] * ratio // 100
        refund += amount
        xp.release(
            db,
            group["wallet_id"],
            "coop-" + identifier,
            amount,
            "coop-settle-" + identifier,
            now,
            "coop_settlement",
        )
    db.execute("UPDATE cooperachas SET state=?,refund=? WHERE id=?", (state, refund, identifier))


def retire_job(db, receipt_id, now):
    for row in db.execute(
        "SELECT * FROM cooperachas WHERE preview_receipt_id=? OR complete_receipt_id=?",
        (receipt_id, receipt_id),
    ).fetchall():
        if row["state"] == "sending":
            settle(db, row["id"], "uncertain", now)
        elif row["state"] in ("preparing", "ready"):
            settle(db, row["id"], "failed", now)


def expire(db, settings, now):
    for row in db.execute(
        "SELECT c.* FROM cooperachas c JOIN inbox i ON c.preview_receipt_id=i.id WHERE c.instance=? AND c.account=? AND c.epoch=? AND c.state IN ('preparing','publishing') AND i.received_ms<=?",
        (settings.instance, settings.account, settings.epoch, now - 300000),
    ).fetchall():
        settle(db, row["id"], "failed", now)
    for row in db.execute(
        "SELECT * FROM cooperachas WHERE instance=? AND account=? AND epoch=? AND state='open' AND expires_ms<=?",
        (settings.instance, settings.account, settings.epoch, now),
    ).fetchall():
        settle(db, row["id"], "expired", now)


def delivered(db, receipt_id, now):
    db.execute(
        "UPDATE cooperachas SET state='open',published_ms=?,expires_ms=? WHERE preview_receipt_id=? AND state='publishing'",
        (now, now + 600000, receipt_id),
    )


def execute(db, context, spec, args, now, app):
    if not context.scope.is_group:
        return Result(
            "failed", "coop_group_required", "Las cooperachas requieren un grupo habilitado."
        )
    expire(db, app.settings, now)
    action = spec.original_action
    if action == "start":
        if not configured(context, app):
            return Result(
                "failed",
                "coop_not_configured",
                "Cooperachas requieren biblioteca publicada y entrega propias habilitadas en este grupo.",
            )
        if db.execute(
            "SELECT 1 FROM cooperachas WHERE "
            + CHAT
            + " AND state IN ('preparing','publishing','open','ready','sending','uncertain')",
            chat_key(context),
        ).fetchone():
            return Result(
                "needs_input",
                "coop_already_active",
                "Ya existe una cooperacha pendiente en el grupo.",
            )
        identifier = uuid4().hex
        queued = app.jobs.reserve(
            db,
            context,
            "manage_cooperacha.start",
            {"challenge_id": identifier, "category": args["category"]},
            [],
            now,
            resource="coop-" + identifier,
        )
        if queued.code == "job_queued":
            db.execute(
                "INSERT INTO cooperachas(id,instance,account,chat,is_group,epoch,creator,category,target,preview_receipt_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    *chat_key(context),
                    context.scope.actor,
                    args["category"],
                    args["target_xp"],
                    context.receipt_id,
                ),
            )
        return queued
    params = list(chat_key(context))
    query = "SELECT * FROM cooperachas WHERE " + CHAT
    if args.get("challenge_id"):
        query += " AND id=?"
        params.append(args["challenge_id"])
    row = db.execute(query + " ORDER BY rowid DESC LIMIT 1", params).fetchone()
    if not row:
        return Result("empty", "coop_not_found", "No hay una cooperacha con ese ID en este grupo.")
    if action == "status":
        return summary(row)
    if action == "cancel":
        if context.scope.actor not in (row["creator"], app.settings.owner):
            return Result(
                "failed", "coop_creator_required", "Solo creador o dueño cancela este reto."
            )
        settle(
            db,
            row["id"],
            "uncertain" if row["state"] in ("sending", "uncertain") else "cancelled",
            now,
        )
        return summary(db.execute("SELECT * FROM cooperachas WHERE id=?", (row["id"],)).fetchone())
    if row["state"] != "open" or row["expires_ms"] <= now:
        return Result("failed", "coop_not_open", "El reto no está abierto para nuevos aportes.")
    source_ms = db.execute(
        "SELECT min(source_ms,received_ms) FROM inbox WHERE id=?", (context.receipt_id,)
    ).fetchone()[0]
    if source_ms <= row["published_ms"]:
        return Result(
            "needs_input",
            "coop_publication_required",
            "El aporte debe ser posterior a la publicación aceptada.",
        )
    amount = args["amount"]
    own = xp.wallet(db, context)
    remaining = row["target"] - row["total"]
    if amount > remaining:
        return Result(
            "needs_input",
            "coop_over_target",
            f"Faltan {remaining} XP; indica un aporte hasta esa cantidad. No desconté saldo.",
        )
    if amount > own["balance"]:
        return Result(
            "failed", "coop_insufficient_xp", "Tu saldo no alcanza; no se tocó saldo ajeno."
        )
    if amount == remaining:
        queued = app.jobs.reserve(
            db,
            context,
            "manage_cooperacha.complete",
            {"challenge_id": row["id"]},
            [],
            now,
            resource="coop-" + row["id"],
        )
        if queued.code != "job_queued":
            return queued
    xp.move(
        db,
        own["id"],
        -amount,
        context.receipt_id,
        "coop_contribution",
        now,
        context.receipt_id,
        reserve=amount,
    )
    db.execute(
        "INSERT INTO xp_holds VALUES(?,?,?) ON CONFLICT(resource,wallet_id) DO UPDATE SET amount=amount+excluded.amount",
        ("coop-" + row["id"], own["id"], amount),
    )
    db.execute(
        "INSERT INTO coop_contributions VALUES(?,?,?,?,?)",
        (context.receipt_id, row["id"], own["id"], amount, now),
    )
    db.execute(
        "UPDATE cooperachas SET total=total+?,state=?,complete_receipt_id=? WHERE id=?",
        (
            amount,
            "ready" if amount == remaining else "open",
            context.receipt_id if amount == remaining else row["complete_receipt_id"],
            row["id"],
        ),
    )
    return (
        queued
        if amount == remaining
        else summary(db.execute("SELECT * FROM cooperachas WHERE id=?", (row["id"],)).fetchone())
    )


def finish_preview(db, context, result):
    row = db.execute(
        "SELECT * FROM cooperachas WHERE id=?", (result.data["challenge_id"],)
    ).fetchone()
    if not row or row["state"] != "preparing":
        return Result("cancelled", "coop_retired", "El reto fue retirado antes de publicarse.")
    db.execute(
        "UPDATE cooperachas SET state='publishing',photo_json=? WHERE id=?",
        (canonical(result.data["photo"]), row["id"]),
    )
    return Result(
        "ok",
        "coop_preview",
        f"Cooperacha {row['id']} · meta {row['target']} XP. Vence10min tras aceptar esta vista completa. Al completar se publica la foto original en este grupo. Al vencer se devuelve80% por persona, redondeado hacia abajo; cancelación o fallo conocido100%; entrega incierta retiene el saldo, sin reenviar.\n/coop aportar {row['id']} 50",
        {
            "challenge_id": row["id"],
            "artifacts": result.data.get("artifacts", []),
            "category": row["category"],
            "target": row["target"],
            "media_first": True,
        },
    )


async def run(job, directory, manager):
    from ..adapters.messenger import MessageError
    from ..jobs import EngineOutput

    library, backend, chats = manager.gallery()
    identifier = job["arguments"]["challenge_id"]
    with manager.store.transaction() as db:
        row = db.execute("SELECT * FROM cooperachas WHERE id=?", (identifier,)).fetchone()
    dispatched = False
    try:
        if library is None or backend is None or row["chat"] not in chats:
            raise ValueError("coop_configuration_changed")
        if job["operation"] == "manage_cooperacha.start":
            with manager.store.transaction() as db:
                seen = {
                    r[0]
                    for r in db.execute(
                        "SELECT photo_id FROM coop_seen WHERE instance=? AND account=? AND chat=? AND epoch=?",
                        (row["instance"], row["account"], row["chat"], row["epoch"]),
                    )
                }
            photos = await asyncio.to_thread(library.select, row["category"], 1, seen)
            if not photos:
                raise ValueError("coop_no_photo")
            photo = photos[0]
            from PIL import Image, ImageFilter

            with Image.open(BytesIO(photo.data)) as original:
                image = original.convert("RGB")
                image.thumbnail((512, 512))
                image = (
                    image.resize((max(1, image.width // 32), max(1, image.height // 32)))
                    .resize(image.size)
                    .filter(ImageFilter.GaussianBlur(12))
                )
                path = directory / "preview.jpg"
                image.save(path, format="JPEG")
            manifest = {
                "id": photo.id,
                "mime": photo.mime,
                "sha256": hashlib.sha256(photo.data).hexdigest(),
            }
            return EngineOutput(
                Result("ok", "coop_preview", data={"challenge_id": identifier, "photo": manifest}),
                (path,),
            )
        manifest = json.loads(row["photo_json"])
        photo = await asyncio.to_thread(library.get_photo, manifest["id"], row["category"])
        if (
            not photo
            or hashlib.sha256(photo.data).hexdigest() != manifest["sha256"]
            or photo.mime != manifest["mime"]
        ):
            raise ValueError("coop_photo_changed")
        with manager.store.transaction() as db:
            current = db.execute("SELECT * FROM cooperachas WHERE id=?", (identifier,)).fetchone()
            if current["state"] != "ready" or not manager.current(job):
                raise ValueError("coop_retired")
            db.execute("UPDATE cooperachas SET state='sending' WHERE id=?", (identifier,))
        manager.mark_provider(job)
        dispatched = True
        provider_id = await backend.send_photo(
            row["chat"],
            photo.data,
            photo.mime,
            view_once=False,
            caption="Cooperacha " + identifier + " completada.",
        )
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("invalid_photo_ack")
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE cooperachas SET provider_message_id=? WHERE id=?", (provider_id, identifier)
            )
            settle(db, identifier, "completed", manager.clock())
    except asyncio.CancelledError:
        with manager.store.transaction() as db:
            settle(db, identifier, "uncertain" if dispatched else "failed", manager.clock())
        raise
    except Exception as exc:
        state = (
            "uncertain"
            if dispatched and (not isinstance(exc, MessageError) or exc.uncertain)
            else "failed"
        )
        with manager.store.transaction() as db:
            settle(db, identifier, state, manager.clock())
    with manager.store.transaction() as db:
        result = summary(
            db.execute("SELECT * FROM cooperachas WHERE id=?", (identifier,)).fetchone()
        )
    return EngineOutput(result)
