"""Blackjack local con baraja persistida, turnos publicados y liquidación única."""

import json
import random
from uuid import uuid4

from ..contracts import Result, canonical
from . import economy as xp

CHAT = "instance=? AND account=? AND chat=? AND is_group=? AND epoch=?"


def chat_key(context):
    return (
        context.instance,
        context.account,
        context.scope.chat,
        int(context.scope.is_group),
        context.epoch,
    )


def deck(decks):
    cards = [
        {
            "rank": str(rank),
            "value": 11 if rank == "A" else 10 if rank in ("J", "Q", "K") else rank,
            "suit": suit,
        }
        for _ in range(decks)
        for suit in ("♠", "♥", "♦", "♣")
        for rank in ("A", 2, 3, 4, 5, 6, 7, 8, 9, 10, "J", "Q", "K")
    ]
    random.SystemRandom().shuffle(cards)
    return cards


def score(hand):
    total = sum(c["value"] for c in hand)
    aces = sum(c["rank"] == "A" for c in hand)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def natural(hand):
    return len(hand) == 2 and score(hand) == 21


def checked_deck(factory, decks):
    cards = (factory or deck)(decks)
    if (
        not isinstance(cards, list)
        or not 52 <= len(cards) <= 104
        or any(
            not isinstance(c, dict)
            or c.get("rank")
            not in ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
            or type(c.get("value")) is not int
            or c["value"]
            != (11 if c["rank"] == "A" else 10 if c["rank"] in ("J", "Q", "K") else int(c["rank"]))
            or c.get("suit") not in ("♠", "♥", "♦", "♣")
            for c in cards
        )
    ):
        raise ValueError("blackjack_invalid_deck")
    return cards


def players(db, identifier):
    return db.execute(
        "SELECT * FROM blackjack_players WHERE game_id=? ORDER BY seat", (identifier,)
    ).fetchall()


def game(db, identifier):
    return db.execute("SELECT * FROM blackjack_games WHERE id=?", (identifier,)).fetchone()


def refund(db, row, now, state="cancelled"):
    if row["state"] not in ("lobby", "playing"):
        return
    for p in players(db, row["id"]):
        xp.release(
            db, p["wallet_id"], "bj-" + row["id"], p["bet"], "bj-refund-" + row["id"], now, "refund"
        )
    result = Result(
        "cancelled",
        "blackjack_" + state,
        "Partida retirada; apuestas devueltas una vez.",
        {"game_id": row["id"], "state": state},
    )
    db.execute(
        "UPDATE blackjack_games SET state=?,deck_json='[]',dealer_json='[]',result_json=?,revision=revision+1 WHERE id=?",
        (state, result.to_json(), row["id"]),
    )


