import hashlib
import json
import stat
import unittest
from datetime import UTC,datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from botsky.adapters.cloudflare_pool import CloudflarePool,write_private
from botsky.adapters.cloudflare_interpreter import InterpreterError
from botsky.integrations import validate_interpreter


class PoolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'private').mkdir(mode=0o700)
        self.entries=[]
        self.add_account('first','a'*32)
        self.add_account('second','b'*32)
        self.registry=self.root/'private/pool.json'
        self.save()
        from botsky.frontend.prompts import tools
        from botsky.frontend.catalog import Catalog
        self.tools=tools(Catalog())
        self.calls=[]
        self.blocked=set()

    def add_account(self,alias,account):
        path='private/'+alias+'.json'
        write_private(self.root/path,{'account_id':account,'api_token':'synthetic-'+alias})
        self.entries.append({'id':alias,'credentials_file':path})

    def save(self):write_private(self.registry,{'version':1,'entries':self.entries})

    def handler(self,request):
        self.calls.append(request)
        if any(account in request.url.path for account in self.blocked):
            return httpx.Response(429,json={'errors':[{'code':4006,'message':'you have used up your daily free allocation of 10,000 neurons'}]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"name":"reply","text":"Hola"}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}})

    def pool(self,http):
        return CloudflarePool(http,self.root,'private/pool.json',model='@cf/meta/llama-4-scout-17b-16e-instruct')

    async def test_daily_quota_no_same_message_retry_and_restart(self):
        self.blocked.add('a'*32)
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.handler)) as http:
            pool=self.pool(http)
            with self.assertRaisesRegex(InterpreterError,'daily_quota'):await pool.propose([],self.tools)
            self.assertEqual(len(self.calls),1)
            await pool.propose([],self.tools)
            self.assertIn('b'*32,self.calls[-1].url.path)
            self.assertEqual(pool.last_metrics['credential_alias'],'second')
            self.assertEqual(stat.S_IMODE(pool.state_path.stat().st_mode),0o600)
            restarted=self.pool(http)
            await restarted.propose([],self.tools)
            self.assertIn('b'*32,self.calls[-1].url.path)
            self.assertEqual(len(self.calls),3)
            self.blocked.add('b'*32)
            with self.assertRaises(InterpreterError):await restarted.propose([],self.tools)
            count=len(self.calls)
            with self.assertRaisesRegex(InterpreterError,'daily_quota_pool'):await self.pool(http).propose([],self.tools)
            self.assertEqual(len(self.calls),count)

    async def test_round_robin_and_operator_addition(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.handler)) as http:
            pool=self.pool(http)
            await pool.propose([],self.tools);await pool.propose([],self.tools)
            self.assertIn('a'*32,self.calls[0].url.path);self.assertIn('b'*32,self.calls[1].url.path)
            self.add_account('third','c'*32);self.save()
            await pool.propose([],self.tools)
            self.assertIn('c'*32,self.calls[2].url.path)
            self.assertTrue(all(json.loads(r.content)['model']=='@cf/meta/llama-4-scout-17b-16e-instruct' for r in self.calls))

    async def test_duplicate_account_does_not_add_quota(self):
        self.add_account('duplicate','a'*32);self.save()
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.handler)) as http:
            with self.assertRaisesRegex(InterpreterError,'pool_duplicate_account'):self.pool(http)
        self.assertEqual(self.calls,[])

    async def test_expired_pause_is_available(self):
        key=hashlib.sha256(('a'*32).encode()).hexdigest()
        write_private(self.root/'private/quota-state.json',{'version':1,'paused_until':{key:(datetime.now(UTC)-timedelta(seconds=1)).isoformat()}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.handler)) as http:
            await self.pool(http).propose([],self.tools)
        self.assertIn('a'*32,self.calls[0].url.path)

    def test_configuration_single_or_pool_and_closed_models(self):
        validate_interpreter({'enabled':True,'pool_file':'private/pool.json','model':'@cf/meta/llama-4-scout-17b-16e-instruct'})
        for block in [{'pool_file':'private/pool.json','credentials_file':'private/a.json'}, {'pool_file':'../escape'}, {'model':'arbitrary'}, {'model':'@cf/meta/llama-4-scout-17b-16e-instruct','reasoning_effort':'low'}]:
            with self.assertRaises(ValueError):validate_interpreter(block)

    def test_operator_registration_and_duplicate_rejection(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
        from registrar_cuenta_cloudflare import register
        source=self.root/'operator-new.json'
        write_private(source,{'account_id':'c'*32,'api_token':'synthetic-third'})
        result=register(self.root,'private/pool.json','third',source)
        self.assertEqual(result['entries'],3)
        self.assertEqual(stat.S_IMODE((self.root/'private/third.json').stat().st_mode),0o600)
        before=self.registry.read_bytes()
        with self.assertRaisesRegex(ValueError,'duplicate_account'):
            register(self.root,'private/pool.json','fourth',source)
        self.assertEqual(self.registry.read_bytes(),before)
        self.assertFalse((self.root/'private/fourth.json').exists())

    async def test_composed_pool_uses_selected_model_and_profile(self):
        from types import SimpleNamespace
        from botsky.integrations import compose_frontend
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.handler)) as http:
            service=compose_frontend(SimpleNamespace(root=self.root),{'enabled':True,'pool_file':'private/pool.json','model':'@cf/qwen/qwen3.8-27b','reasoning_effort':'low'},http)
            decision=await service.decide('Hola')
        self.assertEqual(decision.text,'Hola')
        body=json.loads(self.calls[0].content)
        self.assertEqual(body['model'],'@cf/qwen/qwen3.8-27b')
        self.assertEqual(body['reasoning_effort'],'low')


class PoolWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import test_frontend_worker as fixtures
        fixtures.WorkerTests.setUp(self)
    async def test_all_quota_blocked_does_not_execute_effects(self):
        from unittest.mock import AsyncMock
        from botsky.frontend.worker import run_one
        self.frontend.decide=AsyncMock(side_effect=InterpreterError('daily_quota_pool'))
        receipt=self.app.receive(self.adapter.incoming('quota','alice','private','guarda una nota'))
        await run_one(self.app)
        with self.app.store.transaction() as db:
            from botsky.contracts import Result
            result=Result.from_json(db.execute('SELECT result_json FROM inbox WHERE id=?',(receipt.id,)).fetchone()[0])
            self.assertEqual(result.code,'frontend_quota_exhausted')
            self.assertEqual(db.execute('SELECT count(*) FROM effects').fetchone()[0],0)
        self.frontend.decide.assert_awaited_once()
