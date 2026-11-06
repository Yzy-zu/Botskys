"""R8 administración parcial: SQLite real, miembros dobles y cliente HTTPX cerrado."""

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx
from test_roulette import GroupFixture

from botsky.adapters.groups import GroupError, Groups
from botsky.adapters.local import LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result


class AdminTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793962800000
        self.settings = Settings(
            self.root,
            "admin-lab",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.groups = GroupFixture()
        self.snapshots = 0
        original = self.groups.snapshot

        async def snapshot(chat):
            self.snapshots += 1
            return await original(chat)

        self.groups.snapshot = snapshot
        self.groups.members[1]["aliases"] = ["alice", "alice-target"]
        self.app = Application(self.settings, clock=lambda: self.now, groups=self.groups)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.n = 0

    def incoming(self, text, actor="owner", chat="group", is_group=True):
        self.n += 1
        return self.adapter.incoming(str(self.n), actor, chat, text, is_group=is_group)

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

    async def command(self, text, **kw):
        receipt = self.receive(text, **kw)
        await self.app.jobs.run_pending()
        return receipt, self.result(receipt)

    async def test_owner_denied_before_client_and_warnings_never_route_to_balance(self):
        self.assertEqual(
            self.receive("/admin advertir alice", actor="alice").result.code, "owner_required"
        )
        self.assertEqual(self.snapshots, 0)
        receipt, result = await self.command("/admin advertir alice")
        identifier = result.data["warning_id"]
        self.assertEqual(result.code, "admin_warning_added")
        _, warnings = await self.command("/admin avisos alice")
        self.assertEqual(warnings.data["items"], [{"warning_id": identifier}])
        self.assertEqual(self.rows("SELECT * FROM wallets"), [])
        _, removed = await self.command("/admin quitar-aviso alice " + str(identifier))
        self.assertEqual(removed.code, "admin_warning_revoked")
        self.assertEqual(self.groups.calls, [])
        self.assertEqual(
            self.receive("/admin avisos alice", chat="private", is_group=False).result.code,
            "admin_group_required",
        )

    async def test_local_warning_receipt_survives_crash_before_job_publication(self):
        receipt = self.receive("/admin advertir alice")
        job = self.app.jobs.claim()
        await self.app.jobs.execute_engine(job, self.root)
        self.now += 1831000
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.rows("SELECT * FROM admin_warnings")), 1)
        self.assertEqual(self.result(receipt).code, "admin_warning_added")

    async def test_xp_verified_account_and_target_limits_and_own_scope(self):
        _, result = await self.command("/admin xp-dar --objetivo alice 100")
        self.assertEqual(result.code, "admin_xp_changed")
        own = self.rows("SELECT * FROM wallets WHERE actor='alice'")[0]
        _, result = await self.command("/admin xp-quitar --cuenta " + str(own["id"]) + " 101")
        self.assertEqual(result.code, "admin_xp_limit")
        _, result = await self.command("/admin xp-quitar --cuenta " + str(own["id"]) + " 40")
        self.assertEqual(result.code, "admin_xp_changed")
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='alice'")[0]["balance"], 60
        )
        _, result = await self.command("/admin xp-dar --cuenta 99999 100")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.groups.calls, [])

    async def test_ban_persisted_before_client_uncertain_blocks_mutations_and_unban_alias(self):
        original = self.groups.change

        async def check_ban(chat, action, target):
            self.assertEqual(self.rows("SELECT state FROM admin_bans")[0]["state"], "active")
            return await original(chat, action, target)

        self.groups.change = check_ban
        self.groups.outcome = "uncertain"
        _, result = await self.command("/admin ban alice")
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(self.receive("/admin expulsar bob").result.code, "admin_operation_pending")
        # El registro incierto bloquea cambios; las consultas siguen disponibles.
        _, result = await self.command("/admin avisos alice")
        self.assertEqual(result.code, "admin_warnings")
        with self.app.store.transaction() as db:
            db.execute("UPDATE external_operations SET state='completed' WHERE state='uncertain'")
        _, result = await self.command("/admin unban alice")
        self.assertEqual(result.code, "admin_unban")
        self.assertEqual(self.rows("SELECT state FROM admin_bans")[0]["state"], "revoked")
        self.assertEqual(len(self.groups.calls), 1)

    async def test_protected_targets_and_nuclear_disabled_by_default(self):
        _, result = await self.command("/admin expulsar owner")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.groups.calls, [])
        self.groups.members[1]["admin"] = True
        _, result = await self.command("/admin ban alice")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.rows("SELECT * FROM admin_bans"), [])
        prepared, result = await self.command("/admin nuclear-preparar")
        self.assertEqual(result.code, "nuclear_preview")
        self.assertEqual(
            self.receive("/admin nuclear-confirmar " + result.data["draft_id"]).result.code,
            "nuclear_disabled",
        )
        self.assertEqual(self.groups.calls, [])

    async def nuclear_preview(self):
        from botsky.adapters.local import CollectingTransport

        await self.command("/admin xp-dar --objetivo owner 5000")
        receipt, result = await self.command("/admin nuclear-preparar")
        self.assertEqual(result.code, "nuclear_preview")
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 1
        return result.data["draft_id"]

    async def test_nuclear_publication_role_snapshot_and_single_charge(self):
        from botsky.adapters.local import CollectingTransport

        self.app.nuclear_enabled = True
        await self.command("/admin xp-dar --objetivo owner 5000")
        prepared, result = await self.command("/admin nuclear-preparar")
        identifier = result.data["draft_id"]
        self.assertEqual(
            self.receive("/admin nuclear-confirmar " + identifier).result.code,
            "nuclear_preview_required",
        )
        self.app.deliver(prepared.id, CollectingTransport())
        self.now += 1
        receipt, result = await self.command("/admin nuclear-confirmar " + identifier)
        self.assertEqual(result.data["counts"], {"accepted": 2})
        self.assertEqual(result.data["state"], "completed")
        self.assertEqual(len(self.groups.calls), 2)
        self.assertEqual(
            self.rows("SELECT balance,reserved FROM wallets WHERE actor='owner'")[0],
            {"balance": 0, "reserved": 0},
        )
        await self.command("/admin nuclear-confirmar " + identifier)
        self.assertEqual(len(self.groups.calls), 2)

    async def test_nuclear_changed_role_has_no_effect_or_charge_and_failure_refunds(self):
        self.app.nuclear_enabled = True
        identifier = await self.nuclear_preview()
        self.groups.members[1]["admin"] = True
        _, result = await self.command("/admin nuclear-confirmar " + identifier)
        self.assertEqual(result.data["counts"], {"skipped": 2})
        self.assertEqual(self.groups.calls, [])
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='owner'")[0]["balance"], 5000
        )
        self.groups.members[1]["admin"] = False
        prepared, result = await self.command("/admin nuclear-preparar")
        from botsky.adapters.local import CollectingTransport

        self.app.deliver(prepared.id, CollectingTransport())
        self.now += 1
        self.groups.outcome = "failed"
        _, result = await self.command("/admin nuclear-confirmar " + result.data["draft_id"])
        self.assertEqual(result.data["counts"], {"failed": 2})
        self.assertEqual(
            self.rows("SELECT balance,reserved FROM wallets WHERE actor='owner'")[0],
            {"balance": 5000, "reserved": 0},
        )

    async def test_nuclear_uncertainty_conserves_cost_and_skips_remaining_targets(self):
        self.app.nuclear_enabled = True
        identifier = await self.nuclear_preview()
        self.groups.outcome = "uncertain"
        _, result = await self.command("/admin nuclear-confirmar " + identifier)
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(result.data["counts"], {"skipped": 1, "uncertain": 1})
        self.assertEqual(len(self.groups.calls), 1)
        self.assertEqual(
            self.rows("SELECT balance,reserved FROM wallets WHERE actor='owner'")[0],
            {"balance": 0, "reserved": 0},
        )
        await self.command("/admin nuclear-confirmar " + identifier)
        self.assertEqual(len(self.groups.calls), 1)

    async def test_nuclear_known_adapter_failure_refunds_and_cancellation_preserves_uncertainty(
        self,
    ):
        import asyncio

        self.app.nuclear_enabled = True
        identifier = await self.nuclear_preview()
        original = self.groups.change

        async def known_failure(*args):
            raise GroupError("synthetic_no_dispatch", False)

        self.groups.change = known_failure
        _, result = await self.command("/admin nuclear-confirmar " + identifier)
        self.assertEqual(result.data["counts"], {"failed": 1, "skipped": 1})
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='owner'")[0]["balance"], 5000
        )
        self.groups.change = original
        prepared, result = await self.command("/admin nuclear-preparar")
        from botsky.adapters.local import CollectingTransport

        self.app.deliver(prepared.id, CollectingTransport())
        self.now += 1
        identifier = result.data["draft_id"]
        self.groups.pause = asyncio.Event()
        receipt = self.receive("/admin nuclear-confirmar " + identifier)
        worker = asyncio.create_task(self.app.jobs.run_pending())
        await asyncio.wait_for(self.groups.pause.wait(), 2)
        self.receive("/cancelar " + receipt.id)
        await asyncio.wait_for(worker, 2)
        self.assertEqual(
            self.rows("SELECT state FROM nuclear_drafts WHERE id=?", (identifier,))[0]["state"],
            "uncertain",
        )
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='owner'")[0]["balance"], 0
        )
        self.assertEqual(self.result(receipt).code, "request_cancelled")

    async def test_moderation_setting_routes_preserve_target_and_owner_guards(self):
        settings = []

        async def setting(chat, name, value):
            settings.append((chat, name, value))
            return "accepted"

        self.groups.setting = setting
        for command, action in (
            ("/admin promover alice", "promote"),
            ("/admin degradar alice", "demote"),
        ):
            _, result = await self.command(command)
            self.assertEqual(result.code, "admin_completed")
            self.assertEqual(self.groups.calls[-1], ("group", action, "alice-target"))
        count = len(self.groups.calls)
        _, protected = await self.command("/admin degradar owner")
        self.assertEqual(protected.status, "failed")
        self.assertEqual(len(self.groups.calls), count)
        for command in ("/admin silenciar", "/admin desilenciar", "/admin cerrar", "/admin abrir"):
            self.assertEqual(self.receive(command, actor="alice").result.code, "owner_required")
            _, result = await self.command(command)
            self.assertEqual(result.code, "admin_completed")
        self.assertEqual(
            settings,
            [
                ("group", "announcement", True),
                ("group", "announcement", False),
                ("group", "locked", True),
                ("group", "locked", False),
            ],
        )

    async def test_nuclear_draft_cancel_has_no_cost_or_target_effect(self):
        self.app.nuclear_enabled = True
        identifier = await self.nuclear_preview()
        before = self.rows("SELECT balance,reserved FROM wallets WHERE actor='owner'")
        _, cancelled = await self.command("/admin nuclear-cancelar " + identifier)
        self.assertEqual(cancelled.status, "ok")
        self.assertEqual(self.groups.calls, [])
        self.assertEqual(
            self.rows("SELECT balance,reserved FROM wallets WHERE actor='owner'"), before
        )
        _, refused = await self.command("/admin nuclear-confirmar " + identifier)
        self.assertEqual(refused.data["state"], "cancelled")
        self.assertEqual(self.groups.calls, [])

    async def test_xp_remove_by_verified_target_preserves_exact_delta(self):
        await self.command("/admin xp-dar --objetivo alice 10")
        before = self.rows("SELECT balance FROM wallets WHERE actor='alice'")[0]["balance"]
        _, result = await self.command("/admin xp-quitar --objetivo alice 3")
        self.assertEqual(result.code, "admin_xp_changed")
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor='alice'")[0]["balance"], before - 3
        )


