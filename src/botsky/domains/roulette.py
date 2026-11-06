"""Ruleta con reglas entregadas, apuestas propias y efecto de grupo reservado una vez."""

import asyncio
import re
import secrets
from uuid import uuid4

from .. import access
from ..contracts import Result
from . import economy as xp
from .blackjack import CHAT, chat_key


def room(db, identifier):
    return db.execute("SELECT * FROM roulette_rooms WHERE id=?", (identifier,)).fetchone()


def players(db, identifier):
    return db.execute(
        "SELECT * FROM roulette_players WHERE room_id=? ORDER BY wallet_id", (identifier,)
    ).fetchall()


def validated(info, group):
    if (
        not isinstance(info, dict)
        or info.get("group_id") != group
        or info.get("bot_is_admin") is not True
        or not isinstance(info.get("participants"), list)
        or len(info["participants"]) > 512
    ):
        raise ValueError("roulette_group_invalid")
    actors = set()
    targets = set()
    for p in info["participants"]:
        if (
            not isinstance(p, dict)
            or not all(isinstance(p.get(k), str) and p[k] for k in ("actor", "id"))
            or type(p.get("admin")) is not bool
            or p["actor"] in actors
            or p["id"] in targets
        ):
            raise ValueError("roulette_identity_conflict")
        actors.add(p["actor"])
        targets.add(p["id"])
    return info


def participant(info, actor, settings, allow_admins):
    member = next((p for p in info["participants"] if p["actor"] == actor), None)
    protected = {settings.owner, *settings.bot_ids}
    if (
        not member
        or actor in protected
        or member["id"] in protected
        or member["admin"]
        and not allow_admins
    ):
        raise ValueError("roulette_protected_or_absent")
    if not member["admin"] and (
        not isinstance(member.get("phone"), str)
        or not re.fullmatch(r"[0-9]{5,20}@s\.whatsapp\.net", member["phone"])
    ):
        raise ValueError("roulette_private_identity_required")
    return member


def settle(db, identifier, state, now):
    row = room(db, identifier)
    if not row or row["state"] in ("completed", "cancelled", "expired", "failed"):
        return
    if state == "uncertain":
        db.execute(
            "UPDATE roulette_rooms SET state='uncertain',effect_state='uncertain' WHERE id=?",
            (identifier,),
        )
        return
    ps = players(db, identifier)
    payout = sum(p["bet"] for p in ps) // max(1, len(ps) - 1)
    for p in ps:
        amount = (
            (0 if p["actor"] == row["target_actor"] else payout)
            if state == "completed"
            else p["bet"]
        )
        xp.release(
            db,
            p["wallet_id"],
            "roulette-" + identifier,
            amount,
            "roulette-settle-" + identifier,
            now,
            "roulette_settlement",
        )
    result = Result(
        "ok" if state == "completed" else "cancelled",
        "roulette_" + state,
        f"Ruleta {identifier}: {state}. "
        + (
            f"Cada sobreviviente recibe {payout} XP; efecto aceptado, sin recepción humana comprobada."
            if state == "completed"
            else "Apuestas devueltas una sola vez."
        ),
        {
            "room_id": identifier,
            "state": state,
            "payout_each": payout if state == "completed" else 0,
            "target": row["target_actor"] if state == "completed" else None,
        },
    )
    db.execute(
        "UPDATE roulette_rooms SET state=?,effect_state=?,result_json=?,return_due_ms=?,return_state=? WHERE id=?",
        (
            state,
            "accepted" if state == "completed" else "failed",
            result.to_json(),
            now + 1200000 if state == "completed" and row["action"] == "remove" else None,
            "pending" if state == "completed" and row["action"] == "remove" else None,
            identifier,
        ),
    )


