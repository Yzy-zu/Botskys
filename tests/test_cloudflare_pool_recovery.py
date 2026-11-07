import asyncio,json,os,stat,unittest,multiprocessing
from datetime import UTC,datetime,timedelta
from pathlib import Path
import httpx
import test_cloudflare_pool_audit as audit
from botsky.adapters.cloudflare_pool import CloudflarePool,read_private,write_private
from botsky.adapters.cloudflare_interpreter import InterpreterError

# Module-scope target supports an independent process, not just asyncio interleaving.
def child_pause(root,index,barrier):
 class Provider:
  def __init__(self,*args,**kwargs):self.last_metrics=None;self.paused_until=datetime.now(UTC)+timedelta(hours=1)
  async def propose(self,messages,tools):
   barrier.wait(timeout=5)
   raise InterpreterError('daily_quota')
 pool=CloudflarePool(None,Path(root),'private/pool.json',factory=Provider);pool.cursor=index
 try:asyncio.run(pool.propose([],[]))
 except InterpreterError as exc:
  if str(exc)!='daily_quota':raise

class PoolRecoveryTests(unittest.IsolatedAsyncioTestCase):
 setUp=audit.AuditPoolTests.setUp
 registry=audit.AuditPoolTests.registry
 pool=audit.AuditPoolTests.pool
 async def test_active_broken_credentials_isolated_and_repaired(self):
  for damage in ('missing','json','mode','symlink'):
   with self.subTest(damage=damage):
    self.registry(2);p=self.root/'private/cf1.json'
    if damage=='missing':p.unlink()
    elif damage=='json':p.write_text('{')
    elif damage=='mode':p.chmod(0o644)
    else:
     p.unlink();p.symlink_to(self.root/'outside-secret')
    pool=self.pool(None);self.assertEqual([r[0] for r in pool.entries],['cf2']);self.assertIn('cf1',pool.credential_errors)
    write_private(p,{'account_id':format(1,'032x'),'api_token':'repaired'})
    pool.load();self.assertEqual(len(pool.entries),2);self.assertEqual(pool.credential_errors,{})
 async def test_auth_restart_rotation_and_no_same_turn_retry(self):
  self.registry(2)
  def handler(r):
   self.calls.append(r)
   if r.headers['Authorization']=='Bearer synthetic-cf1':return httpx.Response(403,json={'errors':[{'code':10000}]})
   return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"name":"reply","text":"Hola"}'}}]})
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
   pool=self.pool(http)
   with self.assertRaisesRegex(InterpreterError,'provider_http_403'):await pool.propose([],self.tools)
   self.assertEqual(len(self.calls),1)
   pool=self.pool(http);await pool.propose([],self.tools);self.assertIn(format(2,'032x'),self.calls[-1].url.path)
   write_private(self.root/'private/cf1.json',{'account_id':format(1,'032x'),'api_token':'rotated'})
   pool=self.pool(http);await pool.propose([],self.tools);self.assertEqual(self.calls[-1].headers['Authorization'],'Bearer rotated')
   self.assertEqual(stat.S_IMODE(pool.auth_path.stat().st_mode),0o600)
 async def test_all_credentials_bad_fails_without_request(self):
  self.registry(2)
  for n in (1,2):write_private(self.root/f'private/cf{n}.json',{'invalid':True})
  with self.assertRaisesRegex(InterpreterError,'pool_no_healthy_accounts'):self.pool(None)
  self.assertEqual(self.calls,[])
 def test_two_real_processes_merge_quota_state(self):
  self.registry(2);ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(2)
  processes=[ctx.Process(target=child_pause,args=(str(self.root),i,barrier)) for i in (0,1)]
  try:
   for p in processes:p.start()
   for p in processes:p.join(timeout=10)
   self.assertTrue(all(p.exitcode==0 for p in processes))
   self.assertEqual(len(read_private(self.root/'private/quota-state.json')['paused_until']),2)
  finally:
   for p in processes:
    if p.is_alive():p.terminate();p.join()

 async def test_inflight_old_token_failure_does_not_quarantine_rotated_token(self):
  self.registry(2);started=asyncio.Event();release=asyncio.Event()
  async def handler(r):
   if r.headers['Authorization']=='Bearer synthetic-cf1':
    started.set();await release.wait();return httpx.Response(401,json={'errors':[]})
   return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"name":"reply","text":"Hola"}'}}]})
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
   pool=self.pool(http);pending=asyncio.create_task(pool.propose([],self.tools));await asyncio.wait_for(started.wait(),2)
   write_private(self.root/'private/cf1.json',{'account_id':format(1,'032x'),'api_token':'rotated'})
   pool.load();release.set()
   with self.assertRaisesRegex(InterpreterError,'provider_http_401'):await pending
   pool.load();self.assertEqual(len(pool.entries),2);self.assertEqual(pool.credential_errors,{})
 async def test_malformed_shared_state_still_fails_closed(self):
  self.registry(2)
  write_private(self.root/'private/quota-state.json',{'version':1,'paused_until':{'bad':'invalid'}})
  with self.assertRaisesRegex(InterpreterError,'pool_state_invalid'):self.pool(None)

 def test_operator_cannot_overwrite_pool_state_with_account_alias(self):
  import sys
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
  from registrar_cuenta_cloudflare import register
  self.registry(2);source=self.root/'new.json';write_private(source,{'account_id':'c'*32,'api_token':'new'})
  before=(self.root/'private/pool.json').read_bytes()
  for alias in ('quota-state','authentication-state'):
   with self.assertRaisesRegex(ValueError,'registry_filename_collision'):register(self.root,'private/pool.json',alias,source)
  self.assertEqual((self.root/'private/pool.json').read_bytes(),before)
