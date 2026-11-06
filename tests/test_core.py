"""Recorrido real en SQLite temporal con actores/chats sintéticos y sin red."""

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import DeliveryAck
from botsky.store import Store


class Crash(BaseException):
    pass


class CoreTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.now = int(datetime.fromisoformat("2026-11-06T02:00:00+00:00").timestamp() * 1000)
        self.settings = Settings(
            root,
            "lab",
            "lab-account",
            1,
            root / "private/test.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.clock = lambda: self.now
        self.adapter = LocalAdapter(self.settings, self.clock)
        self.app = Application(self.settings, clock=self.clock)
        self.transport = CollectingTransport()
        self.sequence = 0

    def incoming(self, text, *, actor="alice", chat="private-alice", **kw):
        self.sequence += 1
        return self.adapter.incoming(str(self.sequence), actor, chat, text, **kw)

    def receive(self, text, *, actor="alice", chat="private-alice", **kw):
        return self.app.receive(self.incoming(text, actor=actor, chat=chat, **kw))

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def test_vertical_notes_literal_filter_and_real_delivery_receipt(self):
        literal = "Comprar cable azul; /daily\n--pan  "
        saved = self.receive("/nota guardar " + literal)
        self.assertEqual(saved.result.code, "note_saved")
        self.assertEqual(self.rows("SELECT text FROM notes")[0]["text"], literal)
        self.receive("/nota guardar otro asunto")
        found = self.receive("/notas cable")
        self.assertEqual(found.result.data["total"], 1)
        self.assertEqual(found.result.data["items"][0]["text"], literal)
        self.assertEqual(self.app.deliver(found.id, self.transport), 1)
        self.assertEqual(self.app.deliver(found.id, self.transport), 0)
        self.assertEqual(self.rows("SELECT accepted FROM note_views")[0]["accepted"], 1)
        self.assertEqual(
            self.rows("SELECT state FROM outbox WHERE receipt_id=?", (found.id,))[0]["state"],
            "accepted",
        )

    def test_duplicate_restart_collision_and_concurrent_writes(self):
        incoming = self.incoming("/nota guardar una vez")
        first = self.app.receive(incoming)
        restarted = Application(self.settings, clock=self.clock)
        restarted.router.parse = lambda _: (_ for _ in ()).throw(AssertionError("no reinterpretar"))
        again = restarted.receive(replace(incoming, received_ms=self.now + 1000))
        self.assertTrue(again.duplicate)
        self.assertEqual(again.result, first.result)
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(self.app.receive, [incoming] * 8))
        self.assertTrue(all(r.result.code == "note_saved" for r in receipts))
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)
        collision = self.app.receive(replace(incoming, text="/nota guardar diferente"))
        self.assertEqual(collision.result.code, "message_conflict")
        other_actor = self.app.receive(
            replace(incoming, scope=replace(incoming.scope, actor="bob"))
        )
        self.assertEqual(other_actor.result.code, "message_conflict")
        self.assertNotIn("una vez", other_actor.result.text)

    def test_recovery_executes_saved_canonical_command_without_reparsing(self):
        incoming = self.incoming("/nota guardar /admin nuclear-confirmar EJEMPLO")
        pending = self.app.receive(incoming, execute=False)
        self.assertEqual(pending.state, "queued")
        restarted = Application(self.settings, clock=self.clock)
        restarted.router.parse = lambda _: (_ for _ in ()).throw(AssertionError("no reinterpretar"))
        self.assertEqual(restarted.recover()[0].result.code, "note_saved")
        self.assertEqual(restarted.recover(), [])
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)
        self.assertEqual(len(self.rows("SELECT * FROM effects")), 1)

    def test_rollback_between_note_and_receipt_preserves_atomicity(self):
        pending = self.app.admit(self.incoming("/nota guardar atómica"))
        original = self.app._handle

        def crash_after_write(*args):
            original(*args)
            raise Crash()

        with patch.object(self.app, "_handle", crash_after_write), self.assertRaises(Crash):
            self.app.process(pending.id)
        self.assertEqual(self.rows("SELECT * FROM notes"), [])
        self.assertEqual(self.rows("SELECT * FROM effects"), [])
        self.assertEqual(self.rows("SELECT state FROM inbox")[0]["state"], "queued")
        self.assertEqual(self.app.process(pending.id).result.code, "note_saved")

    def test_scope_and_epoch_isolation_with_same_group(self):
        self.receive("/nota guardar privada")
        self.receive("/nota guardar grupo", chat="group", is_group=True)
        self.assertEqual(
            self.receive("/notas", actor="bob", chat="group", is_group=True).result.data["total"], 0
        )
        self.assertEqual(self.receive("/notas", chat="other-private").result.data["total"], 0)
        self.assertEqual(self.receive("/notas").result.data["total"], 1)
        app = Application(replace(self.settings, epoch=2), clock=self.clock)
        old = self.incoming("/nota guardar vieja")
        self.app.receive(old)
        self.assertEqual(app.receive(old).result.code, "stale_epoch")
        self.assertEqual(app.receive(self.incoming("/notas")).result.data["total"], 0)

    def test_freshness_cutoff_history_future_and_silent_noncommands(self):
        for kw, code in [
            ({"source_ms": self.now - 2000}, "before_cutoff"),
            ({"historical": True}, "before_cutoff"),
            ({"source_ms": self.now + 31000}, "future_message"),
        ]:
            result = self.receive("/nota guardar no", **kw)
            self.assertEqual(result.result.code, code)
        stale_settings = replace(self.settings, activation_ms=self.now - 1000000)
        stale = Application(stale_settings, clock=self.clock)
        self.assertEqual(
            stale.receive(
                self.incoming("/nota guardar no", source_ms=self.now - 301000)
            ).result.code,
            "stale_message",
        )
        for text in ("guardar una nota", "> /nota guardar no", "2", "sí", "alguien descarga esto"):
            self.assertEqual(self.receive(text).state, "ignored")
        self.assertEqual(self.rows("SELECT * FROM notes"), [])
        self.assertEqual(self.rows("SELECT * FROM outbox"), [])

    def test_permissions_before_dispatch_and_revalidated_after_admission(self):
        self.assertEqual(
            self.receive("/nota guardar no", actor="stranger").result.code, "actor_denied"
        )
        self.assertEqual(
            self.receive("/nota guardar no", chat="bad-group", is_group=True).result.code,
            "group_denied",
        )
        self.assertEqual(self.receive("/admin advertir TARGET").result.code, "owner_required")
        self.assertEqual(self.receive("/bot modo activo").result.code, "owner_required")
        pending = self.app.admit(self.incoming("/nota guardar revocada"))
        self.app.settings = replace(self.settings, friends=frozenset())
        self.assertEqual(self.app.process(pending.id).result.code, "actor_denied")
        self.assertEqual(self.rows("SELECT * FROM notes"), [])
        self.assertEqual(self.app.deliver(pending.id, self.transport), 0)

    def test_cancel_exact_pending_own_request_and_status_hides_foreign(self):
        pending = self.app.admit(self.incoming("/nota guardar cancelar"))
        status = self.receive("/estado " + pending.id).result
        self.assertEqual(status.code, "receipt_state")
        self.assertEqual(status.data["id"], pending.id)
        self.assertEqual(status.data["state"], "queued")
        foreign = self.receive("/cancelar " + pending.id, actor="bob")
        self.assertEqual(foreign.result.code, "receipt_not_found")
        self.assertEqual(
            self.receive("/estado " + pending.id, actor="bob").result.code, "receipt_not_found"
        )
        self.assertEqual(self.receive("/cancelar " + pending.id).result.status, "cancelled")
        self.assertEqual(self.app.process(pending.id).state, "cancelled")
        self.assertEqual(self.rows("SELECT * FROM notes"), [])
        done = self.receive("/nota guardar terminada")
        self.assertEqual(self.receive("/cancelar " + done.id).result.code, "already_finished")
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)

    def test_notes_filter_requires_accepted_current_own_view(self):
        for i in range(7):
            self.receive("/nota guardar cable " + str(i))
        self.receive("/nota guardar otro")
        first = self.receive("/notas cable")
        self.assertEqual(self.receive("/notas --pagina 2").result.code, "note_filter_required")
        self.app.deliver(first.id, self.transport)
        second = self.receive("/notas --pagina 2")
        self.assertEqual(second.result.data["query"], "cable")
        self.assertEqual(len(second.result.data["items"]), 2)
        self.assertEqual(
            self.receive("/notas --pagina 2", actor="bob").result.code, "note_filter_required"
        )
        self.now += 900001
        self.assertEqual(self.receive("/notas --pagina 2").result.code, "note_filter_required")
        self.assertEqual(self.receive("/notas --pagina 2 cable").result.data["query"], "cable")
        self.assertEqual(self.receive("/notas %_").result.data["total"], 0)

    def test_uncertain_delivery_restart_does_not_repeat_effect_or_send(self):
        saved = self.receive("/nota guardar una")

        class TimeoutTransport:
            def send(self, part):
                raise TimeoutError()

        self.assertEqual(self.app.deliver(saved.id, TimeoutTransport()), 0)
        self.assertEqual(self.rows("SELECT state FROM outbox")[0]["state"], "uncertain")
        restarted = Application(self.settings, clock=self.clock)
        self.assertEqual(restarted.deliver(saved.id, self.transport, retry_failed=True), 0)
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)
        self.assertEqual(len(self.transport.parts), 0)

    def test_part_receipts_restart_and_explicit_known_failure_retry(self):
        saved = self.receive("/nota guardar " + "x" * 7900)
        found = self.receive("/notas")
        claimed = self.app.store.claim_part(found.id, self.settings, self.now)
        part, revision = claimed
        self.app.store.finish_part(
            part, revision, self.settings, "accepted", "LOCAL-1", None, self.now
        )
        sending = self.app.store.claim_part(found.id, self.settings, self.now)
        self.assertIsNotNone(sending)
        self.assertEqual(self.app.store.recover_deliveries(self.settings, self.now), 1)
        self.assertEqual(self.app.deliver(found.id, self.transport), 0)
        self.assertEqual(self.rows("SELECT accepted FROM note_views")[0]["accepted"], 0)

        class Reject:
            def send(self, part):
                return DeliveryAck(False)

        self.app.deliver(saved.id, Reject())
        self.assertEqual(self.app.deliver(saved.id, self.transport), 0)
        self.assertEqual(self.app.deliver(saved.id, self.transport, retry_failed=True), 1)
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)

    def test_newer_unaccepted_view_does_not_replace_delivered_filter(self):
        old = self.receive("/notas cable")
        self.app.deliver(old.id, self.transport)
        self.receive("/notas otro")
        result = self.receive("/notas --pagina 2")
        self.assertEqual(result.result.data.get("query"), "cable")

    def test_delivery_cas_prevents_parallel_send_and_keeps_network_outside_transaction(self):
        found = self.receive("/notas")
        app = self.app

        class Reentrant:
            calls = 0

            def send(inner, part):
                inner.calls += 1
                # Otra transacción debe poder completar mientras el transporte trabaja.
                result = self.receive("/nota guardar otra transacción")
                self.assertEqual(result.result.code, "note_saved")
                return DeliveryAck(True, "local-reentrant")

        transport = Reentrant()
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(lambda _: app.deliver(found.id, transport), range(2)))
        self.assertEqual(sum(counts), 1)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)

    def test_config_and_foreign_database_are_rejected_without_migration(self):
        example = Path("config.example.toml").read_text()
        path = self.settings.root / "config.toml"
        path.write_text(example)
        self.assertEqual(Settings.load(path).database.parent, self.settings.root / "private")
        path.write_text(example.replace("private/botsky.sqlite3", "../foreign.sqlite3"))
        with self.assertRaises(ValueError):
            Settings.load(path)
        path.write_text(example.replace("epoch = 1", "epoch = true"))
        with self.assertRaises(ValueError):
            Settings.load(path)
        foreign = self.settings.root / "foreign.sqlite3"
        db = sqlite3.connect(foreign)
        db.executescript("CREATE TABLE foreign_table(id); PRAGMA user_version=31;")
        db.close()
        before = hashlib.sha256(foreign.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            Store(foreign)
        self.assertEqual(hashlib.sha256(foreign.read_bytes()).hexdigest(), before)
