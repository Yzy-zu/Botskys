"""Importación local explícita: mismos bytes, publicación conservada, sin leer runtime."""

import hashlib
import json
import sqlite3
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from test_packs import library_fixture

from botsky.adapters.gallery import PublishedLibrary
from botsky.assets_import import avatar_status, import_assets
from botsky.config import Settings


class AssetImportTest(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.library = library_fixture(self.source, count=3)
        with sqlite3.connect(self.library.root / "library.db") as db:
            db.execute("INSERT INTO albums VALUES('private','Hidden','hidden',0)")
            db.execute("CREATE TABLE private_history(secret TEXT)")
            db.execute("INSERT INTO private_history VALUES('must-not-import')")
        self.destination = self.root / "destination"
        self.destination.mkdir()
        self.settings = Settings(
            self.destination,
            "assets",
            "own",
            1,
            self.destination / "private/test.sqlite3",
            1,
            "owner",
            frozenset(),
            frozenset(),
        )
        self.model = self.source / "original.vrm"
        meta = {
            "title": "Synthetic",
            "author": "Fixture",
            "licenseName": "Redistribution_Prohibited",
            "allowedUserName": "Everyone",
        }
        raw = json.dumps(
            {"asset": {"version": "2.0"}, "extensions": {"VRM": {"meta": meta}}}
        ).encode()
        raw += b" " * ((-len(raw)) % 4)
        self.model.write_bytes(
            b"glTF" + struct.pack("<IIII", 2, len(raw) + 20, len(raw), 0x4E4F534A) + raw
        )
        self.manifest = self.source / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "file": "original.vrm",
                    "name": "Original",
                    "license": "Redistribution_Prohibited",
                    "sha256": hashlib.sha256(self.model.read_bytes()).hexdigest(),
                }
            )
        )

    def run_import(self):
        return import_assets(
            self.settings,
            gallery=self.library.root,
            avatar_manifest=self.manifest,
            avatar_model=self.model,
        )

    def test_exact_model_and_static_gallery_copy_preserve_publication_without_other_tables(self):
        source_hash = hashlib.sha256(self.model.read_bytes()).hexdigest()
        result = self.run_import()
        self.assertEqual(
            result["gallery"],
            {"albums": 2, "published_albums": 1, "photos": 3, "publication_preserved": True},
        )
        destination = self.destination / "private"
        self.assertEqual(
            (destination / "calls/avatar/botsky.vrm").read_bytes(), self.model.read_bytes()
        )
        self.assertEqual((destination / "calls/avatar/botsky.vrm").stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["avatar"]["sha256"], source_hash)
        self.assertTrue(avatar_status(self.settings)["configured"])
        target = PublishedLibrary(self.destination)
        self.assertEqual(len(target.catalog()), 1)
        self.assertEqual(target.catalog()[0].count, 3)
        self.assertEqual(len(target.select("sintetico", 3, set())), 3)
        with sqlite3.connect(destination / "gallery/library.db") as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"albums", "photos", "album_photos"})
            self.assertEqual(
                db.execute("SELECT published FROM albums WHERE id='private'").fetchone()[0], 0
            )
        self.assertEqual(hashlib.sha256(self.model.read_bytes()).hexdigest(), source_hash)
        with self.assertRaisesRegex(ValueError, "destination_not_empty"):
            self.run_import()
        self.assertEqual(
            (destination / "calls/avatar/botsky.vrm").read_bytes(), self.model.read_bytes()
        )

        (destination / "calls/avatar/botsky.vrm").chmod(0o644)
        self.assertFalse(avatar_status(self.settings)["configured"])

    def test_wrong_hash_or_license_does_not_publish_partial_gallery(self):
        for kind in ["hash", "license"]:
            original = json.loads(self.manifest.read_text())
            bad = (
                {**original, "sha256": "0" * 64}
                if kind == "hash"
                else {**original, "license": "invented-license"}
            )
            self.manifest.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                self.run_import()
            self.assertFalse((self.destination / "private/gallery").exists())
            self.assertFalse((self.destination / "private/calls/avatar").exists())
            self.manifest.write_text(json.dumps(original))

    def test_gallery_photo_symlink_and_avatar_symlink_rejected(self):
        photo = self.library.select("sintetico", 1, set())[0]
        target = self.library.root / "originals" / photo.filename
        outside = self.root / "outside.png"
        target.rename(outside)
        target.symlink_to(outside)
        with self.assertRaises(OSError):
            self.run_import()
        self.assertFalse((self.destination / "private/gallery").exists())
        alias = self.source / "alias.vrm"
        alias.symlink_to(self.model)
        with self.assertRaises(OSError):
            import_assets(self.settings, avatar_manifest=self.manifest, avatar_model=alias)

    def test_external_resource_in_model_is_rejected_before_copy(self):
        raw = json.dumps(
            {
                "extensions": {"VRM": {"meta": {"licenseName": "Redistribution_Prohibited"}}},
                "images": [{"uri": "https://example.invalid/private"}],
            }
        ).encode()
        raw += b" " * ((-len(raw)) % 4)
        self.model.write_bytes(
            b"glTF" + struct.pack("<IIII", 2, len(raw) + 20, len(raw), 0x4E4F534A) + raw
        )
        manifest = json.loads(self.manifest.read_text())
        manifest["sha256"] = hashlib.sha256(self.model.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "external_resource"):
            self.run_import()
        self.assertFalse((self.destination / "private/gallery").exists())
