"""Nuclear optativo: snapshot y preview completos, coste único y partes sin repetición."""

from uuid import uuid4

from .. import access
from ..contracts import Result, canonical
from . import economy as xp
from .notes import SCOPE_SQL


def summary(db, row):
    counts = {
        r["state"]: r["n"]
        for r in db.execute(
            "SELECT state,count(*) AS n FROM nuclear_targets WHERE draft_id=? GROUP BY state",
            (row["id"],),
        )
    }
    return Result(
        "uncertain" if counts.get("uncertain") else "ok",
        "nuclear_status",
        f"Nuclear {row['id']}: {row['state']} · coste {row['cost']} XP. "
        + ", ".join(f"{k}: {v}" for k, v in counts.items()),
        {"draft_id": row["id"], "state": row["state"], "counts": counts, "cost": row["cost"]},
    )


def settle(db, identifier, now):
    row = db.execute("SELECT * FROM nuclear_drafts WHERE id=?", (identifier,)).fetchone()
    if not row:
        return
    db.execute(
        "UPDATE nuclear_targets SET state='uncertain' WHERE draft_id=? AND state='sending'",
        (identifier,),
    )
    db.execute(
        "UPDATE nuclear_targets SET state='skipped' WHERE draft_id=? AND state='pending'",
        (identifier,),
    )
    counts = {
        r["state"]: r["n"]
        for r in db.execute(
            "SELECT state,count(*) AS n FROM nuclear_targets WHERE draft_id=? GROUP BY state",
            (identifier,),
        )
    }
    accepted, uncertain = counts.get("accepted", 0), counts.get("uncertain", 0)
    state = (
        "uncertain"
        if uncertain
        else "completed"
        if accepted == sum(counts.values()) and accepted
        else "partial"
        if accepted
        else "cancelled"
    )
    if row["wallet_id"] is not None:
        xp.release(
            db,
            row["wallet_id"],
            "nuclear-" + identifier,
            0 if accepted or uncertain else row["cost"],
            "nuclear-settle-" + identifier,
            now,
            "nuclear_settlement",
        )
    db.execute("UPDATE nuclear_drafts SET state=? WHERE id=?", (state, identifier))
    result = summary(
        db, db.execute("SELECT * FROM nuclear_drafts WHERE id=?", (identifier,)).fetchone()
    )
    if row["confirm_receipt_id"]:
        db.execute(
            "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
            (
                "uncertain" if uncertain else "completed" if accepted else "failed",
                result.to_json(),
                row["confirm_receipt_id"],
            ),
        )


def retire_job(db, receipt_id, now):
    operation = db.execute(
        "SELECT * FROM external_operations WHERE receipt_id=?", (receipt_id,)
    ).fetchone()
    if not operation or operation["state"] not in ("reserved", "sending"):
        return
    for row in db.execute(
        "SELECT * FROM nuclear_drafts WHERE confirm_receipt_id=?", (receipt_id,)
    ).fetchall():
        settle(db, row["id"], now)


