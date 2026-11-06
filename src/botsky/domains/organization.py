"""Organización explícita: estado propio y compartido solo por capacidad declarada."""

import json
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..artifacts import ArtifactProblem
from ..contracts import Result, canonical
from .notes import SCOPE_SQL

ZONE = ZoneInfo("America/Mexico_City")
CHAT_SQL = "instance=? AND account=? AND chat=? AND is_group=? AND epoch=?"


def chat_key(context):
    return (
        context.instance,
        context.account,
        context.scope.chat,
        int(context.scope.is_group),
        context.epoch,
    )


def shared_where(context):
    return (
        (CHAT_SQL, chat_key(context)) if context.scope.is_group else (SCOPE_SQL, context.scope_key)
    )


def future_ms(day, clock, now, *, date_only=False):
    try:
        local_date = date.fromisoformat(day)
        if date_only:
            if local_date <= datetime.fromtimestamp(now / 1000, ZONE).date():
                raise ValueError
            if local_date > datetime.fromtimestamp(now / 1000, ZONE).date() + timedelta(days=366):
                raise ValueError
            return None
        naive = datetime.combine(local_date, time.fromisoformat(clock))
        a, b = naive.replace(tzinfo=ZONE, fold=0), naive.replace(tzinfo=ZONE, fold=1)
        if (
            a.utcoffset() != b.utcoffset()
            or a.astimezone(UTC).astimezone(ZONE).replace(tzinfo=None) != naive
        ):
            raise ValueError
        value = int(a.timestamp() * 1000)
        if not now < value <= now + 366 * 86400000:
            raise ValueError
        return value
    except ValueError, TypeError, OverflowError:
        raise ValueError(
            "Indica una fecha completa futura, no ambigua, hasta un año; hora de Ciudad de México."
        ) from None


def paginate(db, table, where, params, page, *, order="id"):
    total = db.execute(f"SELECT count(*) FROM {table} WHERE " + where, params).fetchone()[0]
    pages = max(1, (total + 19) // 20)
    if page > pages:
        return Result("needs_input", "page_out_of_range", f"Página fuera de rango: 1–{pages}.")
    rows = [
        dict(r)
        for r in db.execute(
            f"SELECT * FROM {table} WHERE " + where + f" ORDER BY {order} LIMIT 20 OFFSET ?",
            (*params, (page - 1) * 20),
        )
    ]
    return Result(
        "ok" if rows else "empty",
        "organization_list",
        "\n".join(f"{r['id']}: {r.get('text', r.get('subject', ''))}" for r in rows)
        or "Sin registros.",
        {"items": rows, "page": page, "pages": pages, "total": total},
    )


def memory(db, context, action, args, now):
    if action == "remember":
        if (
            db.execute(
                "SELECT count(*) FROM memories WHERE " + SCOPE_SQL, context.scope_key
            ).fetchone()[0]
            >= 100
        ):
            return Result(
                "failed", "memory_limit", "Tienes 100 recuerdos en este ámbito; elimina alguno."
            )
        if "@s.whatsapp.net" in args["text"] or "@lid" in args["text"]:
            return Result(
                "failed",
                "memory_private_identifier",
                "No guardo identificadores internos como recuerdos.",
            )
        cur = db.execute(
            "INSERT INTO memories(instance,account,actor,chat,is_group,epoch,kind,text,receipt_id,created_ms,updated_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (*context.scope_key, args["kind"], args["text"], context.receipt_id, now, now),
        )
        return Result(
            "ok",
            "memory_saved",
            f"Recuerdo {cur.lastrowid} guardado como {args['kind']}.",
            {"memory_id": cur.lastrowid},
        )
    if action == "list":
        where, params = SCOPE_SQL, list(context.scope_key)
        if args.get("kind"):
            where += " AND kind=?"
            params.append(args["kind"])
        return paginate(db, "memories", where, params, args["page"])
    if action == "forget_all":
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT id,revision FROM memories WHERE " + SCOPE_SQL + " ORDER BY id",
                context.scope_key,
            )
        ]
        if not rows:
            return Result("empty", "memory_empty", "No hay recuerdos que borrar.")
        identifier = uuid4().hex
        db.execute(
            "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,'{}','[]',?,'pending_delivery',?)",
            (
                identifier,
                context.receipt_id,
                *context.scope_key,
                "memory_forget_all",
                canonical({"rows": rows}),
                now + 900000,
            ),
        )
        return Result(
            "needs_input",
            "memory_delete_preview",
            f"Borraré {len(rows)} recuerdos de este ámbito.\n/confirmar {identifier}",
            {"confirmation_id": identifier},
        )
    row = db.execute(
        "SELECT * FROM memories WHERE id=? AND " + SCOPE_SQL,
        (args["memory_id"], *context.scope_key),
    ).fetchone()
    if not row:
        return Result(
            "empty", "memory_not_found", "No hay un recuerdo propio con ese ID en este chat."
        )
    if action == "correct":
        if "@s.whatsapp.net" in args["text"] or "@lid" in args["text"]:
            return Result(
                "failed", "memory_private_identifier", "No guardo identificadores internos."
            )
        db.execute(
            "UPDATE memories SET text=?,revision=revision+1,updated_ms=? WHERE id=? AND revision=?",
            (args["text"], now, row["id"], row["revision"]),
        )
    else:
        db.execute("DELETE FROM memories WHERE id=? AND revision=?", (row["id"], row["revision"]))
    return Result(
        "ok",
        "memory_corrected" if action == "correct" else "memory_forgotten",
        "Recuerdo corregido." if action == "correct" else "Recuerdo olvidado.",
    )


