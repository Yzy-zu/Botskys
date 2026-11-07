"""Arranque CLI real, webhook local, SIGTERM y reinicio; ningún envío externo."""

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

import httpx

from botsky.store import SCHEMA_VERSION, Store

OWNER = "525511112222@s.whatsapp.net"
BOT = "525544445555@s.whatsapp.net"


class RuntimeProcessTest(IsolatedAsyncioTestCase):
    async def test_cli_serve_sigterm_and_restart_keep_single_note(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config, providers = root / "config.toml", root / "providers.json"
            config.write_text(
                'instance="process-lab"\naccount="'
                + BOT
                + '"\nepoch=1\ndatabase="private/test.sqlite3"\nactivation_at="2026-01-01T00:00:00Z"\nowner="'
                + OWNER
                + '"\nfriends=[]\nallowed_groups=[]\ntransport="evolution"\nbot_ids=["'
                + BOT
                + '"]\n'
            )
            providers.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "gemini": {"key": "synthetic-key", "model": "explicit-model"},
                        "asr": {},
                        "drive": {},
                        "evolution": {
                            "base_url": "http://127.0.0.1:1",
                            "instance": "provider",
                            "api_key": "synthetic-key",
                            "delivery_enabled": False,
                        },
                        "runtime": {
                            "webhook_token": "a" * 64,
                            "port": 0,
                            "poll_seconds": 0.02,
                            "shutdown_seconds": 0.2,
                        },
                    }
                )
            )
            providers.chmod(0o600)
            payload = {
                "event": "messages.upsert",
                "instance": "provider",
                "sender": BOT,
                "data": {
                    "key": {"id": "PROCESS1", "fromMe": False, "remoteJid": OWNER},
                    "messageTimestamp": int(time.time()),
                    "message": {"conversation": "/nota guardar proceso real"},
                },
            }
            store = Store(root / "private/test.sqlite3")
            for iteration in range(2):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "botsky.connected",
                    "--config",
                    str(config),
                    "--providers",
                    str(providers),
                    "serve",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                try:
                    ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
                    self.assertTrue(ready["ready"])
                    async with httpx.AsyncClient(trust_env=False) as http:
                        response = await http.post(
                            f"http://127.0.0.1:{ready['port']}/webhook/evolution",
                            headers={"Authorization": "Bearer " + "a" * 64},
                            json=payload,
                        )
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(response.json()["duplicate"], bool(iteration))
                    for _ in range(150):
                        with store.transaction() as db:
                            count = db.execute("SELECT count(*) FROM notes").fetchone()[0]
                        if count == 1:
                            break
                        await asyncio.sleep(0.02)
                    self.assertEqual(count, 1)
                    process.send_signal(signal.SIGTERM)
                    self.assertEqual(await asyncio.wait_for(process.wait(), 5), 0)
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
            with store.transaction() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM notes").fetchone()[0], 1)
                self.assertEqual(
                    db.execute("SELECT count(*) FROM outbox WHERE state='pending'").fetchone()[0], 1
                )
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
