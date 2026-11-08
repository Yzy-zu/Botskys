"""Claim durable, inferencia fuera de transacción y adopción atómica sin reintento."""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from botsky import access
from botsky.artifacts import ArtifactProblem
from botsky.adapters.cloudflare_interpreter import InterpreterError
from botsky.contracts import Result
from botsky.domains import bot
from botsky.interactions import replace_file_waits
from botsky.store import context_of
from .contracts import ActionRequest, ClarifyDecision, ReplyDecision
from .context import load, save_draft, adopt_context

logger = logging.getLogger(__name__)

_ACTIVE_SCOPES: dict[tuple, asyncio.Event] = {}


def _provider_name(frontend) -> str:
    interp = getattr(frontend, "interpreter", None) or getattr(frontend, "provider", None) if frontend else None
    if interp is None:
        return "none"
    if hasattr(interp, "active_provider"):
        active = getattr(interp, "active_provider", "primary")
        target = getattr(interp, active, None) or interp
    else:
        target = interp

    alias = getattr(target, "last_credential_alias", None)
    if not alias and hasattr(interp, "last_credential_alias"):
        alias = getattr(interp, "last_credential_alias", None)

    name = getattr(target, "provider_name", None)
    if not name:
        target_cls = type(target).__name__.lower()
        if "gemini" in target_cls:
            name = "gemini"
        elif "cloudflare" in target_cls:
            name = "cloudflare"
        else:
            name = target_cls

    if alias:
        return f"{name}:{alias}"
    return str(name)


def _scope_key(app, row):
    return (str(app.settings.database), *context_of(row).scope_key)


def finish(app, db, row, state, result, now, decision=None):
    db.execute('UPDATE frontend_tasks SET state=?,decision_json=?,updated_ms=?,error_code=? WHERE receipt_id=?',
               (state, json.dumps(decision, ensure_ascii=False) if decision else None, now, result.code if state == 'failed' else None, row['id']))
    db.execute("UPDATE inbox SET state='completed',result_json=?,revision=revision+1 WHERE id=?", (result.to_json(), row['id']))
    app.store.enqueue(db, context_of(row), result, now)


def _fail_running_expired(app, db, now):
    expired = db.execute(
        "SELECT i.* FROM frontend_tasks f JOIN inbox i ON i.id=f.receipt_id "
        "WHERE f.state='running' AND f.deadline_ms<=? AND i.instance=? AND i.account=? AND i.epoch=?",
        (now, app.settings.instance, app.settings.account, app.settings.epoch),
    ).fetchall()
    for row in expired:
        if row['state'] == 'queued':
            logger.warning(
                "event=frontend_expired receipt_id=%s stage=frontend.expired error_code=frontend_interrupted",
                row['id'],
            )
            finish(
                app,
                db,
                row,
                'failed',
                Result(
                    'failed',
                    'frontend_interrupted',
                    'Hubo una pausa inesperada al procesar tu mensaje. Por favor, vuelve a enviarlo.',
                ),
                now,
            )


