"""Biblioteca publicada sintética real; fotos verificadas y transporte doble explícito."""

import asyncio
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from uuid import uuid4

from PIL import Image

from botsky.adapters.gallery import PublishedLibrary
from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.adapters.messenger import MessageError
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result


def library_fixture(root, count=6):
    path = root / "private/gallery"
    (path / "originals").mkdir(parents=True, mode=0o700)
    db = sqlite3.connect(path / "library.db")
    db.executescript(
        "CREATE TABLE albums(id TEXT,name TEXT,slug TEXT,published INTEGER);CREATE TABLE photos(id TEXT,mime TEXT,originalPath TEXT,deletedAt TEXT,duration REAL);CREATE TABLE album_photos(albumId TEXT,photoId TEXT);"
    )
    db.execute("INSERT INTO albums VALUES('album','Geométricos sintéticos','sintetico',1)")
    for i in range(count):
        identifier = str(uuid4())
        name = f"originals/{identifier}.png"
        Image.new("RGB", (64, 64), (i * 30, 80, 120)).save(path / name)
        db.execute("INSERT INTO photos VALUES(?,?,?,NULL,NULL)", (identifier, "image/png", name))
        db.execute("INSERT INTO album_photos VALUES(?,?)", ("album", identifier))
    db.commit()
    db.close()
    return PublishedLibrary(root)


class PhotoFixture:
    available = True

    def __init__(self, states=()):
        self.calls = []
        self.states = list(states)

    async def send_photo(self, target, data, mime, *, view_once=False, caption=""):
        self.calls.append((target, data, mime, view_once, caption))
        state = self.states.pop(0) if self.states else "accepted"
        if state != "accepted":
            raise MessageError("synthetic_" + state, state == "uncertain")
        return "photo-" + str(len(self.calls))


class PacksTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793962800000
        self.library = library_fixture(self.root)
        self.transport = PhotoFixture()
        self.settings = Settings(
            self.root,
            "packs-lab",
            "local",
            1,
            self.root / "private/lab.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.app = Application(
            self.settings,
            clock=lambda: self.now,
            gallery=self.library,
            photo_transport=self.transport,
            gallery_chats=frozenset({"private", "group"}),
            daily_roll=lambda: 1,
        )
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.n = 0

    def incoming(self, text, actor="alice", chat="private", **kw):
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
            self.rows("SELECT result_json FROM inbox WHERE id=?", (receipt.id,))[0]["result_json"]
        )

    def deliver(self, receipt):
        self.app.deliver(receipt.id, CollectingTransport())
        self.now += 1

    def offer(self, **kw):
        self.receive("/daily", **kw)
        offer = self.receive("/pack comprar sintetico", **kw)
        self.assertEqual(offer.result.code, "pack_offer")
        self.deliver(offer)
        return offer.result.data["purchase_id"]

    async def test_library_actual_images_catalog_exact_category_and_symlinks(self):
        catalog = self.library.catalog()
        self.assertEqual(catalog[0].count, 6)
        photos = self.library.select("sintetico", 3, set())
        self.assertEqual(len(photos), 3)
        self.assertEqual(self.library.select("inexistente", 3, set()), [])
        photo = photos[0]
        path = self.root / "private/gallery" / ("originals/" + photo.filename)
        path.unlink()
        path.symlink_to(self.root / "outside.png")
        self.assertIsNone(self.library.get_photo(photo.id, "sintetico"))
        self.assertEqual(
            len(self.receive("/pack catalogo --categoria sintetico").result.data["items"]), 1
        )
        self.assertEqual(self.receive("/pack catalogo --pagina 2").result.code, "page_out_of_range")

    async def test_offer_delivery_scope_charge_view_once_and_no_duplicate_purchase(self):
        self.receive("/daily")
        offer = self.receive("/pack comprar sintetico")
        identifier = offer.result.data["purchase_id"]
        self.assertEqual(
            self.receive("/pack confirmar " + identifier).result.code, "pack_preview_required"
        )
        self.assertEqual(
            self.receive("/pack confirmar " + identifier, actor="bob").result.code, "pack_not_found"
        )
        self.deliver(offer)
        incoming = self.incoming("/pack confirmar " + identifier)
        receipt = self.app.receive(incoming)
        self.app.receive(incoming)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).data["state"], "completed")
        self.assertTrue(3 <= len(self.transport.calls) <= 5)
        self.assertTrue(all(c[0] == "alice" and c[3] for c in self.transport.calls))
        self.assertEqual(self.receive("/saldo").result.data["balance"], 850)
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 0)
        count = len(self.transport.calls)
        self.receive("/pack confirmar " + identifier)
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.transport.calls), count)

    async def test_partial_refund_uncertain_hold_and_restart_do_not_send_again(self):
        self.transport.states = ["accepted", "uncertain"]
        identifier = self.offer()
        receipt = self.receive("/pack confirmar " + identifier)
        await self.app.jobs.run_pending()
        result = self.result(receipt)
        self.assertEqual(result.status, "uncertain")
        parts = self.rows("SELECT * FROM gallery_parts ORDER BY position")
        cost = sum(p["cost"] for p in parts if p["state"] in ("accepted", "uncertain"))
        held = sum(p["cost"] for p in parts if p["state"] == "uncertain")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000 - cost)
        self.assertEqual(self.receive("/saldo").result.data["reserved"], held)
        restarted = Application(
            self.settings,
            clock=lambda: self.now,
            gallery=self.library,
            photo_transport=self.transport,
            gallery_chats={"private"},
        )
        await restarted.jobs.run_pending()
        self.receive("/pack confirmar " + identifier)
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.transport.calls), 2)

    async def test_failed_photo_refunds_whole_price_and_discount_expiry_has_no_charge(self):
        self.transport.states = ["failed"]
        identifier = self.offer()
        self.receive("/pack confirmar " + identifier)
        await self.app.jobs.run_pending()
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000)
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 0)
        group = dict(chat="group", is_group=True)
        hh = self.receive("/hh iniciar --duracion 1m", actor="owner", **group)
        self.deliver(hh)
        offer = self.receive("/pack comprar sintetico", **group)
        self.assertEqual(offer.result.data["price"], 75)
        self.deliver(offer)
        self.now += 60001
        self.assertEqual(
            self.receive(
                "/pack confirmar " + offer.result.data["purchase_id"], **group
            ).result.code,
            "pack_discount_expired",
        )
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000)

    async def test_cancel_during_photo_conserves_uncertainty_and_refunds_not_dispatched(self):
        gate = asyncio.Event()

        async def slow(*args, **kw):
            gate.set()
            await asyncio.Event().wait()

        self.transport.send_photo = slow
        identifier = self.offer()
        receipt = self.receive("/pack confirmar " + identifier)
        worker = asyncio.create_task(self.app.jobs.run_pending())
        await asyncio.wait_for(gate.wait(), 2)
        self.receive("/cancelar " + receipt.id)
        await asyncio.wait_for(worker, 2)
        states = [
            r["state"] for r in self.rows("SELECT state FROM gallery_parts ORDER BY position")
        ]
        self.assertEqual(states.count("uncertain"), 1)
        self.assertEqual(states.count("cancelled"), len(states) - 1)
        self.assertEqual(self.result(receipt).code, "request_cancelled")

    async def coop(self, target=100):
        group = dict(chat="group", is_group=True)
        receipt = self.receive("/coop crear sintetico " + str(target), **group)
        await self.app.jobs.run_pending()
        result = self.result(receipt)
        self.assertEqual(result.code, "coop_preview")
        identifier = result.data["challenge_id"]
        self.deliver(receipt)
        return identifier, group

    async def test_coop_publication_own_contributions_goal_and_single_settlement(self):
        self.receive("/daily")
        self.receive("/daily", actor="bob")
        identifier, group = await self.coop()
        alice = self.receive("/coop aportar " + identifier + " 30", **group)
        self.assertEqual(alice.result.data["total"], 30)
        self.assertEqual(self.receive("/saldo", actor="bob").result.data["balance"], 1000)
        self.assertEqual(
            self.receive("/coop aportar " + identifier + " 71", actor="bob", **group).result.code,
            "coop_over_target",
        )
        incoming = self.incoming("/coop aportar " + identifier + " 70", actor="bob", **group)
        receipt = self.app.receive(incoming)
        self.app.receive(incoming)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).data["state"], "completed")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 970)
        self.assertEqual(self.receive("/saldo", actor="bob").result.data["balance"], 930)
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 0)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.transport.calls[0][0], "group")
        self.assertFalse(self.transport.calls[0][3])
        self.receive("/coop cancelar " + identifier, **group)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 970)
        self.assertEqual(
            self.receive("/coop estado " + identifier).result.code, "coop_group_required"
        )

    async def test_coop_expiry_aggregate_rounding_and_cancellation_ownership(self):
        self.receive("/daily")
        self.receive("/daily", actor="bob")
        identifier, group = await self.coop()
        self.receive("/coop aportar " + identifier + " 1", **group)
        self.receive("/coop aportar " + identifier + " 2", **group)
        self.assertEqual(
            self.receive("/coop cancelar " + identifier, actor="bob", **group).result.code,
            "coop_creator_required",
        )
        self.now += 600001
        self.app.scheduler.tick()
        result = self.receive("/coop estado " + identifier, **group).result
        self.assertEqual(result.data["state"], "expired")
        self.assertEqual(result.data["refund"], 2)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 999)
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 0)
        self.receive("/coop cancelar " + identifier, **group)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 999)

    async def test_coop_uncertain_keeps_escrow_and_never_repeats_photo(self):
        self.receive("/daily")
        self.transport.states = ["uncertain"]
        identifier, group = await self.coop()
        receipt = self.receive("/coop aportar " + identifier + " 100", **group)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).status, "uncertain")
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 100)
        self.assertEqual(
            self.receive("/coop cancelar " + identifier, **group).result.data["state"], "uncertain"
        )
        await self.app.jobs.run_pending()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.receive("/saldo").result.data["balance"], 900)

    async def test_coop_missing_original_refunds_known_failure_and_preview_is_censored(self):
        self.receive("/daily")
        identifier, group = await self.coop()
        row = self.rows("SELECT * FROM cooperachas WHERE id=?", (identifier,))[0]
        photo = json.loads(row["photo_json"])
        original = self.library.get_photo(photo["id"], "sintetico")
        artifact = self.rows("SELECT * FROM artifacts WHERE origin='result'")[0]
        self.assertNotEqual(self.app.artifacts.path(artifact["id"]).read_bytes(), original.data)
        (self.library.root / "originals" / original.filename).unlink()
        receipt = self.receive("/coop aportar " + identifier + " 100", **group)
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(receipt).data["state"], "failed")
        self.assertEqual(self.receive("/saldo").result.data["balance"], 1000)
        self.assertEqual(self.receive("/saldo").result.data["reserved"], 0)
        self.assertEqual(self.transport.calls, [])

    async def test_happy_rain_reward_and_scheduled_ticks_have_durable_parts(self):
        group = dict(chat="group", is_group=True)
        event = self.receive("/hh iniciar --duracion 10m", actor="owner", **group)
        self.deliver(event)
        identifier = event.result.data["event_id"]
        self.assertEqual(
            self.receive("/hh lluvia " + identifier, actor="owner", **group).result.code,
            "job_queued",
        )
        await self.app.jobs.run_pending()
        self.assertTrue(1 <= len(self.transport.calls) <= 2)
        self.assertTrue(all(c[0] == "group" and not c[3] for c in self.transport.calls))
        drop = self.receive("/hh airdrop " + identifier, actor="owner", **group)
        self.deliver(drop)
        claim = self.receive("/hh reclamar " + drop.result.data["drop_id"], **group)
        self.assertEqual(claim.result.data["gained"], 500)
        await self.app.jobs.run_pending()
        private = [c for c in self.transport.calls if c[0] == "alice"]
        self.assertTrue(3 <= len(private) <= 6)
        self.assertTrue(all(c[3] for c in private))
        previous = len(self.transport.calls)
        self.now += 240001
        reserved = self.app.scheduler.tick()
        self.assertEqual(len(reserved), 1)
        self.assertEqual(self.app.scheduler.tick(), [])
        await self.app.jobs.run_pending()
        self.assertGreater(len(self.transport.calls), previous)
        self.assertEqual(
            self.rows("SELECT count(*) AS n FROM happy_photo_jobs WHERE kind='rain'")[0]["n"], 2
        )

    async def test_happy_automatic_drop_is_accepted_before_award_and_stop_retires_rain(self):
        group = dict(chat="group", is_group=True)
        event = self.receive("/hh iniciar --duracion 10m", actor="owner", **group)
        self.deliver(event)
        identifier = event.result.data["event_id"]
        self.now += 30001
        receipts = self.app.scheduler.tick()
        self.assertEqual(len(receipts), 2)
        drop = self.rows("SELECT * FROM happy_drops")[0]
        self.assertEqual(
            self.receive("/hh reclamar " + drop["id"], **group).result.code,
            "happy_drop_unavailable",
        )
        self.app.deliver(drop["receipt_id"], CollectingTransport())
        self.now += 1
        self.assertEqual(
            self.receive("/hh reclamar " + drop["id"], **group).result.data["gained"], 500
        )
        self.receive("/hh parar " + identifier, actor="owner", **group)
        await self.app.jobs.run_pending()
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.receive("/saldo").result.data["balance"], 500)

    async def test_photo_http_payload_retains_view_once_and_real_fixture_bytes(self):
        import base64

        import httpx

        from botsky.adapters.messenger import Messenger

        photo = self.library.select("sintetico", 1, set())[0]
        calls = []

        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"key": {"id": "synthetic-photo-ack"}})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(http.aclose)
        client = Messenger("http://127.0.0.1:1", "local", "synthetic", client=http)
        self.assertEqual(
            await client.send_photo(
                "111111111@s.whatsapp.net", photo.data, photo.mime, view_once=True
            ),
            "synthetic-photo-ack",
        )
        self.assertTrue(calls[0]["viewOnce"])
        self.assertEqual(base64.b64decode(calls[0]["media"]), photo.data)
        self.assertEqual(calls[0]["mediatype"], "image")
