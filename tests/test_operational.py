"""Permisos por función/destino y revocación antes de efectos, con HTTP sintético."""

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx
from test_packs import library_fixture

from botsky.adapters.drive import DriveError
from botsky.adapters.groups import GroupError
from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.adapters.messenger import MessageError
from botsky.adapters.minecraft import MinecraftRemoteError
from botsky.config import Settings
from botsky.integrations import Integrations
from botsky.operational import OperationalPolicy

OWNER = "525511112222@s.whatsapp.net"
FRIEND = "525533334444@s.whatsapp.net"
BOT = "525544445555@s.whatsapp.net"
GROUP = "123456789012345@g.us"
OTHER = "999999999999999@g.us"


class OperationalTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1793988000000
        self.settings = Settings(
            self.root,
            "ops",
            BOT,
            1,
            self.root / "private/test.sqlite3",
            self.now - 1000,
            OWNER,
            frozenset({FRIEND}),
            frozenset({GROUP, OTHER}),
            bot_ids=frozenset({BOT}),
        )
        self.path = self.root / "private/providers.json"
        self.path.parent.mkdir()
        self.profile = {
            "version": 1,
            "gemini": {"key": "single-key", "model": "explicit-model"},
            "asr": {},
            "drive": {"folder_id": "synthetic-folder"},
            "evolution": {
                "base_url": "http://127.0.0.1:1",
                "instance": "fixture",
                "api_key": "fixture",
            },
            "contacts": [{"name": "Owner", "jid": OWNER}],
            "permissions": {
                "version": 1,
                "gallery": {"enabled": True, "send": False, "chats": [OWNER, GROUP]},
            },
        }
        library_fixture(self.root)
        self.requests = []

        async def handler(request):
            self.requests.append(request)
            if "/message/" in request.url.path:
                return httpx.Response(200, json={"key": {"id": "synthetic-ack"}})
            raise AssertionError("unexpected request")

        self.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(self.http.aclose)
        self.save()
        self.sequence = 0

    def save(self):
        self.path.write_text(json.dumps(self.profile))
        self.path.chmod(0o600)

    def receive(self, app, text, actor=OWNER, chat=OWNER, group=False):
        self.sequence += 1
        incoming = LocalAdapter(self.settings, lambda: self.now).incoming(
            str(self.sequence), actor, chat, text, is_group=group
        )
        return app.receive(incoming)

    def rows(self, app, query, args=()):
        with app.store.transaction() as db:
            return [dict(r) for r in db.execute(query, args)]

    async def test_composed_catalog_is_readable_without_any_send_permission(self):
        async with Integrations(self.settings, self.path, http=self.http) as app:
            app.clock = lambda: self.now
            result = self.receive(app, "/pack catalogo")
            self.assertEqual(result.result.code, "pack_catalog")
            self.assertEqual(result.result.data["items"][0]["count"], 6)
            self.assertFalse(app.photo_transport.available)
            buy = self.receive(app, "/pack comprar sintetico")
            self.assertEqual(buy.result.code, "operation_not_enabled")
            self.assertFalse(self.rows(app, "SELECT * FROM gallery_orders"))
            self.assertFalse(self.requests)

    async def test_gallery_send_independent_of_recados_and_preserves_confirmation_charge_and_scope(
        self,
    ):
        self.profile["permissions"]["gallery"]["send"] = True
        self.save()
        async with Integrations(self.settings, self.path, http=self.http) as app:
            app.clock = lambda: self.now
            app.jobs.clock = lambda: self.now
            app.daily_roll = lambda: 1
            self.assertTrue(app.photo_transport.available)
            self.assertFalse(app.messenger.available)
            with self.assertRaises(MessageError):
                await app.messenger.send(OWNER, "text", text="blocked")
            self.receive(app, "/daily")
            offer = self.receive(app, "/pack comprar sintetico")
            self.assertEqual(offer.result.code, "pack_offer")
            identifier = offer.result.data["purchase_id"]
            self.assertEqual(
                self.receive(app, "/pack confirmar " + identifier).result.code,
                "pack_preview_required",
            )
            app.deliver(offer.id, CollectingTransport())
            self.now += 1
            confirmation = self.receive(app, "/pack confirmar " + identifier)
            await app.jobs.run_pending()
            final = json.loads(
                self.rows(app, "SELECT result_json FROM inbox WHERE id=?", (confirmation.id,))[0][
                    "result_json"
                ]
            )
            self.assertEqual(
                final["data"]["state"],
                "completed",
            )
            self.assertTrue(3 <= len(self.requests) <= 5)
            bodies = [json.loads(r.content) for r in self.requests]
            self.assertTrue(all(b["number"] == OWNER and b["viewOnce"] for b in bodies))
            self.assertEqual(self.receive(app, "/saldo").result.data["balance"], 850)
            self.receive(app, "/pack confirmar " + identifier)
            await app.jobs.run_pending()
            self.assertEqual(len(self.requests), len(bodies))
            with self.assertRaises(MessageError):
                await app.photo_transport.send_photo(
                    "525577778888@s.whatsapp.net", b"bad", "image/png"
                )

    async def test_method_permissions_deny_before_oauth_http_and_ssh(self):
        self.profile["permissions"].update(
            drive={"read": False, "write": False},
            groups={"read": False, "write": False, "chats": [GROUP]},
            minecraft={"read": False, "write": False},
        )
        self.profile["minecraft"] = {
            "host_alias": "synthetic",
            "container": "fixture",
            "base_path": "/synthetic",
            "worker_path": "/synthetic/worker.py",
            "use_sudo": False,
        }
        self.save()
        async with Integrations(self.settings, self.path, http=self.http) as app:
            for method, args, error in [
                (app.drive.storage_quota, (), DriveError),
                (app.drive.generate_id, (), DriveError),
                (app.groups.snapshot, (GROUP,), GroupError),
                (app.groups.change, (GROUP, "remove", FRIEND), GroupError),
                (app.minecraft.query, ("status",), MinecraftRemoteError),
                (app.minecraft.change, ("start",), MinecraftRemoteError),
            ]:
                with self.assertRaises(error) as caught:
                    await method(*args)
                self.assertFalse(caught.exception.uncertain)
        self.assertEqual(self.requests, [])

    async def test_recados_targets_and_group_chats_are_checked_independently(self):
        self.profile["permissions"].update(
            messages={"send": True, "targets": [OWNER]},
            groups={"read": True, "write": True, "chats": [GROUP]},
        )
        self.save()
        async with Integrations(self.settings, self.path, http=self.http) as app:
            self.assertEqual(
                await app.messenger.send(OWNER, "text", text="synthetic"), "synthetic-ack"
            )
            with self.assertRaises(MessageError):
                await app.messenger.send(FRIEND, "text", text="blocked")
            with self.assertRaises(GroupError):
                await app.groups.snapshot(group=OTHER)
            with self.assertRaises(GroupError):
                await app.groups.change(OTHER, "remove", FRIEND)
            self.assertEqual(len(self.requests), 1)

    async def test_policy_revocation_retires_queued_purchase_without_debit_or_delivery(self):
        self.profile["permissions"]["gallery"]["send"] = True
        self.save()
        async with Integrations(self.settings, self.path, http=self.http) as app:
            app.clock = lambda: self.now
            app.jobs.clock = lambda: self.now
            app.daily_roll = lambda: 1
            self.receive(app, "/daily")
            offer = self.receive(app, "/pack comprar sintetico")
            app.deliver(offer.id, CollectingTransport())
            self.now += 1
            receipt = self.receive(app, "/pack confirmar " + offer.result.data["purchase_id"])
            revoked = deepcopy(self.profile)
            revoked["permissions"]["gallery"]["send"] = False
            app.operations = OperationalPolicy.build(revoked, self.settings)
            await app.jobs.run_pending()
            self.assertEqual(
                self.rows(app, "SELECT state FROM jobs WHERE id=?", (receipt.id,))[0]["state"],
                "cancelled",
            )
            self.assertEqual(self.receive(app, "/saldo").result.data["balance"], 1000)
            self.assertEqual(self.requests, [])

    async def test_explicit_games_and_nuclear_scope_never_enlarge_general_group_access(self):
        profile = deepcopy(self.profile)
        profile["permissions"].update(
            messages={"send": True, "targets": [OWNER, FRIEND]},
            groups={"read": True, "write": True, "chats": [GROUP]},
            roulette={"chats": [GROUP], "allow_admins": False},
            nuclear={"enabled": True, "chats": [GROUP]},
        )
        policy = OperationalPolicy.build(profile, self.settings)
        self.assertEqual(policy.document["roulette"]["chats"], [GROUP])
        from botsky.contracts import CommandContext, Scope

        allowed = CommandContext("receipt", "ops", BOT, Scope(OWNER, GROUP, True), 1, 0)
        denied = CommandContext("receipt", "ops", BOT, Scope(OWNER, OTHER, True), 1, 0)
        self.assertIsNone(policy.authorize(allowed, "manage_admin.nuclear_confirm"))
        self.assertEqual(
            policy.authorize(denied, "manage_admin.nuclear_confirm").code, "operation_not_enabled"
        )
        self.assertIsNone(policy.authorize(denied, "manage_admin.nuclear_cancel"))

    async def test_unknown_fields_wildcards_global_switch_and_inconsistent_flags_rejected(self):
        variants = [
            {"mutations_enabled": True},
            {"permissions": {"surprise": True}},
            {"permissions": {"groups": {"write": True, "read": False}}},
            {"permissions": {"gallery": {"send": True, "enabled": False}}},
            {"permissions": {"delivery": {"chats": ["*"]}}},
            {"permissions": {"roulette": {"chats": [GROUP]}}},
            {"permissions": {"nuclear": {"enabled": True, "chats": []}}},
            {"permissions": {"minecraft": {"write": 1}}},
            {"permissions": {"messages": {"targets": ["unknown"]}}},
            {"evolution": {"delivery_enabled": False}, "permissions": {"delivery": {"send": True}}},
        ]
        for override in variants:
            profile = {**self.profile, **override}
            with self.subTest(override=override), self.assertRaises(ValueError):
                OperationalPolicy.build(profile, self.settings)
        policy = OperationalPolicy.build(self.profile, self.settings)
        document = policy.document
        document["gallery"]["send"] = True
        self.assertFalse(policy.document["gallery"]["send"])
