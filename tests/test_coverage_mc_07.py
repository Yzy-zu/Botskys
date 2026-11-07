"""Cobertura focal R11: efecto de backup limitado al runner sintético."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from botsky.adapters.local import LocalAdapter
from botsky.adapters.minecraft import MinecraftConfig, MinecraftRemote
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result


class MinecraftCoverage07Test(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793962800000
        self.calls = []

        async def runner(argv, payload):
            self.calls.append((argv, json.loads(payload)))
            return json.dumps({"status": "ok", "backup_id": "fixture-001"}).encode()

        settings = Settings(
            self.root,
            "mc-backup-coverage",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset(),
            frozenset({"group"}),
        )
        config = MinecraftConfig(
            "synthetic-server", "bedrock-lab", "/srv/synthetic", "/srv/synthetic/worker.py"
        )
        self.app = Application(
            settings,
            clock=lambda: self.now,
            minecraft=MinecraftRemote(config, runner=runner),
        )
        self.adapter = LocalAdapter(settings, lambda: self.now)

    async def test_backup_effect_reaches_only_synthetic_runner(self):
        receipt = self.app.receive(
            self.adapter.incoming("backup-1", "owner", "group", "/mc backup", is_group=True)
        )
        await self.app.jobs.run_pending()

        db = self.app.store.connect()
        try:
            row = db.execute("SELECT result_json FROM inbox WHERE id=?", (receipt.id,)).fetchone()
        finally:
            db.close()
        result = Result.from_json(row[0])
        self.assertEqual(result.code, "minecraft_completed")
        self.assertEqual(len(self.calls), 1)
        _, payload = self.calls[0]
        self.assertEqual(payload["action"], "backup")
        self.assertEqual(payload["container"], "bedrock-lab")
        self.assertEqual(payload["params"], {})
