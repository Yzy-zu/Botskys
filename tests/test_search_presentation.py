"""Collages JPEG réels, sélection durable et gardes réseau; aucun fournisseur réel."""

import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import test_downloads
from PIL import Image

from botsky.adapters.local import CollectingTransport
from botsky.contracts import DeliveryAck
from botsky.engines.downloads import DownloadOption
from botsky.engines.search_collage import decode_thumbnail, fetch_thumbnail, layout, render
from botsky.presentation.search import duration


class CollageTest(TestCase):
    def test_layouts_cover_canvas_without_overlap_and_jpeg_decodes(self):
        with TemporaryDirectory() as directory:
            for count in range(1, 7):
                mask = Image.new("L", (1280, 720))
                for x, y, width, height in layout(count):
                    self.assertIsNone(mask.crop((x, y, x + width, y + height)).getbbox())
                    mask.paste(255, (x, y, x + width, y + height))
                self.assertEqual(mask.getextrema(), (255, 255))
                choices = [
                    {
                        "url": "https://www.youtube.com/watch?v=AbCDEfgHI12",
                        "title": "Título e\u0301 *literal*",
                        "author": "Autor largo " * 60,
                        "duration": 3672,
                    }
                ] * count
                path = render(choices, [b"corrupta"] * count, Path(directory) / f"{count}.jpg")
                with Image.open(path) as image:
                    image.load()
                    self.assertEqual(image.size, (1280, 720))
                    self.assertEqual(image.format, "JPEG")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            from PIL import ImageFont

            original = ImageFont.truetype

            def missing_system_font(name, *args, **kwargs):
                if isinstance(name, str):
                    raise OSError("sin fuente del sistema")
                return original(name, *args, **kwargs)

            with patch(
                "botsky.engines.search_collage.ImageFont.truetype", side_effect=missing_system_font
            ):
                render(choices, [None] * count, Path(directory) / "fallback.jpg")
            self.assertEqual(duration(None), "Duración desconocida")
            self.assertEqual(duration(float("nan")), "Duración desconocida")
            self.assertEqual(duration(3672), "1:01:12")
            self.assertIsNone(decode_thumbnail(b"x" * (2 * 1024 * 1024 + 1)))
            raw = io.BytesIO()
            Image.new("RGB", (3000, 3000)).save(raw, "PNG")
            self.assertIsNone(decode_thumbnail(raw.getvalue()))


