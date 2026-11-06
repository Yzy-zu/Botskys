"""Real local archives and distinct backup deadlines, without remote effects."""

import importlib.util
import json
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from botsky.adapters import minecraft

spec = importlib.util.spec_from_file_location(
    "backup_worker", Path(__file__).parents[1] / "ops/minecraft_worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class BackupWorkerTest(TestCase):
    def test_larger_budget_real_archive_and_failed_partial_cleanup(self):
        self.assertEqual(worker.MAX_BACKUP_BYTES, 50 * 1024**3)
        self.assertLess(worker.BACKUP_TIMEOUT_SECONDS + 30, minecraft.BACKUP_TIMEOUT_SECONDS)
        self.assertLess(minecraft.BACKUP_TIMEOUT_SECONDS, 1800)
        with TemporaryDirectory() as name:
            root = Path(name)
            data = root / "data"
            data.mkdir()
            payload = b"synthetic fixture" * 1000
            (data / "world.bin").write_bytes(payload)

            def run(*args, **kwargs):
                return json.dumps({"Status": "exited"})

            result = worker._backup(root, data, "fixture", run=run)
            with tarfile.open(root / "zhana-backups" / result["backup"]) as archive:
                self.assertEqual(archive.extractfile("data/world.bin").read(), payload)
            with patch.object(worker, "MAX_BACKUP_BYTES", 1):
                with self.assertRaisesRegex(worker.WorkerError, "backup_size_limit"):
                    worker._backup(root, data, "fixture", run=run)
            self.assertEqual(len(list((root / "zhana-backups").iterdir())), 1)


class BackupTransportTest(IsolatedAsyncioTestCase):
    async def test_only_backup_gets_extended_ssh_deadline(self):
        deadlines = []

        async def exchange(argv, payload, *, timeout_seconds=None):
            deadlines.append(timeout_seconds)
            return b'{"status":"ok"}'

        with patch.object(minecraft, "_run_ssh", exchange):
            backend = minecraft.MinecraftRemote(
                minecraft.MinecraftConfig("fixture", "fixture", "/srv/fixture", "/srv/worker.py")
            )
            await backend.change("backup")
            await backend.query("status")
        self.assertEqual(deadlines, [1260, None])
