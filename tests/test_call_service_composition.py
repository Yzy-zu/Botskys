"""Composición real del cliente y ciclo de proceso IPC propio, sin navegador."""

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx

from botsky.call_policy import CallPolicy
from botsky.call_service import ManagedCalls
from botsky.config import Settings
from botsky.integrations import Integrations

OWNER = "525511112222@s.whatsapp.net"
BOT = "525544445555@s.whatsapp.net"


class CallCompositionTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.settings = Settings(
            self.root,
            "configured",
            BOT,
            1,
            self.root / "private/test.sqlite3",
            1,
            OWNER,
            frozenset(),
            frozenset(),
            transport="evolution",
            bot_ids=frozenset({BOT}),
        )
        self.document = {
            "version": 1,
            "instance": "configured",
            "account": BOT,
            "epoch": 1,
            "owner": OWNER,
            "actors": [OWNER],
            "privateChats": [OWNER],
            "groups": [],
            "features": {"agenda": False, "incoming": False, "live": True, "outgoing": True},
            "schedule": {"timeZone": "America/Mexico_City", "startHour": 8, "endHour": 23},
        }
        self.settings = replace(self.settings, calls=CallPolicy.build(self.document, self.settings))
        self.profile = {
            "version": 1,
            "gemini": {"key": "single-key", "model": "explicit-model"},
            "asr": {},
            "drive": {},
            "evolution": {},
            "call_service": {
                "enabled": True,
                "mode": "external",
                "base_url": "http://127.0.0.1:17888",
                "token": "a" * 64,
            },
        }
        self.path = self.root / "private/providers.json"
        self.path.parent.mkdir()
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.profile))
        self.path.chmod(0o600)

    async def test_external_client_injected_revision_checked_without_call_dispatch(self):
        seen = []

        async def provider(request):
            seen.append(request.url.path)
            self.assertEqual(request.headers["authorization"], "Bearer " + "a" * 64)
            self.assertEqual(request.method, "GET")
            return httpx.Response(
                200, json={"policyRevision": self.settings.calls.revision, "ready": True}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
            composition = Integrations(self.settings, self.path, http=http)
            async with composition as app:
                self.assertIsNotNone(app.calls)
                self.assertFalse(app.calls.is_fixture)
                self.assertEqual(app.calls.policy_revision, self.settings.calls.revision)
                self.assertEqual(seen, [])
                await composition.start_calls()
                self.assertEqual(seen, ["/v1/status", "/healthz"])

    async def test_wrong_policy_and_managed_browser_permission_fail_closed(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"policyRevision": "b" * 64, "ready": True})
            )
        ) as http:
            composition = Integrations(self.settings, self.path, http=http)
            async with composition:
                with self.assertRaisesRegex(ValueError, "not_ready"):
                    await composition.start_calls()
            self.profile["call_service"].update(
                mode="managed", allow_browser_launch=False, port=0, executable="/synthetic/browser"
            )
            self.save()
            composition = Integrations(self.settings, self.path, http=http)
            async with composition as app:
                self.assertIsNone(app.calls)
                with patch(
                    "botsky.call_service.asyncio.create_subprocess_exec",
                    side_effect=AssertionError("must not spawn"),
                ):
                    with self.assertRaisesRegex(ValueError, "browser_not_authorized"):
                        await composition.start_calls()

    async def test_owned_process_ready_pipe_cleanup_and_bad_revision(self):
        config = {
            "allow_browser_launch": True,
            "token": "a" * 64,
            "executable": "/synthetic/browser",
            "port": 0,
        }
        live = {"key": "one-key", "model": "explicit-model"}
        spawn = asyncio.create_subprocess_exec
        captured = []
        script = 'import sys,json,time; p=json.loads(sys.stdin.readline()); print(json.dumps({"ready":True,"url":"http://127.0.0.1:17888","revision":REVISION}),flush=True); time.sleep(60)'

        async def child(*argv, **kwargs):
            self.assertEqual(argv[-1], "--run")
            self.assertTrue(argv[1].endswith("/calls/main.cjs"))
            self.assertNotIn("one-key", str(argv))
            process = await spawn(
                sys.executable,
                "-u",
                "-c",
                script.replace("REVISION", repr(self.settings.calls.revision)),
                **kwargs,
            )
            captured.append(process)
            return process

        service = ManagedCalls(self.settings, config, live)
        with patch("botsky.call_service.asyncio.create_subprocess_exec", child):
            self.assertEqual(await service.start(), "http://127.0.0.1:17888")
        await service.close()
        self.assertIsNotNone(captured[0].returncode)
        self.assertIsNone(service.process)

        async def bad_child(*argv, **kwargs):
            process = await spawn(
                sys.executable, "-u", "-c", script.replace("REVISION", repr("b" * 64)), **kwargs
            )
            captured.append(process)
            return process

        with patch("botsky.call_service.asyncio.create_subprocess_exec", bad_child):
            with self.assertRaisesRegex(ValueError, "invalid_ready"):
                await service.start()
        self.assertIsNotNone(captured[-1].returncode)
        self.assertIsNone(service.process)
