#!/usr/bin/env python3
"""Reempaqueta dependencias instaladas del intérprete invocante, sin red.

Uso de desarrollo: ejecutar con el Python que tiene los paquetes de referencia.
Solo dependencias nombradas y transitivas, no aplicaciones, datos ni credenciales.
Conserva metadatos/licencias; no equivale a un wheel original firmado por upstream.
"""

import argparse
import base64
import csv
import hashlib
import importlib.metadata as metadata
import io
import json
import zipfile
from pathlib import Path

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("packages", nargs="+")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending, done, manifest = list(args.packages), set(), {}
    while pending:
        requested = pending.pop()
        distribution = metadata.distribution(requested)
        name = distribution.metadata["Name"]
        if name.lower() in done:
            continue
        if name.lower() in ("zhana", "zhana-nlp", "botsky"):
            raise ValueError("solo dependencias de terceros, no aplicaciones")
        done.add(name.lower())
        for value in distribution.requires or ():
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
        entries = {}
        base = distribution.locate_file("").resolve()
        for file in distribution.files or ():
            path = distribution.locate_file(file)
            if not path.is_file() or not path.resolve().is_relative_to(base):
                continue
            relative = str(file)
            if (
                relative.endswith(("/RECORD", "/INSTALLER", "/REQUESTED", "/direct_url.json"))
                or "__pycache__" in file.parts
                or relative.endswith(".pyc")
            ):
                continue
            entries[relative] = path.read_bytes()
        wheel_paths = [n for n in entries if n.endswith(".dist-info/WHEEL")]
        if len(wheel_paths) != 1:
            raise ValueError(f"{name}: distribución sin WHEEL original; no se reempaqueta")
        wheel_path = wheel_paths[0]
        directory = wheel_path.split("/")[0]
        tags = {
            line[5:]
            for line in entries[wheel_path].decode().splitlines()
            if line.startswith("Tag: ")
        }
        tag = next(str(t) for t in sys_tags() if str(t) in tags)
        filename = directory.removesuffix(".dist-info") + "-" + tag + ".whl"
        record = io.StringIO(newline="")
        writer = csv.writer(record, lineterminator="\n")
        for relative, data in sorted(entries.items()):
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            writer.writerow((relative, "sha256=" + digest, len(data)))
        writer.writerow((directory + "/RECORD", "", ""))
        entries[directory + "/RECORD"] = record.getvalue().encode()
        output = args.out / filename
        if output.is_symlink():
            output.unlink()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative, data in sorted(entries.items()):
                info = zipfile.ZipInfo(relative, (2026, 11, 6, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        manifest[name] = {
            "version": distribution.version,
            "wheel": filename,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "files": len(entries),
            "origin": "repacked local installed distribution; no network",
        }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({n: v["version"] for n, v in manifest.items()}, indent=2))


if __name__ == "__main__":
    main()
