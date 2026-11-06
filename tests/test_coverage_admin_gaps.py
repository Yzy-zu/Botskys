"""Brechas de cobertura R8: solo SQLite temporal y doble local de grupos."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_roulette import GroupFixture

from botsky.adapters.local import LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result


class AdminCoverageGapsTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793962800000
        self.settings = Settings(
            self.root,
            "admin-gap-lab",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.groups = GroupFixture()
        self.groups.members[1]["aliases"] = ["alice", "alice-target"]
        self.app = Application(self.settings, clock=lambda: self.now, groups=self.groups)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)

    async def test_expel_targets_verified_member_and_duplicate_receipt_does_not_repeat_effect(self):
        incoming = self.adapter.incoming(
            "same-expel", "owner", "group", "/admin expulsar alice", is_group=True
        )

        first = self.app.receive(incoming)
        replay = self.app.receive(replace(incoming, received_ms=self.now + 1))
        self.assertTrue(replay.duplicate)
        self.assertEqual(first.id, replay.id)

        await self.app.jobs.run_pending()
        await self.app.jobs.run_pending()

        self.assertEqual(first.result.code, "job_queued")
        self.assertEqual(self.groups.calls, [("group", "remove", "alice-target")])
        db = self.app.store.connect()
        try:
            receipt = db.execute(
                "SELECT state,result_json FROM inbox WHERE id=?", (first.id,)
            ).fetchone()
            jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE id=?", (first.id,)).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(receipt["state"], "completed")
        result = Result.from_json(receipt["result_json"])
        self.assertEqual((result.status, result.code), ("ok", "admin_completed"))
        self.assertEqual(jobs, 1)
