"""Leyenda basada en archivo final real; no confundir opciones con mediciones."""

from unittest import IsolatedAsyncioTestCase

import test_media

from botsky.adapters.local import CollectingTransport
from botsky.presentation.splitter import units


class FilePresentationTest(IsolatedAsyncioTestCase):
    asyncSetUp = test_media.MediaTest.asyncSetUp
    incoming = test_media.MediaTest.incoming
    rows = test_media.MediaTest.rows
    result = test_media.MediaTest.result
    convert = test_media.MediaTest.convert
    file_of = test_media.MediaTest.file_of

    async def test_real_pdf_has_measured_page_size_and_single_immutable_captioned_part(self):
        _, receipt, result = await self.convert("/convertir pdf", self.png)
        facts = result.data["file_facts"][0]
        self.assertEqual(facts["pages"], 1)
        self.assertEqual(facts["bytes"], self.file_of(result).stat().st_size)
        transport = CollectingTransport()
        self.assertEqual(self.app.deliver(receipt.id, transport), 1)
        part = transport.parts[0]
        self.assertEqual(part.kind, "media")
        self.assertEqual(part.text, "")
        self.assertIn("Páginas: 1", part.payload["caption"])
        self.assertIn("imagen", part.payload["caption"].lower())
        self.assertLessEqual(units(part.payload["caption"]), 900)
        self.assertEqual(part.payload["name"], "Documento convertido.pdf")
        self.assertEqual(self.app.deliver(receipt.id, transport), 0)

    async def test_sticker_success_has_no_redundant_text_or_document_conversion(self):
        _, receipt, result = await self.convert("/sticker", self.png)
        transport = CollectingTransport()
        self.assertEqual(self.app.deliver(receipt.id, transport), 1)
        part = transport.parts[0]
        self.assertEqual(part.text, "")
        self.assertEqual(part.payload["caption"], "")
        self.assertEqual(
            self.rows("SELECT format FROM artifacts WHERE id=?", (part.artifacts[0],))[0]["format"],
            "webp",
        )