def retire_job(db, receipt_id, now):
    for row in db.execute(
        "SELECT * FROM roulette_rooms WHERE play_receipt_id=?", (receipt_id,)
    ).fetchall():
        if row["state"] == "sending":
            settle(db, row["id"], "uncertain", now)
        elif row["state"] == "playing":
            settle(db, row["id"], "failed", now)
    db.execute(
        "UPDATE roulette_rooms SET return_state='uncertain' WHERE return_receipt_id=? AND return_state='sending'",
        (receipt_id,),
    )


def tick(db, settings, now):
    for row in db.execute(
        "SELECT * FROM roulette_rooms WHERE instance=? AND account=? AND epoch=? AND state='lobby' AND deadline_ms<=?",
        (settings.instance, settings.account, settings.epoch, now),
    ).fetchall():
        settle(db, row["id"], "expired", now)


def board(db, context, row, now):
    if row["result_json"]:
        return Result.from_json(row["result_json"])
    if row["state"] != "lobby":
        return Result(
            "uncertain" if row["state"] == "uncertain" else "ok",
            "roulette_status",
            "El efecto está pendiente; no se repite.",
            {"room_id": row["id"], "state": row["state"]},
        )
    ps = players(db, row["id"])
    rules = (
        f"Ruleta {row['id']} · {row['bet']} XP por persona ·2–6 participantes.\nUna persona elegida recibe expulsión de20min; si se permiten administradores, su degradación es permanente. Dueño/bots protegidos; administradores protegidos por defecto. El resto comparte el pozo redondeado hacia abajo. Para expulsión se enviará invitación por privado tras20min, sujeto a identidad/número verificados y privado disponible. Una entrega/acción incierta no se repite.\nAl escribir /ruleta entrar {row['id']} después de recibir estas reglas aceptas apuesta, efecto y aviso privado.\n/ruleta jugar {row['id']}\nAsientos: "
        + ", ".join("#" + str(p["wallet_id"]) for p in ps)
    )
    db.execute(
        "INSERT INTO roulette_views VALUES(?,?,?,NULL)",
        (context.receipt_id, row["id"], row["revision"]),
    )
    return Result(
        "ok",
        "roulette_board",
        rules,
        {
            "room_id": row["id"],
            "state": row["state"],
            "revision": row["revision"],
            "players": len(ps),
        },
    )


def execute(db, context, spec, args, now, app):
    if not context.scope.is_group or context.scope.chat not in app.roulette_chats:
        return Result(
            "failed",
            "roulette_group_not_configured",
            "La ruleta requiere un grupo explícitamente habilitado para esta función.",
        )
    tick(db, app.settings, now)
    if spec.original_action in ("status", "cancel"):
        query = "SELECT * FROM roulette_rooms WHERE " + CHAT
        params = list(chat_key(context))
        if args.get("room_id"):
            query += " AND id=?"
            params.append(args["room_id"])
        row = db.execute(query + " ORDER BY rowid DESC LIMIT 1", params).fetchone()
        if not row:
            return Result("empty", "roulette_not_found", "No hay una sala con ese ID aquí.")
        if spec.original_action == "cancel":
            if row["host"] != context.scope.actor:
                return Result("failed", "roulette_host_required", "Solo anfitrión cancela la sala.")
            if row["state"] != "lobby":
                return board(db, context, row, now)
            settle(db, row["id"], "cancelled", now)
            return Result.from_json(room(db, row["id"])["result_json"])
        return board(db, context, row, now)
    if app.groups is None or not getattr(app.groups, "available", False):
        return Result(
            "failed",
            "roulette_groups_not_configured",
            "No hay cliente propio de miembros/acciones configurado; no se retuvo XP.",
        )
    return app.jobs.reserve(
        db, context, spec.operation, args, [], now, resource="roulette-" + context.scope.chat
    )


