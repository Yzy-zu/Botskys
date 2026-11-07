"""Huecos del catálogo, con oracles de efecto local y transporte exclusivamente doble."""

import json
from unittest import IsolatedAsyncioTestCase, TestCase

import test_admin
import test_calls
import test_games
import test_minecraft
import test_organization

from botsky.adapters.local import CollectingTransport


class SchoolVisualGaps(TestCase):
    setUp = test_organization.OrganizationTest.setUp
    incoming = test_organization.OrganizationTest.incoming
    receive = test_organization.OrganizationTest.receive
    rows = test_organization.OrganizationTest.rows

    def test_author_completes_and_deletes_actual_task_with_visible_result(self):
        created = self.receive("/tarea crear --fecha 2026-11-07 Texto *literal*")
        identifier = created.result.data["task_id"]
        completed = self.receive("/tarea completar " + str(identifier))
        self.assertEqual(completed.result.code, "school_task_completed")
        self.assertEqual(
            self.rows("SELECT state FROM school_tasks WHERE id=?", (identifier,))[0]["state"],
            "completed",
        )
        removed = self.receive("/tarea borrar " + str(identifier))
        self.assertEqual(removed.result.code, "school_task_deleted")
        self.assertEqual(
            self.rows("SELECT state FROM school_tasks WHERE id=?", (identifier,))[0]["state"],
            "deleted",
        )
        self.assertEqual(
            self.receive("/tarea archivo " + str(identifier)).result.code, "task_not_found"
        )
        transport = CollectingTransport()
        self.app.deliver(completed.id, transport)
        self.app.deliver(removed.id, transport)
        self.assertTrue(any("completada" in p.text for p in transport.parts))
        self.assertTrue(any("borrada" in p.text for p in transport.parts))


class BlackjackVisualGaps(TestCase):
    setUp = test_games.GamesTest.setUp
    incoming = test_games.GamesTest.incoming
    receive = test_games.GamesTest.receive
    rows = test_games.GamesTest.rows
    deliver = test_games.GamesTest.deliver

    def test_hit_changes_saved_hand_and_shows_new_score_without_hidden_dealer_card(self):
        self.receive("/daily")
        self.app.blackjack_deck = test_games.arranged("5", "6", "10", "7", "3")
        start = self.receive("/bj iniciar 50")
        self.deliver(start)
        hit = self.receive("/bj pedir " + start.result.data["game_id"])
        self.assertEqual(hit.result.code, "blackjack_board")
        self.assertEqual(hit.result.data["players"][0]["score"], 14)
        self.assertEqual(len(hit.result.data["players"][0]["hand"]), 3)
        self.assertEqual(hit.result.data["dealer_visible"], test_games.cards("10"))
        transport = CollectingTransport()
        self.app.deliver(hit.id, transport)
        text = "".join(p.text for p in transport.parts)
        self.assertIn("14 puntos", text)
        self.assertIn("carta oculta", text)
        self.assertNotIn("7♠", text)


class AdminVisualGaps(IsolatedAsyncioTestCase):
    asyncSetUp = test_admin.AdminTest.asyncSetUp
    incoming = test_admin.AdminTest.incoming
    receive = test_admin.AdminTest.receive
    rows = test_admin.AdminTest.rows
    result = test_admin.AdminTest.result
    command = test_admin.AdminTest.command

    async def test_ban_stores_verified_target_and_known_ack_without_repeating(self):
        receipt, result = await self.command("/admin ban bob-target")
        self.assertEqual(result.code, "admin_completed")
        row = self.rows("SELECT target,state FROM admin_bans")[0]
        self.assertEqual(row, {"target": "bob-target", "state": "active"})
        self.assertEqual(len(self.groups.calls), 1)
        transport = CollectingTransport()
        self.app.deliver(receipt.id, transport)
        text = "".join(p.text for p in transport.parts)
        self.assertIn("Bloquear", text)
        self.assertIn("Participante verificado", text)
        self.assertNotIn("222222222", text)
        self.assertEqual(self.app.deliver(receipt.id, transport), 0)
        self.assertEqual(len(self.groups.calls), 1)


class MinecraftVisualGaps(IsolatedAsyncioTestCase):
    asyncSetUp = test_minecraft.MinecraftTest.asyncSetUp
    incoming = test_minecraft.MinecraftTest.incoming
    receive = test_minecraft.MinecraftTest.receive
    rows = test_minecraft.MinecraftTest.rows
    result = test_minecraft.MinecraftTest.result

    async def test_discover_stop_restart_use_only_runner_and_restart_health_is_observed(self):
        async def runner(argv, payload):
            command = json.loads(payload)
            self.calls.append((argv, command))
            action = command["action"]
            values = {
                "discover": {
                    "status": "ok",
                    "available": True,
                    "active_world": "synthetic-world",
                    "fingerprint": "fixture-only",
                },
                "stop": {"status": "ok", "online": False, "verified": True},
                "restart": {"status": "ok", "requires_healthcheck": True},
                "status": {"status": "ok", "online": True, "game_status": "ready"},
            }
            return json.dumps(values[action]).encode()

        self.remote._runner = runner
        for command, action in (
            ("/mc diagnostico", "discover"),
            ("/mc parar", "stop"),
            ("/mc reiniciar", "restart"),
        ):
            receipt = self.receive(command)
            await self.app.jobs.run_pending()
            result = self.result(receipt)
            self.assertEqual(result.code, "minecraft_completed")
            self.assertEqual(result.data["action"], action)
            if action == "restart":
                self.assertTrue(result.data["response"]["verified"])
            if action == "stop":
                self.assertFalse(result.data["response"]["online"])
            transport = CollectingTransport()
            self.app.deliver(receipt.id, transport)
            self.assertTrue(transport.parts)
        self.assertEqual(
            [row[1]["action"] for row in self.calls], ["discover", "stop", "restart", "status"]
        )


class ClipVisualGaps(IsolatedAsyncioTestCase):
    asyncSetUp = test_calls.CallsTest.asyncSetUp
    close_process = test_calls.CallsTest.close_process
    ipc = test_calls.CallsTest.ipc
    incoming = None
    receive = test_calls.CallsTest.receive
    rows = test_calls.CallsTest.rows
    result = test_calls.CallsTest.result
    command = test_calls.CallsTest.command

    async def test_next_selects_second_actual_synthetic_clip_and_reports_observed_name(self):
        await self.command("/llamar --video")
        await self.ipc({"action": "connect"})
        first = await self.ipc({"action": "seedClip"})
        second = await self.ipc({"action": "seedSecondClip"})
        self.assertNotEqual(first["id"], second["id"])
        await self.command("/clip poner " + first["id"])
        result, receipt, _ = await self.command("/clip siguiente")
        self.assertEqual(result.code, "av_control_applied")
        stats = await self.ipc({"action": "stats"})
        self.assertEqual(stats["active"]["clip"]["clipId"], second["id"])
        self.assertEqual(result.data["clip"]["name"], "Segundo clip sintético")
        transport = CollectingTransport()
        self.app.deliver(receipt.id, transport)
        self.assertIn("Segundo clip sintético", "".join(p.text for p in transport.parts))
