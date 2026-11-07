"""Comparación local antes/después con fixtures idénticos; sin proveedores/producción."""

import json
import os
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "4482c46"


def worker(source):
    sys.path.insert(0, str(Path(source) / "src"))
    from PIL import Image
    from pypdf import PdfWriter

    from botsky.adapters.local import LocalAdapter
    from botsky.app import Application
    from botsky.config import Settings
    from botsky.contracts import Result
    from botsky.store import context_of

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        now = 1793962800000
        settings = Settings(
            root,
            "visual-benchmark",
            "synthetic",
            1,
            root / "private/local.sqlite3",
            now - 1000,
            "owner",
            frozenset(),
            frozenset(),
        )
        app = Application(settings, clock=lambda: now)
        app.store.native_tables_enabled = True
        adapter = LocalAdapter(settings, lambda: now)
        pdf = root / "fixture.pdf"
        writer = PdfWriter()
        writer.add_blank_page(100, 100)
        with pdf.open("wb") as stream:
            writer.write(stream)
        webp = root / "fixture.webp"
        Image.new("RGB", (32, 32), "blue").save(webp, "WEBP")
        results = {}
        for label in ("notes_literal", "pdf_caption", "sticker", "xp_table"):
            durations = []
            plans = []
            for i in range(40):
                receipt = app.receive(
                    adapter.incoming(label + str(i), "owner", "private", "/ayuda")
                )
                with app.store.transaction() as db:
                    row = db.execute("SELECT * FROM inbox WHERE id=?", (receipt.id,)).fetchone()
                    context = context_of(row)
                    db.execute("DELETE FROM outbox WHERE receipt_id=?", (receipt.id,))
                    if label == "notes_literal":
                        result = Result(
                            "ok",
                            "notes_found",
                            "Texto anterior",
                            {
                                "query": "",
                                "total": 1,
                                "page": 1,
                                "pages": 1,
                                "items": [
                                    {"id": 1, "text": "Texto *literal* y e\u0301 de prueba."}
                                ],
                            },
                        )
                    elif label in ("pdf_caption", "sticker"):
                        path = pdf if label == "pdf_caption" else webp
                        staged = app.artifacts.stage(path, output=True)
                        identifier = app.artifacts.register(
                            db,
                            staged,
                            context,
                            "fixture",
                            now,
                            origin="result",
                            receipt_id=receipt.id,
                        )
                        result = Result(
                            "ok",
                            "pdf_assembled" if label == "pdf_caption" else "sticker_created",
                            "PDF terminado." if label == "pdf_caption" else "Sticker listo.",
                            {
                                "artifacts": [identifier],
                                "file_facts": [
                                    {
                                        "format": staged.format,
                                        "extension": staged.format,
                                        "bytes": path.stat().st_size,
                                        **({"pages": 1} if label == "pdf_caption" else {}),
                                    }
                                ],
                            },
                        )
                    else:
                        result = Result(
                            "ok",
                            "xp_top",
                            "Top XP",
                            {
                                "items": [
                                    {"account_id": 1, "balance": 100, "level": 6, "self": True}
                                ]
                            },
                        )
                    started = time.perf_counter()
                    app.store.enqueue(db, context, result, now)
                    durations.append((time.perf_counter() - started) * 1000)
                    parts = db.execute(
                        "SELECT kind,payload,rich_payload_json FROM outbox WHERE receipt_id=? ORDER BY position",
                        (receipt.id,),
                    ).fetchall()
                    plans.append(
                        {
                            "parts": len(parts),
                            "storage_bytes": sum(
                                len(r["payload"].encode()) + len(r["rich_payload_json"].encode())
                                for r in parts
                            ),
                            "text_or_caption_bytes": sum(
                                len(r["payload"].encode())
                                + len(
                                    json.loads(r["rich_payload_json"]).get("caption", "").encode()
                                )
                                for r in parts
                            ),
                        }
                    )
            results[label] = {
                "iterations": 40,
                "plan_median_ms": round(statistics.median(durations), 3),
                "plan_p95_ms": round(sorted(durations)[37], 3),
                "parts_median": statistics.median(p["parts"] for p in plans),
                "storage_bytes_median": statistics.median(p["storage_bytes"] for p in plans),
                "text_or_caption_bytes_median": statistics.median(
                    p["text_or_caption_bytes"] for p in plans
                ),
            }
        print(json.dumps(results))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
        return
    os.umask(0o077)
    out = ROOT / "docs/evidencia/UI-UX-CONT-20261107/benchmark.json"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        archive = root / "baseline.tar"
        with archive.open("wb") as stream:
            subprocess.run(
                ["git", "archive", BASELINE, "src/botsky"], cwd=ROOT, stdout=stream, check=True
            )
        with tarfile.open(archive) as source:
            source.extractall(root, filter="data")
        baseline = json.loads(
            subprocess.check_output([sys.executable, __file__, "--worker", str(root)], text=True)
        )
        current = json.loads(
            subprocess.check_output([sys.executable, __file__, "--worker", str(ROOT)], text=True)
        )
    report = {
        "baseline": BASELINE,
        "current": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scope": "Planificación local de40fixtures porcaso; no motor/proveedor/red/cliente. Másbytesinternospuedenconservarfuente literal.",
        "before": baseline,
        "after": current,
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
