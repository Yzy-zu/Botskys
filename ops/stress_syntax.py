#!/usr/bin/env python3
"""Variantes tipadas por campo, parser puro: no acredita éxito de herramientas."""

import argparse
import json
from collections import Counter

from botsky.commands.registry import Registry
from botsky.commands.router import CommandError, Router


def command(spec, override=None):
    override = override or {}
    options, positions = [], []
    for field in spec.fields:
        value = override.get(field.name, field.example)
        if field.option:
            options.extend([field.option] if field.kind == "flag" else [field.option, value])
        else:
            positions.append(value)
    return " ".join([spec.command, *options, *positions])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    args = parser.parse_args()
    invalid = {
        "enum": "__invalid_enum__",
        "int": "-1",
        "float": "nan",
        "seconds": "-1",
        "duration": "-1s",
        "date": "2026-02-30",
        "clock": "25:99",
        "pages": "0",
        "id": "bad/id",
        "bool": "maybe",
        "url": "not-a-url",
        "contacts": ",",
        "terms": ",",
    }
    rows = []
    router = Router()
    for spec in Registry().specs:
        base = command(spec)
        try:
            parsed = router.parse(base)
            rows.append(
                {
                    "route": spec.command,
                    "phase": "all_fields_explicit",
                    "verdict": "PASS",
                    "fields": sorted(parsed.spans),
                }
            )
        except CommandError as exc:
            rows.append(
                {
                    "route": spec.command,
                    "phase": "construction_review",
                    "verdict": "REVIEW",
                    "code": exc.code,
                    "reply": exc.reply,
                }
            )
            continue
        for field in spec.fields:
            if field.kind == "flag":
                altered = (
                    spec.command
                    + " "
                    + field.option
                    + " "
                    + field.option
                    + " "
                    + base[len(spec.command) :]
                )
            else:
                value = invalid.get(field.kind, '"' + "x" * (field.max_length + 1) + '"')
                altered = command(spec, {field.name: value})
            try:
                router.parse(altered)
                verdict, code = "REVIEW", "mutation_not_rejected"
            except CommandError as exc:
                verdict, code = "PASS", exc.code
            rows.append(
                {
                    "route": spec.command,
                    "field": field.name,
                    "kind": field.kind,
                    "phase": "invalid_boundary",
                    "verdict": verdict,
                    "code": code,
                }
            )
    value = {
        "level": "pure_syntax_only_no_effects_or_network",
        "counts": dict(Counter(r["verdict"] for r in rows)),
        "cases": len(rows),
        "rows": rows,
    }
    with open(args.output, "w") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(json.dumps({k: value[k] for k in ("level", "counts", "cases")}))


if __name__ == "__main__":
    main()