def settle(db, row, now):
    if row["state"] != "playing":
        return
    ps = players(db, row["id"])
    cards = json.loads(row["deck_json"])
    dealer = json.loads(row["dealer_json"])
    if any(p["state"] in ("stood", "blackjack") for p in ps):
        while score(dealer) < 17:
            dealer.append(cards.pop())
    outcomes = []
    for p in ps:
        hand = json.loads(p["hand_json"])
        value = score(hand)
        if p["state"] == "busted":
            gross, outcome = 0, "pierde"
        elif natural(hand):
            gross, outcome = (
                (p["bet"], "empate") if natural(dealer) else (5 * p["bet"] // 2, "blackjack")
            )
        elif natural(dealer):
            gross, outcome = 0, "pierde"
        elif score(dealer) > 21 or value > score(dealer):
            gross, outcome = 2 * p["bet"], "gana"
        elif value == score(dealer):
            gross, outcome = p["bet"], "empate"
        else:
            gross, outcome = 0, "pierde"
        xp.release(db, p["wallet_id"], "bj-" + row["id"], gross, "bj-payout-" + row["id"], now)
        outcomes.append(
            {
                "seat": p["seat"] + 1,
                "score": value,
                "bet": p["bet"],
                "payout": gross,
                "outcome": outcome,
            }
        )
    result = Result(
        "ok",
        "blackjack_settled",
        "Crupier: "
        + str(score(dealer))
        + "\n"
        + "\n".join(
            f"Asiento {o['seat']}: {o['outcome']} · pago {o['payout']} XP" for o in outcomes
        ),
        {"game_id": row["id"], "state": "settled", "dealer": dealer, "players": outcomes},
    )
    db.execute(
        "UPDATE blackjack_games SET state='settled',deck_json='[]',dealer_json='[]',result_json=?,revision=revision+1 WHERE id=?",
        (result.to_json(), row["id"]),
    )


def advance(db, row, now):
    active = [p for p in players(db, row["id"]) if p["state"] == "playing"]
    if not active:
        settle(db, row, now)
        return
    db.execute(
        "UPDATE blackjack_games SET turn=?,revision=revision+1,deadline_ms=? WHERE id=?",
        (active[0]["seat"], now + (60000 if row["mode"] == "individual" else 30000), row["id"]),
    )


def deal(db, row, now, factory):
    cards = checked_deck(factory, 1 if row["mode"] == "individual" else 2)
    for p in players(db, row["id"]):
        hand = [cards.pop(), cards.pop()]
        db.execute(
            "UPDATE blackjack_players SET hand_json=?,state=? WHERE game_id=? AND wallet_id=?",
            (
                canonical(hand),
                "blackjack" if natural(hand) else "playing",
                row["id"],
                p["wallet_id"],
            ),
        )
    dealer = [cards.pop(), cards.pop()]
    db.execute(
        "UPDATE blackjack_games SET state='playing',deck_json=?,dealer_json=?,revision=revision+1 WHERE id=?",
        (canonical(cards), canonical(dealer), row["id"]),
    )
    if natural(dealer):
        db.execute(
            "UPDATE blackjack_players SET state='stood' WHERE game_id=? AND state='playing'",
            (row["id"],),
        )
    advance(db, game(db, row["id"]), now)


def board(db, context, row, now):
    if row["result_json"]:
        return Result.from_json(row["result_json"])
    ps = players(db, row["id"])
    dealer = json.loads(row["dealer_json"])
    visible = [
        {
            "seat": p["seat"] + 1,
            "bet": p["bet"],
            "state": p["state"],
            "hand": json.loads(p["hand_json"]),
            "score": score(json.loads(p["hand_json"])),
        }
        for p in ps
    ]
    lines = [f"Blackjack {row['id']} · {row['state']} · apuesta {row['bet']} XP."]
    if dealer:
        lines.append("Crupier: " + dealer[0]["rank"] + dealer[0]["suit"] + " · carta oculta")
    for p in visible:
        lines.append(
            f"Asiento {p['seat']}: "
            + " ".join(c["rank"] + c["suit"] for c in p["hand"])
            + f" ({p['score']}) · {p['state']}"
        )
    if row["state"] == "lobby":
        lines.extend([f"/bj entrar {row['id']}", f"/bj repartir {row['id']}"])
    else:
        lines.extend(
            [
                f"Turno: asiento {row['turn'] + 1}",
                f"/bj pedir {row['id']}",
                f"/bj plantarse {row['id']}",
                f"/bj doblar {row['id']}",
            ]
        )
    db.execute(
        "INSERT INTO game_views VALUES(?,?,?,NULL)",
        (context.receipt_id, row["id"], row["revision"]),
    )
    db.execute(
        "UPDATE blackjack_games SET board_receipt_id=? WHERE id=?", (context.receipt_id, row["id"])
    )
    return Result(
        "ok",
        "blackjack_board",
        "\n".join(lines),
        {
            "game_id": row["id"],
            "state": row["state"],
            "revision": row["revision"],
            "players": visible,
            "dealer_visible": dealer[:1],
            "bet": row["bet"],
            "turn": row["turn"] + 1,
        },
    )


def published(db, row, source_ms):
    return (
        db.execute(
            "SELECT 1 FROM game_views WHERE game_id=? AND revision=? AND accepted_ms IS NOT NULL AND accepted_ms<?",
            (row["id"], row["revision"], source_ms),
        ).fetchone()
        is not None
    )


def _tick_once(db, now, settings):
    for row in db.execute(
        "SELECT * FROM blackjack_games WHERE instance=? AND account=? AND epoch=? AND state IN ('lobby','playing') AND deadline_ms<=?",
        (settings.instance, settings.account, settings.epoch, now),
    ).fetchall():
        view = db.execute(
            "SELECT accepted_ms FROM game_views WHERE game_id=? AND accepted_ms IS NOT NULL",
            (row["id"],),
        ).fetchone()
        if row["state"] == "lobby" or not view:
            refund(db, row, now, "expired")
            continue
        p = next(
            (
                p
                for p in players(db, row["id"])
                if p["seat"] == row["turn"] and p["state"] == "playing"
            ),
            None,
        )
        if p:
            db.execute(
                "UPDATE blackjack_players SET state='stood' WHERE game_id=? AND wallet_id=?",
                (row["id"], p["wallet_id"]),
            )
        previous_deadline = row["deadline_ms"]
        advance(db, row, now)
        db.execute(
            "UPDATE blackjack_games SET deadline_ms=? WHERE id=? AND state='playing'",
            (previous_deadline + 30000, row["id"]),
        )


def tick(db, now, settings):
    # Como máximo seis asientos por mesa; un tick concilia todos los turnos vencidos.
    for _ in range(6):
        pending = db.execute(
            "SELECT 1 FROM blackjack_games WHERE instance=? AND account=? AND epoch=? AND state IN ('lobby','playing') AND deadline_ms<=? LIMIT 1",
            (settings.instance, settings.account, settings.epoch, now),
        ).fetchone()
        if not pending:
            break
        _tick_once(db, now, settings)


def execute(db, context, action, args, now, app):
    tick(db, now, app.settings)
    own = xp.wallet(db, context)
    if action in ("start", "table"):
        if action == "table" and not context.scope.is_group:
            return Result(
                "failed", "blackjack_group_required", "La mesa requiere grupo habilitado."
            )
        if db.execute(
            "SELECT 1 FROM blackjack_players p JOIN blackjack_games g ON g.id=p.game_id WHERE p.wallet_id=? AND g.state IN ('lobby','playing')",
            (own["id"],),
        ).fetchone():
            return Result(
                "needs_input", "blackjack_already_active", "Tu cuenta ya tiene una partida activa."
            )
        if (
            action == "table"
            and db.execute(
                "SELECT 1 FROM blackjack_games WHERE "
                + CHAT
                + " AND mode='table' AND state IN ('lobby','playing')",
                chat_key(context),
            ).fetchone()
        ):
            return Result(
                "needs_input", "blackjack_table_active", "Ya hay una mesa activa en el grupo."
            )
        bet = args.get("bet") or (20 if own["balance"] < 50 else 50)
        if own["balance"] == 0 and own["reserved"] == 0 and action == "start":
            xp.move(
                db,
                own["id"],
                20,
                context.receipt_id + "-gift",
                "blackjack_gift",
                now,
                context.receipt_id,
            )
            own = xp.wallet(db, context)
        if not 20 <= bet <= 1000 or own["balance"] < bet:
            return Result(
                "needs_input",
                "blackjack_insufficient_xp",
                f"Apuesta20–1000 XP. Saldo {own['balance']} XP; no abrí partida.",
            )
        identifier = uuid4().hex
        try:
            xp.hold(
                db,
                own["id"],
                "bj-" + identifier,
                bet,
                (5 * bet + 1) // 2,
                context.receipt_id,
                now,
                context.receipt_id,
            )
        except ValueError:
            return Result("failed", "xp_headroom", "No hay margen para reservar el pago máximo.")
        db.execute(
            "INSERT INTO blackjack_games(id,instance,account,chat,is_group,epoch,host,mode,state,bet,deadline_ms,created_ms) VALUES(?,?,?,?,?,?,?,?,'lobby',?,?,?)",
            (
                identifier,
                *chat_key(context),
                context.scope.actor,
                "table" if action == "table" else "individual",
                bet,
                now + 35000,
                now,
            ),
        )
        db.execute(
            "INSERT INTO blackjack_players(game_id,wallet_id,actor,seat,bet) VALUES(?,?,?,0,?)",
            (identifier, own["id"], context.scope.actor, bet),
        )
        if action == "start":
            try:
                deal(db, game(db, identifier), now, app.blackjack_deck)
            except ValueError:
                refund(db, game(db, identifier), now)
                return Result(
                    "failed",
                    "blackjack_invalid_deck",
                    "No pude preparar una baraja válida; apuesta devuelta.",
                )
        return board(db, context, game(db, identifier), now)
    identifier = args.get("game_id")
    query = "SELECT * FROM blackjack_games WHERE " + CHAT
    params = list(chat_key(context))
    if identifier:
        query += " AND id=?"
        params.append(identifier)
    else:
        query += " AND state IN ('lobby','playing')"
    if not context.scope.is_group:
        query += " AND host=?"
        params.append(context.scope.actor)
    else:
        query += " AND (mode='table' OR host=?)"
        params.append(context.scope.actor)
    row = db.execute(query + " ORDER BY created_ms DESC LIMIT 1", params).fetchone()
    if not row:
        return Result(
            "empty", "blackjack_not_found", "No hay una partida admisible con ese ID aquí."
        )
    if action == "status":
        return board(db, context, row, now)
    if row["state"] not in ("lobby", "playing"):
        return Result.from_json(row["result_json"])
    source_ms = db.execute(
        "SELECT min(source_ms,received_ms) FROM inbox WHERE id=?", (context.receipt_id,)
    ).fetchone()[0]
    if not published(db, row, source_ms):
        return Result(
            "needs_input",
            "blackjack_board_required",
            "Recibe el tablero vigente y después elige tu acción.",
        )
    if action == "cancel":
        if context.scope.actor not in (row["host"], app.settings.owner):
            return Result(
                "failed", "blackjack_host_required", "Solo anfitrión o dueño cancela esta partida."
            )
        if row["state"] != "lobby":
            return Result(
                "failed",
                "blackjack_cancel_playing",
                "Una mano repartida se termina por turno o plazo; no se devuelve por cancelación voluntaria.",
            )
        refund(db, row, now)
        return Result.from_json(game(db, row["id"])["result_json"])
    if action == "join":
        if row["state"] != "lobby" or row["mode"] != "table":
            return Result("failed", "blackjack_not_lobby", "La mesa ya no admite participantes.")
        if db.execute(
            "SELECT 1 FROM blackjack_players p JOIN blackjack_games g ON g.id=p.game_id WHERE p.wallet_id=? AND g.state IN ('lobby','playing')",
            (own["id"],),
        ).fetchone():
            return Result("failed", "blackjack_already_active", "Ya tienes una partida activa.")
        count = len(players(db, row["id"]))
        if count >= 6 or own["balance"] < row["bet"]:
            return Result(
                "failed", "blackjack_join_unavailable", "Mesa llena o saldo insuficiente."
            )
        try:
            xp.hold(
                db,
                own["id"],
                "bj-" + row["id"],
                row["bet"],
                (5 * row["bet"] + 1) // 2,
                context.receipt_id,
                now,
                context.receipt_id,
            )
        except ValueError:
            return Result("failed", "xp_headroom", "No hay margen para reservar el pago.")
        db.execute(
            "INSERT INTO blackjack_players(game_id,wallet_id,actor,seat,bet) VALUES(?,?,?,?,?)",
            (row["id"], own["id"], context.scope.actor, count, row["bet"]),
        )
        db.execute("UPDATE blackjack_games SET revision=revision+1 WHERE id=?", (row["id"],))
    elif action == "deal":
        if row["host"] != context.scope.actor:
            return Result("failed", "blackjack_host_required", "Solo el anfitrión reparte.")
        if row["state"] != "lobby":
            return Result("failed", "blackjack_not_lobby", "La mano ya se repartió.")
        try:
            deal(db, row, now, app.blackjack_deck)
        except ValueError:
            return Result(
                "failed",
                "blackjack_invalid_deck",
                "No pude preparar la baraja; apuestas siguen en la mesa.",
            )
    else:
        ps = players(db, row["id"])
        p = next((p for p in ps if p["wallet_id"] == own["id"]), None)
        if (
            not p
            or row["state"] != "playing"
            or p["seat"] != row["turn"]
            or p["state"] != "playing"
        ):
            return Result("failed", "blackjack_not_your_turn", "No es tu turno en esa partida.")
        hand = json.loads(p["hand_json"])
        cards = json.loads(row["deck_json"])
        if action == "double":
            if len(hand) != 2:
                return Result(
                    "failed", "blackjack_double_after_hit", "Solo se dobla con dos cartas."
                )
            if own["balance"] < p["bet"]:
                return Result(
                    "failed", "blackjack_insufficient_xp", "Saldo insuficiente para doblar."
                )
            hold = db.execute(
                "SELECT amount FROM xp_holds WHERE resource=? AND wallet_id=?",
                ("bj-" + row["id"], own["id"]),
            ).fetchone()[0]
            newhold = 4 * p["bet"]
            try:
                xp.move(
                    db,
                    own["id"],
                    -p["bet"],
                    context.receipt_id,
                    "blackjack_double",
                    now,
                    context.receipt_id,
                    release=hold,
                    reserve=newhold,
                )
            except ValueError:
                return Result("failed", "xp_headroom", "No hay margen para doblar.")
            db.execute(
                "UPDATE xp_holds SET amount=? WHERE resource=? AND wallet_id=?",
                (newhold, "bj-" + row["id"], own["id"]),
            )
            db.execute(
                "UPDATE blackjack_players SET bet=bet*2 WHERE game_id=? AND wallet_id=?",
                (row["id"], own["id"]),
            )
        if action in ("hit", "double"):
            hand.append(cards.pop())
        state = (
            "busted"
            if score(hand) > 21
            else "stood"
            if action in ("stand", "double") or score(hand) == 21
            else "playing"
        )
        db.execute(
            "UPDATE blackjack_players SET hand_json=?,state=? WHERE game_id=? AND wallet_id=?",
            (canonical(hand), state, row["id"], own["id"]),
        )
        db.execute(
            "UPDATE blackjack_games SET deck_json=?,revision=revision+1 WHERE id=?",
            (canonical(cards), row["id"]),
        )
        if state != "playing":
            advance(db, game(db, row["id"]), now)
    return board(db, context, game(db, row["id"]), now)
