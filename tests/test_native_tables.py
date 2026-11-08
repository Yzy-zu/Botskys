"""Tabla real en frontera HTTP doble, migración propia y barrera durable."""

import json
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx
import test_core
import test_runtime

from botsky.adapters.evolution import EvolutionTransport
from botsky.adapters.messenger import MessageError, Messenger
from botsky.contracts import Result
from botsky.presentation.table import NativeTable
from botsky.store import Store, context_of

TABLE = {
    "title": "Comparación",
    "headers": ["Nombre", "Valor"],
    "rows": [["*literal*", "Uno"], ["RTL עברית", "2"]],
}


class TableStoreTest(TestCase):
    setUp = test_core.CoreTest.setUp
    incoming = test_core.CoreTest.incoming
    receive = test_core.CoreTest.receive
    rows = test_core.CoreTest.rows

    def enqueue(self):
        receipt = self.receive("/ayuda")
        with self.app.store.transaction() as db:
            parent = db.execute("SELECT * FROM inbox WHERE id=?", (receipt.id,)).fetchone()
            db.execute("DELETE FROM outbox WHERE receipt_id=?", (receipt.id,))
            result = Result(
                "ok",
                "table_fixture",
                "Fuente canónica",
                {"native_table": TABLE, "native_intro": "Inicio", "native_footer": "Fin"},
            )
            self.app.store.enqueue(db, context_of(parent), result, self.now)
        return receipt

    def test_table_plan_restart_after_middle_part_does_not_recompose(self):
        self.app.store.native_tables_enabled = True
        receipt = self.enqueue()
        part, rev = self.app.store.claim_part(receipt.id, self.settings, self.now)
        self.app.store.finish_part(part, rev, self.settings, "accepted", "intro-id", None, self.now)
        restarted = Store(self.settings.database)
        table, rev = restarted.claim_part(receipt.id, self.settings, self.now)
        self.assertEqual(table.kind, "table")
        self.assertEqual(table.payload, TABLE)
        restarted.finish_part(table, rev, self.settings, "uncertain", None, "timeout", self.now)
        self.assertIsNone(restarted.claim_part(receipt.id, self.settings, self.now))
        self.assertEqual(
            self.rows(
                "SELECT state FROM outbox WHERE receipt_id=? ORDER BY position", (receipt.id,)
            ),
            [{"state": "accepted"}, {"state": "uncertain"}, {"state": "pending"}],
        )

    def test_invalid_table_preflight_and_tampered_hash_never_dispatch(self):
        with self.assertRaises(ValueError):
            NativeTable.parse({**TABLE, "rows": [["one"]]})
        with self.assertRaises(ValueError):
            NativeTable.parse({**TABLE, "rows": [["😀" * 1800, "x"]]})
        receipt = self.enqueue()
        self.assertEqual(
            self.rows("SELECT kind FROM outbox WHERE receipt_id=?", (receipt.id,)),
            [{"kind": "text"}],
        )
        with self.app.store.transaction() as db:
            db.execute("UPDATE outbox SET payload='tampered' WHERE receipt_id=?", (receipt.id,))
        self.assertIsNone(self.app.store.claim_part(receipt.id, self.settings, self.now))
        self.assertEqual(
            self.rows("SELECT error_code FROM outbox WHERE receipt_id=?", (receipt.id,))[0][
                "error_code"
            ],
            "presentation_plan_corrupt",
        )

    def test_migrate_18_preserves_canonical_data_and_pending_plan(self):
        receipt = self.enqueue()
        with self.app.store.transaction() as db:
            db.execute("DROP TABLE IF EXISTS frontend_tasks")
            db.execute("ALTER TABLE inbox DROP COLUMN input_mode")
            db.execute("DROP INDEX outbox_provider_part")
            for column in ("kind", "rich_payload_json", "visual_version", "content_sha256"):
                db.execute("ALTER TABLE outbox DROP COLUMN " + column)
            db.execute("DELETE FROM schema_version WHERE version IN (19, 20)")
            db.execute("PRAGMA user_version=18")
            before = dict(
                db.execute("SELECT * FROM outbox WHERE receipt_id=?", (receipt.id,)).fetchone()
            )
            canonical = db.execute(
                "SELECT result_json FROM inbox WHERE id=?", (receipt.id,)
            ).fetchone()[0]
        Store(self.settings.database)
        after = self.rows("SELECT * FROM outbox WHERE receipt_id=?", (receipt.id,))[0]
        self.assertEqual({k: after[k] for k in before}, before)
        self.assertEqual(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (receipt.id,))[0]["result_json"],
            canonical,
        )
        self.assertEqual(self.rows("PRAGMA integrity_check")[0]["integrity_check"], "ok")
        self.assertEqual(self.rows("PRAGMA foreign_key_check"), [])


