"""Supervisor Linux mínimo: si muere el worker, retira todo el grupo del motor.

No interpreta texto. Recibe exclusivamente argv controlado del backend.
"""

import ctypes
import os
import signal
import subprocess
import sys


def main():
    parent = int(sys.argv[1])

    def parent_gone(*_):
        os.killpg(os.getpgrp(), signal.SIGKILL)

    signal.signal(signal.SIGUSR1, parent_gone)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGUSR1, 0, 0, 0) != 0:
        return 125
    if os.getppid() != parent:
        parent_gone()
    process = subprocess.Popen(sys.argv[2:], stdin=subprocess.DEVNULL)
    code = process.wait()
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main())
