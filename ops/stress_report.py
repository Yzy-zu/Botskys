#!/usr/bin/env python3
"""Recuento de descubrimiento para contraste posterior, sin confirmar claims de AGY."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from stress_agy import BATCHES, MODEL
from stress_backend import safe_text


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tools, results, candidates, manifests, reports = [], [], [], [], {}
    coverage = defaultdict(lambda: {"cases": [], "fields": set()})
    live_posts = fixture_posts = 0
    for batch_index, families in enumerate(BATCHES, 1):
        for tool in families:
            d = args.directory / f"batch{batch_index}" / tool
            state = read(d / "state.json", {})
            proposal = read(d / "proposal.json", {"cases": []})
            source = d / "execution/recovery1/results.json"
            if not source.exists():
                source = d / "execution/results.json"
            rows = read(source, [])
            counts = Counter(r["verdict"] for r in rows)
            report = read(d / "report.json")
            reopened = read(d / "report-recovery/result.json", {})
            reports[tool] = (
                report
                if report is not None
                else {
                    "report_unavailable": True,
                    "session_error": state.get("error"),
                    "raw_results_available": bool(rows),
                }
            )
            tools.append(
                {
                    "tool": tool,
                    "batch": batch_index,
                    "model": MODEL,
                    "proposed_cases": len(proposal["cases"]),
                    "recorded_cases": len(rows),
                    "counts": dict(counts),
                    "agent_report_available": report is not None,
                    "session_state": state.get("phase"),
                    "conversation_ids": state.get("conversations", []),
                    "reopened_conversation_ids": reopened.get("conversations", []),
                    "mechanical_repair": (d / "mechanical-repair.json").exists(),
                    "not_recorded_cases": [
                        c["id"]
                        for c in proposal["cases"]
                        if c["id"] not in {r["case"] for r in rows}
                    ],
                }
            )
            for r in rows:
                exposed = {
                    k: r.get(k)
                    for k in (
                        "case",
                        "tool",
                        "verdict",
                        "reason",
                        "route",
                        "operation",
                        "explicit_fields",
                        "evidence_level",
                        "physical_sample",
                        "seconds",
                        "delivery_states",
                        "runner_error",
                    )
                }
                exposed["command"] = safe_text(r.get("command", ""))
                exposed["expectation"] = r.get("proposal", {})
                value = r.get("result", {})
                exposed["result"] = {
                    "status": value.get("status"),
                    "code": value.get("code"),
                    "text": safe_text(value.get("text", ""))
                    if tool != "manage_minecraft"
                    else "[server details private]",
                }
                exposed["artifacts"] = [
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
                    for a in r.get("artifacts", [])
                ]
                results.append(exposed)
                if r.get("route"):
                    coverage[r["route"]]["cases"].append(tool + ":" + r["case"])
                    coverage[r["route"]]["fields"].update(r.get("explicit_fields", []))
            if report:
                for i, claim in enumerate(report.get("suspected_errors", []), 1):
                    candidates.append(
                        {
                            "id": f"{tool}-{i:02}",
                            "tool": tool,
                            "review_status": "UNREVIEWED_AGENT_CLAIM",
                            "claim": claim,
                            "evidence_results": str(source),
                            "warning": "Agent confidence is not independent verification; compare contract, fixture and observed output.",
                        }
                    )
            for ledger in (d / "execution").glob("**/remote-deliveries.json"):
                for post in read(ledger, []):
                    if post.get("evidence_level") == "provider":
                        live_posts += 1
                    elif post.get("evidence_level") == "delivery_fixture":
                        fixture_posts += 1
            for name in (
                "proposal.json",
                "state.json",
                "feedback.json",
                "report.json",
                "mechanical-repair.json",
            ):
                path = d / name
                if path.exists():
                    manifests.append(
                        {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}
                    )
            if source.exists():
                manifests.append(
                    {"path": str(source), "bytes": source.stat().st_size, "sha256": sha(source)}
                )
    from botsky.commands.registry import Registry

    routes = [
        {
            "route": s.command,
            "tool": s.family,
            "observed_cases": coverage[s.command]["cases"],
            "explicit_fields": sorted(coverage[s.command]["fields"]),
            "unobserved_fields": sorted({f.name for f in s.fields} - coverage[s.command]["fields"]),
            "acceptance": "OBSERVED_SEE_CASE" if coverage[s.command]["cases"] else "NOT_TESTED",
        }
        for s in Registry().specs
    ]
    summary = {
        "model": MODEL,
        "testers": len(tools),
        "batches": [10, 10, 10],
        "proposed_cases": sum(t["proposed_cases"] for t in tools),
        "recorded_cases": len(results),
        "counts": dict(Counter(r["verdict"] for r in results)),
        "reports_available": sum(t["agent_report_available"] for t in tools),
        "cli_starts": len(tools) + sum(bool(t["reopened_conversation_ids"]) for t in tools),
        "agent_claims_for_future_review": len(candidates),
        "routes_observed": sum(bool(r["observed_cases"]) for r in routes),
        "routes_total": len(routes),
        "provider_delivery_POSTs": live_posts,
        "delivery_fixture_POSTs": fixture_posts,
        "product_modified": False,
        "independent_high_tier_contrast_performed": False,
        "limits": [
            "SUSPECTED is discrepancy, not confirmed bug",
            "PASS includes negative checks and fixture delivery",
            "all scenario statements and agent reports require future independent contrast",
            "no real calls/browser, group/server mutations or transition",
            "case seconds include engine queue; not a latency benchmark",
        ],
    }
    for name, value in [
        ("summary.json", summary),
        ("tools.json", tools),
        ("results.json", results),
        ("claims-for-contrast.json", candidates),
        ("reports.json", reports),
        ("route-coverage.json", routes),
        ("private-evidence-hashes.json", manifests),
    ]:
        write(args.output / name, value)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
