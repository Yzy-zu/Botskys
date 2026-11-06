"""Operator-only bounded provider diagnostics; synthetic inputs, no delivery.

Never run automatically. Each invocation preserves evidence under a fresh run.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from botsky.adapters.gemini import GeminiContent
from botsky.engines.content_jobs import analysis_files
from botsky.engines.process import MediaError
from botsky.engines.web_results import parse_results

ROOT = Path(__file__).resolve().parents[1]


async def main(skip_rss=False):
    from google.genai import _api_client

    out = ROOT / "docs/evidencia/SOSPECHAS-20261106" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    profile = json.loads((ROOT / "private/integrations.json").read_text())["gemini"]
    model = GeminiContent(profile["key"], profile["model"])
    rows, wire = [], []
    original = _api_client.BaseApiClient._async_request

    async def capture(client, http_request, *args, **kwargs):
        request = http_request
        if request.method.lower() == "post":
            body = request.data
            files = []
            for content in body.get("contents", []):
                for part in content.get("parts", []):
                    inline = part.get("inlineData")
                    if inline:
                        data = base64.b64decode(inline["data"])
                        files.append(
                            {
                                "mime": inline.get("mimeType", inline.get("mime_type")),
                                "bytes": len(data),
                                "sha256": hashlib.sha256(data).hexdigest(),
                                "synthetic_content": data.decode("utf-8", errors="replace"),
                            }
                        )
            wire.append(
                {
                    "capture_boundary": "SDK serialized request before HTTP transport",
                    "contents": body.get("contents"),
                    "files": files,
                }
            )
        return await original(client, request, *args, **kwargs)

    with TemporaryDirectory() as temp:
        from pptx import Presentation

        directory = Path(temp)
        fixtures = []
        for kind in ("pptx", "invalid_json"):
            marker = "BOTSKY" + uuid.uuid4().hex.upper()
            path = directory / (kind + (".pptx" if kind == "pptx" else ".json"))
            if kind == "pptx":
                doc = Presentation()
                slide = doc.slides.add_slide(doc.slide_layouts[5])
                slide.shapes.title.text = marker
                doc.save(path)
            else:
                path.write_text('{"reference": "' + marker + '", "broken": [}')
            fixtures.append((kind, path, marker))
        fixtures.append(("no_attachment", None, "AUSENTE"))
        with patch.object(_api_client.BaseApiClient, "_async_request", capture):
            for kind, path, marker in fixtures:
                files = await analysis_files([path], directory / kind) if path else []
                prompt = "Devuelve únicamente el identificador que empieza por BOTSKY dentro del archivo adjunto. No lo inventes; si falta el archivo responde AUSENTE."
                row = {
                    "fixture": kind,
                    "expected_marker": marker,
                    "prompt": prompt,
                    "oracle": "Exact marker from file, absent from prompt/history"
                    if path
                    else "No file: must return AUSENTE",
                    "preprocessed": [
                        {
                            "mime": f.mime,
                            "bytes": f.size,
                            "sha256": hashlib.sha256(f.path.read_bytes()).hexdigest(),
                        }
                        for f in files
                    ],
                }
                before = len(wire)
                try:
                    text = await model.generate(prompt, files=files)
                    row.update(response=text, marker_matches=text.strip() == marker)
                except MediaError as exc:
                    row["error"] = exc.code
                row["wire_requests"] = wire[before:]
                rows.append(row)
                (out / "gemini.json").write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
                )
    searches = []
    search_cases = (
        []
        if skip_rss
        else [
            ("c02", "Botsky testing guide", ["Python", "tutorial"]),
            ("c03", "HTML standards specification", ["W3C", "HTML"]),
        ]
    )
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=15) as client:
        for case, query, terms in search_cases:
            row = {"case": case, "query": query, "required_terms": terms}
            try:
                response = await client.get(
                    "https://www.bing.com/search",
                    params={"q": query, "format": "rss"},
                    headers={"User-Agent": "Botsky/0.1 personal RSS search"},
                )
                raw = response.content
                if len(raw) > 256 * 1024:
                    raise ValueError("response_too_large")
                (out / (case + ".rss")).write_bytes(raw)
                row.update(
                    http_status=response.status_code,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    bytes=len(raw),
                )
                if response.status_code == 200:
                    try:
                        unfiltered = parse_results(raw, query)
                        filtered = parse_results(raw, query, terms)
                        row.update(
                            unfiltered=[vars(i) for i in unfiltered],
                            filtered=[vars(i) for i in filtered],
                        )
                    except Exception as exc:
                        row["parse_error"] = type(exc).__name__
            except httpx.HTTPError as exc:
                row["transport_error"] = type(exc).__name__
            searches.append(row)
            (out / "search.json").write_text(
                json.dumps(searches, ensure_ascii=False, indent=2) + "\n"
            )
    print(str(out.relative_to(ROOT)))
    print(
        json.dumps(
            {
                "gemini": [
                    {
                        "fixture": r["fixture"],
                        "marker_matches": r.get("marker_matches"),
                        "error": r.get("error"),
                        "captured_requests": len(r["wire_requests"]),
                    }
                    for r in rows
                ],
                "rss": [
                    {
                        "case": r["case"],
                        "status": r.get("http_status"),
                        "filtered_count": len(r.get("filtered", [])),
                    }
                    for r in searches
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-rss", action="store_true")
    asyncio.run(main(parser.parse_args().skip_rss))
