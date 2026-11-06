"""Explicit, bounded SSH adapter for an owner-controlled Bedrock server.

This module never discovers a host or container. The configured worker receives
one JSON request on stdin and performs a closed set of operations remotely.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shlex
import signal
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

MAX_OUTPUT = 128 * 1024
MAX_REQUEST = 16 * 1024
TIMEOUT_SECONDS = 30
BACKUP_TIMEOUT_SECONDS = 1260
_ACTIONS = {
    "status",
    "players",
    "worlds",
    "mods",
    "config",
    "start",
    "stop",
    "restart",
    "backup",
    "recover",
    "enable_mod",
    "disable_mod",
    "console",
}
_QUERIES = {"status", "players", "worlds", "mods", "config", "diagnostics", "discover"}
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class MinecraftRemoteError(Exception):
    """Stable adapter failure without remote command output."""

    def __init__(self, code: str, *, uncertain: bool = False) -> None:
        self.code = code
        self.uncertain = uncertain
        super().__init__(code)


class MinecraftLocalValidationError(ValueError):
    """A rejected request known not to have crossed the SSH boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MinecraftConfig:
    host_alias: str
    container: str
    base_path: str
    worker_path: str
    ssh_binary: str = "ssh"
    use_sudo: bool = False

    def validate(self) -> None:
        if not _TOKEN.fullmatch(self.host_alias) or self.host_alias.startswith("-"):
            raise ValueError("invalid_ssh_alias")
        if not _TOKEN.fullmatch(self.container):
            raise ValueError("invalid_container")
        base = PurePosixPath(self.base_path)
        worker = PurePosixPath(self.worker_path)
        if not base.is_absolute() or ".." in base.parts or str(base) != self.base_path.rstrip("/"):
            raise ValueError("invalid_base_path")
        if not worker.is_absolute() or ".." in worker.parts:
            raise ValueError("invalid_worker_path")
        if not _TOKEN.fullmatch(self.ssh_binary):
            raise ValueError("invalid_ssh_binary")
        if type(self.use_sudo) is not bool:
            raise ValueError("invalid_sudo_mode")