def execute(db, context, spec, args, now, app):
    action = spec.original_action
    if action != "nuclear_prepare":
        row = db.execute(
            f"SELECT * FROM nuclear_drafts WHERE id=? AND {SCOPE_SQL}",
            (args["draft_id"], *context.scope_key),
        ).fetchone()
        if not row:
            return Result(
                "empty",
                "nuclear_not_found",
                "No hay un borrador nuclear propio con ese ID en este grupo.",
            )
        if action == "nuclear_cancel":
            settle(db, row["id"], now)
            db.execute("UPDATE interactions SET state='cancelled' WHERE id=?", (row["id"],))
            return summary(
                db, db.execute("SELECT * FROM nuclear_drafts WHERE id=?", (row["id"],)).fetchone()
            )
        if row["state"] != "pending":
            return summary(db, row)
        if not app.nuclear_enabled:
            return Result(
                "failed",
                "nuclear_disabled",
                "La ejecución nuclear está deshabilitada; no hubo cargo ni expulsiones.",
            )
        view = db.execute(
            "SELECT 1 FROM interactions WHERE id=? AND kind='nuclear' AND state='active' AND expires_ms>?",
            (row["id"], now),
        ).fetchone()
        stamp = db.execute(
            "SELECT max(updated_ms) AS stamp,sum(state!='accepted') AS pending FROM outbox WHERE receipt_id=?",
            (row["preview_receipt_id"],),
        ).fetchone()
        source = db.execute(
            "SELECT min(source_ms,received_ms) FROM inbox WHERE id=?", (context.receipt_id,)
        ).fetchone()[0]
        if not view or row["expires_ms"] <= now or stamp["pending"] or source <= stamp["stamp"]:
            return Result(
                "needs_input",
                "nuclear_preview_required",
                "Recibe la vista propia completa vigente y después confirma su ID.",
            )
    if app.groups is None or not app.groups.available:
        return Result(
            "failed", "admin_groups_not_configured", "No hay cliente propio de grupos configurado."
        )
    if db.execute(
        "SELECT 1 FROM external_operations WHERE domain='admin' AND resource=? AND state IN ('reserved','sending','uncertain')",
        (context.scope.chat,),
    ).fetchone():
        return Result(
            "needs_input",
            "admin_operation_pending",
            "Hay una operación pendiente o incierta que debe revisarse primero.",
        )
    result = app.jobs.reserve(
        db, context, spec.operation, args, [], now, resource="admin-" + context.scope.chat
    )
    if result.code == "job_queued":
        db.execute(
            "INSERT INTO external_operations(receipt_id,domain,resource,action,args_json) VALUES(?,?,?,?,?)",
            (context.receipt_id, "admin", context.scope.chat, action, canonical(args)),
        )
        if action == "nuclear_confirm":
            db.execute(
                "UPDATE nuclear_drafts SET state='queued',confirm_receipt_id=? WHERE id=?",
                (context.receipt_id, row["id"]),
            )
    return result


def snapshot(info, context, settings):
    from .roulette import validated

    validated(info, context.scope.chat)
    owner = [
        p
        for p in info["participants"]
        if context.scope.actor in {p["actor"], p["id"], *p.get("aliases", [])}
    ]
    if len(owner) != 1 or owner[0]["admin"] is not True:
        raise ValueError("nuclear_owner_role_required")
    protected = {settings.owner, *settings.bot_ids}
    return [
        p
        for p in info["participants"]
        if p["admin"] is False and not protected & {p["actor"], p["id"], *p.get("aliases", [])}
    ]


