"""Presentación propia: literalidad, ayuda pública y entrega durable sin red."""

from unittest import TestCase

import test_core

from botsky.commands.registry import Registry
from botsky.presentation import Block, Document, split_text


class PresentationTest(TestCase):
    setUp = test_core.CoreTest.setUp
    incoming = test_core.CoreTest.incoming
    receive = test_core.CoreTest.receive
    rows = test_core.CoreTest.rows

    # Reusar el laboratorio SQLite, sin duplicar sus pruebas.
    def test_help_and_literal_delivery_are_exact_without_technical_suffix(self):
        help_receipt = self.receive("/ayuda llamada programar")
        text = help_receipt.result.text
        self.assertIn("Solo el dueño", text)
        for internal in ("R9", "call_authorized", "LIVE_REQUEST", "implementación:", "Permiso:"):
            self.assertNotIn(internal, text)
        self.assertIn("--duracion DURACION_CON_UNIDAD", text)
        literal = "á *literal* `código`\n/nota guardar NO\nעברית e\u0301 " * 130
        with self.app.store.transaction() as db:
            from botsky.contracts import Result
            from botsky.store import context_of

            row = db.execute("SELECT * FROM inbox WHERE id=?", (help_receipt.id,)).fetchone()
            db.execute("DELETE FROM outbox WHERE receipt_id=?", (help_receipt.id,))
            self.app.store.enqueue(db, context_of(row), Result("ok", "literal", literal), self.now)
        self.app.deliver(help_receipt.id, self.transport)
        self.assertEqual("".join(p.text for p in self.transport.parts), literal)
        self.assertFalse(any("/estado " + help_receipt.id in p.text for p in self.transport.parts))
        self.assertEqual(self.app.deliver(help_receipt.id, self.transport), 0)

    def test_short_follow_never_guesses_and_retains_scope(self):
        # Admitir sin ejecutar produce un encargo vivo y propio.
        one = self.app.receive(self.incoming("/nota guardar uno"), execute=False)
        state = self.receive("/estado")
        self.assertEqual(state.result.data["id"], one.id)
        self.assertEqual(self.receive("/estado", actor="bob").result.code, "no_current_request")
        two = self.app.receive(self.incoming("/nota guardar dos"), execute=False)
        ambiguous = self.receive("/cancelar")
        self.assertEqual(ambiguous.result.code, "request_ambiguous")
        self.assertEqual(set(ambiguous.result.data["candidates"]), {one.id, two.id})
        self.assertEqual(self.receive("/cancelar " + two.id).result.code, "request_cancelled")
        self.assertEqual(self.receive("/cancelar").result.code, "request_cancelled")

    def test_public_help_categories_and_detailed_call_navigation(self):
        registry = Registry()
        self.assertIn("Archivos", registry.help())
        self.assertIn("/ayuda llamada programar", registry.help("llamada"))
        for spec in registry.specs:
            text = registry.help(" ".join(spec.path))
            self.assertNotIn("implementación:", text)
            self.assertNotIn("Permiso:", text)
            if spec.permission == "owner":
                self.assertIn("Solo el dueño", text)
        text = "uno\n\ndos\n" * 1000
        self.assertEqual("".join(split_text(text)), text)
        self.assertTrue(all(len(p) <= 3500 for p in split_text(text)))
        self.assertEqual(Document((Block("literal", "*texto* /daily"),)).text(), "*texto* /daily")

    def test_oversized_indivisible_is_retained_as_actual_text_file(self):
        from botsky.contracts import Result
        from botsky.store import context_of

        receipt = self.receive("/ayuda")
        literal = "https://example.invalid/" + "a" * 6000 + "\n**literal** e\u0301"
        with self.app.store.transaction() as db:
            row = db.execute("SELECT * FROM inbox WHERE id=?", (receipt.id,)).fetchone()
            db.execute("DELETE FROM outbox WHERE receipt_id=?", (receipt.id,))
            self.app.store.enqueue(db, context_of(row), Result("ok", "literal", literal), self.now)
        self.assertEqual(self.app.deliver(receipt.id, self.transport), 2)
        self.assertIn("contenido completo", self.transport.parts[0].text)
        artifact = self.transport.parts[1].artifacts[0]
        self.assertEqual(self.app.artifacts.path(artifact).read_text(), literal)
        self.assertEqual(self.app.artifacts.path(artifact).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.app.deliver(receipt.id, self.transport), 0)

    def test_follow_quote_of_intermediate_part_is_bound_to_actor(self):
        from botsky.contracts import Result
        from botsky.store import context_of

        receipt = self.receive("/ayuda")
        with self.app.store.transaction() as db:
            row = db.execute("SELECT * FROM inbox WHERE id=?", (receipt.id,)).fetchone()
            db.execute("DELETE FROM outbox WHERE receipt_id=?", (receipt.id,))
            self.app.store.enqueue(
                db, context_of(row), Result("ok", "literal", "párrafo\n\n" * 1000), self.now
            )
        self.app.deliver(receipt.id, self.transport)
        cited = self.rows(
            "SELECT provider_message_id FROM outbox WHERE receipt_id=? AND position=1",
            (receipt.id,),
        )[0]["provider_message_id"]
        found = self.receive("/estado", quoted_message_id=cited)
        self.assertEqual(found.result.data["id"], receipt.id)
        foreign = self.receive("/estado", actor="bob", quoted_message_id=cited)
        self.assertEqual(foreign.result.code, "request_quote_unavailable")
        self.now += 86400001
        self.assertEqual(
            self.receive("/estado", quoted_message_id=cited).result.code,
            "request_quote_unavailable",
        )
