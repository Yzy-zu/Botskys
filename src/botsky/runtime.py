"""Proceso propio: admisión HTTP durable y bucles independientes, sin activar servicios ajenos."""

import asyncio
import fcntl
import hmac
import json
import os
import re
from contextlib import contextmanager

from .adapters.evolution import EvolutionTransport
from .delivery import deliver_async
from .local_files import private_directory


@contextmanager
def runtime_lock(root):
    directory = private_directory(root, "private")
    fd = os.open(
        directory / "runtime.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("runtime_already_running") from None
        yield
    finally:
        os.close(fd)


def runtime_options(value):
    allowed = {
        "webhook_token",
        "port",
        "scheduler_enabled",
        "notices_enabled",
        "poll_seconds",
        "shutdown_seconds",
    }
    if (
        not isinstance(value, dict)
        or set(value) - allowed
        or not isinstance(value.get("webhook_token"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", value["webhook_token"])
    ):
        raise ValueError("runtime_configuration_required")
    result = {
        "port": 8787,
        "scheduler_enabled": False,
        "notices_enabled": False,
        "poll_seconds": 1.0,
        "shutdown_seconds": 30.0,
        **value,
    }
    if (
        type(result["port"]) is not int
        or not 0 <= result["port"] <= 65535
        or any(type(result[k]) is not bool for k in ("scheduler_enabled", "notices_enabled"))
        or any(
            type(result[k]) not in (int, float) or not 0.01 <= result[k] <= 60
            for k in ("poll_seconds", "shutdown_seconds")
        )
    ):
        raise ValueError("runtime_configuration_invalid")
    return result


class WebhookServer:
    """HTTP loopback acotado para proxy explícito; nunca registra cuerpos o credenciales."""

    def __init__(self, transport, token, port):
        self.transport, self.token, self.port = transport, token, port
        self.server = None
        self.connections = set()
        self.writers = set()

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", self.port, limit=16384)
        self.port = self.server.sockets[0].getsockname()[1]

    async def close(self):
        if self.server:
            self.server.close()
        for writer in tuple(self.writers):
            writer.close()
        tasks = tuple(self.connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.server:
            await self.server.wait_closed()

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self.connections) >= 32:
            writer.close()
            return
        self.connections.add(task)
        self.writers.add(writer)
        status, result = 400, {"error": "invalid_request"}
        try:
            async with asyncio.timeout(10):
                head = await reader.readuntil(b"\r\n\r\n")
                lines = head.decode("ascii").split("\r\n")
                method, path, version = lines[0].split(" ")
                headers = {}
                for line in lines[1:-2]:
                    name, value = line.split(":", 1)
                    name = name.lower()
                    if not re.fullmatch(r"[a-z0-9-]+", name) or name in headers:
                        raise ValueError("invalid_headers")
                    headers[name] = value.strip()
                if version != "HTTP/1.1" or "transfer-encoding" in headers or "origin" in headers:
                    raise ValueError("invalid_protocol")
                if not hmac.compare_digest(
                    headers.get("authorization", ""), "Bearer " + self.token
                ):
                    status, result = 401, {"error": "unauthorized"}
                elif method == "GET" and path == "/healthz":
                    status, result = 200, {"ready": True}
                elif method != "POST" or path != "/webhook/evolution":
                    status, result = 404, {"error": "not_found"}
                elif headers.get("content-type", "").split(";")[0].strip() != "application/json":
                    status, result = 415, {"error": "json_required"}
                else:
                    length = headers.get("content-length", "")
                    if not re.fullmatch(r"[0-9]{1,8}", length):
                        raise ValueError("length_required")
                    if not 0 < int(length) <= 1024 * 1024:
                        status, result = 413, {"error": "body_too_large"}
                    else:
                        payload = json.loads(await reader.readexactly(int(length)))
                        result = self.transport.enqueue(payload)
                        status = 202
        except asyncio.CancelledError:
            writer.close()
            self.writers.discard(writer)
            self.connections.discard(task)
            raise
        except OverflowError:
            status, result = 503, {"error": "queue_full"}
        except ValueError as exc:
            if str(exc) == "transport_message_conflict":
                status, result = 409, {"error": "message_conflict"}
        except TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, UnicodeError:
            pass
        except Exception:
            status, result = 503, {"error": "admission_unavailable"}
        try:
            body = json.dumps(result).encode()
            writer.write(
                f"HTTP/1.1 {status} Response\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        except OSError, ConnectionError:
            pass
        finally:
            writer.close()
            self.writers.discard(writer)
            self.connections.discard(task)


class Runtime:
    def __init__(self, app, profile, http, *, services=None):
        self.app = app
        self.services = services
        self.options = runtime_options(profile.get("runtime"))
        self.transport = EvolutionTransport(app, profile["evolution"], http)
        self.webhook = WebhookServer(
            self.transport, self.options["webhook_token"], self.options["port"]
        )
        self.running = False

    async def admission_once(self):
        await self.transport.receive_pending(media=False)
        self.app.recover(limit=20)

    async def media_once(self):
        # A slow media download cannot hold text commands from other chats.
        await self.transport.receive_pending(media=True)
        self.app.recover(limit=20)

    async def frontend_once(self):
        if self.app.frontend is not None:
            from .frontend.worker import run_pending
            await run_pending(self.app, limit=2)

    async def jobs_once(self):
        await self.app.jobs.run_pending(limit=8)

    async def scheduler_once(self):
        if self.options["scheduler_enabled"]:
            self.app.scheduler.tick()
        if self.options["notices_enabled"] and self.app.calls:
            await self.app.poll_call_notices()

    async def delivery_once(self):
        if not self.transport.delivery_enabled:
            return
        seen = set()
        attempted = 0
        while attempted < 20:
            exclusion = (
                f" AND o.receipt_id NOT IN ({','.join('?' for _ in seen)})" if seen else ""
            )
            with self.app.store.transaction() as db:
                rows = db.execute(
                    "SELECT DISTINCT o.receipt_id FROM outbox o JOIN inbox i ON i.id=o.receipt_id "
                    "WHERE i.instance=? AND i.account=? AND i.epoch=? AND o.state='pending' "
                    "AND (json_extract(o.rich_payload_json,'$.reaction')='' "
                    "OR NOT EXISTS(SELECT 1 FROM outbox p WHERE p.receipt_id=o.receipt_id "
                    "AND p.position<o.position AND json_extract(p.rich_payload_json,'$.reaction') IS NULL "
                    "AND p.state!='accepted'))"
                    + exclusion
                    + " ORDER BY o.updated_ms LIMIT 20",
                    (
                        self.app.settings.instance,
                        self.app.settings.account,
                        self.app.settings.epoch,
                        *seen,
                    ),
                ).fetchall()
            if not rows:
                break
            for row in rows:
                receipt_id = row[0]
                seen.add(receipt_id)
                if self.app.operations:
                    with self.app.store.transaction() as db:
                        chat = db.execute(
                            "SELECT chat FROM inbox WHERE id=?", (receipt_id,)
                        ).fetchone()[0]
                        if not self.app.operations.delivers(chat):
                            db.execute(
                                "UPDATE outbox SET state='cancelled',revision=revision+1 WHERE receipt_id=? AND state='pending'",
                                (receipt_id,),
                            )
                            continue
                with self.app.store.transaction() as db:
                    before = db.execute(
                        "SELECT count(*) FROM delivery_attempts WHERE receipt_id=?",
                        (receipt_id,),
                    ).fetchone()[0]
                await deliver_async(
                    self.app.store, receipt_id, self.app.settings, self.transport, self.app.clock
                )
                with self.app.store.transaction() as db:
                    after = db.execute(
                        "SELECT count(*) FROM delivery_attempts WHERE receipt_id=?",
                        (receipt_id,),
                    ).fetchone()[0]
                if after > before:
                    attempted += 1
                    if attempted >= 20:
                        break

    async def maintenance_once(self):
        self.app.store.prune_context(self.app.settings, self.app.clock())
        self.app.artifacts.collect(self.app.clock())
        with self.app.store.transaction() as db:
            # Preserve admission fingerprints/receipts; erase expired raw media envelopes.
            db.execute(
                "UPDATE transport_inbox SET state='rejected',error_code='stale_epoch',payload='' WHERE instance=? AND account=? AND epoch!=? AND state='pending'",
                (self.app.settings.instance, self.app.settings.account, self.app.settings.epoch),
            )

    async def loop(self, action, stop, delay):
        while not stop.is_set():
            await action()
            try:
                await asyncio.wait_for(stop.wait(), delay)
            except TimeoutError:
                pass

    async def watch_calls(self, stop):
        child = asyncio.create_task(self.services.call_process.wait())
        ending = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait([child, ending], return_when=asyncio.FIRST_COMPLETED)
            if child in done:
                child.result()
        finally:
            child.cancel()
            ending.cancel()
            await asyncio.gather(child, ending, return_exceptions=True)

    async def run(self, stop, *, on_ready=None):
        # Must acquire exclusive ownership before classifying interrupted sends.
        with runtime_lock(self.app.settings.root):
            self.app.store.recover_deliveries(self.app.settings, self.app.clock())
            tasks = []
            waiter = asyncio.create_task(stop.wait())
            try:
                if self.services:
                    starting = asyncio.create_task(self.services.start_calls())
                    try:
                        done, _ = await asyncio.wait(
                            [starting, waiter], return_when=asyncio.FIRST_COMPLETED
                        )
                        if waiter in done:
                            return
                        await starting
                    finally:
                        if not starting.done():
                            starting.cancel()
                        await asyncio.gather(starting, return_exceptions=True)
                await self.webhook.start()
                self.running = True
                tasks = [
                    asyncio.create_task(self.loop(action, stop, delay), name=name)
                    for name, action, delay in (
                        ("admission", self.admission_once, self.options["poll_seconds"]),
                        ("media-ingress", self.media_once, self.options["poll_seconds"]),
                        ("frontend", self.frontend_once, self.options["poll_seconds"]),
                        ("jobs", self.jobs_once, self.options["poll_seconds"]),
                        ("scheduler", self.scheduler_once, self.options["poll_seconds"]),
                        ("delivery", self.delivery_once, self.options["poll_seconds"]),
                        ("maintenance", self.maintenance_once, 60),
                    )
                ]
                if self.services and self.services.call_process:
                    tasks.append(asyncio.create_task(self.watch_calls(stop), name="calls-service"))
                if on_ready:
                    on_ready(self.webhook.port)
                done, _ = await asyncio.wait([waiter, *tasks], return_when=asyncio.FIRST_COMPLETED)
                # Failure in any loop stops siblings; no silent half-running daemon.
                for task in done:
                    if task is not waiter:
                        task.result()
            finally:
                self.running = False
                stop.set()
                await self.webhook.close()
                _, pending = (
                    await asyncio.wait(tasks, timeout=self.options["shutdown_seconds"])
                    if tasks
                    else (set(), set())
                )
                for task in pending:
                    task.cancel()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
                failure = next((r for r in results if isinstance(r, Exception)), None)
                if failure:
                    raise failure
