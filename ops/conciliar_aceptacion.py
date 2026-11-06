"""Índice de evidencia R10. Una observación no se convierte en PASS semántico."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    from botsky.commands.registry import Registry

    observed = json.loads((ROOT / "private/R10/observations.json").read_text())
    if not observed["test_success"] or observed["network_denied"]:
        raise ValueError("acceptance_run_not_clean")
    registry = Registry()
    by_command = {r["command"]: r for r in observed["routes"]}
    if set(by_command) != {s.command for s in registry.specs}:
        raise ValueError("acceptance_registry_changed")
    for spec in registry.specs:
        row = by_command[spec.command]
        if (
            not row["domain_observed"]
            or not row["syntax_observed"]
            or {f["name"] for f in row["public_fields"]} != {f.name for f in spec.fields}
        ):
            raise ValueError("acceptance_route_gap: " + spec.command)
        if any(
            not f["explicit_syntax_tests"] or not f["domain_observation_tests"]
            for f in row["public_fields"]
        ):
            raise ValueError("acceptance_field_gap: " + spec.command)
    rows = []
    with (ROOT / "docs/command-matrix.csv").open(newline="") as file:
        original = list(csv.DictReader(file))
    for old in original:
        family, action, field = old["family"], old["original_action"], old["original_field"]
        candidates = [
            s
            for s in registry.specs
            if s.family == family and (action == "única" or s.original_action == action)
        ]
        if family == "manage_conversation" and action == "cancel":
            candidates = [s for s in registry.specs if s.command == "/cancelar"]
        if family == "media_options":
            candidates = [s for s in registry.specs if any(f.name == field for f in s.fields)]
        evidence = [by_command[s.command] for s in candidates]
        tests = sorted(
            {
                v["test"]
                for item in evidence
                for v in item["observed_results"]
                if not v["test"].startswith("test_acceptance_local.")
            }
        )
        fields = [
            f
            for item in evidence
            for f in item["public_fields"]
            if f["name"] in old["new_field"].split("; ")
            or f["name"] == field
            or f["original"] == field
        ]
        syntax = sorted({t for f in fields for t in f["explicit_syntax_tests"]})
        domain = sorted({t for f in fields for t in f["domain_observation_tests"]})
        if field == "interpretation":
            state = "CANCELLED_SCOPE_NO_INTERPRETER"
            tests = ["tests/test_commands.py; deterministic commands; no classifier"]
        elif old["new_field"] == "no aplica":
            state = "NOT_APPLICABLE_FOR_ACTION"
        elif family.startswith("audiovisual.") and action == "backend":
            state = "LOCAL_COMPONENTS; NATIVE_PROVIDER_RENDER_NOT_TESTED"
            tests = ["docs/evidencia/R9.json", "docs/evidencia/R10-node-tests.txt"]
        elif family == "conversation" and action in {"ask", "silent"}:
            state = "ADAPTED_OUTPUT_CONTRACT"
            tests = ["tests/test_ai.py", "tests/test_commands.py"]
        elif syntax and domain:
            state = "PUBLIC_FIELD_SYNTAX_AND_DOMAIN_OBSERVED"
        elif evidence:
            state = "ROUTE_OBSERVED; BACKEND_DERIVED_OR_CONSTANT"
        else:
            raise ValueError("unreconciled_inventory_row: " + repr((family, action, field)))
        rows.append(
            {
                "family": family,
                "action": action,
                "original_field": field,
                "command": old["command"],
                "mapping": old["new_field"],
                "local_evidence": state,
                "test_references": "; ".join(domain or tests),
                "syntax_references": "; ".join(syntax),
                "decision": old["decision"],
                "semantic_acceptance": "Use the assertions in referenced tests; not inferred from observation",
                "remote_human_acceptance": "NOT_TESTED; subsequent explicit commission required",
            }
        )
    directory = ROOT / "docs"
    with (directory / "acceptance-matrix.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    inventory = json.loads((directory / "inventario/audiovisual-files.json").read_text())
    av = []
    replacements = {
        "calls/service/main.cjs": "calls/bootstrap.cjs",
        "calls/service/config.cjs": "calls/policy/botsky-policy.cjs",
    }
    for name, reference in inventory.items():
        destination = replacements.get(name, name)
        file = ROOT / destination
        if not file.is_file():
            raise ValueError("av_component_missing: " + name)
        sha = hashlib.sha256(file.read_bytes()).hexdigest()
        av.append(
            {
                "source": name,
                "destination": destination,
                "source_sha256": reference["sha256"],
                "destination_sha256": sha,
                "decision": "VERBATIM"
                if sha == reference["sha256"]
                else "EXPLICIT_REPLACEMENT"
                if name in replacements or name.endswith("live-credentials.cjs")
                else "BOUNDARY_ADAPTATION",
                "evidence": "docs/R9.md; docs/evidencia/R9.json; R10-node-tests.txt",
                "browser_provider_human": "NOT_TESTED",
            }
        )
    catalog = json.loads((directory / "inventario/catalog.json").read_text())
    assert len(catalog) == 30 and len(av) == 48
    report = {
        "status": "LOCAL_EVIDENCE_RECONCILED; R10_GLOBAL_OPEN",
        "catalog_families": len(catalog),
        "original_matrix_rows": len(rows),
        "routes": len(by_command),
        "public_fields": sum(len(r["public_fields"]) for r in by_command.values()),
        "local_evidence_counts": dict(Counter(r["local_evidence"] for r in rows)),
        "audiovisual": av,
        "route_observations": "R10-route-observations.json",
        "local_matrix": "../acceptance-matrix.csv",
        "limits": [
            "all 152 routes and 190 public fields have indexed observations; these do not certify every value/branch",
            "per-test oracles distinguish rejection, success, uncertainty, duplicate and cleanup",
            "provider configuration, real transport, Android and human acceptance remain open",
            "no implicit reduction of scope or authorization for transition",
        ],
    }
    (directory / "evidencia/R10-inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "catalog_families",
                    "original_matrix_rows",
                    "routes",
                    "public_fields",
                    "local_evidence_counts",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    build()
