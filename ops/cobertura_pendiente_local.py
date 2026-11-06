"""Supplement the closed campaign with local, test-oracle-backed observations.

Records field names and result codes only. Never loads integration credentials.
An observation does not assert semantic success; inspect its referenced test.
"""

import hashlib
import ipaddress
import json
import os
import socket
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidencia/COBERTURA-20261106"


def main():
    from botsky.commands.router import Router
    from botsky.jobs import Jobs
    from botsky.store import Store

    OUT.mkdir(parents=True, exist_ok=True)
    run_directory = OUT / "runs" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_directory.mkdir(parents=True)
    baseline_path = ROOT / "docs/evidencia/STRESS-20261106/route-coverage.json"
    baseline = json.loads(baseline_path.read_text())
    active, parsed, observations, tests, denied = {"test": ""}, {}, [], {}, []
    parse_original, execute_original, finish_original = Router.parse, Store.execute, Jobs.finish

    def parse(router, text):
        value = parse_original(router, text)
        if value:
            parsed[text] = (value.spec.command, sorted(value.spans))
        return value

    def observe(store, identifier, phase):
        # Cold probes only check admission/availability, not domain acceptance.
        if active["test"].startswith("test_acceptance_local."):
            return
        db = store.connect()
        try:
            row = db.execute(
                "SELECT text,path_json,result_json FROM inbox WHERE id=?", (identifier,)
            ).fetchone()
        finally:
            db.close()
        if not row or not row["path_json"] or not row["result_json"]:
            return
        route = "/" + " ".join(json.loads(row["path_json"]))
        recorded_route, fields = parsed.get(row["text"], (None, []))
        result = json.loads(row["result_json"])
        item = {
            "test": active["test"],
            "route": route,
            "explicit_fields": fields if recorded_route == route else [],
            "phase": phase,
            "status": result["status"],
            "code": result["code"],
        }
        if item not in observations:
            observations.append(item)

    def execute(store, identifier, *args, **kwargs):
        value = execute_original(store, identifier, *args, **kwargs)
        observe(store, identifier, "committed_receipt")
        return value

    def finish(manager, job, *args, **kwargs):
        value = finish_original(manager, job, *args, **kwargs)
        if value:
            observe(manager.store, job["id"], "finished_worker")
        return value

    def guard(original):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                try:
                    local = ipaddress.ip_address(address[0]).is_loopback
                except ValueError:
                    local = address[0] == "localhost"
                if not local:
                    denied.append({"test": active["test"]})
                    raise OSError("COVERAGE_NON_LOOPBACK_DENIED")
            return original(sock, address)

        return connect

    class Results(unittest.TextTestResult):
        def startTest(self, test):
            active["test"] = test.id()
            parsed.clear()
            tests[test.id()] = "RUNNING"
            super().startTest(test)

        def addSuccess(self, test):
            tests[test.id()] = "PASS"
            super().addSuccess(test)

        def addFailure(self, test, err):
            tests[test.id()] = "FAIL"
            super().addFailure(test, err)

        def addError(self, test, err):
            tests[test.id()] = "ERROR"
            super().addError(test, err)

    os.environ["NODE_OPTIONS"] = "--require=" + str(ROOT / "ops/restringir_red_local.cjs")
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (
        (OUT / "python-tests.txt").open("w") as log,
        patch.object(Router, "parse", parse),
        patch.object(Store, "execute", execute),
        patch.object(Jobs, "finish", finish),
        patch.object(socket.socket, "connect", guard(socket.socket.connect)),
        patch.object(socket.socket, "connect_ex", guard(socket.socket.connect_ex)),
    ):
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Results).run(suite)
    successful = [o for o in observations if tests.get(o["test"]) == "PASS"]
    routes = []
    for row in baseline:
        observed = [o for o in successful if o["route"] == row["route"]]
        fields = sorted({f for o in observed for f in o["explicit_fields"]})
        routes.append(
            {
                "route": row["route"],
                "campaign_observed": bool(row["observed_cases"]),
                "campaign_unobserved_fields": row["unobserved_fields"],
                "local_observations": observed,
                "local_explicit_fields": fields,
                "remaining_campaign_field_gaps": sorted(
                    set(row["unobserved_fields"]) - set(fields)
                ),
                "acceptance": "SEE_TEST_ORACLE; LOCAL_ONLY" if observed else "NOT_OBSERVED_LOCALLY",
            }
        )
    summary = {
        "run_directory": str(run_directory.relative_to(ROOT)),
        "baseline_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        "tests": result.testsRun,
        "success": result.wasSuccessful(),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "non_loopback_attempts": len(denied),
        "routes": len(routes),
        "baseline_missing_route_count": sum(not r["campaign_observed"] for r in routes),
        "baseline_missing_explicit_field_count": sum(
            len(r["campaign_unobserved_fields"]) for r in routes
        ),
        "previously_missing_routes": [r["route"] for r in routes if not r["campaign_observed"]],
        "missing_routes_without_local_observation": [
            r["route"] for r in routes if not r["campaign_observed"] and not r["local_observations"]
        ],
        "remaining_explicit_field_gaps": {
            r["route"]: r["remaining_campaign_field_gaps"]
            for r in routes
            if r["remaining_campaign_field_gaps"]
        },
        "limits": [
            "Local doubles/fixtures only; no provider or human acceptance",
            "Cold route probes and parser-only tests excluded from domain observations",
            "Passing test plus observation requires review of referenced semantic assertions",
            "Closed campaign evidence is unchanged",
        ],
    }
    for name, value in (
        ("observations.json", observations),
        ("route-coverage.json", routes),
        ("test-results.json", tests),
        ("summary.json", summary),
    ):
        content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        (OUT / name).write_text(content)
        (run_directory / name).write_text(content)
    (run_directory / "python-tests.txt").write_bytes((OUT / "python-tests.txt").read_bytes())
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