class TableHTTPTest(IsolatedAsyncioTestCase):
    async def test_typed_payload_and_uncertain_statuses_never_retry_or_fallback(self):
        for status, payload, uncertain in (
            (201, {"key": {"id": "table-id"}}, None),
            (400, {"code": "NATIVE_TABLE_INVALID"}, False),
            (400, {"error": "untyped"}, True),
            (404, {}, False),
            (409, {}, True),
            (500, {}, True),
            (200, {}, True),
        ):
            sent = []

            async def handle(request):
                sent.append((request.url.path, json.loads(await request.aread())))
                return httpx.Response(status, json=payload)

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                api = Messenger("http://127.0.0.1:1", "fixture", "synthetic-key", client=http)
                if uncertain is None:
                    self.assertEqual(await api.send_table(test_runtime.OWNER, TABLE), "table-id")
                else:
                    with self.assertRaises(MessageError) as error:
                        await api.send_table(test_runtime.OWNER, TABLE)
                    self.assertEqual(error.exception.uncertain, uncertain)
                self.assertEqual(len(sent), 1)
                self.assertEqual(sent[0][0], "/message/sendNativeTable/fixture")
                self.assertEqual(sent[0][1]["table"], TABLE)


class TableEvolutionTest(IsolatedAsyncioTestCase):
    setUp = test_runtime.RuntimeTest.setUp
    provider = test_runtime.RuntimeTest.provider
    payload = test_runtime.RuntimeTest.payload

    async def test_evolution_sends_typed_table_and_never_text_substitute(self):
        from botsky.delivery import deliver_async

        self.profile["evolution"]["native_tables_enabled"] = True
        transport = EvolutionTransport(self.app, self.profile["evolution"], self.http)
        receipt_id = transport.enqueue(self.payload("/ayuda"))["receipt_id"]
        await transport.receive_pending()
        self.app.recover()
        with self.app.store.transaction() as db:
            parent = db.execute("SELECT * FROM inbox WHERE id=?", (receipt_id,)).fetchone()
            db.execute("DELETE FROM outbox WHERE receipt_id=?", (receipt_id,))
            self.app.store.enqueue(
                db,
                context_of(parent),
                Result("ok", "synthetic", "Fuente", {"native_table": TABLE}),
                self.now,
            )
        self.assertEqual(
            await deliver_async(
                self.app.store, receipt_id, self.settings, transport, lambda: self.now
            ),
            1,
        )
        self.assertEqual(self.sent[0]["table"], TABLE)
        self.assertEqual(self.requests[-1], "/message/sendNativeTable/provider-instance")
        self.assertEqual(
            await deliver_async(
                self.app.store, receipt_id, self.settings, transport, lambda: self.now
            ),
            0,
        )


class TableRecoveryTest(TestCase):
    setUp = test_core.CoreTest.setUp
    incoming = test_core.CoreTest.incoming
    receive = test_core.CoreTest.receive
    rows = test_core.CoreTest.rows
    enqueue = TableStoreTest.enqueue

    # Compartir solo fixture/helper, no repetir la suite de la clase base.
    def test_restart_sending_table_becomes_uncertain_and_retains_frozen_plan(self):
        self.app.store.native_tables_enabled = True
        receipt = self.enqueue()
        before = self.rows(
            "SELECT position,payload,rich_payload_json,content_sha256 FROM outbox WHERE receipt_id=? ORDER BY position",
            (receipt.id,),
        )
        intro, rev = self.app.store.claim_part(receipt.id, self.settings, self.now)
        self.app.store.finish_part(intro, rev, self.settings, "accepted", "intro", None, self.now)
        table, _ = self.app.store.claim_part(receipt.id, self.settings, self.now)
        self.assertEqual(table.kind, "table")
        restarted = Store(self.settings.database)
        self.assertEqual(restarted.recover_deliveries(self.settings, self.now), 1)
        self.assertIsNone(restarted.claim_part(receipt.id, self.settings, self.now))
        self.assertEqual(
            self.rows(
                "SELECT position,payload,rich_payload_json,content_sha256 FROM outbox WHERE receipt_id=? ORDER BY position",
                (receipt.id,),
            ),
            before,
        )

    def test_cancel_inflight_preserves_prior_ack_warns_and_suppresses_footer(self):
        self.app.store.native_tables_enabled = True
        receipt = self.enqueue()
        with self.app.store.transaction() as db:
            db.execute(
                "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,'{}','[]','pending_delivery',?)",
                (
                    "synthetic-view",
                    receipt.id,
                    self.settings.instance,
                    self.settings.account,
                    "alice",
                    "private-alice",
                    0,
                    1,
                    "download",
                    self.now + 900000,
                ),
            )
        intro, rev = self.app.store.claim_part(receipt.id, self.settings, self.now)
        self.app.store.finish_part(intro, rev, self.settings, "accepted", "intro", None, self.now)
        table, rev = self.app.store.claim_part(receipt.id, self.settings, self.now)
        cancelled = self.receive("/cancelar " + receipt.id)
        self.assertIn("ya aceptó 1 partes", cancelled.result.text)
        self.assertIn("No pude confirmar", cancelled.result.text)
        self.app.store.finish_part(
            table, rev, self.settings, "accepted", "late-table", None, self.now
        )
        self.assertIsNone(self.app.store.claim_part(receipt.id, self.settings, self.now))
        self.assertEqual(
            self.rows(
                "SELECT state FROM outbox WHERE receipt_id=? ORDER BY position", (receipt.id,)
            ),
            [{"state": "accepted"}, {"state": "uncertain"}, {"state": "cancelled"}],
        )
        self.assertEqual(
            self.rows("SELECT state FROM interactions WHERE receipt_id=?", (receipt.id,))[0][
                "state"
            ],
            "cancelled",
        )
