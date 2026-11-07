"""Modos explícitos del chat; nunca habilitan conversación espontánea."""

from ..contracts import Result
from ..jobs import cancel_job


def key(context):
    return (
        context.instance,
        context.account,
        context.scope.chat,
        int(context.scope.is_group),
        context.epoch,
    )


def current(db, context):
    row = db.execute(
        "SELECT mode,paused_until_ms,revision FROM chat_modes WHERE instance=? AND account=? AND chat=? AND is_group=? AND epoch=?",
        key(context),
    ).fetchone()
    return dict(row) if row else {"mode": "discreto", "paused_until_ms": 0, "revision": 0}


def gate(db, context, spec, now):
    if (
        spec.family == "manage_conversation"
        or spec.family == "core"
        and spec.original_action in ("help", "estado", "cancelar")
    ):
        return None
    state = current(db, context)
    if state["mode"] == "apagado":
        return Result(
            "failed",
            "bot_disabled",
            "Botsky está apagado en este chat. El dueño puede usar /bot reanudar.",
        )
    if state["paused_until_ms"] > now:
        return Result(
            "failed",
            "bot_paused",
            "Botsky está en pausa en este chat. El dueño puede usar /bot reanudar.",
        )
    return None


def execute(db, context, action, args, now, capabilities):
    state = current(db, context)
    if action == "status":
        active = [name for name, available in capabilities.items() if available]
        return Result(
            "ok",
            "bot_status",
            f"Modo: {state['mode']}. "
            + ("En pausa. " if state["paused_until_ms"] > now else "")
            + "Capacidades locales/configuradas: "
            + ", ".join(active)
            + ".",
            {
                "mode": state["mode"],
                "paused_until_ms": state["paused_until_ms"],
                "capabilities": capabilities,
            },
        )
    mode, paused = state["mode"], state["paused_until_ms"]
    if action == "mode":
        mode = args["mode"]
    elif action == "pause":
        paused = now + int(args["minutes"]) * 60000
    elif action == "resume":
        mode, paused = ("discreto" if mode == "apagado" else mode), 0
    else:
        return Result("failed", "unsupported_bot_action", "Acción de control no disponible.")
    db.execute(
        "INSERT INTO chat_modes VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(instance,account,chat,is_group,epoch) DO UPDATE SET mode=excluded.mode,paused_until_ms=excluded.paused_until_ms,revision=chat_modes.revision+1",
        (*key(context), mode, paused),
    )
    if mode == "apagado" or paused > now:
        pending = db.execute("SELECT i.id FROM inbox i JOIN frontend_tasks f ON f.receipt_id=i.id WHERE i.instance=? AND i.account=? AND i.chat=? AND i.is_group=? AND i.epoch=? AND f.state IN ('pending','running')", key(context)).fetchall()
        for item in pending:
            db.execute("UPDATE frontend_tasks SET state='cancelled',updated_ms=? WHERE receipt_id=?", (now, item['id']))
            db.execute("UPDATE inbox SET state='cancelled',revision=revision+1 WHERE id=? AND state='queued'", (item['id'],))
        rows = db.execute(
            "SELECT j.id FROM jobs j JOIN inbox i ON j.id=i.id WHERE i.instance=? AND i.account=? AND i.chat=? AND i.is_group=? AND i.epoch=? AND j.state IN ('queued','running') UNION SELECT receipt_id AS id FROM interactions WHERE instance=? AND account=? AND chat=? AND is_group=? AND epoch=? AND state IN ('active','pending_delivery')",
            (*key(context), *key(context)),
        ).fetchall()
        for row in rows:
            cancel_job(db, context, row["id"])
    return Result(
        "ok",
        "bot_mode_updated",
        "Modo " + mode + ". " + ("Pausa activada." if paused > now else "Sin pausa."),
        {"mode": mode, "paused_until_ms": paused},
    )
