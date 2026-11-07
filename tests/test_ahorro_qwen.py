import sys,json,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
from medir_ahorro_qwen import ExperimentHTTP,MARK,PROTO

class SavingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_prefix_stable_without_losing_dynamic_context(self):
        class HTTP:
            def __init__(self):self.calls=[]
            async def post(self,url,**kw):
                self.calls.append(kw)
                return SimpleNamespace(status_code=200,json=lambda:{'usage':{'neurons':1},'choices':[]})
        h=HTTP();transport=ExperimentHTTP(h,'prefijo_afinidad')
        for n in [1,2]:
            await transport.post('synthetic',headers={},json={'messages':[{'role':'system','content':'CATALOGO'+MARK+json.dumps({'now':n})+PROTO+'schema'},{'role':'assistant','content':'¿Formato?'},{'role':'user','content':'PDF'}]},timeout=1)
        self.assertEqual(h.calls[0]['json']['messages'][0]['content'].split(MARK)[0],h.calls[1]['json']['messages'][0]['content'].split(MARK)[0])
        self.assertNotEqual(h.calls[0]['json']['messages'][0],h.calls[1]['json']['messages'][0])
        self.assertEqual(sum(m['role']=='system' for m in h.calls[0]['json']['messages']),1)
        for call in h.calls:
            self.assertEqual(call['json']['messages'][-1],{'role':'user','content':'PDF'})
            self.assertIn('x-session-affinity',call['headers'])
            self.assertIn(PROTO,call['json']['messages'][0]['content'])
        self.assertEqual(len(h.calls),2)
