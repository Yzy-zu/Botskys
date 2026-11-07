"""Packs con oferta entregada, fotos publicadas propias y cargo/liquidación única."""

import asyncio
import hashlib
import secrets
from uuid import uuid4

from .. import access
from ..contracts import Result, canonical
from . import economy as xp
from .happy_hour import active
from .notes import SCOPE_SQL


def configured(context, app):
    return (
        context.scope.chat in app.gallery_chats
        and app.gallery is not None
        and app.photo_transport is not None
        and getattr(app.photo_transport, "available", False)
    )


def summary(db, row):
    parts = [
        dict(p)
        for p in db.execute(
            "SELECT position,state,cost,error_code FROM gallery_parts WHERE order_id=? ORDER BY position",
            (row["id"],),
        )
    ]
    return Result(
        "uncertain" if any(p["state"] == "uncertain" for p in parts) else "ok",
        "pack_status",
        f"Pack {row['id']}: {row['state']}. Precio {row['price']} XP · devuelto {row['refund']} XP.\n"
        + "\n".join(f"Foto {p['position'] + 1}: {p['state']} · {p['cost']} XP" for p in parts),
        {
            "purchase_id": row["id"],
            "state": row["state"],
            "price": row["price"],
            "refund": row["refund"],
            "parts": parts,
        },
    )


def finish(db, identifier, now):
    row = db.execute("SELECT * FROM gallery_orders WHERE id=?", (identifier,)).fetchone()
    if not row or row["state"] not in ("preparing", "sending"):
        return
    db.execute(
        "UPDATE gallery_parts SET state='uncertain',error_code='interrupted' WHERE order_id=? AND state='sending'",
        (identifier,),
    )
    db.execute(
        "UPDATE gallery_parts SET state='cancelled' WHERE order_id=? AND state='pending'",
        (identifier,),
    )
    parts = db.execute("SELECT * FROM gallery_parts WHERE order_id=?", (identifier,)).fetchall()
    for p in parts:
        resource = f"pack-{identifier}-{p['position']}"
        if p["state"] == "uncertain":
            continue
        xp.release(
            db,
            row["wallet_id"],
            resource,
            0 if p["state"] == "accepted" else p["cost"],
            resource + "-settle",
            now,
            "pack_settlement",
        )
    refund = sum(p["cost"] for p in parts if p["state"] not in ("accepted", "uncertain"))
    state = (
        "completed"
        if parts and all(p["state"] == "accepted" for p in parts)
        else "uncertain"
        if any(p["state"] == "uncertain" for p in parts)
        else "partial"
        if any(p["state"] == "accepted" for p in parts)
        else "failed"
    )
    db.execute("UPDATE gallery_orders SET state=?,refund=? WHERE id=?", (state, refund, identifier))


def retire_job(db, receipt_id, now):
    for row in db.execute(
        "SELECT id FROM gallery_orders WHERE send_receipt_id=?", (receipt_id,)
    ).fetchall():
        finish(db, row["id"], now)


