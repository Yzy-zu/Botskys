"""R10: runner de aceptación local e inventario de evidencia por ruta/campo.

Observa solo nombres/códigos, nunca valores de mensajes, archivos o credenciales.
No interpreta una ejecución observada como aceptación semántica del campo.
"""

import ipaddress
import json
import os
import socket
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    from botsky.commands.registry import Registry
    from botsky.commands.router import Router
    from botsky.jobs import Jobs
    from botsky.store import Store

    out = ROOT / "private/R10"
    out.mkdir(parents=True, exist_ok=True)
    registry, active = Registry(), {"test": ""}
    syntax, executions = defaultdict(dict), defaultdict(list)
    network_denied = []
    original_parse, original_execute, original_finish = Router.parse, Store.execute, Jobs.finish
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def parse(self, text):
        result = original_parse(self, text)
        if result is not None:
            for field in ("action", *result.spans):
                syntax[result.spec.command].setdefault(field, set()).add(active["test"])
        return result

    def observe(store, identifier, level):
        db = store.connect()
        try:
            row = db.execute(
                "SELECT path_json,command_json,result_json FROM inbox WHERE id=?", (identifier,)
            ).fetchone()
        finally:
            db.close()
        if not row or not row["command_json"] or not row["result_json"]:
            return
        command, result = json.loads(row["command_json"]), json.loads(row["result_json"])
        route = "/" + " ".join(json.loads(row["path_json"]))
        item = {
            "test": active["test"],
            "level": level,
            "fields": sorted(command["arguments"]),
            "status": result["status"],
            "code": result["code"],
        }
        if item not in executions[route]:
            executions[route].append(item)

    def execute(self, identifier, *args, **kwargs):
        result = original_execute(self, identifier, *args, **kwargs)
        observe(self, identifier, "committed_receipt")
        return result

    def finish(self, job, *args, **kwargs):
        result = original_finish(self, job, *args, **kwargs)
        if result:
            observe(self.store, job["id"], "finished_worker")
        return result

    def guard(original):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                try:
                    local = ipaddress.ip_address(address[0]).is_loopback
                except ValueError:
                    local = address[0] == "localhost"
                if not local:
                    network_denied.append({"test": active["test"], "kind": "non_loopback"})
                    raise OSError("R10_NON_LOOPBACK_NETWORK_DENIED")
            return original(sock, address)

        return connect

    class Results(unittest.TextTestResult):
        def startTest(self, test):
            active["test"] = test.id()
            super().startTest(test)

    os.environ["NODE_OPTIONS"] = "--require=" + str(ROOT / "ops/restringir_red_local.cjs")
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (
        (out / "python-tests.txt").open("w") as stream,
        patch.object(Router, "parse", parse),
        patch.object(Store, "execute", execute),
        patch.object(Jobs, "finish", finish),
        patch.object(socket.socket, "connect", guard(original_connect)),
        patch.object(socket.socket, "connect_ex", guard(original_connect_ex)),
    ):
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Results).run(suite)
    routes = []
    for spec in registry.specs:
        observed = executions[spec.command]
        domain = [
            v
            for v in observed
            if not v["test"].startswith("test_acceptance_local.") and v["code"] != "job_queued"
        ]
        routes.append(
            {
                "command": spec.command,
                "family": spec.family,
                "action": spec.original_action,
                "block": spec.block,
                "syntax_observed": bool(syntax[spec.command]),
                "public_fields": [
                    {
                        "name": f.name,
                        "original": f.original,
                        "explicit_syntax_tests": sorted(syntax[spec.command].get(f.name, ())),
                        "domain_observation_tests": sorted(
                            {v["test"] for v in domain if f.name in v["fields"]}
                        ),
                    }
                    for f in spec.fields
                ],
                "observed_results": observed,
                "domain_observed": bool(domain),
                "acceptance": "TEST_ORACLES_IN_REFERENCED_TESTS; observation alone is not PASS",
            }
        )
    report = {
        "block": "R10-local",
        "test_success": result.wasSuccessful(),
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "routes": routes,
        "network_denied": network_denied,
        "limits": [
            "cold probes verify admission/guards/handler availability only",
            "field observation includes canonical defaults; explicit syntax spans recorded separately",
            "domain acceptance is asserted by test oracle, not inferred from status codes",
            "no remote provider, browser, WPP, Android or human acceptance",
        ],
    }
    (out / "observations.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "tests": result.testsRun,
                "success": result.wasSuccessful(),
                "routes": len(routes),
                "routes_with_domain_observations": sum(r["domain_observed"] for r in routes),
                "fields": sum(len(r["public_fields"]) for r in routes),
                "network_denied": len(network_denied),
            }
        )
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
