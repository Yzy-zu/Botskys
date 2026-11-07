"""Administración de dueño; objetivos verificados y efectos remotos fuera de SQLite."""

from .. import access
from ..contracts import Result, canonical
from . import economy as xp


def scope(context):
    return (context.instance, context.account, context.scope.chat, context.epoch)


SCOPE = "instance=? AND account=? AND chat=? AND epoch=?"


def target(info, identifier):
    found = [
        p
        for p in info["participants"]
        if identifier in {p["id"], p["actor"], *p.get("aliases", [])}
    ]
    if len(found) != 1:
        raise ValueError("admin_target_unverified")
    return found[0]


def execute(db, context, spec, args, now, app):
    if not context.scope.is_group:
        return Result(
            "failed",
            "admin_group_required",
            "La administración requiere grupo habilitado e identidad de dueño.",
        )
    action = spec.original_action
    if action.startswith("nuclear_"):
        from . import nuclear

        return nuclear.execute(db, context, spec, args, now, app)
    if app.groups is None or not app.groups.available:
        return Result(
            "failed",
            "admin_groups_not_configured",
            "No hay cliente propio de miembros configurado.",
        )
    if (
        action != "warnings"
        and db.execute(
            "SELECT 1 FROM external_operations WHERE domain='admin' AND resource=? AND state IN ('reserved','sending','uncertain')",
            (context.scope.chat,),
        ).fetchone()
    ):
        return Result(
            "needs_input",
            "admin_operation_pending",
            "Hay una operación administrativa pendiente o incierta en este grupo; consulta su recibo antes de otra mutación.",
        )
    queued = app.jobs.reserve(
        db, context, spec.operation, args, [], now, resource="admin-" + context.scope.chat
    )
    if queued.code == "job_queued":
        db.execute(
            "INSERT INTO external_operations(receipt_id,domain,resource,action,args_json) VALUES(?,?,?,?,?)",
            (
                context.receipt_id,
                "admin",
                context.scope.chat if action != "warnings" else "read-" + context.receipt_id,
                action,
                canonical(args),
            ),
        )
    return queued


def retire_job(db, receipt_id, now):
    from .nuclear import retire_job as retire_nuclear

    retire_nuclear(db, receipt_id, now)
    db.execute(
        "UPDATE external_operations SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END WHERE receipt_id=? AND state IN ('reserved','sending')",
        (receipt_id,),
    )


def local(db, job, manager, info):
    context = job["context"]
    args = job["arguments"]
    action = job["operation"].split(".")[-1]
    if not manager.current(job) or access.authorize("owner", context, manager.settings):
        raise ValueError("admin_owner_required")
    actor = next(
        (
            p
            for p in info["participants"]
            if context.scope.actor in {p["actor"], p["id"], *p.get("aliases", [])}
        ),
        None,
    )
    if not actor or (
        action in ("kick", "ban", "promote", "demote", "mute", "unmute", "lock", "unlock")
        and (actor["admin"] is not True or info["bot_is_admin"] is not True)
    ):
        raise ValueError("admin_current_permissions_required")
    if action == "unban":
        changed = db.execute(
            "UPDATE admin_bans SET state=? WHERE "
            + SCOPE
            + " AND state='active' AND (target=? OR EXISTS(SELECT 1 FROM json_each(aliases_json) WHERE value=?))",
            ("revoked", *scope(context), args["target"], args["target"]),
        ).rowcount
        return Result(
            "ok" if changed else "empty",
            "admin_unban",
            "Bloqueo retirado del registro local; no se reincorporó a nadie.",
        ), None
    member = None
    if args.get("target"):
        member = target(info, args["target"])
    if action in ("xp_grant", "xp_remove"):
        if args.get("account_id"):
            own = db.execute(
                "SELECT * FROM wallets WHERE id=? AND instance=? AND account=? AND epoch=?",
                (args["account_id"], context.instance, context.account, context.epoch),
            ).fetchone()
            if not own or not any(p["actor"] == own["actor"] for p in info["participants"]):
                raise ValueError("admin_account_unverified")
        else:
            own = xp.wallet(db, context, member["actor"])
        try:
            xp.move(
                db,
                own["id"],
                args["amount"] if action == "xp_grant" else -args["amount"],
                job["id"],
                "admin_" + action,
                manager.clock(),
                job["id"],
            )
        except ValueError:
            return Result(
                "failed", "admin_xp_limit", "Saldo o margen insuficientes; no se modificó XP."
            ), None
        return Result(
            "ok",
            "admin_xp_changed",
            f"Cuenta #{own['id']}: ajuste {'+' if action == 'xp_grant' else '-'}{args['amount']} XP.",
        ), None
    if action in ("warn", "unwarn", "warnings"):
        selected = member["id"] if member else actor["id"]
        if action == "warn":
            cursor = db.execute(
                "INSERT INTO admin_warnings(instance,account,chat,epoch,target,receipt_id) VALUES(?,?,?,?,?,?)",
                (*scope(context), selected, job["id"]),
            )
            return Result(
                "ok",
                "admin_warning_added",
                f"Aviso #{cursor.lastrowid} guardado. No se expulsó a nadie.",
                {"warning_id": cursor.lastrowid},
            ), None
        if action == "unwarn":
            changed = db.execute(
                "UPDATE admin_warnings SET state=? WHERE id=? AND "
                + SCOPE
                + " AND target=? AND state='active'",
                ("revoked", args["warning_id"], *scope(context), selected),
            ).rowcount
            return Result(
                "ok" if changed else "empty",
                "admin_warning_revoked",
                "Aviso retirado." if changed else "No hay ese aviso activo para esa persona aquí.",
            ), None
        items = [
            {"warning_id": r["id"]}
            for r in db.execute(
                "SELECT * FROM admin_warnings WHERE "
                + SCOPE
                + " AND target=? AND state='active' ORDER BY id LIMIT 100",
                (*scope(context), selected),
            )
        ]
        return Result(
            "ok" if items else "empty",
            "admin_warnings",
            "Avisos activos: " + ", ".join(str(i["warning_id"]) for i in items),
            {"items": items},
        ), None
    if action in ("kick", "ban", "promote", "demote"):
        if (
            member["actor"] in {manager.settings.owner, *manager.settings.bot_ids}
            or member["id"] in manager.settings.bot_ids
        ):
            raise ValueError("admin_protected_target")
        if action in ("kick", "ban") and member["admin"]:
            raise ValueError("admin_protected_admin")
        return None, member
    return None, None