def execute(db, context, spec, args, now, app):
    if spec.original_action == "status":
        row = db.execute(
            f"SELECT * FROM gallery_orders WHERE id=? AND {SCOPE_SQL}",
            (args["purchase_id"], *context.scope_key),
        ).fetchone()
        return (
            summary(db, row)
            if row
            else Result("empty", "pack_not_found", "No hay una compra propia con ese ID aquí.")
        )
    catalog_ready = (
        spec.original_action == "catalog"
        and context.scope.chat in app.gallery_chats
        and app.gallery is not None
    )
    if not catalog_ready and not configured(context, app):
        return Result(
            "failed",
            "packs_not_configured",
            "Packs requieren biblioteca publicada y entrega privada explícitamente habilitadas en este chat; no hubo cargo.",
        )
    own = xp.wallet(db, context)
    if spec.original_action == "catalog":
        from ..adapters.gallery import LibraryError

        try:
            albums = app.gallery.catalog()
        except LibraryError:
            return Result(
                "failed",
                "gallery_unavailable",
                "No pude leer la biblioteca propia; no se usó una fuente web.",
            )
        if args.get("category"):
            albums = [
                a
                for a in albums
                if args["category"].casefold() in (a.slug.casefold(), a.name.casefold())
            ]
        pages = max(1, (len(albums) + 4) // 5)
        if args["page"] > pages:
            return Result("needs_input", "page_out_of_range", f"Página fuera de rango:1–{pages}.")
        items = [
            {"name": a.name, "category": a.slug, "count": a.count}
            for a in albums[(args["page"] - 1) * 5 : args["page"] * 5]
        ]
        return Result(
            "ok" if items else "empty",
            "pack_catalog",
            "Packs publicados ·150 XP, hora feliz75 XP.\n"
            + "\n".join(f"{a['name']} ({a['category']}): {a['count']} fotos" for a in items),
            {"items": items, "pages": pages, "page": args["page"]},
        )
    if not args.get("purchase_id"):
        category = args["category"]
        if category != "azar":
            from ..adapters.gallery import LibraryError

            try:
                available = app.gallery.category_exists(category)
            except LibraryError:
                return Result(
                    "failed",
                    "gallery_unavailable",
                    "No pude comprobar la categoría publicada; no se creó una oferta.",
                )
            if not available:
                return Result(
                    "needs_input",
                    "pack_category_unavailable",
                    "Esa categoría no está publicada. Consulta /pack catalogo; no se creó una oferta.",
                )
        event = active(db, context, now)
        price = 75 if event else 150
        if own["balance"] < price:
            return Result(
                "failed",
                "pack_insufficient_xp",
                f"Precio {price} XP. Saldo {own['balance']}; no hubo cargo.",
            )
        identifier = uuid4().hex
        db.execute(
            f"UPDATE gallery_orders SET state='cancelled' WHERE {SCOPE_SQL} AND state='offered'",
            context.scope_key,
        )
        db.execute(
            "INSERT INTO gallery_orders(id,instance,account,actor,chat,is_group,epoch,wallet_id,category,price,happy_event_id,preview_receipt_id,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                *context.scope_key,
                own["id"],
                None if args["category"] == "azar" else args["category"],
                price,
                event["id"] if event else None,
                context.receipt_id,
                now + 300000,
            ),
        )
        db.execute(
            "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,'{}','[]',?,'pending_delivery',?)",
            (
                identifier,
                context.receipt_id,
                *context.scope_key,
                "pack_offer",
                canonical({"purchase_id": identifier}),
                now + 300000,
            ),
        )
        return Result(
            "needs_input",
            "pack_offer",
            f"Pack {identifier}: {args['category']} · {price} XP · {'4–6' if event else '3–5'} fotos (mínimo3 por stock), visualización única en tu privado. Rechazo conocido devuelve su parte; incertidumbre la conserva sin reenviar. No he cobrado. Caduca en5min.\n/pack confirmar {identifier}",
            {
                "purchase_id": identifier,
                "price": price,
                "category": args["category"],
                "min_photos": 4 if event else 3,
                "max_photos": 6 if event else 5,
                "expires_ms": now + 300000,
            },
        )
    row = db.execute(
        f"SELECT * FROM gallery_orders WHERE id=? AND {SCOPE_SQL}",
        (args["purchase_id"], *context.scope_key),
    ).fetchone()
    if not row:
        return Result("empty", "pack_not_found", "No hay compra propia con ese ID.")
    if row["state"] != "offered":
        return summary(db, row)
    view = db.execute(
        "SELECT 1 FROM interactions WHERE id=? AND kind='pack_offer' AND state='active' AND expires_ms>?",
        (row["id"], now),
    ).fetchone()
    accepted = db.execute(
        "SELECT max(updated_ms) AS stamp,sum(state!='accepted') AS pending FROM outbox WHERE receipt_id=?",
        (row["preview_receipt_id"],),
    ).fetchone()
    source = db.execute(
        "SELECT min(source_ms,received_ms) FROM inbox WHERE id=?", (context.receipt_id,)
    ).fetchone()[0]
    if not view or accepted["pending"] or source <= accepted["stamp"]:
        return Result(
            "needs_input",
            "pack_preview_required",
            "Recibe la oferta completa vigente y después confirma su ID.",
        )
    if row["happy_event_id"]:
        event = active(db, context, now)
        if not event or event["id"] != row["happy_event_id"]:
            return Result(
                "needs_input",
                "pack_discount_expired",
                "Hora feliz terminó; solicita otra oferta sin cargo.",
            )
    queued = app.jobs.reserve(
        db,
        context,
        "manage_pack.buy",
        {"purchase_id": row["id"]},
        [],
        now,
        resource="pack-wallet-" + str(own["id"]),
    )
    if queued.code == "job_queued":
        db.execute(
            "UPDATE gallery_orders SET state='preparing',send_receipt_id=? WHERE id=?",
            (context.receipt_id, row["id"]),
        )
    return queued


