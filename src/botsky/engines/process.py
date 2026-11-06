# Componente técnico adaptado de Zhana 7e12d54, media.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
import asyncio
import math
import os
import signal
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

PROCESS_ADDRESS_SPACE = 4 * 1024 * 1024 * 1024


class MediaError(Exception):
    """A stable error code without subprocess output or file contents."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def run_process(
    argv: Sequence[str],
    timeout_seconds: float,
    *,
    allowed_returncodes: tuple[int, ...] = (0,),
    env: dict[str, str] | None = None,
    failure_code: Callable[[bytes], str] | None = None,
) -> bytes:
    """Run a child in its own process group, draining bounded captured output."""
    bounded_argv = [
        "prlimit",
        f"--as={PROCESS_ADDRESS_SPACE}",
        f"--cpu={max(1, math.ceil(timeout_seconds))}",
        "--",
        *argv,
    ]
    # Shield process creation: cancellation while the OS is spawning must not
    # discard the only handle to a child that may already exist.
    launch = asyncio.create_task(
        asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(Path(__file__).with_name("child.py")),
            str(os.getpid()),
            *bounded_argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
    )
    cancelled_during_launch = False
    while True:
        try:
            process = await asyncio.shield(launch)
            break
        except asyncio.CancelledError:
            # A cancelled launch is terminal: shielding the same cancelled task
            # again raises synchronously forever and starves the event loop.
            if launch.cancelled():
                raise
            cancelled_during_launch = True
        except OSError as exc:
            if cancelled_during_launch:
                raise asyncio.CancelledError from exc
            raise MediaError("process_unavailable") from exc

    async def drain(stream: asyncio.StreamReader) -> bytes:
        result = bytearray()
        while chunk := await stream.read(65536):
            result.extend(chunk[: max(0, 65536 - len(result))])
        return bytes(result)

    assert process.stdout is not None and process.stderr is not None
    stdout = asyncio.create_task(drain(process.stdout))
    stderr = asyncio.create_task(drain(process.stderr))

    async def stop() -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), 1.0)
        except TimeoutError:
            pass
        # A descendant can survive even if the group leader has exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
        await asyncio.gather(stdout, stderr, return_exceptions=True)

    try:
        if cancelled_during_launch:
            raise asyncio.CancelledError
        async with asyncio.timeout(timeout_seconds):
            await process.wait()
            out, err = await asyncio.gather(stdout, stderr)
    except (asyncio.CancelledError, TimeoutError) as exc:
        cleanup = asyncio.create_task(stop())
        # Repeated cancellation must not leave a child behind.
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                continue
        await cleanup
        if isinstance(exc, TimeoutError):
            raise MediaError("process_timeout") from exc
        raise
    if process.returncode not in allowed_returncodes:
        raise MediaError(failure_code(err) if failure_code else "process_failed")
    return out
