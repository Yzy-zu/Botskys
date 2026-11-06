"""SQLite propia: admisión durable, efectos locales atómicos y recibos por parte."""

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

from . import access
from .contracts import CommandContext, Receipt, Result, Scope, canonical

APPLICATION_ID = 1112755033
SCHEMA_VERSION = 16
PART_CHARS = 3500


def context_of(row):
    return CommandContext(
        row["id"],
        row["instance"],
        row["account"],
        Scope(row["actor"], row["chat"], bool(row["is_group"])),
        row["epoch"],
        row["revision"],
    )


def receipt_of(row, duplicate=False):
    return Receipt(
        row["id"],
        row["state"],
        Result.from_json(row["result_json"]) if row["result_json"] else None,
        duplicate,
    )


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("DB symlink no admisible")
        try:
            descriptor = os.open(
                self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
            )
        except FileExistsError:
            if not stat.S_ISREG(self.path.lstat().st_mode):
                raise ValueError("DB no regular") from None
        else:
            os.close(descriptor)
        db = self.connect()
        try:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            application_id = db.execute("PRAGMA application_id").fetchone()[0]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version == 0 and not tables and application_id == 0:
                db.executescript(
                    "BEGIN IMMEDIATE; CREATE TABLE schema_version(version INTEGER PRIMARY KEY); INSERT INTO schema_version VALUES(1); PRAGMA user_version=1; COMMIT;"
                )
                version, tables = 1, {"schema_version"}
            if version == 1:
                if (
                    tables != {"schema_version"}
                    or application_id != 0
                    or [r[0] for r in db.execute("SELECT version FROM schema_version")] != [1]
                ):
                    raise ValueError("DB v1 ajena o no reconocida; no migrar")
                db.executescript((Path(__file__).parent / "migrations/002_core.sql").read_text())
                version, application_id = 2, APPLICATION_ID
            if version == 2 and application_id == APPLICATION_ID:
                db.executescript((Path(__file__).parent / "migrations/003_jobs.sql").read_text())
                version = 3
            if version == 3 and application_id == APPLICATION_ID:
                db.executescript((Path(__file__).parent / "migrations/004_ai.sql").read_text())
                version = 4
            if version == 4 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/005_organization.sql").read_text()
                )
                version = 5
            if version == 5 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/006_integrations.sql").read_text()
                )
                version = 6
            if version == 6 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/007_economy_blackjack.sql").read_text()
                )
                version = 7
            if version == 7 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/008_happy_hour.sql").read_text()
                )
                version = 8
            if version == 8 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/009_gallery_orders.sql").read_text()
                )
                version = 9
            if version == 9 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/010_cooperacha.sql").read_text()
                )
                version = 10
            if version == 10 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/011_happy_media.sql").read_text()
                )
                version = 11
            if version == 11 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/012_roulette.sql").read_text()
                )
                version = 12
            if version == 12 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/013_coop_seen.sql").read_text()
                )
                version = 13
            if version == 13 and application_id == APPLICATION_ID:
                db.executescript(
                    (Path(__file__).parent / "migrations/014_external_operations.sql").read_text()
                )
                version = 14
            if version == 14 and application_id == APPLICATION_ID:
                db.executescript((Path(__file__).parent / "migrations/015_admin.sql").read_text())
                version = 15
            if version == 15 and application_id == APPLICATION_ID:
                db.executescript((Path(__file__).parent / "migrations/016_nuclear.sql").read_text())
                version = 16
            if version != SCHEMA_VERSION or application_id != APPLICATION_ID:
                raise ValueError("DB ajena o esquema incompatible; no migrar")
            db.execute("PRAGMA journal_mode=WAL")
            self.path.chmod(0o600)
        finally:
            db.close()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
        except BaseException:
            db.close()
            raise
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def admit(self, incoming, settings, prepare):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM inbox WHERE instance=? AND account=? AND message_id=?",
                (incoming.instance, incoming.account, incoming.message_id),
            ).fetchone()
            if row:
                if row["fingerprint"] != incoming.fingerprint:
                    return Receipt(
                        incoming.id,
                        "rejected",
                        Result(
                            "failed",
                            "message_conflict",
                            "El identificador ya corresponde a otra entrada.",
                        ),
                        True,
                    )
                if row["epoch"] != settings.epoch:
                    return Receipt(
                        incoming.id,
                        "rejected",
                        Result(
                            "failed", "stale_epoch", "El recibo pertenece a una época anterior."
                        ),
                        True,
                    )
                return receipt_of(row, True)
            context = CommandContext(
                incoming.id, incoming.instance, incoming.account, incoming.scope, settings.epoch, 0
            )
            parsed, result, state = prepare(context, db)
            notice = ""
            if parsed is not None and result is None and parsed.spec.family != "core":
                from .interactions import replace_file_waits

                notice = replace_file_waits(db, context)
            command = parsed.canonical() if parsed else None
            path = canonical(parsed.spec.path) if parsed else None
            permission = parsed.spec.permission if parsed and result is None else "public"
            db.execute(
                "INSERT INTO inbox(id,instance,account,message_id,actor,chat,is_group,epoch,source_ms,received_ms,fingerprint,command_json,path_json,permission,state,result_json,attachments_json,quoted_message_id,notice,text,mentions_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    incoming.id,
                    incoming.instance,
                    incoming.account,
                    incoming.message_id,
                    incoming.scope.actor,
                    incoming.scope.chat,
                    int(incoming.scope.is_group),
                    settings.epoch,
                    incoming.source_ms,
                    incoming.received_ms,
                    incoming.fingerprint,
                    command,
                    path,
                    permission,
                    state,
                    result.to_json() if result else None,
                    canonical(incoming.attachments),
                    incoming.quoted_message_id,
                    notice,
                    incoming.text
                    if incoming.scope.actor in (settings.friends | {settings.owner})
                    and (
                        not incoming.scope.is_group
                        or incoming.scope.chat in settings.allowed_groups
                    )
                    else "",
                    canonical(incoming.mentioned_ids),
                ),
            )
            if result and state == "completed":
                self.enqueue(db, context, result, incoming.received_ms)
            return Receipt(incoming.id, state, result)

    @staticmethod
    def enqueue(db, context, result, now):
        if result.code == "job_queued":
            return
        text = result.text + "\n/estado " + context.receipt_id if result.text else ""
        count = 0
        for position, start in enumerate(range(0, len(text), PART_CHARS)):
            db.execute(
                "INSERT INTO outbox(receipt_id,position,payload,state,updated_ms) VALUES(?,?,?,'pending',?)",
                (context.receipt_id, position, text[start : start + PART_CHARS], now),
            )
            count = position + 1
        for artifact_id in result.data.get("artifacts", ()):
            db.execute(
                "INSERT INTO outbox(receipt_id,position,payload,state,updated_ms,artifacts_json) VALUES(?,?,'','pending',?,?)",
                (context.receipt_id, count, now, canonical([artifact_id])),
            )
            count += 1

    def execute(self, receipt_id, settings, now, handler):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM inbox WHERE id=?", (receipt_id,)).fetchone()
            if row is None:
                raise ValueError("recibo inexistente")
            if row["state"] != "queued":
                return receipt_of(row)
            context = context_of(row)
            rejection = access.authorize(row["permission"], context, settings)
            command = json.loads(row["command_json"])
            effect_id = hashlib.sha256(
                canonical([receipt_id, row["command_json"], context.scope_key]).encode()
            ).hexdigest()
            result = rejection or handler(
                db, context, tuple(json.loads(row["path_json"])), command, effect_id, now
            )
            if row["notice"]:
                from dataclasses import replace

                result = replace(result, text=row["notice"] + result.text)
            db.execute(
                "INSERT INTO effects VALUES(?,?,?,?,?,?)",
                (
                    effect_id,
                    receipt_id,
                    command["operation"],
                    canonical(command["arguments"]),
                    result.to_json(),
                    now,
                ),
            )
            changed = db.execute(
                "UPDATE inbox SET state='completed',result_json=?,revision=revision+1 WHERE id=? AND state='queued' AND revision=?",
                (result.to_json(), receipt_id, context.revision),
            ).rowcount
            if changed != 1:
                raise RuntimeError("revisión cambió durante efecto local")
            self.enqueue(db, context, result, now)
            return Receipt(receipt_id, "completed", result)

    def queued(self, settings, limit=100):
        db = self.connect()
        try:
            return [
                r[0]
                for r in db.execute(
                    "SELECT id FROM inbox WHERE instance=? AND account=? AND epoch=? AND state='queued' ORDER BY received_ms,id LIMIT ?",
                    (settings.instance, settings.account, settings.epoch, limit),
                )
            ]
        finally:
            db.close()

    def own_receipt(self, db, receipt_id, context):
        return db.execute(
            "SELECT * FROM inbox WHERE id=? AND instance=? AND account=? AND actor=? AND chat=? AND is_group=? AND epoch=?",
            (receipt_id, *context.scope_key),
        ).fetchone()

    def state(self, db, context, target):
        row = self.own_receipt(db, target, context)
        if row is None:
            return Result(
                "empty", "receipt_not_found", "No hay un encargo propio con ese ID en este chat."
            )
        deliveries = [
            dict(r)
            for r in db.execute(
                "SELECT position,state FROM outbox WHERE receipt_id=? ORDER BY position", (target,)
            )
        ]
        job = db.execute(
            "SELECT state,revision,result_json FROM jobs WHERE id=?", (target,)
        ).fetchone()
        job_data = {"state": job["state"], "revision": job["revision"]} if job else None
        if job and job["result_json"]:
            result = Result.from_json(job["result_json"])
            job_data.update(status=result.status, code=result.code)
        visible_state = (
            "uncertain"
            if job_data and job_data.get("status") == "uncertain"
            else job["state"]
            if job
            else row["state"]
        )
        return Result(
            "ok",
            "receipt_state",
            "Encargo " + target + ": " + visible_state + ".",
            {
                "id": target,
                "state": row["state"],
                "revision": row["revision"],
                "delivery": deliveries,
                "job": job_data,
            },
        )

    def cancel(self, db, context, target):
        if target == context.receipt_id:
            return Result(
                "failed",
                "cannot_cancel_self",
                "El comando de cancelación no puede cancelarse a sí mismo.",
            )
        row = self.own_receipt(db, target, context)
        if row is None:
            return Result(
                "empty", "receipt_not_found", "No hay un encargo propio con ese ID en este chat."
            )
        from .jobs import cancel_job

        if job_result := cancel_job(db, context, target):
            return job_result
        if row["state"] != "queued":
            return Result(
                "empty",
                "already_finished",
                "El encargo ya terminó; no se deshace su efecto.",
                {"id": target, "state": row["state"]},
            )
        result = Result("cancelled", "request_cancelled", "Encargo cancelado antes de ejecutarse.")
        db.execute(
            "UPDATE inbox SET state='cancelled',result_json=?,revision=revision+1 WHERE id=? AND revision=? AND state='queued'",
            (result.to_json(), target, row["revision"]),
        )
        db.execute(
            "UPDATE outbox SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state='pending'",
            (target,),
        )
        return Result(
            "cancelled", "request_cancelled", "Encargo " + target + " cancelado.", {"id": target}
        )

    def claim_part(self, receipt_id, settings, now, retry_failed=False):
        with self.transaction() as db:
            parent = db.execute("SELECT * FROM inbox WHERE id=?", (receipt_id,)).fetchone()
            if parent is None or parent["state"] != "completed":
                return None
            context = context_of(parent)
            if access.authorize(parent["permission"], context, settings):
                return None
            from .domains.game_delivery import retired

            if retired(db, receipt_id, settings, now):
                db.execute(
                    "UPDATE outbox SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state='pending'",
                    (receipt_id,),
                )
                return None
            if parent["origin"] == "internal":
                from .domains.bot import current

                mode = current(db, context)
                if mode["mode"] == "apagado" or mode["paused_until_ms"] > now:
                    return None
                event = db.execute(
                    "SELECT expires_ms FROM organization_events WHERE delivery_receipt_id=?",
                    (receipt_id,),
                ).fetchone()
                if event and event["expires_ms"] <= now:
                    db.execute(
                        "UPDATE outbox SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state='pending'",
                        (receipt_id,),
                    )
                    db.execute(
                        "UPDATE reminders SET state='expired',revision=revision+1 WHERE delivery_receipt_id=? AND state='emitted'",
                        (receipt_id,),
                    )
                    db.execute(
                        "UPDATE organization_events SET state='expired' WHERE delivery_receipt_id=? AND state='emitted'",
                        (receipt_id,),
                    )
                    return None
            row = db.execute(
                "SELECT * FROM outbox WHERE receipt_id=? AND state!='accepted' ORDER BY position LIMIT 1",
                (receipt_id,),
            ).fetchone()
            if row is None or row["state"] not in (
                ("pending", "failed") if retry_failed else ("pending",)
            ):
                return None
            artifact_ids = tuple(json.loads(row["artifacts_json"]))
            if artifact_ids:
                from .artifacts import ArtifactProblem, Artifacts

                try:
                    Artifacts(self, settings.root / "private/artifacts").lease(
                        db,
                        artifact_ids,
                        context,
                        f"delivery-{receipt_id}-{row['position']}",
                        str(row["revision"] + 1),
                        now + 86400000,
                        now,
                    )
                except ArtifactProblem as exc:
                    db.execute(
                        "UPDATE outbox SET state='failed',error_code=?,revision=revision+1 WHERE receipt_id=? AND position=?",
                        (exc.code, receipt_id, row["position"]),
                    )
                    return None
            changed = db.execute(
                "UPDATE outbox SET state='sending',revision=revision+1,updated_ms=? WHERE receipt_id=? AND position=? AND revision=? AND state=?",
                (now, receipt_id, row["position"], row["revision"], row["state"]),
            ).rowcount
            if changed != 1:
                return None
            from .contracts import DeliveryPart

            return DeliveryPart(
                receipt_id, row["position"], context, row["payload"], artifact_ids
            ), row["revision"] + 1

    def finish_part(self, part, revision, settings, state, provider_id, code, now):
        with self.transaction() as db:
            parent = db.execute("SELECT * FROM inbox WHERE id=?", (part.receipt_id,)).fetchone()
            if (
                parent is None
                or parent["epoch"] != settings.epoch
                or parent["revision"] != part.context.revision
            ):
                state, code = "uncertain", "stale_delivery"
            db.execute(
                "INSERT OR IGNORE INTO delivery_attempts VALUES(?,?,?,?,?,?,?)",
                (part.receipt_id, part.position, revision, state, provider_id, code, now),
            )
            changed = db.execute(
                "UPDATE outbox SET state=?,provider_message_id=?,error_code=?,revision=revision+1,updated_ms=? WHERE receipt_id=? AND position=? AND state='sending' AND revision=?",
                (state, provider_id, code, now, part.receipt_id, part.position, revision),
            ).rowcount
            if changed and state != "uncertain":
                db.execute(
                    "DELETE FROM artifact_leases WHERE holder=? AND token=?",
                    (f"delivery-{part.receipt_id}-{part.position}", str(revision)),
                )
            if changed and state in ("failed", "uncertain"):
                db.execute(
                    "UPDATE reminders SET state=?,revision=revision+1 WHERE delivery_receipt_id=?",
                    (state, part.receipt_id),
                )
                db.execute(
                    "UPDATE organization_events SET state=? WHERE delivery_receipt_id=?",
                    (state, part.receipt_id),
                )
            if (
                changed
                and state == "accepted"
                and not db.execute(
                    "SELECT 1 FROM outbox WHERE receipt_id=? AND state!='accepted'",
                    (part.receipt_id,),
                ).fetchone()
            ):
                db.execute(
                    "UPDATE note_views SET accepted=1 WHERE receipt_id=? AND epoch=? AND expires_ms>?",
                    (part.receipt_id, settings.epoch, now),
                )
                db.execute(
                    "UPDATE interactions SET state='active',revision=revision+1 WHERE receipt_id=? AND state='pending_delivery' AND epoch=? AND expires_ms>?",
                    (part.receipt_id, settings.epoch, now),
                )
                db.execute(
                    "UPDATE ai_history SET accepted=1 WHERE receipt_id=? AND epoch=? AND expires_ms>?",
                    (part.receipt_id, settings.epoch, now),
                )
                db.execute(
                    "UPDATE polls SET published_ms=coalesce(published_ms,?) WHERE receipt_id=? AND state='open'",
                    (now, part.receipt_id),
                )
                db.execute(
                    "UPDATE game_views SET accepted_ms=coalesce(accepted_ms,?) WHERE receipt_id=?",
                    (now, part.receipt_id),
                )
                from .domains.happy_hour import delivered

                delivered(db, part.receipt_id, now)
                from .domains.cooperacha import delivered as coop_delivered

                coop_delivered(db, part.receipt_id, now)
                db.execute(
                    "UPDATE roulette_views SET accepted_ms=coalesce(accepted_ms,?) WHERE receipt_id=?",
                    (now, part.receipt_id),
                )
                db.execute(
                    "UPDATE blackjack_games SET deadline_ms=(SELECT min(accepted_ms) FROM game_views WHERE game_id=blackjack_games.id AND revision=blackjack_games.revision)+CASE WHEN state='lobby' THEN 35000 WHEN mode='individual' THEN 60000 ELSE 30000 END WHERE id IN (SELECT game_id FROM game_views WHERE receipt_id=? AND revision=blackjack_games.revision) AND state IN ('lobby','playing')",
                    (part.receipt_id,),
                )
                db.execute(
                    "UPDATE reminders SET state='sent',revision=revision+1 WHERE delivery_receipt_id=?",
                    (part.receipt_id,),
                )
                db.execute(
                    "UPDATE organization_events SET state='accepted' WHERE delivery_receipt_id=?",
                    (part.receipt_id,),
                )
            return bool(changed)

    def recover_deliveries(self, settings, now):
        # Invocar solo al recuperar la propiedad exclusiva del proceso.
        with self.transaction() as db:
            return db.execute(
                "UPDATE outbox SET state='uncertain',error_code='interrupted_delivery',revision=revision+1,updated_ms=? WHERE state='sending' AND receipt_id IN (SELECT id FROM inbox WHERE instance=? AND account=?)",
                (now, settings.instance, settings.account),
            ).rowcount

    def prune_context(self, settings, now):
        with self.transaction() as db:
            db.execute(
                "DELETE FROM ai_history WHERE instance=? AND account=? AND expires_ms<=?",
                (settings.instance, settings.account, now),
            )
            db.execute(
                "UPDATE inbox SET text='' WHERE instance=? AND account=? AND received_ms<? AND state!='queued'",
                (settings.instance, settings.account, now - 86400000),
            )
