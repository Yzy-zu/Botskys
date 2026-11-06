"""Regresión Python con red solo loopback; evidencia nueva sin reescribir R10."""

import argparse
import ipaddress
import json
import os
import re
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
denied = []


def guard(original):
    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            try:
                local = ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                local = address[0] == "localhost"
            if not local:
                denied.append("non_loopback")
                raise OSError("RUNTIME_NON_LOOPBACK_DENIED")
        return original(sock, address)

    return connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="RUNTIME")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z0-9-]{1,40}", args.prefix):
        parser.error("prefix inválido")
    os.environ["NODE_OPTIONS"] = "--require=" + str(ROOT / "ops/restringir_red_local.cjs")
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    out = ROOT / "docs/evidencia"
    with (
        (out / (args.prefix + "-python-regression.txt")).open("w") as log,
        patch.object(socket.socket, "connect", guard(socket.socket.connect)),
        patch.object(socket.socket, "connect_ex", guard(socket.socket.connect_ex)),
    ):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {
        "tests": result.testsRun,
        "success": result.wasSuccessful(),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "non_loopback_attempts": len(denied),
    }
    (out / (args.prefix + "-python-summary.json")).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if result.wasSuccessful() and not denied else 1


if __name__ == "__main__":
    sys.exit(main())
