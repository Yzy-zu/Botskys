import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import httpx
from comparar_modelos_cf import MODELS,ModelProvider
from botsky.adapters.cloudflare_interpreter import MODEL
from botsky.frontend.service import FrontendService
from botsky.frontend.contracts import ReplyDecision


class ModelsExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_override_is_isolated_and_one_request(self):
        calls=[]
        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"name":"reply","text":"Hola"}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            provider=ModelProvider(http,{'account_id':'a'*32,'api_token':'synthetic'},MODELS[-1])
            decision=await FrontendService(provider).decide('Hola')
        self.assertIsInstance(decision,ReplyDecision)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['model'],'@cf/qwen/qwen3.8-27b')
        self.assertEqual(calls[0]['reasoning_effort'],'low')
        self.assertEqual(MODEL,'@cf/zai-org/glm-4.7-flash')
        self.assertEqual(provider.last_metrics['model'],calls[0]['model'])

    async def test_actual_quota_code_4006_pauses_without_second_request(self):
        from botsky.adapters.cloudflare_interpreter import InterpreterError
        calls=[]
        def handle(request):
            calls.append(request)
            return httpx.Response(429,json={'errors':[{'code':4006,'message':'you have used up your daily free allocation of 10,000 neurons'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            provider=ModelProvider(http,{'account_id':'a'*32,'api_token':'synthetic'},MODELS[0])
            for _ in range(2):
                with self.assertRaisesRegex(InterpreterError,'daily_quota'):
                    await provider.propose([],[])
        self.assertEqual(len(calls),1)
