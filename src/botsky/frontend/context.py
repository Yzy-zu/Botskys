"""Contexto propio acotado por actor/chat/época; solo referencias entregadas."""
import json
from uuid import uuid4

from botsky.contracts import canonical
from botsky.domains.notes import SCOPE_SQL
from botsky.presentation.quotes import own_delivered_parent
from botsky.store import context_of
from .contracts import ClarifyDecision

TTL = 900000
CONFIRMATIONS = {
    'message_preview': ('recado.enviar', 'draft_id'),
    'nuclear': ('admin.nuclear-confirmar', 'draft_id'),
    'pack_offer': ('pack.confirmar', 'purchase_id'),
    'memory_forget_all': ('confirmar', 'id'),
    'delivery_retry': ('confirmar', 'id'),
}


def load(app, db, row, now):
    context = context_of(row)
    parent = own_delivered_parent(db, context, row['quoted_message_id'], now) if row['quoted_message_id'] else None
    rows = db.execute(f"SELECT * FROM interactions WHERE {SCOPE_SQL} AND state='active' AND expires_ms>? ORDER BY rowid DESC LIMIT 12", (*context.scope_key, now)).fetchall()
    if row['quoted_message_id']:
        rows = [v for v in rows if parent and v['receipt_id'] == parent['id']]
    drafts = [v for v in rows if v['kind'] == 'frontend_draft']
    draft = drafts[0] if len(drafts) == 1 else None
    references = []
    for view in rows:
        kind = view['kind']
        data = json.loads(view['data_json'])
        if kind in ('download', 'drive'):
            references.append({'kind': kind, 'view_id': view['id'],
                               'choices': [{'number': n, 'title': str(c.get('title', c.get('name', '')))[:300]}
                                           for n, c in enumerate(data.get('choices', [])[:10], 1)],
                               'actions': ['dl.elegir', 'dl.detalle'] if kind == 'download' else ['drive.elegir']})
        elif kind in CONFIRMATIONS:
            action, field = CONFIRMATIONS[kind]
            references.append({'kind': kind, 'action_key': action, 'arguments': {field: view['id']}})
    turns = db.execute(
        "SELECT i.text,f.decision_json FROM inbox i JOIN frontend_tasks f ON f.receipt_id=i.id WHERE "
        + " AND ".join("i." + term for term in SCOPE_SQL.split(" AND "))
        + " AND f.state='completed' AND i.received_ms>? AND i.id<>? "
        "AND NOT EXISTS(SELECT 1 FROM outbox o WHERE o.receipt_id=i.id AND o.state!='accepted') "
        "ORDER BY i.received_ms DESC,i.rowid DESC LIMIT 4",
        (*context.scope_key, now-TTL, row['id'])).fetchall()
    conversation = []
    for turn in reversed(turns):
        decision = json.loads(turn['decision_json'] or '{}')
        answer = decision.get('text') or decision.get('question')
        if answer:
            conversation.append({'user': turn['text'][:800], 'frontend': answer[:800]})
    pages = db.execute(
        "SELECT i.id,i.path_json,i.command_json,i.result_json FROM inbox i WHERE "
        + " AND ".join("i." + term for term in SCOPE_SQL.split(" AND "))
        + " AND i.state='completed' AND i.received_ms>? AND i.id<>? "
        "AND EXISTS(SELECT 1 FROM outbox o WHERE o.receipt_id=i.id AND o.state='accepted') "
        "AND NOT EXISTS(SELECT 1 FROM outbox o WHERE o.receipt_id=i.id AND o.state!='accepted') "
        "ORDER BY i.received_ms DESC,i.rowid DESC LIMIT 6", (*context.scope_key, now-TTL, row['id'])).fetchall()
    for page in pages:
        result_data = json.loads(page['result_json'] or '{}').get('data', {})
        if result_data.get('pages', 0) > result_data.get('page', 1) and page['command_json']:
            command = json.loads(page['command_json'])
            arguments = command.get('arguments', {})
            # Only list filters and page references, not domain result content.
            arguments = {k:v for k,v in arguments.items() if k in ('query','page','category','kind','state','include_closed')}
            arguments['page'] = result_data.get('page', 1)+1
            references.append({'kind': 'pagination', 'action_key': '.'.join(json.loads(page['path_json'])), 'arguments': arguments})
    result = {'conversation': conversation, 'references': references, 'quoted_reference_unavailable': bool(row['quoted_message_id'] and not parent)}
    if draft:
        result['draft'] = json.loads(draft['data_json'])
    return result, draft