class GroupsHTTPTest(IsolatedAsyncioTestCase):
    async def test_real_client_proofs_roles_changed_setting_and_ack_target(self):
        group = "12345-67890@g.us"
        bot = "999999999@s.whatsapp.net"
        target = "111111111@s.whatsapp.net"
        calls = []
        locked = False

        def handle(request):
            nonlocal locked
            calls.append(request)
            if "findGroupInfos" in request.url.path:
                return httpx.Response(
                    200,
                    json={
                        "id": group,
                        "restrict": locked,
                        "announce": False,
                        "participants": [
                            {"id": bot, "admin": "admin"},
                            {"id": target, "lid": "person1@lid", "admin": None},
                        ],
                    },
                )
            if "updateSetting" in request.url.path:
                locked = json.loads(request.content)["action"] == "locked"
                return httpx.Response(200, json={})
            return httpx.Response(
                200, json={"updateParticipants": [{"jid": target, "status": "200"}]}
            )

        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(http.aclose)
        client = Groups("http://127.0.0.1:1", "fixture", "synthetic", [bot], client=http)
        snapshot = await client.snapshot(group)
        self.assertTrue(snapshot["bot_is_admin"])
        self.assertIn("person1@lid", snapshot["participants"][1]["aliases"])
        self.assertEqual(await client.change(group, "remove", target), "accepted")
        self.assertEqual(await client.setting(group, "locked", True), "accepted")
        posted = [json.loads(r.content) for r in calls if r.method == "POST"]
        self.assertEqual(posted[0]["participants"], [target])
        self.assertEqual(posted[1]["groupJid"], group)

    async def test_unknown_role_alias_conflict_and_mismatched_mutation_ack_fail_closed(self):
        group = "12345-67890@g.us"
        bot = "999999999@s.whatsapp.net"
        target = "111111111@s.whatsapp.net"
        data = {
            "id": group,
            "participants": [{"id": bot, "admin": "admin"}, {"id": target, "admin": None}],
        }

        def handle(request):
            if request.method == "POST":
                return httpx.Response(
                    200, json={"updateParticipants": [{"jid": bot, "status": "200"}]}
                )
            return httpx.Response(200, json=copy.deepcopy(data))

        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(http.aclose)
        client = Groups("http://127.0.0.1:1", "fixture", "synthetic", [bot], client=http)
        self.assertEqual(await client.change(group, "remove", target), "uncertain")
        data["participants"][1].pop("admin")
        with self.assertRaises(GroupError):
            await client.snapshot(group)
        data["participants"][1]["admin"] = None
        data["participants"][1]["phoneNumber"] = "222222222@s.whatsapp.net"
        with self.assertRaises(GroupError):
            await client.snapshot(group)
