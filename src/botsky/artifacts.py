"""Archivos retenidos propios: referencias opacas, copia sin symlinks y leases SQLite."""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .contracts import ArtifactRef, Scope
from .domains.notes import SCOPE_SQL
from .local_files import private_directory

MAX_BYTES = 2000000000
INPUT_BYTES = 1000000000
DOCUMENT_BYTES = 100000000
RETENTION_MS = 86400000


class ArtifactProblem(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StagedFile:
    id: str
    path: Path
    format: str
    size: int
    sha256: str


class Artifacts:
    def __init__(self, store, root):
        self.store = store
        candidate = Path(root)
        self.root = private_directory(candidate.parent.parent, "private/artifacts")

    def path(self, artifact_id):
        if not isinstance(artifact_id, str) or not re.fullmatch(r"[a-f0-9]{32}", artifact_id):
            raise ArtifactProblem("invalid_artifact_id")
        return self.root / (artifact_id + ".bin")

    def stage(self, source, *, output=False):
        descriptor = None
        destination = self.path(uuid4().hex)
        try:
            descriptor = os.open(source, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None
                info = os.fstat(stream.fileno())
                limit = MAX_BYTES if output else INPUT_BYTES
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                    raise ArtifactProblem("input_size")
                digest, size = hashlib.sha256(), 0
                fd = os.open(
                    destination, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600
                )
                with os.fdopen(fd, "wb") as target:
                    while chunk := stream.read(192 * 1024):
                        size += len(chunk)
                        if size > limit:
                            raise ArtifactProblem("input_size")
                        digest.update(chunk)
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
            with destination.open("rb") as stream:
                header = stream.read(4096)
            if output and header.startswith(b"PK\x03\x04"):
                try:
                    format = self._format(destination, header)
                except ArtifactProblem:
                    format = "zip"
            else:
                format = self._format(destination, header)
            if (
                not output
                and format not in ("mp4", "webm", "ogg", "mp3", "aac", "wav", "flac")
                and size > DOCUMENT_BYTES
            ):
                raise ArtifactProblem("input_size")
            return StagedFile(destination.stem, destination, format, size, digest.hexdigest())
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def stage_text(self, text):
        raw = text.encode("utf-8")
        if not 0 < len(raw) <= DOCUMENT_BYTES:
            raise ArtifactProblem("input_size")
        destination = self.path(uuid4().hex)
        try:
            fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            return StagedFile(
                destination.stem, destination, "txt", len(raw), hashlib.sha256(raw).hexdigest()
            )
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def _format(path, header):
        from .engines.documents import _kind
        from .engines.media_edit import _demuxer
        from .engines.process import MediaError

        if re.search(rb"(?m)^\d+\s*\r?\n\d{2,}:\d{2}:\d{2},\d{3} --> ", header):
            return "srt"

        try:
            demuxer = _demuxer(header)
            return {"mov": "mp4", "matroska": "webm"}.get(demuxer, demuxer)
        except MediaError:
            pass
        try:
            return _kind(path.read_bytes())
        except MediaError as exc:
            raise ArtifactProblem(exc.code) from None

    def register(
        self, db, staged, context, source_message_id, now, *, origin="incoming", receipt_id=None
    ):
        db.execute(
            "INSERT INTO artifacts(id,instance,account,actor,chat,is_group,epoch,source_message_id,receipt_id,origin,format,size,sha256,created_ms,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                staged.id,
                *context.scope_key,
                source_message_id,
                receipt_id,
                origin,
                staged.format,
                staged.size,
                staged.sha256,
                now,
                now + RETENTION_MS,
            ),
        )
        return staged.id

    def import_local(self, source, context, source_message_id, now):
        staged = self.stage(source)
        try:
            with self.store.transaction() as db:
                self.register(db, staged, context, source_message_id, now)
        except BaseException:
            staged.path.unlink(missing_ok=True)
            raise
        return staged.id

    def owned(self, db, artifact_id, context, now, *, holder=None):
        row = db.execute(
            f"SELECT * FROM artifacts WHERE id=? AND {SCOPE_SQL} AND state='active'",
            (artifact_id, *context.scope_key),
        ).fetchone()
        school_access = False
        if context.scope.is_group:
            shared = db.execute(
                "SELECT a.* FROM artifacts a JOIN school_asset_grants g ON g.artifact_id=a.id JOIN school_tasks t ON t.id=g.task_id WHERE a.id=? AND g.instance=? AND g.account=? AND g.chat=? AND g.is_group=1 AND g.epoch=? AND g.expires_ms>? AND a.state='active' AND t.state!='deleted'",
                (
                    artifact_id,
                    context.instance,
                    context.account,
                    context.scope.chat,
                    context.epoch,
                    now,
                ),
            ).fetchone()
            if shared:
                row = shared
                school_access = True
        if row is None:
            raise ArtifactProblem("artifact_access_denied")
        if row["actor"] == context.scope.actor and not school_access:
            school_access = bool(
                db.execute(
                    "SELECT 1 FROM school_tasks t JOIN artifact_leases l ON l.artifact_id=t.artifact_id AND l.holder='school-'||t.id WHERE t.artifact_id=? AND t.instance=? AND t.account=? AND t.actor=? AND t.chat=? AND t.is_group=? AND t.epoch=? AND t.state!='deleted' AND l.expires_ms>?",
                    (artifact_id, *context.scope_key, now),
                ).fetchone()
            )
        if row["expires_ms"] <= now and not school_access:
            lease = (
                db.execute(
                    "SELECT 1 FROM artifact_leases WHERE artifact_id=? AND holder=? AND expires_ms>?",
                    (artifact_id, holder, now),
                ).fetchone()
                if holder
                else None
            )
            if not lease:
                raise ArtifactProblem("artifact_expired")
        path = self.path(artifact_id)
        try:
            info = path.lstat()
        except OSError:
            raise ArtifactProblem("artifact_missing") from None
        if not stat.S_ISREG(info.st_mode) or info.st_size != row["size"]:
            raise ArtifactProblem("artifact_changed")
        return row

    def ref(self, row):
        return ArtifactRef(
            row["id"],
            Scope(row["actor"], row["chat"], bool(row["is_group"])),
            row["instance"],
            row["account"],
            row["epoch"],
            row["source_message_id"],
            row["format"],
            row["size"],
            row["sha256"],
            row["expires_ms"],
        )

    def resolve(self, db, context, incoming_row, now):
        ids = json.loads(incoming_row["attachments_json"])
        if ids:
            for artifact_id in ids:
                row = self.owned(db, artifact_id, context, now)
                if (
                    row["origin"] != "incoming"
                    or row["source_message_id"] != incoming_row["message_id"]
                ):
                    raise ArtifactProblem("attachment_source_mismatch")
            return ids
        quote = incoming_row["quoted_message_id"]
        if not quote:
            return []
        prior = db.execute(
            "SELECT * FROM inbox WHERE instance=? AND account=? AND message_id=? AND actor=? AND chat=? AND is_group=? AND epoch=?",
            (
                context.instance,
                context.account,
                quote,
                context.scope.actor,
                context.scope.chat,
                int(context.scope.is_group),
                context.epoch,
            ),
        ).fetchone()
        if prior:
            ids = json.loads(prior["attachments_json"])
        else:
            sent = db.execute(
                "SELECT o.artifacts_json FROM inbox i JOIN outbox o ON i.id=o.receipt_id WHERE o.provider_message_id=? AND o.state='accepted' AND o.artifacts_json!='[]' AND i.instance=? AND i.account=? AND i.actor=? AND i.chat=? AND i.is_group=? AND i.epoch=?",
                (quote, *context.scope_key),
            ).fetchone()
            if not sent:
                raise ArtifactProblem("quoted_attachment_unavailable")
            ids = json.loads(sent["artifacts_json"])
        for artifact_id in ids:
            self.owned(db, artifact_id, context, now)
        return ids

    def lease(self, db, ids, context, holder, token, expires, now, *, source_holder=None):
        for artifact_id in ids:
            self.owned(db, artifact_id, context, now, holder=source_holder or holder)
            db.execute(
                "INSERT INTO artifact_leases VALUES(?,?,?,?) ON CONFLICT(artifact_id,holder) DO UPDATE SET token=excluded.token,expires_ms=excluded.expires_ms",
                (artifact_id, holder, token, expires),
            )

    def collect(self, now):
        with self.store.transaction() as db:
            db.execute("DELETE FROM artifact_leases WHERE expires_ms<=?", (now,))
            rows = db.execute(
                "SELECT id FROM artifacts a WHERE expires_ms<=? AND NOT EXISTS(SELECT 1 FROM artifact_leases l WHERE l.artifact_id=a.id)",
                (now,),
            ).fetchall()
            for row in rows:
                db.execute("UPDATE artifacts SET state='deleting' WHERE id=?", (row["id"],))
        removed = 0
        for row in rows:
            self.path(row["id"]).unlink(missing_ok=True)
            with self.store.transaction() as db:
                db.execute("DELETE FROM artifacts WHERE id=? AND state='deleting'", (row["id"],))
            removed += 1
        return removed
