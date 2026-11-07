"""Datos del archivo final, jamás cifras deducidas de opciones pedidas."""

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

from .process import MediaError, run_process


async def enrich(output):
    if not output.files:
        return output
    facts = []
    for path in output.files:
        measured = {
            "bytes": path.stat().st_size,
            "extension": path.suffix.lower().removeprefix("."),
        }
        try:
            if path.suffix.lower() in (".mp3", ".mp4", ".webm", ".ogg", ".wav"):
                from .media_edit import _demuxer, _probe

                with path.open("rb") as stream:
                    header = stream.read(64)
                info = await _probe(path, _demuxer(header))
                value = float(info.get("format", {}).get("duration", "nan"))
                if math.isfinite(value) and value > 0:
                    measured["duration_seconds"] = value
            else:
                raw = await run_process(
                    [
                        sys.executable,
                        "-I",
                        str(Path(__file__).with_name("output_facts_worker.py")),
                        str(path),
                    ],
                    8,
                )
                value = json.loads(raw)
                allowed = {
                    "bytes",
                    "extension",
                    "pages",
                    "sheets",
                    "slides",
                    "files",
                    "width",
                    "height",
                    "pages_status",
                    "status",
                }
                if isinstance(value, dict) and not set(value) - allowed:
                    measured.update(value)
        except MediaError, OSError, ValueError:
            measured["status"] = "unavailable"
        facts.append(measured)
    return replace(
        output, result=replace(output.result, data={**output.result.data, "file_facts": facts})
    )
