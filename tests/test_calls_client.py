"""Cliente portado: conciliar POST incierto sin repetirlo; cancelación exacta."""

import asyncio
import json
from unittest import IsolatedAsyncioTestCase

import httpx

from botsky.adapters.calls import CallRequest, CallsClient, CallsError
from botsky.contracts import Scope

OWNER = "525511112222@s.whatsapp.net"


class CallsClientTest(IsolatedAsyncioTestCase):
    def fixture(self, handler):
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
        self.addAsyncCleanup(http.aclose)
        return CallsClient(
            http, "http://127.0.0.1:3691", "a" * 64, "b" * 64, frozenset({OWNER}), is_fixture=True
        )

    def request(self):
        return CallRequest(
            "request-123", Scope(OWNER, OWNER), OWNER, "live", topic="Texto /nota no ejecutable"
        )

    async def test_lost_start_response_reconciles_without_repeating_post(self):
        seen = []

        def handler(req):
            seen.append(req)
            if req.method == "POST":
                self.assertEqual(req.headers["idempotency-key"], "request-123")
                self.assertEqual(
                    json.loads(req.content)["origin"], {"chatId": OWNER, "requesterId": OWNER}
                )
                raise httpx.ReadTimeout("synthetic lost response")
            return httpx.Response(
                200, json={"call": {"id": "known-call", "state": "dialing"}, "cancelled": False}
            )

        client = self.fixture(handler)
        self.assertEqual((await client.start(self.request()))["call"]["id"], "known-call")
        self.assertEqual([req.method for req in seen], ["POST", "GET"])

    async def test_absence_after_timeout_is_uncertain_and_not_a_license_to_redial(self):
        seen = []

        def handler(req):
            seen.append(req.method)
            if req.method == "POST":
                raise httpx.ReadError("lost")
            return httpx.Response(200, json={"call": None, "cancelled": False})

        with self.assertRaises(CallsError) as error:
            await self.fixture(handler).start(self.request())
        self.assertEqual(error.exception.code, "delivery_uncertain")
        self.assertEqual(seen, ["POST", "GET"])

    async def test_cancellation_during_dispatch_shields_durable_tombstone(self):
        reached = asyncio.Event()
        seen = []

        async def handler(req):
            seen.append(req.url.path)
            if req.url.path == "/v1/calls":
                reached.set()
                await asyncio.Future()
            return httpx.Response(200, json={"cancelled": True})

        client = self.fixture(handler)
        task = asyncio.create_task(client.start(self.request()))
        await reached.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(seen, ["/v1/calls", "/v1/calls/cancel"])

    async def test_cross_chat_and_unbounded_response_rejected(self):
        seen = []

        def handler(req):
            seen.append(req)
            return httpx.Response(200, content=b" " * 65537)

        client = self.fixture(handler)
        with self.assertRaises(CallsError) as error:
            await client.start(
                CallRequest(
                    "request-cross", Scope(OWNER, "525533334444@s.whatsapp.net"), OWNER, "live"
                )
            )
        self.assertEqual(error.exception.code, "not_allowed")
        self.assertEqual(seen, [])
        with self.assertRaises(CallsError):
            await client.status()
        self.assertEqual(len(seen), 1)

    async def test_errors_never_expose_provider_body_and_redirects_are_not_followed(self):
        client = self.fixture(
            lambda req: httpx.Response(
                429,
                json={
                    "error": {"code": "LIVE_QUOTA_EXCEEDED", "message": "PRIVATE_PROVIDER_MESSAGE"}
                },
            )
        )
        with self.assertRaises(CallsError) as error:
            await client.status()
        self.assertEqual(str(error.exception), "rate_limited")
        redirected = self.fixture(
            lambda req: httpx.Response(302, headers={"Location": "https://forbidden.invalid"})
        )
        with self.assertRaises(CallsError):
            await redirected.status()
