"""No publicar un tablero/reto retirado; hooks explícitos para dominios R7."""

from . import blackjack, happy_hour


def retired(db, receipt_id, settings, now):
    nuclear = db.execute(
        "SELECT * FROM nuclear_drafts WHERE preview_receipt_id=?", (receipt_id,)
    ).fetchone()
    if nuclear and (nuclear["state"] != "pending" or nuclear["expires_ms"] <= now):
        return True
    from .cooperacha import expire

    expire(db, settings, now)
    from .roulette import room
    from .roulette import tick as tick_roulette

    tick_roulette(db, settings, now)
    roulette = db.execute(
        "SELECT * FROM roulette_views WHERE receipt_id=?", (receipt_id,)
    ).fetchone()
    if roulette:
        current = room(db, roulette["room_id"])
        if current["state"] != "lobby" or current["revision"] != roulette["revision"]:
            return True
    coop = db.execute(
        "SELECT state FROM cooperachas WHERE preview_receipt_id=?", (receipt_id,)
    ).fetchone()
    if coop and coop["state"] != "publishing":
        return True
    view = db.execute(
        "SELECT v.revision,g.* FROM game_views v JOIN blackjack_games g ON v.game_id=g.id WHERE v.receipt_id=?",
        (receipt_id,),
    ).fetchone()
    if view:
        blackjack.tick(db, now, settings)
        current = blackjack.game(db, view["id"])
        if current["revision"] != view["revision"] or current["state"] not in ("lobby", "playing"):
            return True
    event = db.execute(
        "SELECT e.*,i.received_ms FROM happy_events e JOIN inbox i ON e.receipt_id=i.id WHERE e.receipt_id=?",
        (receipt_id,),
    ).fetchone()
    if event:
        happy_hour.expire(db, now, settings)
        if event["state"] == "closed" or event["received_ms"] + 300000 <= now:
            return True
    drop = db.execute(
        "SELECT d.state,e.state AS event_state,e.expires_ms FROM happy_drops d JOIN happy_events e ON e.id=d.event_id WHERE d.receipt_id=?",
        (receipt_id,),
    ).fetchone()
    return bool(
        drop
        and (
            drop["state"] == "closed"
            or drop["event_state"] != "active"
            or drop["expires_ms"] <= now
        )
    )
