import unittest
from botsky.frontend.catalog import Catalog
from botsky.frontend.compact_catalog import LosslessCatalog,expand
from botsky.frontend.contracts import ActionRequest

class VideoDefaultsTests(unittest.TestCase):
 def test_search_without_container_defaults_to_video_only_in_frontend(self):
  c=Catalog();p=c.build(ActionRequest('dl.buscar',{'query':'volcanes','source':'youtube'}))
  self.assertEqual(p.arguments['container'],'mp4')
  self.assertEqual(c.build(ActionRequest('dl.buscar',{'query':'volcanes','source':'youtube','container':'mp3'})).arguments['container'],'mp3')
 def test_compact_advertises_default_and_keeps_source_required(self):
  c=LosslessCatalog();row=next(r for r in expand(c.describe()) if r['action_key']=='dl.buscar')
  self.assertNotIn('container',row['parameters']['required']);self.assertIn('source',row['parameters']['required'])
  self.assertEqual(row['parameters']['properties']['container']['default'],'mp4')
  with self.assertRaises(ValueError):c.build(ActionRequest('dl.buscar',{'query':'x'}))

class SourceDiagnosticsTests(unittest.TestCase):
 def test_extractor_diagnostics_are_content_free(self):
  from botsky.engines.downloads import adult_failure_code
  for raw,expected in [(b'HTTP Error 403 at https://private.example/x','source_access_denied'),(b'HTTP Error 404','source_content_unavailable'),(b'Requested format is not available','source_format_unavailable'),(b'connection reset','source_network_failed'),(b'unknown output','source_failed')]:self.assertEqual(adult_failure_code(raw),expected)
