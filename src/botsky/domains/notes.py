"""Notas explícitas, consulta literal y paginación ligada a entrega propia."""

from uuid import uuid4

from ..contracts import Result

SCOPE_SQL = "instance=? AND account=? AND actor=? AND chat=? AND is_group=? AND epoch=?"
PAGE_SIZE = 5
VIEW_TTL_MS = 900000


def save(db, context, args, effect_id, now):
    text = args["text"]
    cursor = db.execute(
        "INSERT INTO notes(instance,account,actor,chat,is_group,epoch,text,search_text,created_ms,effect_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (*context.scope_key, text, text.casefold(), now, effect_id),
    )
    return Result(
        "ok", "note_saved", f"Nota {cursor.lastrowid} guardada.", {"note_id": cursor.lastrowid}
    )


def find(db, context, args, now):
    page = args["page"]
    query = args.get("query")
    if query is None and page == 1:
        query = ""
    elif query is None:
        incoming = db.execute(
            "SELECT quoted_message_id FROM inbox WHERE id=?", (context.receipt_id,)
        ).fetchone()
        quoted = incoming["quoted_message_id"] if incoming else None
        if quoted:
            from ..presentation.quotes import own_delivered_parent

            parent = own_delivered_parent(db, context, quoted, now)
            view = (
                db.execute(
                    f"SELECT query FROM note_views WHERE receipt_id=? AND {SCOPE_SQL} AND accepted=1 AND expires_ms>? ORDER BY rowid DESC LIMIT 1",
                    (parent["id"], *context.scope_key, now),
                ).fetchone()
                if parent is not None
                else None
            )
        else:
            view = db.execute(
                f"SELECT query FROM note_views WHERE {SCOPE_SQL} AND accepted=1 AND expires_ms>? ORDER BY rowid DESC LIMIT 1",
                (*context.scope_key, now),
            ).fetchone()
        if view is None:
            return Result(
                "needs_input",
                "note_filter_required",
                "Falta una búsqueda propia entregada y vigente. Usa /notas --pagina N TEXTO.",
            )
        query = view["query"]
    where = SCOPE_SQL + " AND instr(search_text,?)>0"
    params = (*context.scope_key, query.casefold())
    total = db.execute("SELECT count(*) FROM notes WHERE " + where, params).fetchone()[0]
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    data = {"query": query, "page": page, "pages": pages, "total": total, "items": []}
    if page > pages:
        return Result(
            "needs_input", "note_page_out_of_range", f"Página fuera de rango: 1–{pages}.", data
        )
    rows = db.execute(
        "SELECT id,text,created_ms FROM notes WHERE " + where + " ORDER BY id LIMIT ? OFFSET ?",
        (*params, PAGE_SIZE, (page - 1) * PAGE_SIZE),
    ).fetchall()
    data["items"] = [dict(row) for row in rows]
    view_id = uuid4().hex
    db.execute(
        "INSERT INTO note_views VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (view_id, context.receipt_id, *context.scope_key, query, 0, now + VIEW_TTL_MS),
    )
    data["view_id"] = view_id
    lines = [f"Notas: {total}. Página {page}/{pages}."]
    lines += [f"{row['id']}: {row['text']}" for row in rows]
    if not rows:
        lines.append("Sin coincidencias.")
    if page < pages:
        lines.append(f"/notas --pagina {page + 1}")
    return Result(
        "ok" if total else "empty",
        "notes_found" if total else "notes_empty",
        "\n".join(lines),
        data,
    )