def save_draft(app, db, row, decision, now):
    if not isinstance(decision, ClarifyDecision):
        return
    context = context_of(row)
    if decision.action_key is not None:
        spec = app.frontend.catalog.specs.get(decision.action_key)
        if spec is None:
            raise ValueError('unknown_draft_action')
        from .catalog import native_fields, scalar
        fields = {f.name: f for f in native_fields(spec)}
        if set(decision.partial_arguments) - set(fields):
            raise ValueError('unknown_draft_fields')
        for key, value in decision.partial_arguments.items():
            f = fields[key]
            if f.repeated:
                if type(value) is not list or not f.min_items <= len(value) <= f.max_items:
                    raise ValueError('invalid_draft_array')
                for item in value:
                    scalar(f, item)
            else:
                scalar(f, value)
    _, prior = load(app, db, row, now)
    identifier = uuid4().hex
    attachments = json.loads(row['attachments_json'])
    source_holder = None
    if not attachments and prior:
        previous = json.loads(prior['data_json'])
        if previous['action_key'] == decision.action_key:
            attachments = previous['attachments']
            source_holder = 'frontend-'+prior['id']
    app.artifacts.lease(db, attachments, context, 'frontend-'+identifier, identifier, now+TTL, now, source_holder=source_holder)
    db.execute(f"UPDATE interactions SET state='cancelled',revision=revision+1 WHERE {SCOPE_SQL} AND kind='frontend_draft' AND state IN ('active','pending_delivery')", context.scope_key)
    payload = {'action_key': decision.action_key, 'partial_arguments': decision.partial_arguments,
               'missing_fields': decision.missing_fields, 'question': decision.question,
               'attachments': attachments}
    db.execute("INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,'frontend_draft','{}','[]',?,'pending_delivery',?)", (identifier, row['id'], *context.scope_key, canonical(payload), now+TTL))


def adopt_context(app, db, row, decision, snapshot, draft, now):
    """Resolver solo IDs publicados en contexto; nunca elegir la lista más reciente."""
    args = dict(decision.arguments)
    spec = app.frontend.catalog.specs[decision.action_key]
    if spec.operation in ('download_media.choose', 'download_media.inspect', 'manage_drive.choose'):
        kind = 'drive' if spec.operation == 'manage_drive.choose' else 'download'
        candidates = [v for v in snapshot['references'] if v['kind'] == kind]
        if 'view_id' not in args:
            if len(candidates) != 1:
                raise ValueError('ambiguous_reference')
            args['view_id'] = candidates[0]['view_id']
        if args['view_id'] not in {v['view_id'] for v in candidates}:
            raise ValueError('unavailable_reference')
    confirmation_fields = {'recado.enviar': 'draft_id', 'pack.confirmar': 'purchase_id', 'confirmar': 'id', 'admin.nuclear-confirmar': 'draft_id'}
    if decision.action_key in confirmation_fields:
        field = confirmation_fields[decision.action_key]
        if not any(v.get('action_key') == decision.action_key and v['arguments'].get(field) == args.get(field) for v in snapshot['references']):
            raise ValueError('confirmation_not_published')
    if draft:
        live = db.execute("SELECT state,expires_ms FROM interactions WHERE id=?", (draft['id'],)).fetchone()
        if not live or live['state'] != 'active' or live['expires_ms'] <= now:
            raise ValueError('draft_expired')
        data = json.loads(draft['data_json'])
        if decision.action_key == data['action_key'] and not json.loads(row['attachments_json']):
            attachments = data['attachments']
            app.artifacts.lease(db, attachments, context_of(row), row['id'], 'frontend', now+TTL, now, source_holder='frontend-'+draft['id'])
            db.execute('UPDATE inbox SET attachments_json=? WHERE id=?', (canonical(attachments), row['id']))
        db.execute("UPDATE interactions SET state='consumed',revision=revision+1,data_json=json_set(data_json,'$.continuation_receipt',?) WHERE id=?", (row['id'], draft['id']))
    from .contracts import ActionRequest
    return ActionRequest(decision.action_key, args)
