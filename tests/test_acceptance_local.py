"""R10: admisión/handler/entrega aislada y campos explícitos del registro completo."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

from botsky.adapters.lab import LabTransport
from botsky.adapters.local import LocalAdapter
from botsky.app import Application
from botsky.commands.registry import Registry
from botsky.commands.router import Router
from botsky.config import Settings
from botsky.contracts import Result


def sample_with_field(spec, selected):
    chosen = {f.name for f in spec.fields if f.required} | {selected.name}
    if spec.operation in ("download_media.choose", "manage_drive.choose"):
        chosen.add("choice")
    overrides = {"container": "srt"} if selected.name == "subtitle_language" else {}
    if spec.family == "audiovisual.clip" and spec.original_action == "play":
        chosen.discard("query" if selected.name == "clip_id" else "clip_id")
    if spec.original_action == "configure_digest":
        chosen.add("digest_time")
    if spec.family == "manage_messages" and spec.original_action == "prepare":
        chosen.add("text")
    if (
        spec.family == "manage_admin"
        and spec.original_action in {"xp_grant", "xp_remove"}
        and selected.name == "amount"
    ):
        chosen.add("target")
    if spec.family == "audiovisual.agenda" and selected.name == "end_after_audio":
        chosen.add("audio_id")
    options, positional = [], []
    for field in spec.fields:
        if field.name not in chosen:
            continue
        values = [overrides.get(field.name, field.example)]
        if field.option:
            options += [field.option] + ([] if field.kind == "flag" else values)
        else:
            positional += values
    return " ".join([spec.command, *options, *positional])


class AllFieldsTest(TestCase):
    def test_each_public_field_is_explicitly_parsed_with_span_and_canonical_roundtrip(self):
        router = Router()
        count = 0
        for spec in router.registry.specs:
            for field in spec.fields:
                with self.subTest(command=spec.command, field=field.name):
                    text = sample_with_field(spec, field)
                    parsed = router.parse(text)
                    self.assertEqual(parsed.spec, spec)
                    self.assertIn(field.name, parsed.arguments)
                    self.assertIn(field.name, parsed.spans)
                    self.assertEqual(router.parse(text).canonical(), parsed.canonical())
                    count += 1
        self.assertEqual(count, 190)


class LocalTransportAcceptanceTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793988000000

    def settings(self, index):
        root = self.root / str(index)
        root.mkdir()
        return Settings(
            root,
            "acceptance-lab",
            "synthetic-account",
            1,
            root / "private/test.sqlite3",
            self.now - 1,
            "owner-synthetic",
            frozenset({"friend-synthetic"}),
            frozenset({"group-synthetic"}),
        )

    async def test_every_route_reaches_its_guard_or_handler_and_delivers_locally(self):
        # A cold route probe proves handler availability/guards, not successful
        # remote effects or every stateful path. Domain suites supply those oracles.
        for index, spec in enumerate(Registry().specs):
            with self.subTest(command=spec.command):
                settings = self.settings(index)
                app = Application(settings, clock=lambda: self.now)
                adapter = LocalAdapter(settings, lambda: self.now)
                transport = LabTransport(settings, artifacts=app.artifacts, clock=lambda: self.now)
                incoming = adapter.incoming(
                    "route-probe", settings.owner, "private-synthetic", spec.sample
                )
                receipt = app.receive(incoming)
                await app.jobs.run_pending()
                db = app.store.connect()
                try:
                    row = db.execute("SELECT * FROM inbox WHERE id=?", (receipt.id,)).fetchone()
                    result = Result.from_json(row["result_json"])
                    self.assertNotIn(
                        result.code,
                        {"capability_unavailable", "command_version_unavailable", "job_failed"},
                    )
                    self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                finally:
                    db.close()
                app.deliver(receipt.id, transport)
                self.assertGreater(transport.accepted(), 0)
                accepted = transport.accepted()
                self.assertEqual(app.deliver(receipt.id, transport), 0)
                self.assertEqual(transport.accepted(), accepted)
                self.assertTrue(app.receive(incoming).duplicate)

    async def test_transport_restarts_and_rejects_foreign_epoch(self):
        from botsky.contracts import CommandContext, DeliveryPart, Scope

        settings = self.settings("restart")
        transport = LabTransport(settings)
        context = CommandContext(
            "synthetic-receipt",
            settings.instance,
            settings.account,
            Scope(settings.owner, "private"),
            settings.epoch,
            0,
        )
        part = DeliveryPart(context.receipt_id, 0, context, "Mensaje sintético", ())
        ack = transport.send(part)
        self.assertEqual(LabTransport(settings).send(part), ack)
        self.assertEqual(transport.accepted(), 1)
        foreign = replace(part, context=replace(context, epoch=2))
        self.assertFalse(transport.send(foreign).accepted)
        with self.assertRaises(ValueError):
            transport.send(replace(part, text="contenido diferente"))
        self.assertEqual(transport.accepted(), 1)

    async def test_image_to_pdf_delivers_verified_bytes_into_the_local_receiver(self):
        import hashlib

        from PIL import Image
        from pypdf import PdfReader

        settings = self.settings("file-receiver")
        app = Application(settings, clock=lambda: self.now)
        transport = LabTransport(settings, artifacts=app.artifacts, clock=lambda: self.now)
        source = settings.root / "synthetic.png"
        Image.new("RGB", (24, 32), "blue").save(source)
        adapter = LocalAdapter(settings, lambda: self.now)
        incoming = app.attach_local(
            adapter.incoming("image-pdf", settings.owner, "private", "/convertir pdf"), source
        )
        receipt = app.receive(incoming)
        await app.jobs.run_pending()
        app.deliver(receipt.id, transport)
        with app.store.transaction() as db:
            result = Result.from_json(
                db.execute("SELECT result_json FROM inbox WHERE id=?", (receipt.id,)).fetchone()[0]
            )
            self.assertEqual(result.code, "document_converted")
            artifact_id = result.data["artifacts"][0]
            row = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            self.assertEqual(
                {
                    r[0]
                    for r in db.execute(
                        "SELECT state FROM outbox WHERE receipt_id=?", (receipt.id,)
                    )
                },
                {"accepted"},
            )
        delivered = settings.root / "private/lab/media" / row["sha256"]
        self.assertEqual(hashlib.sha256(delivered.read_bytes()).hexdigest(), row["sha256"])
        self.assertEqual(len(PdfReader(delivered).pages), 1)
        self.assertEqual(app.deliver(receipt.id, transport), 0)


class AcceptanceNetworkGuardTest(TestCase):
    def test_node_guard_rejects_normalized_and_direct_non_loopback_without_network(self):
        import subprocess

        script = r"""
const net=require('node:net'),assert=require('node:assert/strict');let calls=0;
net.Socket.prototype.connect=function(){calls++;return this;};
delete require.cache[require.resolve('./ops/restringir_red_local.cjs')];
require('./ops/restringir_red_local.cjs');
const sock=new net.Socket();
for(const args of [[{port:443,host:'provider.invalid'}],[[{port:443,host:'provider.invalid'}]],['443','provider.invalid'],[443,'provider.invalid']]){
 assert.throws(()=>sock.connect(...args),{code:'R10_NON_LOOPBACK_NETWORK_DENIED'});
}
assert.equal(calls,0);sock.connect({port:1234,host:'127.0.0.1'});assert.equal(calls,1);
sock.destroy();
"""
        subprocess.run(
            ["node", "-e", script],
            cwd=Path(__file__).resolve().parents[1],
            timeout=5,
            check=True,
            capture_output=True,
        )
