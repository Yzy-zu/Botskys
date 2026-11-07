"""Miniaturas bajo límites con HTTP doble, sin red; cancelación en render propio."""

import asyncio
import io
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx
from PIL import Image

from botsky.engines.search_collage import MAX_THUMB_BYTES, create, fetch_thumbnail, render

URL = "https://i.ytimg.com/vi/AbCDEfgHI12/mqdefault.jpg"
CHOICE = {
    "url": "https://www.youtube.com/watch?v=AbCDEfgHI12",
    "title": "Muestra",
    "thumbnail_url": URL,
}


class ThumbnailBoundariesTest(IsolatedAsyncioTestCase):
    async def test_redirect_timeout_and_byte_limit_are_bounded_without_retry(self):
        for mode in ("redirect", "timeout", "large", "ok"):
            calls = []

            async def provider(request):
                calls.append(request)
                if mode == "redirect":
                    return httpx.Response(
                        302, headers={"location": "http://127.0.0.1/secret"}, content=b"datos"
                    )
                if mode == "timeout":
                    raise httpx.ReadTimeout("fixture")
                if mode == "large":
                    return httpx.Response(200, content=b"a" * (MAX_THUMB_BYTES + 1))
                return httpx.Response(200, content=b"fixture-sin-decodificar")

            async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
                raw = await fetch_thumbnail(URL, "youtube", client=client)
                self.assertEqual(raw, b"fixture-sin-decodificar" if mode == "ok" else None)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("cookie", calls[0].headers)
                self.assertNotIn("authorization", calls[0].headers)

    async def test_at_most_two_concurrent_thumbnails_and_partial_failure_keeps_order(self):
        live = peak = 0
        calls = []
        image = io.BytesIO()
        Image.new("RGB", (80, 40), "#c34145").save(image, "JPEG")

        async def provider(thumbnail, video):
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            calls.append(thumbnail)
            try:
                await asyncio.sleep(0.01)
                return image.getvalue() if thumbnail.endswith("0") else b"corrupta"
            finally:
                live -= 1

        choices = [
            {**CHOICE, "title": f"Opción {i}", "thumbnail_url": URL + str(i)} for i in range(6)
        ]
        with TemporaryDirectory() as directory:
            path = await create(choices, Path(directory) / "actual.jpg", provider)
            with Image.open(path) as jpeg:
                jpeg.load()
                self.assertEqual(jpeg.size, (1280, 720))
                self.assertGreater(jpeg.getpixel((50, 200))[0], jpeg.getpixel((480, 200))[0])
            self.assertEqual(peak, 2)
            self.assertEqual(calls, [c["thumbnail_url"] for c in choices])

    async def test_cancel_waits_for_bounded_render_before_scratch_can_be_deleted(self):
        entered = threading.Event()
        release = threading.Event()

        def blocked(choices, thumbnails, path):
            entered.set()
            if not release.wait(2):
                raise AssertionError("release fixture")
            return render(choices, thumbnails, path)

        with (
            TemporaryDirectory() as directory,
            patch("botsky.engines.search_collage.render", side_effect=blocked),
        ):
            task = asyncio.create_task(create([CHOICE], Path(directory) / "actual.jpg"))
            await asyncio.to_thread(entered.wait, 2)
            self.assertTrue(entered.is_set())
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue((Path(directory) / "actual.jpg").exists())
