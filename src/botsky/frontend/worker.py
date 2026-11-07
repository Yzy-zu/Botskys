"""Claim durable, inferencia fuera de transacción y adopción atómica sin reintento."""
import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from botsky import access
from botsky.artifacts import ArtifactProblem
from botsky.adapters.cloudflare_interpreter import InterpreterError
from botsky.contracts import Result
from botsky.domains import bot
from botsky.store import context_of
from .contracts import ActionRequest, ClarifyDecision, ReplyDecision
from .context import load, save_draft, adopt_context


def finish(app, db, row, state, result, now, decision=None):
    db.execute('UPDATE frontend_tasks SET state=?,decision_json=?,updated_ms=?,error_code=? WHERE receipt_id=?',
               (state, json.dumps(decision, ensure_ascii=False) if decision else None, now, result.code if state == 'failed' else None, row['id']))
    db.execute("UPDATE inbox SET state='completed',result_json=?,revision=revision+1 WHERE id=?", (result.to_json(), row['id']))
    app.store.enqueue(db, context_of(row), result, now)


async def run_one(app):
    now = app.clock()
    token = uuid.uuid4().hex
    with app.store.transaction() as db:
        # An interrupted inference is never submitted again. Late responses lose token/state.
        expired = db.execute("SELECT i.* FROM frontend_tasks f JOIN inbox i ON i.id=f.receipt_id WHERE f.state='running' AND f.deadline_ms<=? AND i.instance=? AND i.account=? AND i.epoch=?", (now, app.settings.instance, app.settings.account, app.settings.epoch)).fetchall()
        for row in expired:
            if row['state'] == 'queued':
                finish(app, db, row, 'failed', Result('failed', 'frontend_interrupted', 'La interpretación se interrumpió. Puedes enviar una petición nueva.'), now)
        db.execute("UPDATE frontend_tasks SET state='cancelled',updated_ms=? WHERE state IN ('pending','running') AND receipt_id IN (SELECT id FROM inbox WHERE state!='queued')", (now,))
        row = db.execute("SELECT i.* FROM frontend_tasks f JOIN inbox i ON i.id=f.receipt_id WHERE f.state='pending' AND i.state='queued' AND i.instance=? AND i.account=? AND i.epoch=? ORDER BY f.created_ms LIMIT 1", (app.settings.instance, app.settings.account, app.settings.epoch)).fetchone()
        if row is None:
            return False
        context = context_of(row)
        gate_spec = app.router.registry.paths[('nota', 'guardar')]
        denied = access.authorize('friend', context, app.settings) or (bot.gate(db, context, gate_spec, now) if context.scope.actor != app.settings.owner else None)
        if denied:
            finish(app, db, row, 'cancelled', denied, now)
            return True
        db.execute("UPDATE frontend_tasks SET state='running',token=?,deadline_ms=?,updated_ms=? WHERE receipt_id=?", (token, now + 60000, now, row['id']))
    with app.store.transaction() as db:
        snapshot, draft = load(app, db, row, now)
    try:
        async with asyncio.timeout(50):
            decision = await app.frontend.decide(row['text'], {
                'now': datetime.fromtimestamp(now / 1000, UTC).isoformat(),
                'timezone': app.settings.timezone,
                'attachments': json.loads(row['attachments_json']), **snapshot})
        error = None
    except InterpreterError as exc:
        decision=None
        error='frontend_quota_exhausted' if str(exc)=='daily_quota_pool' else 'frontend_account_quota' if str(exc)=='daily_quota' else 'frontend_unavailable'
    except Exception:
        decision, error = None, 'frontend_unavailable'
    with app.store.transaction() as db:
        current = db.execute("SELECT i.*,f.state AS frontend_state,f.token,f.deadline_ms FROM inbox i JOIN frontend_tasks f ON f.receipt_id=i.id WHERE i.id=?", (row['id'],)).fetchone()
        if current['state'] != 'queued' or current['frontend_state'] != 'running' or current['token'] != token:
            return True
        now = app.clock()
        if current['epoch'] != app.settings.epoch or now >= current['deadline_ms']:
            finish(app, db, current, 'failed', Result('failed', 'frontend_expired', 'La interpretación caducó; envía una petición nueva.'), now)
            return True
        denied = access.authorize('friend', context_of(current), app.settings) or (bot.gate(db, context_of(current), gate_spec, now) if current['actor'] != app.settings.owner else None)
        if denied:
            finish(app, db, current, 'cancelled', denied, now)
        elif error:
            finish(app, db, current, 'failed', Result('failed', error, 'La cuota diaria de las cuentas configuradas está agotada. La interpretación volverá a estar disponible cuando el proveedor renueve la cuota.' if error == 'frontend_quota_exhausted' else 'La cuenta elegida agotó su cuota. Puedes enviar la petición de nuevo para usar otra cuenta disponible.' if error == 'frontend_account_quota' else 'No pude interpretar la petición. Inténtalo con un mensaje nuevo.'), now)
        elif isinstance(decision, ActionRequest):
            db.execute('SAVEPOINT frontend_adoption')
            try:
                decision = adopt_context(app, db, current, decision, snapshot, draft, now)
                parsed = app.frontend.catalog.build(decision)
            except (ValueError, KeyError, TypeError, ArtifactProblem):
                db.execute('ROLLBACK TO frontend_adoption')
                db.execute('RELEASE frontend_adoption')
                finish(app, db, current, 'failed', Result('failed', 'invalid_proposal', 'La propuesta no es válida.'), now)
                return True
            db.execute('RELEASE frontend_adoption')
            db.execute("UPDATE inbox SET command_json=?,path_json=?,permission=?,revision=revision+1 WHERE id=?", (parsed.canonical(), json.dumps(parsed.spec.path), parsed.spec.permission, row['id']))
            db.execute("UPDATE frontend_tasks SET state='adopted',decision_json=?,updated_ms=? WHERE receipt_id=?", (json.dumps(asdict(decision), ensure_ascii=False), now, row['id']))
        else:
            if isinstance(decision, ClarifyDecision):
                db.execute('SAVEPOINT frontend_draft')
                try:
                    save_draft(app, db, current, decision, now)
                except (ValueError, ArtifactProblem):
                    db.execute('ROLLBACK TO frontend_draft')
                    db.execute('RELEASE frontend_draft')
                    finish(app, db, current, 'failed', Result('failed', 'invalid_draft', 'No pude conservar la petición; vuelve a indicarla.'), now)
                    return True
                db.execute('RELEASE frontend_draft')
            elif draft:
                db.execute("UPDATE interactions SET state='cancelled',revision=revision+1 WHERE id=?", (draft['id'],))
            text = decision.text if isinstance(decision, ReplyDecision) else decision.question if isinstance(decision, ClarifyDecision) else 'De acuerdo.'
            finish(app, db, current, 'completed', Result('ok', 'frontend_reply', text), now, asdict(decision))
    # Adoption is already committed: restart only executes this canonical request.
    app.recover(limit=20)
    return True


async def run_pending(app, limit=2):
    return await asyncio.gather(*(run_one(app) for _ in range(limit)))
