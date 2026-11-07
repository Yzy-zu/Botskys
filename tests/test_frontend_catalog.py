import unittest

from botsky.commands.registry import Registry
from botsky.commands.router import Router
from botsky.frontend.catalog import Catalog
from botsky.frontend.contracts import ActionRequest


class CatalogTests(unittest.TestCase):
    def test_all_declared_examples(self):
        catalog = Catalog()
        self.assertEqual(len(catalog.describe()), 155)
        for spec in Registry().specs:
            with self.subTest(path=spec.path):
                parsed = Router().parse(spec.sample)
                arguments = {k: list(v) if isinstance(v, tuple) else v
                             for k, v in parsed.arguments.items()
                             if k not in dict(spec.constants)}
                native = catalog.build(ActionRequest('.'.join(spec.path), arguments))
                self.assertEqual(native.canonical(), parsed.canonical())

    def test_reject_authority_and_wrong_types(self):
        catalog = Catalog()
        spec = next(s for s in Registry().specs if s.path == ('nota', 'guardar'))
        key = '.'.join(spec.path)
        with self.assertRaises(ValueError):
            catalog.build(ActionRequest(key, {'actor': 'owner'}))
        with self.assertRaises(ValueError):
            catalog.build(ActionRequest(key, {'text': True}))

    def test_native_selection_and_constants(self):
        catalog = Catalog()
        for key, spec in catalog.specs.items():
            if spec.operation in ('download_media.choose', 'download_media.inspect', 'manage_drive.choose'):
                parsed = catalog.build(ActionRequest(key, {'choice': 2}))
                self.assertEqual(parsed.arguments['choice'], 2)
                self.assertNotIn('view_id', parsed.arguments)
                with self.assertRaises(ValueError):
                    catalog.build(ActionRequest(key, {'choice': True}))
            if spec.constants:
                with self.assertRaises(ValueError):
                    catalog.build(ActionRequest(key, dict(spec.constants)))

    def test_native_scalars_arrays_and_ranges(self):
        from botsky.commands.types import Field
        from botsky.frontend.catalog import scalar
        self.assertTrue(scalar(Field('enabled', 'bool'), True))
        self.assertEqual(scalar(Field('duration', 'duration', minimum=5), 60), 60)
        self.assertEqual(scalar(Field('terms', 'terms'), ['uno', 'dos']), ('uno', 'dos'))
        for f, value in [(Field('n', 'int'), True), (Field('n', 'int'), '2'),
                         (Field('n', 'int', maximum=2), 3),
                         (Field('n', 'float'), float('nan')),
                         (Field('terms', 'terms'), ['uno', 'uno'])]:
            with self.assertRaises(ValueError):
                scalar(f, value)
