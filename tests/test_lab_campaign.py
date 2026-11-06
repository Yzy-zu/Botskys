"""Guardias del runner remoto con HTTP sintético; nunca envía a WhatsApp."""

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx

SPEC = importlib.util.spec_from_file_location(
    "lab_campaign", Path(__file__).resolve().parents[1] / "ops/campana_lab.py"
)
campaign = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign)


class LabCampaignTest(IsolatedAsyncioTestCase):
    async def test_missing_dependency_is_blocked_before_parsing_or_network(self):
        previous = {"search": {"receipt": "synthetic", "data": {}}}
        with self.assertRaisesRegex(campaign.MissingCaseDependency, "search.view_id"):
            campaign.resolve_command("/drive elegir {search.view_id} 1", previous)
        self.assertEqual(self.seen, [])
        previous["search"]["data"]["view_id"] = "actual-view-from-result"
        self.assertEqual(
            campaign.resolve_command("/drive elegir {search.view_id} 1", previous),
            "/drive elegir actual-view-from-result 1",
        )

    async def asyncSetUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lab = "123456789@g.us"
        self.owner = "1234567890@s.whatsapp.net"
        self.seen = []
        self.gate = campaign.LabHTTP(
            self.root, "https://evolution.invalid", self.lab, [self.lab, self.owner], limit=1
        )
        await self.gate.inner.aclose()

        async def handler(request):
            self.seen.append(request)
            return httpx.Response(201, json={"key": {"id": "synthetic-ack"}})

        self.gate.inner = httpx.MockTransport(handler)
        self.http = httpx.AsyncClient(transport=self.gate)
        self.addAsyncCleanup(self.http.aclose)

    async def test_group_server_destinations_and_budget_before_network(self):
        for endpoint, body in (
            ("/group/updateParticipant/test", {}),
            ("/message/sendText/test", {"number": "111111111@s.whatsapp.net", "text": "no"}),
            ("/message/delete/test", {"number": self.lab}),
        ):
            with self.assertRaises(ValueError):
                await self.http.post("https://evolution.invalid" + endpoint, json=body)
        self.assertEqual(self.seen, [])
        await self.http.post(
            "https://evolution.invalid/message/sendText/test",
            json={"number": self.owner, "text": "synthetic"},
        )
        self.assertEqual(json.loads(self.seen[0].content)["number"], self.lab)
        self.assertEqual(json.loads(self.seen[0].content)["text"], "synthetic")
        with self.assertRaisesRegex(ValueError, "budget"):
            await self.http.post(
                "https://evolution.invalid/message/sendText/test",
                json={"number": self.lab, "text": "no"},
            )
        self.assertEqual(len(self.seen), 1)

    async def test_uncertain_post_is_preserved_without_automatic_retry_or_resume(self):
        attempts = []

        async def ambiguous(request):
            attempts.append(request)
            raise httpx.ReadTimeout("synthetic timeout")

        self.gate.inner = httpx.MockTransport(ambiguous)
        with self.assertRaises(httpx.ReadTimeout):
            await self.http.post(
                "https://evolution.invalid/message/sendText/test",
                json={"number": self.lab, "text": "synthetic"},
            )
        rows = json.loads((self.root / "remote-deliveries.json").read_text())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(rows[0]["state"], "uncertain")
        with self.assertRaisesRegex(ValueError, "no_automatic_resume"):
            campaign.LabHTTP(self.root, "https://evolution.invalid", self.lab, [self.lab])

    async def test_oracle_does_not_accept_guard_as_success_or_ignore_wrong_artifact(self):
        from botsky.contracts import Result

        verdict, _ = campaign.evaluate(
            {"kind": "positive"}, Result("failed", "operation_not_enabled"), []
        )
        self.assertEqual(verdict, "BLOCKED")
        verdict, _ = campaign.evaluate({"kind": "blocked"}, Result("ok", "mutated"), [])
        self.assertEqual(verdict, "FAIL")
        verdict, _ = campaign.evaluate(
            {"kind": "positive", "artifact": "pdf"}, Result("ok", "converted"), [{"format": "png"}]
        )
        self.assertEqual(verdict, "FAIL")
        verdict, _ = campaign.evaluate(
            {"kind": "positive", "data": {"total": 1}}, Result("ok", "found", data={"total": 2}), []
        )
        self.assertEqual(verdict, "FAIL")
