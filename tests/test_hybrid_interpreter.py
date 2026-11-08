"""Pruebas unitarias para GeminiInterpreter y HybridInterpreter con conmutación por error."""

import asyncio
import json
import time
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx

from botsky.adapters.cloudflare_interpreter import InterpreterError
from botsky.adapters.gemini_interpreter import GeminiInterpreter
from botsky.adapters.hybrid_interpreter import HybridInterpreter
from botsky.frontend.compact_catalog import LosslessCatalog
from botsky.frontend.contracts import ActionRequest, ReplyDecision
from botsky.frontend.prompts import tools
from botsky.frontend.service import FrontendService
from botsky.integrations import compose_frontend, validate_interpreter


class MockTransport:
    def __init__(self, handler):
        self.handler = handler

    async def handle_async_request(self, request):
        return await self.handler(request)


class GeminiInterpreterTest(IsolatedAsyncioTestCase):
    async def test_successful_reply_proposal(self):
        async def handle(request):
            data = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {"name": "reply", "text": "¡Hola! ¿En qué puedo ayudarte?"}
                                    )
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 8},
            }
            return httpx.Response(200, json=data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            interp = GeminiInterpreter(http, "synthetic-key")
            catalog = LosslessCatalog()
            service = FrontendService(interp, catalog)
            decision = await service.decide("hola")
            self.assertIsInstance(decision, ReplyDecision)
            self.assertEqual(decision.text, "¡Hola! ¿En qué puedo ayudarte?")
            self.assertIsNotNone(interp.last_metrics)
            self.assertEqual(interp.last_metrics["model"], "gemini-3.5-flash-lite")

    async def test_successful_action_selection(self):
        async def handle(request):
            data = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "name": "select_action",
                                            "action_key": "nota.guardar",
                                            "arguments": {"text": "comprar leche"},
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
            return httpx.Response(200, json=data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            interp = GeminiInterpreter(http, "synthetic-key")
            service = FrontendService(interp)
            decision = await service.decide("guarda nota comprar leche")
            self.assertIsInstance(decision, ActionRequest)
            self.assertEqual(decision.action_key, "nota.guardar")
            self.assertEqual(decision.arguments, {"text": "comprar leche"})

    async def test_error_status_mapping(self):
        for status, expected_err in (
            (429, "rate_limited"),
            (503, "service_unavailable"),
            (401, "auth_error"),
            (403, "auth_error"),
            (500, "provider_http_500"),
        ):
            async def handle(request, st=status):
                return httpx.Response(st, json={"error": {"code": st}})

            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                interp = GeminiInterpreter(http, "synthetic-key")
                catalog = LosslessCatalog()
                with self.assertRaisesRegex(InterpreterError, expected_err):
                    await interp.propose([{"role": "user", "content": "test"}], tools(catalog))

    async def test_transport_error_mapping(self):
        async def handle(request):
            raise httpx.ReadTimeout("timeout sintético")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            interp = GeminiInterpreter(http, "synthetic-key")
            catalog = LosslessCatalog()
            with self.assertRaisesRegex(InterpreterError, "transport_error"):
                await interp.propose([{"role": "user", "content": "test"}], tools(catalog))


class HybridInterpreterTest(IsolatedAsyncioTestCase):
    async def test_primary_success_never_calls_fallback(self):
        fallback_called = False

        class MockPrimary:
            async def propose(self, messages, tools):
                envelope = {"name": "reply", "arguments": {"text": "Respuesta primaria Gemini"}}
                return {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [{"function": envelope}]}}]}

        class MockFallback:
            async def propose(self, messages, tools):
                nonlocal fallback_called
                fallback_called = True
                envelope = {"name": "reply", "arguments": {"text": "Respuesta fallback Cloudflare"}}
                return {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [{"function": envelope}]}}]}

        hybrid = HybridInterpreter(MockPrimary(), MockFallback(), cooldown_seconds=60)
        service = FrontendService(hybrid)
        decision = await service.decide("hola")
        self.assertEqual(decision.text, "Respuesta primaria Gemini")
        self.assertFalse(fallback_called)
        self.assertEqual(hybrid.active_provider, "primary")

    async def test_primary_failover_on_429_immediately_uses_fallback_and_cools_down(self):
        primary_calls = 0
        fallback_calls = 0

        class MockPrimary:
            async def propose(self, messages, tools):
                nonlocal primary_calls
                primary_calls += 1
                raise InterpreterError("rate_limited")

        class MockFallback:
            async def propose(self, messages, tools):
                nonlocal fallback_calls
                fallback_calls += 1
                envelope = {"name": "reply", "arguments": {"text": "Respuesta fallback Cloudflare"}}
                return {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [{"function": envelope}]}}]}

        hybrid = HybridInterpreter(MockPrimary(), MockFallback(), cooldown_seconds=60)
        service = FrontendService(hybrid)

        # Primer llamado: Primary falla con rate_limited -> salta a fallback inmediatamente
        decision1 = await service.decide("hola")
        self.assertEqual(decision1.text, "Respuesta fallback Cloudflare")
        self.assertEqual(primary_calls, 1)
        self.assertEqual(fallback_calls, 1)
        self.assertEqual(hybrid.active_provider, "fallback")
        self.assertGreater(hybrid.cooldown_until, time.monotonic())

        # Segundo llamado: En período de enfriamiento -> va directo a fallback sin llamar a primary
        decision2 = await service.decide("segundo mensaje")
        self.assertEqual(decision2.text, "Respuesta fallback Cloudflare")
        self.assertEqual(primary_calls, 1)
        self.assertEqual(fallback_calls, 2)
        self.assertEqual(hybrid.active_provider, "fallback")

    async def test_primary_failover_on_503_and_cooldown_expiration(self):
        primary_calls = 0
        primary_healthy = False

        class MockPrimary:
            async def propose(self, messages, tools):
                nonlocal primary_calls
                primary_calls += 1
                if not primary_healthy:
                    raise InterpreterError("service_unavailable")
                envelope = {"name": "reply", "arguments": {"text": "Gemini recuperado"}}
                return {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [{"function": envelope}]}}]}

        class MockFallback:
            async def propose(self, messages, tools):
                envelope = {"name": "reply", "arguments": {"text": "Cloudflare colchón"}}
                return {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [{"function": envelope}]}}]}

        hybrid = HybridInterpreter(MockPrimary(), MockFallback(), cooldown_seconds=5)
        service = FrontendService(hybrid)

        # 1. Fallo inicial 503
        d1 = await service.decide("hola")
        self.assertEqual(d1.text, "Cloudflare colchón")
        self.assertEqual(primary_calls, 1)

        # 2. Simular expiración de enfriamiento y recuperación de Gemini
        hybrid.cooldown_until = time.monotonic() - 1
        primary_healthy = True

        d2 = await service.decide("segundo intento")
        self.assertEqual(d2.text, "Gemini recuperado")
        self.assertEqual(primary_calls, 2)
        self.assertEqual(hybrid.active_provider, "primary")

    async def test_primary_failover_on_500_server_error_and_invalid_envelope(self):
        class MockPrimary500:
            async def propose(self, messages, tools):
                raise InterpreterError("provider_http_500")

        class MockFallback:
            async def propose(self, messages, tools):
                envelope = {"name": "reply", "arguments": {"text": "Respaldo tras error 500"}}
                return {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [{"function": envelope}]}}]}

        hybrid = HybridInterpreter(MockPrimary500(), MockFallback(), cooldown_seconds=60)
        service = FrontendService(hybrid)
        decision = await service.decide("test")
        self.assertEqual(decision.text, "Respaldo tras error 500")
        self.assertEqual(hybrid.active_provider, "fallback")
        self.assertGreater(hybrid.cooldown_until, time.monotonic())


class HybridConfigurationTest(TestCase):
    def test_validate_interpreter_hybrid(self):
        block = {
            "enabled": True,
            "provider": "hybrid",
            "gemini_key": "AQ.Ab8RN6fake",
            "gemini_model": "gemini-3.5-flash-lite",
            "cooldown_seconds": 60,
            "pool_file": "private/pool.json",
            "model": "@cf/qwen/qwen3.8-27b",
        }
        validated = validate_interpreter(block)
        self.assertEqual(validated["provider"], "hybrid")

        # Falla si falta gemini_key
        with self.assertRaises(ValueError):
            validate_interpreter({**block, "gemini_key": ""})

        # Falla si modelo de Gemini no es soportado
        with self.assertRaises(ValueError):
            validate_interpreter({**block, "gemini_model": "invalid-model"})

        # Falla si cooldown_seconds es inválido
        with self.assertRaises(ValueError):
            validate_interpreter({**block, "cooldown_seconds": 1})
