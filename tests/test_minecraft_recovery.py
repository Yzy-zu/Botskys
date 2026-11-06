"""Crash recovery on synthetic world files, no network."""

import json
from unittest import TestCase
from unittest.mock import patch

from test_minecraft_mod_worker import A, ModsWorkerTest, worker


class RecoveryTest(TestCase):
    setUp = ModsWorkerTest.setUp
    pack = ModsWorkerTest.pack
    call = ModsWorkerTest.call

    def test_restore_exact_bytes_and_refuse_concurrent_edits(self):
        self.pack(A, "own")
        original = b"[  ]\n"
        self.path.write_bytes(original)
        self.call("enable_mod", A)
        self.path.write_text('[{"pack_id":"external"}]')
        self.assertEqual(self.call("recover")["code"], "recovery_conflict")
        self.path.write_text(
            json.dumps([{"pack_id": A, "version": [1, 0, 0]}], ensure_ascii=False, indent=2)
        )
        self.assertTrue(self.call("recover")["recovered"])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.call("recover")["changed"])

    def test_partial_write_survives_process_restart_and_prevents_start(self):
        self.pack(A, "own")
        original = self.path.read_bytes()
        real = worker._atomic_json

        def fail(path, rows, **kwargs):
            real(path, rows, **kwargs)
            if path == self.path:
                raise OSError("synthetic crash after replacement")

        with patch.object(worker, "_atomic_json", fail):
            with self.assertRaises(OSError):
                self.call("enable_mod", A)
        self.assertEqual(self.call("start")["code"], "recovery_required")
        self.assertTrue(self.call("recover")["recovered"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_idempotent_request_preserves_last_recovery_point(self):
        self.pack(A, "own")
        before = self.path.read_bytes()
        self.call("enable_mod", A)
        self.call("enable_mod", A)
        self.call("recover")
        self.assertEqual(self.path.read_bytes(), before)


# Imported TestCase must not be collected twice by unittest.
del ModsWorkerTest
