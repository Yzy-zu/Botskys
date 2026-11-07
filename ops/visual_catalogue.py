"""Catálogo reproducible desde pruebas con fixtures propios; nunca aceptación visual.

No construye una app productiva, no carga perfiles y bloquea red no loopback.
Guarda salidas de pruebas que pasan y distingue sondeo/guardia de efecto local.
"""

import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    from botsky.commands.registry import Registry
    from botsky.contracts import canonical
    from botsky.presentation.domains import present
    from botsky.presentation.splitter import units
    from botsky.store import Store

    os.umask(0o077)
    target = ROOT / "docs/evidencia/UI-UX-CATALOGO-20261107" / datetime.now(UTC).strftime("%H%M%S")
    target.mkdir(parents=True, exist_ok=False)
    os.environ["NODE_OPTIONS"] = "--require=" + str(ROOT / "ops/restringir_red_local.cjs")
    active = {"test": ""}
    samples = {}
    tests = {}
    denied = []
    metrics = []
    original_enqueue = Store.enqueue

    def enqueue(store, db, context, result, now):
        started = time.perf_counter()
        value = original_enqueue(store, db, context, result, now)
        if not active["test"] or not Path(store.path).resolve().is_relative_to("/tmp"):
            return value
        parent = db.execute(
            "SELECT text,path_json,command_json FROM inbox WHERE id=?", (context.receipt_id,)
        ).fetchone()
        if not parent or not parent["path_json"] or result.code == "job_queued":
            return value
        path = json.loads(parent["path_json"])
        if not path:
            return value
        route = "/" + " ".join(path)
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT position,kind,payload,rich_payload_json,visual_version,content_sha256 FROM outbox WHERE receipt_id=? ORDER BY position",
                (context.receipt_id,),
            )
        ]
        if not rows:
            return value
        parts = []
        for row in rows:
            part = {**row, "rich_payload": json.loads(row.pop("rich_payload_json"))}
            part.pop("rich_payload_json", None)
            part["utf16_units"] = units(part["payload"])
            if part["kind"] == "text" and part["utf16_units"] > 3500:
                raise AssertionError("texto excede UTF16")
            parts.append(part)
        projected = present(result)
        native = projected.data.get("native_tables") or (
            [projected.data["native_table"]] if projected.data.get("native_table") else []
        )
        item = {
            "route": route,
            "operation": json.loads(parent["command_json"])["operation"],
            "test": active["test"],
            "input": parent["text"],
            "result": json.loads(result.to_json()),
            "document": projected.data.get("document"),
            "native_preview": native,
            "parts": parts,
            "synthetic_data": True,
            "provider": "DOBLE_O_LOCAL",
            "client_visual": "NO_PROBADO",
            "human_reception": "NO_PROBADO",
        }
        key = (route, result.code, result.status, active["test"])
        # Una muestra representativa por contrato/estado/test, sin miles de copias.
        samples.setdefault(key, item)
        metrics.append(
            {
                "route": route,
                "test": active["test"],
                "parts": len(parts),
                "text_utf16": sum(p["utf16_units"] for p in parts),
                "plan_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )
        return value

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            active["test"] = test.id()
            super().startTest(test)

        def addSuccess(self, test):
            tests[test.id()] = "PASS"
            super().addSuccess(test)

        def addFailure(self, test, error):
            tests[test.id()] = "FAIL"
            super().addFailure(test, error)

        def addError(self, test, error):
            tests[test.id()] = "ERROR"
            super().addError(test, error)

        def addSkip(self, test, reason):
            tests[test.id()] = "SKIP"
            super().addSkip(test, reason)

    def guard(original):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                try:
                    local = ipaddress.ip_address(address[0]).is_loopback
                except ValueError:
                    local = address[0] == "localhost"
                if not local:
                    denied.append(active["test"])
                    raise OSError("VISUAL_EXTERNAL_NETWORK_DENIED")
            return original(sock, address)

        return connect

    source_files = sorted((ROOT / "src/botsky").rglob("*.py")) + sorted(
        (ROOT / "calls/service").glob("*.*")
    )
    source_hashes = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
        if path.is_file()
    }
    source_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (
        (target / "tests.log").open("w") as log,
        patch.object(Store, "enqueue", enqueue),
        patch.object(socket.socket, "connect", guard(socket.socket.connect)),
        patch.object(socket.socket, "connect_ex", guard(socket.socket.connect_ex)),
    ):
        run = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Result).run(suite)
    cases = []
    sample_dir = target / "samples"
    sample_dir.mkdir()
    synthetic_only = (
        "test_presentation.",
        "test_visual_integrity.",
        "test_native_tables.",
        "test_acceptance_local.",
    )
    allowed_previews = {
        "download_choices",
        "drive_choices",
        "message_preview",
        "pack_offer",
        "memory_delete_preview",
        "nuclear_preview",
    }
    for item in samples.values():
        item["asserting_test_result"] = tests.get(item["test"], "UNKNOWN")
        item["semantic_candidate"] = (
            item["asserting_test_result"] == "PASS"
            and not item["test"].startswith(synthetic_only)
            and (
                item["result"]["status"] in ("ok", "cancelled")
                or item["result"]["code"] in allowed_previews
            )
        )
        sample_hash = hashlib.sha256(canonical(item).encode()).hexdigest()
        file = sample_dir / (sample_hash[:20] + ".json")
        file.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n")
        cases.append(
            {
                "route": item["route"],
                "code": item["result"]["code"],
                "status": item["result"]["status"],
                "test": item["test"],
                "test_result": item["asserting_test_result"],
                "semantic_candidate": item["semantic_candidate"],
                "sample": str(file.relative_to(target)),
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            }
        )
    coverage = []
    for spec in Registry().specs:
        observed = [case for case in cases if case["route"] == spec.command]
        meaningful = [case for case in observed if case["semantic_candidate"]]
        coverage.append(
            {
                "route": spec.command,
                "operation": spec.operation,
                "family": spec.family,
                "observed": len(observed),
                "semantic_candidates": len(meaningful),
                "review": "PENDIENTE_REVISAR_ORACLE" if meaningful else "HUECO_O_SOLO_GUARDIA",
                "sample_refs": [case["sample"] for case in meaningful],
                "visual": "NO_PROBADO",
            }
        )
    summary = {
        "source_revision": source_revision,
        "source_sha256": source_hashes,
        "source_unchanged": all(
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
            for path, digest in source_hashes.items()
        ),
        "tests": run.testsRun,
        "success": run.wasSuccessful(),
        "failures": len(run.failures),
        "errors": len(run.errors),
        "skipped": len(run.skipped),
        "non_loopback_attempts": len(denied),
        "routes": len(coverage),
        "families": len({s.family for s in Registry().specs}),
        "operation_roots": len({s.family.split(".")[0] for s in Registry().specs}),
        "captured_routes": sum(bool(r["observed"]) for r in coverage),
        "semantic_candidate_routes": sum(bool(r["semantic_candidates"]) for r in coverage),
        "samples": len(cases),
        "client_visual": "NO_PROBADO",
        "human_reception": "NO_PROBADO",
        "note": "Candidato exige revisión del oracle del test. Captura/guardia no acreditan efecto ni render.",
    }
    for name, data in (
        ("index.json", cases),
        ("coverage.json", coverage),
        ("metrics.json", metrics),
        ("summary.json", summary),
    ):
        (target / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "directory": str(target.relative_to(ROOT)),
                **{key: value for key, value in summary.items() if key != "source_sha256"},
            }
        )
    )
    return 0 if run.wasSuccessful() and not denied and summary["source_unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
