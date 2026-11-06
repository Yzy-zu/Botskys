"""R9: núcleo determinista/SQLite/HTTP Node real, proveedor audiovisual sintético."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx

from botsky.adapters.calls import CallsClient
from botsky.adapters.local import LocalAdapter
from botsky.app import Application
from botsky.call_policy import CallPolicy
from botsky.config import Settings
from botsky.contracts import Result

OWNER = "525511112222@s.whatsapp.net"
FRIEND = "525533334444@s.whatsapp.net"
GROUP = "123456789012345@g.us"
ROOT = Path(__file__).resolve().parents[1]


class CallsTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1793988000000  # 06/11/2026 12:00 Mexico
        self.settings = Settings(
            self.root,
            "calls-lab",
            "own",
            1,
            self.root / "private/test.sqlite3",
            self.now - 1000,
            OWNER,
            frozenset({FRIEND}),
            frozenset({GROUP}),
        )
        document = {
            "version": 1,
            "instance": "calls-lab",
            "account": "own",
            "epoch": 1,
            "owner": OWNER,
            "actors": [OWNER, FRIEND],
            "privateChats": [OWNER],
            "groups": [{"id": GROUP, "name": "Synthetic", "maxParticipants": 8}],
            "features": {"agenda": True, "incoming": False, "live": True, "outgoing": True},
            "schedule": {"timeZone": "America/Mexico_City", "startHour": 8, "endHour": 23},
        }
        self.settings = replace(self.settings, calls=CallPolicy.build(document, self.settings))
        self.process = await asyncio.create_subprocess_exec(
            "node",
            "calls/test/service-fixture.cjs",
            cwd=ROOT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.addAsyncCleanup(self.close_process)
        ready = await self.ipc(
            {
                "projectRoot": str(self.root),
                "document": document,
                "token": "a" * 64,
                "now": "2026-11-06T12:00:00-06:00",
            }
        )
        self.assertEqual(ready["revision"], self.settings.calls.revision)
        self.http = httpx.AsyncClient(trust_env=False)
        self.addAsyncCleanup(self.http.aclose)
        self.backend = CallsClient(
            self.http,
            ready["url"],
            "a" * 64,
            ready["revision"],
            self.settings.calls.targets,
            is_fixture=True,
        )
        self.app = Application(self.settings, clock=lambda: self.now, calls=self.backend)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.n = 0

    async def close_process(self):
        if self.process.returncode is None:
            try:
                await self.ipc({"action": "stop"})
                await asyncio.wait_for(self.process.wait(), 3)
            except Exception:
                self.process.kill()
                await self.process.wait()

    async def ipc(self, value):
        self.process.stdin.write((json.dumps(value) + "\n").encode())
        await self.process.stdin.drain()
        data = await asyncio.wait_for(self.process.stdout.readline(), 5)
        self.assertTrue(data, "fixture process ended")
        result = json.loads(data)
        self.assertNotIn("error", result)
        return result

    def receive(self, text, actor=OWNER, chat=OWNER, group=False):
        self.n += 1
        incoming = self.adapter.incoming(str(self.n), actor, chat, text, is_group=group)
        return self.app.receive(incoming), incoming

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

    async def command(self, text, **scope):
        receipt, incoming = self.receive(text, **scope)
        await self.app.jobs.run_pending()
        return self.result(receipt), receipt, incoming

    async def test_explicit_commands_dispatch_once_and_control_exact_call(self):
        result, receipt, incoming = await self.command(
            '/llamar --video --tema "Conversar sin ejecutar /nota"'
        )
        self.assertEqual(result.code, "call_requested")
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)
        self.assertTrue(self.app.receive(incoming).duplicate)
        await self.app.jobs.run_pending()
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)
        self.assertEqual(self.receive("/llamar")[0].result.code, "call_busy")
        await self.ipc({"action": "connect"})
        status, _, _ = await self.command("/llamada estado")
        self.assertEqual(status.data["call"]["state"], "connected")
        self.assertNotIn("key", status.to_json())
        clips, _, _ = await self.command("/clip lista")
        self.assertEqual(clips.code, "av_control_applied")
        avatar, _, _ = await self.command("/avatar expresion happy")
        self.assertEqual(avatar.code, "av_control_unconfirmed")
        ended, _, _ = await self.command("/llamada colgar")
        self.assertEqual(ended.code, "call_end_requested")
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)
        self.assertEqual(self.rows("SELECT count(*) n FROM notes")[0]["n"], 0)

    async def test_scope_transport_revision_and_access_before_provider(self):
        denied, _ = self.receive("/llamar", actor=FRIEND, chat=FRIEND)
        self.assertEqual(denied.result.code, "call_not_configured")
        self.app.calls.is_fixture = False
        denied, _ = self.receive("/llamar")
        self.assertEqual(denied.result.code, "calls_not_configured")
        self.app.calls.is_fixture = True
        self.app.calls._revision = "b" * 64
        denied, _ = self.receive("/llamar")
        self.assertEqual(denied.result.code, "calls_policy_changed")
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 0)
        self.assertEqual(self.rows("SELECT count(*) n FROM jobs")[0]["n"], 0)

    async def test_cancel_before_dispatch_persists_tombstone_across_application_restart(self):
        queued, _ = self.receive("/llamar")
        cancelled, _ = self.receive("/cancelar " + queued.id)
        self.assertEqual(cancelled.result.status, "cancelled")
        self.assertEqual(self.rows("SELECT state FROM call_cancellations")[0]["state"], "pending")
        self.app = Application(self.settings, clock=lambda: self.now, calls=self.backend)
        await self.app.jobs.run_pending()
        self.assertTrue((await self.backend.operation(queued.id))["cancelled"])
        self.assertEqual(self.rows("SELECT state FROM call_cancellations")[0]["state"], "confirmed")
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 0)

    async def test_group_call_controls_are_scoped_to_authorized_group_members(self):
        result, _, _ = await self.command("/llamar", chat=GROUP, group=True)
        self.assertEqual(result.code, "call_requested")
        outside, _, _ = await self.command("/llamada colgar")
        self.assertEqual(outside.code, "no_current_call")
        end, _, _ = await self.command("/llamada cancelar", actor=FRIEND, chat=GROUP, group=True)
        self.assertEqual(end.code, "call_end_requested")

    async def test_agenda_is_durable_without_dial_and_reprogram_cancel_keep_scope(self):
        result, _, _ = await self.command(
            '/llamada programar 2026-11-07 13:00 --tema "Tema literal" --duracion 60s'
        )
        self.assertEqual(result.code, "agenda_create")
        schedule_id = result.data["schedule"]["id"]
        listed, _, _ = await self.command("/llamada agenda")
        self.assertEqual(len(listed.data["schedules"]), 1)
        updated, _, _ = await self.command(f"/llamada reprogramar {schedule_id} 2026-11-07 14:00")
        self.assertEqual(updated.code, "agenda_update")
        cancelled, _, _ = await self.command("/llamada cancelar-agenda " + schedule_id)
        self.assertEqual(cancelled.code, "agenda_cancel")
        listed, _, _ = await self.command("/llamada agenda")
        self.assertEqual(listed.data["schedules"], [])
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 0)

    async def test_failure_notice_is_own_outbox_and_ack_does_not_redial(self):
        from botsky.contracts import DeliveryAck

        started, _, _ = await self.command("/llamar")
        self.assertEqual(started.code, "call_requested")
        await self.ipc({"action": "fail"})
        notices = await self.app.poll_call_notices()
        self.assertEqual(len(notices), 1)
        self.assertEqual(await self.app.poll_call_notices(), [])
        sent = []

        class Transport:
            def send(inner, part):
                sent.append(part)
                return DeliveryAck(True, "synthetic-acceptance")

        self.app.deliver(notices[0], Transport())
        await self.app.poll_call_notices()
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.rows("SELECT state FROM call_notices")[0]["state"], "acknowledged")
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)
        self.assertEqual(await self.app.poll_call_notices(), [])

    async def test_cancel_after_provider_acceptance_closes_exact_call_and_suppresses_late_result(
        self,
    ):
        original = self.backend.start
        reached = asyncio.Event()

        async def delayed(request):
            result = await original(request)
            reached.set()
            await asyncio.Future()
            return result

        self.backend.start = delayed
        queued, _ = self.receive("/llamar")
        worker = asyncio.create_task(self.app.jobs.run_pending())
        await asyncio.wait_for(reached.wait(), 5)
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)
        cancelled, _ = self.receive("/cancelar " + queued.id)
        self.assertEqual(cancelled.result.status, "cancelled")
        await asyncio.wait_for(worker, 5)
        state = await self.ipc({"action": "stats"})
        self.assertEqual(state["dials"], 1)
        self.assertIsNone(state["active"])
        self.assertTrue((await self.backend.operation(queued.id))["cancelled"])
        self.assertEqual(self.result(queued).status, "cancelled")

    async def test_expired_dispatched_worker_is_cancelled_without_second_offer(self):
        from botsky.adapters.calls import CallRequest

        queued, _ = self.receive("/llamar")
        job = self.app.jobs.claim()
        self.app.jobs.mark_provider(job)
        await self.backend.start(CallRequest(queued.id, job["context"].scope, OWNER, "live"))
        self.now += 2000000
        self.app = Application(self.settings, clock=lambda: self.now, calls=self.backend)
        await self.app.jobs.run_pending()
        state = await self.ipc({"action": "stats"})
        self.assertEqual(state["dials"], 1)
        self.assertIsNone(state["active"])
        self.assertTrue((await self.backend.operation(queued.id))["cancelled"])
        self.assertEqual(self.result(queued).status, "uncertain")
        self.assertEqual(self.rows("SELECT state FROM call_cancellations")[0]["state"], "confirmed")

    async def test_all_clip_controls_use_catalog_ids_and_current_session_only(self):
        await self.command("/llamar --video")
        await self.ipc({"action": "connect"})
        asset = await self.ipc({"action": "seedClip"})
        listing, _, _ = await self.command("/clip lista")
        self.assertEqual(listing.data["clips"][0]["id"], asset["id"])
        self.assertIn(asset["id"], listing.text)
        named, _, _ = await self.command(
            "/clip poner --nombre "
            + json.dumps(listing.data["clips"][0]["name"], ensure_ascii=False)
        )
        self.assertEqual(named.code, "av_control_applied")
        commands = [
            "/clip poner " + asset["id"],
            "/clip pausa",
            "/clip seguir",
            "/clip volumen 0.7",
            "/clip ajustar bajar 0.1",
            "/clip repetir",
            "/clip siguiente",
            "/clip parar",
        ]
        for command in commands:
            result, _, _ = await self.command(command)
            self.assertEqual(
                result.code,
                "av_control_unconfirmed" if command == "/clip siguiente" else "av_control_applied",
                (command, result),
            )
        await self.ipc({"action": "confirmAvatar"})
        for command in (
            "/avatar fondo neon",
            "/avatar gesto wave --duracion 2",
            "/avatar rubor suave",
        ):
            result, _, _ = await self.command(command)
            self.assertEqual(result.code, "av_control_applied", (command, result))
        await self.command("/llamada colgar")
        state, _, _ = await self.command("/llamada estado")
        self.assertEqual(state.data["call"]["state"], "ended")
        retired, _, _ = await self.command("/clip repetir")
        self.assertEqual(retired.code, "call_ended")
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)

    async def test_schedule_ids_are_delivered_and_pending_agenda_does_not_hide_active_call(self):
        await self.command("/llamar")
        scheduled, _, _ = await self.command("/llamada programar 2026-11-07 13:00")
        self.assertIn(scheduled.data["schedule"]["id"], scheduled.text)
        listing, _, _ = await self.command("/llamada agenda")
        self.assertIn(scheduled.data["schedule"]["id"], listing.text)
        state, _, _ = await self.command("/llamada estado")
        self.assertEqual(state.data["call"]["state"], "dialing")
        ended, _, _ = await self.command("/llamada colgar")
        self.assertEqual(ended.code, "call_end_requested")

    async def test_prepared_audio_agenda_retains_own_audio_id_volume_and_end_policy(self):
        audio = await self.ipc({"action": "seedAudio"})
        result, _, _ = await self.command(
            "/llamada programar 2026-11-07 13:00 --audio "
            + audio["id"]
            + " --terminar-audio --volumen 0.4"
        )
        self.assertEqual(result.code, "agenda_create")
        self.assertEqual(result.data["schedule"]["mode"], "audio preparado")
        rows = (await self.ipc({"action": "agendaData"}))["rows"]
        self.assertEqual(rows[0]["call"]["audioId"], audio["id"])
        self.assertTrue(rows[0]["call"]["endAfterAudio"])
        self.assertEqual(rows[0]["call"]["volume"], 0.4)
        self.assertFalse(rows[0]["call"]["live"])
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 0)

    async def test_backend_removed_after_admission_does_not_lose_cancellation_or_start(self):
        queued, _ = self.receive("/llamar")
        self.app.calls = None
        await self.app.jobs.run_pending()
        self.assertEqual(self.result(queued).code, "calls_not_configured")
        self.app.calls = self.backend
        await self.app.jobs.run_pending()
        self.assertTrue((await self.backend.operation(queued.id))["cancelled"])
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 0)