def confirm_memory(db, context, view, now):
    expected = json.loads(view["data_json"])["rows"]
    actual = [
        dict(r)
        for r in db.execute(
            "SELECT id,revision FROM memories WHERE " + SCOPE_SQL + " ORDER BY id",
            context.scope_key,
        )
    ]
    if actual != expected:
        return Result(
            "needs_input",
            "confirmation_stale",
            "Los recuerdos cambiaron; solicita otra vista previa.",
        )
    db.execute(
        "UPDATE interactions SET state='consumed',revision=revision+1 WHERE id=? AND state='active' AND revision=?",
        (view["id"], view["revision"]),
    )
    db.execute("DELETE FROM memories WHERE " + SCOPE_SQL, context.scope_key)
    return Result(
        "ok", "memories_deleted", "Recuerdos del ámbito borrados.", {"count": len(actual)}
    )


def withdraw(db, receipt_id):
    if not receipt_id:
        return
    db.execute(
        "UPDATE outbox SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state='pending'",
        (receipt_id,),
    )
    db.execute("UPDATE inbox SET revision=revision+1 WHERE id=?", (receipt_id,))


def reminder(db, context, action, args, now):
    if action == "create":
        incoming = db.execute(
            "SELECT received_ms FROM inbox WHERE id=?", (context.receipt_id,)
        ).fetchone()
        if "duration_seconds" in args:
            due = incoming["received_ms"] + args["duration_seconds"] * 1000
        else:
            try:
                due = future_ms(args["date"], args["time"], now)
            except ValueError as exc:
                return Result("needs_input", "invalid_reminder_date", str(exc))
        if not now < due <= now + 366 * 86400000:
            return Result(
                "needs_input",
                "invalid_reminder_date",
                "El recordatorio debe ser futuro y estar dentro de un año.",
            )
        if (
            db.execute(
                "SELECT count(*) FROM reminders WHERE " + SCOPE_SQL + " AND state='pending'",
                context.scope_key,
            ).fetchone()[0]
            >= 100
        ):
            return Result(
                "failed", "reminder_limit", "Tienes 100 recordatorios pendientes en este ámbito."
            )
        cur = db.execute(
            "INSERT INTO reminders(instance,account,actor,chat,is_group,epoch,text,due_ms,receipt_id,created_ms) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (*context.scope_key, args["text"], due, context.receipt_id, now),
        )
        shown = datetime.fromtimestamp(due / 1000, ZONE).strftime("%Y-%m-%d %H:%M:%S")
        return Result(
            "ok",
            "reminder_created",
            f"Recordatorio {cur.lastrowid}: {args['text']}\n{shown} · Ciudad de México. Aviso local pendiente; no hay WhatsApp activado.",
            {"reminder_id": cur.lastrowid, "due_ms": due},
        )
    if action == "list":
        return paginate(
            db,
            "reminders",
            SCOPE_SQL
            + (
                ""
                if args["include_closed"]
                else " AND state IN ('pending','emitted','expired','uncertain','failed')"
            ),
            context.scope_key,
            args["page"],
            order="due_ms,id",
        )
    row = db.execute(
        "SELECT * FROM reminders WHERE id=? AND " + SCOPE_SQL,
        (args["reminder_id"], *context.scope_key),
    ).fetchone()
    if not row:
        return Result(
            "empty", "reminder_not_found", "No hay un recordatorio propio con ese ID en este chat."
        )
    if action == "archive" and row["state"] == "pending":
        return Result(
            "needs_input", "reminder_still_pending", "Cancela el recordatorio antes de archivarlo."
        )
    if action == "cancel" and row["delivery_receipt_id"]:
        states = {
            r[0]
            for r in db.execute(
                "SELECT state FROM outbox WHERE receipt_id=?", (row["delivery_receipt_id"],)
            )
        }
        if "accepted" in states:
            return Result(
                "empty",
                "reminder_already_sent",
                "El recordatorio ya fue entregado al transporte; no se deshace.",
            )
        if states & {"sending", "uncertain"}:
            return Result(
                "uncertain",
                "reminder_delivery_uncertain",
                "El envío ya empezó o quedó incierto. No lo repetiré.",
            )
        withdraw(db, row["delivery_receipt_id"])
    state = "archived" if action == "archive" else "cancelled"
    db.execute(
        "UPDATE reminders SET state=?,revision=revision+1 WHERE id=? AND revision=?",
        (state, row["id"], row["revision"]),
    )
    return Result("ok", "reminder_" + state, "Recordatorio " + state + ".")


