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
        drive=None,
        directory=None,
        messenger=None,
        daily_roll=None,
        blackjack_deck=None,
        gallery=None,
        photo_transport=None,
        gallery_chats=frozenset(),
        groups=None,
        roulette_chats=frozenset(),
        allow_roulette_admins=False,
        roulette_choice=None,
        minecraft=None,
        nuclear_enabled=False,
        calls=None,
        operations=None,
    ):
        self.settings, self.clock = settings, clock
        self.router = router or Router()
        self.downloads = downloads
        self.web = web
        self.gemini, self.tts, self.asr = gemini, tts, asr
        from .domains.contacts import Directory

        self.drive = drive
        self.directory = directory if directory is not None else Directory()
        self.messenger = messenger
        self.daily_roll, self.blackjack_deck = daily_roll, blackjack_deck
        self.gallery, self.photo_transport, self.gallery_chats = (
            gallery,
            photo_transport,
            frozenset(gallery_chats),
        )
        self.store = Store(settings.database)
        self.calls = calls
        self.operations = operations
        self.minecraft = minecraft
        self.nuclear_enabled = bool(nuclear_enabled)
        self.groups, self.roulette_chats, self.allow_roulette_admins, self.roulette_choice = (
            groups,
            frozenset(roulette_chats),
            bool(allow_roulette_admins),
            roulette_choice,
        )
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
            drive=lambda: self.drive,
            messages=lambda: (self.messenger, self.directory),
            gallery=lambda: (self.gallery, self.photo_transport, self.gallery_chats),
            groups=lambda: self.groups,
            minecraft=lambda: self.minecraft,
            calls=lambda: self.calls,
            operations=lambda: self.operations,
            nuclear_enabled=lambda: self.nuclear_enabled,
            roulette_policy=lambda: (
                self.roulette_chats,
                self.allow_roulette_admins,
                self.roulette_choice,
            ),
        )
        from .scheduler import Scheduler

        self.scheduler = Scheduler(self)

    async def poll_call_notices(self):
        from .domains.call_notices import poll

        return await poll(self)

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
            if not access.authorize("friend", context, self.settings):
                from .domains.economy import credit_message

                credit_message(db, context, incoming, self.clock())
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
            if self.operations and (
                denied := self.operations.authorize(context, command.spec.operation)
            ):
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
        if self.operations and (denied := self.operations.authorize(context, spec.operation)):
            return denied
        if denied := bot.gate(db, context, spec, now):
            return denied
        args = command["arguments"]
        operation = command["operation"]
        if spec.family == "control_call" or spec.family.startswith("audiovisual."):
            from .domains import calls

            return calls.execute(db, context, spec, args, now, self)
        if spec.family == "manage_admin":
            from .domains import admin

            return admin.execute(db, context, spec, args, now, self)
        if spec.family == "manage_minecraft":
            from .domains import minecraft

            return minecraft.execute(db, context, spec, args, now, self)
        if spec.family == "manage_roulette":
            from .domains import roulette

            return roulette.execute(db, context, spec, args, now, self)
        if spec.family == "manage_cooperacha":
            from .domains import cooperacha

            return cooperacha.execute(db, context, spec, args, now, self)
        if spec.family == "manage_pack":
            from .domains import packs

            return packs.execute(db, context, spec, args, now, self)
        if spec.family == "manage_happy_hour":
            from .domains import happy_hour

            return happy_hour.execute(db, context, spec.original_action, args, now, self)
        if spec.family == "manage_economy":
            from .domains import economy

            return economy.execute(db, context, spec.original_action, now, self.daily_roll)
        if spec.family == "manage_blackjack":
            from .domains import blackjack

            return blackjack.execute(db, context, spec.original_action, args, now, self)
        if spec.family == "make_prank":
            from .domains.prank import execute

            return execute(context, args)
        if spec.family == "manage_drive":
            from .domains import drive

            return drive.execute(db, context, spec, command, now, self)
        if spec.family == "manage_messages":
            from .domains import messages

            return messages.execute(db, context, spec, command, now, self)
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
        if spec.family in ("manage_memory", "manage_reminder", "manage_school", "manage_poll"):
            from .domains import organization

            return organization.execute(db, context, spec, command, now, self)
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
    sub.add_parser("tick", help="reserva avisos locales vencidos sin transporte remoto")
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
    if args.command == "tick":
        print(json.dumps({"notifications_queued": app.scheduler.tick()}))
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
