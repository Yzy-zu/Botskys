"""Entrada local optativa con proveedores explícitos. No webhook, browser ni env heredado."""

import argparse
import asyncio
import json
from pathlib import Path

from .adapters.local import LocalAdapter, clock_ms
from .config import Settings
from .integrations import Integrations


async def run(args):
    settings = Settings.load(args.config)
    providers = Integrations(settings, args.providers)
    async with providers as app:
        if args.action == "status":
            # Availability is configuration, not proof of remote authorization or human delivery.
            print(
                json.dumps(
                    {
                        "gemini": app.gemini.available,
                        "tts": app.tts.enabled,
                        "asr": app.asr.available,
                        "drive": app.drive is not None,
                        "messenger": app.messenger.available,
                        "groups": app.groups.available,
                        "minecraft": app.minecraft is not None,
                        "calls": False,
                        "incoming_transport": False,
                        "mutations_enabled": providers.profile.get("mutations_enabled", False),
                    }
                )
            )
        elif args.action == "work":
            print(json.dumps({"processed": await app.jobs.run_pending()}))
        else:
            incoming = LocalAdapter(settings).incoming(
                args.id, args.actor, args.chat, args.text, is_group=args.group
            )
            receipt = app.receive(incoming)
            await app.jobs.run_pending()
            db = app.store.connect()
            try:
                row = db.execute(
                    "SELECT result_json FROM inbox WHERE id=?", (receipt.id,)
                ).fetchone()
                print(row[0])
            finally:
                db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Botsky con proveedores propios; entrada de operador local"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--providers", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    sub.add_parser("work")
    local = sub.add_parser("local")
    local.add_argument("text")
    local.add_argument("--id", default="operator-" + str(clock_ms()))
    local.add_argument("--actor", required=True)
    local.add_argument("--chat", required=True)
    local.add_argument("--group", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
