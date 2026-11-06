"""XP propio global por identidad verificada/época; ledger y reservas en la misma tx."""

import secrets

from ..contracts import Result

MAX_BALANCE = 9007199254740991
DAY = 86400000


def wallet(db, context, actor=None):
    key = (context.instance, context.account, actor or context.scope.actor, context.epoch)
    db.execute("INSERT OR IGNORE INTO wallets(instance,account,actor,epoch) VALUES(?,?,?,?)", key)
    return db.execute(
        "SELECT * FROM wallets WHERE instance=? AND account=? AND actor=? AND epoch=?", key
    ).fetchone()


def move(db, identifier, amount, event, kind, now, receipt=None, *, release=0, reserve=0):
    if (
        type(amount) is not int
        or type(reserve) is not int
        or type(release) is not int
        or reserve < 0
        or release < 0
    ):
        raise ValueError("invalid_xp_amount")
    prior = db.execute(
        "SELECT 1 FROM xp_entries WHERE event_key=? AND wallet_id=?", (event, identifier)
    ).fetchone()
    if prior:
        return False
    row = db.execute("SELECT * FROM wallets WHERE id=?", (identifier,)).fetchone()
    balance = row["balance"] + amount
    held = row["reserved"] - release + reserve
    if not 0 <= balance <= MAX_BALANCE or not 0 <= held or balance + held > MAX_BALANCE:
        raise ValueError("xp_funds_or_headroom")
    db.execute("UPDATE wallets SET balance=?,reserved=? WHERE id=?", (balance, held, identifier))
    db.execute(
        "INSERT INTO xp_entries VALUES(?,?,?,?,?,?,?)",
        (event, identifier, kind, amount, balance, receipt, now),
    )
    return True


def hold(db, identifier, resource, amount, room, event, now, receipt=None):
    move(db, identifier, -amount, event, "stake", now, receipt, reserve=room)
    db.execute("INSERT INTO xp_holds VALUES(?,?,?)", (resource, identifier, room))


def release(db, identifier, resource, amount, event, now, kind="payout"):
    row = db.execute(
        "SELECT amount FROM xp_holds WHERE resource=? AND wallet_id=?", (resource, identifier)
    ).fetchone()
    if not row:
        return False
    move(db, identifier, amount, event, kind, now, release=row["amount"])
    db.execute("DELETE FROM xp_holds WHERE resource=? AND wallet_id=?", (resource, identifier))
    return True


def prize(draw):
    if type(draw) is not int or not 1 <= draw <= 100:
        raise ValueError("invalid_daily_draw")
    return next(
        amount
        for upper, amount in ((3, 1000), (15, 300), (50, 100), (85, 40), (95, 15), (100, 0))
        if draw <= upper
    )


def execute(db, context, action, now, rng=None):
    own = wallet(db, context)
    if action == "top":
        rows = [
            {
                "account_id": r["id"],
                "balance": r["balance"],
                "level": r["balance"] // 20 + 1,
                "self": r["id"] == own["id"],
            }
            for r in db.execute(
                "SELECT * FROM wallets WHERE instance=? AND account=? AND epoch=? ORDER BY balance DESC,id LIMIT 10",
                (context.instance, context.account, context.epoch),
            )
        ]
        return Result(
            "ok",
            "xp_top",
            "Top XP:\n"
            + "\n".join(
                f"{i}. {'Tú' if r['self'] else 'Jugador'} · cuenta #{r['account_id']} · {r['balance']} XP"
                for i, r in enumerate(rows, 1)
            ),
            {"items": rows},
        )
    data = {
        "account_id": own["id"],
        "balance": own["balance"],
        "reserved": own["reserved"],
        "level": own["balance"] // 20 + 1,
    }
    if action == "daily":
        last = own["last_daily_ms"]
        if last is not None and now - last < DAY:
            return Result(
                "ok",
                "daily_cooldown",
                "Daily ya reclamado; consulta el próximo instante en el resultado.",
                {**data, "retry_at_ms": last + DAY, "streak": own["streak"]},
            )
        base = prize((rng or (lambda: secrets.randbelow(100) + 1))())
        streak = own["streak"] + 1 if last is not None and now - last <= 2 * DAY else 1
        gained = base + (min((streak - 1) * 20, 100) if base else 0)
        try:
            move(db, own["id"], gained, context.receipt_id, "daily", now, context.receipt_id)
        except ValueError:
            return Result(
                "failed",
                "xp_limit",
                "El premio excedería el límite de tu cuenta y sus reservas; no se consumió daily.",
            )
        db.execute(
            "UPDATE wallets SET last_daily_ms=?,streak=? WHERE id=?", (now, streak, own["id"])
        )
        data.update(
            balance=own["balance"] + gained,
            level=(own["balance"] + gained) // 20 + 1,
            gained=gained,
            streak=streak,
            retry_at_ms=now + DAY,
        )
        return Result(
            "ok",
            "daily_awarded",
            f"Daily: +{gained} XP. Racha {streak}. Saldo {data['balance']} XP.",
            data,
        )
    return Result(
        "ok",
        "xp_balance",
        f"Cuenta #{own['id']}: {own['balance']} XP · nivel {data['level']}. Reservas de pago: {own['reserved']} XP. Cuenta compartida entre tus chats de Botsky.",
        data,
    )


def credit_message(db, context, incoming, now):
    if (
        not incoming.scope.is_group
        or not incoming.text.strip()
        and not incoming.attachments
        or incoming.text.lstrip().startswith(("!", ".", "/"))
    ):
        return
    own = wallet(db, context)
    from .happy_hour import active

    event = active(db, context, now, incoming.source_ms)
    try:
        move(
            db,
            own["id"],
            20 if event else 1,
            "message-" + context.receipt_id,
            "message",
            now,
            context.receipt_id,
        )
        if event:
            db.execute("UPDATE happy_events SET activity=activity+1 WHERE id=?", (event["id"],))
    except ValueError:
        pass
