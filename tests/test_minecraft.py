"""R8 Minecraft: cliente SSH real con runner doble, operaciones durables locales."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from botsky.adapters.local import LocalAdapter
from botsky.adapters.minecraft import MinecraftConfig, MinecraftRemote
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result


class MinecraftTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793962800000
        self.calls = []
        self.outcome = {"status": "ok", "online": True}
        self.settings = Settings(
            self.root,
            "mc-lab",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice"}),
            frozenset({"group"}),
        )

        async def runner(argv, payload):
            self.calls.append((argv, json.loads(payload)))
            return json.dumps(self.outcome).encode()

        self.config = MinecraftConfig(
            "synthetic-server", "bedrock-lab", "/srv/synthetic", "/srv/synthetic/worker.py"
        )
        self.remote = MinecraftRemote(self.config, runner=runner)
        self.app = Application(self.settings, clock=lambda: self.now, minecraft=self.remote)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.n = 0

    def incoming(self, text, actor="owner"):
        self.n += 1
        return self.adapter.incoming(str(self.n), actor, "private", text)

    def receive(self, text, **kw):
        return self.app.receive(self.incoming(text, **kw))

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def result(self, r):
        return Result.from_json(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (r.id,))[0]["result_json"]
        )

    async def test_permissions_console_allowlist_and_queries_before_client(self):
        self.assertEqual(self.receive("/mc parar", actor="alice").result.code, "owner_required")
        self.assertEqual(
            self.receive("/mc consola rm -rf /").result.code, "minecraft_local_validation"
        )
        self.assertEqual(
            self.receive("/mc consola list; reboot").result.code, "minecraft_local_validation"
        )
        self.assertEqual(self.calls, [])
        receipt = self.receive("/mc estado", actor="alice")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).text, "Minecraft: en línea.")
        argv, payload = self.calls[0]
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertEqual(payload["container"], "bedrock-lab")
        self.assertEqual(payload["params"], {})

    async def test_mod_literal_json_console_is_not_shell_and_duplicate_once(self):
        incoming = self.incoming('/mc mod activar "Nombre con espacios"')
        receipt = self.app.receive(incoming)
        self.app.receive(incoming)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).code, "minecraft_completed")
        self.assertEqual(self.calls[0][1]["params"], {"name": "Nombre con espacios"})
        self.assertNotIn("Nombre con espacios", " ".join(self.calls[0][0]))
        receipt = self.receive("/mc consola /list")
        await self.app.jobs.run_pending()
        self.assertIn("no hay confirmación", self.result(receipt).text)
        self.assertEqual(self.calls[-1][1]["params"], {"command": "list"})
        self.app.receive(incoming)
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.calls), 2)

    async def test_uncertain_change_blocks_next_mutation_but_status_is_available(self):
        self.outcome = {"status": "uncertain"}
        receipt = self.receive("/mc reiniciar")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).status, "uncertain")
        self.assertEqual(self.receive("/mc iniciar").result.code, "minecraft_resource_busy")
        self.outcome = {"status": "ok", "online": False}
        receipt = self.receive("/mc estado")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).text, "Minecraft: apagado.")
        self.assertEqual(len(self.calls), 2)

    async def test_revocation_after_admission_and_interrupted_dispatch_never_replays(self):
        receipt = self.receive("/mc backup")
        self.app.settings = replace(self.settings, owner="alice", friends=frozenset({"owner"}))
        await self.app.jobs.run_pending()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.result(receipt).code, "owner_required")
        self.app.settings = self.settings
        receipt = self.receive("/mc reiniciar")
        job = self.app.jobs.claim()
        self.app.jobs.mark_provider(job)
        with self.app.store.transaction() as db:
            db.execute(
                "UPDATE external_operations SET state='sending' WHERE receipt_id=?", (receipt.id,)
            )
        self.now += 1831000
        self.assertIsNone(self.app.jobs.claim())
        self.assertEqual(self.result(receipt).code, "provider_interrupted")
        self.assertEqual(self.receive("/mc parar").result.code, "minecraft_resource_busy")
        self.assertEqual(self.calls, [])

    async def test_cancel_during_remote_call_is_uncertain_and_configuration_is_explicit(self):
        gate = asyncio.Event()

        async def slow(argv, payload):
            gate.set()
            await asyncio.Event().wait()

        self.remote._runner = slow
        receipt = self.receive("/mc parar")
        worker = asyncio.create_task(self.app.jobs.run_pending())
        await asyncio.wait_for(gate.wait(), 2)
        self.receive("/cancelar " + receipt.id)
        await asyncio.wait_for(worker, 2)
        self.assertEqual(
            self.rows("SELECT state FROM external_operations")[0]["state"], "uncertain"
        )
        self.assertEqual(self.result(receipt).code, "request_cancelled")
        for config in (
            replace(self.config, host_alias="-bad"),
            replace(self.config, container="x;id"),
            replace(self.config, worker_path="/srv/../unsafe"),
        ):
            with self.assertRaises(ValueError):
                MinecraftRemote(config)

    async def test_ssh_boundary_real_local_process_json_and_timeout_release(self):
        import os
        import sys
        from unittest.mock import patch

        from botsky.adapters.minecraft import _run_ssh

        result = await _run_ssh(
            [
                sys.executable,
                "-c",
                'import sys,json; v=json.load(sys.stdin); print(json.dumps({"status":"ok","action":v["action"]}))',
            ],
            b'{"action":"status"}',
        )
        self.assertEqual(json.loads(result), {"status": "ok", "action": "status"})
        pidfile = self.root / "pid"
        program = (
            'import sys,os,time; open(sys.argv[1],"w").write(str(os.getpid())); time.sleep(30)'
        )
        with patch("botsky.adapters.minecraft.TIMEOUT_SECONDS", 0.1):
            with self.assertRaises(TimeoutError):
                await _run_ssh([sys.executable, "-c", program, str(pidfile)], b"{}")
        if pidfile.exists():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pidfile.read_text()), 0)
