# fmt: off
"""Fixed stdlib worker invoked remotely by minecraft_remote.py.

The worker accepts exactly one JSON request on stdin. It uses argv-based
subprocess calls and only accesses the configured Bedrock directory.
"""

from __future__ import annotations

import base64
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
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_SCAN = 1000
MAX_BACKUP_BYTES = 50 * 1024 * 1024 * 1024
MAX_BACKUP_FILES = 100_000
BACKUP_TIMEOUT_SECONDS = 1200
WORKER_TIMEOUT_SECONDS = 25
PACK_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


class WorkerError(Exception):
    pass


def _run(
    argv: list[str], *, timeout: int = 15, check: bool = True, merge_stderr: bool = False,
    max_output_bytes: int = MAX_OUTPUT,
) -> str:
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
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
                chunk = os.read(key.fd, min(16384, max_output_bytes + 1 - len(output)))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if len(output) > max_output_bytes:
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


def _without_symlinks(path: Path) -> bool:
    """Return whether every existing component of an absolute path is real."""
    if not path.is_absolute():
        return False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                return False
        except OSError:
            return False
    return True


def discover(container: str, base: Path, *, run: Callable[..., str] = _run) -> dict[str, Any]:
    """Resolve the mounted Bedrock data directory from Docker's full inspect."""
    if base.is_symlink() or not base.is_dir() or not _without_symlinks(base):
        raise WorkerError("invalid_base_path")
    raw = run(["docker", "inspect", "--format", "{{json .}}", container], check=False).strip()
    if not raw:
        raise WorkerError("container_inspect_unavailable")
    try:
        inspected = json.loads(raw)
        if isinstance(inspected, list):
            inspected = inspected[0] if len(inspected) == 1 else None
        config = inspected["Config"]
        mounts = inspected["Mounts"]
        identity = inspected["Id"]
        image = inspected["Image"]
        working_dir = config["WorkingDir"]
    except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise WorkerError("container_inspect_invalid") from exc
    if not isinstance(identity, str) or not identity or not isinstance(image, str) or not image:
        raise WorkerError("container_inspect_invalid")
    if not isinstance(working_dir, str) or not Path(working_dir).is_absolute() or ".." in Path(working_dir).parts:
        raise WorkerError("container_workdir_invalid")
    matches = []
    for mount in mounts if isinstance(mounts, list) else []:
        if not isinstance(mount, dict):
            continue
        source, destination = mount.get("Source"), mount.get("Destination")
        if not isinstance(source, str) or not isinstance(destination, str):
            continue
        destination_path = Path(destination)
        if not destination_path.is_absolute() or ".." in destination_path.parts:
            continue
        try:
            relative = Path(working_dir).relative_to(destination_path)
        except ValueError:
            continue
        matches.append((len(destination_path.parts), source, destination_path, relative))
    if not matches:
        raise WorkerError("data_mount_unavailable")
    _, source, destination, relative = max(matches, key=lambda item: item[0])
    source_path = Path(source)
    if not source_path.is_absolute() or not _without_symlinks(source_path):
        raise WorkerError("unsafe_data_mount")
    try:
        base_real = base.resolve(strict=True)
        source_real = source_path.resolve(strict=True)
        source_real.relative_to(base_real)
    except (OSError, ValueError) as exc:
        raise WorkerError("data_mount_outside_base") from exc
    data = source_real / relative
    if not _without_symlinks(data) or not data.is_dir():
        raise WorkerError("data_unavailable")
    properties = data / "server.properties"
    if properties.is_symlink() or not properties.is_file():
        raise WorkerError("server_properties_unavailable")
    world = _active_world(data)
    mount_fingerprint = hashlib.sha256(
        f"{source_real}\0{destination}\0{relative}".encode()
    ).hexdigest()
    return {
        "status": "ok",
        "data_path": data,
        "active_world": world,
        "fingerprint": {"image": image, "id": identity, "mount": mount_fingerprint},
    }


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


