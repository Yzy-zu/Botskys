"""Importación explícita de galería/VRM; nunca se invoca desde el runtime."""

import hashlib
import json
import os
import shutil
import sqlite3
import struct
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from .adapters.gallery import MAX_PHOTO_BYTES, _valid_static_image
from .local_files import private_directory

MAX_VRM = 50 * 1024 * 1024
GALLERY_APPLICATION_ID = 1112755527


def read_regular(path, maximum):
    import stat

    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ValueError("asset_size_or_type")
        data = stream.read(maximum + 1)
    if len(data) != info.st_size:
        raise ValueError("asset_changed")
    return data


def write_private(path, data):
    with os.fdopen(
        os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600), "wb"
    ) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def vrm_metadata(raw):
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("avatar_invalid_glb")
    version, length, count, kind = struct.unpack_from("<IIII", raw, 4)
    if (
        version != 2
        or length != len(raw)
        or kind != 0x4E4F534A
        or count > 4 * 1024 * 1024
        or 20 + count > length
    ):
        raise ValueError("avatar_invalid_glb")
    doc = json.loads(raw[20 : 20 + count])
    if any(
        item.get("uri") and not item["uri"].startswith("data:")
        for item in doc.get("buffers", []) + doc.get("images", [])
    ):
        raise ValueError("avatar_external_resource")
    ext = doc.get("extensions", {})
    meta = ext.get("VRMC_vrm", {}).get("meta") or ext.get("VRM", {}).get("meta")
    if not isinstance(meta, dict) or not (meta.get("licenseName") or meta.get("licenseUrl")):
        raise ValueError("avatar_license_missing")
    return meta


