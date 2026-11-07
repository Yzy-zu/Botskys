"""Auditoría reproducible; incluye límites observados, no todos son garantías deseadas."""
import asyncio,json,unittest,hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import httpx
from botsky.adapters.cloudflare_pool import CloudflarePool,write_private,read_private
from botsky.adapters.cloudflare_interpreter import InterpreterError

class AuditPoolTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  from botsky.frontend.prompts import tools
  from botsky.frontend.catalog import Catalog
  self.tools=tools(Catalog())
  tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);(self.root/'private').mkdir(mode=0o700);self.calls=[]
 def registry(self,n):
  entries=[]
  for i in range(n):
   alias='cf'+str(i+1);name='private/'+alias+'.json';write_private(self.root/name,{'account_id':format(i+1,'032x'),'api_token':'synthetic-'+alias});entries.append({'id':alias,'credentials_file':name})
  write_private(self.root/'private/pool.json',{'version':1,'entries':entries})
 def pool(self,http):return CloudflarePool(http,self.root,'private/pool.json')
 def ok(self,r):
  self.calls.append(r.url.path)
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"name":"reply","text":"Hola"}'}}]})
 async def test_seven_accounts_seventy_turns_balanced(self):
  self.registry(7)
  from botsky.frontend.prompts import tools
  from botsky.frontend.catalog import Catalog
  async with httpx.AsyncClient(transport=httpx.MockTransport(self.ok)) as http:
   pool=self.pool(http)
   for _ in range(70):await pool.propose([],tools(Catalog()))
  self.assertEqual(len(self.calls),70)
  self.assertTrue(all(self.calls.count(path)==10 for path in set(self.calls)))
  self.assertEqual(len(set(self.calls)),7)
 async def test_revoked_token_is_quarantined_between_turns(self):
  self.registry(2)
  def handler(r):
   if format(1,'032x') in r.url.path:
    self.calls.append(r.url.path);return httpx.Response(401,json={'errors':[{'code':10000,'message':'Authentication error'}]})
   return self.ok(r)
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
   pool=self.pool(http)
   with self.assertRaisesRegex(InterpreterError,'provider_http_401'):await pool.propose([],self.tools)
   for _ in range(3):await pool.propose([],self.tools)
   self.assertEqual(pool.pauses,{})
   self.assertEqual(sum(format(1,'032x') in path for path in self.calls),1)
   self.assertEqual(len(read_private(pool.auth_path)['blocked_credentials']),1)
  self.assertEqual(len(self.calls),4)
 async def test_disabled_broken_credential_is_not_read(self):
  self.registry(2);p=self.root/'private/pool.json';data=read_private(p);data['entries'][0]['enabled']=False;write_private(p,data);write_private(self.root/'private/cf1.json',{'broken':True})
  pool=self.pool(None)
  self.assertEqual([entry[0] for entry in pool.entries],['cf2'])
  self.assertEqual(pool.credential_errors,{})
 async def parallel_quota(self,instances):
  self.registry(2);started=[asyncio.Event(),asyncio.Event()];release=[asyncio.Event(),asyncio.Event()]
  async def handler(r):
   index=0 if format(1,'032x') in r.url.path else 1;started[index].set();await release[index].wait()
   return httpx.Response(429,json={'errors':[{'code':3036}]})
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
   first=self.pool(http);second=self.pool(http) if instances==2 else first
   if instances==2:second.cursor=1
   a=asyncio.create_task(first.propose([],[]));b=asyncio.create_task(second.propose([],[]))
   await asyncio.wait_for(asyncio.gather(*(e.wait() for e in started)),2)
   release[0].set();await asyncio.gather(a,return_exceptions=True)
   release[1].set();await asyncio.gather(b,return_exceptions=True)
  return read_private(self.root/'private/quota-state.json')['paused_until']
 async def test_concurrent_quota_single_instance_preserves_both_pauses(self):self.assertEqual(len(await self.parallel_quota(1)),2)
 async def test_multiple_instances_preserve_both_pauses(self):self.assertEqual(len(await self.parallel_quota(2)),2)