async def run(job, directory, manager):
    from ..jobs import EngineOutput
    from .roulette import validated

    backend = manager.groups()
    context = job["context"]
    action = job["operation"].split(".")[-1]
    dispatched = False
    try:
        with manager.store.transaction() as db:
            prior = db.execute(
                "SELECT * FROM external_operations WHERE receipt_id=?", (job["id"],)
            ).fetchone()
            if prior and prior["result_json"] and prior["state"] in ("completed", "failed"):
                return EngineOutput(Result.from_json(prior["result_json"]))
        if backend is None:
            raise ValueError("admin_not_configured")
        info = validated(
            await backend.snapshot(context.scope.chat), context.scope.chat, require_admin=False
        )
        with manager.store.transaction() as db:
            result, member = local(db, job, manager, info)
            if result is not None:
                db.execute(
                    "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
                    (
                        "completed" if result.status in ("ok", "empty") else "failed",
                        result.to_json(),
                        job["id"],
                    ),
                )
        if result is None:
            # Segunda instantánea antes de una mutación irreversible.
            fresh = validated(await backend.snapshot(context.scope.chat), context.scope.chat)
            with manager.store.transaction() as db:
                _, verified = local(db, job, manager, fresh)
                if member and (
                    verified is None
                    or member["id"] != verified["id"]
                    or member["actor"] != verified["actor"]
                    or member["admin"] != verified["admin"]
                ):
                    raise ValueError("admin_target_changed")
            manager.mark_provider(job)
            with manager.store.transaction() as db:
                if not manager.current(job):
                    raise ValueError("job_retired")
                db.execute(
                    "UPDATE external_operations SET state='sending' WHERE receipt_id=? AND state='reserved'",
                    (job["id"],),
                )
                if action == "ban":
                    db.execute(
                        "INSERT INTO admin_bans VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(instance,account,chat,epoch,target) DO UPDATE SET receipt_id=excluded.receipt_id,state=excluded.state,aliases_json=excluded.aliases_json",
                        (
                            *scope(context),
                            member["id"],
                            job["id"],
                            "active",
                            canonical(
                                sorted({member["id"], member["actor"], *member.get("aliases", [])})
                            ),
                        ),
                    )
            dispatched = True
            if action in ("mute", "unmute", "lock", "unlock"):
                outcome = await backend.setting(
                    context.scope.chat,
                    "announcement" if action in ("mute", "unmute") else "locked",
                    action in ("mute", "lock"),
                )
            else:
                outcome = await backend.change(
                    context.scope.chat,
                    "remove" if action in ("kick", "ban") else action,
                    member["id"],
                )
            state = (
                "completed"
                if outcome == "accepted"
                else "failed"
                if outcome == "failed"
                else "uncertain"
            )
            result = Result(
                "ok" if state == "completed" else "failed" if state == "failed" else "uncertain",
                "admin_" + state,
                "Acción administrativa: " + state + ". Una acción incierta no se repetirá.",
                {
                    "action": action,
                    "target_label": "Participante verificado del comando"
                    if member
                    else "Este grupo",
                },
            )
            if action == "ban" and state == "failed":
                with manager.store.transaction() as db:
                    db.execute(
                        "UPDATE admin_bans SET state='revoked' WHERE receipt_id=?", (job["id"],)
                    )

        else:
            state = "completed" if result.status in ("ok", "empty") else "failed"
    except BaseException as exc:
        unknown = dispatched and getattr(exc, "uncertain", True) is not False
        state = "uncertain" if unknown else "failed"
        result = Result(
            "uncertain" if unknown else "failed",
            "admin_" + state,
            "No pude verificar la operación administrativa. "
            + ("No la repetiré." if unknown else "No se despachó una mutación."),
        )
        with manager.store.transaction() as db:
            if action == "ban" and not unknown:
                db.execute("UPDATE admin_bans SET state='revoked' WHERE receipt_id=?", (job["id"],))
            db.execute(
                "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
                (state, result.to_json(), job["id"]),
            )
        if not isinstance(exc, Exception):
            raise
    with manager.store.transaction() as db:
        db.execute(
            "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
            (state, result.to_json(), job["id"]),
        )
    return EngineOutput(result)
