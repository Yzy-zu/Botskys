"""Proceso AV propio supervisado; no abre navegador al importar o consultar estado."""

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit


class ManagedCalls:
    def __init__(self, settings, config, live):
        self.settings, self.config, self.live = settings, config, live
        self.process = None
        self.url = None

    async def start(self):
        c, s = self.config, self.settings
        if c.get("allow_browser_launch") is not True:
            raise ValueError("browser_not_authorized")
        if s.calls is None or s.transport != "evolution":
            raise ValueError("call_policy_required")
        port = c.get("port", 0)
        executable = c.get("executable")
        if (
            type(port) is not int
            or not 0 <= port <= 65535
            or not isinstance(executable, str)
            or not Path(executable).is_absolute()
        ):
            raise ValueError("call_service_configuration_invalid")
        token = c.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
            raise ValueError("call_service_token_invalid")
        node = shutil.which("node")
        main = Path(__file__).resolve().parents[2] / "calls/main.cjs"
        if node is None or not main.is_file():
            raise ValueError("call_service_not_installed")
        payload = {
            "projectRoot": str(s.root),
            "document": s.calls.document,
            "token": token,
            "live": self.live,
            "port": port,
            "executable": executable,
            "allowBrowserLaunch": True,
            "agendaTimers": c.get("agenda_timers", False),
        }
        try:
            self.process = await asyncio.create_subprocess_exec(
                node,
                str(main),
                "--run",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                limit=65536,
            )
            self.process.stdin.write(json.dumps(payload).encode() + b"\n")
            await self.process.stdin.drain()
            self.process.stdin.close()
            async with asyncio.timeout(120):
                line = await self.process.stdout.readline()
            value = json.loads(line)
            url = urlsplit(value.get("url", ""))
            if (
                value.get("ready") is not True
                or value.get("revision") != s.calls.revision
                or url.scheme != "http"
                or url.hostname != "127.0.0.1"
                or not url.port
                or url.path
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("call_service_invalid_ready")
            self.url = value["url"]
            return self.url
        except BaseException:
            await self.close()
            raise

    async def wait(self):
        if self.process:
            await self.process.wait()
            raise RuntimeError("call_service_exited")

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 15)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None
