"""R6 end-to-end local: SQLite real, proveedores HTTP dobles y datos sintéticos."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx

from botsky.adapters.drive import DriveClient
from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.adapters.messenger import Messenger
from botsky.adapters.oauth import OAuthToken
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result
from botsky.domains.contacts import Contact, Directory


class IntegrationsTest(IsolatedAsyncioTestCase):
    async def test_drive_revoked_authorization_has_actionable_message_without_claiming_upload(self):
        from botsky.adapters.drive import DriveError

        class RevokedDrive:
            available = True
            folder_id = "synthetic"

            async def storage_quota(self):
                raise DriveError("oauth_refresh_rejected")

        self.app.drive = RevokedDrive()
        receipt = self.receive("/drive cuota")
        await self.app.jobs.run_pending()
        result = self.result(receipt)
        self.assertEqual(result.code, "oauth_refresh_rejected")
        self.assertEqual(result.status, "failed")
        self.assertIn("volver a conectar", result.text)
        self.assertNotIn("subida", result.text)

    async def asyncSetUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1793962800000
        self.settings = Settings(
            self.root,
            "integrations-lab",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice"}),
            frozenset({"group"}),
        )
        self.directory = Directory(
            (
                Contact("Amiga", "123456789@s.whatsapp.net"),
                Contact("Otra", "987654321@s.whatsapp.net"),
            )
        )
        self.app = Application(self.settings, clock=lambda: self.now, directory=self.directory)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.n = 0
        self.http_calls = []

    def incoming(self, text, actor="owner", chat="private", **kw):
        self.n += 1
        return self.adapter.incoming(str(self.n), actor, chat, text, **kw)

    def receive(self, text, **kw):
        return self.app.receive(self.incoming(text, **kw))

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def result(self, receipt):
        return Result.from_json(
            self.rows(
                "SELECT result_json FROM inbox WHERE id=?",
                (receipt.id if hasattr(receipt, "id") else receipt,),
            )[0]["result_json"]
        )

    async def messenger(self, handler=None):
        def success(request):
            self.http_calls.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"key": {"id": "out-" + str(len(self.http_calls))}})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler or success))
        self.addAsyncCleanup(http.aclose)
        self.app.messenger = Messenger("http://127.0.0.1:1", "lab", "synthetic", client=http)

    async def preview(self, text="/recado preparar --para Amiga -- hola literal"):
        receipt = self.receive(text)
        self.assertEqual(receipt.result.code, "message_preview")
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 1
        return receipt, receipt.result.data["draft_id"]

    async def test_message_preview_owner_private_directory_literal_and_duplicate(self):
        await self.messenger()
        self.assertEqual(self.receive("/contactos", actor="alice").result.code, "owner_required")
        self.assertEqual(
            self.receive(
                "/recado preparar --para Amiga -- hola", chat="group", is_group=True
            ).result.code,
            "message_private_required",
        )
        self.assertEqual(
            self.receive("/recado preparar --para Desconocida -- hola").result.code,
            "message_recipient_unknown",
        )
        receipt = self.receive("/recado preparar --para Amiga -- /nota guardar NO_EJECUTAR")
        identifier = receipt.result.data["draft_id"]
        self.assertEqual(
            self.receive("/recado enviar " + identifier).result.code, "message_preview_required"
        )
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 1
        incoming = self.incoming("/recado enviar " + identifier)
        sent = self.app.receive(incoming)
        self.assertEqual(sent.result.code, "job_queued")
        self.assertTrue(self.app.receive(incoming).duplicate)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(sent).data["state"], "completed")
        self.assertEqual(len(self.http_calls), 1)
        self.assertEqual(self.http_calls[0][1]["text"], "/nota guardar NO_EJECUTAR")
        self.assertEqual(self.rows("SELECT * FROM notes"), [])
        self.receive("/recado enviar " + identifier)
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.http_calls), 1)

    async def test_message_partial_uncertain_restart_never_sends_second_destination(self):
        calls = []

        def handle(request):
            calls.append(json.loads(request.content)["number"])
            if len(calls) == 2:
                raise httpx.ReadTimeout("cut", request=request)
            return httpx.Response(200, json={"key": {"id": "first"}})

        await self.messenger(handle)
        _, identifier = await self.preview("/recado preparar --para Amiga,Otra -- literal")
        sent = self.receive("/recado enviar " + identifier)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(sent).status, "uncertain")
        self.assertEqual(
            [p["state"] for p in self.rows("SELECT state FROM message_parts ORDER BY position")],
            ["accepted", "uncertain"],
        )
        restarted = Application(
            self.settings,
            clock=lambda: self.now,
            directory=self.directory,
            messenger=self.app.messenger,
        )
        await restarted.jobs.run_pending()
        restarted.receive(self.incoming("/recado enviar " + identifier))
        await restarted.jobs.run_pending()
        self.assertEqual(len(calls), 2)

    async def test_message_directory_change_expiry_cancel_and_stale_confirmation(self):
        await self.messenger()
        preview, identifier = await self.preview()
        self.app.directory = Directory((Contact("Amiga", "111111111@s.whatsapp.net"),))
        self.assertEqual(
            self.receive("/recado enviar " + identifier).result.code, "message_directory_changed"
        )
        self.app.directory = self.directory
        self.now += 300000
        self.assertEqual(
            self.receive("/recado enviar " + identifier).result.code, "message_preview_expired"
        )
        _, identifier = await self.preview()
        self.receive("/recado cancelar " + identifier)
        self.assertEqual(
            self.receive("/recado enviar " + identifier).result.data["state"], "cancelled"
        )
        preview, identifier = await self.preview()
        old = self.incoming("/recado enviar " + identifier, source_ms=self.now - 2)
        self.assertEqual(self.app.receive(old).result.code, "message_preview_required")
        self.assertEqual(self.http_calls, [])

    async def test_message_quote_attachment_and_ownership_and_mid_send_cancel(self):
        await self.messenger()
        path = self.root / "literal.txt"
        path.write_text("archivo propio sintético")
        source = self.app.attach_local(self.incoming("texto fuente literal"), path)
        self.app.receive(source)
        receipt = self.receive(
            "/recado preparar --para Amiga --fuente cita --adjunto",
            quoted_message_id=source.message_id,
        )
        self.assertEqual(receipt.result.code, "message_preview")
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 1
        sent = self.receive("/recado enviar " + receipt.result.data["draft_id"])
        await self.app.jobs.run_pending()
        self.assertEqual([p[0].split("/")[-2] for p in self.http_calls], ["sendMedia", "sendText"])
        self.assertEqual(self.http_calls[1][1]["text"], "texto fuente literal")
        self.assertEqual(self.result(sent).data["state"], "completed")
        foreign = self.app.attach_local(self.incoming("archivo ajeno", actor="alice"), path)
        self.app.receive(foreign)
        self.assertEqual(
            self.receive(
                "/recado preparar --para Amiga --fuente cita --adjunto",
                quoted_message_id=foreign.message_id,
            ).result.status,
            "failed",
        )
        gate = asyncio.Event()

        async def slow(request):
            gate.set()
            await asyncio.Event().wait()

        await self.messenger(slow)
        _, identifier = await self.preview()
        sent = self.receive("/recado enviar " + identifier)
        worker = asyncio.create_task(self.app.jobs.run_pending())
        await asyncio.wait_for(gate.wait(), 2)
        self.receive("/cancelar " + sent.id)
        await asyncio.wait_for(worker, 2)
        self.assertEqual(
            self.rows("SELECT state FROM message_parts WHERE draft_id=?", (identifier,))[0][
                "state"
            ],
            "uncertain",
        )
        self.assertEqual(self.result(sent).code, "request_cancelled")

    async def test_message_crash_and_revoked_owner_stop_before_next_send(self):
        await self.messenger()
        _, identifier = await self.preview()
        sent = self.receive("/recado enviar " + identifier)
        job = self.app.jobs.claim()
        self.app.jobs.mark_provider(job)
        with self.app.store.transaction() as db:
            db.execute("UPDATE message_parts SET state='sending' WHERE draft_id=?", (identifier,))
        self.now += 1831000
        restarted = Application(
            self.settings,
            clock=lambda: self.now,
            directory=self.directory,
            messenger=self.app.messenger,
        )
        self.assertIsNone(restarted.jobs.claim())
        self.assertEqual(self.result(sent).code, "provider_interrupted")
        self.assertEqual(
            self.rows("SELECT state FROM message_parts WHERE draft_id=?", (identifier,))[0][
                "state"
            ],
            "uncertain",
        )
        self.assertEqual(self.http_calls, [])
        _, identifier = await self.preview()
        self.receive("/recado enviar " + identifier)
        self.app.settings = replace(self.settings, owner="alice", friends=frozenset({"owner"}))
        await self.app.jobs.run_pending()
        self.assertEqual(self.http_calls, [])

    async def drive(self):
        scope = None
        self.drive_calls = []

        def meta():
            return {
                "id": "file1",
                "name": "literal.txt",
                "mimeType": "text/plain",
                "size": "3",
                "parents": ["folder1"],
                "appProperties": {"botsky_scope": scope},
                "trashed": False,
            }

        def handle(request):
            nonlocal scope
            self.drive_calls.append((request.method, request.url.path))
            if request.url.path.endswith("generateIds"):
                return httpx.Response(200, json={"ids": ["file1"]})
            if request.url.path.endswith("/folder1"):
                return httpx.Response(
                    200,
                    json={
                        "id": "folder1",
                        "name": "Lab",
                        "mimeType": "application/vnd.google-apps.folder",
                        "trashed": False,
                        "capabilities": {"canAddChildren": True},
                    },
                )
            if request.url.path.endswith("/files") and request.method == "GET":
                import re

                scope = re.search("value='([a-f0-9]+)'", request.url.params["q"])[1]
                return httpx.Response(200, json={"files": [meta()]})
            if request.url.params.get("alt") == "media":
                return httpx.Response(200, content=b"abc")
            if request.url.path.endswith("/about"):
                return httpx.Response(200, json={"storageQuota": {"usage": "100"}})
            if request.method == "POST":
                body = json.loads(request.content)
                scope = body["appProperties"]["botsky_scope"]
                return httpx.Response(
                    200,
                    headers={
                        "Location": "https://www.googleapis.com/upload/drive/v3/files?upload_id=lab"
                    },
                )
            return httpx.Response(200, json=meta())

        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(http.aclose)

        async def token():
            return "synthetic"

        self.app.drive = DriveClient("folder1", token, client=http)

    async def test_drive_search_selection_delivered_scope_and_real_artifact(self):
        await self.drive()
        search = self.receive("/drive buscar literal")
        await self.app.jobs.run_pending()
        result = self.result(search)
        identifier = result.data["view_id"]
        self.assertEqual(
            self.receive("/drive elegir " + identifier + " 1").result.code, "drive_view_unavailable"
        )
        self.app.deliver(search.id, CollectingTransport())
        self.assertEqual(
            self.receive("/drive elegir " + identifier + " 1", actor="alice").result.code,
            "drive_view_unavailable",
        )
        self.assertEqual(
            self.receive("/drive elegir " + identifier + " 5").result.code,
            "drive_choice_out_of_range",
        )
        choice = self.receive("/drive elegir " + identifier + " 1")
        await self.app.jobs.run_pending()
        result = self.result(choice)
        self.assertEqual(result.code, "drive_downloaded")
        self.assertEqual(self.app.artifacts.path(result.data["artifacts"][0]).read_bytes(), b"abc")
        self.now += 300001
        self.assertEqual(
            self.receive("/drive elegir " + identifier + " 1").result.code, "drive_view_unavailable"
        )
        self.assertEqual(self.receive("/drive cuota", actor="alice").result.code, "owner_required")

    async def test_drive_save_reserved_identity_hash_and_no_repeat_after_restart(self):
        await self.drive()
        path = self.root / "source.txt"
        path.write_bytes(b"abc")
        incoming = self.app.attach_local(self.incoming("/drive guardar"), path)
        receipt = self.app.receive(incoming)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).code, "drive_saved")
        self.assertEqual(self.rows("SELECT state FROM drive_uploads")[0]["state"], "uploaded")
        self.app.receive(incoming)
        await self.app.jobs.run_pending()
        self.assertEqual(len([c for c in self.drive_calls if c[0] == "POST"]), 1)
        self.assertEqual(len([c for c in self.drive_calls if c[0] == "PUT"]), 1)

    async def test_oauth_explicit_private_storage_rotation_single_refresh_and_no_redirect(self):
        directory = self.root / "private/drive"
        directory.mkdir(mode=0o700)
        for name, value in [
            ("client.json", {"client_id": "synthetic-client", "client_secret": "synthetic-secret"}),
            ("token.json", {"refresh_token": "synthetic-refresh"}),
        ]:
            p = directory / name
            p.write_text(json.dumps(value))
            p.chmod(0o600)
        calls = []

        def handle(request):
            calls.append(request)
            return httpx.Response(
                200,
                json={
                    "access_token": "synthetic-access",
                    "refresh_token": "rotated",
                    "expires_in": 3600,
                },
            )

        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(http.aclose)
        token = OAuthToken(self.root, client=http)
        values = await asyncio.gather(token(), token())
        self.assertEqual(values, ["synthetic-access"] * 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            json.loads((directory / "token.json").read_text()), {"refresh_token": "rotated"}
        )
        self.assertEqual((directory / "token.json").stat().st_mode & 0o777, 0o600)

    async def test_messenger_real_loopback_http_and_explicit_rejection(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread

        from botsky.adapters.messenger import MessageError

        captured = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                payload = b'{"key":{"id":"loopback-accepted"}}'
                self.send_response(200 if len(captured) == 1 else 400)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        backend = Messenger("http://127.0.0.1:" + str(server.server_port), "fixture", "synthetic")
        try:
            self.assertEqual(
                await backend.send("123456789@s.whatsapp.net", "text", text="literal"),
                "loopback-accepted",
            )
            with self.assertRaises(MessageError) as caught:
                await backend.send("123456789@s.whatsapp.net", "text", text="rechazado")
            self.assertFalse(caught.exception.uncertain)
        finally:
            await backend.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(captured[0]["text"], "literal")
        self.assertFalse(captured[0]["linkPreview"])

    async def test_oauth_rejects_loose_permissions_and_redirect_before_followup(self):
        from botsky.adapters.drive import DriveError

        directory = self.root / "private/drive"
        directory.mkdir(mode=0o700)
        for name, value in [
            ("client.json", {"client_id": "client", "client_secret": "secret"}),
            ("token.json", {"refresh_token": "refresh"}),
        ]:
            path = directory / name
            path.write_text(json.dumps(value))
            path.chmod(0o600)
        (directory / "client.json").chmod(0o644)
        calls = []

        def redirect(request):
            calls.append(request)
            return httpx.Response(302, headers={"Location": "https://example.invalid/oauth"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(redirect))
        self.addAsyncCleanup(http.aclose)
        token = OAuthToken(self.root, client=http)
        with self.assertRaises(DriveError):
            await token()
        self.assertEqual(calls, [])
        (directory / "client.json").chmod(0o600)
        with self.assertRaises(DriveError) as caught:
            await token()
        self.assertEqual(caught.exception.code, "oauth_refresh_rejected")
        self.assertEqual(len(calls), 1)

    async def test_two_recado_confirmations_reserve_only_one_job_and_parts(self):
        from concurrent.futures import ThreadPoolExecutor

        await self.messenger()
        _, identifier = await self.preview()
        incoming = [self.incoming("/recado enviar " + identifier) for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(self.app.receive, incoming))
        self.assertEqual(sum(r.result.code == "job_queued" for r in receipts), 1)
        self.assertEqual(len(self.rows("SELECT * FROM message_parts")), 1)
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.http_calls), 1)

    async def test_drive_configuration_change_and_dispatched_restart_never_reupload(self):
        await self.drive()
        path = self.root / "source.txt"
        path.write_bytes(b"abc")
        receipt = self.app.receive(self.app.attach_local(self.incoming("/drive guardar"), path))
        job = self.app.jobs.claim()
        with self.app.store.transaction() as db:
            db.execute(
                "INSERT INTO drive_uploads VALUES(?,?,?,?,?,?,?)",
                (
                    receipt.id,
                    "file1",
                    "folder1",
                    job["arguments"]["scope_hash"],
                    job["arguments"]["sha256"],
                    "reserved",
                    self.now,
                ),
            )
        self.app.jobs.mark_provider(job)
        self.now += 1831000
        self.assertIsNone(self.app.jobs.claim())
        self.assertEqual(self.result(receipt).status, "uncertain")
        self.assertEqual(self.rows("SELECT state FROM drive_uploads")[0]["state"], "uncertain")
        self.assertEqual(self.drive_calls, [])
        search = self.receive("/drive buscar literal")
        await self.app.jobs.run_pending()
        identifier = self.result(search).data["view_id"]
        self.app.deliver(search.id, CollectingTransport())
        self.app.drive.folder_id = "other-folder"
        self.assertEqual(
            self.receive("/drive elegir " + identifier + " 1").result.code,
            "drive_configuration_changed",
        )

    async def test_cancelled_message_or_changed_directory_between_parts_cannot_continue(self):
        calls = []

        def handle(request):
            calls.append(request)
            self.app.directory = Directory(
                (
                    Contact("Amiga", "111111111@s.whatsapp.net"),
                    Contact("Otra", "987654321@s.whatsapp.net"),
                )
            )
            return httpx.Response(200, json={"key": {"id": "accepted-first"}})

        await self.messenger(handle)
        _, identifier = await self.preview("/recado preparar --para Amiga,Otra -- literal")
        self.receive("/recado enviar " + identifier)
        await self.app.jobs.run_pending()
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [r["state"] for r in self.rows("SELECT state FROM message_parts ORDER BY position")],
            ["accepted", "cancelled"],
        )

    async def test_contact_and_draft_status_and_drive_capacity_are_scoped_read_only(self):
        await self.messenger()
        contacts = self.receive("/contactos")
        self.assertEqual(contacts.result.code, "message_contacts")
        prepared = self.receive("/recado preparar --para Amiga -- Mensaje sintético")
        identifier = prepared.result.data["draft_id"]
        status = self.receive("/recado estado " + identifier)
        self.assertEqual(status.result.status, "ok")
        self.assertEqual(len(self.http_calls), 0)
        await self.drive()
        receipt = self.receive("/drive cuota")
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).status, "ok")
