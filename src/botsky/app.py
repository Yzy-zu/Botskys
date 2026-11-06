"""Composición local. Ningún transporte o proveedor remoto se inicia implícitamente."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from . import access, delivery, ingress, interactions
from .adapters.local import LocalAdapter, clock_ms
from .artifacts import ArtifactProblem, Artifacts
from .commands.router import CommandError, Router
from .config import Settings
from .contracts import CommandContext, DeliveryAck, Result
from .domains import ai, bot, notes
from .jobs import Jobs
from .store import Store


class Application:
    def __init__(
        self,
        settings,
        *,
        clock=clock_ms,
        router=None,
        downloads=None,
        web=None,
        gemini=None,
        tts=None,
        asr=None,
    ):
        self.settings, self.clock = settings, clock
        self.router = router or Router()
        self.downloads = downloads
        self.web = web
        self.gemini, self.tts, self.asr = gemini, tts, asr
        self.store = Store(settings.database)
        self.artifacts = Artifacts(self.store, settings.root / "private/artifacts")
        self.jobs = Jobs(
            self.store,
            settings,
            self.artifacts,
            clock,
            policy=lambda: self.settings,
            downloads=lambda: self.downloads,
            web=lambda: self.web,
            content=lambda: (self.gemini, self.tts, self.asr),
        )

    def attach_local(self, incoming, path):
        """Adjunto explícito de operador; nunca una ruta extraída de texto de chat."""
        from dataclasses import replace

        context = CommandContext(
            incoming.id, incoming.instance, incoming.account, incoming.scope, self.settings.epoch, 0
        )
        if access.authorize("friend", context, self.settings):
            raise ArtifactProblem("artifact_access_denied")
        artifact_id = self.artifacts.import_local(path, context, incoming.message_id, self.clock())
        return replace(incoming, attachments=(*incoming.attachments, artifact_id))

    def admit(self, incoming):
        def prepare(context, db):
            if denied := ingress.freshness(incoming, self.settings, self.clock()):
                return None, denied, "rejected"
            try:
                command = self.router.parse(incoming.text)
            except CommandError as exc:
                return None, Result("needs_input", exc.code, exc.reply), "completed"
            if command is None:
                command = ai.invoked(
                    db, context, incoming, self.settings, self.router.registry, self.clock()
                )
            if command is None:
                command = interactions.resume_file(
                    db, context, incoming, self.router.registry, self.clock()
                )
            if command is None:
                return None, None, "ignored"
            if denied := access.authorize(command.spec.permission, context, self.settings):
                return command, denied, "completed"
            if denied := bot.gate(db, context, command.spec, self.clock()):
                return command, denied, "completed"
            return command, None, "queued"

        return self.store.admit(incoming, self.settings, prepare)

    def receive(self, incoming, *, execute=True):
        receipt = self.admit(incoming)
        if receipt.state == "queued" and execute:
            completed = self.process(receipt.id)
            if receipt.duplicate:
                from dataclasses import replace

                completed = replace(completed, duplicate=True)
            return completed
        return receipt

    def process(self, receipt_id):
        return self.store.execute(receipt_id, self.settings, self.clock(), self._handle)

    def _handle(self, db, context, path, command, effect_id, now):
        spec = self.router.registry.paths.get(path)
        if command["version"] != 1 or spec is None or spec.operation != command["operation"]:
            return Result(
                "failed",
                "command_version_unavailable",
                "La versión de este comando no está disponible; no se reinterpretó.",
            )
        if denied := access.authorize(spec.permission, context, self.settings):
            return denied
        if denied := bot.gate(db, context, spec, now):
            return denied
        args = command["arguments"]
        operation = command["operation"]
        if spec.family == "manage_conversation":
            caps = {
                "comandos": True,
                "notas": True,
                "medios_locales": True,
                "gemini_configurado": self.gemini is not None
                and getattr(self.gemini, "available", True),
                "tts_configurado": self.tts is not None and getattr(self.tts, "enabled", True),
                "asr_configurado": self.asr is not None and getattr(self.asr, "available", True),
                "descargas_configuradas": self.downloads is not None
                and getattr(self.downloads, "enabled", True),
            }
            return bot.execute(db, context, spec.original_action, args, now, caps)
        if spec.family in ("conversation", "make_voice", "transcribe_media"):
            return ai.execute(db, context, spec, command, now, self)
        if operation == "core.help":
            return Result("ok", "help", self.router.registry.help(args.get("topic", "")))
        if operation == "core.estado":
            return self.store.state(db, context, args["id"])
        if operation == "core.cancelar":
            return self.store.cancel(db, context, args["id"])
        if operation == "core.confirmar":
            return interactions.confirm(db, context, args["id"], now)
        if operation == "save_note.run":
            return notes.save(db, context, args, effect_id, now)
        if operation == "find_notes.run":
            return notes.find(db, context, args, now)
        if spec.family == "manage_pdf":
            from .domains import pdf

            return pdf.execute(db, context, spec, command, now, self.artifacts, self.jobs)
        if spec.family == "download_media":
            from .domains import downloads

            return downloads.execute(
                db, context, spec, args, now, self.jobs, self.artifacts, self.downloads
            )
        if spec.family == "send_sticker":
            return self.jobs.reserve(db, context, spec.operation, args, [], now)
        if operation in (
            "convert_document.run",
            "edit_media.run",
            "make_sticker.run",
            "read_image.run",
            "manage_pdf.extract",
        ):
            row = db.execute("SELECT * FROM inbox WHERE id=?", (context.receipt_id,)).fetchone()
            try:
                inputs = self.artifacts.resolve(db, context, row, now)
                if not inputs:
                    return interactions.wait_file(db, context, spec, command, now)
                if len(inputs) != 1:
                    return Result(
                        "needs_input",
                        "one_attachment_required",
                        "Este comando requiere exactamente un archivo.",
                    )
                return self.jobs.reserve(db, context, operation, args, inputs, now)
            except ArtifactProblem as exc:
                return Result(
                    "failed",
                    exc.code,
                    "No puedo usar ese archivo en este ámbito. Adjunta uno propio y disponible.",
                )
        if spec.family == "search_web":
            if self.web is None or getattr(self.web, "enabled", True) is not True:
                return Result(
                    "failed",
                    "web_not_configured",
                    "El buscador remoto no está habilitado en este laboratorio.",
                )
            return self.jobs.reserve(db, context, spec.operation, args, [], now)
        return Result(
            "failed",
            "capability_unavailable",
            f"{spec.command}: función pendiente de {spec.block}; no se ejecutó.",
            {"block": spec.block},
        )

    def recover(self, *, limit=100):
        return [self.process(receipt_id) for receipt_id in self.store.queued(self.settings, limit)]

    def deliver(self, receipt_id, transport, *, retry_failed=False):
        return delivery.deliver(
            self.store, receipt_id, self.settings, transport, self.clock, retry_failed=retry_failed
        )


class StdoutTransport:
    def send(self, part):
        if part.text:
            print(part.text, flush=True)
        for identifier in part.artifacts:
            print("Archivo retenido: " + identifier, flush=True)
        return DeliveryAck(True, f"stdout-{part.receipt_id}-{part.position}")


def main():
    parser = argparse.ArgumentParser(description="Botsky: laboratorio local sin transporte remoto")
    parser.add_argument("--config", type=Path, default=Path("config.example.toml"))
    sub = parser.add_subparsers(dest="command", required=True)
    parse = sub.add_parser("parse", help="parser puro sin DB, IA ni proveedores")
    parse.add_argument("text")
    local = sub.add_parser("local", help="entrada sintética de operador local")
    local.add_argument("text")
    local.add_argument("--actor", default="owner-local")
    local.add_argument("--chat", default="owner-local")
    local.add_argument("--group", action="store_true")
    local.add_argument("--message-id", default=None)
    local.add_argument(
        "--file", type=Path, action="append", default=[], help="adjunto sintético local explícito"
    )
    local.add_argument("--quote", default=None, help="ID de mensaje local citado exactamente")
    local.add_argument(
        "--source-ms",
        type=int,
        default=None,
        help="timestamp de origen estable para simular reentrega",
    )
    sub.add_parser("init", help="inicializa solo almacenamiento propio")
    sub.add_parser("work", help="ejecuta trabajos locales pendientes; no activa proveedores")
    send = sub.add_parser(
        "deliver", help="aceptación por STDOUT de partes pendientes, sin transporte remoto"
    )
    send.add_argument("id")
    args = parser.parse_args()
    if args.command == "parse":
        try:
            command = Router().parse(args.text)
        except CommandError as exc:
            print(exc.reply, file=sys.stderr)
            return 2
        print(command.canonical() if command else "null")
        return 0
    settings = Settings.load(args.config)
    app = Application(settings)
    if args.command == "work":
        import asyncio

        from .local_files import WorkerBusy

        try:
            count = asyncio.run(app.jobs.run_pending())
        except WorkerBusy as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(json.dumps({"jobs_processed": count}))
        return 0
    if args.command == "deliver":
        print(json.dumps({"parts_accepted": app.deliver(args.id, StdoutTransport())}))
        return 0
    if args.command == "init":
        print("Almacenamiento propio listo; ningún proveedor activado.")
        return 0
    incoming = LocalAdapter(settings).incoming(
        args.message_id or uuid4().hex,
        args.actor,
        args.chat,
        args.text,
        is_group=args.group,
        source_ms=args.source_ms,
        quoted_message_id=args.quote,
    )
    for path in args.file:
        incoming = app.attach_local(incoming, path)
    receipt = app.receive(incoming)
    if receipt.state == "completed":
        app.deliver(receipt.id, StdoutTransport())
        if receipt.result and receipt.result.code == "job_queued":
            print(receipt.result.text)
    elif receipt.result:
        print(receipt.result.text)
    print(
        json.dumps({"receipt": receipt.id, "state": receipt.state, "duplicate": receipt.duplicate})
    )
    return 0