class MinecraftRemote:
    def __init__(self, config: MinecraftConfig, *, runner=None) -> None:
        config.validate()
        self.config = config
        self._runner = runner or _run_ssh
        identity = "\0".join((config.host_alias.casefold(), config.container, config.base_path))
        self.server_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    async def query(
        self, action: Literal["status", "players", "worlds", "mods", "config", "diagnostics"] | str
    ) -> dict[str, Any]:
        if action not in _QUERIES:
            raise ValueError("invalid_query_action")
        return await self._request(action, {})

    async def change(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        clean = self.validate_change(action, params)
        return await self.change_validated(action, clean)

    async def change_validated(self, action: str, clean: dict[str, Any]) -> dict[str, Any]:
        """Dispatch parameters already checked by ``validate_change``."""
        try:
            result = await self._request(action, clean)
            if action in {"start", "restart"} and result.get("requires_healthcheck") is True:
                deadline = asyncio.get_running_loop().time() + 90
                while asyncio.get_running_loop().time() < deadline:
                    observed = await self.query("status")
                    if observed.get("game_status") == "ready":
                        return {**result, "game_status": "ready", "verified": True}
                    if observed.get("game_status") == "failed":
                        return {
                            "status": "uncertain",
                            "code": "game_startup_failed",
                            "recovery_available": True,
                        }
                    await asyncio.sleep(2)
                return {
                    "status": "uncertain",
                    "code": "game_startup_unverified",
                    "recovery_available": True,
                }
            # The worker returns this only when it observed a running server
            # before creating the backup; no backup side effect was dispatched.
            if action == "backup" and result.get("status") == "needs_input":
                return {**result, "dispatched": False}
            return result
        except MinecraftRemoteError as exc:
            if exc.uncertain:
                return {
                    "status": "uncertain",
                    "action": action,
                    "message": "No pude confirmar si el cambio terminó; no lo repetiré.",
                }
            raise

    def validate_change(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate and size a mutation before the caller records dispatch."""
        if action not in {
            "start",
            "stop",
            "restart",
            "backup",
            "recover",
            "enable_mod",
            "disable_mod",
            "console",
        }:
            raise MinecraftLocalValidationError("invalid_change_action")
        try:
            clean = _validate_params(action, params or {})
            payload = json.dumps(
                {
                    "action": action,
                    "params": clean,
                    "container": self.config.container,
                    "base_path": self.config.base_path,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(payload) > MAX_REQUEST:
                raise MinecraftLocalValidationError("request_too_large")
        except MinecraftLocalValidationError:
            raise
        except ValueError as exc:
            raise MinecraftLocalValidationError(str(exc)) from exc
        return clean

    async def _request(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(
            {
                "action": action,
                "params": params,
                "container": self.config.container,
                "base_path": self.config.base_path,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > MAX_REQUEST:
            raise ValueError("request_too_large")
        prefix = "sudo -n " if self.config.use_sudo else ""
        remote_command = f"{prefix}python3 -I {shlex.quote(self.config.worker_path)}"
        argv = [
            self.config.ssh_binary,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=5",
            self.config.host_alias,
            remote_command,
        ]
        try:
            if action == "backup" and self._runner is _run_ssh:
                raw = await _run_ssh(argv, payload, timeout_seconds=BACKUP_TIMEOUT_SECONDS)
            else:
                raw = await self._runner(argv, payload)
        except TimeoutError as exc:
            raise MinecraftRemoteError(
                "remote_timeout",
                uncertain=action
                in {"start", "stop", "restart", "backup", "enable_mod", "disable_mod", "console"},
            ) from exc
        except MinecraftRemoteError as exc:
            mutating = action not in _QUERIES - {"diagnostics"}
            if mutating and exc.code in {
                "ssh_failed",
                "output_too_large",
                "invalid_remote_response",
            }:
                raise MinecraftRemoteError(exc.code, uncertain=True) from exc
            raise
        except asyncio.CancelledError:
            raise
        except OSError as exc:
            raise MinecraftRemoteError("ssh_unavailable") from exc
        if len(raw) > MAX_OUTPUT:
            raise MinecraftRemoteError(
                "output_too_large",
                uncertain=action not in {"status", "players", "worlds", "mods", "config"},
            )
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MinecraftRemoteError(
                "invalid_remote_response",
                uncertain=action not in {"status", "players", "worlds", "mods", "config"},
            ) from exc
        if not isinstance(result, dict) or not isinstance(result.get("status"), str):
            raise MinecraftRemoteError(
                "invalid_remote_response",
                uncertain=action not in {"status", "players", "worlds", "mods", "config"},
            )
        return result


async def _run_ssh(argv: list[str], payload: bytes, *, timeout_seconds=None) -> bytes:
    """Run SSH without a local shell and kill its process group on timeout/cancel."""
    launch = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
        )
    )
    cancelled_during_launch = False
    while True:
        try:
            process = await asyncio.shield(launch)
            break
        except asyncio.CancelledError:
            cancelled_during_launch = True
        except OSError:
            if cancelled_during_launch:
                raise asyncio.CancelledError
            raise
    if cancelled_during_launch:
        await _stop_process(process)
        raise asyncio.CancelledError
    assert process.stdin is not None and process.stdout is not None
    stdin = process.stdin
    stdout = process.stdout

    async def exchange() -> bytes:
        stdin.write(payload)
        await stdin.drain()
        stdin.close()
        output = bytearray()
        while chunk := await stdout.read(16384):
            if len(output) < MAX_OUTPUT + 1:
                output.extend(chunk[: MAX_OUTPUT + 1 - len(output)])
        await process.wait()
        if len(output) > MAX_OUTPUT:
            raise MinecraftRemoteError("output_too_large")
        if process.returncode != 0:
            raise MinecraftRemoteError("ssh_failed")
        return bytes(output)

    try:
        return await asyncio.wait_for(
            exchange(), TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        )
    except TimeoutError, asyncio.CancelledError:
        await _stop_process(process)
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            raise asyncio.CancelledError
        raise TimeoutError
    except BaseException:
        await _stop_process(process)
        raise


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), 1)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


def _validate_params(action: str, params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("invalid_params")
    if action in {"start", "stop", "restart", "backup", "recover"}:
        if params:
            raise ValueError("unexpected_params")
        return {}
    if action in {"enable_mod", "disable_mod"}:
        if set(params) != {"name"}:
            raise ValueError("invalid_mod_params")
        name = params["name"]
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 128
            or any(ord(char) < 32 for char in name)
        ):
            raise ValueError("invalid_mod_name")
        return {"name": name.strip()}
    if action == "console":
        if set(params) != {"command"} or not isinstance(params["command"], str):
            raise ValueError("invalid_console_params")
        command = params["command"].strip().lstrip("/")
        allowed = {"list", "save", "time query daytime", "weather query"}
        if command not in allowed:
            raise ValueError("console_command_not_allowed")
        return {"command": command}
    raise ValueError("invalid_action")
