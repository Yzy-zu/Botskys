"""Índice de citas hacia recibos propios; una parte no publica el conjunto."""

from ..domains.notes import SCOPE_SQL


def own_delivered_parent(db, context, message_id, now, *, ttl_ms=86400000):
    rows = db.execute(
        "SELECT DISTINCT i.* FROM inbox i JOIN outbox o ON o.receipt_id=i.id "
        "WHERE o.provider_message_id=? AND o.state='accepted' AND "
        + " AND ".join("i." + term for term in SCOPE_SQL.split(" AND "))
        + " AND i.received_ms>? AND i.state='completed' "
        "AND NOT EXISTS(SELECT 1 FROM outbox p WHERE p.receipt_id=i.id AND p.state!='accepted') LIMIT 2",
        (message_id, *context.scope_key, now - ttl_ms),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None
