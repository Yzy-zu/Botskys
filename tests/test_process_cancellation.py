"""Cancellation regressions run under an external watchdog for event-loop starvation."""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


class ProcessCancellationTest(TestCase):
    def run_isolated(self, program):
        result = subprocess.run(
            [sys.executable, "-c", program], capture_output=True, text=True, timeout=8
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cancelled_launch_terminates_without_starving_loop(self):
        self.run_isolated("""
import asyncio
from unittest.mock import patch
from botsky.engines.process import run_process
async def main():
    started = asyncio.Event()
    async def launch(*args, **kwargs):
        started.set()
        asyncio.current_task().cancel()
        await asyncio.sleep(0)
    with patch('asyncio.create_subprocess_exec', launch):
        task = asyncio.create_task(run_process(['no-real-child'], 1))
        await started.wait()
        try:
            await task
        except asyncio.CancelledError:
            return
        raise AssertionError('launch cancellation was swallowed')
asyncio.run(main())
""")

    def test_repeated_cancellation_during_launch_reaps_real_child(self):
        with TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            child_code = (
                "import os,time; from pathlib import Path; "
                f"Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
            )
            self.run_isolated(
                """
import asyncio, os, sys
from pathlib import Path
from unittest.mock import patch
from botsky.engines.process import run_process
pidfile = Path(__PIDFILE__)
async def main():
    real_launch = asyncio.create_subprocess_exec
    started, release = asyncio.Event(), asyncio.Event()
    async def delayed(*args, **kwargs):
        process = await real_launch(*args, **kwargs)
        started.set()
        await release.wait()
        return process
    with patch('asyncio.create_subprocess_exec', delayed):
        task = asyncio.create_task(run_process([
            sys.executable, '-c',
            __CHILD_CODE__
        ], 30))
        await started.wait()
        while not pidfile.exists():
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        release.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError('caller cancellation was swallowed')
asyncio.run(main())
""".replace("__PIDFILE__", repr(str(pidfile))).replace("__CHILD_CODE__", repr(child_code))
            )
            pid = int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_launch_failure_preserves_stable_error_and_cancellation(self):
        self.run_isolated("""
import asyncio
from unittest.mock import patch
from botsky.engines.process import MediaError, run_process
async def main():
    async def fail(*args, **kwargs):
        raise OSError('synthetic')
    with patch('asyncio.create_subprocess_exec', fail):
        try:
            await run_process(['no-real-child'], 1)
        except MediaError as exc:
            assert exc.code == 'process_unavailable'
        else:
            raise AssertionError('missing stable failure')
    ready, release = asyncio.Event(), asyncio.Event()
    async def delayed_fail(*args, **kwargs):
        ready.set()
        await release.wait()
        raise OSError('synthetic')
    with patch('asyncio.create_subprocess_exec', delayed_fail):
        task = asyncio.create_task(run_process(['no-real-child'], 1))
        await ready.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        try:
            await task
        except asyncio.CancelledError:
            return
        raise AssertionError('caller cancellation was swallowed')
asyncio.run(main())
""")
