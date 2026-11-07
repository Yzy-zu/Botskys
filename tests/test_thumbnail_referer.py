import unittest,httpx
from botsky.engines.search_collage import fetch_thumbnail
class RefererTests(unittest.IsolatedAsyncioTestCase):
 async def test_allowed_cdn_receives_public_source_referer_without_secrets(self):
  seen=[]
  def handler(r):
   seen.append(r);return httpx.Response(200,content=b'fixture')
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as h:
   self.assertEqual(await fetch_thumbnail('https://ei.phncdn.com/synthetic.jpg','pornhub',client=h),b'fixture')
  self.assertEqual(seen[0].headers['Referer'],'https://www.pornhub.com/')
  self.assertNotIn('cookie',seen[0].headers);self.assertNotIn('authorization',seen[0].headers)
