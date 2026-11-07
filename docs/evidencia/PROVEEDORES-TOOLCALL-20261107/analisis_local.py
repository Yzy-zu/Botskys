"""Análisis reproducible offline; no inferencia, credenciales ni acceso a producción.

Ejecutar desde la raíz: .venv/bin/python docs/evidencia/PROVEEDORES-TOOLCALL-20261107/analisis_local.py
Las declaraciones sirven para medir tamaño, no para ejecutarlas ni publicarlas.
Los escenarios de tokens son supuestos explícitos, no mediciones de tokenizador.
"""

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from botsky.commands.registry import Registry


def declaration(spec):
    properties = {}
    for field in spec.fields:
        kind = {
            "int": "integer", "float": "number", "seconds": "number",
            "duration": "integer", "flag": "boolean", "bool": "boolean",
        }.get(field.kind, "string")
        item = {"type": kind}
        if field.choices:
            item["enum"] = list(field.choices)
        if kind in ("integer", "number"):
            if field.minimum is not None:
                item["minimum"] = field.minimum
            if field.maximum is not None:
                item["maximum"] = field.maximum
        if kind == "string":
            item["maxLength"] = field.max_length
        if field.repeated or field.kind in ("terms", "contacts"):
            item = {"type": "array", "items": item, "maxItems": field.max_items}
        properties[field.name] = item
    return {
        "type": "function",
        "function": {
            "name": "_".join(spec.path),
            "description": spec.summary or spec.operation,
            "parameters": {
                "type": "object", "properties": properties,
                "required": [f.name for f in spec.fields if f.required],
                "additionalProperties": False,
            },
        },
    }


def size(value):
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return {"characters": len(serialized), "utf8_bytes": len(serialized.encode())}


specs = Registry().specs
families = defaultdict(list)
for spec in specs:
    families[spec.family].append(declaration(spec))

scenarios = []
for input_tokens, output_tokens, calls in ((2000, 100, 1), (3000, 200, 1), (4000, 200, 2)):
    # Totales por tarea, incluyendo todos los pases previos a ejecutar.
    neurons_glm = input_tokens * 5500 / 1e6 + output_tokens * 36400 / 1e6
    neurons_gemma = input_tokens * 9091 / 1e6 + output_tokens * 27273 / 1e6
    scenarios.append({
        "assumed_input_tokens_per_task": input_tokens,
        "assumed_output_tokens_per_task_including_reasoning": output_tokens,
        "inference_calls_per_task": calls,
        "groq_daily_upper_bound": min(1000 // calls, 200000 // (input_tokens + output_tokens)),
        "cloudflare_glm47_neurons_per_task": round(neurons_glm, 6),
        "cloudflare_glm47_daily_upper_bound": math.floor(10000 / neurons_glm),
        "cloudflare_gemma4_daily_upper_bound": math.floor(10000 / neurons_gemma),
        "openrouter_free_variant_daily_request_bound": 50 // calls,
        "sambanova_one_model_daily_request_bound": 20 // calls,
    })

output = {
    "kind": "offline_catalog_measurement_and_hypothetical_capacity",
    "provider_inference_executed": False,
    "production_data_read": False,
    "routes": len(specs),
    "distinct_operations": len({s.operation for s in specs}),
    "families": len(families),
    "all_route_declarations": size([declaration(s) for s in specs]),
    "by_family": {k: {"tools": len(v), **size(v)} for k, v in sorted(families.items())},
    "source_sha256": {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path("src/botsky/commands/registry.py"), Path("src/botsky/commands/types.py"))
    },
    "capacity_scenarios_not_benchmarks": scenarios,
    "caveats": [
        "Schemas are size probes; not a validated interpreter contract.",
        "Token counts are assumptions, never characters/4 or provider measurements.",
        "No cache hits, retries, other workloads or additional reasoning assumed.",
        "Daily upper bounds omit minute limits, contention and availability.",
        "Cloudflare rates from pricing table; model page rounding can differ.",
        "Free quotas apply to accounts/organizations; not to each Botsky user.",
    ],
}
print(json.dumps(output, ensure_ascii=False, indent=2))
