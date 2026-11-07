import json
import unittest

import httpx

from botsky.adapters.cloudflare_interpreter import CloudflareInterpreter, InterpreterError
from botsky.frontend.service import FrontendService
from botsky.frontend.contracts import ActionRequest, ReplyDecision, ClarifyDecision
from botsky.integrations import validate_interpreter


def response(name='reply', args=None, finish='tool_calls', count=1):
    return {'choices': [{'finish_reason': finish, 'message': {'tool_calls': [
        {'function': {'name': name, 'arguments': json.dumps(args or {'text': 'Hola'})}}
    ] * count}}]}


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, payload, status=200):
        calls = []
        def handle(request):
            calls.append(json.loads(request.content))
            wire = payload
            if status == 200 and payload.get('choices'):
                import copy
                wire = copy.deepcopy(payload)
                for choice in wire['choices']:
                    original = choice['message'].get('tool_calls', [])
                    if len(original) == 1:
                        function = original[0]['function']
                        arguments = json.loads(function['arguments'])
                        choice['message'] = {'content': json.dumps({'name': function['name'], **arguments})}
                        if choice['finish_reason'] == 'tool_calls':
                            choice['finish_reason'] = 'stop'
            return httpx.Response(status, json=wire)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            adapter = CloudflareInterpreter(http, {'account_id': 'a'*32, 'api_token': 'synthetic'})
            service = FrontendService(adapter)
            try:
                return await service.decide('petición sintética'), calls
            finally:
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]['response_format'], {'type': 'json_object'})
                self.assertNotIn('tools', calls[0])
                self.assertEqual(calls[0]['temperature'], 0)
                self.assertEqual(calls[0]['max_completion_tokens'], 2048)
                self.assertIn('nota.guardar', calls[0]['messages'][0]['content'])

    async def test_decisions(self):
        for name, args, kind in [('reply', {'text': 'Hola'}, ReplyDecision),
            ('clarify', {'question': '¿A qué formato?'}, ClarifyDecision),
            ('select_action', {'action_key': 'nota.guardar', 'arguments': {'text': '*pan*'}}, ActionRequest)]:
            with self.subTest(name=name):
                decision, _ = await self.run_case(response(name, args))
                self.assertIsInstance(decision, kind)

    async def test_invalid_responses(self):
        for payload in [response(finish='length'), response(count=2), response(count=0),
                        response('unknown'), response('select_action', {'action_key': 'nota.guardar', 'arguments': {'actor': 'owner'}})]:
            with self.assertRaises(InterpreterError):
                await self.run_case(payload)

    async def test_quota_and_capacity(self):
        for code, reason in [(3036, 'daily_quota'), (3040, 'capacity')]:
            with self.assertRaisesRegex(InterpreterError, reason):
                await self.run_case({'errors': [{'code': code}]}, 429)

    def test_configuration(self):
        self.assertEqual(validate_interpreter({}), {})
        for block in [{'enabled': 1}, {'model': 'other'}, {'max_concurrency': True},
                      {'credentials_file': '../secret'}, {'pool': []}]:
            with self.assertRaises(ValueError):
                validate_interpreter(block)

    async def test_timeout_no_retry(self):
        calls = []
        async def handle(request):
            calls.append(request)
            raise httpx.ReadTimeout('synthetic')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            service = FrontendService(CloudflareInterpreter(http, {'account_id': 'a'*32, 'api_token': 'synthetic'}))
            with self.assertRaisesRegex(InterpreterError, 'transport_error'):
                await service.decide('hola')
        self.assertEqual(len(calls), 1)

    async def test_daily_quota_pauses_next_request(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(429, json={'errors': [{'code': 3036}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            adapter = CloudflareInterpreter(http, {'account_id': 'a'*32, 'api_token': 'synthetic'})
            for _ in range(2):
                with self.assertRaisesRegex(InterpreterError, 'daily_quota'):
                    await adapter.propose([], [])
        self.assertEqual(len(calls), 1)

    def test_disabled_does_not_read_credentials(self):
        from botsky.integrations import compose_frontend
        self.assertIsNone(compose_frontend(None, {}, None))

    async def test_json_envelope_is_closed(self):
        for content in ('no-json', '[]', '{"name":"reply","arguments":{"text":"Hola"},"actor":"owner"}'):
            def handle(request):
                return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':content}}]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                service=FrontendService(CloudflareInterpreter(http,{'account_id':'a'*32,'api_token':'synthetic'}))
                with self.assertRaisesRegex(InterpreterError,'invalid_json_envelope'):
                    await service.decide('hola')

    async def test_captured_direct_action_envelope_is_closed(self):
        from botsky.frontend.contracts import ActionRequest
        for name,expected in [('ia',True),('arbitrary_executor',False)]:
            def handle(request):
                return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'name':name,'arguments':{'text':'Explícame por qué la luna tiene fases'}})}}]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
                service=FrontendService(CloudflareInterpreter(http,{'account_id':'a'*32,'api_token':'synthetic'}))
                if expected:
                    decision=await service.decide('Explícame por qué la luna tiene fases')
                    self.assertIsInstance(decision,ActionRequest)
                    self.assertEqual(decision.action_key,'ia')
                else:
                    with self.assertRaises(InterpreterError):
                        await service.decide('Explícame por qué la luna tiene fases')
