"""Transporte de laboratorio local durable. Nunca conecta una cuenta real."""

import hashlib
import os
import sqlite3
from contextlib import closing
from uuid import uuid4

from ..contracts import DeliveryAck, canonical
from ..local_files import private_directory


class LabTransport:
    def __init__(self, settings, *, artifacts=None, clock=None):
        if settings.transport != "local":
            raise ValueError("lab_requires_local_transport")
        from .local import clock_ms

        self.settings = settings
        self.artifacts = artifacts
        self.clock = clock or clock_ms
        self.path = private_directory(settings.root, "private/lab") / "transport.sqlite3"
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if self.path.is_symlink() or not self.path.is_file():
                raise ValueError("lab_storage_invalid") from None
        else:
            os.close(fd)
        with closing(sqlite3.connect(self.path)) as db, db:
            app_id = db.execute("PRAGMA application_id").fetchone()[0]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if app_id == 0 and not tables:
                db.executescript(
                    "PRAGMA application_id=1112755276; CREATE TABLE accepted(id TEXT PRIMARY KEY, payload TEXT NOT NULL, instance TEXT NOT NULL, account TEXT NOT NULL, epoch INTEGER NOT NULL);"
                )
            elif app_id != 1112755276 or tables != {"accepted"}:
                raise ValueError("lab_foreign_storage")

    def send(self, part):
        c, s = part.context, self.settings
        if (c.instance, c.account, c.epoch) != (s.instance, s.account, s.epoch):
            return DeliveryAck(False)
        if part.artifacts and self.artifacts is None:
            return DeliveryAck(False)
        media = []
        for identifier in part.artifacts:
            with self.artifacts.store.transaction() as db:
                row = self.artifacts.owned(
                    db,
                    identifier,
                    c,
                    self.clock(),
                    holder=f"delivery-{part.receipt_id}-{part.position}",
                )
            directory = private_directory(s.root, "private/lab/media")
            target, temporary = directory / row["sha256"], directory / (uuid4().hex + ".tmp")
            digest, size = hashlib.sha256(), 0
            try:
                source_fd = os.open(self.artifacts.path(identifier), os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(source_fd, "rb") as source, temporary.open("xb") as output:
                    os.chmod(temporary, 0o600)
                    while chunk := source.read(192 * 1024):
                        size += len(chunk)
                        if size > row["size"]:
                            raise ValueError("lab_media_size_changed")
                        digest.update(chunk)
                        output.write(chunk)
                if size != row["size"] or digest.hexdigest() != row["sha256"]:
                    raise ValueError("lab_media_hash_changed")
                if target.is_symlink():
                    raise ValueError("lab_media_symlink")
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            media.append({"id": identifier, "sha256": row["sha256"], "size": size})
        payload = canonical(
            {
                "context": c.scope_key,
                "receipt_id": part.receipt_id,
                "position": part.position,
                "text": part.text,
                "artifacts": part.artifacts,
                "media": media,
            }
        )
        identity = hashlib.sha256(
            canonical([c.instance, c.account, c.epoch, part.receipt_id, part.position]).encode()
        ).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            prior = db.execute("SELECT payload FROM accepted WHERE id=?", (identity,)).fetchone()
            if prior and prior[0] != payload:
                raise ValueError("lab_delivery_conflict")
            db.execute(
                "INSERT OR IGNORE INTO accepted VALUES(?,?,?,?,?)",
                (identity, payload, c.instance, c.account, c.epoch),
            )
        return DeliveryAck(True, "lab-" + identity)

    def accepted(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute(
                "SELECT count(*) FROM accepted WHERE instance=? AND account=? AND epoch=?",
                (self.settings.instance, self.settings.account, self.settings.epoch),
            ).fetchone()[0]
