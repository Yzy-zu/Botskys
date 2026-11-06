"""Pack state on real fixture files; no SSH, server or existing user data."""

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "mods_worker", Path(__file__).parents[1] / "ops/minecraft_worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


class ModsWorkerTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.world = self.data / "worlds/Test"
        self.world.mkdir(parents=True)
        (self.data / "server.properties").write_text("level-name=Test\n")
        self.path = self.world / "world_behavior_packs.json"
        self.path.write_text("[]\n")

    def pack(self, identity, folder, *, dependencies=(), version=None):
        target = self.data / "behavior_packs" / folder
        target.mkdir(parents=True)
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "header": {
                        "uuid": identity,
                        "name": "Same name",
                        "version": version or [1, 0, 0],
                    },
                    "dependencies": list(dependencies),
                }
            )
        )

    def call(self, action, name=None):
        return worker.handle(
            {
                "action": action,
                "params": {} if name is None else {"name": name},
                "container": "fixture",
                "base_path": str(self.root),
            },
            discover_layout=False,
            run=lambda *a, **kw: json.dumps({"Status": "exited"}),
        )

    def test_enable_disable_verified_idempotence_preserves_other_rows(self):
        self.pack(A, "first")
        original = [{"pack_id": B, "version": [1, 0, 0], "subpack": "keep"}]
        self.path.write_text(json.dumps(original))
        enabled = self.call("enable_mod", A)
        self.assertTrue(enabled["changed"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        self.assertTrue(enabled["restart_required"])
        self.assertFalse(enabled["loaded_known"])
        self.assertEqual(json.loads(self.path.read_text())[0], original[0])
        before = self.path.stat().st_mtime_ns
        self.assertFalse(self.call("enable_mod", A)["changed"])
        self.assertEqual(before, self.path.stat().st_mtime_ns)
        self.assertTrue(self.call("mods")["installed"][0]["active"])
        self.assertTrue(self.call("disable_mod", A)["changed"])
        self.assertEqual(json.loads(self.path.read_text()), original)

    def test_dependencies_and_ambiguous_names_rejected_without_writes(self):
        self.pack(A, "first")
        self.pack(B, "second", dependencies=[{"uuid": A, "version": [1, 0, 0]}])
        before = self.path.read_bytes()
        for name, code in (
            ("Same name", "pack_not_unique_or_installed"),
            (B, "pack_dependency_not_configured"),
        ):
            result = self.call("enable_mod", name)
            self.assertEqual(result["code"], code)
            self.assertIs(result["dispatched"], False)
            self.assertEqual(self.path.read_bytes(), before)
        self.call("enable_mod", A)
        self.call("enable_mod", B)
        self.assertEqual(self.call("disable_mod", A)["code"], "pack_required_by_configured")
        self.call("disable_mod", B)
        self.assertTrue(self.call("disable_mod", A)["changed"])

    def test_version_conflict_is_not_active_or_silent_success(self):
        self.pack(A, "first", version=[2, 0, 0])
        rows = [{"pack_id": A, "version": [1, 0, 0], "subpack": "preserve"}]
        self.path.write_text(json.dumps(rows))
        listing = self.call("mods")
        self.assertFalse(listing["installed"][0]["active"])
        self.assertFalse(listing["behavior"][0]["installed"])
        self.assertEqual(self.call("enable_mod", A)["code"], "pack_version_conflict")
        self.assertEqual(json.loads(self.path.read_text()), rows)

    def test_players_waits_for_delayed_log_without_resending_command(self):
        calls = []
        reads = 0

        def run(argv, **kwargs):
            nonlocal reads
            calls.append(argv)
            if argv[1] == "inspect":
                return "running"
            if argv[1] == "logs":
                reads += 1
                if reads == 1:
                    return ""
                return datetime.now(UTC).isoformat() + " There are 0/10 players online:"
            return ""

        with (
            patch.object(worker.Path, "home", return_value=self.root),
            patch.object(worker.time, "sleep"),
        ):
            result = worker._players(self.root, "fixture", run=run)
        self.assertTrue(result["players_known"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(sum(argv[1] == "exec" for argv in calls), 1)
        self.assertEqual(reads, 2)

    def test_reenable_restores_subpack_and_original_stack_position(self):
        self.pack(A, "first")
        original = [
            {"pack_id": A, "version": [1, 0, 0], "subpack": "2_e"},
            {"pack_id": B, "version": [1, 0, 0]},
        ]
        self.path.write_text(json.dumps(original))
        self.call("disable_mod", A)
        history = self.world / ".botsky-disabled-packs.json"
        self.assertEqual(history.stat().st_mode & 0o777, 0o600)
        self.call("enable_mod", A)
        self.assertEqual(json.loads(self.path.read_text()), original)
        self.assertEqual(json.loads(history.read_text()), [])

    def test_only_current_startup_positive_pack_stack_is_observed(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[1] == "inspect":
                return json.dumps({"Status": "running", "StartedAt": "2026-11-06T21:00:00Z"})
            return f"Pack Stack - [00] fixture (id: {A}, version: 1.0.0) @ behavior_packs/fixture"

        self.assertEqual(worker._observed_packs("fixture", run=run), {(A, "1.0.0")})
        self.assertEqual(calls[-1][3], "2026-11-06T21:00:00Z")

    def test_mutual_dependency_pair_toggles_together(self):
        self.pack(A, "first", dependencies=[{"uuid": B, "version": [1, 0, 0]}])
        self.pack(B, "second", dependencies=[{"uuid": A, "version": [1, 0, 0]}])
        enabled = self.call("enable_mod", A)
        self.assertEqual(len(enabled["affected"]), 2)
        self.assertEqual({row["pack_id"] for row in json.loads(self.path.read_text())}, {A, B})
        disabled = self.call("disable_mod", B)
        self.assertEqual(len(disabled["affected"]), 2)
        self.assertEqual(json.loads(self.path.read_text()), [])

    def test_cycle_restores_order_with_unrelated_row_after_pair(self):
        self.pack(A, "first", dependencies=[{"uuid": B, "version": [1, 0, 0]}])
        self.pack(B, "second", dependencies=[{"uuid": A, "version": [1, 0, 0]}])
        original = [
            {"pack_id": B, "version": [1, 0, 0], "subpack": "keep"},
            {"pack_id": A, "version": [1, 0, 0]},
            {"pack_id": "33333333-3333-4333-8333-333333333333", "version": [1, 0, 0]},
        ]
        self.path.write_text(json.dumps(original))
        self.call("disable_mod", A)
        self.call("enable_mod", A)
        self.assertEqual(json.loads(self.path.read_text()), original)

    def test_running_container_is_not_proof_game_is_ready(self):
        state = {"Status": "running", "StartedAt": "2026-11-06T21:00:00Z"}
        self.assertEqual(
            worker._game_status(
                "fixture",
                state,
                run=lambda *a, **kw: "free(): invalid next size (normal)",
            ),
            "failed",
        )
        self.assertEqual(
            worker._game_status("fixture", state, run=lambda *a, **kw: "Loading level"),
            "starting",
        )
        self.assertEqual(
            worker._game_status("fixture", state, run=lambda *a, **kw: "Server started."),
            "ready",
        )

    def test_game_status_reads_native_error_written_to_stderr(self):
        original_popen = worker.subprocess.Popen

        def popen_with_real_log_process(argv, **kwargs):
            self.assertTrue(kwargs["stderr"] == worker.subprocess.STDOUT)
            return original_popen(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.write('warning\\n' * 40000); print('Server started.'); print('free(): invalid next size', file=sys.stderr)",
                ],
                **kwargs,
            )

        def run_real_log(argv, **kwargs):
            self.assertEqual(kwargs["max_output_bytes"], worker.MAX_LOG_BYTES)
            return worker._run(argv, **kwargs)

        with patch.object(worker.subprocess, "Popen", side_effect=popen_with_real_log_process):
            result = worker._game_status(
                "fixture",
                {"Status": "running", "StartedAt": "2026-11-06T21:00:00Z"},
                run=run_real_log,
            )
        self.assertEqual(result, "failed")

    def test_large_startup_log_still_confirms_ready(self):
        original_popen = worker.subprocess.Popen

        def popen_with_real_log_process(argv, **kwargs):
            return original_popen(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.write('warning\\n' * 40000); print('Server started.')",
                ],
                **kwargs,
            )

        def run_real_log(argv, **kwargs):
            self.assertEqual(kwargs["max_output_bytes"], worker.MAX_LOG_BYTES)
            return worker._run(argv, **kwargs)

        with patch.object(worker.subprocess, "Popen", side_effect=popen_with_real_log_process):
            result = worker._game_status(
                "fixture",
                {"Status": "running", "StartedAt": "2026-11-06T21:00:00Z"},
                run=run_real_log,
            )
        self.assertEqual(result, "ready")
