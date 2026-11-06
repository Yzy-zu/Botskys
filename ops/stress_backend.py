#!/usr/bin/env python3
"""Ejecutor de casos AGY: evidencia antes que diagnóstico, sin modificar producto.

Una DB por herramienta. Proveedores reales; entregas de batería capturadas localmente
y hasta dos muestras reales por herramienta. Todo ACK simulado se etiqueta como tal.
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import zipfile
from collections import Counter
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import campana_lab as lab
import httpx
from agy_lab import save
from stress_agy import BATCHES, FIXTURES

from botsky.adapters.evolution import EvolutionTransport
from botsky.adapters.local import LocalAdapter
from botsky.artifacts import ArtifactProblem
from botsky.commands.router import CommandError, Router
from botsky.config import Settings
from botsky.contracts import CommandContext, DeliveryAck, Result, Scope
from botsky.delivery import deliver_async
from botsky.integrations import Integrations, read_profile

ROOT = Path(__file__).resolve().parents[1]
ENGINE_LIMIT = asyncio.Semaphore(2)
SEND_LIMIT = asyncio.Semaphore(1)


class Captured:
    async def send(self, part):
        return DeliveryAck(True, f"fixture-{part.receipt_id}-{part.position}")


class RoutingHTTP(httpx.AsyncBaseTransport):
    def __init__(self, owner, inner):
        self.owner, self.inner = owner, inner

    async def handle_async_request(self, request):
        is_message = (
            request.url.path.startswith("/message/") and request.url.host == self.owner.origin.host
        )
        if is_message:
            self.owner.posts[-1]["evidence_level"] = (
                "provider" if self.owner.live else "delivery_fixture"
            )
            lab.save(self.owner.path, self.owner.posts)
            if not self.owner.live:
                return httpx.Response(201, json={"key": {"id": "fixture-" + uuid4().hex}})
            async with SEND_LIMIT:
                return await self.inner.handle_async_request(request)
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


class ToolHTTP(lab.LabHTTP):
    def __init__(self, directory, base, target, owner):
        super().__init__(directory, base, target, [target, owner], limit=170)
        self.live = False
        self.inner = RoutingHTTP(self, self.inner)


async def prepare(base):
    base.mkdir(mode=0o700, parents=True, exist_ok=False)
    settings = Settings.load(ROOT / "private/config.integrations.toml")
    profile = read_profile(ROOT / "private/integrations.json")
    from botsky.adapters.groups import Groups

    async with httpx.AsyncClient(trust_env=False, timeout=20) as http:
        e = profile["evolution"]
        client = Groups(e["base_url"], e["instance"], e["api_key"], settings.bot_ids, client=http)
        verified = []
        for chat in settings.allowed_groups:
            meta = await client._request("GET", "findGroupInfos", chat)
            meta = meta.get("group", meta)
            verified.append({"target": chat, "subject": meta.get("subject")})
        save(base / "group-preflight.json", verified)
    lab.prepare(base)
    async with Integrations(
        Settings.load(base / "app/config.toml"), base / "app/private/integrations.json"
    ) as app:
        paths = await lab.fixtures(base / "fixtures", app)
    from docx import Document
    from openpyxl import Workbook
    from PIL import Image
    from pptx import Presentation
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen.canvas import Canvas

    f = base / "fixtures"
    Image.open(paths["image"]).save(f / "jpg.jpg")
    Image.open(paths["image"]).save(f / "webp.webp")
    Image.new("RGB", (256, 256), "white").save(f / "blank_image.png")
    Image.new("RGB", (4097, 16), "red").save(f / "wide_image.png")
    Image.new("RGB", (4000, 4000), "navy").save(f / "large_image.png")
    Image.new("RGB", (64, 64), "red").save(
        f / "animated_webp.webp",
        save_all=True,
        append_images=[Image.new("RGB", (64, 64), "blue")],
        duration=100,
        loop=0,
    )
    (f / "broken_png.png").write_bytes(b"\x89PNG\r\n\x1a\ntruncated")
    (f / "broken_pdf.pdf").write_bytes(b"%PDF-1.7\n1 0 obj <</Type /Catalog>>\ntruncated")
    writer = PdfWriter()
    for p in PdfReader(paths["pdf"]).pages:
        writer.add_page(p)
    writer.encrypt("Botsky-synthetic-password")
    with (f / "encrypted_pdf.pdf").open("wb") as out:
        writer.write(out)
    c = Canvas(str(f / "scan_pdf.pdf"))
    c.drawImage(str(paths["image"]), 40, 300, width=500, height=250)
    c.save()
    writer = PdfWriter()
    for _ in range(501):
        writer.add_blank_page(width=72, height=72)
    with (f / "many_pages_pdf.pdf").open("wb") as out:
        writer.write(out)
    (f / "empty.bin").touch()
    with (f / "oversized.bin").open("wb") as out:
        out.truncate(1_000_000_001)
    # Actual 8MiB UTF-8 document, not an advertised synthetic byte count.
    with (f / "large_txt.txt").open("wb") as out:
        for _ in range(8192):
            out.write(b"Botsky Lab 31415 " + b"x" * 1007 + b"\n")
    doc = Document()
    doc.add_paragraph("Botsky Lab31415 - Contenido sintetico")
    doc.save(f / "docx.docx")
    for name, multi in [("xlsx", False), ("multisheet_xlsx", True)]:
        book = Workbook()
        sheet = book.active
        sheet.title = "Datos"
        sheet.append(["nombre", "cantidad"])
        sheet.append(["alpha", 3])
        sheet.append(["beta", 7])
        if multi:
            book.create_sheet("Segunda").append(["gamma", 11])
        book.save(f / (name + ".xlsx"))
        book.close()
    pres = Presentation()
    slide = pres.slides.add_slide(pres.slide_layouts[5])
    slide.shapes.title.text = "Botsky Lab31415"
    pres.save(f / "pptx.pptx")
    for name, text in {
        "csv.csv": "nombre,cantidad\nalpha,3\nbeta,7\n",
        "json.json": '[{"nombre":"alpha","cantidad":3},{"nombre":"beta","cantidad":7}]',
        "invalid_json.json": '{"broken": [}',
        "html.html": "<h1>Botsky Lab31415</h1><p>Contenido sintetico</p>",
        "md.md": "# Botsky Lab31415\n\nContenido sintetico",
        "broken_srt.srt": "1\ninvalid time\nBotsky",
    }.items():
        (f / name).write_text(text)
    (f / "broken_audio.ogg").write_bytes(b"OggS" + b"broken" * 30)
    commands = [
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:duration=12",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=15:duration=12",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(f / "long_video.mp4"),
        ],
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=96x64:r=5:d=2",
            "-c:v",
            "libx264",
            str(f / "noaudio_video.mp4"),
        ],
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "2",
            str(f / "silence.wav"),
        ],
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "350",
            str(f / "large_audio.wav"),
        ],
    ]
    for command in commands:
        await asyncio.to_thread(
            subprocess.run, command, check=True, timeout=60, capture_output=True
        )
    mapping = {p.stem: str(p.resolve()) for p in f.iterdir() if p.is_file()}
    for name, path in paths.items():
        mapping[name] = str(path.resolve())
    for p in f.iterdir():
        if p.is_file():
            p.chmod(0o600)
    save(base / "fixtures.json", mapping)
    save(
        base / "fixture-ledger.json",
        {
            k: {
                "bytes": Path(v).stat().st_size,
                "sparse": k == "oversized",
                "sha256": None if k == "oversized" else lab.digest(Path(v)),
            }
            for k, v in mapping.items()
        },
    )


def safe_text(value):
    value = re.sub(r"[A-Za-z0-9_-]+@(?:s\.whatsapp\.net|lid)|[0-9-]+@g\.us", "[IDENTITY]", value)
    return re.sub(r"\b[a-f0-9]{32}\b", "[ID]", value)


def inspect_files(app, receipt_id, result):
    files = lab.artifacts(app, receipt_id)
    # Check ZIP containers/XML, TXT/JSON outputs as actual content, not extension-only.
    for identifier in result.data.get("artifacts", []):
        path = app.artifacts.path(identifier)
        with app.store.transaction() as db:
            row = db.execute("SELECT format FROM artifacts WHERE id=?", (identifier,)).fetchone()
        if not row:
            continue
        fmt = row[0]
        item = next((f for f in files if f["sha256"] == lab.digest(path)), None)
        if item is None:
            continue
        if fmt in {"docx", "xlsx", "pptx", "odt", "ods", "odp", "zip"}:
            with zipfile.ZipFile(path) as archive:
                bad = archive.testzip()
                if bad:
                    raise ValueError("output_zip_crc_failed")
                item["zip_entries"] = len(archive.namelist())
                if fmt in {"docx", "xlsx", "pptx"}:
                    from xml.etree import ElementTree

                    xml = [n for n in archive.namelist() if n.endswith(".xml")]
                    for name in xml:
                        ElementTree.fromstring(archive.read(name))
                    item["xml_documents_checked"] = len(xml)
        elif fmt in {"txt", "json", "csv", "md", "html", "srt"}:
            text = path.read_text(errors="strict")
            item["text_chars"] = len(text)
            item["content_excerpt"] = text[:600]
            if fmt == "json":
                json.loads(text)
    return files


def review_case(case, tool):
    if not isinstance(case, dict) or not re.fullmatch(r"c[0-9]{2}", str(case.get("id", ""))):
        raise ValueError("proposal_case_id")
    if not isinstance(case.get("command"), str) or len(case["command"]) > 64000:
        raise ValueError("proposal_command")
    if (
        case.get("fixture")
        and case["fixture"] not in FIXTURES
        and not re.fullmatch(r"output:c[0-9]{2}", case["fixture"])
    ):
        raise ValueError("proposal_fixture_unknown")
    if case.get("kind") not in {"positive", "negative", "blocked"}:
        raise ValueError("proposal_kind")
    statuses = case.get("statuses")
    if (
        not isinstance(statuses, list)
        or not statuses
        or set(statuses) - {"ok", "empty", "needs_input", "failed", "cancelled", "uncertain"}
    ):
        raise ValueError("proposal_statuses")
    command = re.sub(r"\{c[0-9]{2}\.[a-z_]+\}", "1", case["command"])
    try:
        parsed = Router().parse(command)
    except CommandError:
        return
    if (
        parsed
        and parsed.spec.family not in {tool, "core"}
        and not (tool == "control_call" and parsed.spec.family.startswith("audiovisual."))
    ):
        raise ValueError("proposal_other_tool")


async def execute_tool(batch, tool, base, *, resume=False):
    directory = batch / tool
    if (directory / "feedback.json").exists():
        return
    out = directory / "execution"
    original_out = out
    old_rows = []
    if resume and out.exists():
        old_rows = json.loads((out / "results.json").read_text())
        out = out / "recovery1"
    out.mkdir(mode=0o700)
    while not (directory / "proposal.json").exists():
        state = (
            json.loads((directory / "state.json").read_text())
            if (directory / "state.json").exists()
            else {}
        )
        if state.get("phase") == "error":
            save(
                directory / "feedback.json",
                {"blocked": "AGY did not produce a valid proposal", "session": state},
            )
            return
        await asyncio.sleep(2)
    proposal = json.loads((directory / "proposal.json").read_text())
    cases = proposal.get("cases", [])
    if not isinstance(cases, list) or not 1 <= len(cases) <= 40:
        save(directory / "feedback.json", {"runner_review": "invalid proposal case count"})
        return
    save(out / "frozen-proposal.json", proposal)
    root = original_out / "app"
    if not root.exists():
        shutil.copytree(base / "app", root)
    profile_path = root / "private/integrations.json"
    p = read_profile(profile_path)
    settings = Settings.load(root / "config.toml")
    settings = replace(
        settings, root=root, database=root / "lab.sqlite3", friends=frozenset({"lab-friend"})
    )
    target = next(iter(settings.allowed_groups))
    p["permissions"]["gallery"]["send"] = tool in {
        "manage_pack",
        "manage_cooperacha",
        "manage_happy_hour",
    }
    save(profile_path, p)
    fixture_paths = {
        k: Path(v) for k, v in json.loads((base / "fixtures.json").read_text()).items()
    }
    httpgate = ToolHTTP(out, p["evolution"]["base_url"], target, settings.owner)
    rows = [r for r in old_rows if r.get("result") and r["verdict"] != "REVIEW"]
    previous = {
        r["case"]: {"receipt": r.get("receipt"), "data": r["result"].get("data", {})} for r in rows
    }
    completed = {r["case"] for r in rows}
    published = sum(bool(r.get("physical_sample")) for r in rows)
    oauth_blocked = False
    async with httpx.AsyncClient(
        transport=httpgate, trust_env=False, timeout=30, follow_redirects=False
    ) as http:
        async with Integrations(settings, profile_path, http=http) as app:
            # Explicit synthetic balance fixture, no external credit or user data.
            from botsky.domains import economy

            ctx = CommandContext(
                "fixture",
                settings.instance,
                settings.account,
                Scope(settings.owner, target, True),
                settings.epoch,
                0,
            )
            with app.store.transaction() as db:
                wallet = economy.wallet(db, ctx)
                economy.move(db, wallet["id"], 5000, "lab-seed", "fixture", app.clock())
            if tool == "find_notes":
                setup = []
                adapter = LocalAdapter(settings)
                for index in range(12):
                    value = replace(
                        adapter.incoming(
                            f"seed-note-{index}",
                            settings.owner,
                            target,
                            f"/nota guardar proyecto botsky lab reunión {index} · EXACTO; /daily",
                            is_group=True,
                        ),
                        transport="evolution",
                    )
                    receipt = app.receive(value)
                    await deliver_async(app.store, receipt.id, settings, Captured(), app.clock)
                    setup.append(
                        {
                            "message_id": value.message_id,
                            "text": value.text,
                            "receipt": receipt.id,
                            "synthetic": True,
                        }
                    )
                save(out / "setup-notes.json", setup)
            if p["permissions"]["gallery"]["send"]:
                gallery = root / "private/gallery"
                with sqlite3.connect(gallery / "library.db") as db:
                    db.execute(
                        "INSERT OR IGNORE INTO albums VALUES('stress','LAB sintético','lab-sintetico',1)"
                    )
                    for _ in range(8):
                        identifier = str(uuid4())
                        name = f"originals/{identifier}.png"
                        shutil.copyfile(fixture_paths["image"], gallery / name)
                        db.execute(
                            "INSERT INTO photos VALUES(?,?,?,NULL,NULL)",
                            (identifier, "image/png", name),
                        )
                        db.execute("INSERT INTO album_photos VALUES('stress',?)", (identifier,))
            evolution = EvolutionTransport(app, p["evolution"], http)
            entry = LocalAdapter(settings)
            for n, original in enumerate(cases):
                if original["id"] in completed:
                    continue
                row = {
                    "case": original.get("id"),
                    "tool": tool,
                    "proposal": original,
                    "verdict": "REVIEW",
                }
                rows.append(row)
                started = time.monotonic()
                save(out / "results.json", rows)
                try:
                    review_case(original, tool)
                    case = dict(original)
                    command = lab.resolve_command(case["command"], previous)
                    row["command"] = command
                    if oauth_blocked and tool == "manage_drive" and case["kind"] == "positive":
                        raise lab.MissingCaseDependency("Drive OAuth invalid_grant")
                    private = tool in {"manage_messages", "manage_drive"} or bool(
                        case.get("private")
                    )
                    actor = (
                        settings.owner
                        if case.get("actor", "owner") == "owner"
                        else "lab-friend"
                        if case.get("actor") == "friend"
                        else "lab-outsider"
                    )
                    incoming = replace(
                        entry.incoming(
                            f"{tool}-{case['id']}",
                            actor,
                            settings.owner if private else target,
                            command,
                            is_group=not private,
                        ),
                        transport="evolution",
                    )
                    with app.store.transaction() as db:
                        prior = db.execute(
                            "SELECT * FROM inbox WHERE message_id=?", (incoming.message_id,)
                        ).fetchone()
                        prior_job = (
                            db.execute(
                                "SELECT state,provider_dispatched FROM jobs WHERE id=?",
                                (prior["id"],),
                            ).fetchone()
                            if prior
                            else None
                        )
                        if prior_job and prior_job["state"] == "running":
                            from botsky.jobs import cancel_job
                            from botsky.store import context_of

                            cancel_job(db, context_of(prior), prior["id"])
                    if prior_job and prior_job["state"] == "running":
                        row.update(
                            verdict="REVIEW",
                            evidence_level="interrupted_harness",
                            reason="In-flight case preserved and retired after process interruption; not repeated",
                            receipt=prior["id"],
                        )
                        continue
                    if prior:
                        incoming = replace(
                            incoming,
                            source_ms=prior["source_ms"],
                            attachments=tuple(json.loads(prior["attachments_json"])),
                            quoted_message_id=prior["quoted_message_id"],
                            mentioned_ids=tuple(json.loads(prior["mentions_json"])),
                        )
                    if not prior and (
                        case.get("fixture", "").startswith("output:")
                        if isinstance(case.get("fixture"), str)
                        else False
                    ):
                        parent = case["fixture"].split(":")[1]
                        ids = previous.get(parent, {}).get("data", {}).get("artifacts", [])
                        if not ids:
                            raise lab.MissingCaseDependency("artifact:" + parent)
                        incoming = replace(incoming, attachments=(ids[0],))
                    elif not prior and case.get("fixture"):
                        incoming = app.attach_local(incoming, fixture_paths[case["fixture"]])
                    parsed = None
                    try:
                        parsed = Router().parse(command)
                    except CommandError as exc:
                        row["syntax_error"] = exc.code
                    if parsed:
                        row.update(
                            route=parsed.spec.command,
                            operation=parsed.spec.operation,
                            explicit_fields=sorted(parsed.spans),
                        )
                    httpgate.case = case["id"]
                    # Small corrupt/oversized fixtures are never sent; samples selected by tester are capped.
                    live = bool(case.get("publish")) and published < 2
                    httpgate.live = live
                    async with ENGINE_LIMIT:
                        receipt = app.receive(incoming)
                        await asyncio.wait_for(app.jobs.run_pending(), 150)
                    with app.store.transaction() as db:
                        saved = db.execute(
                            "SELECT result_json FROM inbox WHERE id=?", (receipt.id,)
                        ).fetchone()
                    result = (
                        Result.from_json(saved[0])
                        if saved and saved[0]
                        else Result("empty", "silent")
                    )
                    files = inspect_files(app, receipt.id, result)
                    expected = {
                        **case,
                        "codes": case.get("codes") or [],
                        "artifact": case.get("artifact") or None,
                        "contains": case.get("contains") or None,
                    }
                    verdict, reason = lab.evaluate(expected, result, files)
                    # In discovery, failed expectations are suspicions until independent contrast.
                    row.update(
                        verdict="SUSPECTED" if verdict == "FAIL" else verdict,
                        reason=reason,
                        result=json.loads(result.to_json()),
                        artifacts=files,
                        receipt=receipt.id,
                        evidence_level="providers_real_delivery_fixture",
                        physical_sample=live,
                    )
                    previous[case["id"]] = {"receipt": receipt.id, "data": result.data}
                    if result.code == "oauth_refresh_rejected":
                        oauth_blocked = True
                    transport = (
                        lab.AnnotatedDelivery(
                            evolution, {"id": tool + "/" + case["id"], "command": command}
                        )
                        if live
                        else Captured()
                    )
                    row["accepted_parts"] = await deliver_async(
                        app.store, receipt.id, settings, transport, app.clock
                    )
                    if live:
                        published += 1
                    with app.store.transaction() as db:
                        states = [
                            r[0]
                            for r in db.execute(
                                "SELECT state FROM outbox WHERE receipt_id=?", (receipt.id,)
                            )
                        ]
                    row["delivery_states"] = states
                    if "uncertain" in states:
                        raise RuntimeError("uncertain_delivery_stop")
                    if case.get("duplicate"):
                        repeated = app.receive(incoming)
                        row["duplicate_preserved"] = repeated.duplicate
                except ArtifactProblem as exc:
                    row.update(
                        verdict="PASS" if original.get("kind") == "negative" else "SUSPECTED",
                        evidence_level="attachment_ingress",
                        result={"status": "failed", "code": exc.code},
                        reason="Operator attachment boundary rejected fixture before command handler",
                    )
                except lab.MissingCaseDependency as exc:
                    row.update(
                        verdict="BLOCKED", reason=str(exc), evidence_level="not_executed_dependency"
                    )
                except Exception as exc:
                    row.update(
                        verdict="REVIEW", runner_error=type(exc).__name__ + ": " + str(exc)[:180]
                    )
                    if isinstance(exc, RuntimeError) and "uncertain_delivery" in str(exc):
                        raise
                finally:
                    row["seconds"] = round(time.monotonic() - started, 3)
                    save(out / "results.json", rows)
                    print(
                        json.dumps(
                            {
                                "tool": tool,
                                "case": row["case"],
                                "verdict": row["verdict"],
                                "seconds": row["seconds"],
                            }
                        ),
                        flush=True,
                    )
            httpgate.live = True
            httpgate.case = "tool-summary"
            counts = dict(Counter(r["verdict"] for r in rows))
            await evolution.api.send(
                target,
                "text",
                text=f"🧪 Tanda de profundidad · {tool}\n{len(rows)} casos: {counts}.\n"
                "SUSPECTED es discrepancia por contrastar, no error confirmado. Batería guardada completa; "
                "entregas capturadas localmente salvo muestras etiquetadas. Producto sin modificar.",
            )
    # Retire effects in every tool-specific profile even though no service was installed.
    for block, key in [
        ("messages", "send"),
        ("delivery", "send"),
        ("gallery", "send"),
        ("drive", "write"),
    ]:
        p["permissions"][block][key] = False
    save(profile_path, p)
    feedback = {"tool": tool, "counts": dict(Counter(r["verdict"] for r in rows)), "rows": []}
    for row in rows:
        exposed_result = row.get("result", {})
        if tool == "manage_minecraft":
            exposed_result = {
                "status": exposed_result.get("status"),
                "code": exposed_result.get("code"),
                "text": "Raw server details retained privately; read-only query evidence only.",
            }
        feedback["rows"].append(
            {
                "case": row["case"],
                "command": safe_text(row.get("command", "")),
                "verdict": row["verdict"],
                "expected": row["proposal"].get("expected"),
                "reason": row.get("reason"),
                "result": safe_text(json.dumps(exposed_result, ensure_ascii=False))[:1700],
                "artifacts": row.get("artifacts", []),
                "evidence_level": row.get("evidence_level"),
                "runner_error": row.get("runner_error"),
            }
        )
    save(directory / "feedback.json", feedback)
    save(
        out / "summary.json",
        {
            "counts": feedback["counts"],
            "cases": len(rows),
            "physical_samples": published,
            "product_modified": False,
            "effects_disabled": True,
        },
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--batch", type=int, choices=(1, 2, 3))
    parser.add_argument("--tool", choices=tuple(t for batch in BATCHES for t in batch))
    parser.add_argument("--resume-interrupted", action="store_true")
    args = parser.parse_args()
    args.directory = args.directory.resolve()
    if args.action == "prepare":
        await prepare(args.directory / "base")
    else:
        if not args.batch:
            parser.error("--batch requerido")
        if args.tool:
            await execute_tool(
                args.directory / f"batch{args.batch}",
                args.tool,
                args.directory / "base",
                resume=args.resume_interrupted,
            )
        else:
            # Separate OS processes contain event-loop hangs and cancellation failures.
            capacity = asyncio.Semaphore(2)
            save(
                args.directory / f"batch{args.batch}-quota.json", await asyncio.to_thread(lab.quota)
            )

            async def worker(tool):
                directory = args.directory / f"batch{args.batch}" / tool
                if (directory / "feedback.json").exists():
                    return
                async with capacity:
                    command = [
                        __import__("sys").executable,
                        str(Path(__file__).resolve()),
                        "execute",
                        "--directory",
                        str(args.directory),
                        "--batch",
                        str(args.batch),
                        "--tool",
                        tool,
                    ]
                    if args.resume_interrupted:
                        command.append("--resume-interrupted")
                    with (directory / "backend-worker.log").open("wb") as log:
                        proc = await asyncio.create_subprocess_exec(
                            *command, stdout=log, stderr=log
                        )
                        started = time.monotonic()
                        while proc.returncode is None:
                            await asyncio.sleep(5)
                            result_files = list((directory / "execution").glob("**/results.json"))
                            last_progress = max(
                                (p.stat().st_mtime for p in result_files), default=time.time()
                            )
                            if (
                                time.time() - last_progress > 210
                                or time.monotonic() - started > 900
                            ):
                                proc.terminate()
                                try:
                                    await asyncio.wait_for(proc.wait(), 5)
                                except TimeoutError:
                                    proc.kill()
                                    await proc.wait()
                                break
                    if not (directory / "feedback.json").exists():
                        save(
                            directory / "feedback.json",
                            {
                                "tool": tool,
                                "runner_error": "isolated worker stopped",
                                "exit": proc.returncode,
                                "evidence": "backend-worker.log; partial results preserved",
                            },
                        )
                    profile = directory / "execution/app/private/integrations.json"
                    if profile.exists():
                        value = read_profile(profile)
                        for block, key in [
                            ("messages", "send"),
                            ("delivery", "send"),
                            ("gallery", "send"),
                            ("drive", "write"),
                        ]:
                            value["permissions"][block][key] = False
                        save(profile, value)
                    print(json.dumps({"tool": tool, "worker_exit": proc.returncode}), flush=True)

            await asyncio.gather(*(worker(tool) for tool in BATCHES[args.batch - 1]))


if __name__ == "__main__":
    os.umask(0o077)
    asyncio.run(main())
