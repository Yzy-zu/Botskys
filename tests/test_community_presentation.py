from unittest import TestCase

import test_games

from botsky.adapters.local import CollectingTransport
from botsky.contracts import Result
from botsky.presentation.domains import present


class CommunityPresentationTest(TestCase):
    setUp = test_games.GamesTest.setUp
    incoming = test_games.GamesTest.incoming
    receive = test_games.GamesTest.receive
    rows = test_games.GamesTest.rows

    def test_available_balance_top_native_and_daily_time(self):
        self.app.store.native_tables_enabled = True
        self.receive("/daily")
        own = self.receive("/saldo")
        transport = CollectingTransport()
        self.app.deliver(own.id, transport)
        self.assertIn("Disponible: 1000 XP", transport.parts[0].text)
        self.assertIn("Reservado: 0 XP", transport.parts[0].text)
        top = self.receive("/top")
        transport = CollectingTransport()
        self.app.deliver(top.id, transport)
        table = next(p for p in transport.parts if p.kind == "table")
        self.assertEqual(table.payload["rows"][0][2], "1000")
        self.assertNotIn("alice", str(table.payload))
        cooldown = self.receive("/daily")
        transport = CollectingTransport()
        self.app.deliver(cooldown.id, transport)
        self.assertIn("America/Mexico_City", transport.parts[0].text)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000)

    def test_blackjack_settlement_names_gross_and_net_without_mutating_facts(self):
        source = Result(
            "ok",
            "blackjack_settled",
            "raw",
            {
                "dealer": test_games.cards(10, 7),
                "players": [
                    {"seat": 1, "score": 20, "bet": 20, "payout": 40, "outcome": "gana"},
                    {"seat": 2, "score": 17, "bet": 20, "payout": 20, "outcome": "empate"},
                ],
            },
        )
        text = present(source).text
        self.assertIn("pago bruto: 40 XP · resultado neto: +20 XP", text)
        self.assertIn("pago bruto: 20 XP · resultado neto: +0 XP", text)
        self.assertEqual(source.text, "raw")

    def test_mods_table_never_asserts_unknown_configuration_or_load_and_keeps_warnings(self):
        source = Result(
            "ok",
            "minecraft_completed",
            'Carga en juego: desconocida.\n/mc mod activar "selector"',
            {"action": "mods", "response": {"installed": [{"name": "Mapa", "version": [1, 0, 2]}]}},
        )
        shown = present(source)
        self.assertEqual(
            shown.data["native_tables"][0]["rows"][0][1:], ["1.0.2", "Desconocido", "Desconocida"]
        )
        self.assertIn(source.text, shown.text)