async def run_one(app):
    while True:
        now = app.clock()
        token = uuid.uuid4().hex
        wait_event = None
        skey = None
        with app.store.transaction() as db:
            # An interrupted inference is never submitted again. Late responses lose token/state.
            _fail_running_expired(app, db, now)
            db.execute("UPDATE frontend_tasks SET state='cancelled',updated_ms=? WHERE state IN ('pending','running') AND receipt_id IN (SELECT id FROM inbox WHERE state!='queued')", (now,))
            candidates = db.execute(
                "SELECT i.* FROM frontend_tasks f JOIN inbox i ON i.id=f.receipt_id "
                "WHERE f.state='pending' AND i.state='queued' AND i.instance=? AND i.account=? AND i.epoch=? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM frontend_tasks pf JOIN inbox p ON p.id=pf.receipt_id "
                "  WHERE p.instance=i.instance AND p.account=i.account AND p.actor=i.actor "
                "  AND p.chat=i.chat AND p.is_group=i.is_group AND p.epoch=i.epoch AND p.id<>i.id "
                "  AND ("
                "    (pf.state='running' AND pf.deadline_ms>?) "
                "    OR (pf.state='adopted' AND p.state='queued') "
                "    OR (pf.state='pending' AND p.state='queued' AND (p.received_ms<i.received_ms OR (p.received_ms=i.received_ms AND p.rowid<i.rowid)))"
                "  )"
                ") ORDER BY i.received_ms, i.rowid",
                (app.settings.instance, app.settings.account, app.settings.epoch, now),
            ).fetchall()
            row = next((c for c in candidates if _scope_key(app, c) not in _ACTIVE_SCOPES), None)
            if row is None:
                pending_rows = db.execute(
                    "SELECT i.* FROM frontend_tasks f JOIN inbox i ON i.id=f.receipt_id WHERE f.state='pending' AND i.state='queued' AND i.instance=? AND i.account=? AND i.epoch=? ORDER BY i.received_ms, i.rowid",
                    (app.settings.instance, app.settings.account, app.settings.epoch),
                ).fetchall()
                for pending_row in pending_rows:
                    ev = _ACTIVE_SCOPES.get(_scope_key(app, pending_row))
                    if ev is not None:
                        wait_event = ev
                        break
                if wait_event is None:
                    return False
            else:
                context = context_of(row)
                gate_spec = app.router.registry.paths[('nota', 'guardar')]
                denied = access.authorize('friend', context, app.settings) or (bot.gate(db, context, gate_spec, now) if context.scope.actor != app.settings.owner else None)
                if denied:
                    finish(app, db, row, 'cancelled', denied, now)
                    return True
                db.execute("UPDATE frontend_tasks SET state='running',token=?,deadline_ms=?,updated_ms=? WHERE receipt_id=?", (token, now + 60000, now, row['id']))
                skey = _scope_key(app, row)
                _ACTIVE_SCOPES[skey] = asyncio.Event()
        if wait_event is not None:
            await wait_event.wait()
            continue
        break
    try:
        with app.store.transaction() as db:
            snapshot, draft = load(app, db, row, now)
        decide_start = time.monotonic()
        try:
            async with asyncio.timeout(50):
                decision = await app.frontend.decide(row['text'], {
                    'now': datetime.fromtimestamp(now / 1000, UTC).isoformat(),
                    'timezone': app.settings.timezone,
                    'attachments': json.loads(row['attachments_json']), **snapshot})
            error = None
        except InterpreterError as exc:
            duration_ms = int((time.monotonic() - decide_start) * 1000)
            decision = None
            err_str = str(exc)
            error = 'frontend_quota_exhausted' if err_str == 'daily_quota_pool' else 'frontend_account_quota' if err_str == 'daily_quota' else 'frontend_unavailable'
            provider = _provider_name(app.frontend)
            http_status = getattr(exc, "http_status", None)
            if http_status is None and err_str.startswith("provider_http_"):
                try:
                    http_status = int(err_str.split("_")[-1])
                except ValueError:
                    pass
            logger.warning(
                "event=frontend_decide_failed receipt_id=%s stage=frontend.decide provider=%s error_code=%s http_status=%s exc_type=%s duration_ms=%d",
                row['id'],
                provider,
                getattr(exc, "code", err_str),
                http_status,
                type(exc).__name__,
                duration_ms,
            )
        except TimeoutError as exc:
            duration_ms = int((time.monotonic() - decide_start) * 1000)
            decision, error = None, 'frontend_unavailable'
            provider = _provider_name(app.frontend)
            logger.warning(
                "event=frontend_decide_failed receipt_id=%s stage=frontend.decide provider=%s error_code=%s http_status=%s exc_type=%s duration_ms=%d",
                row['id'],
                provider,
                "timeout",
                None,
                type(exc).__name__,
                duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - decide_start) * 1000)
            decision, error = None, 'frontend_unavailable'
            provider = _provider_name(app.frontend)
            logger.warning(
                "event=frontend_decide_failed receipt_id=%s stage=frontend.decide provider=%s error_code=%s http_status=%s exc_type=%s duration_ms=%d",
                row['id'],
                provider,
                getattr(exc, "code", str(exc)),
                getattr(exc, "http_status", None),
                type(exc).__name__,
                duration_ms,
            )
        with app.store.transaction() as db:
            current = db.execute("SELECT i.*,f.state AS frontend_state,f.token,f.deadline_ms FROM inbox i JOIN frontend_tasks f ON f.receipt_id=i.id WHERE i.id=?", (row['id'],)).fetchone()
            if current['state'] != 'queued' or current['frontend_state'] != 'running' or current['token'] != token:
                return True
            now = app.clock()
            if current['epoch'] != app.settings.epoch or now >= current['deadline_ms']:
                finish(app, db, current, 'failed', Result('failed', 'frontend_expired', 'Se agotó el tiempo de espera para procesar tu solicitud. Por favor, inténtalo de nuevo.'), now)
                return True
            denied = access.authorize('friend', context_of(current), app.settings) or (bot.gate(db, context_of(current), gate_spec, now) if current['actor'] != app.settings.owner else None)
            if denied:
                finish(app, db, current, 'cancelled', denied, now)
            elif error:
                finish(app, db, current, 'failed', Result('failed', error, 'El asistente conversacional alcanzó su límite de consultas de hoy. Estará disponible de nuevo mañana; mientras tanto, puedes usar comandos directos (escribe /ayuda).' if error == 'frontend_quota_exhausted' else 'El servicio estuvo momentáneamente ocupado. Por favor, reenvía tu mensaje para reintentarlo.' if error == 'frontend_account_quota' else 'El servicio conversacional está temporalmente caído. Inténtalo de nuevo más tarde o usa un comando directo como /ayuda o /nota guardar.'), now)
            elif isinstance(decision, ActionRequest):
                db.execute('SAVEPOINT frontend_adoption')
                try:
                    decision = adopt_context(app, db, current, decision, snapshot, draft, now)
                    parsed = app.frontend.catalog.build(decision)
                except (ValueError, KeyError, TypeError, ArtifactProblem) as exc:
                    db.execute('ROLLBACK TO frontend_adoption')
                    db.execute('RELEASE frontend_adoption')
                    action_key = getattr(decision, "action_key", None)
                    error_code = getattr(exc, "code", str(exc))
                    logger.warning(
                        "event=frontend_adopt_failed receipt_id=%s stage=frontend.adopt action_key=%s error_code=%s exc_type=%s",
                        current['id'],
                        action_key,
                        error_code,
                        type(exc).__name__,
                    )
                    finish(app, db, current, 'failed', Result('failed', 'invalid_proposal', 'No pude procesar esa acción con los datos indicados. Escribe claramente qué deseas hacer o responde al mensaje correspondiente.'), now)
                    return True
                db.execute('RELEASE frontend_adoption')
                notice = ""
                if parsed.spec.family != "core" or parsed.spec.operation == "core.cancelar":
                    notice = replace_file_waits(db, context_of(current))
                    if parsed.spec.operation == "core.cancelar":
                        notice = ""
                db.execute("UPDATE inbox SET command_json=?,path_json=?,permission=?,notice=?,revision=revision+1 WHERE id=?", (parsed.canonical(), json.dumps(parsed.spec.path), parsed.spec.permission, notice, row['id']))
                db.execute("UPDATE frontend_tasks SET state='adopted',decision_json=?,updated_ms=? WHERE receipt_id=?", (json.dumps(asdict(decision), ensure_ascii=False), now, row['id']))
            else:
                replace_file_waits(db, context_of(current))
                if isinstance(decision, ClarifyDecision):
                    db.execute('SAVEPOINT frontend_draft')
                    try:
                        save_draft(app, db, current, decision, now)
                    except (ValueError, ArtifactProblem) as exc:
                        db.execute('ROLLBACK TO frontend_draft')
                        db.execute('RELEASE frontend_draft')
                        if isinstance(exc, ValueError):
                            kind = getattr(decision, "action_key", None) or "clarify"
                            logger.warning(
                                "event=frontend_draft_failed receipt_id=%s stage=frontend.draft kind=%s error_code=invalid_draft exc_type=%s",
                                current['id'],
                                kind,
                                type(exc).__name__,
                            )
                        finish(app, db, current, 'failed', Result('failed', 'invalid_draft', 'No pude guardar el borrador de tu solicitud. Por favor, vuelve a indicarla desde el principio.'), now)
                        return True
                    db.execute('RELEASE frontend_draft')
                elif draft:
                    db.execute("UPDATE interactions SET state='cancelled',revision=revision+1 WHERE id=?", (draft['id'],))
                text = decision.text if isinstance(decision, ReplyDecision) else decision.question if isinstance(decision, ClarifyDecision) else 'Entendido. Si necesitas algo más, aquí estaré para ayudarte.'
                finish(app, db, current, 'completed', Result('ok', 'frontend_reply', text), now, asdict(decision))
        # Adoption is already committed: restart only executes this canonical request.
        app.recover(limit=20)
        return True
    finally:
        if skey is not None:
            ev = _ACTIVE_SCOPES.pop(skey, None)
            if ev is not None:
                ev.set()


async def run_pending(app, limit=2):
    return await asyncio.gather(*(run_one(app) for _ in range(limit)))
