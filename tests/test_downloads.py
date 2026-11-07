"""Clientes técnicos con dobles de red; motores reales sobre video sintético local."""

import asyncio
import json
import socket
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

import httpx

from botsky.adapters.downloads import NetworkDownloads
from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.adapters.web import NetworkWeb
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result
from botsky.domains.downloads import validate_url
from botsky.engines.downloads import DownloadOption, _allowed_host, _proxy, download_source
from botsky.engines.media_edit import MediaEditor
from botsky.engines.process import MediaError, run_process
from botsky.engines.web_results import SearchError, parse_results

W3 = "https://media.w3.org/2010/05/bunny/trailer.mp4"


class FixtureDownloads:
    enabled = True
    adult_sources_enabled = False

    def __init__(self, video):
        self.video = video
        self.searches = []
        self.downloads = []

    async def search(self, query, source, directory):
        self.searches.append((query, source))
        return (DownloadOption(W3, "Video sintético /nota guardar NO"),)

    async def resolve_spotify(self, url, directory):
        return "Título Spotify sintético"

    async def download(self, url, options, directory):
        self.downloads.append(url)
        return await MediaEditor(directory / "local-fixture").convert_file(self.video, options)


class DownloadsTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = int(datetime.fromisoformat("2026-11-06T04:00:00+00:00").timestamp() * 1000)
        self.settings = Settings(
            self.root,
            "download-lab",
            "local",
            1,
            self.root / "private/test.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset(),
        )
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.sequence = 0
        self.video = self.root / "fixture.mp4"
        await run_process(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=96x64:r=10",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(self.video),
            ],
            15,
        )
        self.backend = FixtureDownloads(self.video)
        self.app = Application(self.settings, clock=lambda: self.now, downloads=self.backend)

    def receive(self, text, actor="alice"):
        self.sequence += 1
        return self.app.receive(self.adapter.incoming(str(self.sequence), actor, "private", text))

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def result(self, identifier):
        return Result.from_json(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (identifier,))[0]["result_json"]
        )

    async def test_view_accepted_scope_choice_format_and_previous_reuses_file(self):
        search = self.receive("/dl buscar mp4 --hasta 0.8 CABLE literal")
        await self.app.jobs.run_pending()
        result = self.result(search.id)
        self.assertEqual(result.code, "download_choices")
        view = result.data["view_id"]
        self.assertEqual(
            self.receive("/dl elegir " + view + " 1").result.code, "download_view_unavailable"
        )
        self.app.deliver(search.id, CollectingTransport())
        self.assertEqual(
            self.receive("/dl elegir " + view + " 1", actor="bob").result.code,
            "download_view_unavailable",
        )
        self.assertEqual(
            self.receive("/dl elegir " + view + " 2").result.code, "download_choice_out_of_range"
        )
        choice = self.receive("/dl elegir " + view + " 1")
        await self.app.jobs.run_pending()
        downloaded = self.result(choice.id)
        self.assertEqual(downloaded.code, "download_ready")
        self.assertEqual(self.backend.searches, [("CABLE literal", "youtube")])
        self.assertEqual(self.backend.downloads, [W3])
        self.app.deliver(choice.id, CollectingTransport())
        self.app.downloads = None
        previous = self.receive("/dl anterior mp3")
        self.assertEqual(previous.result.code, "job_queued")
        await self.app.jobs.run_pending()
        converted = self.result(previous.id)
        self.assertEqual(converted.code, "media_edited")
        path = self.app.artifacts.path(converted.data["artifacts"][0])
        info = json.loads(
            await run_process(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "json",
                    str(path),
                ],
                10,
            )
        )
        self.assertEqual(info["streams"][0]["codec_name"], "mp3")
        self.assertEqual(len(self.backend.downloads), 1)
        self.assertEqual(self.rows("SELECT * FROM notes"), [])

    async def test_spotify_requires_real_choice_and_view_expiration_is_enforced(self):
        receipt = self.receive("/dl mp3 https://open.spotify.com/track/0123456789abcdefghijkl")
        await self.app.jobs.run_pending()
        result = self.result(receipt.id)
        self.assertEqual(result.code, "download_choices")
        self.assertIn("Spotify", result.text)
        self.assertEqual(self.backend.downloads, [])
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 900001
        self.assertEqual(
            self.receive("/dl elegir " + result.data["view_id"] + " 1").result.code,
            "download_view_unavailable",
        )

    async def test_remote_clients_are_disabled_and_sources_do_not_fall_back(self):
        self.app.downloads = NetworkDownloads()
        self.assertEqual(self.receive("/dl mp4 " + W3).result.code, "downloads_not_configured")
        self.app.downloads = self.backend
        self.assertEqual(
            self.receive("/dl buscar mp4 --fuente vimeo ejemplo").result.code,
            "source_search_unavailable",
        )
        self.assertEqual(self.backend.searches, [])
        self.assertEqual(
            self.receive(
                "/dl mp4 https://www.pornhub.com/view_video.php?viewkey=synthetic"
            ).result.code,
            "adult_sources_disabled",
        )
        self.assertEqual(self.rows("SELECT * FROM jobs"), [])

    async def test_url_contract_all_sources_and_no_private_or_arbitrary_url(self):
        sources = {
            "youtube": "https://www.youtube.com/watch?v=AbCDEfgHI12",
            "w3": W3,
            "dailymotion": "https://www.dailymotion.com/video/synthetic",
            "vimeo": "https://vimeo.com/12345678",
            "facebook": "https://www.facebook.com/reel/12345678",
            "instagram": "https://www.instagram.com/reel/Synthetic01/",
            "tiktok": "https://www.tiktok.com/@synthetic/video/12345678",
            "pornhub": "https://www.pornhub.com/view_video.php?viewkey=synthetic",
            "xnxx": "https://www.xnxx.com/video-synthetic/example",
        }
        for source, url in sources.items():
            self.assertEqual(download_source(validate_url(url, adult=True)), source)
        self.assertIn(
            "open.spotify.com",
            validate_url("https://open.spotify.com/track/0123456789abcdefghijkl"),
        )
        for url in (
            "https://127.0.0.1/a",
            "https://[::1]/a",
            "https://www.youtube.com.evil.test/watch?v=AbCDEfgHI12",
            "http://www.youtube.com/watch?v=AbCDEfgHI12",
            "https://www.youtube.com:8443/watch?v=AbCDEfgHI12",
            "https://u:p@www.youtube.com/watch?v=AbCDEfgHI12",
            "file:///tmp/a",
            "https://www.youtube.com/playlist?list=synthetic",
            "https://soundcloud.com/synthetic/song",
            "https://www.soundcloud.com/synthetic/song",
            "https://on.soundcloud.com/abc123",
            "https://api-v2.soundcloud.com/tracks/123",
        ):
            with self.assertRaises(MediaError):
                validate_url(url)

        for host in (
            "soundcloud.com",
            "www.soundcloud.com",
            "on.soundcloud.com",
            "api-v2.soundcloud.com",
            "api.soundcloud.com",
            "a-v2.sndcdn.com",
            "playback.media-streaming.soundcloud.cloud",
        ):
            self.assertFalse(_allowed_host(host, "youtube"))

    async def test_connect_proxy_rejects_private_dns_and_pins_public_address_without_remote_io(
        self,
    ):
        loop = asyncio.get_running_loop()
        async with _proxy("youtube") as proxy:
            reader, writer = await asyncio.open_connection("127.0.0.1", urlsplit(proxy).port)
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
            with (
                patch.object(loop, "getaddrinfo", AsyncMock(return_value=addresses)),
                patch("botsky.engines.downloads.asyncio.open_connection", AsyncMock()) as outbound,
            ):
                writer.write(b"CONNECT www.youtube.com:443 HTTP/1.1\r\n\r\n")
                await writer.drain()
                self.assertNotIn(b"200", await asyncio.wait_for(reader.read(), 1))
                outbound.assert_not_awaited()
            writer.close()
            await writer.wait_closed()
        async with _proxy("youtube") as proxy:
            reader, writer = await asyncio.open_connection("127.0.0.1", urlsplit(proxy).port)
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
            with (
                patch.object(loop, "getaddrinfo", AsyncMock(return_value=addresses)),
                patch(
                    "botsky.engines.downloads.asyncio.open_connection",
                    AsyncMock(side_effect=OSError("mock unavailable")),
                ) as outbound,
            ):
                writer.write(b"CONNECT www.youtube.com:443 HTTP/1.1\r\n\r\n")
                await writer.drain()
                await asyncio.wait_for(reader.read(), 1)
                outbound.assert_awaited_once_with("8.8.8.8", 443)
            writer.close()
            await writer.wait_closed()

    async def test_real_http_client_with_mock_rss_keeps_site_and_terms_and_rejects_irrelevance(
        self,
    ):
        seen = []
        rss = b"<rss><channel><item><title>Python docs</title><link>https://docs.python.org/3/</link><description>Python documentation</description></item><item><title>Noise</title><link>https://example.org/noise</link><description>Other</description></item></channel></rss>"

        def respond(request):
            seen.append(request)
            return httpx.Response(200, content=rss)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            self.app.web = NetworkWeb(enabled=True, client=client)
            request = self.receive("/buscar --terminos Python Python site:python.org")
            await self.app.jobs.run_pending()
            result = self.result(request.id)
            self.assertEqual(result.code, "web_results")
            self.assertEqual(
                [item["url"] for item in result.data["items"]], ["https://docs.python.org/3/"]
            )
            self.assertEqual(seen[0].url.params["q"], 'Python site:python.org "Python"')
            empty = self.receive("/buscar --terminos inexistente Python site:python.org")
            await self.app.jobs.run_pending()
            self.assertEqual(self.result(empty.id).code, "web_empty")
            self.assertIn("No encontré", self.result(empty.id).text)
        with self.assertRaises(SearchError):
            parse_results(b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///tmp/no">]><rss/>', "test")

    async def test_url_webm_and_embedded_srt_are_real_files_without_remote_download(self):
        captions = self.root / "fixture.srt"
        captions.write_text("1\n00:00:00,000 --> 00:00:00,800\nSubtítulo sintético literal.\n")
        video = self.root / "subtitled.mp4"
        await run_process(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-i",
                str(self.video),
                "-i",
                str(captions),
                "-c",
                "copy",
                "-c:s",
                "mov_text",
                "-metadata:s:s:0",
                "language=spa",
                str(video),
            ],
            15,
        )
        self.backend.video = video
        for command, suffix in (("/dl webm " + W3, "webm"), ("/dl srt --idioma es " + W3, "srt")):
            receipt = self.receive(command)
            await self.app.jobs.run_pending()
            result = self.result(receipt.id)
            self.assertEqual(result.code, "download_ready")
            artifact = self.app.artifacts.path(result.data["artifacts"][0])
            if suffix == "srt":
                self.assertIn("Subtítulo sintético literal.", artifact.read_text())
            else:
                info = json.loads(
                    await run_process(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-show_entries",
                            "stream=codec_type",
                            "-of",
                            "json",
                            str(artifact),
                        ],
                        10,
                    )
                )
                self.assertIn("video", {s["codec_type"] for s in info["streams"]})
        self.assertEqual(self.backend.downloads, [W3, W3])

    async def test_clip_options_flow_through_url_search_and_retained_source(self):
        for container in ("mp3", "mp4", "webm"):
            receipt = self.receive("/dl " + container + " --hasta 0.8 " + W3)
            await self.app.jobs.run_pending()
            result = self.result(receipt.id)
            self.assertEqual(result.code, "download_ready")
            output = self.app.artifacts.path(result.data["artifacts"][0])
            info = json.loads(
                await run_process(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "json",
                        str(output),
                    ],
                    10,
                )
            )
            self.assertLess(float(info["format"]["duration"]), 0.95)
            self.app.deliver(receipt.id, CollectingTransport())
        previous = self.receive("/dl anterior mp3 --desde 0.1 --hasta 0.5")
        await self.app.jobs.run_pending()
        retained = self.result(previous.id)
        self.assertEqual(retained.code, "media_edited")
        info = json.loads(
            await run_process(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(self.app.artifacts.path(retained.data["artifacts"][0])),
                ],
                10,
            )
        )
        self.assertAlmostEqual(float(info["format"]["duration"]), 0.4, delta=0.15)
        no_subs = self.receive("/dl anterior srt --idioma es")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(no_subs.id).code, "subtitles_unavailable")
        previous_options = json.loads(
            self.rows("SELECT arguments_json FROM jobs WHERE id=?", (no_subs.id,))[0][
                "arguments_json"
            ]
        )
        self.assertEqual(previous_options["subtitle_language"], "es")
        search = self.receive("/dl buscar srt --idioma es consulta sintética")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(search.id).code, "download_choices")
        search_options = json.loads(
            self.rows("SELECT arguments_json FROM jobs WHERE id=?", (search.id,))[0][
                "arguments_json"
            ]
        )
        self.assertEqual(search_options["subtitle_language"], "es")
        self.assertEqual(self.backend.downloads, [W3, W3, W3])