def _atomic_json(path: Path, value: list[dict[str, Any]], *, mode: int = 0o644) -> None:
    if path.is_symlink():
        raise WorkerError("unsafe_pack_file")
    fd, temp_name = tempfile.mkstemp(prefix=".zhana-packs-", dir=path.parent)
    try:
        # World pack configuration contains public pack IDs, not credentials.
        # mkstemp's 0600 makes it unreadable to the container's game user.
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
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
            with tarfile.open(fileobj=archive_stream, mode="w:gz", compresslevel=1) as archive:
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
            for delay in (0.25, 0.5, 1.0):
                time.sleep(delay)
                log = run(["docker", "logs", "--since", f"{sent_at:.6f}", "--timestamps", container], timeout=10, merge_stderr=True, max_output_bytes=MAX_LOG_BYTES)
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
                if len(matches) == 1:
                    break
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


def _game_status(container: str, state: dict[str, Any], *, run: Callable[..., str]) -> str:
    if state.get("Status") != "running":
        return "offline"
    started = state.get("StartedAt")
    if not isinstance(started, str) or not started:
        return "unknown"
    try:
        log = run(["docker", "logs", "--since", started, container], timeout=10, merge_stderr=True, max_output_bytes=MAX_LOG_BYTES)
    except (WorkerError, OSError, subprocess.SubprocessError):
        return "unknown"
    if "free(): invalid next size" in log or "Fatal glibc error" in log:
        return "failed"
    if "Server started." in log and "Stopping server" not in log and "Server stop requested" not in log:
        return "ready"
    return "starting"


def _observed_packs(container: str, *, run: Callable[..., str]) -> set[tuple[str, str]]:
    """Positive evidence only, scoped to this container's current startup."""
    try:
        raw = run(["docker", "inspect", "--format", "{{json .State}}", container], check=False)
        state = json.loads(raw)
        started = state.get("StartedAt")
        if state.get("Status") != "running" or not isinstance(started, str) or not started:
            return set()
        log = run(["docker", "logs", "--since", started, container], timeout=10, merge_stderr=True, max_output_bytes=MAX_LOG_BYTES)
        pattern = re.compile(r"Pack Stack - .*?\(id: ([0-9a-fA-F-]{36}), version: ([0-9]+\.[0-9]+\.[0-9]+)\)")
        return {(identity.casefold(), version) for identity, version in pattern.findall(log)}
    except (WorkerError, ValueError, OSError, subprocess.SubprocessError):
        return set()


