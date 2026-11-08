"""Motores reales y contratos de trabajo con fixtures sintéticos; cero proveedores remotos."""

import asyncio
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result
from botsky.engines.process import MediaError, run_process
from botsky.jobs import EngineOutput


class MediaTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.now = int(datetime.fromisoformat("2026-11-06T03:00:00+00:00").timestamp() * 1000)
        self.settings = Settings(
            root,
            "media-lab",
            "local",
            1,
            root / "private/test.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.app = Application(self.settings, clock=lambda: self.now)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.sequence = 0
        self.png = root / "fixture.dat"
        image = Image.new("RGB", (800, 200), "white")
        font = ImageFont.load_default(size=40)
        ImageDraw.Draw(image).text((20, 60), "BOTSKY CABLE AZUL 2026", fill="black", font=font)
        image.save(self.png, format="PNG")

    def incoming(self, text, *, actor="alice", chat="private", **kw):
        self.sequence += 1
        return self.adapter.incoming(str(self.sequence), actor, chat, text, **kw)

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def result(self, receipt_id):
        return Result.from_json(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (receipt_id,))[0]["result_json"]
        )

    async def convert(self, text, file):
        incoming = self.app.attach_local(self.incoming(text), file)
        receipt = self.app.receive(incoming)
        self.assertEqual(receipt.result.code, "job_queued")
        await self.app.jobs.run_pending()
        return incoming, receipt, self.result(receipt.id)

    def file_of(self, result):
        return self.app.artifacts.path(result.data["artifacts"][0])

    async def test_image_pdf_sticker_ocr_qr_outputs_and_source_bytes(self):
        _, receipt, result = await self.convert("/convertir pdf", self.png)
        self.assertEqual(result.code, "document_converted")
        self.assertEqual(len(PdfReader(self.file_of(result)).pages), 1)
        self.assertEqual(result.data["source_format"], "png")
        _, _, sticker = await self.convert("/sticker", self.png)
        with Image.open(self.file_of(sticker)) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (512, 512)))
        _, _, ocr = await self.convert("/ocr", self.png)
        self.assertIn("CABLE AZUL", ocr.text)
        qr = self.settings.root / "qr.png"
        await run_process(["qrencode", "-s", "10", "-o", str(qr), "SYNTHETIC:BOTSKY-2026"], 10)
        _, _, result = await self.convert("/qr", qr)
        self.assertEqual(result.text, "SYNTHETIC:BOTSKY-2026")
        transport = CollectingTransport()
        self.assertEqual(self.app.deliver(receipt.id, transport), 1)
        self.assertEqual(
            transport.parts[-1].artifacts, (self.result(receipt.id).data["artifacts"][0],)
        )
        self.assertEqual(self.app.deliver(receipt.id, transport), 0)

    async def test_video_and_gif_produce_animated_sticker(self):
        video = self.settings.root / "anim.mp4"
        await run_process(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=160x120:rate=15",
                "-t",
                "2",
                str(video),
            ],
            10,
        )
        _, _, sticker = await self.convert("/sticker", video)
        self.assertEqual(sticker.code, "sticker_created")
        sticker_path = self.file_of(sticker)
        self.assertLessEqual(sticker_path.stat().st_size, 950000)
        with Image.open(sticker_path) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (512, 512)))
            self.assertTrue(getattr(image, "is_animated", False))

        gif = self.settings.root / "anim.gif"
        await run_process(
            ["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-t", "1", str(gif)],
            10,
        )
        _, _, gif_sticker = await self.convert("/sticker", gif)
        self.assertEqual(gif_sticker.code, "sticker_created")
        gif_sticker_path = self.file_of(gif_sticker)
        self.assertLessEqual(gif_sticker_path.stat().st_size, 950000)
        with Image.open(gif_sticker_path) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (512, 512)))
            self.assertTrue(getattr(image, "is_animated", False))

    async def test_ten_second_video_produces_high_quality_animated_sticker(self):
        video = self.settings.root / "ten_sec.mp4"
        await run_process(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x240:rate=15",
                "-t",
                "10",
                str(video),
            ],
            15,
        )
        _, _, sticker = await self.convert("/sticker", video)
        self.assertEqual(sticker.code, "sticker_created")
        sticker_path = self.file_of(sticker)
        self.assertLessEqual(sticker_path.stat().st_size, 950000)
        with Image.open(sticker_path) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (512, 512)))
            self.assertTrue(getattr(image, "is_animated", False))
            self.assertGreaterEqual(getattr(image, "n_frames", 1), 60)

    async def test_animated_webp_sticker_strictly_under_limit_with_metadata(self):
        # Create an animated WebP and convert it to sticker
        source_anim = self.settings.root / "source_anim.webp"
        await run_process(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=512x512:rate=10",
                "-t",
                "3",
                "-c:v",
                "libwebp_anim",
                "-q:v",
                "60",
                str(source_anim),
            ],
            15,
        )
        _, _, sticker = await self.convert("/sticker", source_anim)
        self.assertEqual(sticker.code, "sticker_created")
        sticker_path = self.file_of(sticker)
        self.assertLessEqual(sticker_path.stat().st_size, 950000)
        with Image.open(sticker_path) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (512, 512)))
            self.assertTrue(getattr(image, "is_animated", False))

    async def test_static_sticker_has_sar_and_metadata_under_limit(self):
        _, _, sticker = await self.convert("/sticker", self.png)
        self.assertEqual(sticker.code, "sticker_created")
        sticker_path = self.file_of(sticker)
        self.assertLessEqual(sticker_path.stat().st_size, 102400)
        with Image.open(sticker_path) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (512, 512)))
            self.assertFalse(getattr(image, "is_animated", False))

    async def test_video_without_duration_metadata_produces_sticker(self):
        from botsky.engines.images import sticker

        raw_video = self.settings.root / "raw_stream.h264"
        await run_process(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x240:rate=15",
                "-t",
                "2",
                "-c:v",
                "libx264",
                str(raw_video),
            ],
            15,
        )
        out_dir = self.settings.root / "raw_sticker_dir"
        out_dir.mkdir(parents=True, exist_ok=True)
        sticker_path = await sticker(raw_video, out_dir)
        self.assertLessEqual(sticker_path.stat().st_size, 950000)
        with Image.open(sticker_path) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (512, 512)))
            self.assertTrue(getattr(image, "is_animated", False))

    async def test_same_video_mp3_actual_stream_and_clip_duration(self):
        video = self.settings.root / "video.mp4"
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
                "2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(video),
            ],
            15,
        )
        original, _, result = await self.convert("/editar mp3", video)
        self.assertEqual(result.code, "media_edited")
        raw = await run_process(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_name,codec_type",
                "-of",
                "json",
                str(self.file_of(result)),
            ],
            10,
        )
        info = json.loads(raw)
        self.assertEqual({s["codec_type"] for s in info["streams"]}, {"audio"})
        self.assertEqual(info["streams"][0]["codec_name"], "mp3")
        self.assertAlmostEqual(float(info["format"]["duration"]), 2, delta=0.15)
        quoted = self.incoming(
            "/editar mp4 --desde 0.5 --hasta 1.5", quoted_message_id=original.message_id
        )
        receipt = self.app.receive(quoted)
        await self.app.jobs.run_pending()
        result = self.result(receipt.id)
        self.assertEqual(result.code, "media_edited")
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
                    str(self.file_of(result)),
                ],
                10,
            )
        )
        self.assertAlmostEqual(float(info["format"]["duration"]), 1, delta=0.15)

    async def test_pdf_all_pages_text_and_scanned_error_is_specific(self):
        source = self.settings.root / "text.pdf"
        doc = canvas.Canvas(str(source))
        doc.drawString(50, 700, "PAGINA UNO CABLE AZUL")
        doc.showPage()
        doc.drawString(50, 700, "PAGINA DOS CABLE ROJO")
        doc.save()
        _, _, result = await self.convert("/convertir docx", source)
        self.assertEqual(result.code, "document_converted")
        from docx import Document

        text = "\n".join(p.text for p in Document(self.file_of(result)).paragraphs)
        self.assertIn("PAGINA UNO", text)
        self.assertIn("PAGINA DOS", text)
        scanned = self.settings.root / "scanned.pdf"
        with Image.open(self.png) as image:
            image.save(scanned, format="PDF")
        _, _, result = await self.convert("/convertir docx", scanned)
        self.assertEqual(result.code, "document_no_text")
        self.assertIn("escaneo", result.text)
        self.assertNotIn("artifacts", result.data)

    async def test_multiple_sheet_csv_keeps_sheets_and_neutralizes_formula_text(self):
        from openpyxl import Workbook

        path = self.settings.root / "book.xlsx"
        book = Workbook()
        book.active.append(["A", "B"])
        book.active.append(["uno", "@FORMULA"])
        sheet = book.create_sheet("Segunda")
        sheet.append(["C", "D"])
        sheet.append([2, "dos"])
        book.save(path)
        _, _, result = await self.convert("/convertir csv", path)
        self.assertEqual(result.code, "document_converted")
        self.assertIn("Cada hoja", result.text)
        with zipfile.ZipFile(self.file_of(result)) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            self.assertIn("'@FORMULA", archive.read("hoja-1.csv").decode("utf-8-sig"))
            self.assertIn("dos", archive.read("hoja-2.csv").decode("utf-8-sig"))

    async def test_cancelled_motor_and_late_output_do_not_publish_or_deliver(self):
        incoming = self.app.attach_local(self.incoming("/convertir pdf"), self.png)
        receipt = self.app.receive(incoming)
        started = asyncio.Event()

        async def late(job, directory):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                pass
            output = directory / "late.png"
            output.write_bytes(self.png.read_bytes())
            return EngineOutput(Result("ok", "late", "Esto no debe publicarse."), (output,))

        with patch.object(self.app.jobs, "execute_engine", late):
            running = asyncio.create_task(self.app.jobs.run_pending())
            await started.wait()
            cancellation = self.app.receive(self.incoming("/cancelar " + receipt.id))
            self.assertEqual(cancellation.result.status, "cancelled")
            await running
        self.assertEqual(self.result(receipt.id).status, "cancelled")
        self.assertEqual(self.rows("SELECT * FROM artifacts WHERE origin='result'"), [])
        self.assertEqual(self.rows("SELECT * FROM outbox WHERE receipt_id=?", (receipt.id,)), [])
        self.assertEqual(list(self.app.jobs.root.iterdir()), [])

    async def test_current_attachment_priority_foreign_quote_symlink_and_expiry(self):
        original = self.app.attach_local(self.incoming("", actor="bob"), self.png)
        self.app.receive(original)
        own = self.app.attach_local(
            self.incoming("/convertir pdf", quoted_message_id=original.message_id), self.png
        )
        receipt = self.app.receive(own)
        self.assertEqual(receipt.result.code, "job_queued")
        denied = self.app.receive(
            self.incoming("/convertir pdf", quoted_message_id=original.message_id)
        )
        self.assertEqual(denied.result.code, "quoted_attachment_unavailable")
        lied = self.app.receive(self.incoming("/convertir pdf", attachments=original.attachments))
        self.assertEqual(lied.result.code, "artifact_access_denied")
        link = self.settings.root / "linked"
        link.symlink_to(self.png)
        with self.assertRaises(OSError):
            self.app.attach_local(self.incoming("/sticker"), link)
        self.now += 86399000
        self.assertIsNotNone(self.app.jobs.claim())
        self.now += 1001
        # El lease vigente de un trabajo activo protege más allá de la retención.
        self.assertGreater(self.app.artifacts.collect(self.now), 0)
        self.assertTrue(self.app.artifacts.path(own.attachments[0]).exists())

    async def test_restart_recovers_queue_and_old_token_cannot_publish(self):
        incoming = self.app.attach_local(self.incoming("/convertir pdf"), self.png)
        receipt = self.app.receive(incoming)
        old = self.app.jobs.claim()
        self.now += 1831000
        restarted = Application(self.settings, clock=lambda: self.now)
        job = restarted.jobs.claim()
        self.assertEqual(job["id"], old["id"])
        self.assertNotEqual(job["token"], old["token"])
        self.assertFalse(restarted.jobs.finish(old, EngineOutput(Result("ok", "late", "late")), []))
        await restarted.jobs.run_one(job)
        self.assertEqual(self.result(receipt.id).code, "document_converted")
        self.assertEqual(len(self.rows("SELECT * FROM artifacts WHERE origin='result'")), 1)

    async def test_file_output_quote_requires_accepted_own_receipt(self):
        _, receipt, result = await self.convert("/convertir pdf", self.png)
        unknown = self.app.receive(self.incoming("/pdf extraer 1", quoted_message_id="not-sent"))
        self.assertEqual(unknown.result.code, "quoted_attachment_unavailable")
        transport = CollectingTransport()
        self.app.deliver(receipt.id, transport)
        quote = transport.parts[-1].receipt_id
        provider_id = "local-" + quote + "-" + str(transport.parts[-1].position)
        request = self.app.receive(self.incoming("/pdf extraer 1", quoted_message_id=provider_id))
        self.assertEqual(request.result.code, "job_queued")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(request.id).code, "pdf_extracted")
        self.assertEqual(len(PdfReader(self.file_of(self.result(request.id))).pages), 1)

    async def test_process_timeout_is_bounded_and_stable(self):
        with self.assertRaises(MediaError) as ctx:
            await run_process(["/usr/bin/python3", "-c", "import time; time.sleep(30)"], 0.1)
        self.assertEqual(ctx.exception.code, "process_timeout")

    async def test_file_wait_only_after_own_delivered_prompt_and_new_order_replaces_it(self):
        prompt = self.app.receive(self.incoming("/convertir pdf"))
        self.assertEqual(prompt.result.code, "attachment_required")
        file = self.app.attach_local(self.incoming(""), self.png)
        self.assertEqual(self.app.receive(file).state, "ignored")
        self.app.deliver(prompt.id, CollectingTransport())
        foreign = self.app.attach_local(self.incoming("", actor="bob"), self.png)
        self.assertEqual(self.app.receive(foreign).state, "ignored")
        own = self.app.attach_local(self.incoming(""), self.png)
        receipt = self.app.receive(own)
        self.assertEqual(receipt.result.code, "job_queued")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt.id).code, "document_converted")
        another = self.app.receive(self.incoming("/sticker"))
        self.app.deliver(another.id, CollectingTransport())
        note = self.app.receive(self.incoming("/nota guardar otra orden"))
        self.assertIn("Reemplacé", note.result.text)
        self.assertEqual(self.result(another.id).code, "file_wait_replaced")
        file = self.app.attach_local(self.incoming(""), self.png)
        self.assertEqual(self.app.receive(file).state, "ignored")

    async def test_pdf_session_restart_multiple_sources_and_cancel_exact_job(self):
        start = self.app.receive(self.incoming("/pdf iniciar"))
        self.assertEqual(start.result.code, "pdf_session_started")
        for _ in range(2):
            incoming = self.app.attach_local(self.incoming("/pdf agregar"), self.png)
            self.assertEqual(self.app.receive(incoming).result.code, "pdf_sources_added")
        restarted = Application(self.settings, clock=lambda: self.now)
        finish = restarted.receive(self.incoming("/pdf terminar"))
        self.assertEqual(finish.result.code, "job_queued")
        self.assertEqual(
            restarted.receive(self.incoming("/pdf agregar")).result.code, "pdf_session_busy"
        )
        await restarted.jobs.run_pending()
        result = self.result(finish.id)
        self.assertEqual(result.code, "pdf_assembled")
        self.assertEqual(len(PdfReader(self.file_of(result)).pages), 2)
        self.assertEqual(self.rows("SELECT state FROM pdf_sessions")[0]["state"], "finished")
        # Nueva sesión conserva el historial de la anterior y permite cancelación exacta.
        incoming = self.app.attach_local(self.incoming("/pdf iniciar"), self.png)
        self.assertEqual(self.app.receive(incoming).result.code, "pdf_session_started")
        pending = self.app.receive(self.incoming("/pdf terminar"))
        self.assertEqual(
            self.app.receive(self.incoming("/cancelar " + pending.id)).result.status, "cancelled"
        )
        self.assertEqual(
            self.rows("SELECT state FROM pdf_sessions WHERE state='open'")[0]["state"], "open"
        )
        self.assertEqual(
            self.app.receive(self.incoming("/pdf cancelar")).result.code, "pdf_session_cancelled"
        )
        self.assertEqual(await self.app.jobs.run_pending(), 0)
        bad = self.settings.root / "unsupported.txt"
        bad.write_text("Solo texto")
        before = len(self.rows("SELECT * FROM pdf_sessions"))
        incoming = self.app.attach_local(self.incoming("/pdf iniciar"), bad)
        self.assertEqual(self.app.receive(incoming).result.code, "pdf_source_format")
        self.assertEqual(len(self.rows("SELECT * FROM pdf_sessions")), before)

    async def test_uncertain_pdf_retry_requires_delivered_bound_preview_and_never_repeats_motor(
        self,
    ):
        _, receipt, result = await self.convert("/convertir pdf", self.png)

        class Timeout:
            def send(self, part):
                raise TimeoutError()

        self.app.deliver(receipt.id, Timeout())
        request = self.app.receive(
            self.incoming("/pdf reintentar " + receipt.id + " --confirmar-incierto")
        )
        self.assertEqual(request.result.code, "retry_preview_required")
        preview = self.app.receive(self.incoming("/pdf reintentar " + receipt.id))
        self.assertEqual(preview.result.code, "delivery_retry_preview")
        identifier = preview.result.data["confirmation_id"]
        no = self.app.receive(self.incoming("/confirmar " + identifier))
        self.assertEqual(no.result.code, "confirmation_unavailable")
        self.app.deliver(preview.id, CollectingTransport())
        foreign = self.app.receive(self.incoming("/confirmar " + identifier, actor="bob"))
        self.assertEqual(foreign.result.code, "confirmation_unavailable")
        confirmed = self.app.receive(self.incoming("/confirmar " + identifier))
        self.assertEqual(confirmed.result.code, "delivery_retry_authorized")
        self.assertEqual(
            self.app.receive(self.incoming("/confirmar " + identifier)).result.code,
            "confirmation_unavailable",
        )
        transport = CollectingTransport()
        self.assertEqual(self.app.deliver(receipt.id, transport), 1)
        self.assertEqual(len(self.rows("SELECT * FROM jobs")), 1)
        self.assertEqual(await self.app.jobs.run_pending(), 0)
        self.assertEqual(self.result(receipt.id).data["artifacts"], result.data["artifacts"])
        attempts = self.rows(
            "SELECT state FROM delivery_attempts WHERE receipt_id=?", (receipt.id,)
        )
        self.assertIn("uncertain", {row["state"] for row in attempts})
        self.assertIn("accepted", {row["state"] for row in attempts})

    async def test_uncertain_pdf_retry_flag_consumes_only_delivered_preview(self):
        _, receipt, result = await self.convert("/convertir pdf", self.png)

        class Timeout:
            def send(self, part):
                raise TimeoutError()

        self.app.deliver(receipt.id, Timeout())
        command = "/pdf reintentar " + receipt.id + " --confirmar-incierto"
        self.assertEqual(
            self.app.receive(self.incoming(command)).result.code, "retry_preview_required"
        )
        preview = self.app.receive(self.incoming("/pdf reintentar " + receipt.id))
        self.app.deliver(preview.id, CollectingTransport())
        confirmed = self.app.receive(self.incoming(command))
        self.assertEqual(confirmed.result.code, "delivery_retry_authorized")
        self.assertEqual(
            self.app.receive(self.incoming(command)).result.code, "no_retryable_delivery"
        )
        self.assertEqual(self.app.deliver(receipt.id, CollectingTransport()), 1)
        self.assertEqual(self.result(receipt.id).data["artifacts"], result.data["artifacts"])
        self.assertEqual(len(self.rows("SELECT * FROM jobs")), 1)
        self.assertEqual(await self.app.jobs.run_pending(), 0)

    async def test_webm_and_embedded_subtitle_outputs_and_catalog_assets(self):
        source = self.settings.root / "subtitle.srt"
        source.write_text("1\n00:00:00,000 --> 00:00:01,000\nCABLE AZUL\n", encoding="utf-8")
        video = self.settings.root / "subtitled.mp4"
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
                "-i",
                str(source),
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-c:s",
                "mov_text",
                "-metadata:s:s:0",
                "language=spa",
                str(video),
            ],
            15,
        )
        _, _, subtitle = await self.convert("/editar srt --idioma es", video)
        self.assertEqual(subtitle.code, "media_edited")
        self.assertIn("CABLE AZUL", self.file_of(subtitle).read_text())
        self.assertEqual(
            self.rows("SELECT format FROM artifacts WHERE id=?", (subtitle.data["artifacts"][0],))[
                0
            ]["format"],
            "srt",
        )
        _, _, webm = await self.convert("/editar webm", video)
        self.assertEqual(webm.code, "media_edited")
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
                    str(self.file_of(webm)),
                ],
                10,
            )
        )
        self.assertEqual({s["codec_name"] for s in info["streams"]}, {"vp9", "opus"})
        for label in ("saludo", "risa", "pensando", "sonrojo"):
            receipt = self.app.receive(self.incoming("/reaccion " + label))
            await self.app.jobs.run_pending()
            result = self.result(receipt.id)
            self.assertEqual(result.code, "reaction_ready")
            with Image.open(self.file_of(result)) as image:
                self.assertEqual(image.format, "WEBP")

    async def test_worker_exclusion_and_real_parent_death_release_process_group(self):
        import os
        import signal
        import sys

        from botsky.local_files import WorkerBusy, worker_lock

        with worker_lock(self.settings.root), self.assertRaises(WorkerBusy):
            await self.app.jobs.run_pending()
        pid_file = self.settings.root / "child.pid"
        program = "import asyncio,sys; from botsky.engines.process import run_process; asyncio.run(run_process([sys.executable,'-c',sys.argv[1]],30))"
        child_code = f"import os,time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)"
        parent = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            program,
            child_code,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(5):
                while not pid_file.exists():
                    await asyncio.sleep(0.01)
            child_pid = int(pid_file.read_text())
            os.kill(parent.pid, signal.SIGKILL)
            await parent.wait()
            async with asyncio.timeout(5):
                while True:
                    status = Path(f"/proc/{child_pid}/stat")
                    if not status.exists() or status.read_text().split()[2] == "Z":
                        break
                    await asyncio.sleep(0.01)
        finally:
            if parent.returncode is None:
                parent.kill()
                await parent.wait()

    async def test_nineteen_document_targets_have_real_output_of_the_declared_format(self):
        from docx import Document
        from openpyxl import Workbook
        from pptx import Presentation

        from botsky.engines.documents import DocumentEngine, detect_document_format

        text = b"BOTSKY CABLE AZUL 2026\nSegunda linea.\n"
        book = Workbook()
        book.active.append(["Nombre", "Valor"])
        book.active.append(["BOTSKY", 2026])
        spreadsheet = io.BytesIO()
        book.save(spreadsheet)
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "BOTSKY CABLE AZUL"
        slides = io.BytesIO()
        presentation.save(slides)
        doc = Document()
        doc.add_heading("BOTSKY CABLE AZUL", 1)
        writer = io.BytesIO()
        doc.save(writer)
        jpeg = io.BytesIO()
        with Image.open(self.png) as image:
            image.save(jpeg, format="JPEG")
        cases = {
            **{target: text for target in ("pdf", "docx", "doc", "odt", "rtf", "txt")},
            **{target: spreadsheet.getvalue() for target in ("xlsx", "xls", "ods", "csv", "json")},
            **{target: slides.getvalue() for target in ("pptx", "ppt", "odp")},
            "png": jpeg.getvalue(),
            "jpg": self.png.read_bytes(),
            "webp": self.png.read_bytes(),
            "html": b"# BOTSKY CABLE AZUL\n",
            "md": writer.getvalue(),
        }
        self.assertEqual(len(cases), 19)
        engine = DocumentEngine(self.settings.root / "document-targets")
        for target, source in cases.items():
            with self.subTest(target=target):
                output = await engine.convert(source, target)
                self.assertEqual(detect_document_format(output.read_bytes()), target)
                if target == "pdf":
                    self.assertIn("BOTSKY", PdfReader(output).pages[0].extract_text())
                elif target in (
                    "doc",
                    "docx",
                    "odt",
                    "rtf",
                    "xls",
                    "xlsx",
                    "ods",
                    "ppt",
                    "pptx",
                    "odp",
                ):
                    roundtrip = await engine.convert(output.read_bytes(), "txt")
                    self.assertIn("BOTSKY", roundtrip.read_text())

    async def test_bwrap_uses_compatible_python_and_pillow_converts_image_to_pdf_and_docs_links_valid(
        self,
    ):
        import re
        from botsky.engines.documents import SANDBOX_PYTHON, DocumentEngine
        from botsky.engines.pdf import PdfOperations

        doc_engine = DocumentEngine(self.settings.root / "bwrap-doc")
        pdf_ops = PdfOperations(self.settings.root / "bwrap-pdf")
        self.assertTrue(await doc_engine.available())
        self.assertTrue(await pdf_ops.available())
        sandbox_cmd = doc_engine._sandbox(self.settings.root, ["/usr/bin/python3", "-c", "pass"])
        self.assertIn(SANDBOX_PYTHON, sandbox_cmd)

        converted = await doc_engine.convert(self.png.read_bytes(), "pdf")
        self.assertTrue(converted.read_bytes().startswith(b"%PDF-"))
        self.assertEqual(len(PdfReader(converted).pages), 1)

        assembled = await pdf_ops.assemble([self.png.read_bytes()])
        self.assertTrue(assembled.read_bytes().startswith(b"%PDF-"))
        self.assertEqual(len(PdfReader(assembled).pages), 1)

        repo_root = Path(__file__).resolve().parents[1]
        for doc_rel in ("README.md", "docs/GUIA_BOTSKY.md"):
            doc_path = repo_root / doc_rel
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn("Responder", content)
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
                if target.startswith(("http://", "https://", "#")):
                    continue
                self.assertFalse(target.startswith("/"), f"Enlace absoluto en {doc_rel}: {target}")
                resolved = (doc_path.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"Enlace roto en {doc_rel}: {target}")
