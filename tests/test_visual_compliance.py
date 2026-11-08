"""Verificación programática de cumplimiento de invariantes visuales móviles de WhatsApp."""

import unittest
from botsky.contracts import Result
from botsky.presentation import Block, Document, attach_document
from botsky.presentation.domains import present, size
from botsky.presentation.help import render_natural_help
from botsky.presentation.natural import adapt
from botsky.presentation.plan import compile_result
from botsky.presentation.table import NativeTable
from botsky.commands.registry import Registry


class VisualComplianceTest(unittest.TestCase):
    def test_table_fallback_renders_as_stacked_cards_without_monospace_fencing(self):
        table = NativeTable("Resumen de Ventas", ("Producto", "Precio", "Stock"), (
            ("Café", "$50", "10"),
            ("Té", "$35", "25"),
        ))
        fallback = table.fallback()
        self.assertIn("*Resumen de Ventas*", fallback)
        self.assertIn("• *Producto*: Café", fallback)
        self.assertIn("• *Precio*: $50", fallback)
        self.assertIn("• *Stock*: 10", fallback)
        self.assertIn("• *Producto*: Té", fallback)
        # Invariante visual: no debe contener cercas de código monoespaciado
        self.assertNotIn("```", fallback)

    def test_plan_compiles_fallback_table_as_paragraph_block_not_literal(self):
        table = {"title": "Horarios", "headers": ["Día", "Hora"], "rows": [["Lunes", "10:00"]]}
        res = Result("ok", "own_table", "canonical", {"native_table": table})
        parts = compile_result(res, lambda _: "art-id", native_tables=False)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].kind, "text")
        # No debe envolverse en triple acento grave en la burbuja de WhatsApp
        self.assertNotIn("```", parts[0].text)
        self.assertIn("• *Día*: Lunes", parts[0].text)

    def test_natural_mode_sanitizes_raw_bytes_and_iana_timezones(self):
        doc = Document((
            Block("paragraph", "Descarga: archivo.pdf · 2.50 MB (2621440 bytes) · 2026-11-08 15:30:00 · America/Mexico_City"),
        ))
        adapted = adapt(attach_document(Result("ok", "test_bytes_date"), doc))
        # Invariantes visuales
        self.assertIn("2.50 MB", adapted.text)
        self.assertNotIn("(2621440 bytes)", adapted.text)
        self.assertIn("08/11/2026, 03:30 p.m.", adapted.text)
        self.assertNotIn("America/Mexico_City", adapted.text)

    def test_natural_mode_condenses_validity_clauses(self):
        doc = Document((
            Block("notice", "Vigencia máxima: 5:00 desde la preparación. Vence: 2026-11-08 15:35:00 · America/Mexico_City. Opciones 1–4."),
        ))
        adapted = adapt(attach_document(Result("ok", "test_vigencia"), doc))
        self.assertIn("⏱️ _Opciones válidas por 5 min. Elige respondiendo del 1 al 4._", adapted.text)
        self.assertNotIn("Vigencia máxima:", adapted.text)

    def test_natural_mode_adds_functional_emojis_to_headings(self):
        doc = Document((
            Block("heading", "Videos"),
            Block("heading", "Notas"),
            Block("heading", "Estado de Botsky"),
            Block("heading", "Recordatorio 42 guardado"),
            Block("heading", "Tarea 7 guardada"),
            Block("heading", "Documento convertido"),
        ))
        adapted = adapt(attach_document(Result("ok", "test_emojis"), doc))
        self.assertIn("*🎬 Videos*", adapted.text)
        self.assertIn("*📝 Notas*", adapted.text)
        self.assertIn("*🤖 Estado de Botsky*", adapted.text)
        self.assertIn("*🔔 Recordatorio 42 guardado*", adapted.text)
        self.assertIn("*📋 Tarea 7 guardada*", adapted.text)
        self.assertIn("*📄 Documento convertido*", adapted.text)

    def test_overflow_to_text_file_uses_friendly_filenames_and_captions(self):
        large_literal = "a" * 4000
        res = attach_document(Result("ok", "large_fixture"), Document((Block("literal", large_literal),)))
        retained = []
        parts = compile_result(res, lambda text: retained.append(text) or "id-123")
        media_parts = [p for p in parts if p.kind == "media"]
        self.assertTrue(media_parts)
        payload = media_parts[0].payload
        self.assertEqual(payload["name"], "Documento.txt")
        self.assertEqual(payload["caption"], "📄 Archivo de texto adjunto")
        text_parts = [p for p in parts if p.kind == "text"]
        self.assertTrue(any("📄 El texto es muy extenso" in p.text for p in text_parts))

    def test_natural_help_provides_human_examples_without_cli_prefixes(self):
        help_text = render_natural_help(Registry())
        self.assertIn("Pídeme lo que necesitas con tus palabras", help_text)
        self.assertIn("«Guarda una nota: comprar pan»", help_text)
        self.assertIn("«Busca videos de gatos»", help_text)
        self.assertNotIn("/ayuda", help_text)
        self.assertNotIn("/dl", help_text)
        self.assertNotIn("/nota", help_text)


if __name__ == "__main__":
    unittest.main()
