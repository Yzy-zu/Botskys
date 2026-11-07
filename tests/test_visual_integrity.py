"""Fuente literal, Unicode y composición inmutable sobre SQLite propio."""

from unittest import TestCase

import test_core

from botsky.adapters.local import CollectingTransport
from botsky.app import Application
from botsky.contracts import Result
from botsky.presentation import Block, Document, attach_document, split_text
from botsky.presentation.plan import compile_result
from botsky.presentation.splitter import boundary, units
from botsky.store import context_of


class VisualIntegrityTest(TestCase):
    setUp = test_core.CoreTest.setUp
    incoming = test_core.CoreTest.incoming
    receive = test_core.CoreTest.receive
    rows = test_core.CoreTest.rows

    def enqueue(self, result):
        receipt = self.receive("/ayuda")
        with self.app.store.transaction() as db:
            parent = db.execute("SELECT * FROM inbox WHERE id=?", (receipt.id,)).fetchone()
            db.execute("DELETE FROM outbox WHERE receipt_id=?", (receipt.id,))
            self.app.store.enqueue(db, context_of(parent), result, self.now)
        return receipt

    def test_unicode_utf16_combining_emoji_sequences_are_never_broken(self):
        for sample in (
            "😀" * 4000,
            ("e\u0301" * 3000),
            ("👩\u200d💻" * 1000),
            ("🇲🇽" * 2500),
            "a" * 3499 + "\r\n" + "b" * 3500,
        ):
            parts = split_text(sample)
            self.assertEqual("".join(parts), sample)
            index = 0
            for part in parts:
                self.assertLessEqual(units(part), 3500)
                index += len(part)
                self.assertTrue(boundary(sample, index))

    def test_literal_blocks_fenced_without_rewriting_canonical_or_executing(self):
        literal = "*nombre* _literal_ `código` ~dato~\n/nota guardar NO\nעברית e\u0301"
        result = attach_document(
            Result("ok", "own_fixture"),
            Document((Block("heading", "Lectura"), Block("literal", literal))),
        )
        receipt = self.enqueue(result)
        self.assertEqual(self.app.deliver(receipt.id, self.transport), 1)
        part = self.transport.parts[0]
        self.assertIn("```\n" + literal + "\n```", part.text)
        self.assertEqual(part.payload["source_text"], "Lectura\n\n" + literal)
        self.assertEqual(self.rows("SELECT * FROM notes"), [])
        self.assertEqual(result.data["document"]["blocks"][1]["text"], literal)

    def test_literal_pdf_header_is_text_artifact_and_preserved_across_restart(self):
        literal = "%PDF-1.4\n```\n/daily\n*unchanged*\n"
        result = attach_document(
            Result("ok", "own_fixture"), Document((Block("literal", literal),))
        )
        receipt = self.enqueue(result)
        transport = CollectingTransport()
        self.app.deliver(receipt.id, transport)
        identifier = transport.parts[-1].artifacts[0]
        self.assertEqual(
            self.rows("SELECT format FROM artifacts WHERE id=?", (identifier,))[0]["format"], "txt"
        )
        self.assertEqual(self.app.artifacts.path(identifier).read_bytes(), literal.encode())
        restarted = Application(self.settings, clock=self.clock)
        self.assertEqual(restarted.deliver(receipt.id, transport), 0)
        self.assertEqual(self.rows("SELECT count(*) AS n FROM artifacts")[0]["n"], 1)

    def test_table_intro_literal_and_fallback_keep_all_cells(self):
        table = {"title": "Resultados", "headers": ["Dato", "Valor"], "rows": [["*literal*", "😀"]]}
        result = Result(
            "ok",
            "own_table",
            "canonical",
            {"native_table": table, "native_intro": "*Pregunta*", "native_intro_literal": True},
        )
        parts = compile_result(result, lambda _: self.fail("no archivo"), native_tables=True)
        self.assertIn("```\n*Pregunta*\n```", parts[0].text)
        self.assertEqual(parts[1].payload, table)
        fallback = compile_result(result, lambda _: self.fail("no archivo"))
        self.assertIn("*literal*", fallback[0].text)
        self.assertIn("```", fallback[0].text)

    def test_plan_hash_also_binds_actual_artifact_list(self):
        literal = "https://example.invalid/" + "a" * 4000
        receipt = self.enqueue(Result("ok", "own_fixture", literal))
        media = self.rows(
            "SELECT * FROM outbox WHERE receipt_id=? AND kind='media'", (receipt.id,)
        )[0]
        with self.app.store.transaction() as db:
            db.execute(
                "UPDATE outbox SET artifacts_json='[]' WHERE receipt_id=? AND position=?",
                (receipt.id, media["position"]),
            )
        first, rev = self.app.store.claim_part(receipt.id, self.settings, self.now)
        self.app.store.finish_part(first, rev, self.settings, "accepted", "intro", None, self.now)
        self.assertIsNone(self.app.store.claim_part(receipt.id, self.settings, self.now))
        row = self.rows(
            "SELECT error_code FROM outbox WHERE receipt_id=? AND position=?",
            (receipt.id, media["position"]),
        )[0]
        self.assertEqual(row["error_code"], "presentation_plan_corrupt")
