import sys,json,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
from catalogo_qwen_sin_perdidas import LosslessCatalog,expand
from botsky.frontend.catalog import Catalog

class LosslessTests(unittest.TestCase):
    def test_roundtrip_every_value_including_metadata_and_field_descriptions(self):
        for adult,enabled in [(True,True),(False,True),(False,False)]:
            with self.subTest(adult=adult,enabled=enabled):
                original,encoded=Catalog(),LosslessCatalog()
                for catalog in (original,encoded):
                    catalog.configure_downloads(SimpleNamespace(enabled=enabled,adult_sources_enabled=adult))
                    catalog.availability={'minecraft':{'enabled':False,'reason':'fixture'}}
                # JSON normalize tuples exactly as provider sees them.
                full=json.loads(json.dumps(original.describe()))
                wire=json.loads(json.dumps(encoded.describe()))
                self.assertEqual(full,expand(wire))
                self.assertEqual(len(wire['actions']),155)
                self.assertLess(len(json.dumps(wire)),len(json.dumps(full)))