def stage_avatar(destination, manifest, model):
    source = json.loads(read_regular(manifest, 65536))
    raw = read_regular(model, MAX_VRM)
    digest = hashlib.sha256(raw).hexdigest()
    if source.get("sha256") != digest:
        raise ValueError("avatar_source_hash_mismatch")
    meta = vrm_metadata(raw)
    license_name = meta.get("licenseName") or meta["licenseUrl"]
    if source.get("license") != license_name:
        raise ValueError("avatar_source_license_mismatch")
    destination.mkdir(mode=0o700)
    write_private(destination / "botsky.vrm", raw)
    write_private(
        destination / "manifest.json",
        (
            json.dumps(
                {
                    "file": "botsky.vrm",
                    "name": meta.get("title") or meta.get("name") or source.get("name"),
                    "sha256": digest,
                    "license": license_name,
                    "source": "owner-authorized-local-copy",
                    "usage": "private_only",
                    "metadata": meta,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    write_private(
        destination / "origin.json",
        (
            json.dumps(
                {
                    "source_manifest": source,
                    "metadata": meta,
                    "sha256": digest,
                    "bytes": len(raw),
                    "permission": "Owner explicitly requested preserving Zhana gallery and VRM; private copy only, no public redistribution",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    return {"sha256": digest, "bytes": len(raw), "license": license_name, "private_only": True}


def avatar_status(settings):
    """Inspección de copia propia, sin crear directorios, compilar ni iniciar Node."""
    directory = settings.root / "private/calls/avatar"
    try:
        if directory.is_symlink():
            raise ValueError("avatar_directory_symlink")
        if any(
            (directory / name).lstat().st_mode & 0o077 for name in ("manifest.json", "botsky.vrm")
        ):
            raise ValueError("avatar_permissions")
        manifest = json.loads(read_regular(directory / "manifest.json", 65536))
        if manifest.get("file") != "botsky.vrm" or manifest.get("usage") != "private_only":
            raise ValueError("avatar_manifest_invalid")
        raw = read_regular(directory / "botsky.vrm", MAX_VRM)
        digest = hashlib.sha256(raw).hexdigest()
        metadata = vrm_metadata(raw)
        license_name = metadata.get("licenseName") or metadata.get("licenseUrl")
        if digest != manifest.get("sha256") or license_name != manifest.get("license"):
            raise ValueError("avatar_integrity_or_license")
        return {
            "configured": True,
            "bytes": len(raw),
            "sha256": digest,
            "license": license_name,
            "private_only": True,
        }
    except FileNotFoundError:
        return {"configured": False, "code": "avatar_not_configured"}
    except OSError, ValueError:
        return {"configured": False, "code": "avatar_invalid"}


def stage_gallery(destination, source):
    source = Path(source).absolute()
    if source.is_symlink() or (source / "library.db").is_symlink():
        raise ValueError("gallery_source_symlink")
    uri = "file:" + quote(str(source / "library.db"), safe="/") + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    destination.mkdir(mode=0o700)
    (destination / "originals").mkdir(mode=0o700)
    target = sqlite3.connect(destination / "library.db")
    (destination / "library.db").chmod(0o600)
    originals_fd = None
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        albums = db.execute(
            "SELECT id,name,slug,published FROM albums ORDER BY id LIMIT 101"
        ).fetchall()
        if len(albums) > 100:
            raise ValueError("gallery_album_limit")
        photos = db.execute(
            "SELECT DISTINCT p.id,p.mime,p.originalPath FROM photos p JOIN album_photos ap ON p.id=ap.photoId JOIN albums a ON a.id=ap.albumId WHERE p.deletedAt IS NULL AND p.duration IS NULL AND p.mime IN ('image/jpeg','image/png','image/webp') ORDER BY p.id LIMIT 10001"
        ).fetchall()
        if len(photos) > 10000:
            raise ValueError("gallery_photo_limit")
        target.executescript(
            f"PRAGMA application_id={GALLERY_APPLICATION_ID};CREATE TABLE albums(id TEXT PRIMARY KEY,name TEXT NOT NULL,slug TEXT NOT NULL,published INTEGER NOT NULL CHECK(published IN(0,1)));CREATE TABLE photos(id TEXT PRIMARY KEY,mime TEXT NOT NULL,originalPath TEXT NOT NULL,deletedAt TEXT,duration REAL);CREATE TABLE album_photos(albumId TEXT NOT NULL REFERENCES albums(id),photoId TEXT NOT NULL REFERENCES photos(id),PRIMARY KEY(albumId,photoId));"
        )
        ledger = []
        for row in albums:
            if any(
                not isinstance(row[k], str) or not 0 < len(row[k]) <= 240
                for k in ("id", "name", "slug")
            ) or row["published"] not in (0, 1):
                raise ValueError("gallery_album_invalid")
            target.execute("INSERT INTO albums VALUES(?,?,?,?)", tuple(row))
        if photos:
            originals_fd = os.open(
                source / "originals", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
        for row in photos:
            identifier = str(UUID(row["id"]))
            extensions, fmt = {
                "image/jpeg": ({"jpg", "jpeg"}, "jpeg"),
                "image/png": ({"png"}, "png"),
                "image/webp": ({"webp"}, "webp"),
            }[row["mime"]]
            if row["id"] != identifier or row["originalPath"] not in {
                f"originals/{identifier}.{ext}" for ext in extensions
            }:
                raise ValueError("gallery_photo_path")
            filename = row["originalPath"].split("/")[1]
            fd = os.open(filename, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=originals_fd)
            with os.fdopen(fd, "rb") as stream:
                import stat

                mode = os.fstat(stream.fileno())
                if not stat.S_ISREG(mode.st_mode) or not 0 < mode.st_size <= MAX_PHOTO_BYTES:
                    raise ValueError("gallery_photo_size")
                raw = stream.read(MAX_PHOTO_BYTES + 1)
            if len(raw) != mode.st_size or not _valid_static_image(raw, fmt):
                raise ValueError("gallery_photo_invalid")
            write_private(destination / row["originalPath"], raw)
            target.execute("INSERT INTO photos VALUES(?,?,?,NULL,NULL)", tuple(row))
            ledger.append(
                {"id": identifier, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            )
        for row in db.execute(
            "SELECT ap.albumId,ap.photoId FROM album_photos ap JOIN photos p ON ap.photoId=p.id WHERE p.deletedAt IS NULL AND p.duration IS NULL AND p.mime IN ('image/jpeg','image/png','image/webp')"
        ):
            target.execute("INSERT INTO album_photos VALUES(?,?)", tuple(row))
        target.commit()
        # Keep descriptive/curation metadata privately; no user histories or other tables.
        metadata = {
            "albums": [dict(r) for r in db.execute("SELECT * FROM albums ORDER BY id")],
            "photos": ledger,
            "publication_preserved": True,
            "permission": "Owner explicitly requested preserving gallery; own private copy",
        }
        write_private(
            destination / "origin.json",
            (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode(),
        )
        return {
            "albums": len(albums),
            "published_albums": sum(r["published"] for r in albums),
            "photos": len(photos),
            "publication_preserved": True,
        }
    finally:
        if originals_fd is not None:
            os.close(originals_fd)
        db.rollback()
        db.close()
        target.close()


def import_assets(settings, *, gallery=None, avatar_manifest=None, avatar_model=None):
    private = private_directory(settings.root, "private")
    staging = private / ("asset-import-" + uuid4().hex)
    staging.mkdir(mode=0o700)
    results, prepared = {}, []
    try:
        if gallery is not None:
            results["gallery"] = stage_gallery(staging / "gallery", gallery)
            prepared.append((staging / "gallery", private / "gallery"))
        if avatar_manifest is not None or avatar_model is not None:
            if avatar_manifest is None or avatar_model is None:
                raise ValueError("avatar_explicit_paths_required")
            results["avatar"] = stage_avatar(staging / "avatar", avatar_manifest, avatar_model)
            calls = private_directory(settings.root, "private/calls")
            prepared.append((staging / "avatar", calls / "avatar"))
        for _, target in prepared:
            if target.is_symlink() or target.exists() and any(target.iterdir()):
                raise ValueError("asset_destination_not_empty")
        for source, target in prepared:
            if target.exists():
                target.rmdir()
            os.rename(source, target)
        return results
    finally:
        shutil.rmtree(staging)