def _installed_packs(data: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for pack_type, folder in (("behavior", "behavior_packs"), ("resource", "resource_packs")):
        manifests = data / folder
        if not manifests.is_dir() or manifests.is_symlink():
            continue
        for entry in sorted(manifests.iterdir(), key=lambda child: child.name)[:MAX_SCAN]:
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
            version = header.get("version")
            dependencies = content.get("dependencies", [])
            if (not isinstance(version, list) or len(version) != 3
                    or any(type(part) is not int or part < 0 for part in version)
                    or not isinstance(dependencies, list)):
                continue
            raw_name = header.get("name")
            name = raw_name if isinstance(raw_name, str) and raw_name not in {"", "pack.name"} else entry.name
            found.append({
                "pack_id": pack_id.lower(), "name": name[:128], "folder": entry.name[:128],
                "pack_type": pack_type, "version": version,
                "dependencies": [dep for dep in content.get("dependencies", [])
                                 if isinstance(dep, dict) and PACK_ID.fullmatch(str(dep.get("uuid", "")))],
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


def _mod_plan(data: Path, name: str, action: str) -> dict[str, Any]:
    path, target = _find_pack(data, name)
    installed = _installed_packs(data)
    def key(pack):
        return (pack["pack_type"], pack["pack_id"], tuple(pack["version"]))
    packs = {key(pack): pack for pack in installed}
    def dependencies(pack):
        return [(dep["uuid"].casefold(), dep.get("version")) for dep in pack["dependencies"]]
    graph = {identity: {other for other, candidate in packs.items()
                       if any(candidate["pack_id"] == dep_id and candidate["version"] == version
                              for dep_id, version in dependencies(pack))}
             for identity, pack in packs.items()}
    def reachable(start, graph):
        seen, pending = set(), [start]
        while pending:
            item = pending.pop()
            if item not in seen:
                seen.add(item)
                pending.extend(graph[item] - seen)
        return seen
    start = key(target)
    reverse = {identity: {other for other, edges in graph.items() if identity in edges}
               for identity in packs}
    # A strongly connected group cannot be toggled one half at a time.
    component = reachable(start, graph) & reachable(start, reverse)
    if any(sum(key(pack) == identity for pack in installed) != 1 for identity in component):
        raise WorkerError("duplicate_installed_pack")
    selected = [packs[identity] for identity in sorted(component)]
    world = path.parent
    paths = {kind: world / filename for kind, filename in
             (("behavior", "world_behavior_packs.json"), ("resource", "world_resource_packs.json"))}
    originals = {kind: _json_file(file) for kind, file in paths.items()}
    configured = originals["behavior"] + originals["resource"]
    def configured_pack(pack):
        return any(str(row.get("pack_id", "")).casefold() == pack["pack_id"]
                   and row.get("version") == pack["version"] for row in configured)
    for pack in selected:
        existing = [row for row in originals[pack["pack_type"]]
                    if str(row.get("pack_id", "")).casefold() == pack["pack_id"]]
        if len(existing) > 1:
            raise WorkerError("duplicate_configured_pack")
        if action == "enable_mod":
            if existing and existing[0].get("version") != pack["version"]:
                raise WorkerError("pack_version_conflict")
            for dep_id, version in dependencies(pack):
                candidates = [other for identity, other in packs.items()
                              if other["pack_id"] == dep_id and other["version"] == version]
                if len(candidates) != 1 or not (key(candidates[0]) in component or configured_pack(candidates[0])):
                    raise WorkerError("pack_dependency_not_configured")
    if action == "disable_mod":
        removed_ids = {pack["pack_id"] for pack in selected}
        for identity, pack in packs.items():
            if identity not in component and configured_pack(pack):
                if any(dep_id in removed_ids for dep_id, _version in dependencies(pack)):
                    raise WorkerError("pack_required_by_configured")
    history_path = world / ".botsky-disabled-packs.json"
    history = _json_file(history_path)
    rows = {kind: list(values) for kind, values in originals.items()}
    changed = False
    touched = set()
    def restore_order(pack):
        positions = [item.get("position") for item in history
                     if item.get("pack_type") == pack["pack_type"]
                     and str(item.get("pack_id", "")).casefold() == pack["pack_id"]
                     and type(item.get("position")) is int]
        return (pack["pack_type"], positions[0] if len(positions) == 1 else 100000, pack["pack_id"])
    ordered = sorted(selected, key=restore_order) if action == "enable_mod" else selected
    for pack in ordered:
        kind, pack_id = pack["pack_type"], pack["pack_id"]
        touched.add(kind)
        existing = [row for row in originals[kind] if str(row.get("pack_id", "")).casefold() == pack_id]
        saved = [item for item in history if item.get("pack_type") == kind
                 and str(item.get("pack_id", "")).casefold() == pack_id]
        remaining = [item for item in history if item not in saved]
        if action == "disable_mod" and existing:
            history = remaining + [{"pack_id": pack_id, "pack_type": kind,
                                    "position": originals[kind].index(existing[0]), "row": existing[0]}]
            rows[kind] = [row for row in rows[kind] if str(row.get("pack_id", "")).casefold() != pack_id]
            changed = True
        elif action == "enable_mod" and not existing:
            row, position = {"pack_id": pack_id, "version": pack["version"]}, len(rows[kind])
            if len(saved) == 1:
                previous = saved[0].get("row")
                if (isinstance(previous, dict) and str(previous.get("pack_id", "")).casefold() == pack_id
                        and previous.get("version") == pack["version"]):
                    row = previous
                    if type(saved[0].get("position")) is int:
                        position = max(0, min(len(rows[kind]), saved[0]["position"]))
            rows[kind].insert(position, row)
            history = remaining
            changed = True
    repaired = any(paths[kind].exists() and stat.S_IMODE(paths[kind].stat().st_mode) != 0o644 for kind in touched)
    return {"paths": paths, "originals": originals, "rows": rows, "touched": touched,
            "history_path": history_path, "history": history, "history_before": _json_file(history_path),
            "target": target, "selected": selected, "changed": changed, "repaired": repaired}


def _journal_read(world):
    path = world / '.botsky-recovery.json'
    if path.is_symlink():
        raise WorkerError('unsafe_recovery_journal')
    if not path.exists():
        return None
    if path.stat().st_size > 1024 * 1024:
        raise WorkerError('invalid_recovery_journal')
    value = json.loads(path.read_text())
    if not isinstance(value, list) or len(value) != 1 or value[0].get('version') != 1:
        raise WorkerError('invalid_recovery_journal')
    return value[0]


def _journal_prepare(plan):
    world = plan['history_path'].parent
    previous = _journal_read(world)
    if previous and previous['phase'] == 'pending':
        raise WorkerError('recovery_required')
    entries = []
    values = {plan['paths'][kind]: plan['rows'][kind] for kind in plan['touched']}
    values[plan['history_path']] = plan['history']
    for path, rows in values.items():
        if path.is_symlink():
            raise WorkerError('unsafe_recovery_target')
        raw = path.read_bytes() if path.exists() else None
        after = json.dumps(rows, ensure_ascii=False, indent=2).encode()
        entries.append({'name': path.name, 'before': base64.b64encode(raw).decode() if raw is not None else None,
                        'mode': stat.S_IMODE(path.stat().st_mode) if raw is not None else None,
                        'after_hash': hashlib.sha256(after).hexdigest()})
    record = {'version': 1, 'id': uuid.uuid4().hex, 'phase': 'pending', 'entries': entries, 'fingerprint': plan.get('fingerprint')}
    _atomic_json(world / '.botsky-recovery.json', [record], mode=0o600)
    return record


def _recover(data, container, *, run, fingerprint=None):
    try:
        fd = _world_lock(data / 'worlds' / _active_world(data))
    except WorkerError as exc:
        if str(exc) == 'minecraft_change_busy':
            return {'status': 'needs_input', 'dispatched': False, 'code': 'minecraft_change_busy'}
        raise
    try:
        return _recover_locked(data, container, run=run, fingerprint=fingerprint)
    finally:
        os.close(fd)


def _recover_locked(data, container, *, run, fingerprint=None):
    world = data / 'worlds' / _active_world(data)
    record = _journal_read(world)
    if not record or record['phase'] == 'recovered':
        state = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', container]))
        if state.get('Status') not in {'exited', 'created'}:
            return {'status': 'needs_input', 'dispatched': False, 'code': 'recovery_requires_offline'}
        return {'status': 'ok', 'changed': False, 'recovered': True, 'offline_verified': True}
    if record.get('fingerprint') and record['fingerprint'] != fingerprint:
        return {'status': 'needs_input', 'dispatched': False, 'code': 'recovery_environment_changed'}
    state = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', container]))
    if state.get('Status') not in {'exited', 'created'}:
        return {'status': 'needs_input', 'dispatched': False, 'code': 'recovery_requires_offline'}
    allowed = {'world_behavior_packs.json', 'world_resource_packs.json', '.botsky-disabled-packs.json'}
    prepared = []
    for entry in record['entries']:
        if entry['name'] not in allowed:
            raise WorkerError('unsafe_recovery_target')
        path = world / entry['name']
        if path.is_symlink():
            raise WorkerError('unsafe_recovery_target')
        current = path.read_bytes() if path.exists() else None
        before = base64.b64decode(entry['before'], validate=True) if entry['before'] is not None else None
        if current != before and (current is None or hashlib.sha256(current).hexdigest() != entry['after_hash']):
            return {'status': 'needs_input', 'dispatched': False, 'code': 'recovery_conflict'}
        prepared.append((path, before, entry['mode']))
    for path, before, mode in prepared:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            fd, temp = tempfile.mkstemp(dir=world, prefix='.botsky-restore-')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(before)
                    os.fchmod(stream.fileno(), mode)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
    record['phase'] = 'recovered'
    _atomic_json(world / '.botsky-recovery.json', [record], mode=0o600)
    return {'status': 'ok', 'changed': True, 'recovered': True, 'recovery_id': record['id'], 'offline_verified': True}


def _world_lock(world):
    fd = os.open(world / '.botsky-operation.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise WorkerError('minecraft_change_busy')
    return fd


def _apply_mod_plan(plan, action):
    fd = _world_lock(plan['history_path'].parent)
    try:
        if any(_json_file(plan['paths'][kind]) != rows for kind, rows in plan['originals'].items()):
            raise WorkerError('configuration_changed_during_plan')
        return _apply_mod_plan_locked(plan, action)
    finally:
        os.close(fd)


def _apply_mod_plan_locked(plan: dict[str, Any], action: str) -> dict[str, Any]:
    world = plan['history_path'].parent
    record = _journal_prepare(plan) if plan["changed"] or plan["repaired"] else None
    # Record restoration metadata before deleting any configured row. A failure
    # between the two atomic world files is uncertain, never a safe-to-retry error.
    if action == "disable_mod" and plan["history"] != plan["history_before"]:
        _atomic_json(plan["history_path"], plan["history"], mode=0o600)
    for kind in sorted(plan["touched"]):
        path = plan["paths"][kind]
        if plan["rows"][kind] != plan["originals"][kind] or plan["repaired"]:
            _atomic_json(path, plan["rows"][kind])
            if _json_file(path) != plan["rows"][kind]:
                raise WorkerError("pack_write_not_verified")
    if action == "enable_mod" and plan["history"] != plan["history_before"]:
        _atomic_json(plan["history_path"], plan["history"], mode=0o600)
    if record is not None:
        record['phase'] = 'applied'
        _atomic_json(world / '.botsky-recovery.json', [record], mode=0o600)
    target = plan["target"]
    return {"status": "ok", "action": action, "pack_id": target["pack_id"], "name": target["name"],
            "affected": [{"name": pack["name"], "pack_id": pack["pack_id"], "pack_type": pack["pack_type"]}
                         for pack in plan["selected"]], "changed": plan["changed"],
            "configured": action == "enable_mod", "restart_required": plan["changed"] or plan["repaired"],
            "permissions_repaired": plan["repaired"], "loaded_known": False}


def handle(request: dict[str, Any], *, run: Callable[..., str] = _run, discover_layout: bool = True) -> dict[str, Any]:
    action = request.get("action")
    params = request.get("params")
    container = request.get("container")
    base = request.get("base_path")
    if not isinstance(container, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container):
        raise WorkerError("invalid_container")
    if not isinstance(base, str) or not Path(base).is_absolute() or ".." in Path(base).parts:
        raise WorkerError("invalid_base_path")
    if action not in {"status", "players", "worlds", "mods", "config", "diagnostics", "discover", "start", "stop", "restart", "backup", "enable_mod", "disable_mod", "recover", "console"} or not isinstance(params, dict):
        raise WorkerError("invalid_request")
    root = Path(base)
    data = root / "data"
    layout = None
    if discover_layout and action not in {"diagnostics", "discover"}:
        try:
            layout = discover(container, root, run=run)
            data = layout['data_path']
        except WorkerError as exc:
            return {'status': 'needs_input', 'dispatched': False, 'code': str(exc)}

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
    if action == "discover":
        result = discover(container, root, run=run)
        return {
            "status": "ok",
            "available": True,
            "active_world": result["active_world"],
            "fingerprint": result["fingerprint"],
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
        game_status = _game_status(container, state, run=run)
        result: dict[str, Any] = {"status": "ok", "online": True if game_status == "ready" else False if status in {"exited", "created", "paused"} else None,
                                  "container_status": status, "game_status": game_status,
                                  "started_at": state.get("StartedAt"), "telemetry": "current_startup_log"}
        if data.is_dir() and not data.is_symlink():
            props = _props(data)
            result["active_world"] = props.get("level-name")
        if layout:
            result['environment'] = layout['fingerprint']
        journal = _journal_read(data / 'worlds' / _active_world(data))
        result['reconciliation'] = journal['phase'] if journal else 'no_pending_change'
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
        active_ids: set[tuple[str, str, str]] = set()
        for pack_type, filename in (("behavior", "world_behavior_packs.json"), ("resource", "world_resource_packs.json")):
            rows = _json_file(world / filename)
            output[pack_type] = rows
            active_ids.update((pack_type, str(row.get("pack_id", "")).casefold(), json.dumps(row.get("version"))) for row in rows)
        output["installed"] = [
            {**pack, "active": (pack["pack_type"], pack["pack_id"].casefold(), json.dumps(pack["version"])) in active_ids}
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
        observed = _observed_packs(container, run=run)
        for pack in output["installed"]:
            pack["loaded"] = True if (pack["pack_id"], ".".join(map(str, pack["version"]))) in observed else None
        for pack_type in ("behavior", "resource"):
            for row in output[pack_type]:
                version = row.get("version")
                if isinstance(version, list):
                    row["loaded"] = True if (str(row.get("pack_id", "")).casefold(), ".".join(map(str, version))) in observed else None
        output["load_evidence"] = "current_startup_pack_stack_positive_only"
        output["installed"].sort(key=lambda pack: (not pack["active"], pack["name"].casefold(), pack["pack_type"], pack["folder"]))
        output["loaded_known"] = False
        return output

    if action in {"start", "stop", "restart"}:
        try:
            fd = _world_lock(data / 'worlds' / _active_world(data))
        except WorkerError as exc:
            if str(exc) == 'minecraft_change_busy':
                return {'status': 'needs_input', 'dispatched': False, 'code': 'minecraft_change_busy'}
            raise
        try:
            if action != "stop":
                journal = _journal_read(data / 'worlds' / _active_world(data))
                if journal and journal['phase'] == 'pending':
                    return {'status': 'needs_input', 'code': 'recovery_required', 'dispatched': False}
            run(["docker", action, container], timeout=25)
            return {"status": "ok", "action": action, "requires_healthcheck": action in {"start", "restart"}}
        finally:
            os.close(fd)
    if action == "backup":
        return _backup(root, data, container, run=run)
    if action == "recover":
        return _recover(data, container, run=run, fingerprint=layout['fingerprint'] if layout else None)
    if action in {"enable_mod", "disable_mod"}:
        name = params.get("name")
        if not isinstance(name, str):
            raise WorkerError("invalid_mod_params")
        try:
            plan = _mod_plan(data, name, action)
        except WorkerError as exc:
            return {"status": "needs_input", "code": str(exc), "dispatched": False}
        plan['fingerprint'] = layout['fingerprint'] if layout else None
        return _apply_mod_plan(plan, action)
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
            if request.get("action") == "backup":
                signal.setitimer(signal.ITIMER_REAL, BACKUP_TIMEOUT_SECONDS + 30)
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
