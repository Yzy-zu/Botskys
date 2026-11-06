"""Cobertura focal de rutas audiovisuales ausentes en la campaña local.

Todo el tráfico termina en calls/test/service-fixture.cjs, proceso IPC propio.
No se inicia navegador, proveedor real ni llamada telefónica.
"""

import json
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from zoneinfo import ZoneInfo

import test_calls as calls_tests

OWNER = calls_tests.OWNER
FRIEND = calls_tests.FRIEND


class CoverageAvGapsTest(IsolatedAsyncioTestCase):
    # Reutiliza el fixture y sus helpers sin exponer el TestCase original al loader.
    asyncSetUp = calls_tests.CallsTest.asyncSetUp
    close_process = calls_tests.CallsTest.close_process
    ipc = calls_tests.CallsTest.ipc
    receive = calls_tests.CallsTest.receive
    rows = calls_tests.CallsTest.rows
    result = calls_tests.CallsTest.result
    command = calls_tests.CallsTest.command

    async def test_llamar_payload_carries_explicit_fields_once_after_duplicate(self):
        requests = []
        original = self.backend._request

        async def capture(method, endpoint, **kwargs):
            if endpoint == "/v1/calls":
                requests.append((method, endpoint, kwargs["payload"], kwargs["headers"]))
            return await original(method, endpoint, **kwargs)

        self.backend._request = capture
        text = '/llamar --video --duracion 125s --tema "Tema /literal"'
        result, receipt, incoming = await self.command(text)
        self.assertEqual(result.code, "call_requested")
        self.assertTrue(self.app.receive(incoming).duplicate)
        await self.app.jobs.run_pending()
        self.assertEqual(len(requests), 1)
        method, endpoint, payload, headers = requests[0]
        self.assertEqual((method, endpoint), ("POST", "/v1/calls"))
        self.assertEqual(
            set(payload),
            {
                "inputTransport",
                "targetJid",
                "origin",
                "live",
                "video",
                "maxSeconds",
                "liveRequest",
                "sourceReceipt",
            },
        )
        self.assertEqual(payload["targetJid"], OWNER)
        self.assertEqual(payload["origin"], {"chatId": OWNER, "requesterId": OWNER})
        self.assertEqual(
            (payload["live"], payload["video"], payload["maxSeconds"]), (True, True, 125)
        )
        self.assertEqual(payload["liveRequest"], "Tema /literal")
        self.assertEqual(payload["sourceReceipt"]["chatId"], OWNER)
        self.assertEqual(headers["Idempotency-Key"], receipt.id)
        self.assertEqual(headers["X-Call-Job-Key"], receipt.id)
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)

    async def test_agenda_create_update_cancel_payloads_keep_mode_ids_and_scope(self):
        calls = []
        original = self.backend.command

        async def capture(action, payload=None, *, key=None):
            calls.append((action, dict(payload or {}), key))
            return await original(action, payload, key=key)

        self.backend.command = capture
        live, _, _ = await self.command(
            '/llamada programar 2026-11-07 13:20 --duracion 95s --tema "Repaso" --volumen 0.35'
        )
        self.assertEqual(live.code, "agenda_create")
        live_action, live_payload, live_key = calls[-1]
        expected_due = int(
            datetime(2026, 11, 7, 13, 20, tzinfo=ZoneInfo("America/Mexico_City")).timestamp() * 1000
        )
        self.assertEqual(live_action, "agenda.create")
        self.assertEqual(
            set(live_payload),
            {
                "origin",
                "dueAt",
                "timeZone",
                "targetJid",
                "maxSeconds",
                "volume",
                "endAfterAudio",
                "durationFromAnswer",
                "live",
                "liveRequest",
                "sourceReceipt",
            },
        )
        self.assertEqual(live_payload["dueAt"], expected_due)
        self.assertEqual(live_payload["timeZone"], "America/Mexico_City")
        self.assertEqual(live_payload["origin"], {"chatId": OWNER, "requesterId": OWNER})
        self.assertEqual((live_payload["targetJid"], live_payload["maxSeconds"]), (OWNER, 95))
        self.assertEqual(
            (live_payload["volume"], live_payload["endAfterAudio"], live_payload["live"]),
            (0.35, False, True),
        )
        self.assertEqual(live_payload["liveRequest"], "Repaso")
        self.assertEqual(live_payload["durationFromAnswer"], True)
        self.assertEqual(live_payload["sourceReceipt"]["chatId"], OWNER)
        schedule_id = live.data["schedule"]["id"]

        audio = await self.ipc({"action": "seedAudio"})
        prepared, _, _ = await self.command(
            "/llamada programar 2026-11-07 14:10 --audio "
            + audio["id"]
            + " --terminar-audio --volumen 0.6"
        )
        self.assertEqual(prepared.code, "agenda_create")
        _, prepared_payload, _ = calls[-1]
        self.assertEqual(prepared_payload["audioId"], audio["id"])
        self.assertEqual(prepared_payload["endAfterAudio"], True)
        self.assertEqual(prepared_payload["live"], False)
        self.assertEqual(prepared_payload["volume"], 0.6)
        self.assertNotIn("liveRequest", prepared_payload)

        updated, _, _ = await self.command(f"/llamada reprogramar {schedule_id} 2026-11-07 15:45")
        self.assertEqual(updated.code, "agenda_update")
        update_action, update_payload, _ = calls[-1]
        self.assertEqual(update_action, "agenda.update")
        self.assertEqual(set(update_payload), {"origin", "dueAt", "timeZone", "id"})
        self.assertEqual(update_payload["id"], schedule_id)
        self.assertEqual(
            update_payload["dueAt"],
            int(
                datetime(2026, 11, 7, 15, 45, tzinfo=ZoneInfo("America/Mexico_City")).timestamp()
                * 1000
            ),
        )
        self.assertEqual(update_payload["origin"], {"chatId": OWNER, "requesterId": OWNER})

        cancelled, _, _ = await self.command("/llamada cancelar-agenda " + schedule_id)
        self.assertEqual(cancelled.code, "agenda_cancel")
        cancel_action, cancel_payload, _ = calls[-1]
        self.assertEqual(cancel_action, "agenda.cancel")
        self.assertEqual(
            cancel_payload, {"origin": {"chatId": OWNER, "requesterId": OWNER}, "id": schedule_id}
        )
        listing, _, _ = await self.command("/llamada agenda")
        self.assertEqual(
            {s["id"] for s in listing.data["schedules"]}, {prepared.data["schedule"]["id"]}
        )
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 0)
        self.assertTrue(all(key is not None for action, _, key in calls if action != "agenda.list"))

    async def test_clip_id_and_name_are_distinct_catalog_selection_payloads(self):
        calls = []
        original = self.backend.command

        async def capture(action, payload=None, *, key=None):
            calls.append((action, dict(payload or {}), key))
            return await original(action, payload, key=key)

        self.backend.command = capture
        await self.command("/llamar --video")
        await self.ipc({"action": "connect"})
        status, _, _ = await self.command("/llamada estado")
        call_id = status.data["call"]["id"]
        asset = await self.ipc({"action": "seedClip"})
        listing, _, _ = await self.command("/clip lista")
        clip = listing.data["clips"][0]
        self.assertEqual(clip["id"], asset["id"])

        by_id, _, _ = await self.command("/clip poner " + clip["id"])
        self.assertEqual(by_id.code, "av_control_applied")
        action, payload, _ = calls[-1]
        self.assertEqual(action, "clip.play")
        self.assertEqual(payload, {"callId": call_id, "clipId": clip["id"]})

        # Stop current playback, then resolve the same catalog item by label.
        await self.command("/clip parar")
        by_name, _, _ = await self.command(
            "/clip poner --nombre " + json.dumps(clip["name"], ensure_ascii=False)
        )
        self.assertEqual(by_name.code, "av_control_applied")
        action, payload, _ = calls[-1]
        self.assertEqual(action, "clip.command")
        self.assertEqual(
            payload,
            {
                "callId": call_id,
                "scope": str(("calls-lab", "own", OWNER, OWNER, 0, 1)),
                "request": {"action": "play", "query": clip["name"]},
            },
        )
        self.assertNotIn("clipId", payload)

        stranger, _ = self.receive("/clip poner " + clip["id"], actor=FRIEND, chat=FRIEND)
        self.assertEqual(stranger.result.code, "call_not_configured")
        self.assertEqual((await self.ipc({"action": "stats"}))["dials"], 1)