def poll(db, context, action, args, now, owner):
    if action == "create":
        normalized = [unicodedata.normalize("NFKC", s.strip()).casefold() for s in args["options"]]
        if len(set(normalized)) != len(normalized):
            return Result(
                "needs_input", "poll_duplicate_options", "Las opciones deben ser distintas."
            )
        cur = db.execute(
            "INSERT INTO polls(instance,account,actor,chat,is_group,epoch,question,options_json,receipt_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (*context.scope_key, args["question"], canonical(args["options"]), context.receipt_id),
        )
        identifier = cur.lastrowid
        lines = [f"Encuesta {identifier}: " + args["question"]]
        for i, value in enumerate(args["options"], 1):
            lines.extend([f"{i}. {value}", f"/encuesta votar {identifier} {i}"])
        return Result(
            "ok",
            "poll_created",
            "\n".join(lines),
            {"poll_id": identifier, "options": list(args["options"])},
        )
    where, params = shared_where(context)
    row = db.execute(
        "SELECT * FROM polls WHERE id=? AND " + where, (args["poll_id"], *params)
    ).fetchone()
    if not row:
        return Result("empty", "poll_not_found", "No hay una encuesta con ese ID en este ámbito.")
    if row["published_ms"] is None:
        return Result(
            "needs_input", "poll_not_published", "La encuesta aún no tiene publicación aceptada."
        )
    incoming = db.execute(
        "SELECT source_ms,rowid AS sequence FROM inbox WHERE id=?", (context.receipt_id,)
    ).fetchone()
    if incoming["source_ms"] < row["published_ms"]:
        return Result(
            "needs_input",
            "poll_event_before_publication",
            "El mensaje es anterior a la publicación. Envía una elección nueva.",
        )
    options = json.loads(row["options_json"])
    if action == "close":
        if context.scope.actor not in (row["actor"], owner):
            return Result(
                "failed",
                "poll_author_required",
                "Solo el creador o el dueño puede cerrar esta encuesta.",
            )
        db.execute("UPDATE polls SET state='closed',revision=revision+1 WHERE id=?", (row["id"],))
    if action == "vote":
        if row["state"] != "open":
            return Result("needs_input", "poll_closed", "La encuesta ya está cerrada.")
        if args["choice"] > len(options):
            return Result(
                "needs_input",
                "poll_invalid_choice",
                "Elige una opción que aparezca en esa encuesta.",
            )
        db.execute(
            "INSERT INTO poll_votes VALUES(?,?,?,?,?,?) ON CONFLICT(poll_id,actor) DO UPDATE SET choice=excluded.choice,source_ms=excluded.source_ms,sequence=excluded.sequence,receipt_id=excluded.receipt_id WHERE poll_votes.source_ms<excluded.source_ms OR (poll_votes.source_ms=excluded.source_ms AND poll_votes.sequence<=excluded.sequence)",
            (
                row["id"],
                context.scope.actor,
                args["choice"],
                incoming["source_ms"],
                incoming["sequence"],
                context.receipt_id,
            ),
        )
    counts = {
        r["choice"]: r["n"]
        for r in db.execute(
            "SELECT choice,count(*) AS n FROM poll_votes WHERE poll_id=? GROUP BY choice",
            (row["id"],),
        )
    }
    results = [
        {"choice": i, "text": value, "votes": counts.get(i, 0)}
        for i, value in enumerate(options, 1)
    ]
    return Result(
        "ok",
        "poll_results",
        "\n".join(
            [row["question"], *[f"{r['choice']}. {r['text']}: {r['votes']}" for r in results]]
        ),
        {"poll_id": row["id"], "options": results, "participants": sum(counts.values())},
    )