def action(db, job, manager, info):
    if not manager.current(job):
        raise ValueError("job_retired")
    context = job["context"]
    args = job["arguments"]
    now = manager.clock()
    settings = manager.settings
    if access.authorize("friend", context, settings):
        raise ValueError("roulette_actor_denied")
    if job["operation"] == "manage_roulette.create":
        if db.execute(
            "SELECT 1 FROM roulette_rooms WHERE "
            + CHAT
            + " AND state IN ('lobby','playing','sending','uncertain')",
            chat_key(context),
        ).fetchone():
            return Result(
                "needs_input", "roulette_already_active", "Ya hay una ruleta pendiente aquí."
            )
        identifier = uuid4().hex
        db.execute(
            "INSERT INTO roulette_rooms(id,instance,account,chat,is_group,epoch,host,bet,deadline_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            (identifier, *chat_key(context), context.scope.actor, args["bet"], now + 120000),
        )
        return board(db, context, room(db, identifier), now)
    row = db.execute(
        "SELECT * FROM roulette_rooms WHERE id=? AND " + CHAT, (args["room_id"], *chat_key(context))
    ).fetchone()
    if not row:
        return Result("empty", "roulette_not_found", "No hay sala con ese ID en este grupo.")
    if row["state"] != "lobby":
        return board(db, context, row, now)
    if row["deadline_ms"] <= now:
        settle(db, row["id"], "expired", now)
        return Result.from_json(room(db, row["id"])["result_json"])
    source_ms = db.execute(
        "SELECT min(source_ms,received_ms) FROM inbox WHERE id=?", (job["id"],)
    ).fetchone()[0]
    if not db.execute(
        "SELECT 1 FROM roulette_views WHERE room_id=? AND revision=? AND accepted_ms IS NOT NULL AND accepted_ms<?",
        (row["id"], row["revision"], source_ms),
    ).fetchone():
        return Result(
            "needs_input",
            "roulette_rules_required",
            "Recibe las reglas y lista de asientos vigentes antes de aceptar o jugar.",
        )
    if job["operation"] == "manage_roulette.join":
        participant(info, context.scope.actor, settings, manager.roulette_policy()[1])
        own = xp.wallet(db, context)
        if db.execute(
            "SELECT 1 FROM roulette_players p JOIN roulette_rooms r ON p.room_id=r.id WHERE p.wallet_id=? AND r.state IN ('lobby','playing','sending','uncertain')",
            (own["id"],),
        ).fetchone():
            return Result(
                "failed",
                "roulette_already_staked",
                "Tu cuenta ya tiene una apuesta pendiente en ruleta.",
            )
        if len(players(db, row["id"])) >= 6 or own["balance"] < row["bet"]:
            return Result("failed", "roulette_join_unavailable", "Sala llena o saldo insuficiente.")
        try:
            xp.hold(
                db,
                own["id"],
                "roulette-" + row["id"],
                row["bet"],
                6 * row["bet"],
                job["id"],
                now,
                job["id"],
            )
        except ValueError:
            return Result("failed", "xp_headroom", "Falta margen protegido para el pago máximo.")
        db.execute(
            "INSERT INTO roulette_players VALUES(?,?,?,?,?)",
            (row["id"], own["id"], context.scope.actor, row["bet"], job["id"]),
        )
        db.execute("UPDATE roulette_rooms SET revision=revision+1 WHERE id=?", (row["id"],))
        return board(db, context, room(db, row["id"]), now)
    if context.scope.actor != row["host"]:
        return Result("failed", "roulette_host_required", "Solo anfitrión juega la sala.")
    ps = players(db, row["id"])
    if not 2 <= len(ps) <= 6:
        return Result("needs_input", "roulette_player_count", "Se necesitan2–6 apuestas aceptadas.")
    try:
        eligible = [
            participant(info, p["actor"], settings, manager.roulette_policy()[1]) for p in ps
        ]
    except ValueError:
        settle(db, row["id"], "cancelled", now)
        return Result.from_json(room(db, row["id"])["result_json"])
    chosen = (manager.roulette_policy()[2] or secrets.choice)(eligible)
    if chosen not in eligible:
        raise ValueError("roulette_invalid_choice")
    db.execute(
        "UPDATE roulette_rooms SET state='playing',target_actor=?,target_id=?,phone_id=?,action=?,effect_state='reserved',play_receipt_id=? WHERE id=?",
        (
            chosen["actor"],
            chosen["id"],
            chosen.get("phone"),
            "demote" if chosen["admin"] else "remove",
            job["id"],
            row["id"],
        ),
    )
    return None


