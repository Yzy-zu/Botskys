# fmt: off
"""Fixed stdlib worker invoked remotely by minecraft_remote.py.

The worker accepts exactly one JSON request on stdin. It uses argv-based
subprocess calls and only accesses the configured Bedrock directory.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_INPUT = 16 * 1024
MAX_OUTPUT = 128 * 1024
MAX_SCAN = 1000
MAX_BACKUP_BYTES = 1024 * 1024 * 1024
MAX_BACKUP_FILES = 100_000
BACKUP_TIMEOUT_SECONDS = 25
WORKER_TIMEOUT_SECONDS = 25
PACK_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


class WorkerError(Exception):
    pass


def _run(argv: list[str], *, timeout: int = 15, check: bool = True) -> str:
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise WorkerError("remote_command_unavailable") from exc
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WorkerError("remote_command_timeout")
            for key, _ in selector.select(min(remaining, 0.25)):
                chunk = os.read(key.fd, min(16384, MAX_OUTPUT + 1 - len(output)))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if len(output) > MAX_OUTPUT:
                    raise WorkerError("remote_output_too_large")
        returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except (subprocess.TimeoutExpired, WorkerError) as exc:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        if isinstance(exc, WorkerError):
            raise
        raise WorkerError("remote_command_timeout") from exc
    finally:
        selector.close()
        process.stdout.close()
    if check and returncode:
        raise WorkerError("remote_command_failed")
    return output.decode("utf-8", "replace")


def _props(data: Path) -> dict[str, str]:
    path = data / "server.properties"
    result: dict[str, str] = {}
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
            return result
        for line in path.read_text("utf-8", errors="replace").splitlines():
            match = re.fullmatch(r"\s*([A-Za-z0-9_-]+)\s*=\s*(.*?)\s*", line)
            if match:
                result[match.group(1).lower()] = match.group(2).strip("\"'")
    except OSError:
        return {}
    return result


def _active_world(data: Path) -> str:
    name = _props(data).get("level-name", "")
    if not name or name in {".", ".."} or Path(name).name != name:
        raise WorkerError("invalid_world_name")
    world = data / "worlds" / name
    if world.is_symlink() or not world.is_dir():
        raise WorkerError("world_unavailable")
    return name


def _json_file(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.exists():
        return []
    if not path.is_file() or path.stat().st_size > MAX_OUTPUT:
        raise WorkerError("invalid_pack_file")
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkerError("invalid_pack_file") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise WorkerError("invalid_pack_file")
    return value


def _atomic_json(path: Path, value: list[dict[str, Any]]) -> None:
    if path.is_symlink():
        raise WorkerError("unsafe_pack_file")
    fd, temp_name = tempfile.mkstemp(prefix=".zhana-packs-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _backup(root: Path, data: Path, container: str, *, run: Callable[..., str]) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir() or data.is_symlink() or not data.is_dir():
        raise WorkerError("data_unavailable")
    state_raw = run(["docker", "inspect", "--format", "{{json .State}}", container], check=False).strip()
    if not state_raw:
        raise WorkerError("container_state_unknown")
    try:
        state = json.loads(state_raw)
    except json.JSONDecodeError as exc:
        raise WorkerError("container_state_unknown") from exc
    if state.get("Status") == "running":
        return {"status": "needs_input", "message": "Apaga el servidor explícitamente antes de crear el respaldo."}
    if state.get("Status") not in {"exited", "created"}:
        raise WorkerError("container_state_unknown")

    backup_dir = root / "zhana-backups"
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    if backup_dir.is_symlink() or not backup_dir.is_dir():
        raise WorkerError("unsafe_backup_path")
    os.chmod(backup_dir, 0o700)
    filename = f"minecraft-{uuid.uuid4().hex}.tar.gz"
    target = backup_dir / filename
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    started = time.monotonic()
    bytes_seen = 0
    entries_seen = 0
    try:
        with os.fdopen(fd, "wb") as archive_stream:
            with tarfile.open(fileobj=archive_stream, mode="w:gz") as archive:
                pending: list[tuple[Path, str]] = [(data, "data")]
                data_root = data.resolve(strict=True)
                while pending:
                    path, relative = pending.pop()
                    if time.monotonic() - started > BACKUP_TIMEOUT_SECONDS:
                        raise WorkerError("backup_timeout")
                    st = path.lstat()
                    if path.is_symlink():
                        continue
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(data_root):
                        raise WorkerError("backup_path_escape")
                    entries_seen += 1
                    if entries_seen > MAX_BACKUP_FILES:
                        raise WorkerError("backup_file_limit")
                    if path.is_dir():
                        info = tarfile.TarInfo(relative.rstrip("/") + "/")
                        info.type = tarfile.DIRTYPE
                        info.mode = st.st_mode & 0o777
                        info.mtime = int(st.st_mtime)
                        archive.addfile(info)
                        try:
                            children = sorted(path.iterdir(), key=lambda child: child.name, reverse=True)
                        except OSError as exc:
                            raise WorkerError("backup_read_failed") from exc
                        for child in children:
                            if child.name in {".", ".."} or "/" in child.name:
                                continue
                            pending.append((child, f"{relative}/{child.name}"))
                    elif path.is_file():
                        if st.st_size < 0 or bytes_seen + st.st_size > MAX_BACKUP_BYTES:
                            raise WorkerError("backup_size_limit")
                        fd_in = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                        try:
                            opened = os.fstat(fd_in)
                            if not stat.S_ISREG(opened.st_mode) or opened.st_ino != st.st_ino or opened.st_dev != st.st_dev:
                                raise WorkerError("backup_file_changed")
                            info = tarfile.TarInfo(relative)
                            info.size = opened.st_size
                            info.mode = opened.st_mode & 0o777
                            info.mtime = int(opened.st_mtime)
                            with os.fdopen(fd_in, "rb", closefd=False) as source:
                                archive.addfile(info, source)
                            bytes_seen += opened.st_size
                            if time.monotonic() - started > BACKUP_TIMEOUT_SECONDS:
                                raise WorkerError("backup_timeout")
                        finally:
                            os.close(fd_in)
            archive_stream.flush()
            os.fsync(archive_stream.fileno())
        os.chmod(target, 0o600)
    except BaseException:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        raise
    return {"status": "ok", "backup": filename, "bytes": bytes_seen, "files": entries_seen}


def _players(root: Path, container: str, *, run: Callable[..., str]) -> dict[str, Any]:
    state = run(["docker", "inspect", "--format", "{{.State.Status}}", container], check=False).strip()
    if state != "running":
        if state in {"exited", "created", "paused"}:
            return {"status": "offline", "online": False, "players_known": False, "count": None, "max": None, "players": []}
        return {"status": "unknown", "online": None, "players_known": False, "count": None, "max": None, "players": []}
    if root.is_symlink() or not root.is_dir():
        return {"status": "online", "online": True, "players_known": False, "count": None, "max": None, "players": []}
    home = Path.home()
    if home.is_symlink() or not home.is_dir():
        raise WorkerError("players_lock_unavailable")
    cache_dir = home / ".cache"
    app_dir = cache_dir / "zhana"
    for directory in (cache_dir, app_dir):
        if directory.is_symlink():
            raise WorkerError("players_lock_unavailable")
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
    lock_key = hashlib.sha256(f"{container}\0{root}".encode()).hexdigest()[:24]
    lock_path = app_dir / f"minecraft-players-{lock_key}.lock"
    if lock_path.is_symlink():
        raise WorkerError("unsafe_players_lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        deadline = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    return {"status": "online", "online": True, "players_known": False, "count": None, "max": None, "players": []}
                time.sleep(0.05)
        try:
            sent_at = time.time()
            run(["docker", "exec", container, "send-command", "list"], timeout=10)
            time.sleep(0.25)
            log = run(["docker", "logs", "--since", f"{sent_at:.6f}", "--timestamps", container], timeout=10)
            matches: list[tuple[int, int, str]] = []
            pattern = re.compile(r"^(\S+)\s+.*?There are\s+(\d+)/(\d+)\s+players online:([^\r\n]*)", re.IGNORECASE)
            for line in log.splitlines():
                match = pattern.match(line)
                if not match:
                    continue
                try:
                    timestamp = datetime.fromisoformat(match.group(1).replace("Z", "+00:00")).timestamp()
                except ValueError:
                    continue
                if timestamp + 0.001 < sent_at:
                    continue
                matches.append((int(match.group(2)), int(match.group(3)), match.group(4)))
            if len(matches) != 1:
                return {"status": "online", "online": True, "players_known": False, "count": None, "max": None, "players": []}
            count, maximum, raw_names = matches[0]
            names = [name.strip() for name in raw_names.split(",") if name.strip()]
            if count > maximum or count > 100 or maximum > 10000 or any(len(name) > 64 or any(ord(ch) < 32 for ch in name) for name in names):
                return {"status": "online", "online": True, "players_known": False, "count": None, "max": None, "players": []}
            if count == 0:
                names = []
            elif names and len(names) != count:
                names = []
            return {"status": "online", "online": True, "players_known": True, "count": count, "max": maximum, "players": names}
        except (WorkerError, OSError, subprocess.SubprocessError):
            return {"status": "online", "online": True, "players_known": False, "count": None, "max": None, "players": []}
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _installed_packs(data: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for pack_type, folder in (("behavior", "behavior_packs"), ("resource", "resource_packs")):
        manifests = data / folder
        if not manifests.is_dir() or manifests.is_symlink():
            continue
        for entry in list(manifests.iterdir())[:MAX_SCAN]:
            if not entry.is_dir() or entry.is_symlink():
                continue
            manifest = entry / "manifest.json"
            if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 128 * 1024:
                continue
            try:
                content = json.loads(manifest.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            header = content.get("header") if isinstance(content, dict) else None
            if not isinstance(header, dict):
                continue
            pack_id = str(header.get("uuid", ""))
            if not PACK_ID.fullmatch(pack_id):
                continue
            raw_name = header.get("name")
            name = raw_name if isinstance(raw_name, str) and raw_name not in {"", "pack.name"} else entry.name
            found.append({
                "pack_id": pack_id.lower(), "name": name[:128], "folder": entry.name[:128],
                "pack_type": pack_type, "version": header.get("version", [1, 0, 0]),
            })
    return found


def _find_pack(data: Path, name: str) -> tuple[Path, dict[str, Any]]:
    query = name.strip().casefold()
    if not query:
        raise WorkerError("invalid_mod_name")
    matches = [
        item for item in _installed_packs(data)
        if query in {item["name"].casefold(), item["folder"].casefold(), item["pack_id"].casefold()}
    ]
    if len(matches) != 1:
        raise WorkerError("pack_not_unique_or_installed")
    item = matches[0]
    active_file = "world_behavior_packs.json" if item["pack_type"] == "behavior" else "world_resource_packs.json"
    world_path = data / "worlds" / _active_world(data) / active_file
    return world_path, item


def handle(request: dict[str, Any], *, run: Callable[..., str] = _run) -> dict[str, Any]:
    action = request.get("action")
    params = request.get("params")
    container = request.get("container")
    base = request.get("base_path")
    if not isinstance(container, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container):
        raise WorkerError("invalid_container")
    if not isinstance(base, str) or not Path(base).is_absolute() or ".." in Path(base).parts:
        raise WorkerError("invalid_base_path")
    if action not in {"status", "players", "worlds", "mods", "config", "diagnostics", "start", "stop", "restart", "backup", "enable_mod", "disable_mod", "console"} or not isinstance(params, dict):
        raise WorkerError("invalid_request")
    root = Path(base)
    data = root / "data"

    if action == "diagnostics":
        docker_path = shutil.which("docker")
        probe = run(["docker", "inspect", "--format", "{{.State.Status}}", container], check=False).strip() if docker_path else ""
        return {
            "status": "ok",
            "python_available": True,
            "docker_available": docker_path is not None,
            "data_available": data.is_dir() and not data.is_symlink(),
            "configured_container_found": bool(probe),
        }
    if action == "status":
        raw = run(["docker", "inspect", "--format", "{{json .State}}", container], check=False).strip()
        if not raw:
            return {
                "status": "unknown", "reachable": True, "online": None,
                "container_status": "unknown", "telemetry": "unknown",
            }
        try:
            state = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkerError("invalid_status") from exc
        status = str(state.get("Status", "unknown"))
        result: dict[str, Any] = {"status": "ok", "online": status == "running", "container_status": status,
                                  "started_at": state.get("StartedAt"), "telemetry": "not_collected"}
        if data.is_dir() and not data.is_symlink():
            props = _props(data)
            result["active_world"] = props.get("level-name")
        return result
    if action == "players":
        return _players(root, container, run=run)
    if action == "config":
        if not data.is_dir() or data.is_symlink():
            raise WorkerError("data_unavailable")
        all_props = _props(data)
        safe_keys = {"level-name", "gamemode", "difficulty", "allow-cheats", "server-port", "server-name", "online-mode", "max-players"}
        return {"status": "ok", "properties": {key: value for key, value in all_props.items() if key in safe_keys}}
    if action == "worlds":
        if not data.is_dir() or data.is_symlink():
            raise WorkerError("data_unavailable")
        active = _props(data).get("level-name")
        worlds_dir = data / "worlds"
        worlds = []
        if worlds_dir.is_dir() and not worlds_dir.is_symlink():
            for item in list(worlds_dir.iterdir())[:MAX_SCAN]:
                if item.is_dir() and not item.is_symlink():
                    worlds.append({"name": item.name, "active": item.name == active})
        return {"status": "ok", "worlds": worlds}
    if action == "mods":
        if not data.is_dir() or data.is_symlink():
            raise WorkerError("data_unavailable")
        world = data / "worlds" / _active_world(data)
        output: dict[str, Any] = {"status": "ok", "active_world": world.name, "behavior": [], "resource": [], "installed": []}
        active_ids: set[tuple[str, str]] = set()
        for pack_type, filename in (("behavior", "world_behavior_packs.json"), ("resource", "world_resource_packs.json")):
            rows = _json_file(world / filename)
            output[pack_type] = rows
            active_ids.update((pack_type, str(row.get("pack_id", "")).casefold()) for row in rows)
        output["installed"] = [
            {**pack, "active": (pack["pack_type"], pack["pack_id"].casefold()) in active_ids}
            for pack in _installed_packs(data)
        ]
        for pack_type in ("behavior", "resource"):
            for row in output[pack_type]:
                matches = [pack for pack in output["installed"]
                           if pack["pack_type"] == pack_type
                           and pack["pack_id"].casefold() == str(row.get("pack_id", "")).casefold()
                           and pack["version"] == row.get("version")]
                row["name"] = matches[0]["name"] if len(matches) == 1 else None
                row["installed"] = bool(matches)
                row["configured"] = True
                row["loaded"] = None
        output["loaded_known"] = False
        return output

    if action in {"start", "stop", "restart"}:
        run(["docker", action, container], timeout=25)
        return {"status": "ok", "action": action}
    if action == "backup":
        return _backup(root, data, container, run=run)
    if action in {"enable_mod", "disable_mod"}:
        name = params.get("name")
        if not isinstance(name, str):
            raise WorkerError("invalid_mod_params")
        path, pack = _find_pack(data, name)
        pack_id = str(pack["pack_id"])
        rows = _json_file(path)
        exists = any(str(row.get("pack_id", "")).lower() == pack_id.lower() for row in rows)
        if action == "enable_mod" and not exists:
            rows.append({"pack_id": pack_id, "version": pack["version"]})
        elif action == "disable_mod":
            rows = [row for row in rows if str(row.get("pack_id", "")).lower() != pack_id.lower()]
        _atomic_json(path, rows)
        return {"status": "ok", "action": action, "pack_id": pack_id, "name": pack["name"], "changed": exists != (action == "enable_mod")}
    if action == "console":
        command = params.get("command")
        if command not in {"list", "save", "time query daytime", "weather query"}:
            raise WorkerError("console_command_not_allowed")
        console_output = run(["docker", "exec", container, "send-command", command], timeout=15)
        return {"status": "ok", "output": console_output[:MAX_OUTPUT]}
    raise WorkerError("invalid_action")


def main() -> int:
    def timeout_handler(_signum: int, _frame: Any) -> None:
        raise WorkerError("worker_timeout")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, WORKER_TIMEOUT_SECONDS)
    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        response = {"status": "error", "code": "input_too_large"}
    else:
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise WorkerError("invalid_request")
            response = handle(request)
        except (WorkerError, OSError, subprocess.SubprocessError, ValueError) as exc:
            code = str(exc) if isinstance(exc, WorkerError) else "worker_failed"
            response = {"status": "error", "code": code}
    encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_OUTPUT:
        encoded = b'{"status":"error","code":"output_too_large"}'
    signal.setitimer(signal.ITIMER_REAL, 0)
    sys.stdout.buffer.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