async def run(job, directory, manager):
    from ..adapters.messenger import MessageError
    from ..engines.process import MediaError
    from ..jobs import EngineOutput

    app_gallery, backend, chats = manager.gallery()
    identifier = job["arguments"]["purchase_id"]
    with manager.store.transaction() as db:
        row = db.execute("SELECT * FROM gallery_orders WHERE id=?", (identifier,)).fetchone()
        excluded = {
            p[0]
            for p in db.execute(
                "SELECT photo_id FROM gallery_seen WHERE wallet_id=?", (row["wallet_id"],)
            )
        }
    try:
        if app_gallery is None or backend is None or row["chat"] not in chats:
            raise ValueError("gallery_configuration_changed")
        count = secrets.randbelow(3) + (4 if row["price"] == 75 else 3)
        photos = await asyncio.to_thread(app_gallery.select, row["category"], count, excluded)
        if len(photos) < 3 or len({p.id for p in photos}) != len(photos):
            raise ValueError("gallery_stock_insufficient")
        with manager.store.transaction() as db:
            current = db.execute(
                "SELECT * FROM gallery_orders WHERE id=?", (identifier,)
            ).fetchone()
            if current["state"] != "preparing" or not manager.current(job):
                raise ValueError("order_retired")
            own = xp.wallet(db, job["context"])
            if access.authorize("friend", job["context"], manager.settings):
                raise ValueError("pack_permission_revoked")
            if own["balance"] < row["price"]:
                raise ValueError("pack_insufficient_xp")
            # Comprobar el margen total antes de crear las reservas por foto.
            if own["balance"] + own["reserved"] > xp.MAX_BALANCE:
                raise ValueError("xp_headroom")
            for i, photo in enumerate(photos):
                cost = row["price"] // len(photos) + int(i < row["price"] % len(photos))
                xp.hold(
                    db,
                    own["id"],
                    f"pack-{identifier}-{i}",
                    cost,
                    cost,
                    f"pack-charge-{identifier}-{i}",
                    manager.clock(),
                    job["id"],
                )
                db.execute(
                    "INSERT INTO gallery_parts(order_id,position,photo_id,sha256,cost) VALUES(?,?,?,?,?)",
                    (identifier, i, photo.id, hashlib.sha256(photo.data).hexdigest(), cost),
                )
            db.execute("UPDATE gallery_orders SET state='sending' WHERE id=?", (identifier,))
        for i, photo in enumerate(photos):
            if not manager.current(job):
                break
            with manager.store.transaction() as db:
                if not db.execute(
                    "SELECT 1 FROM gallery_orders WHERE id=? AND state='sending'", (identifier,)
                ).fetchone():
                    break
                db.execute(
                    "UPDATE gallery_parts SET state='sending' WHERE order_id=? AND position=? AND state='pending'",
                    (identifier, i),
                )
            state, code, provider_id = "uncertain", "pack_uncertain", None
            try:
                manager.mark_provider(job)
                _, current_backend, current_chats = manager.gallery()
                if current_backend is not backend or row["chat"] not in current_chats:
                    raise MessageError("gallery_configuration_changed", False)
                provider_id = await backend.send_photo(
                    row["actor"], photo.data, photo.mime, view_once=True
                )
                if not isinstance(provider_id, str) or not provider_id:
                    raise ValueError("invalid_photo_ack")
                state, code = "accepted", None
            except MessageError as exc:
                state, code = ("uncertain" if exc.uncertain else "failed"), exc.code
            except MediaError as exc:
                state, code = "failed", exc.code
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE gallery_parts SET state=?,provider_message_id=?,error_code=? WHERE order_id=? AND position=?",
                    (state, provider_id, code, identifier, i),
                )
                if state in ("accepted", "uncertain"):
                    db.execute(
                        "INSERT OR IGNORE INTO gallery_seen VALUES(?,?)",
                        (row["wallet_id"], photo.id),
                    )
            if state != "accepted":
                break
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    finally:
        with manager.store.transaction() as db:
            finish(db, identifier, manager.clock())
    with manager.store.transaction() as db:
        result = summary(
            db, db.execute("SELECT * FROM gallery_orders WHERE id=?", (identifier,)).fetchone()
        )
    return EngineOutput(result)