class SearchPresentationTest(IsolatedAsyncioTestCase):
    asyncSetUp = test_downloads.DownloadsTest.asyncSetUp
    receive = test_downloads.DownloadsTest.receive
    rows = test_downloads.DownloadsTest.rows
    result = test_downloads.DownloadsTest.result

    async def test_collage_list_barrier_partial_ack_and_short_choice(self):
        async def search(query, source, directory):
            return tuple(
                DownloadOption(
                    f"https://www.youtube.com/watch?v=AbCDEfgHI1{i}",
                    "Título íntegro " * 15,
                    252,
                    "Autor",
                )
                for i in range(4)
            )

        self.backend.search = search
        search_receipt = self.receive("/dl buscar mp4 muestra")
        await self.app.jobs.run_pending()
        result = self.result(search_receipt.id)
        self.assertEqual(len(result.data["choices"]), 4)
        self.assertEqual(result.data["choices"][0]["title"], "Título íntegro " * 15)
        self.assertIn("4:12 · Autor · YouTube", result.text)
        self.assertIn("[vista previa]", result.text)
        self.assertIn("/dl elegir NUMERO", result.text)
        self.assertEqual(self.receive("/dl elegir 1").result.code, "download_view_unavailable")

        class Partial:
            def send(self, part):
                if part.artifacts:
                    return DeliveryAck(True, "image-part")
                raise TimeoutError()

        self.assertEqual(self.app.deliver(search_receipt.id, Partial()), 1)
        self.assertEqual(self.receive("/dl elegir 1").result.code, "download_view_unavailable")
        self.assertEqual(
            self.rows("SELECT state FROM interactions WHERE kind='download'"),
            [{"state": "pending_delivery"}],
        )
        self.assertEqual(
            self.rows("SELECT id FROM interactions WHERE kind='download_previous'"), []
        )
        self.assertEqual(self.app.deliver(search_receipt.id, CollectingTransport()), 0)

    async def test_short_choice_ambiguous_and_immutable_no_search_again(self):
        first = self.receive("/dl buscar mp4 primera")
        await self.app.jobs.run_pending()
        self.app.deliver(first.id, CollectingTransport())
        second = self.receive("/dl buscar mp4 segunda")
        await self.app.jobs.run_pending()
        self.app.deliver(second.id, CollectingTransport())
        self.assertEqual(self.receive("/dl elegir 1").result.code, "selection_ambiguous")
        view = self.result(first.id).data["view_id"]
        chosen = self.receive("/dl elegir " + view + " 1")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(chosen.id).code, "download_ready")
        self.assertEqual(self.backend.downloads, [test_downloads.W3])
        self.assertEqual(len(self.backend.searches), 2)
        self.now += 900001
        self.assertEqual(self.receive("/dl elegir 1").result.code, "download_view_unavailable")

    async def test_thumbnail_private_credentials_and_ports_never_open_proxy(self):
        with patch("botsky.engines.downloads._proxy", side_effect=AssertionError("red prohibida")):
            for url in (
                "https://127.0.0.1/a",
                "https://i.ytimg.com:443/a",
                "https://u:p@i.ytimg.com/a",
                "https://evil.invalid/a",
            ):
                self.assertIsNone(await fetch_thumbnail(url, "youtube"))

    async def test_quote_selects_exact_list_from_multiple_and_rejects_partial_or_foreign(self):
        from dataclasses import replace

        first = self.receive("/dl buscar mp4 primera")
        await self.app.jobs.run_pending()
        self.app.deliver(first.id, CollectingTransport())
        second = self.receive("/dl buscar mp4 segunda")
        await self.app.jobs.run_pending()
        self.app.deliver(second.id, CollectingTransport())
        cited = self.rows(
            "SELECT provider_message_id FROM outbox WHERE receipt_id=? AND position=0", (first.id,)
        )[0]["provider_message_id"]
        self.sequence += 1
        incoming = self.adapter.incoming(
            str(self.sequence), "alice", "private", "/dl elegir 1", quoted_message_id=cited
        )
        choice = self.app.receive(incoming)
        self.assertEqual(choice.result.code, "job_queued")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(choice.id).code, "download_ready")
        self.assertEqual(self.backend.downloads, [test_downloads.W3])
        self.sequence += 1
        foreign = self.app.receive(
            replace(
                incoming, message_id=str(self.sequence), scope=replace(incoming.scope, actor="bob")
            )
        )
        self.assertEqual(foreign.result.code, "selection_quote_unavailable")

        async def multi_search(query, source, directory):
            return tuple(
                DownloadOption(
                    f"https://www.youtube.com/watch?v=AbCDEfgHI2{i}",
                    "Título íntegro " * 15,
                    252,
                    "Autor",
                )
                for i in range(4)
            )

        self.backend.search = multi_search
        third = self.receive("/dl buscar mp4 tercera")
        await self.app.jobs.run_pending()

        class Partial:
            def send(self, part):
                if part.artifacts:
                    return DeliveryAck(True, "accepted-image-only")
                raise TimeoutError()

        self.app.deliver(third.id, Partial())
        self.sequence += 1
        partial = self.app.receive(
            self.adapter.incoming(
                str(self.sequence),
                "alice",
                "private",
                "/dl elegir 1",
                quoted_message_id="accepted-image-only",
            )
        )
        self.assertEqual(partial.result.code, "selection_quote_unavailable")

    async def test_detail_retains_complete_title_author_without_refetch_or_backend(self):

        title = "Título completo *literal* " * 20
        author = "Autor largo " * 30

        async def search(query, source, directory):
            return (DownloadOption(test_downloads.W3, title, 85, author),)

        self.backend.search = search
        first = self.receive("/dl buscar mp4 muestra")
        await self.app.jobs.run_pending()
        self.app.deliver(first.id, CollectingTransport())
        self.app.downloads = None
        detail = self.receive("/dl detalle 1")
        self.assertEqual(detail.result.code, "download_detail")
        self.assertNotIn(test_downloads.W3, self.result(first.id).text)
        self.assertIn(test_downloads.W3, detail.result.text)
        self.assertIn(title, detail.result.text)
        self.assertIn(author, detail.result.text)
        self.assertEqual(detail.result.data["choice"]["url"], test_downloads.W3)
        self.assertEqual(self.backend.downloads, [])
        self.assertIn(
            "/dl elegir " + self.result(first.id).data["view_id"] + " 1", detail.result.text
        )
        self.sequence += 1
        incoming = self.adapter.incoming(str(self.sequence), "bob", "private", "/dl detalle 1")
        self.assertEqual(self.app.receive(incoming).result.code, "download_view_unavailable")
