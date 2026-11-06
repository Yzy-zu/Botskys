"""Composición local. Ningún transporte o proveedor remoto se inicia implícitamente."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from . import access, delivery, ingress
from .adapters.local import LocalAdapter, clock_ms
from .commands.router import CommandError, Router
from .config import Settings
from .contracts import DeliveryAck, Result
from .domains import notes
from .store import Store


class Application:
    def __init__(self, settings, *, clock=clock_ms, router=None):
        self.settings, self.clock = settings, clock
        self.router = router or Router()
        self.store = Store(settings.database)

    def admit(self, incoming):
        def prepare(context):
            if denied := ingress.freshness(incoming, self.settings, self.clock()):
                return None, denied, "rejected"
            try:
                command = self.router.parse(incoming.text)
            except CommandError as exc:
                return None, Result("needs_input", exc.code, exc.reply), "completed"
            if command is None:
                return None, None, "ignored"
            if denied := access.authorize(command.spec.permission, context, self.settings):
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
        args = command["arguments"]
        operation = command["operation"]
        if operation == "core.help":
            return Result("ok", "help", self.router.registry.help(args.get("topic", "")))
        if operation == "core.estado":
            return self.store.state(db, context, args["id"])
        if operation == "core.cancelar":
            return self.store.cancel(db, context, args["id"])
        if operation == "save_note.run":
            return notes.save(db, context, args, effect_id, now)
        if operation == "find_notes.run":
            return notes.find(db, context, args, now)
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
        print(part.text, flush=True)
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
    sub.add_parser("init", help="inicializa solo almacenamiento propio")
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
    if args.command == "init":
        print("Almacenamiento propio listo; ningún proveedor activado.")
        return 0
    incoming = LocalAdapter(settings).incoming(
        args.message_id or uuid4().hex, args.actor, args.chat, args.text, is_group=args.group
    )
    receipt = app.receive(incoming)
    if receipt.state == "completed":
        app.deliver(receipt.id, StdoutTransport())
    elif receipt.result:
        print(receipt.result.text)
    print(
        json.dumps({"receipt": receipt.id, "state": receipt.state, "duplicate": receipt.duplicate})
    )
    return 0
