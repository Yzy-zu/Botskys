#!/usr/bin/env python3
"""Resume un informe saneado de cobertura AGY sin adjudicar claims."""

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from stress_agy import BATCHES, MODEL


def read(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def clean(value):
    """Remove common secret/identity forms while preserving synthetic oracles."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            name = str(key)
            if re.search(
                r"(?i)(api.?key|access.?token|refresh.?token|secret|password|authorization|cookie)",
                name,
            ):
                cleaned[name] = "[REDACTED]"
            else:
                cleaned[name] = clean(item)
        return cleaned
    if isinstance(value, list):
        return [clean(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
    value = re.sub(r"(?i)(api[_-]?key|token|secret|password)=([^&\s]+)", r"\1=[REDACTED]", value)
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    value = re.sub(r"\b\+?\d[\d ()-]{7,}\d\b", "[PHONE_OR_ID]", value)
    value = re.sub(r"[A-Za-z0-9_-]+@(?:s\.whatsapp\.net|lid)|[0-9-]+@g\.us", "[IDENTITY]", value)
    value = re.sub(r"\b[a-f0-9]{32}\b", "[ID]", value, flags=re.I)
    value = re.sub(r"(?:/home/[^\s:]+|private/[^\s:]+)", "[PRIVATE_PATH]", value)
    return value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.directory.resolve(), args.output.resolve()
    if not root.is_dir():
        parser.error("directory debe existir")
    os.umask(0o077)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)

    from botsky.commands.registry import Registry

    specs = Registry().specs
    tools, results, reports, claims = [], [], {}, []
    parsed_route_cases = defaultdict(list)
    observed_route_cases = defaultdict(list)
    route_fields = defaultdict(set)
    all_counts = Counter()
    kind_counts = defaultdict(Counter)
    result_manifest = []
    for batch_number, names in enumerate(BATCHES, 1):
        for tool in names:
            directory = root / f"batch{batch_number}" / tool
            state = read(directory / "state.json", {})
            proposal = read(directory / "proposal.json", {})
            report = read(directory / "report.json")
            reports[tool] = {
                "available": report is not None,
                "session_phase": state.get("phase"),
                "suspected_claims": len((report or {}).get("suspected_errors", [])),
                "oracle_issues": len((report or {}).get("oracle_issues", [])),
                "blocked_items": len((report or {}).get("blocked", [])),
                "coverage_gaps": clean((report or {}).get("coverage_gaps", [])),
                "report": clean(report) if report is not None else None,
            }
            for claim_index, claim in enumerate((report or {}).get("suspected_errors", []), 1):
                claims.append(
                    {
                        "id": f"{tool}-{claim_index:02}",
                        "tool": tool,
                        "review_status": "UNREVIEWED_AGENT_CLAIM",
                        "classification": "NOT_ADJUDICATED",
                        "claim": clean(claim),
                    }
                )

            attempt_paths = sorted(directory.glob("execution/**/results.json"))
            rows = []
            for attempt_path in attempt_paths:
                attempt = str(attempt_path.parent.relative_to(directory))
                current = read(attempt_path, [])
                result_manifest.append(
                    {
                        "tool": tool,
                        "attempt": attempt,
                        "bytes": attempt_path.stat().st_size,
                        "sha256": sha(attempt_path),
                    }
                )
                rows.extend((attempt, row) for row in current)

            counts = Counter()
            by_kind = defaultdict(Counter)
            parsed_route_set = set()
            observed_route_set = set()
            fields_set = set()
            for attempt, row in rows:
                kind = (row.get("proposal") or {}).get("kind", "unknown")
                verdict = row.get("verdict", "unknown")
                counts[verdict] += 1
                by_kind[kind][verdict] += 1
                all_counts[verdict] += 1
                kind_counts[kind][verdict] += 1
                route = row.get("route")
                explicit = row.get("explicit_fields", [])
                if route:
                    case_ref = f"{tool}:{row.get('case')}:{attempt}"
                    parsed_route_cases[route].append(case_ref)
                    parsed_route_set.add(route)
                    fields_set.update(explicit)
                    if row.get("receipt") and row.get("result"):
                        observed_route_cases[route].append(case_ref)
                        route_fields[route].update(explicit)
                        observed_route_set.add(route)
                raw_result = row.get("result", {})
                if tool in {"manage_admin", "manage_minecraft"}:
                    safe_result = {
                        "status": raw_result.get("status"),
                        "code": raw_result.get("code"),
                        "text": "[sensitive operational details withheld]",
                    }
                else:
                    safe_result = clean(raw_result)
                exposed = {
                    "tool": tool,
                    "case": row.get("case"),
                    "attempt": attempt,
                    "kind": kind,
                    "verdict": verdict,
                    "route_effective": route,
                    "operation_effective": row.get("operation"),
                    "explicit_fields_effective": sorted(explicit),
                    "command": clean(row.get("command")),
                    "expectation": clean(row.get("proposal", {})),
                    "result": safe_result,
                    "artifacts": clean(
                        [
                            {
                                k: a[k]
                                for k in (
                                    "format",
                                    "bytes",
                                    "sha256",
                                    "pages",
                                    "image_size",
                                    "ffprobe",
                                    "zip_entries",
                                    "xml_documents_checked",
                                    "text_chars",
                                )
                                if k in a
                            }
                            for a in row.get("artifacts", [])
                        ]
                    ),
                    "evidence_level": row.get("evidence_level"),
                    "reason": clean(row.get("reason")),
                    "runner_error": clean(row.get("runner_error")),
                    "delivery_states": row.get("delivery_states", []),
                }
                results.append(exposed)

            state_summary = {
                "tool": tool,
                "batch": batch_number,
                "state_file_available": (directory / "state.json").is_file(),
                "model": state.get("model", MODEL),
                "phase": state.get("phase", "NOT_STARTED"),
                "turns": state.get("turns"),
                "elapsed_seconds": state.get("elapsed_seconds"),
                "error": clean(state.get("error")),
                "conversation_count": len(state.get("conversations", [])),
                "proposed_cases": len(proposal.get("cases", []))
                if isinstance(proposal.get("cases", []), list)
                else None,
                "recorded_rows": len(rows),
                "parsed_routes": sorted(parsed_route_set),
                "observed_routes": sorted(observed_route_set),
                "effective_fields": sorted(fields_set),
                "verdict_counts": dict(counts),
                "kind_verdict_counts": {k: dict(v) for k, v in by_kind.items()},
                "report_available": report is not None,
            }
            tools.append(state_summary)

    coverage = []
    for spec in specs:
        route = spec.command
        fields = route_fields[route]
        coverage.append(
            {
                "route": route,
                "family": spec.family,
                "operation": spec.operation,
                "parsed_cases": parsed_route_cases[route],
                "observed_cases": observed_route_cases[route],
                "effective_fields": sorted(fields),
                "unobserved_fields": sorted({f.name for f in spec.fields} - fields),
                "parsed": bool(parsed_route_cases[route]),
                "coverage": "OBSERVED" if observed_route_cases[route] else "NOT_TESTED",
            }
        )
    summary = {
        "model": MODEL,
        "expected_tools": sum(len(batch) for batch in BATCHES),
        "tool_states_present": sum(t["state_file_available"] for t in tools),
        "proposed_cases": sum(t["proposed_cases"] or 0 for t in tools),
        "recorded_result_rows": len(results),
        "verdict_counts": dict(all_counts),
        "kind_verdict_counts": {k: dict(v) for k, v in kind_counts.items()},
        "reports_available": sum(t["report_available"] for t in tools),
        "effective_routes_observed": sum(bool(r["observed_cases"]) for r in coverage),
        "effective_routes_total": len(coverage),
        "claims_are_adjudicated": False,
        "human_content_acceptance": "NOT_TESTED",
        "human_delivery_receipt": "NOT_TESTED",
        "notes": [
            "SUSPECTED/discrepancy labels are unadjudicated claims, not confirmed errors.",
            "Parsed and observed routes are separate; observation requires a receipt and result, including guards.",
            "An observed guard does not establish a business effect; BLOCKED and NOT_TESTED are not success.",
            "This is a sanitized index; inspect private evidence under its existing access controls.",
        ],
    }
    for name, value in (
        ("summary.json", summary),
        ("tools.json", tools),
        ("results.json", results),
        ("reports.json", reports),
        ("claims-for-contrast.json", claims),
        ("route-coverage.json", coverage),
        ("result-manifest.json", result_manifest),
    ):
        destination = output / name
        destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        destination.chmod(0o600)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
