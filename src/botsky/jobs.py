"""Trabajos de archivos durables, acotados y retirables antes de publicar."""

import asyncio
import json
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from . import access
from .artifacts import ArtifactProblem
from .contracts import Result, canonical
from .local_files import private_directory, worker_lock
from .store import context_of

MAX_CONCURRENCY = 2
MAX_QUEUED = 128
MAX_ACTOR_QUEUED = 8


@dataclass(frozen=True)
class EngineOutput:
    result: Result
    files: tuple[Path, ...] = ()


def cancel_job(db, context, target):
    row = db.execute(
        "SELECT * FROM jobs WHERE id=? AND state IN ('queued','running')", (target,)
    ).fetchone()
    interaction = db.execute(
        "SELECT 1 FROM interactions WHERE receipt_id=? AND state IN ('pending_delivery','active')",
        (target,),
    ).fetchone()
    if not row and not interaction:
        return None
    delivery = {
        r["state"]: r["n"]
        for r in db.execute(
            "SELECT state,count(*) AS n FROM outbox WHERE receipt_id=? GROUP BY state", (target,)
        )
    }
    text = "Cancelado."
    if delivery.get("accepted"):
        text += f" El servicio ya aceptó {delivery['accepted']} partes; no se retiraron."
    if delivery.get("sending") or delivery.get("uncertain"):
        text += " No pude confirmar si llegó una parte en curso. Revisa antes de repetir."
    result = Result(
        "cancelled", "request_cancelled", text, {"id": target, "delivery_before_cancel": delivery}
    )
    db.execute(
        "UPDATE jobs SET state='cancelled',lease_token=NULL,revision=revision+1,result_json=? WHERE id=? AND state IN ('queued','running')",
        (result.to_json(), target),
    )
    db.execute(
        "UPDATE interactions SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state IN ('pending_delivery','active')",
        (target,),
    )
    db.execute(
        "UPDATE inbox SET result_json=?,revision=revision+1 WHERE id=?", (result.to_json(), target)
    )
    db.execute("UPDATE effects SET result_json=? WHERE receipt_id=?", (result.to_json(), target))
    db.execute(
        "UPDATE outbox SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state='pending'",
        (target,),
    )
    # En ejecución el lease de archivo se retiene hasta que el worker libere sus recursos.
    if not row or row["state"] == "queued":
        db.execute("DELETE FROM artifact_leases WHERE holder=?", ("job-" + target,))
    if row:
        if row["operation"].startswith(("control_call.", "audiovisual.")):
            from time import time_ns

            from .domains.calls import retire_job

            retire_job(db, target, time_ns() // 1000000)
        if row["operation"].startswith("manage_admin."):
            from time import time_ns

            from .domains.admin import retire_job

            retire_job(db, target, time_ns() // 1000000)
        if row["operation"].startswith("manage_minecraft."):
            from time import time_ns

            from .domains.minecraft import retire_job

            retire_job(db, target, time_ns() // 1000000)
        if row["operation"].startswith("manage_roulette."):
            from time import time_ns

            from .domains.roulette import retire_job

            retire_job(db, target, time_ns() // 1000000)
        if row["operation"].startswith("manage_happy_hour."):
            from time import time_ns

            from .domains.happy_media import retire_job

            retire_job(db, target, time_ns() // 1000000)
        if row["operation"].startswith("manage_cooperacha."):
            from time import time_ns

            from .domains.cooperacha import retire_job

            retire_job(db, target, time_ns() // 1000000)
        if row["operation"] == "manage_messages.send":
            from time import time_ns

            from .domains.messages import retire_job

            retire_job(db, target, time_ns() // 1000000)
        if row["operation"] == "manage_pack.buy":
            from time import time_ns

            from .domains.packs import retire_job

            retire_job(db, target, time_ns() // 1000000)
        args = json.loads(row["arguments_json"])
        if args.get("session_id"):
            db.execute(
                "UPDATE pdf_sessions SET state='open',revision=revision+1 WHERE id=? AND state='processing' AND revision=?",
                (args["session_id"], args["session_revision"]),
            )
    return result


class Jobs:
    def __init__(
        self,
        store,
        settings,
        artifacts,
        clock,
        policy=None,
        downloads=None,
        web=None,
        content=None,
        drive=None,
        messages=None,
        gallery=None,
        groups=None,
        minecraft=None,
        calls=None,
        nuclear_enabled=None,
        roulette_policy=None,
        operations=None,
    ):
        self.store, self.artifacts, self.clock = store, artifacts, clock
        self._policy = policy or (lambda: settings)
        self.downloads = downloads or (lambda: None)
        self.web = web or (lambda: None)
        self.content = content or (lambda: (None, None, None))
        self.drive = drive or (lambda: None)
        self.messages = messages or (lambda: (None, None))
        self.gallery = gallery or (lambda: (None, None, frozenset()))
        self.groups = groups or (lambda: None)
        self.calls = calls or (lambda: None)
        self.operations = operations or (lambda: None)
        self.minecraft = minecraft or (lambda: None)
        self.nuclear_enabled = nuclear_enabled or (lambda: False)
        self.roulette_policy = roulette_policy or (lambda: (frozenset(), False, None))
        self.root = private_directory(settings.root, "tmp/jobs")

    @property
    def settings(self):
        return self._policy()

    def reserve(
        self, db, context, operation, args, inputs, now, *, resource=None, source_holder=None
    ):
        if (
            db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[
                0
            ]
            >= MAX_QUEUED
        ):
            return Result("failed", "job_queue_full", "La cola está llena. Prueba después.")
        count = db.execute(
            "SELECT count(*) FROM jobs j JOIN inbox i ON j.id=i.id WHERE j.state IN ('queued','running') AND i.instance=? AND i.account=? AND i.actor=? AND i.epoch=?",
            (context.instance, context.account, context.scope.actor, context.epoch),
        ).fetchone()[0]
        if count >= MAX_ACTOR_QUEUED:
            return Result("failed", "actor_queue_full", "Tienes demasiados trabajos pendientes.")
        self.artifacts.lease(
            db,
            inputs,
            context,
            "job-" + context.receipt_id,
            "reserved",
            now + 86400000,
            now,
            source_holder=source_holder,
        )
        db.execute(
            "INSERT INTO jobs(id,instance,account,epoch,operation,arguments_json,inputs_json,state,parent_revision,resource_key,created_ms,updated_ms) VALUES(?,?,?,?,?,?,?,'queued',?,?,?,?)",
            (
                context.receipt_id,
                context.instance,
                context.account,
                context.epoch,
                operation,
                canonical(args),
                canonical(inputs),
                context.revision + 1,
                resource or context.receipt_id,
                now,
                now,
            ),
        )
        return Result(
            "ok",
            "job_queued",
            "Trabajo en cola. Usa /estado para consultarlo.",
            {"job_id": context.receipt_id},
        )

    def claim(self):
        now = self.clock()
        with self.store.transaction() as db:
            interrupted = db.execute(
                "SELECT j.*,i.revision AS actual_parent FROM jobs j JOIN inbox i ON i.id=j.id WHERE j.instance=? AND j.account=? AND j.epoch=? AND j.state='running' AND j.provider_dispatched=1 AND j.lease_until_ms<=?",
                (self.settings.instance, self.settings.account, self.settings.epoch, now),
            ).fetchall()
            for row in interrupted:
                if row["operation"].startswith(("control_call.", "audiovisual.")):
                    from .domains.calls import retire_job

                    retire_job(db, row["id"], now)
                if row["operation"].startswith("manage_admin."):
                    from .domains.admin import retire_job

                    retire_job(db, row["id"], now)
                if row["operation"].startswith("manage_minecraft."):
                    from .domains.minecraft import retire_job

                    retire_job(db, row["id"], now)
                if row["operation"].startswith("manage_roulette."):
                    from .domains.roulette import retire_job

                    retire_job(db, row["id"], now)
                if row["operation"].startswith("manage_happy_hour."):
                    from .domains.happy_media import retire_job

                    retire_job(db, row["id"], now)
                if row["operation"].startswith("manage_cooperacha."):
                    from .domains.cooperacha import retire_job

                    retire_job(db, row["id"], now)
                if row["operation"] == "manage_pack.buy":
                    from .domains.packs import retire_job

                    retire_job(db, row["id"], now)
                if row["operation"] == "manage_messages.send":
                    from .domains.messages import retire_job

                    retire_job(db, row["id"], now)
                db.execute(
                    "UPDATE drive_uploads SET state='uncertain',updated_ms=? WHERE receipt_id=? AND state='reserved'",
                    (now, row["id"]),
                )
                result = Result(
                    "uncertain",
                    "provider_interrupted",
                    "El proveedor quedó interrumpido; no repetí la solicitud automáticamente.",
                )
                db.execute(
                    "UPDATE jobs SET state='failed',revision=revision+1,lease_token=NULL,result_json=? WHERE id=?",
                    (result.to_json(), row["id"]),
                )
                if row["parent_revision"] == row["actual_parent"]:
                    parent = db.execute("SELECT * FROM inbox WHERE id=?", (row["id"],)).fetchone()
                    db.execute(
                        "UPDATE inbox SET result_json=?,revision=revision+1 WHERE id=?",
                        (result.to_json(), row["id"]),
                    )
                    db.execute(
                        "UPDATE effects SET result_json=? WHERE receipt_id=?",
                        (result.to_json(), row["id"]),
                    )
                    self.store.enqueue(db, context_of(parent), result, now)
                db.execute("DELETE FROM artifact_leases WHERE holder=?", ("job-" + row["id"],))
            # Solo motores locales/lecturas externas; nunca una compra, envío o marcado.
            db.execute(
                "UPDATE jobs SET state='queued',lease_token=NULL,revision=revision+1 WHERE instance=? AND account=? AND epoch=? AND state='running' AND lease_until_ms<=?",
                (self.settings.instance, self.settings.account, self.settings.epoch, now),
            )
            active = db.execute(
                "SELECT count(*) FROM jobs WHERE instance=? AND account=? AND state='running' AND lease_until_ms>?",
                (self.settings.instance, self.settings.account, now),
            ).fetchone()[0]
            if active >= MAX_CONCURRENCY:
                return None
            job = db.execute(
                "SELECT * FROM jobs j WHERE instance=? AND account=? AND epoch=? AND state='queued' AND NOT EXISTS(SELECT 1 FROM jobs r WHERE r.resource_key=j.resource_key AND r.state='running' AND r.lease_until_ms>?) ORDER BY created_ms,id LIMIT 1",
                (self.settings.instance, self.settings.account, self.settings.epoch, now),
            ).fetchone()
            if not job:
                return None
            parent = db.execute("SELECT * FROM inbox WHERE id=?", (job["id"],)).fetchone()
            context = context_of(parent)
            token = uuid4().hex
            budget = (
                10800 if job["operation"].startswith(("edit_media.", "download_media.")) else 1800
            )
            expires = now + (budget + 30) * 1000
            result = access.authorize(parent["permission"], context, self.settings)
            try:
                if not result:
                    self.artifacts.lease(
                        db,
                        json.loads(job["inputs_json"]),
                        context,
                        "job-" + job["id"],
                        token,
                        expires,
                        now,
                    )
            except ArtifactProblem as exc:
                result = Result(
                    "failed", exc.code, "El archivo ya no está disponible; adjúntalo de nuevo."
                )
            db.execute(
                "UPDATE jobs SET state='running',lease_token=?,lease_until_ms=?,revision=revision+1,updated_ms=? WHERE id=? AND state='queued' AND revision=?",
                (token, expires, now, job["id"], job["revision"]),
            )
            return {
                "id": job["id"],
                "token": token,
                "revision": job["revision"] + 1,
                "budget": budget,
                "operation": job["operation"],
                "arguments": json.loads(job["arguments_json"]),
                "inputs": json.loads(job["inputs_json"]),
                "context": context,
                "early_result": result,
            }

    def mark_provider(self, job):
        with self.store.transaction() as db:
            from .domains.bot import current
            from .engines.process import MediaError

            parent = db.execute("SELECT * FROM inbox WHERE id=?", (job["id"],)).fetchone()
            denied = access.authorize(parent["permission"], context_of(parent), self.settings)
            mode = current(db, context_of(parent))
            if denied or mode["mode"] == "apagado" or mode["paused_until_ms"] > self.clock():
                raise MediaError(denied.code if denied else "bot_paused")
            changed = db.execute(
                "UPDATE jobs SET provider_dispatched=1 WHERE id=? AND state='running' AND lease_token=? AND revision=? AND lease_until_ms>?",
                (job["id"], job["token"], job["revision"], self.clock()),
            ).rowcount
            if changed != 1:
                from .engines.process import MediaError

                raise MediaError("job_retired")

    def current(self, job):
        db = self.store.connect()
        try:
            row = db.execute(
                "SELECT j.*,i.revision AS actual_parent_revision FROM jobs j JOIN inbox i ON j.id=i.id WHERE j.id=?",
                (job["id"],),
            ).fetchone()
            return bool(
                row
                and row["state"] == "running"
                and row["lease_token"] == job["token"]
                and row["revision"] == job["revision"]
                and row["epoch"] == self.settings.epoch
                and row["parent_revision"] == row["actual_parent_revision"]
                and row["lease_until_ms"] > self.clock()
            )
        finally:
            db.close()

    def finish(self, job, output, staged):
        result = output.result
        now = self.clock()
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
            parent = db.execute("SELECT * FROM inbox WHERE id=?", (job["id"],)).fetchone()
            if (
                not row
                or row["state"] != "running"
                or row["lease_token"] != job["token"]
                or row["revision"] != job["revision"]
                or row["epoch"] != self.settings.epoch
                or parent["revision"] != row["parent_revision"]
                or row["lease_until_ms"] <= now
            ):
                return False
            context = context_of(parent)
            args = json.loads(row["arguments_json"])
            if row["operation"] in (
                "control_call.start",
                "audiovisual.agenda.create",
            ) and result.code not in ("call_requested", "agenda_create"):
                from .domains.calls import retire_job

                retire_job(db, job["id"], now)
            if row["operation"].startswith("manage_admin."):
                from .domains.admin import retire_job

                retire_job(db, job["id"], now)
            if row["operation"].startswith("manage_minecraft."):
                from .domains.minecraft import retire_job

                retire_job(db, job["id"], now)
            if row["operation"].startswith("manage_roulette."):
                from .domains.roulette import retire_job

                retire_job(db, job["id"], now)
            if row["operation"].startswith("manage_happy_hour."):
                from .domains.happy_media import retire_job

                retire_job(db, job["id"], now)
            if row["operation"] == "manage_cooperacha.complete":
                from .domains.cooperacha import retire_job

                retire_job(db, job["id"], now)
            if row["operation"] == "manage_pack.buy":
                from .domains.packs import retire_job

                retire_job(db, job["id"], now)
            if row["operation"] == "manage_messages.send":
                from .domains.messages import retire_job

                retire_job(db, job["id"], now)
            session = None
            if args.get("session_id"):
                session = db.execute(
                    "SELECT * FROM pdf_sessions WHERE id=?", (args["session_id"],)
                ).fetchone()
                if (
                    not session
                    or session["state"] != "processing"
                    or session["revision"] != args["session_revision"]
                ):
                    return False
            denied = access.authorize(parent["permission"], context, self.settings)
            if denied:
                result, staged = denied, []
            ids = []
            for file in staged:
                ids.append(
                    self.artifacts.register(
                        db,
                        file,
                        context,
                        parent["message_id"],
                        now,
                        origin="result",
                        receipt_id=job["id"],
                    )
                )
            if result.data.get("file_facts"):
                from dataclasses import replace

                facts = [
                    {**fact, "format": staged[index].format}
                    for index, fact in enumerate(result.data["file_facts"])
                    if index < len(staged)
                ]
                result = replace(result, data={**result.data, "file_facts": facts})
            if ids:
                result = Result(
                    result.status, result.code, result.text, {**result.data, "artifacts": ids}
                )
            if result.code == "download_choices":
                identifier = uuid4().hex
                data = {"choices": result.data["choices"], "arguments": result.data["arguments"]}
                db.execute(
                    "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'pending_delivery',?)",
                    (
                        identifier,
                        context.receipt_id,
                        *context.scope_key,
                        "download",
                        parent["command_json"],
                        parent["path_json"],
                        canonical(data),
                        now + 900000,
                    ),
                )
                from dataclasses import asdict

                from .presentation.search import video_document

                document = video_document(data["choices"], now + 900000, now, intro="Videos")
                result = Result(
                    "needs_input",
                    "download_choices",
                    document.text(),
                    {
                        **result.data,
                        "view_id": identifier,
                        "choices": data["choices"],
                        "media_first": True,
                        "document": asdict(document),
                        "expires_ms": now + 900000,
                    },
                )
            if result.code == "drive_choices":
                from .domains.drive import finish_choices

                result = finish_choices(db, context, parent, result, now)
            if result.code == "coop_preview":
                from .domains.cooperacha import finish_preview

                result = finish_preview(db, context, result)
            if result.code == "download_ready" and ids:
                identifier = uuid4().hex
                db.execute(
                    "INSERT INTO interactions(id,receipt_id,instance,account,actor,chat,is_group,epoch,kind,command_json,path_json,data_json,state,expires_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'pending_delivery',?)",
                    (
                        identifier,
                        context.receipt_id,
                        *context.scope_key,
                        "download_previous",
                        parent["command_json"],
                        parent["path_json"],
                        canonical({"artifact_id": ids[0]}),
                        now + 86400000,
                    ),
                )
            if result.code == "ai_reply":
                db.execute(
                    "INSERT INTO ai_history VALUES(?,?,?,?,?,?,?,?,?,0,?,?)",
                    (
                        context.receipt_id,
                        *context.scope_key,
                        args["text"],
                        result.text,
                        now,
                        now + 1800000,
                    ),
                )
            db.execute(
                "UPDATE jobs SET state=?,result_json=?,lease_token=NULL,revision=revision+1,updated_ms=? WHERE id=? AND revision=?",
                (
                    "succeeded" if result.status in ("ok", "empty", "needs_input") else "failed",
                    result.to_json(),
                    now,
                    job["id"],
                    job["revision"],
                ),
            )
            db.execute(
                "UPDATE inbox SET result_json=?,revision=revision+1 WHERE id=? AND revision=?",
                (result.to_json(), job["id"], parent["revision"]),
            )
            db.execute(
                "UPDATE effects SET result_json=? WHERE receipt_id=?", (result.to_json(), job["id"])
            )
            self.store.enqueue(db, context, result, now)
            if session:
                state = "finished" if result.status == "ok" else "open"
                db.execute(
                    "UPDATE pdf_sessions SET state=?,revision=revision+1,updated_ms=? WHERE id=? AND revision=?",
                    (state, now, session["id"], session["revision"]),
                )
                if state == "finished":
                    db.execute(
                        "DELETE FROM artifact_leases WHERE holder=?", ("pdf-" + session["id"],)
                    )
            db.execute(
                "DELETE FROM artifact_leases WHERE holder=? AND token=?",
                ("job-" + job["id"], job["token"]),
            )
            return True

    async def run_one(self, job):
        directory = self.root / (job["id"] + "-" + job["token"])
        directory.mkdir(mode=0o700)
        staged = []
        task = None
        published = False
        try:
            if job["early_result"]:
                output = EngineOutput(job["early_result"])
            else:
                policy = self.operations()
                if policy and policy.authorize(job["context"], job["operation"]):
                    with self.store.transaction() as db:
                        cancel_job(db, job["context"], job["id"])
                    return

                async def execute_with_facts():
                    from .engines.output_facts import enrich

                    return await enrich(await self.execute_engine(job, directory))

                task = asyncio.create_task(execute_with_facts())
                async with asyncio.timeout(job["budget"]):
                    while not task.done():
                        await asyncio.wait([task], timeout=0.05)
                        if not self.current(job):
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                            return
                    output = await task
            for file in output.files:
                staged.append(self.artifacts.stage(file, output=True))
            published = self.finish(job, output, staged)
        except asyncio.CancelledError:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            # Trabajo retirado queda sin publicación. Recuperación por lease vencido.
            raise
        except Exception as exc:
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            code = exc.code if isinstance(exc, ArtifactProblem) else "job_failed"
            from .engines.process import MediaError

            if isinstance(exc, MediaError):
                code = exc.code
            if isinstance(exc, TimeoutError):
                code = "job_timeout"
            from .engines.documents import present_document_error
            from .presentation.errors import job_error

            message = (
                present_document_error(code)
                if code.startswith(
                    (
                        "document_",
                        "protected_pdf",
                        "invalid_or_protected_pdf",
                        "unsupported_document",
                        "unsupported_target",
                        "unsupported_conversion",
                    )
                )
                else job_error(code, job["operation"])
            )
            self.finish(
                job,
                EngineOutput(Result("failed", code, message)),
                [],
            )
        finally:
            with self.store.transaction() as db:
                for file in staged:
                    if (
                        not published
                        or not db.execute(
                            "SELECT 1 FROM artifacts WHERE id=?", (file.id,)
                        ).fetchone()
                    ):
                        file.path.unlink(missing_ok=True)
                db.execute(
                    "DELETE FROM artifact_leases WHERE holder=? AND token=? AND NOT EXISTS(SELECT 1 FROM jobs WHERE id=? AND state='running' AND lease_token=?)",
                    ("job-" + job["id"], job["token"], job["id"], job["token"]),
                )
            shutil.rmtree(directory, ignore_errors=True)

    async def run_pending(self, limit=MAX_QUEUED):
        with worker_lock(self.settings.root):
            if self.calls() is not None:
                from .domains.calls import drain_cancellations

                await drain_cancellations(self, self.calls())
            try:
                return await self._run_pending(limit)
            finally:
                if self.calls() is not None:
                    from .domains.calls import drain_cancellations

                    await drain_cancellations(self, self.calls())

    async def _run_pending(self, limit):
        self.store.prune_context(self.settings, self.clock())
        db = self.store.connect()
        try:
            for directory in self.root.iterdir():
                if (
                    directory.is_symlink()
                    or not directory.is_dir()
                    or not re.fullmatch(r"[a-f0-9]{32}-[a-f0-9]{32}", directory.name)
                ):
                    continue
                identifier, token = directory.name.split("-")
                row = db.execute(
                    "SELECT state,lease_token,lease_until_ms FROM jobs WHERE id=?", (identifier,)
                ).fetchone()
                if (
                    row
                    and row["state"] == "running"
                    and row["lease_token"] == token
                    and row["lease_until_ms"] > self.clock()
                ):
                    continue
                shutil.rmtree(directory)
        finally:
            db.close()
        finished = 0
        active = set()
        try:
            while finished < limit:
                while len(active) < MAX_CONCURRENCY and finished + len(active) < limit:
                    job = self.claim()
                    if not job:
                        break
                    active.add(asyncio.create_task(self.run_one(job)))
                if not active:
                    break
                done, active = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
                finished += len(done)
        finally:
            for task in active:
                task.cancel()
            await asyncio.gather(*active, return_exceptions=True)
        return finished

    async def execute_engine(self, job, directory):
        from .engines.documents import DocumentEngine
        from .engines.formats import conversion_notice
        from .engines.images import read_image, sticker
        from .engines.media_edit import MediaEditor, MediaOptions
        from .engines.pdf import PdfOperations
        from .engines.process import MediaError

        args = job["arguments"]
        paths = []
        fingerprints = []
        with self.store.transaction() as db:
            for artifact_id in job["inputs"]:
                row = self.artifacts.owned(
                    db, artifact_id, job["context"], self.clock(), holder="job-" + job["id"]
                )
                paths.append(self.artifacts.path(artifact_id))
                fingerprints.append(row["sha256"])
        import hashlib
        import os

        for path, expected in zip(paths, fingerprints, strict=True):
            digest = hashlib.sha256()
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
                while chunk := stream.read(192 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ArtifactProblem("artifact_changed")
        op = job["operation"]
        if op.startswith(("control_call.", "audiovisual.")):
            from .domains.calls import run

            return await run(job, directory, self)
        if op.startswith("manage_admin.nuclear_"):
            from .domains.nuclear import run

            return await run(job, directory, self)
        if op.startswith("manage_admin."):
            from .domains.admin import run

            return await run(job, directory, self)
        if op.startswith("manage_minecraft."):
            from .domains.minecraft import run

            return await run(job, directory, self)
        if op == "manage_roulette.return":
            from .domains.roulette_return import run

            return await run(job, directory, self)
        if op.startswith("manage_roulette."):
            from .domains.roulette import run

            return await run(job, directory, self)
        if op.startswith("manage_happy_hour."):
            from .domains.happy_media import run

            return await run(job, directory, self)
        if op.startswith("manage_cooperacha."):
            from .domains.cooperacha import run

            return await run(job, directory, self)
        if op == "manage_pack.buy":
            from .domains.packs import run

            return await run(job, directory, self)
        if op.startswith("manage_drive."):
            from .domains.drive import run

            return await run(job, directory, paths, self, self.drive())
        if op == "manage_messages.send":
            from .domains.messages import run

            backend, contacts = self.messages()
            return await run(job, directory, paths, self, backend, contacts)
        if (
            op == "conversation.respond"
            or op.startswith("make_voice.")
            or op == "transcribe_media.run"
        ):
            from .engines.content_jobs import execute

            gemini, tts, asr = self.content()
            return await execute(job, directory, paths, self, gemini, tts, asr)
        if op == "search_web.run":
            from dataclasses import asdict

            backend = self.web()
            if backend is None:
                raise MediaError("web_not_configured")
            items = await backend.search(args["query"], args.get("required_terms", ()))
            from .presentation.search import web_document

            document = web_document(items, args["query"])
            text = document.text()
            return EngineOutput(
                Result(
                    "ok" if items else "empty",
                    "web_results" if items else "web_empty",
                    text,
                    {"items": [asdict(item) for item in items], "document": asdict(document)},
                )
            )
        if op == "send_sticker.run":
            source = Path(__file__).parent / "assets/reactions" / (args["sticker_id"] + ".webp")
            catalog = json.loads(source.with_name("catalog.json").read_text())
            import hashlib

            if (
                hashlib.sha256(source.read_bytes()).hexdigest()
                != catalog["stickers"][args["sticker_id"]]["sha256"]
            ):
                raise MediaError("reaction_asset_changed")
            return EngineOutput(Result("ok", "reaction_ready", ""), (source,))
        if op.startswith("download_media."):
            backend = self.downloads()
            if backend is None:
                raise MediaError("downloads_not_configured")
            from .domains.downloads import validate_url
            from .engines.downloads import is_spotify_url

            if op == "download_media.search" or is_spotify_url(args.get("url", "")):
                spotify = is_spotify_url(args.get("url", ""))
                query = (
                    await backend.resolve_spotify(args["url"], directory)
                    if spotify
                    else args["query"]
                )
                source = "youtube" if spotify else args.get("source", "youtube")
                choices = await backend.search(query, source, directory)
                normalized = []
                seen = set()
                for candidate in choices:
                    url = validate_url(
                        candidate.url, getattr(backend, "adult_sources_enabled", False)
                    )
                    if url in seen or len(normalized) >= 6:
                        continue
                    title = str(candidate.title)
                    if not title.strip():
                        continue
                    seen.add(url)
                    normalized.append(
                        {
                            "url": url,
                            "title": title,
                            "duration": candidate.duration
                            if isinstance(candidate.duration, (int, float))
                            and not isinstance(candidate.duration, bool)
                            and math.isfinite(candidate.duration)
                            and candidate.duration > 0
                            else None,
                            "author": candidate.author,
                            "thumbnail_url": candidate.thumbnail_url,
                        }
                    )
                if not normalized:
                    return EngineOutput(
                        Result(
                            "empty", "download_no_matches", "No encontré coincidencias disponibles."
                        )
                    )
                parameters = {k: v for k, v in args.items() if k not in ("url", "query")}
                from .engines.search_collage import create

                collage_files = ()
                collage_state = "unavailable"
                try:
                    collage = await create(
                        normalized, directory / "videos.jpg", getattr(backend, "thumbnail", None)
                    )
                    collage_files = (collage,)
                    collage_state = "ready"
                except OSError, ValueError:
                    pass
                return EngineOutput(
                    Result(
                        "needs_input",
                        "download_choices",
                        "Spotify aporta metadatos; selecciona una coincidencia real."
                        if spotify
                        else "Elige una coincidencia:",
                        {
                            "choices": normalized,
                            "arguments": parameters,
                            "collage_state": collage_state,
                        },
                    ),
                    collage_files,
                )
            opts = {
                k: args[k]
                for k in (
                    "container",
                    "quality",
                    "start_seconds",
                    "end_seconds",
                    "subtitle_language",
                )
                if k in args
            }
            url = validate_url(args["url"], getattr(backend, "adult_sources_enabled", False))
            output = await backend.download(url, MediaOptions(**opts), directory)
            return EngineOutput(
                Result(
                    "ok",
                    "download_ready",
                    "Archivo preparado.",
                    {"url": url, "format": args["container"], "title": args.get("title", "Video")},
                ),
                (output,),
            )
        if op == "convert_document.run":
            engine = DocumentEngine(directory / "documents")
            source = paths[0].read_bytes()
            from .engines.documents import detect_document_format

            origin = detect_document_format(source)
            output = await engine.convert(source, args["target"])
            notice = conversion_notice(origin, args["target"], output.suffix)
            return EngineOutput(
                Result(
                    "ok",
                    "document_converted",
                    "Conversión lista. " + notice,
                    {"source_format": origin, "target_format": args["target"]},
                ),
                (output,),
            )
        if op == "edit_media.run":
            opts = {
                k: args[k]
                for k in (
                    "container",
                    "quality",
                    "start_seconds",
                    "end_seconds",
                    "subtitle_language",
                )
                if k in args
            }
            output = await MediaEditor(directory / "media").convert_file(
                paths[0], MediaOptions(**opts)
            )
            return EngineOutput(
                Result("ok", "media_edited", "Archivo convertido.", {"format": args["container"]}),
                (output,),
            )
        if op == "make_sticker.run":
            output = await sticker(paths[0], directory)
            return EngineOutput(Result("ok", "sticker_created", "Sticker listo."), (output,))
        if op == "read_image.run":
            text, data = await read_image(paths[0], args["mode"], directory)
            return EngineOutput(
                Result(
                    "ok" if text else "empty",
                    "image_read" if text else "image_empty",
                    text or "No encontré contenido extraíble.",
                    {**data, "mode": args["mode"]},
                )
            )
        if op == "manage_pdf.finish":
            output = await PdfOperations(directory / "pdf").assemble(
                [p.read_bytes() for p in paths]
            )
            return EngineOutput(Result("ok", "pdf_assembled", "PDF terminado."), (output,))
        if op == "manage_pdf.extract":
            output = await PdfOperations(directory / "pdf").extract(
                paths[0].read_bytes(), args["pages"]
            )
            return EngineOutput(Result("ok", "pdf_extracted", "Páginas extraídas."), (output,))
        raise MediaError("engine_unavailable")
