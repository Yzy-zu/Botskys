"""Guardias del descubrimiento; HTTP local sintético, sin proveedores reales."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
from stress_backend import RoutingHTTP, ToolHTTP, review_case


class StressCampaignTest(IsolatedAsyncioTestCase):
    async def test_fixture_ack_is_labeled_and_never_sent_to_provider(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = "123456789@g.us"
            gate = ToolHTTP(
                directory, "https://evolution.invalid", target, "1234567890@s.whatsapp.net"
            )
            await gate.inner.aclose()
            seen = []

            async def provider(request):
                seen.append(request)
                return httpx.Response(201, json={"key": {"id": "provider-synthetic"}})

            gate.inner = RoutingHTTP(gate, httpx.MockTransport(provider))
            async with httpx.AsyncClient(transport=gate) as http:
                response = await http.post(
                    "https://evolution.invalid/message/sendText/test",
                    json={"number": target, "text": "fixture"},
                )
                self.assertTrue(response.json()["key"]["id"].startswith("fixture-"))
                self.assertEqual(seen, [])
                self.assertEqual(gate.posts[-1]["evidence_level"], "delivery_fixture")
                gate.live = True
                await http.post(
                    "https://evolution.invalid/message/sendText/test",
                    json={"number": target, "text": "live"},
                )
                self.assertEqual(len(seen), 1)
                self.assertEqual(gate.posts[-1]["evidence_level"], "provider")

    async def test_proposal_cannot_dispatch_another_tool(self):
        case = {
            "id": "c01",
            "command": "/mc reiniciar",
            "fixture": None,
            "kind": "positive",
            "statuses": ["ok"],
        }
        with self.assertRaisesRegex(ValueError, "other_tool"):
            review_case(case, "convert_document")
        case["command"] = "/convertir pdf"
        case["fixture"] = "/home/private/source.pdf"
        with self.assertRaisesRegex(ValueError, "fixture_unknown"):
            review_case(case, "convert_document")
