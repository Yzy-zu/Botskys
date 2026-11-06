"""Entradas de operador y proceso continuo con configuración propia explícita."""

import argparse
import asyncio
import json
import signal
from pathlib import Path

from .adapters.local import LocalAdapter, clock_ms
from .assets_import import avatar_status
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
                        "calls": app.calls is not None,
                        "calls_configured": providers.profile.get("call_service", {}).get(
                            "enabled", False
                        ),
                        "incoming_transport_configured": settings.transport == "evolution"
                        and "runtime" in providers.profile,
                        "incoming_transport_running": False,
                        "permissions": providers.policy.document,
                        "gallery_configured": app.gallery is not None,
                        "avatar": avatar_status(settings),
                    }
                )
            )
        elif args.action == "serve":
            from .runtime import Runtime

            runtime = Runtime(app, providers.profile, providers.http, services=providers)
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, stop.set)
            try:
                await runtime.run(
                    stop,
                    on_ready=lambda port: print(
                        json.dumps({"ready": True, "host": "127.0.0.1", "port": port}), flush=True
                    ),
                )
            finally:
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.remove_signal_handler(sig)
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
    sub.add_parser(
        "serve", help="proceso continuo propio; requiere configuración runtime explícita"
    )
    local = sub.add_parser("local")
    local.add_argument("text")
    local.add_argument("--id", default="operator-" + str(clock_ms()))
    local.add_argument("--actor", required=True)
    local.add_argument("--chat", required=True)
    local.add_argument("--group", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
