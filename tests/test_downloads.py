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

    def test_sanitize_search_query_adult_and_general(self):
        from botsky.engines.downloads import sanitize_search_query
        self.assertEqual(sanitize_search_query("teens nopor", "adult"), "teens")
        self.assertEqual(sanitize_search_query("Oye busca videos de teens nopor en mp4", "adult"), "teens")
        self.assertEqual(sanitize_search_query("videos de maduras nopor", "adult"), "maduras")
        self.assertEqual(sanitize_search_query("colegialas porno xxx", "adult"), "colegialas")
        self.assertEqual(sanitize_search_query("videos xxx de latinas en xnxx", "adult"), "latinas")
        self.assertEqual(sanitize_search_query("chicas calientes nopor", "adult"), "chicas calientes")
        self.assertEqual(sanitize_search_query("nopor", "adult"), "popular")
        self.assertEqual(sanitize_search_query("quiero ver videos de bad bunny en youtube", "youtube"), "bad bunny")
        self.assertEqual(sanitize_search_query("videos de rock de los 80 de youtube", "youtube"), "rock de los 80")
        self.assertEqual(sanitize_search_query("cancion hotel california mp3", "youtube"), "hotel california")
        self.assertEqual(sanitize_search_query("CABLE literal", "youtube"), "CABLE literal")

    async def test_search_collage_and_choices_deliver_in_single_captioned_media_message(self):
        search = self.receive("/dl buscar mp4 --hasta 0.8 CABLE literal")
        await self.app.jobs.run_pending()
        transport = CollectingTransport()
        self.assertEqual(self.app.deliver(search.id, transport), 1)
        self.assertEqual(len(transport.parts), 1)
        part = transport.parts[0]
        self.assertEqual(part.kind, "media")
        self.assertEqual(part.text, "")
        self.assertIn("Videos", part.payload["caption"])
        self.assertIn("1. Video sintético", part.payload["caption"])
        self.assertTrue(part.payload.get("caption_frozen"))
        self.assertNotIn("siguiente", part.payload["caption"])

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
            "twitter": "https://x.com/acervodoguinhos/status/2119437133891199166/video/1",
            "pornhub": "https://www.pornhub.com/view_video.php?viewkey=synthetic",
            "xnxx": "https://www.xnxx.com/video-synthetic/example",
        }
        for source, url in sources.items():
            self.assertEqual(download_source(validate_url(url, adult=True)), source)
        self.assertEqual(
            download_source(validate_url("https://www.xnxx.es/video-synthetic/example", adult=True)),
            "xnxx",
        )
        self.assertEqual(
            download_source(validate_url("https://es.pornhub.com/view_video.php?viewkey=synthetic", adult=True)),
            "pornhub",
        )
        self.assertEqual(
            download_source(validate_url("https://twitter.com/acervodoguinhos/status/2119437133891199166")),
            "twitter",
        )
        self.assertEqual(
            download_source(validate_url("https://t.co/abcXYZ123")),
            "twitter",
        )
        self.assertIn(
            "open.spotify.com",
            validate_url("https://open.spotify.com/track/0123456789abcdefghijkl"),
        )
        for url in (
            "https://x.com/home",
            "https://x.com/acervodoguinhos",
            "https://twitter.com/settings",
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

    async def test_reaction_failure_and_late_ack_deliver_mp4_once_and_preserve_uncertain_mp4(self):
        from botsky.contracts import DeliveryAck

        search = self.receive("/dl buscar mp4 muestra")
        await self.app.jobs.run_pending()
        self.app.deliver(search.id, CollectingTransport())
        view = self.result(search.id).data["view_id"]

        # Caso 1: la reacción ⏳ falla al enviar; el MP4 debe entregarse una sola vez.
        choice1 = self.receive("/dl elegir " + view + " 1")

        class RejectReactionTransport:
            def __init__(self):
                self.media_parts = []
                self.reactions = 0

            def send(self, part):
                if part.payload.get("reaction"):
                    self.reactions += 1
                    return DeliveryAck(False, None)
                self.media_parts.append(part)
                return DeliveryAck(True, f"mp4-{len(self.media_parts)}")

        t1 = RejectReactionTransport()
        self.assertEqual(self.app.deliver(choice1.id, t1), 0)
        self.assertEqual(t1.reactions, 1)
        await self.app.jobs.run_pending()
        self.assertEqual(self.app.deliver(choice1.id, t1), 1)
        self.assertEqual(len(t1.media_parts), 1)
        self.assertEqual(self.app.deliver(choice1.id, t1), 0)
        self.assertEqual(len(t1.media_parts), 1)

        # Caso 2: la confirmación de ⏳ llega después de preparar el MP4; el MP4 se entrega una sola vez.
        choice2 = self.receive("/dl elegir " + view + " 1")
        claimed_reaction = self.app.store.claim_part(choice2.id, self.settings, self.now)
        self.assertIsNotNone(claimed_reaction)
        reaction_part, reaction_rev = claimed_reaction
        self.assertEqual(reaction_part.payload.get("reaction"), "⏳")
        await self.app.jobs.run_pending()
        t2 = CollectingTransport()
        self.assertEqual(self.app.deliver(choice2.id, t2), 1)
        self.assertEqual(len(t2.parts), 1)
        self.assertEqual(t2.parts[0].kind, "media")
        self.assertTrue(
            self.app.store.finish_part(
                reaction_part,
                reaction_rev,
                self.settings,
                "accepted",
                "late-reaction-ack",
                None,
                self.now,
            )
        )
        self.assertEqual(self.app.deliver(choice2.id, t2), 0)
        self.assertEqual([p.kind for p in t2.parts if p.kind == "media"], ["media"])
        self.assertEqual(t2.parts[-1].payload.get("reaction"), "")

        # Caso 3: pendiente antiguo de reacción no reenvía MP4, y acuse incierto del propio MP4 conserva protección.
        choice3 = self.receive("/dl elegir " + view + " 1")
        await self.app.jobs.run_pending()

        class UncertainMp4Transport:
            def __init__(self):
                self.media_attempts = 0

            def send(self, part):
                if part.payload.get("reaction"):
                    return DeliveryAck(True, "reaction-ok")
                self.media_attempts += 1
                raise TimeoutError("uncertain mp4 ack")

        t3 = UncertainMp4Transport()
        self.assertEqual(self.app.deliver(choice3.id, t3), 1)
        self.assertEqual(t3.media_attempts, 1)
        # Simular fila antigua de reacción pendiente cuando el MP4 ya quedó incierto
        with self.app.store.transaction() as db:
            db.execute(
                "UPDATE outbox SET state='pending' WHERE receipt_id=? AND position=0",
                (choice3.id,),
            )
        self.assertEqual(self.app.deliver(choice3.id, CollectingTransport()), 0)
        states = {
            r["position"]: r["state"]
            for r in self.rows(
                "SELECT position,state FROM outbox WHERE receipt_id=?", (choice3.id,)
            )
        }
        self.assertEqual(states[0], "cancelled")
        self.assertEqual(states[1], "uncertain")

    async def test_youtube_extractor_receives_the_xx_intro_and_nissan_skyline_r34_intact(self):
        from unittest.mock import patch
        from botsky.engines.downloads import Downloader, sanitize_search_query
        from botsky.frontend.prompts import FINAL_RULES, SYSTEM

        self.assertEqual(sanitize_search_query("The xx Intro", "youtube"), "The xx Intro")
        self.assertEqual(
            sanitize_search_query("Nissan Skyline R34", "youtube"), "Nissan Skyline R34"
        )
        captured_cmds = []

        async def fake_run_process(cmd, timeout, **kwargs):
            captured_cmds.append(list(cmd))
            return b'{"entries": []}'

        downloader = Downloader(self.settings.root / "dl-engine")
        with patch("botsky.engines.downloads.run_process", side_effect=fake_run_process):
            await downloader.search("The xx Intro", "youtube")
            await downloader.search("Nissan Skyline R34", "youtube")
        self.assertEqual(len(captured_cmds), 2)
        self.assertIn("ytsearch20:The xx Intro", captured_cmds[0])
        self.assertIn("ytsearch20:Nissan Skyline R34", captured_cmds[1])
        self.assertIn("recetas rusas", SYSTEM)
        self.assertIn("recetas rusas", FINAL_RULES)
        self.assertIn("source='youtube', query='recetas rusas'", FINAL_RULES)

    async def test_long_jobs_queue_reaction_report_stage_and_optimize_polling(self):
        import time
        from unittest.mock import patch
        from botsky.contracts import DeliveryAck

        # 1. Descarga por URL y búsqueda encolan reacción ⏳ sin texto repetitivo y detallan etapa en /estado
        dl_receipt = self.receive("/dl mp4 " + W3)
        self.assertEqual(dl_receipt.result.code, "job_queued")
        self.assertEqual(dl_receipt.result.data.get("reaction"), "⏳")
        queued_status = self.receive("/estado " + dl_receipt.id).result
        self.assertIn("En cola (descarga).", queued_status.text)

        reactions_sent = []
        media_sent = []

        class TrackingTransport:
            def send(self, part):
                if "reaction" in part.payload:
                    reactions_sent.append((part.text, part.payload["reaction"]))
                    return DeliveryAck(True, f"rx-{len(reactions_sent)}")
                media_sent.append(part)
                return DeliveryAck(True, f"media-{len(media_sent)}")

        transport = TrackingTransport()
        # Si se entrega mientras está en cola/ejecución, envía solo la reacción ⏳ vacía de texto
        self.assertEqual(self.app.deliver(dl_receipt.id, transport), 1)
        self.assertEqual(reactions_sent, [("", "⏳")])
        self.assertEqual(media_sent, [])

        # Ejecución rápida (<500ms) no realiza consultas de polling innecesarias a Jobs.current
        current_calls = 0
        orig_current = self.app.jobs.current

        def counted_current(job):
            nonlocal current_calls
            current_calls += 1
            return orig_current(job)

        with patch.object(self.app.jobs, "current", side_effect=counted_current):
            await self.app.jobs.run_pending()
        self.assertEqual(current_calls, 0)

        # Al terminar el trabajo, retira la reacción ⏳ ("") y entrega el archivo final una sola vez
        self.assertEqual(self.app.deliver(dl_receipt.id, transport), 1)
        self.assertEqual(reactions_sent, [("", "⏳"), ("", "")])
        self.assertEqual(len(media_sent), 1)
        self.assertEqual(self.app.deliver(dl_receipt.id, transport), 0)
        self.assertEqual(reactions_sent, [("", "⏳"), ("", "")])

        # 2. Cancelación en curso despierta inmediatamente y retira la reacción ⏳ ya enviada
        slow_receipt = self.receive("/dl buscar mp4 consulta lenta")
        cancel_reactions = []

        class CancelReactionTransport:
            def send(self, part):
                if "reaction" in part.payload:
                    cancel_reactions.append(part.payload["reaction"])
                    return DeliveryAck(True, f"crx-{len(cancel_reactions)}")
                return DeliveryAck(True, "other")

        cancel_transport = CancelReactionTransport()
        self.assertEqual(self.app.deliver(slow_receipt.id, cancel_transport), 1)
        self.assertEqual(cancel_reactions, ["⏳"])

        started = asyncio.Event()

        async def slow_engine(job, directory):
            started.set()
            await asyncio.sleep(10)

        with patch.object(self.app.jobs, "execute_engine", slow_engine):
            run_task = asyncio.create_task(self.app.jobs.run_pending())
            await asyncio.wait_for(started.wait(), 1.0)
            running_status = self.receive("/estado " + slow_receipt.id).result
            self.assertIn("Lo estoy preparando (buscando resultados).", running_status.text)
            t0 = time.monotonic()
            cancel_res = self.receive("/cancelar " + slow_receipt.id)
            self.assertEqual(cancel_res.result.status, "cancelled")
            self.assertEqual(cancel_res.result.text, "Cancelado.")
            await asyncio.wait_for(run_task, 0.25)
            elapsed = time.monotonic() - t0
            self.assertLess(elapsed, 0.25)

        self.assertEqual(self.app.deliver(slow_receipt.id, cancel_transport), 0)
        self.assertEqual(cancel_reactions, ["⏳", ""])
        self.assertEqual(self.app.deliver(slow_receipt.id, cancel_transport), 0)
        self.assertEqual(cancel_reactions, ["⏳", ""])

        # 3. Si un trabajo con ⏳ ya enviada falla, también retira la reacción ⏳ al entregar el error
        fail_receipt = self.receive("/dl buscar mp4 fallo")
        fail_reactions = []
        fail_texts = []

        class FailTrackingTransport:
            def send(self, part):
                if "reaction" in part.payload:
                    fail_reactions.append(part.payload["reaction"])
                    return DeliveryAck(True, f"frx-{len(fail_reactions)}")
                fail_texts.append(part.text)
                return DeliveryAck(True, "ftxt-1")

        fail_transport = FailTrackingTransport()
        self.assertEqual(self.app.deliver(fail_receipt.id, fail_transport), 1)
        self.assertEqual(fail_reactions, ["⏳"])

        async def failing_search(job, directory):
            from botsky.engines.process import MediaError

            raise MediaError("source_failed")

        with patch.object(self.app.jobs, "execute_engine", failing_search):
            await self.app.jobs.run_pending()

        self.assertEqual(self.app.deliver(fail_receipt.id, fail_transport), 1)
        self.assertEqual(fail_reactions, ["⏳", ""])
        self.assertEqual(len(fail_texts), 1)

    async def test_reaction_in_flight_when_job_finishes_is_cleared_after_confirmation(self):
        from botsky.contracts import DeliveryAck

        # 1. Reacción ⏳ entra en estado 'sending'
        receipt = self.receive("/dl mp4 " + W3)
        claimed = self.app.store.claim_part(receipt.id, self.settings, self.now)
        self.assertIsNotNone(claimed)
        reaction_part, reaction_rev = claimed
        self.assertEqual(reaction_part.payload.get("reaction"), "⏳")

        # 2. El trabajo finaliza mientras la reacción ⏳ sigue en 'sending'
        await self.app.jobs.run_pending()
        clear_rows = self.rows(
            "SELECT state FROM outbox WHERE receipt_id=? AND json_extract(rich_payload_json,'$.reaction')=''",
            (receipt.id,),
        )
        self.assertEqual(len(clear_rows), 1)
        self.assertEqual(clear_rows[0]["state"], "pending")

        # 3. La reacción ⏳ se confirma ('accepted')
        self.assertTrue(
            self.app.store.finish_part(
                reaction_part,
                reaction_rev,
                self.settings,
                "accepted",
                "rx-inflight-ok",
                None,
                self.now,
            )
        )

        # 4. Se entrega su retirada ("") y el archivo final una sola vez
        events = []

        class InFlightTransport:
            def send(self, part):
                if "reaction" in part.payload:
                    events.append(("reaction", part.payload["reaction"]))
                    return DeliveryAck(True, "rx-clear-ok")
                events.append((part.kind, len(part.artifacts)))
                return DeliveryAck(True, "media-ok")

        transport = InFlightTransport()
        self.assertEqual(self.app.deliver(receipt.id, transport), 1)
        self.assertEqual(events, [("reaction", ""), ("media", 1)])
        self.assertEqual(self.app.deliver(receipt.id, transport), 0)
        self.assertEqual(events, [("reaction", ""), ("media", 1)])

    async def test_video_download_compresses_heavy_sources_and_sets_faststart_for_streaming(self):
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock, patch
        from botsky.engines.downloads import Downloader

        downloader = Downloader(self.root / "dl-stream-engine")
        captured_ffmpeg_calls = []
        real_run_process = run_process

        async def intercept_run_process(cmd, timeout, **kwargs):
            if cmd and cmd[0] == "prlimit" and "ffmpeg" in cmd:
                captured_ffmpeg_calls.append(list(cmd))
            return await real_run_process(cmd, timeout, **kwargs)

        # 1. Video ligero compatible: remux directo con copy y faststart
        light_bytes = self.video.read_bytes()
        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def aiter_light():
            yield light_bytes

        mock_response.aiter_bytes = aiter_light

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        @asynccontextmanager
        async def fake_stream(*args, **kwargs):
            yield mock_response

        mock_client.stream = fake_stream

        with patch("httpx.AsyncClient", return_value=mock_client), patch(
            "botsky.engines.downloads.run_process", side_effect=intercept_run_process
        ):
            artifact = await downloader.download(W3, format="video")

        self.assertTrue(artifact.is_file())
        self.assertEqual(len(captured_ffmpeg_calls), 1)
        copy_cmd = captured_ffmpeg_calls[0]
        self.assertIn("copy", copy_cmd)
        self.assertIn("+faststart", copy_cmd)

        with artifact.open("rb") as f:
            header = f.read(256)
            self.assertIn(b"moov", header)
            self.assertLess(header.find(b"moov"), 100)

        # 2. Video pesado o de alto bitrate: activa compresión estilo WhatsApp con CRF 26, maxrate 1.6M y faststart
        captured_ffmpeg_calls.clear()
        heavy_video = self.root / "heavy_fixture.mp4"
        await real_run_process(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=duration=2:size=1280x720:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=duration=2",
                "-c:v",
                "libx264",
                "-b:v",
                "15000k",
                "-c:a",
                "aac",
                str(heavy_video),
            ],
            15,
        )
        heavy_bytes = heavy_video.read_bytes()

        async def aiter_heavy():
            yield heavy_bytes

        mock_response.aiter_bytes = aiter_heavy

        with patch("httpx.AsyncClient", return_value=mock_client), patch(
            "botsky.engines.downloads.run_process", side_effect=intercept_run_process
        ):
            heavy_artifact = await downloader.download(W3, format="video")

        self.assertTrue(heavy_artifact.is_file())
        self.assertEqual(len(captured_ffmpeg_calls), 1)
        compress_cmd = captured_ffmpeg_calls[0]
        self.assertNotIn("copy", compress_cmd)
        self.assertIn("libx264", compress_cmd)
        self.assertIn("-crf", compress_cmd)
        self.assertIn("26", compress_cmd)
        self.assertIn("-maxrate", compress_cmd)
        self.assertIn("1600000", compress_cmd)
        self.assertIn("+faststart", compress_cmd)

        with heavy_artifact.open("rb") as f:
            header = f.read(256)
            self.assertIn(b"moov", header)
            self.assertLess(header.find(b"moov"), 100)

        # 3. Video de más de 20MB: nunca pasa por remux directo, va forzado a compresión y streaming
        import struct

        captured_ffmpeg_calls.clear()
        raw_light = self.video.read_bytes()
        pad_size = 21 * 1024 * 1024
        over_20mb_bytes = raw_light + struct.pack(">I4s", pad_size, b"free") + b"\x00" * (pad_size - 8)
        self.assertGreater(len(over_20mb_bytes), 20 * 1024 * 1024)

        async def aiter_over_20mb():
            yield over_20mb_bytes

        mock_response.aiter_bytes = aiter_over_20mb

        with patch("httpx.AsyncClient", return_value=mock_client), patch(
            "botsky.engines.downloads.run_process", side_effect=intercept_run_process
        ):
            over_20mb_artifact = await downloader.download(W3, format="video")

        self.assertTrue(over_20mb_artifact.is_file())
        self.assertEqual(len(captured_ffmpeg_calls), 1)
        over_20mb_cmd = captured_ffmpeg_calls[0]
        self.assertNotIn("copy", over_20mb_cmd)
        self.assertIn("libx264", over_20mb_cmd)
        self.assertIn("+faststart", over_20mb_cmd)

        with over_20mb_artifact.open("rb") as f:
            header = f.read(256)
            self.assertIn(b"moov", header)
            self.assertLess(header.find(b"moov"), 100)


