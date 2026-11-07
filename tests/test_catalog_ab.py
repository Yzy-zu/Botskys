import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
from comparar_catalogos import CompactCatalog
from botsky.frontend.catalog import Catalog
from botsky.frontend.contracts import ActionRequest
from botsky.commands.router import Router


class CatalogABTests(unittest.TestCase):
    def test_projection_preserves_all_native_contracts(self):
        actual,compact=Catalog(),CompactCatalog()
        full={r['action_key']:r for r in actual.describe()}
        small={r['action_key']:r for r in compact.describe()['actions']}
        self.assertEqual(set(full),set(small))
        self.assertEqual(len(small),155)
        for key,row in full.items():
            with self.subTest(action=key):
                self.assertEqual(row['parameters']['required'],small[key]['parameters']['required'])
                properties=row['parameters']['properties']
                reduced=small[key]['parameters']['properties']
                self.assertEqual(set(properties),set(reduced))
                for name,schema in properties.items():
                    self.assertEqual({k:v for k,v in schema.items() if k!='description'},reduced[name])
                self.assertEqual(row['constants'],small[key].get('constants',{}))
                parsed=Router().parse(actual.specs[key].sample)
                args={k:list(v) if isinstance(v,tuple) else v for k,v in parsed.arguments.items() if k not in row['constants']}
                request=ActionRequest(key,args)
                self.assertEqual(actual.build(request).canonical(),compact.build(request).canonical())
