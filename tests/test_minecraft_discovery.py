"""Docker mount discovery against synthetic inspect fixtures."""

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

spec = importlib.util.spec_from_file_location(
    "discovery_worker", Path(__file__).parents[1] / "ops/minecraft_worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class MinecraftDiscoveryTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "volumes" / "bedrock"
        self.data = self.source
        (self.data / "worlds" / "Example").mkdir(parents=True)
        (self.data / "server.properties").write_text("level-name=Example\n")

    def inspect(self, source=None, mounts=None, workdir="/srv/server"):
        value = {
            "Id": "container-id",
            "Image": "sha256:image-id",
            "Config": {"WorkingDir": workdir},
            "Mounts": mounts
            or [
                {"Source": str(self.base / "volumes"), "Destination": "/srv"},
                {"Source": str(source or self.source), "Destination": "/srv/server"},
            ],
        }
        return json.dumps(value)

    def test_chooses_most_specific_mount_and_returns_internal_path(self):
        result = worker.discover("fixture", self.base, run=lambda *a, **kw: self.inspect())
        self.assertEqual(result["data_path"], self.data)
        self.assertEqual(result["active_world"], "Example")
        self.assertEqual(result["fingerprint"]["image"], "sha256:image-id")
        self.assertEqual(result["fingerprint"]["id"], "container-id")
        public = worker.handle(
            {
                "action": "discover",
                "params": {},
                "container": "fixture",
                "base_path": str(self.base),
            },
            run=lambda *a, **kw: self.inspect(),
        )
        self.assertNotIn(str(self.base), json.dumps(public))

    def test_mount_outside_base_fails_closed(self):
        with TemporaryDirectory() as outside:
            with self.assertRaisesRegex(worker.WorkerError, "data_mount_outside_base"):
                worker.discover(
                    "fixture",
                    self.base,
                    run=lambda *a, **kw: self.inspect(source=outside),
                )

    def test_symlinked_mount_source_fails_closed(self):
        link = self.base / "linked"
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(worker.WorkerError, "unsafe_data_mount"):
            worker.discover(
                "fixture",
                self.base,
                run=lambda *a, **kw: self.inspect(source=link),
            )

    def test_missing_active_world_fails_closed(self):
        (self.data / "server.properties").write_text("level-name=Missing\n")
        with self.assertRaisesRegex(worker.WorkerError, "world_unavailable"):
            worker.discover("fixture", self.base, run=lambda *a, **kw: self.inspect())