async def run(job, directory, manager):
    from ..jobs import EngineOutput

    backend = manager.groups()
    chat = job["context"].scope.chat
    identifier = job["arguments"].get("room_id")
    dispatched = False
    try:
        if backend is None or chat not in manager.roulette_policy()[0]:
            raise ValueError("roulette_not_configured")
        info = validated(await backend.snapshot(chat), chat)
        if not manager.current(job):
            raise ValueError("job_retired")
        with manager.store.transaction() as db:
            result = action(db, job, manager, info)
        if result is not None:
            return EngineOutput(result)
        with manager.store.transaction() as db:
            row = room(db, identifier)
        link = None
        if row["action"] == "remove":
            link = await backend.invite_link(chat)
            if not isinstance(link, str) or not re.fullmatch(
                r"https://chat\.whatsapp\.com/[A-Za-z0-9_-]{10,128}", link
            ):
                raise ValueError("roulette_return_link_invalid")
        info = validated(await backend.snapshot(chat), chat)
        with manager.store.transaction() as db:
            row = room(db, identifier)
            if row["state"] != "playing" or not manager.current(job):
                raise ValueError("roulette_retired")
            for p in players(db, identifier):
                participant(info, p["actor"], manager.settings, manager.roulette_policy()[1])
            chosen = participant(
                info, row["target_actor"], manager.settings, manager.roulette_policy()[1]
            )
            if (
                chosen["id"] != row["target_id"]
                or chosen.get("phone") != row["phone_id"]
                or chosen["admin"] != (row["action"] == "demote")
            ):
                raise ValueError("roulette_target_changed")
            db.execute("UPDATE roulette_rooms SET invite_link=? WHERE id=?", (link, identifier))
        manager.mark_provider(job)
        with manager.store.transaction() as db:
            if not manager.current(job):
                raise ValueError("job_retired")
            db.execute(
                "UPDATE roulette_rooms SET state='sending',effect_state='sending' WHERE id=? AND state='playing'",
                (identifier,),
            )
        dispatched = True
        outcome = await backend.change(chat, row["action"], row["target_id"])
        state = (
            "completed"
            if outcome == "accepted"
            else "failed"
            if outcome == "failed"
            else "uncertain"
        )
        with manager.store.transaction() as db:
            settle(db, identifier, state, manager.clock())
    except asyncio.CancelledError:
        if identifier:
            with manager.store.transaction() as db:
                row = room(db, identifier)
                if row and row["play_receipt_id"] == job["id"]:
                    settle(db, identifier, "uncertain" if dispatched else "failed", manager.clock())
        raise
    except Exception:
        with manager.store.transaction() as db:
            row = room(db, identifier) if identifier else None
            if row and row["play_receipt_id"] == job["id"]:
                settle(db, identifier, "uncertain" if dispatched else "failed", manager.clock())
                result = (
                    Result.from_json(room(db, identifier)["result_json"])
                    if room(db, identifier)["result_json"]
                    else Result(
                        "uncertain",
                        "roulette_uncertain",
                        "El efecto quedó incierto; no se repite.",
                        {"room_id": identifier},
                    )
                )
            else:
                result = Result(
                    "failed",
                    "roulette_preflight_failed",
                    "No pude verificar miembros, identidad o permisos. No inicié un efecto de grupo.",
                )
        return EngineOutput(result)
    with manager.store.transaction() as db:
        row = room(db, identifier)
        result = (
            Result.from_json(row["result_json"])
            if row["result_json"]
            else Result(
                "uncertain",
                "roulette_uncertain",
                "Efecto incierto; apuestas retenidas, sin repetir.",
                {"room_id": identifier},
            )
        )
    return EngineOutput(result)
