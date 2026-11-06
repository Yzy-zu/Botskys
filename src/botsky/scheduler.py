"""Scheduler local optativo: reserva avisos en outbox, nunca envía dentro de SQLite."""

import hashlib
from datetime import datetime, time
from uuid import uuid4

from . import access
from .contracts import CommandContext, Result, Scope, canonical
from .domains.bot import current
from .domains.organization import CHAT_SQL, ZONE, chat_key


class Scheduler:
    def __init__(self, app):
        self.app = app

    def allowed(self, db, row, now):
        context = CommandContext(
            "",
            row["instance"],
            row["account"],
            Scope(row["actor"], row["chat"], bool(row["is_group"])),
            row["epoch"],
            0,
        )
        if access.authorize("friend", context, self.app.settings):
            return False
        mode = current(db, context)
        return mode["mode"] != "apagado" and mode["paused_until_ms"] <= now

    def emit(self, db, row, kind, event_key, text, now):
        identifier = hashlib.sha256(canonical(["internal", event_key]).encode()).hexdigest()[:32]
        result = Result("ok", kind + "_notice", text)
        context = CommandContext(
            identifier,
            row["instance"],
            row["account"],
            Scope(row["actor"], row["chat"], bool(row["is_group"])),
            row["epoch"],
            0,
        )
        command = canonical(
            {
                "version": 1,
                "operation": "scheduler." + kind,
                "arguments": {"source_receipt_id": row["receipt_id"], "event_key": event_key},
            }
        )
        db.execute(
            "INSERT INTO inbox(id,instance,account,message_id,actor,chat,is_group,epoch,source_ms,received_ms,fingerprint,command_json,path_json,permission,state,result_json,origin,source_receipt_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'[]','friend','completed',?,'internal',?)",
            (
                identifier,
                *context.scope_key[:2],
                "internal-" + uuid4().hex,
                context.scope.actor,
                context.scope.chat,
                int(context.scope.is_group),
                context.epoch,
                now,
                now,
                hashlib.sha256(command.encode()).hexdigest(),
                command,
                result.to_json(),
                row["receipt_id"],
            ),
        )
        effect = hashlib.sha256(("effect-" + identifier).encode()).hexdigest()
        db.execute(
            "INSERT INTO effects VALUES(?,?,?,?,?,?)",
            (effect, identifier, "scheduler." + kind, command, result.to_json(), now),
        )
        self.app.store.enqueue(db, context, result, now)
        return identifier

    def tick(self, *, limit=20):
        now = self.app.clock()
        settings = self.app.settings
        emitted = []
        with self.app.store.transaction() as db:
            db.execute(
                "UPDATE reminders SET state='expired',revision=revision+1 WHERE instance=? AND account=? AND epoch=? AND state='pending' AND due_ms<?",
                (settings.instance, settings.account, settings.epoch, now - 600000),
            )
            rows = db.execute(
                "SELECT * FROM reminders WHERE instance=? AND account=? AND epoch=? AND state='pending' AND due_ms<=? ORDER BY due_ms,id LIMIT ?",
                (settings.instance, settings.account, settings.epoch, now, limit),
            ).fetchall()
            for row in rows:
                if not self.allowed(db, row, now):
                    continue
                key = canonical(
                    ["reminder", row["instance"], row["account"], row["epoch"], row["id"]]
                )
                if db.execute(
                    "SELECT 1 FROM organization_events WHERE event_key=?", (key,)
                ).fetchone():
                    continue
                identifier = self.emit(
                    db,
                    row,
                    "reminder",
                    key,
                    f"Recordatorio {row['id']}: "
                    + row["text"]
                    + (" (con retraso)" if now - row["due_ms"] > 1000 else ""),
                    now,
                )
                db.execute(
                    "INSERT INTO organization_events VALUES(?,?,?,?,'emitted',?,?)",
                    (key, "reminder", str(row["id"]), identifier, now, row["due_ms"] + 600000),
                )
                db.execute(
                    "UPDATE reminders SET state='emitted',delivery_receipt_id=?,revision=revision+1 WHERE id=? AND state='pending'",
                    (identifier, row["id"]),
                )
                emitted.append(identifier)
            local = datetime.fromtimestamp(now / 1000, ZONE)
            for row in db.execute(
                "SELECT * FROM school_digests WHERE instance=? AND account=? AND epoch=? AND enabled=1",
                (settings.instance, settings.account, settings.epoch),
            ).fetchall():
                if len(emitted) >= limit:
                    break
                if (
                    not self.allowed(db, row, now)
                    or row["actor"] != settings.owner
                    or not row["is_group"]
                ):
                    continue
                day = local.date().isoformat()
                at = datetime.combine(local.date(), time.fromisoformat(row["digest_time"]), ZONE)
                delay = (local - at).total_seconds()
                if delay < 0:
                    continue
                context = CommandContext(
                    "",
                    row["instance"],
                    row["account"],
                    Scope(row["actor"], row["chat"], True),
                    row["epoch"],
                    0,
                )
                key = canonical(["digest", chat_key(context), day])
                if db.execute(
                    "SELECT 1 FROM organization_events WHERE event_key=?", (key,)
                ).fetchone():
                    continue
                target = canonical(chat_key(context))
                if delay > 600:
                    db.execute(
                        "INSERT INTO organization_events VALUES(?,?,?,NULL,'expired',?,?)",
                        (key, "digest", target, now, int(at.timestamp() * 1000) + 600000),
                    )
                    continue
                lessons = db.execute(
                    "SELECT * FROM school_lessons WHERE "
                    + CHAT_SQL
                    + " AND weekday=? ORDER BY start_time",
                    (*chat_key(context), local.isoweekday()),
                ).fetchall()
                tasks = db.execute(
                    "SELECT * FROM school_tasks WHERE "
                    + CHAT_SQL
                    + " AND due_date=? AND state='pending' ORDER BY due_time,id LIMIT 20",
                    (*chat_key(context), day),
                ).fetchall()
                lines = ["Resumen escolar · " + day + " · Ciudad de México", "Clases:"]
                lines += [
                    r["start_time"] + "–" + r["end_time"] + " " + r["subject"] for r in lessons
                ] or ["Sin clases guardadas."]
                lines += (
                    ["Entregas de hoy:"] + [f"{r['id']}: " + r["text"] for r in tasks]
                    if tasks
                    else ["Sin tareas pendientes para hoy."]
                )
                identifier = self.emit(db, row, "digest", key, "\n".join(lines)[:6000], now)
                db.execute(
                    "INSERT INTO organization_events VALUES(?,?,?,?,'emitted',?,?)",
                    (key, "digest", target, identifier, now, int(at.timestamp() * 1000) + 600000),
                )
                emitted.append(identifier)
        return emitted
