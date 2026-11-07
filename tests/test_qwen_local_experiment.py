import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import httpx
from probar_qwen_local import LocalProvider,guarded
from botsky.frontend.service import FrontendService


class LocalExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_loopback_and_full_catalog(self):
        requests=[]
        def handle(request):
            requests.append(request)
            return httpx.Response(200,json={'model':'qwen3.5:2b','done':True,'done_reason':'stop','message':{'content':'{"name":"reply","text":"Hola"}'},'prompt_eval_count':22000,'eval_count':10,'total_duration':1000})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            provider=LocalProvider(http,'qwen3.5:2b')
            service=FrontendService(provider)
            decision=await service.decide('Hola')
        self.assertEqual(decision.text,'Hola')
        self.assertEqual(len(requests),1)
        self.assertEqual(str(requests[0].url),'http://127.0.0.1:11435/api/chat')
        self.assertNotIn('authorization',requests[0].headers)
        payload=json.loads(requests[0].content)
        self.assertEqual(payload['options']['num_ctx'],32768)
        self.assertEqual(payload['options']['num_thread'],1)
        self.assertFalse(payload['think'])
        self.assertIn('nota.guardar',payload['messages'][0]['content'])
        self.assertIn('admin.nuclear-confirmar',payload['messages'][0]['content'])
        self.assertEqual(provider.last_metrics['model'],'qwen3.5:2b')

    async def test_memory_guard_cancels_inference(self):
        import asyncio
        async def wait():await asyncio.sleep(100)
        with patch('probar_qwen_local.memory_available_mb',return_value=1000):
            with self.assertRaisesRegex(RuntimeError,'resource_guard'):
                await guarded(wait())
