#!/usr/bin/env python3
"""Inventario estático acotado. Lee código/manifestos públicos; nunca private/ o NLP.

El catálogo se exporta por separado, cargando únicamente tools.catalog.
"""

import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/home/petrov/zhana")
OUT = ROOT / "docs/inventario"


def collect():
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    modified = set(
        subprocess.check_output(["git", "diff", "--name-only"], cwd=SOURCE, text=True).splitlines()
    )
    files = [
        SOURCE / "pyproject.toml",
        SOURCE / "calls/package.json",
        SOURCE / "calls/package-lock.json",
    ]
    files += sorted((SOURCE / "src/zhana").glob("*.py"))
    files += sorted((SOURCE / "src/zhana/tools").glob("*.py"))
    files += sorted((SOURCE / "calls/service").glob("*.*js"))
    files += sorted((SOURCE / "calls/policy").glob("*.js"))
    # Entrada NLP y sus adaptadores no son referencia de Botsky.
    files = [
        p
        for p in files
        if not any(word in p.name for word in ("nlp", "invocation", "conversation"))
    ]
    manifest, models, audiovisual = {}, {}, {}
    for path in files:
        rel = str(path.relative_to(SOURCE))
        data = path.read_bytes()
        manifest[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "modified": rel in modified}
        if path.suffix == ".py":
            source = data.decode()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.ClassDef) and (
                    node.name.endswith("Args") or node.name == "MediaOptions"
                ):
                    fields = {}
                    for field in node.body:
                        if isinstance(field, ast.AnnAssign) and isinstance(field.target, ast.Name):
                            fields[field.target.id] = {
                                "type": ast.unparse(field.annotation),
                                "default_constraint": ast.unparse(field.value)
                                if field.value
                                else None,
                            }
                    models[node.name] = {
                        "file": rel,
                        "line": node.lineno,
                        "fields": fields,
                        "contract": ast.get_source_segment(source, node),
                    }
        elif "/service/" in rel or "/policy/" in rel:
            audiovisual[rel] = {"sha256": manifest[rel]["sha256"]}
    for name, value in [
        ("reference.json", {"head": head, "files": manifest}),
        ("args.json", models),
        ("audiovisual-files.json", audiovisual),
    ]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(models)} modelos; {len(audiovisual)} archivos audiovisuales; referencia {head}")


if __name__ == "__main__":
    collect()
