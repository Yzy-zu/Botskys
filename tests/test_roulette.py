"""Ruleta local: reglas entregadas, grupo doble, apuestas y efectos sin API real."""

import asyncio
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result


class GroupFixture:
    available = True

    def __init__(self):
        self.members = [
            {
                "actor": "owner",
                "id": "owner-target",
                "phone": "555550000@s.whatsapp.net",
                "admin": True,
            },
            {
                "actor": "alice",
                "id": "alice-target",
                "phone": "111111111@s.whatsapp.net",
                "admin": False,
            },
            {
                "actor": "bob",
                "id": "bob-target",
                "phone": "222222222@s.whatsapp.net",
                "admin": False,
            },
        ]
        self.calls = []
        self.outcome = "accepted"
        self.pause = None

    async def snapshot(self, chat):
        return {"group_id": chat, "bot_is_admin": True, "participants": copy.deepcopy(self.members)}

    async def invite_link(self, chat):
        return "https://chat.whatsapp.com/SyntheticInvite01"

    async def change(self, chat, action, target):
        self.calls.append((chat, action, target))
        if self.pause:
            self.pause.set()
            await asyncio.Event().wait()
        return self.outcome


class ReturnFixture:
    available = True

    def __init__(self):
        self.calls = []

    async def send(self, target, kind, *, text="", path=None):
        self.calls.append((target, kind, text))
        return "accepted-return"


class RouletteTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1793962800000
        self.settings = Settings(
            self.root,
            "roulette-lab",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.groups = GroupFixture()
        self.returns = ReturnFixture()
        self.app = Application(
            self.settings,
            clock=lambda: self.now,
            groups=self.groups,
            messenger=self.returns,
            roulette_chats={"group"},
            roulette_choice=lambda items: items[0],
            daily_roll=lambda: 1,
        )
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.n = 0
        for actor in ("alice", "bob"):
            self.receive("/daily", actor=actor, chat="private", is_group=False)

    def incoming(self, text, actor="owner", chat="group", is_group=True, **kw):
        self.n += 1
        return self.adapter.incoming(str(self.n), actor, chat, text, is_group=is_group, **kw)

    def receive(self, text, **kw):
        return self.app.receive(self.incoming(text, **kw))

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def result(self, receipt):
        return Result.from_json(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (receipt.id,))[0]["result_json"]
        )

    def deliver(self, receipt):
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 1

    async def command(self, text, **kw):
        receipt = self.receive(text, **kw)
        await self.app.jobs.run_pending()
        return receipt, self.result(receipt)

    async def lobby(self):
        receipt, result = await self.command("/ruleta crear 50")
        identifier = result.data["room_id"]
        self.deliver(receipt)
        for actor in ("alice", "bob"):
            receipt, result = await self.command("/ruleta entrar " + identifier, actor=actor)
            self.assertEqual(result.code, "roulette_board")
            self.deliver(receipt)
        return identifier

    async def test_rules_must_be_delivered_before_acceptance_and_stake_is_own(self):
        created, result = await self.command("/ruleta crear 50")
        identifier = result.data["room_id"]
        _, result = await self.command("/ruleta entrar " + identifier, actor="alice")
        self.assertEqual(result.code, "roulette_rules_required")
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='alice'")[0]["balance"], 1000
        )
        self.deliver(created)
        alice, result = await self.command("/ruleta entrar " + identifier, actor="alice")
        self.assertEqual(result.code, "roulette_board")
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='bob'")[0]["balance"], 1000
        )
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='alice'")[0]["balance"], 950
        )
        self.deliver(alice)
        _, result = await self.command("/ruleta entrar " + identifier, actor="owner")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.groups.calls, [])

    async def test_one_effect_payout_and_return_after_twenty_minutes_once(self):
        identifier = await self.lobby()
        receipt, result = await self.command("/ruleta jugar " + identifier)
        self.assertEqual(result.code, "roulette_completed")
        self.assertEqual(self.groups.calls, [("group", "remove", "alice-target")])
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='alice'")[0]["balance"], 950
        )
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='bob'")[0]["balance"], 1050
        )
        self.assertEqual(self.rows("SELECT * FROM xp_holds"), [])
        await self.command("/ruleta jugar " + identifier)
        self.assertEqual(len(self.groups.calls), 1)
        self.now += 1200000
        self.assertEqual(len(self.app.scheduler.tick()), 1)
        self.assertEqual(self.app.scheduler.tick(), [])
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.returns.calls), 1)
        self.assertEqual(self.returns.calls[0][0], "111111111@s.whatsapp.net")
        self.assertIn("https://chat.whatsapp.com/SyntheticInvite01", self.returns.calls[0][2])
        self.assertEqual(
            self.rows("SELECT return_state FROM roulette_rooms")[0]["return_state"], "accepted"
        )

    async def test_uncertain_effect_retains_stakes_and_restart_does_not_repeat(self):
        identifier = await self.lobby()
        self.groups.outcome = "uncertain"
        _, result = await self.command("/ruleta jugar " + identifier)
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(len(self.rows("SELECT * FROM xp_holds")), 2)
        restarted = Application(
            self.settings, clock=lambda: self.now, groups=self.groups, roulette_chats={"group"}
        )
        await restarted.jobs.run_pending()
        await self.command("/ruleta jugar " + identifier)
        self.assertEqual(len(self.groups.calls), 1)
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='bob'")[0]["balance"], 950
        )

    async def test_known_effect_failure_refunds_everyone_and_expiry_is_once(self):
        identifier = await self.lobby()
        self.groups.outcome = "failed"
        _, result = await self.command("/ruleta jugar " + identifier)
        self.assertEqual(result.code, "roulette_failed")
        self.assertTrue(
            all(
                r["balance"] == 1000
                for r in self.rows("SELECT balance FROM wallets WHERE actor IN ('alice','bob')")
            )
        )
        identifier = await self.lobby()
        self.now += 120001
        self.app.scheduler.tick()
        self.assertEqual(
            self.rows("SELECT state FROM roulette_rooms WHERE id=?", (identifier,))[0]["state"],
            "expired",
        )
        self.app.scheduler.tick()
        self.assertTrue(
            all(
                r["balance"] == 1000
                for r in self.rows("SELECT balance FROM wallets WHERE actor IN ('alice','bob')")
            )
        )

    async def test_role_change_before_dispatch_refunds_and_cancel_during_effect_is_uncertain(self):
        identifier = await self.lobby()
        original = self.groups.invite_link

        async def change_role(chat):
            self.groups.members[1]["admin"] = True
            return await original(chat)

        self.groups.invite_link = change_role
        _, result = await self.command("/ruleta jugar " + identifier)
        self.assertEqual(result.code, "roulette_failed")
        self.assertEqual(self.groups.calls, [])
        self.groups.members[1]["admin"] = False
        self.groups.invite_link = original
        identifier = await self.lobby()
        self.groups.pause = asyncio.Event()
        receipt = self.receive("/ruleta jugar " + identifier)
        worker = asyncio.create_task(self.app.jobs.run_pending())
        await asyncio.wait_for(self.groups.pause.wait(), 2)
        self.receive("/cancelar " + receipt.id)
        await asyncio.wait_for(worker, 2)
        self.assertEqual(
            self.rows("SELECT state FROM roulette_rooms WHERE id=?", (identifier,))[0]["state"],
            "uncertain",
        )
        self.assertEqual(self.result(receipt).code, "request_cancelled")
