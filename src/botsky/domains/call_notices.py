"""Avisos del journal portado a outbox propia, sin enviar ni remarcar llamadas."""

from .. import access
from ..adapters.calls import CallsError
from ..store import context_of
from .calls import permitted, validate_owned_call


async def poll(app):
    backend = app.calls
    if (
        backend is None
        or app.settings.calls is None
        or (app.settings.transport == "local" and not backend.is_fixture)
    ):
        return []
    now, emitted = app.clock(), []
    with app.store.transaction() as db:
        waiting = db.execute(
            "SELECT n.* FROM call_notices n JOIN call_bindings b ON n.receipt_id=b.receipt_id WHERE b.instance=? AND b.account=? AND n.state IN ('queued','ack_pending')",
            (app.settings.instance, app.settings.account),
        ).fetchall()
    for row in waiting:
        with app.store.transaction() as db:
            parts = db.execute(
                "SELECT state FROM outbox WHERE receipt_id=?", (row["delivery_receipt_id"],)
            ).fetchall()
            states = {p["state"] for p in parts}
            outcome = row["outcome"]
            if row["state"] == "queued":
                if states == {"accepted"}:
                    outcome = "accepted"
                elif "uncertain" in states:
                    outcome = "uncertain"
                elif "failed" in states:
                    outcome = "rejected"  # Explicit local retry remains an operator decision.
                elif "cancelled" in states:
                    outcome = "rejected"
                else:
                    continue
                db.execute(
                    "UPDATE call_notices SET state='ack_pending',outcome=?,updated_ms=? WHERE call_id=?",
                    (outcome, now, row["call_id"]),
                )
        try:
            await backend.ack_failure_notice(row["call_id"], row["lease"], outcome)
        except CallsError:
            continue
        with app.store.transaction() as db:
            db.execute(
                "UPDATE call_notices SET state='acknowledged',updated_ms=? WHERE call_id=?",
                (now, row["call_id"]),
            )
    try:
        notices = await backend.claim_failure_notices()
    except CallsError:
        return emitted
    for notice in notices:
        call_id, lease = notice["callId"], notice["lease"]
        try:
            remote = await backend.call_by_id(call_id)
            with app.store.transaction() as db:
                binding = db.execute(
                    "SELECT * FROM call_bindings WHERE receipt_id=?", (remote["key"],)
                ).fetchone()
                parent = db.execute("SELECT * FROM inbox WHERE id=?", (remote["key"],)).fetchone()
                prior = db.execute(
                    "SELECT 1 FROM call_notices WHERE call_id=?", (call_id,)
                ).fetchone()
            valid = bool(
                binding
                and parent
                and not prior
                and permitted(backend, app.settings, context_of(parent))
                and parent["message_id"] == notice["messageKey"]["id"]
                and parent["chat"] == notice["chatId"]
                and parent["actor"] == notice["requesterId"]
                and notice["messageKey"]["remoteJid"] == parent["chat"]
            )
            if valid:
                validate_owned_call(remote["call"], binding)
            if not await backend.begin_failure_notice(call_id, lease):
                continue
            if not valid:
                await backend.ack_failure_notice(call_id, lease, "rejected")
                continue
            with app.store.transaction() as db:
                # A crash before this commit leaves Node's notice uncertain, never resent.
                if access.authorize(
                    "call_authorized", context_of(parent), app.settings
                ) or not app.scheduler.allowed(db, parent, now):
                    identifier = None
                else:
                    identifier = app.scheduler.emit(
                        db,
                        {**dict(parent), "receipt_id": parent["id"]},
                        "call_failure",
                        ["call_failure", call_id],
                        "La llamada terminó con un fallo o una interrupción. /llamada estado muestra lo que se pudo confirmar; no se marcó otra por este aviso.",
                        now,
                    )
                    db.execute(
                        "UPDATE inbox SET permission='call_authorized' WHERE id=?", (identifier,)
                    )
                db.execute(
                    "INSERT INTO call_notices(call_id,receipt_id,delivery_receipt_id,lease,state,outcome,updated_ms) VALUES(?,?,?,?,?,?,?)",
                    (
                        call_id,
                        parent["id"],
                        identifier,
                        lease,
                        "queued" if identifier else "ack_pending",
                        None if identifier else "rejected",
                        now,
                    ),
                )
                if identifier:
                    emitted.append(identifier)
        except CallsError:
            continue
    return emitted
