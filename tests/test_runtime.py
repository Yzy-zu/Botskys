"""Transporte continuo con proveedor sintético; HTTP real solo loopback."""

import asyncio
import base64
import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

import httpx
from PIL import Image
from pypdf import PdfReader

from botsky.adapters.evolution import EvolutionTransport
from botsky.adapters.evolution_normalize import normalize
from botsky.app import Application
from botsky.config import Settings
from botsky.delivery import deliver_async
from botsky.runtime import Runtime, runtime_lock

OWNER = "525511112222@s.whatsapp.net"
BOT = "525544445555@s.whatsapp.net"
GROUP = "123456789012345@g.us"


class RuntimeTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1793988000000
        self.settings = Settings(
            self.root,
            "own-bot",
            BOT,
            1,
            self.root / "private/test.sqlite3",
            self.now - 1000,
            OWNER,
            frozenset(),
            frozenset({GROUP}),
            transport="evolution",
            bot_ids=frozenset({BOT}),
        )
        self.app = Application(self.settings, clock=lambda: self.now)
        self.sent, self.requests, self.ack_mode = [], [], "ok"
        image = io.BytesIO()
        Image.new("RGB", (32, 24), "red").save(image, "PNG")
        self.image = image.getvalue()
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(self.provider))
        self.addAsyncCleanup(self.http.aclose)
        self.profile = {
            "evolution": {
                "base_url": "http://127.0.0.1:1",
                "api_key": "fixture-key",
                "instance": "provider-instance",
                "delivery_enabled": True,
            },
            "runtime": {
                "port": 0,
                "webhook_token": "a" * 64,
                "poll_seconds": 0.02,
                "shutdown_seconds": 0.2,
            },
        }
        self.transport = EvolutionTransport(self.app, self.profile["evolution"], self.http)

    async def provider(self, request):
        self.requests.append(request.url.path)
        if "/chat/getBase64" in request.url.path:
            return httpx.Response(200, json={"base64": base64.b64encode(self.image).decode()})
        if "/message/" in request.url.path:
            self.sent.append(json.loads(await request.aread()))
            if self.ack_mode == "lost":
                raise httpx.ReadError("synthetic lost ack")
            if self.ack_mode == "reject":
                return httpx.Response(403)
            return httpx.Response(200, json={"key": {"id": "provider-" + str(len(self.sent))}})
        raise AssertionError(request.url.path)

    def payload(
        self, text="/nota guardar tortilla", *, identifier="MSG1", group=False, media=False
    ):
        return {
            "event": "messages.upsert",
            "instance": "provider-instance",
            "sender": BOT,
            "data": {
                "key": {
                    "id": identifier,
                    "fromMe": False,
                    "remoteJid": GROUP if group else OWNER,
                    **({"participant": OWNER} if group else {}),
                },
                "messageTimestamp": self.now // 1000,
                "message": {"imageMessage": {"caption": text, "fileLength": len(self.image)}}
                if media
                else {"extendedTextMessage": {"text": text}},
            },
        }

    def rows(self, query, args=()):
        with self.app.store.transaction() as db:
            return [dict(r) for r in db.execute(query, args)]

    async def admit(self, payload):
        identifier = self.transport.enqueue(payload)["receipt_id"]
        await self.transport.receive_pending()
        self.app.recover()
        return identifier

    async def test_durable_enqueue_restart_duplicate_and_changed_payload(self):
        payload = self.payload()
        first = self.transport.enqueue(payload)
        self.assertEqual(self.rows("SELECT state FROM transport_inbox")[0]["state"], "pending")
        self.assertFalse(self.rows("SELECT * FROM notes"))
        self.app = Application(self.settings, clock=lambda: self.now)
        self.transport = EvolutionTransport(self.app, self.profile["evolution"], self.http)
        await self.admit(payload)
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)
        self.assertTrue(self.transport.enqueue(payload)["duplicate"])
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.transport.enqueue(self.payload("/nota guardar otra"))
        self.assertEqual(
            await deliver_async(
                self.app.store, first["receipt_id"], self.settings, self.transport, self.app.clock
            ),
            1,
        )
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.rows("SELECT payload FROM transport_inbox")[0]["payload"], "")

    async def test_media_quote_ownership_and_real_pdf_delivered(self):
        await self.admit(self.payload("", media=True, identifier="PHOTO1"))
        command = self.payload("/convertir pdf", identifier="CONVERT")
        command["data"]["message"]["extendedTextMessage"]["contextInfo"] = {
            "stanzaId": "PHOTO1",
            "mentionedJid": [BOT],
            "participant": OWNER,
        }
        identifier = await self.admit(command)
        await self.app.jobs.run_pending()
        self.assertEqual(
            self.rows("SELECT state FROM jobs WHERE id=?", (identifier,))[0]["state"], "succeeded"
        )
        self.assertEqual(
            await deliver_async(
                self.app.store, identifier, self.settings, self.transport, self.app.clock
            ),
            1,
        )
        media = next(body for body in self.sent if "media" in body)
        self.assertEqual(len(PdfReader(io.BytesIO(base64.b64decode(media["media"]))).pages), 1)
        self.assertEqual(media["mimetype"], "application/pdf")
        self.assertEqual(media["number"], OWNER)
        self.assertEqual(
            self.requests.count("/chat/getBase64FromMediaMessage/provider-instance"), 1
        )
        other = self.payload("/convertir pdf", identifier="FOREIGN", group=True)
        other["data"]["message"]["extendedTextMessage"]["contextInfo"] = {"stanzaId": "PHOTO1"}
        identifier = await self.admit(other)
        result = json.loads(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (identifier,))[0]["result_json"]
        )
        self.assertNotEqual(result["code"], "job_queued")

    async def test_normalization_aliases_ambiguity_mentions_wrappers_and_cutoff(self):
        p = self.payload(group=True)
        p["data"]["key"].update(participant="123456789@lid", participantPn=OWNER)
        p["data"]["message"] = {
            "ephemeralMessage": {
                "message": {
                    "extendedTextMessage": {
                        "text": "/ayuda",
                        "contextInfo": {"mentionedJid": [BOT], "stanzaId": "QUOTE"},
                    }
                }
            }
        }
        incoming, _, _ = normalize(p, self.settings, "provider-instance", self.now)
        self.assertEqual(incoming.scope.actor, OWNER)
        self.assertEqual(incoming.mentioned_ids, (BOT,))
        self.assertEqual(incoming.quoted_message_id, "QUOTE")
        p["data"]["key"]["participantAlt"] = "525599998888@s.whatsapp.net"
        with self.assertRaises(ValueError):
            normalize(p, self.settings, "provider-instance", self.now)
        for kind in (
            "old",
            "future",
            "history",
            "account",
            "instance",
            "missing-time",
            "from-self",
        ):
            p = self.payload(identifier=kind)
            if kind == "old":
                p["data"]["messageTimestamp"] -= 900
            if kind == "future":
                p["data"]["messageTimestamp"] += 900
            if kind == "history":
                p["data"]["historical"] = True
            if kind == "account":
                p["sender"] = OWNER
            if kind == "instance":
                p["instance"] = "foreign"
            if kind == "missing-time":
                p["data"].pop("messageTimestamp")
            if kind == "from-self":
                p["data"]["key"]["fromMe"] = True
            if kind in ("account", "instance", "missing-time"):
                with self.assertRaises(ValueError):
                    self.transport.enqueue(p)
            else:
                self.transport.enqueue(p)
        await self.transport.receive_pending()
        self.app.recover()
        self.assertFalse(self.rows("SELECT * FROM notes"))
        self.assertFalse(self.requests)

    async def test_uncertain_ack_cancel_and_restart_never_repeat_send(self):
        identifier = await self.admit(self.payload())
        self.ack_mode = "lost"
        self.assertEqual(
            await deliver_async(
                self.app.store, identifier, self.settings, self.transport, self.app.clock
            ),
            0,
        )
        self.assertEqual(self.rows("SELECT state FROM outbox")[0]["state"], "uncertain")
        self.app.store.recover_deliveries(self.settings, self.now)
        self.assertEqual(
            await deliver_async(
                self.app.store, identifier, self.settings, self.transport, self.app.clock
            ),
            0,
        )
        self.assertEqual(len(self.sent), 1)
        for name in ("crash", "cancel"):
            identifier = await self.admit(self.payload(identifier=name))
            if name == "crash":
                self.app.store.claim_part(identifier, self.settings, self.now)
                self.app.store.recover_deliveries(self.settings, self.now)
            else:

                class Cancelling:
                    async def send(self, part):
                        raise asyncio.CancelledError()

                with self.assertRaises(asyncio.CancelledError):
                    await deliver_async(
                        self.app.store, identifier, self.settings, Cancelling(), self.app.clock
                    )
            self.assertEqual(
                self.rows("SELECT state FROM outbox WHERE receipt_id=?", (identifier,))[0]["state"],
                "uncertain",
            )

    async def test_rejected_ack_and_disabled_delivery_have_no_retry(self):
        runtime = Runtime(self.app, self.profile, self.http)
        identifier = await self.admit(self.payload())
        self.ack_mode = "reject"
        await runtime.delivery_once()
        await runtime.delivery_once()
        self.assertEqual(
            self.rows("SELECT state FROM outbox WHERE receipt_id=?", (identifier,))[0]["state"],
            "failed",
        )
        self.assertEqual(len(self.sent), 1)
        profile = copy.deepcopy(self.profile)
        profile["evolution"]["delivery_enabled"] = False
        runtime = Runtime(self.app, profile, self.http)
        await self.admit(self.payload(identifier="disabled"))
        await runtime.delivery_once()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(
            self.rows("SELECT count(*) n FROM outbox WHERE state='pending'")[0]["n"], 1
        )

    async def test_http_auth_limits_durable_ack_and_continuous_shutdown(self):
        runtime = Runtime(self.app, self.profile, self.http)
        stop, ready = asyncio.Event(), asyncio.Event()
        running = asyncio.create_task(runtime.run(stop, on_ready=lambda port: ready.set()))
        self.addAsyncCleanup(self.stop_runtime, stop, running)
        await asyncio.wait_for(ready.wait(), 3)
        with self.assertRaisesRegex(RuntimeError, "already_running"):
            with runtime_lock(self.root):
                pass
        url = f"http://127.0.0.1:{runtime.webhook.port}"
        async with httpx.AsyncClient(trust_env=False) as http:
            self.assertEqual(
                (await http.post(url + "/webhook/evolution", json=self.payload())).status_code, 401
            )
            headers = {"Authorization": "Bearer " + "a" * 64}
            self.assertEqual((await http.get(url + "/healthz", headers=headers)).status_code, 200)
            response = await http.post(
                url + "/webhook/evolution", headers=headers, json=self.payload()
            )
            self.assertEqual(response.status_code, 202)
            identifier = response.json()["receipt_id"]
            self.assertEqual(
                (
                    await http.post(
                        url + "/webhook/evolution", headers=headers, json=self.payload()
                    )
                ).status_code,
                202,
            )
            self.assertEqual(
                (
                    await http.post(
                        url + "/webhook/evolution",
                        headers=headers,
                        json=self.payload("/nota guardar conflict"),
                    )
                ).status_code,
                409,
            )
            for _ in range(150):
                if self.rows("SELECT state FROM outbox WHERE receipt_id=?", (identifier,)) == [
                    {"state": "accepted"}
                ]:
                    break
                await asyncio.sleep(0.02)
            self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)
            self.assertEqual(len(self.sent), 1)
            headers["Content-Type"] = "application/json"
            reader, writer = await asyncio.open_connection("127.0.0.1", runtime.webhook.port)
            writer.write(
                (
                    "POST /webhook/evolution HTTP/1.1\r\nAuthorization: Bearer "
                    + "a" * 64
                    + "\r\nContent-Type: application/json\r\nContent-Length: 1048577\r\n\r\n"
                ).encode()
            )
            await writer.drain()
            self.assertIn(b"413", await reader.readline())
            writer.close()
            await writer.wait_closed()
        stop.set()
        await asyncio.wait_for(running, 3)
        self.assertFalse(runtime.running)
        self.assertFalse(runtime.webhook.server.is_serving())

    async def stop_runtime(self, stop, running):
        stop.set()
        await asyncio.wait_for(running, 3)

    async def test_runtime_scheduler_notices_and_failure_stop_other_loops(self):
        runtime = Runtime(self.app, self.profile, self.http)
        self.app.poll_call_notices = AsyncMock()
        await runtime.scheduler_once()
        self.app.poll_call_notices.assert_not_awaited()
        runtime.options.update(scheduler_enabled=True, notices_enabled=True)
        self.app.calls = object()
        called = []
        self.app.scheduler.tick = lambda: called.append(True)
        await runtime.scheduler_once()
        self.assertEqual(called, [True])
        self.app.poll_call_notices.assert_awaited_once()

        async def fail():
            raise RuntimeError("synthetic-loop-failure")

        runtime.jobs_once = fail
        with self.assertRaisesRegex(RuntimeError, "synthetic-loop-failure"):
            await asyncio.wait_for(runtime.run(asyncio.Event()), 3)
        self.assertFalse(runtime.running)
        self.assertFalse(runtime.webhook.server.is_serving())

    async def test_media_error_reports_without_executing_command(self):
        self.image = b"not a supported file"
        identifier = await self.admit(self.payload("/nota guardar must-not-execute", media=True))
        self.assertFalse(self.rows("SELECT * FROM notes"))
        result = json.loads(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (identifier,))[0]["result_json"]
        )
        self.assertEqual(result["status"], "failed")
        self.assertFalse(list((self.root / "private/ingress").glob("*.tmp")))

    async def test_crash_after_media_admission_reuses_attachments(self):
        payload = self.payload("", media=True)
        identifier = await self.admit(payload)
        with self.app.store.transaction() as db:
            db.execute(
                "UPDATE transport_inbox SET state='pending',payload=? WHERE id=?",
                (json.dumps(payload), identifier),
            )
        await self.transport.receive_pending()
        self.assertEqual(len(self.rows("SELECT * FROM artifacts")), 1)
        self.assertEqual(
            self.requests.count("/chat/getBase64FromMediaMessage/provider-instance"), 1
        )

    async def test_partial_uncertainty_does_not_starve_other_receipts(self):
        for n in range(24):
            await self.admit(self.payload("/ayuda", identifier="HELP" + str(n)))
        runtime = Runtime(self.app, self.profile, self.http)
        self.ack_mode = "lost"
        await runtime.delivery_once()
        await runtime.delivery_once()
        self.assertEqual(len(self.sent), 24)
        self.assertEqual(
            self.rows("SELECT count(*) n FROM outbox WHERE state='uncertain'")[0]["n"], 24
        )
        await runtime.delivery_once()
        self.assertEqual(len(self.sent), 24)

    async def test_sticker_uses_native_endpoint_and_scoped_output(self):
        identifier = await self.admit(self.payload("/sticker", media=True))
        await self.app.jobs.run_pending()
        await deliver_async(
            self.app.store, identifier, self.settings, self.transport, self.app.clock
        )
        self.assertIn("/message/sendSticker/provider-instance", self.requests)
        sticker = next(part for part in self.sent if "sticker" in part)
        with Image.open(io.BytesIO(base64.b64decode(sticker["sticker"]))) as image:
            self.assertEqual(image.format, "WEBP")
        self.assertEqual(sticker["number"], OWNER)

    async def test_stopping_runtime_cleans_incomplete_http_connections(self):
        runtime = Runtime(self.app, self.profile, self.http)
        stop, ready = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(runtime.run(stop, on_ready=lambda port: ready.set()))
        self.addAsyncCleanup(self.stop_runtime, stop, task)
        await asyncio.wait_for(ready.wait(), 3)
        reader, writer = await asyncio.open_connection("127.0.0.1", runtime.webhook.port)
        writer.write(b"POST /webhook/evolution HTTP/1.1\r\n")
        await writer.drain()
        await asyncio.sleep(0)
        stop.set()
        await asyncio.wait_for(task, 3)
        self.assertEqual(await reader.read(), b"")
        self.assertFalse(runtime.webhook.connections)
        self.assertFalse(runtime.webhook.writers)
        writer.close()
        await writer.wait_closed()

    async def test_stop_during_av_startup_cancels_owned_start_before_http_admission(self):
        from types import SimpleNamespace

        entered, cancelled, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def start():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        services = SimpleNamespace(start_calls=start, call_process=None)
        runtime = Runtime(self.app, self.profile, self.http, services=services)
        task = asyncio.create_task(runtime.run(stop))
        await asyncio.wait_for(entered.wait(), 3)
        stop.set()
        await asyncio.wait_for(task, 3)
        self.assertTrue(cancelled.is_set())
        self.assertFalse(runtime.running)
        self.assertIsNone(runtime.webhook.server)

    async def test_slow_media_does_not_block_text_commands_and_cancels_on_shutdown(self):
        runtime = Runtime(self.app, self.profile, self.http)
        runtime.options["shutdown_seconds"] = 0.02
        entered, cancelled, stop, ready = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        async def slow(record):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        runtime.transport.download = slow
        media = runtime.transport.enqueue(self.payload("", media=True, identifier="SLOW"))
        task = asyncio.create_task(runtime.run(stop, on_ready=lambda port: ready.set()))
        self.addAsyncCleanup(self.stop_runtime, stop, task)
        await asyncio.wait_for(ready.wait(), 3)
        await asyncio.wait_for(entered.wait(), 3)
        runtime.transport.enqueue(
            self.payload("/nota guardar sin esperar medios", identifier="FAST")
        )
        for _ in range(100):
            if self.rows("SELECT count(*) n FROM notes")[0]["n"] == 1:
                break
            await asyncio.sleep(0.02)
        self.assertEqual(len(self.rows("SELECT * FROM notes")), 1)
        stop.set()
        await asyncio.wait_for(task, 3)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(
            self.rows("SELECT state FROM transport_inbox WHERE id=?", (media["receipt_id"],))[0][
                "state"
            ],
            "pending",
        )
