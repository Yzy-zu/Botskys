"""Economía/blackjack R7 con SQLite real y barajas sintéticas fijadas antes del caso."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.domains import economy


def cards(*ranks):
    return [
        {
            "rank": str(r),
            "value": 11 if r == "A" else 10 if r in ("J", "Q", "K") else int(r),
            "suit": "♠",
        }
        for r in ranks
    ]


def arranged(*ranks):
    # Motor pop() en orden: dos jugador, dos crupier y después robo.
    return lambda count: cards(*(["2"] * 52)) + list(reversed(cards(*ranks)))


class GamesTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793962800000
        self.settings = Settings(
            self.root,
            "games-lab",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.app = Application(self.settings, clock=lambda: self.now, daily_roll=lambda: 1)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.n = 0

    def incoming(self, text, actor="alice", chat="private", **kw):
        self.n += 1
        return self.adapter.incoming(str(self.n), actor, chat, text, **kw)

    def receive(self, text, **kw):
        return self.app.receive(self.incoming(text, **kw))

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def deliver(self, receipt):
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 1

    def test_daily_race_scope_global_cooldown_streak_and_maximum_hold(self):
        incoming = self.incoming("/daily")
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(self.app.receive, [incoming, incoming]))
        self.assertEqual(sum(r.duplicate for r in receipts), 1)
        self.assertEqual(self.receive("/saldo", chat="other").result.data["balance"], 1000)
        self.assertEqual(self.receive("/daily").result.code, "daily_cooldown")
        self.assertEqual(self.receive("/saldo", actor="bob").result.data["balance"], 0)
        self.now += 86400000
        self.assertEqual(self.receive("/daily").result.data["gained"], 1020)
        self.app.daily_roll = lambda: 100
        self.now += 86400000
        self.assertEqual(self.receive("/daily").result.data["gained"], 0)
        self.assertEqual(self.receive("/daily").result.code, "daily_cooldown")
        self.assertEqual(self.receive("/saldo").result.data["level"], 102)
        self.assertNotIn("alice", self.receive("/top").result.text)
        self.app.daily_roll = lambda: 1
        self.now += 86400000
        with self.app.store.transaction() as db:
            db.execute(
                "UPDATE wallets SET balance=?,reserved=20 WHERE actor=?",
                (economy.MAX_BALANCE - 20, "alice"),
            )
        self.assertEqual(self.receive("/daily").result.code, "xp_limit")

    def test_group_message_credit_duplicate_old_and_commands_excluded(self):
        group = dict(chat="group", is_group=True)
        incoming = self.incoming("texto normal", **group)
        self.app.receive(incoming)
        self.app.receive(incoming)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1)
        self.receive("/ayuda", **group)
        self.receive("!otro", **group)
        self.receive(".otro", **group)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1)
        self.app.receive(self.incoming("histórico", source_ms=self.now - 400000, **group))
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1)

    def test_blackjack_natural_payout_single_receipt_and_rescue_default(self):
        self.app.blackjack_deck = arranged("A", "K", "10", "8")
        incoming = self.incoming("/bj iniciar")
        result = self.app.receive(incoming)
        self.assertEqual(result.result.code, "blackjack_settled")
        self.assertEqual(result.result.data["players"][0]["payout"], 50)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 50)
        self.app.receive(incoming)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 50)
        self.assertEqual(self.rows("SELECT * FROM xp_holds"), [])
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 0)

    def test_blackjack_board_publication_turn_double_and_restart_saved_cards(self):
        self.receive("/daily")
        self.app.blackjack_deck = arranged("5", "6", "10", "7", "10")
        start = self.receive("/bj iniciar 50")
        identifier = start.result.data["game_id"]
        self.assertEqual(
            self.receive("/bj doblar " + identifier).result.code, "blackjack_board_required"
        )
        self.deliver(start)
        restarted = Application(
            self.settings,
            clock=lambda: self.now,
            blackjack_deck=lambda _: (_ for _ in ()).throw(AssertionError("must not reshuffle")),
        )
        result = restarted.receive(self.incoming("/bj doblar " + identifier))
        self.assertEqual(result.result.code, "blackjack_settled")
        self.assertEqual(result.result.data["players"][0]["payout"], 200)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1100)
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 0)
        self.assertEqual(
            self.receive("/bj estado " + identifier, actor="bob").result.code, "blackjack_not_found"
        )

    def test_blackjack_table_stakes_own_wallet_turns_and_cancel_refund_once(self):
        group = dict(chat="group", is_group=True)
        self.receive("/daily")
        self.receive("/daily", actor="bob")
        table = self.receive("/bj mesa 50", **group)
        identifier = table.result.data["game_id"]
        self.deliver(table)
        joined = self.receive("/bj entrar " + identifier, actor="bob", **group)
        self.assertEqual(joined.result.code, "blackjack_board")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 950)
        self.assertEqual(self.receive("/saldo", actor="bob").result.data["balance"], 950)
        self.deliver(joined)
        self.assertEqual(
            self.receive("/bj cancelar " + identifier, actor="bob", **group).result.code,
            "blackjack_host_required",
        )
        cancelled = self.receive("/bj cancelar " + identifier, **group)
        self.assertEqual(cancelled.result.code, "blackjack_cancelled")
        self.receive("/bj cancelar " + identifier, **group)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000)
        self.assertEqual(self.receive("/saldo", actor="bob").result.data["balance"], 1000)

    def test_blackjack_timeout_refunds_unpublished_and_settles_published(self):
        self.receive("/daily")
        self.app.blackjack_deck = arranged("10", "8", "10", "7")
        start = self.receive("/bj iniciar 50")
        identifier = start.result.data["game_id"]
        self.now += 60001
        self.assertEqual(self.receive("/bj estado " + identifier).result.code, "blackjack_expired")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000)
        start = self.receive("/bj iniciar 50")
        identifier = start.result.data["game_id"]
        self.deliver(start)
        self.now += 60001
        self.assertEqual(self.receive("/bj estado " + identifier).result.code, "blackjack_settled")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1050)

    def test_prank_safe_fiction_never_looks_up_or_mutates_foreign_data(self):
        result = self.receive("/broma Patito azul").result
        self.assertEqual(result.code, "prank_fiction")
        self.assertIn("FICCIÓN", result.text)
        self.assertIn("No investigué", result.text)
        self.assertEqual(self.receive("/broma 123").result.code, "prank_invalid_label")
        self.assertEqual(self.rows("SELECT * FROM notes"), [])

    def test_happy_hour_publication_owner_scope_drop_race_and_expiry(self):
        group = dict(chat="group", is_group=True)
        self.assertEqual(self.receive("/hh iniciar", **group).result.code, "owner_required")
        created = self.receive("/hh iniciar --duracion 1m", actor="owner", **group)
        identifier = created.result.data["event_id"]
        self.assertEqual(
            self.receive("/hh estado " + identifier, **group).result.data["state"], "preparing"
        )
        self.receive("sin bonus todavía", **group)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1)
        self.deliver(created)
        self.receive("ahora bonus", **group)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 21)
        drop = self.receive("/hh airdrop " + identifier, actor="owner", **group)
        did = drop.result.data["drop_id"]
        self.assertEqual(
            self.receive("/hh reclamar " + did, **group).result.code, "happy_drop_unavailable"
        )
        self.deliver(drop)
        incoming = [
            self.incoming("/hh reclamar " + did, actor=actor, **group) for actor in ("alice", "bob")
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.app.receive, incoming))
        self.assertEqual(sum(r.result.code == "happy_drop_claimed" for r in results), 1)
        self.assertEqual(len(self.rows("SELECT * FROM xp_entries WHERE kind='airdrop'")), 1)
        self.assertEqual(
            self.receive("/hh airdrop " + identifier, actor="owner", **group).result.code,
            "happy_drop_exists",
        )
        self.now += 60001
        self.app.scheduler.tick()
        self.assertEqual(
            self.receive("/hh estado " + identifier, **group).result.data["state"], "closed"
        )
        self.receive("sin bonus al vencer", **group)
        self.assertEqual(
            self.rows(
                "SELECT amount FROM xp_entries WHERE kind='message' ORDER BY created_ms DESC LIMIT 1"
            )[0]["amount"],
            1,
        )

    def test_stale_game_board_and_delayed_happy_publication_are_not_delivered(self):
        self.receive("/daily")
        self.app.blackjack_deck = arranged("5", "6", "10", "7", "10")
        start = self.receive("/bj iniciar 50")
        identifier = start.result.data["game_id"]
        self.deliver(start)
        older = self.receive("/bj estado " + identifier)
        self.receive("/bj plantarse " + identifier)
        self.assertEqual(self.app.deliver(older.id, CollectingTransport()), 0)
        happy = self.receive("/hh iniciar", actor="owner", chat="group", is_group=True)
        self.now += 300001
        self.assertEqual(self.app.deliver(happy.id, CollectingTransport()), 0)
        self.assertEqual(self.rows("SELECT state FROM happy_events")[0]["state"], "closed")

    def test_blackjack_table_natural_and_double_settle_all_wallets_once(self):
        group = dict(chat="group", is_group=True)
        self.receive("/daily")
        self.receive("/daily", actor="bob")
        self.app.blackjack_deck = arranged("A", "K", "5", "6", "10", "7", "10")
        table = self.receive("/bj mesa 50", **group)
        identifier = table.result.data["game_id"]
        self.deliver(table)
        joined = self.receive("/bj entrar " + identifier, actor="bob", **group)
        self.deliver(joined)
        dealt = self.receive("/bj repartir " + identifier, **group)
        self.deliver(dealt)
        self.assertEqual(
            self.receive("/bj pedir " + identifier, **group).result.code, "blackjack_not_your_turn"
        )
        result = self.receive("/bj doblar " + identifier, actor="bob", **group).result
        self.assertEqual(result.code, "blackjack_settled")
        self.assertEqual([p["payout"] for p in result.data["players"]], [125, 200])
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1075)
        self.assertEqual(self.receive("/saldo", actor="bob").result.data["balance"], 1100)
        self.receive("/bj estado " + identifier, **group)
        self.assertEqual(self.rows("SELECT * FROM xp_holds"), [])

    def test_blackjack_invalid_deck_refunds_and_admission_before_publication_is_denied(self):
        self.receive("/daily")
        self.app.blackjack_deck = lambda _: []
        self.assertEqual(self.receive("/bj iniciar 50").result.code, "blackjack_invalid_deck")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000)
        self.app.blackjack_deck = arranged("5", "6", "10", "7", "10")
        start = self.receive("/bj iniciar 50")
        identifier = start.result.data["game_id"]
        queued = self.app.admit(self.incoming("/bj doblar " + identifier, source_ms=self.now + 100))
        self.now += 1
        self.deliver(start)
        self.assertEqual(self.app.process(queued.id).result.code, "blackjack_board_required")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 950)