async def run(job, directory, manager):
    from ..jobs import EngineOutput

    context = job["context"]
    backend = manager.groups()
    identifier = job["arguments"].get("draft_id")
    now = manager.clock()
    if job["operation"].endswith("nuclear_prepare"):
        try:
            with manager.store.transaction() as db:
                prior = db.execute(
                    "SELECT result_json FROM external_operations WHERE receipt_id=?", (job["id"],)
                ).fetchone()
                if prior["result_json"]:
                    return EngineOutput(Result.from_json(prior["result_json"]))
            eligible = snapshot(
                await backend.snapshot(context.scope.chat), context, manager.settings
            )
            if not eligible:
                raise ValueError("nuclear_empty")
            identifier = uuid4().hex
            with manager.store.transaction() as db:
                if not manager.current(job) or access.authorize("owner", context, manager.settings):
                    raise ValueError("nuclear_retired")
                db.execute(
                    "INSERT INTO nuclear_drafts(id,instance,account,actor,chat,is_group,epoch,preview_receipt_id,expires_ms) VALUES(?,?,?,?,?,?,?,?,?)",
                    (identifier, *context.scope_key, job["id"], now + 300000),
                )
                for i, p in enumerate(eligible):
                    db.execute(
                        "INSERT INTO nuclear_targets(draft_id,position,target_id,target_actor) VALUES(?,?,?,?)",
                        (identifier, i, p["id"], p["actor"]),
                    )
                db.execute(
                    "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,'{}','[]',?,'pending_delivery',?)",
                    (
                        identifier,
                        job["id"],
                        *context.scope_key,
                        "nuclear",
                        canonical({"draft_id": identifier}),
                        now + 300000,
                    ),
                )
                result = Result(
                    "needs_input",
                    "nuclear_preview",
                    f"Nuclear {identifier}: {len(eligible)} miembros no administradores elegibles. Coste5000 XP si se confirma. Dueño/bots/admins protegidos. Sin cargo ni expulsiones todavía. Caduca en5min.\n/admin nuclear-confirmar {identifier}\n/admin nuclear-cancelar {identifier}",
                    {"draft_id": identifier, "count": len(eligible), "cost": 5000},
                )
                db.execute(
                    "UPDATE external_operations SET state='completed',result_json=? WHERE receipt_id=?",
                    (result.to_json(), job["id"]),
                )
            return EngineOutput(result)
        except Exception:
            return EngineOutput(
                Result(
                    "failed",
                    "nuclear_preview_failed",
                    "No pude comprobar una vista nuclear propia; no hubo cargo ni acción.",
                )
            )
    try:
        eligible = snapshot(await backend.snapshot(context.scope.chat), context, manager.settings)
        with manager.store.transaction() as db:
            row = db.execute("SELECT * FROM nuclear_drafts WHERE id=?", (identifier,)).fetchone()
            targets = db.execute(
                "SELECT * FROM nuclear_targets WHERE draft_id=? ORDER BY position", (identifier,)
            ).fetchall()
            if (
                row["state"] != "queued"
                or row["expires_ms"] <= manager.clock()
                or not manager.current(job)
                or access.authorize("owner", context, manager.settings)
                or not manager.nuclear_enabled()
            ):
                raise ValueError("nuclear_retired")
            for t in targets:
                if not any(
                    p["id"] == t["target_id"] and p["actor"] == t["target_actor"] for p in eligible
                ):
                    raise ValueError("nuclear_snapshot_changed")
            own = xp.wallet(db, context)
            xp.hold(
                db,
                own["id"],
                "nuclear-" + identifier,
                row["cost"],
                row["cost"],
                "nuclear-charge-" + identifier,
                now,
                job["id"],
            )
            db.execute(
                "UPDATE nuclear_drafts SET state='running',wallet_id=? WHERE id=?",
                (own["id"], identifier),
            )
        for t in targets:
            if not manager.nuclear_enabled():
                break
            eligible = snapshot(
                await backend.snapshot(context.scope.chat), context, manager.settings
            )
            if not any(
                p["id"] == t["target_id"] and p["actor"] == t["target_actor"] for p in eligible
            ):
                break
            manager.mark_provider(job)
            with manager.store.transaction() as db:
                if not manager.current(job):
                    break
                changed = db.execute(
                    "UPDATE nuclear_targets SET state='sending' WHERE draft_id=? AND position=? AND state='pending'",
                    (identifier, t["position"]),
                ).rowcount
                if changed != 1:
                    break
                db.execute(
                    "UPDATE external_operations SET state='sending' WHERE receipt_id=?",
                    (job["id"],),
                )
            outcome = await backend.change(context.scope.chat, "remove", t["target_id"])
            state = (
                "accepted"
                if outcome == "accepted"
                else "failed"
                if outcome == "failed"
                else "uncertain"
            )
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE nuclear_targets SET state=? WHERE draft_id=? AND position=?",
                    (state, identifier, t["position"]),
                )
            if state == "uncertain":
                break
    except BaseException as exc:
        if isinstance(exc, Exception) and getattr(exc, "uncertain", True) is False:
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE nuclear_targets SET state='failed' WHERE draft_id=? AND state='sending'",
                    (identifier,),
                )
        with manager.store.transaction() as db:
            settle(db, identifier, manager.clock())
        if not isinstance(exc, Exception):
            raise
    with manager.store.transaction() as db:
        settle(db, identifier, manager.clock())
        result = summary(
            db, db.execute("SELECT * FROM nuclear_drafts WHERE id=?", (identifier,)).fetchone()
        )
    return EngineOutput(result)