def school(db, context, spec, command, now, app):
    action = spec.original_action
    args = command["arguments"]
    where, params = shared_where(context)
    if (
        action in ("set_lesson", "delete_lesson", "configure_digest")
        and context.scope.actor != app.settings.owner
    ):
        return Result(
            "failed", "owner_required", "Solo el dueño cambia horarios y resúmenes automáticos."
        )
    if action == "add_task":
        try:
            future_ms(
                args["due_date"], args.get("due_time"), now, date_only=not args.get("due_time")
            )
        except ValueError as exc:
            return Result("needs_input", "invalid_task_date", str(exc))
        if (
            db.execute(
                "SELECT count(*) FROM school_tasks WHERE " + where + " AND state='pending'", params
            ).fetchone()[0]
            >= 100
        ):
            return Result(
                "failed", "school_task_limit", "Hay 100 tareas pendientes en este ámbito."
            )
        artifact_id = None
        if args.get("attach"):
            row = db.execute("SELECT * FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
            try:
                inputs = app.artifacts.resolve(db, context, row, now)
                if not inputs:
                    from .. import interactions

                    return interactions.wait_file(db, context, spec, command, now)
                if len(inputs) != 1:
                    return Result(
                        "needs_input",
                        "one_attachment_required",
                        "La tarea requiere un solo archivo.",
                    )
                artifact = app.artifacts.owned(db, inputs[0], context, now)
                if artifact["size"] > 10 * 1024 * 1024 or artifact["format"] in (
                    "mp4",
                    "webm",
                    "ogg",
                    "mp3",
                    "wav",
                    "flac",
                    "aac",
                ):
                    return Result(
                        "failed",
                        "school_attachment_limit",
                        "Adjunta imagen/documento de hasta 10 MiB.",
                    )
                used = db.execute(
                    "SELECT coalesce(sum(a.size),0) FROM school_tasks t JOIN artifacts a ON t.artifact_id=a.id WHERE t.instance=? AND t.account=? AND t.chat=? AND t.is_group=? AND t.epoch=? AND t.state!='deleted'",
                    chat_key(context),
                ).fetchone()[0]
                if used + artifact["size"] > 32 * 1024 * 1024:
                    return Result(
                        "failed",
                        "school_assets_full",
                        "El ámbito alcanzó 32 MiB de archivos escolares.",
                    )
                artifact_id = inputs[0]
            except ArtifactProblem as exc:
                return Result("failed", exc.code, "No puedo usar ese archivo para la tarea.")
        cur = db.execute(
            "INSERT INTO school_tasks(instance,account,actor,chat,is_group,epoch,text,subject,due_date,due_time,artifact_id,receipt_id,created_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                *context.scope_key,
                args["text"],
                args.get("subject", ""),
                args["due_date"],
                args.get("due_time"),
                artifact_id,
                context.receipt_id,
                now,
            ),
        )
        if artifact_id:
            expires = now + 396 * 86400000
            app.artifacts.lease(
                db, [artifact_id], context, "school-" + str(cur.lastrowid), "1", expires, now
            )
            if context.scope.is_group:
                db.execute(
                    "INSERT INTO school_asset_grants VALUES(?,?,?,?,?,?,?,?)",
                    (cur.lastrowid, artifact_id, *chat_key(context), expires),
                )
        return Result(
            "ok",
            "school_task_created",
            f"Tarea {cur.lastrowid} guardada para {args['due_date']}"
            + (" " + args["due_time"] if args.get("due_time") else " (sin hora definida)."),
            {"task_id": cur.lastrowid},
        )
    if action == "list_tasks":
        return paginate(
            db,
            "school_tasks",
            where + (" AND state!='deleted'" if args["include_closed"] else " AND state='pending'"),
            params,
            args["page"],
            order="due_date,id",
        )
    if action in ("complete_task", "delete_task", "get_attachment"):
        own = action != "get_attachment"
        sql, values = (SCOPE_SQL, context.scope_key) if own else (where, params)
        row = db.execute(
            "SELECT * FROM school_tasks WHERE id=? AND " + sql + " AND state!='deleted'",
            (args["task_id"], *values),
        ).fetchone()
        if not row:
            return Result("empty", "task_not_found", "No hay una tarea admisible con ese ID.")
        if action == "get_attachment":
            if not row["artifact_id"]:
                return Result("empty", "task_no_attachment", "La tarea no tiene archivo.")
            try:
                app.artifacts.owned(
                    db, row["artifact_id"], context, now, holder="school-" + str(row["id"])
                )
            except ArtifactProblem as exc:
                return Result("failed", exc.code, "El archivo ya no está disponible.")
            return Result(
                "ok", "task_attachment", "Archivo de la tarea.", {"artifacts": [row["artifact_id"]]}
            )
        state = "completed" if action == "complete_task" else "deleted"
        db.execute(
            "UPDATE school_tasks SET state=?,revision=revision+1 WHERE id=?", (state, row["id"])
        )
        if state == "deleted":
            db.execute("DELETE FROM school_asset_grants WHERE task_id=?", (row["id"],))
            db.execute("DELETE FROM artifact_leases WHERE holder=?", ("school-" + str(row["id"]),))
        return Result("ok", "school_task_" + state, "Tarea " + state + ".")
    if action == "set_lesson":
        if (
            db.execute("SELECT count(*) FROM school_lessons WHERE " + where, params).fetchone()[0]
            >= 100
        ):
            return Result("failed", "school_lesson_limit", "Hay 100 clases en este ámbito.")
        if db.execute(
            "SELECT 1 FROM school_lessons WHERE "
            + where
            + " AND weekday=? AND start_time<? AND end_time>?",
            (*params, args["weekday"], args["end_time"], args["start_time"]),
        ).fetchone():
            return Result(
                "needs_input", "school_lesson_overlap", "Ese horario se cruza con otra clase."
            )
        cur = db.execute(
            "INSERT INTO school_lessons(instance,account,actor,chat,is_group,epoch,subject,weekday,start_time,end_time) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                *context.scope_key,
                args["subject"],
                args["weekday"],
                args["start_time"],
                args["end_time"],
            ),
        )
        return Result(
            "ok",
            "school_lesson_created",
            f"Clase {cur.lastrowid} guardada.",
            {"lesson_id": cur.lastrowid},
        )
    if action == "list_schedule":
        if args.get("weekday"):
            where += " AND weekday=?"
            params = (*params, args["weekday"])
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM school_lessons WHERE " + where + " ORDER BY weekday,start_time",
                params,
            )
        ]
        return Result(
            "ok" if rows else "empty",
            "school_schedule",
            "\n".join(
                f"{r['id']}: día {r['weekday']} {r['start_time']}–{r['end_time']} {r['subject']}"
                for r in rows
            )
            or "Sin clases.",
            {"items": rows},
        )
    if action == "delete_lesson":
        changed = db.execute(
            "DELETE FROM school_lessons WHERE id=? AND " + where, (args["lesson_id"], *params)
        ).rowcount
        return Result(
            "ok" if changed else "empty",
            "school_lesson_deleted" if changed else "lesson_not_found",
            "Clase eliminada." if changed else "No hay una clase con ese ID.",
        )
    if action == "configure_digest":
        if not context.scope.is_group:
            return Result(
                "failed",
                "digest_group_required",
                "El resumen automático se configura en grupos habilitados.",
            )
        clock = args.get("digest_time", "")
        db.execute(
            "INSERT INTO school_digests VALUES(?,?,?,?,?,?,?,?,1,?) ON CONFLICT(instance,account,chat,is_group,epoch) DO UPDATE SET actor=excluded.actor,enabled=excluded.enabled,digest_time=excluded.digest_time,revision=school_digests.revision+1,receipt_id=excluded.receipt_id",
            (*context.scope_key, int(args["enabled"]), clock, context.receipt_id),
        )
        # Desactivar/reconfigurar retira los resúmenes pendientes de la revisión anterior.
        for row in db.execute(
            "SELECT delivery_receipt_id FROM organization_events WHERE kind='digest' AND target=? AND state='emitted'",
            (canonical(chat_key(context)),),
        ).fetchall():
            withdraw(db, row["delivery_receipt_id"])
    settings = db.execute(
        "SELECT enabled,digest_time,revision FROM school_digests WHERE " + CHAT_SQL,
        chat_key(context),
    ).fetchone()
    return Result(
        "ok",
        "school_digest_status",
        ("Resumen activo a las " + settings["digest_time"] + " · Ciudad de México.")
        if settings and settings["enabled"]
        else "Resumen desactivado.",
        dict(settings) if settings else {"enabled": False},
    )


def execute(db, context, spec, command, now, app):
    args = command["arguments"]
    action = spec.original_action
    if spec.family == "manage_memory":
        return memory(db, context, action, args, now)
    if spec.family == "manage_reminder":
        return reminder(db, context, action, args, now)
    if spec.family == "manage_poll":
        return poll(db, context, action, args, now, app.settings.owner)
    return school(db, context, spec, command, now, app)
