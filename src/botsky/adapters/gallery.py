"""Bounded published library component adapted for Botsky; own storage only."""

from __future__ import annotations

import os
import random
import re
import sqlite3
import stat
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

MAX_CATALOG_ALBUMS = 100
MAX_QUERY_ROWS = 10_000
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_SELECTION_BYTES = 30 * 1024 * 1024
MAX_COUNT = 100
MAX_OPERATION_SECONDS = 15.0

_FORMATS = {
    "image/jpeg": ("jpg", "jpeg"),
    "image/png": ("png", "png"),
    "image/webp": ("webp", "webp"),
}
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


class LibraryError(Exception):
    """A private library could not be read safely."""

    def __init__(self) -> None:
        super().__init__("Published library unavailable")


@dataclass(frozen=True)
class Album:
    id: str
    name: str
    slug: str
    count: int


@dataclass(frozen=True)
class LibraryPhoto:
    id: str
    mime: str
    filename: str
    data: bytes


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", value).casefold())
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).split())


class PublishedLibrary:
    def __init__(self, project_root: Path) -> None:
        from ..local_files import private_directory

        self.root = private_directory(Path(project_root), "private/gallery")

    def _open_db(self, deadline: float) -> sqlite3.Connection:
        try:
            root_stat = self.root.lstat()
            if not stat.S_ISDIR(root_stat.st_mode):
                raise LibraryError
            db_path = self.root / "library.db"
            db_stat = db_path.lstat()
            if not stat.S_ISREG(db_stat.st_mode):
                raise LibraryError
            uri = "file:" + quote(str(db_path.resolve(strict=True)), safe="/") + "?mode=ro"
            db = sqlite3.connect(uri, uri=True, timeout=3, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA busy_timeout=3000")
            db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            db.execute("BEGIN")
            return db
        except OSError, sqlite3.Error, ValueError:
            raise LibraryError from None

    @staticmethod
    def _bounded(rows: list[sqlite3.Row], maximum: int) -> list[sqlite3.Row]:
        if len(rows) > maximum:
            raise LibraryError
        return rows

    def catalog(self) -> list[Album]:
        deadline = time.monotonic() + MAX_OPERATION_SECONDS
        self._require_pillow()
        db = self._open_db(deadline)
        try:
            albums = self._bounded(
                db.execute(
                    "SELECT id,name,slug FROM albums WHERE published=1 ORDER BY slug,id LIMIT ?",
                    (MAX_CATALOG_ALBUMS + 1,),
                ).fetchall(),
                MAX_CATALOG_ALBUMS,
            )
            self._check_deadline(deadline)
            result = []
            for album in albums:
                self._check_deadline(deadline)
                count = db.execute(
                    "SELECT count(*) FROM album_photos ap JOIN photos p ON p.id=ap.photoId "
                    "WHERE ap.albumId=? AND p.deletedAt IS NULL AND p.duration IS NULL "
                    "AND p.mime IN ('image/jpeg','image/png','image/webp')",
                    (album["id"],),
                ).fetchone()[0]
                result.append(Album(album["id"], album["name"], album["slug"], int(count)))
            return result
        except sqlite3.Error, TypeError, KeyError:
            raise LibraryError from None
        finally:
            try:
                db.rollback()
            finally:
                db.close()

    def select(self, category: str | None, count: int, excluded: set[str]) -> list[LibraryPhoto]:
        if type(count) is not int or count < 1 or count > MAX_COUNT:
            raise LibraryError
        deadline = time.monotonic() + MAX_OPERATION_SECONDS
        self._require_pillow()
        db = self._open_db(deadline)
        root_fd = -1
        originals_fd = -1
        try:
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            originals_fd = os.open(
                "originals", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
            )
            albums = self._bounded(
                db.execute(
                    "SELECT id,name,slug FROM albums WHERE published=1 ORDER BY id LIMIT ?",
                    (MAX_QUERY_ROWS + 1,),
                ).fetchall(),
                MAX_QUERY_ROWS,
            )
            self._check_deadline(deadline)
            if category is None:
                album_ids = {str(row["id"]) for row in albums}
            else:
                wanted = _normalized(category)
                matched = [
                    str(row["id"])
                    for row in albums
                    if wanted
                    and wanted in {_normalized(str(row["name"])), _normalized(str(row["slug"]))}
                ]
                album_ids = set(matched)
            if not album_ids:
                return []
            placeholders = ",".join("?" for _ in album_ids)
            candidates = self._bounded(
                db.execute(
                    "SELECT DISTINCT p.id,p.mime,p.originalPath FROM photos p "
                    "JOIN album_photos ap ON ap.photoId=p.id "
                    f"WHERE ap.albumId IN ({placeholders}) AND p.deletedAt IS NULL AND p.duration IS NULL "
                    "AND p.mime IN ('image/jpeg','image/png','image/webp') "
                    "ORDER BY p.id LIMIT ?",
                    (*sorted(album_ids), MAX_QUERY_ROWS + 1),
                ).fetchall(),
                MAX_QUERY_ROWS,
            )
            self._check_deadline(deadline)
            random.SystemRandom().shuffle(candidates)
            unseen = [row for row in candidates if row["id"] not in excluded]
            seen = [row for row in candidates if row["id"] in excluded]
            result: list[LibraryPhoto] = []
            total = 0
            selected: set[str] = set()
            for row in (*unseen, *seen):
                self._check_deadline(deadline)
                photo = self._read_photo(row, originals_fd, deadline)
                if photo is None or photo.id in selected:
                    continue
                if total + len(photo.data) > MAX_SELECTION_BYTES:
                    if result:
                        break
                    continue
                result.append(photo)
                selected.add(photo.id)
                total += len(photo.data)
                if len(result) == count:
                    break
            return result
        except LibraryError:
            raise
        except OSError, sqlite3.Error, TypeError, KeyError, ValueError:
            raise LibraryError from None
        finally:
            if originals_fd >= 0:
                os.close(originals_fd)
            if root_fd >= 0:
                os.close(root_fd)
            try:
                db.rollback()
            finally:
                db.close()

    def get_photo(self, photo_id: str, category: str | None = None) -> LibraryPhoto | None:
        if not isinstance(photo_id, str) or not _UUID_RE.fullmatch(photo_id):
            return None
        try:
            canonical_id = str(uuid.UUID(photo_id))
        except ValueError:
            return None
        deadline = time.monotonic() + MAX_OPERATION_SECONDS
        self._require_pillow()
        db = self._open_db(deadline)
        root_fd = -1
        originals_fd = -1
        try:
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            originals_fd = os.open(
                "originals", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
            )
            albums = self._bounded(
                db.execute(
                    "SELECT id,name,slug FROM albums WHERE published=1 ORDER BY id LIMIT ?",
                    (MAX_QUERY_ROWS + 1,),
                ).fetchall(),
                MAX_QUERY_ROWS,
            )
            self._check_deadline(deadline)
            if category is None:
                album_ids = {str(row["id"]) for row in albums}
            else:
                wanted = _normalized(category)
                album_ids = {
                    str(row["id"])
                    for row in albums
                    if wanted
                    and wanted in {_normalized(str(row["name"])), _normalized(str(row["slug"]))}
                }
            if not album_ids:
                return None
            placeholders = ",".join("?" for _ in album_ids)
            row = db.execute(
                "SELECT DISTINCT p.id,p.mime,p.originalPath FROM photos p "
                "JOIN album_photos ap ON ap.photoId=p.id "
                "JOIN albums a ON a.id=ap.albumId AND a.published=1 "
                f"WHERE p.id=? AND ap.albumId IN ({placeholders}) AND p.deletedAt IS NULL "
                "AND p.duration IS NULL AND p.mime IN ('image/jpeg','image/png','image/webp') "
                "LIMIT 1",
                (canonical_id, *sorted(album_ids)),
            ).fetchone()
            self._check_deadline(deadline)
            return self._read_photo(row, originals_fd, deadline) if row is not None else None
        except LibraryError:
            raise
        except OSError, sqlite3.Error, TypeError, KeyError, ValueError:
            raise LibraryError from None
        finally:
            if originals_fd >= 0:
                os.close(originals_fd)
            if root_fd >= 0:
                os.close(root_fd)
            try:
                db.rollback()
            finally:
                db.close()

    @staticmethod
    def _read_photo(row: sqlite3.Row, originals_fd: int, deadline: float) -> LibraryPhoto | None:
        photo_id = str(row["id"])
        mime = str(row["mime"])
        file_info = _FORMATS.get(mime)
        if file_info is None or not _UUID_RE.fullmatch(photo_id):
            return None
        try:
            canonical_id = str(uuid.UUID(photo_id))
        except ValueError:
            return None
        extension, image_format = file_info
        allowed_extensions = ("jpg", "jpeg") if mime == "image/jpeg" else (extension,)
        if row["originalPath"] not in {
            f"originals/{canonical_id}.{candidate}" for candidate in allowed_extensions
        }:
            return None
        fd = -1
        try:
            selected_extension = str(row["originalPath"]).rsplit(".", 1)[-1]
            fd = os.open(
                f"{canonical_id}.{selected_extension}",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=originals_fd,
            )
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size < 1 or info.st_size > MAX_PHOTO_BYTES:
                return None
            chunks: list[bytes] = []
            remaining = MAX_PHOTO_BYTES + 1
            while remaining:
                PublishedLibrary._check_deadline(deadline)
                chunk = os.read(fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) != info.st_size or len(data) > MAX_PHOTO_BYTES:
                return None
        except OSError:
            return None
        finally:
            if fd >= 0:
                os.close(fd)
        if not _valid_static_image(data, image_format):
            return None
        return LibraryPhoto(canonical_id, mime, f"{canonical_id}.{selected_extension}", data)

    @staticmethod
    def _check_deadline(deadline: float) -> None:
        if time.monotonic() >= deadline:
            raise LibraryError

    @staticmethod
    def _require_pillow() -> None:
        try:
            import PIL  # noqa: F401
        except ImportError:
            raise LibraryError from None


def _valid_static_image(data: bytes, fmt: str) -> bool:
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 16_000_000
        with Image.open(__import__("io").BytesIO(data)) as image:
            if image.format != fmt.upper() or getattr(image, "is_animated", False):
                return False
            width, height = image.size
            if (
                width < 1
                or height < 1
                or width > 4096
                or height > 4096
                or width * height > 16_000_000
            ):
                return False
            image.verify()
            return True
    except ImportError:
        raise LibraryError from None
    except Exception:
        return False
