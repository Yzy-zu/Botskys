"""Integración optativa: secretos propios, una clave y efectos protegidos por defecto."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx

from botsky.adapters.groups import GroupError
from botsky.adapters.messenger import MessageError
from botsky.config import Settings
from botsky.integrations import Integrations, read_profile


class ConfiguredIntegrationsTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / "private"
        self.private.mkdir()
        self.path = self.private / "integrations.json"
        self.profile = {
            "version": 1,
            "gemini": {"key": "synthetic-one-key", "model": "explicit-test-model"},
            "asr": {"key": "synthetic-asr", "model": "explicit-asr"},
            "evolution": {
                "base_url": "http://127.0.0.1:1",
                "api_key": "synthetic-evolution",
                "instance": "test",
            },
            "drive": {},
            "contacts": [],
            "mutations_enabled": False,
        }
        self.save()
        self.settings = Settings(
            self.root,
            "configured-fixture",
            "own",
            1,
            self.private / "test.sqlite3",
            1,
            "owner",
            frozenset(),
            frozenset(),
            bot_ids=frozenset({"1234567890@s.whatsapp.net"}),
        )

    def save(self):
        self.path.write_text(json.dumps(self.profile))
        self.path.chmod(0o600)

    async def test_explicit_composition_makes_no_network_requests_and_blocks_remote_writes(self):
        seen = []

        async def handler(request):
            seen.append(request)
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with Integrations(self.settings, self.path, http=http) as app:
                self.assertTrue(app.gemini.available)
                self.assertTrue(app.asr.available)
                self.assertIsNone(app.calls)
                with self.assertRaises(MessageError) as error:
                    await app.messenger.send("synthetic", "text", text="must not send")
                self.assertFalse(error.exception.uncertain)
                with self.assertRaises(GroupError) as error:
                    await app.groups.change("123456789@g.us", "remove", "1234567890@s.whatsapp.net")
                self.assertFalse(error.exception.uncertain)
        self.assertEqual(seen, [])

    async def test_profile_rejects_pool_unknown_fields_and_unsafe_permissions(self):
        self.profile["gemini"]["keys"] = ["forbidden-pool"]
        self.save()
        with self.assertRaises(ValueError):
            read_profile(self.path)
        self.profile["gemini"].pop("keys")
        self.profile["env"] = "must not discover global environment"
        self.save()
        with self.assertRaises(ValueError):
            read_profile(self.path)
        self.profile.pop("env")
        self.save()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            read_profile(self.path)

    async def test_symlink_profile_is_rejected_and_defaults_never_read_zhana(self):
        link = self.private / "linked.json"
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            Integrations(self.settings, link)
        with self.assertRaises(FileNotFoundError):
            Integrations(self.settings, self.private / "missing.json")
        self.assertNotIn("/home/petrov/zhana", self.path.read_text())
