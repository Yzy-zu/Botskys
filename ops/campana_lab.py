#!/usr/bin/env python3
"""Campaña R10 explícita: simulación de operador -> backend -> WhatsApp Lab.

Nunca instala el runtime ni cambia webhooks. Un directorio por campaña; reanudar
requiere revisar el ledger, no repetir POST inciertos. Evidencia privada por defecto.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import httpx

from botsky.adapters.evolution import EvolutionTransport
from botsky.adapters.local import LocalAdapter, clock_ms
from botsky.commands.registry import Registry
from botsky.commands.router import CommandError, Router
from botsky.config import Settings
from botsky.contracts import Result
from botsky.delivery import deliver_async
from botsky.integrations import Integrations, read_profile

ROOT = Path(__file__).resolve().parents[1]


class MissingCaseDependency(Exception):
    pass


def resolve_command(command, previous):
    def substitute(match):
        reference, key = match.group(1).split(".", 1)
        try:
            data = previous[reference]
            return str(data["receipt"] if key == "receipt" else data["data"][key])
        except KeyError:
            raise MissingCaseDependency(reference + "." + key) from None

    return re.sub(r"\{([a-z0-9_-]+\.[a-z_]+)\}", substitute, command)


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quota():
    result = subprocess.run(
        ["python3", "/home/petrov/zhana/ops/consultar_uso_codex.py"],
        capture_output=True,
        check=True,
        timeout=20,
    )
    value = json.loads(result.stdout)
    remaining = [
        window["remaining_percent"]
        for bucket in value["buckets"]
        for name in ("primary", "secondary")
        if (window := bucket.get(name))
    ]
    if not remaining or min(remaining) <= 5:
        raise RuntimeError("quota_stop_5_percent")
    return value


class LabHTTP(httpx.AsyncBaseTransport):
    """Solo el adaptador de laboratorio redirige las salidas privadas al Lab.

    El transporte de producto valida el ámbito/artefacto original sin cambios.
    Se modifica exclusivamente number en la frontera de pruebas, antes de la red.
    Ledger persistido antes del POST y sin reintento automático.
    """

    def __init__(self, directory, base_url, target, sources, *, limit=175):
        self.inner = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        self.directory, self.origin = directory, httpx.URL(base_url)
        self.target, self.sources, self.limit = target, set(sources), limit
        self.posts, self.case = [], "setup"
        self.path = directory / "remote-deliveries.json"
        if self.path.exists():
            raise ValueError("campaign_delivery_ledger_exists_no_automatic_resume")

    async def handle_async_request(self, request):
        if request.url.copy_with(path="/", query=None) == self.origin.copy_with(
            path="/", query=None
        ):
            if request.method != "GET":
                endpoint = request.url.path.split("/")
                if (
                    len(endpoint) != 4
                    or endpoint[1] != "message"
                    or endpoint[2]
                    not in {"sendText", "sendMedia", "sendSticker", "sendWhatsAppAudio"}
                ):
                    raise ValueError("lab_remote_mutation_denied")
                if len(self.posts) >= self.limit:
                    raise ValueError("lab_delivery_budget_exhausted")
                raw = bytearray()
                async for block in request.stream:
                    raw.extend(block)
                    if len(raw) > 24 * 1024 * 1024:
                        raise ValueError("lab_delivery_size_limit")
                body = json.loads(raw)
                if body.get("number") not in self.sources:
                    raise ValueError("lab_unapproved_original_destination")
                redirected = body["number"] != self.target
                body["number"] = self.target
                item = {
                    "case": self.case,
                    "endpoint": endpoint[2],
                    "state": "uncertain",
                    "redirected_private_output": redirected,
                    "at_ms": clock_ms(),
                    "body_sha256": hashlib.sha256(raw).hexdigest(),
                }
                self.posts.append(item)
                save(self.path, self.posts)
                headers = dict(request.headers)
                headers.pop("content-length", None)
                headers.pop("transfer-encoding", None)
                request = httpx.Request(
                    request.method,
                    request.url,
                    json=body,
                    headers=headers,
                    extensions=request.extensions,
                )
                await asyncio.sleep(0.75)
                response = await self.inner.handle_async_request(request)
                item["http_status"] = response.status_code
                # The product transport still checks the actual ACK/message ID.
                item["state"] = "http_response"
                save(self.path, self.posts)
                return response
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


class AnnotatedDelivery:
    def __init__(self, base, case):
        self.base, self.case, self.annotated = base, case, False

    async def send(self, part):
        if part.text and not self.annotated:
            prefix = (
                f"[Botsky Lab · {self.case['id']}]\nEntrada simulada: {self.case['command']}\n\n"
            )
            part = replace(part, text=prefix + part.text)
            self.annotated = True
        return await self.base.send(part)


def prepare(directory, *, synthetic_gallery=False, message_budget=175):
    root = directory / "app"
    root.mkdir(mode=0o700, exist_ok=False)
    (root / "private").mkdir(mode=0o700)
    source = Settings.load(ROOT / "private/config.integrations.toml")
    profile = read_profile(ROOT / "private/integrations.json")
    groups = json.loads((directory / "group-preflight.json").read_text())
    found = [
        v for v in groups if v["subject"] == "Botsky Lab" and v["target"] in source.allowed_groups
    ]
    if len(found) != 1:
        raise ValueError("verified_lab_target_required")
    target = found[0]["target"]
    config = {
        "instance": "botsky-lab-20261106",
        "account": source.account,
        "epoch": 1,
        "database": "lab.sqlite3",
        "activation_at": "2026-11-06T00:00:00Z",
        "owner": source.owner,
        "friends": [],
        "allowed_groups": [target],
        "timezone": source.timezone,
        "transport": "evolution",
        "bot_ids": sorted(source.bot_ids),
    }
    toml = "\n".join(k + " = " + json.dumps(v) for k, v in config.items()) + "\n"
    path = root / "config.toml"
    path.write_text(toml)
    path.chmod(0o600)
    profile.pop("mutations_enabled", None)
    profile.pop("runtime", None)
    profile["call_service"] = {"enabled": False}
    profile["contacts"] = [{"name": "Botsky Lab", "jid": target, "aliases": ["Lab"]}]
    profile["permissions"] = {
        "version": 1,
        "messages": {"send": True, "targets": [target]},
        "drive": {"read": True, "write": True},
        "groups": {"read": True, "write": False, "chats": [target]},
        "minecraft": {"read": True, "write": False},
        "gallery": {"enabled": True, "send": synthetic_gallery, "chats": [target, source.owner]},
        "roulette": {"chats": [], "allow_admins": False},
        "nuclear": {"enabled": False, "chats": []},
        "delivery": {"send": True, "chats": [target, source.owner]},
    }
    save(root / "private/integrations.json", profile)
    oauth = root / "private/drive"
    oauth.mkdir(mode=0o700)
    for name in ("client.json", "token.json", "folder.json"):
        shutil.copyfile(ROOT / "private/drive" / name, oauth / name)
        (oauth / name).chmod(0o600)
    gallery = source.root / "private/gallery"
    shutil.copytree(gallery, root / "private/gallery")
    save(
        directory / "campaign-scope.json",
        {
            "target": target,
            "owner": source.owner,
            "simulated_ingress": True,
            "production_transition": False,
            "max_delivery_posts": message_budget,
            "synthetic_gallery": synthetic_gallery,
            "allowed_remote_effects": [
                "WhatsApp outputs to verified Lab",
                "own Drive synthetic fixtures",
            ],
            "forbidden": [
                "group changes",
                "server changes",
                "calls",
                "browser",
                "production webhook",
            ],
            "quota": quota(),
        },
    )
    return root


async def fixtures(directory, app):
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfgen.canvas import Canvas

    directory.mkdir(mode=0o700)
    image = Image.new("RGB", (1200, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 48)
    draw.text((70, 100), "BOTSKY LAB 31415", fill="black", font=font)
    draw.text((70, 200), "Archivo sintetico de prueba", fill="black", font=font)
    image.save(directory / "image.png")
    subprocess.run(
        ["qrencode", "-o", str(directory / "qr.png"), "-s", "12", "BOTSKY-LAB-27182"], check=True
    )
    c = Canvas(str(directory / "pdf.pdf"))
    c.drawString(72, 720, "BOTSKY LAB 31415 - documento sintetico")
    c.showPage()
    c.drawString(72, 720, "Segunda pagina - 27182")
    c.save()
    (directory / "txt.txt").write_text("Botsky Lab 31415\nContenido sintetico.\n")
    (directory / "srt.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nBotsky Lab 31415\n")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=15:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(directory / "video.mp4"),
        ],
        check=True,
        timeout=30,
    )
    voice = await app.tts.synthesize(
        "Botsky Lab. El código de prueba es tres uno cuatro uno cinco.",
        "mexicana",
        "none",
        directory / "tts-input",
    )
    shutil.copyfile(voice, directory / "audio.ogg")
    for path in directory.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    return {
        "image": directory / "image.png",
        "qr": directory / "qr.png",
        "pdf": directory / "pdf.pdf",
        "txt": directory / "txt.txt",
        "srt": directory / "srt.srt",
        "video": directory / "video.mp4",
        "audio": directory / "audio.ogg",
    }


def artifacts(app, identifier):
    from PIL import Image
    from pypdf import PdfReader

    with app.store.transaction() as db:
        rows = db.execute(
            "SELECT * FROM artifacts WHERE receipt_id=? AND origin='result'", (identifier,)
        ).fetchall()
    result = []
    for row in rows:
        path = app.artifacts.path(row["id"])
        item = {"format": row["format"], "bytes": path.stat().st_size, "sha256": digest(path)}
        if item["sha256"] != row["sha256"] or item["bytes"] != row["size"]:
            raise ValueError("artifact_integrity")
        if row["format"] in ("png", "jpg", "webp"):
            with Image.open(path) as image:
                item["image_size"] = list(image.size)
                image.verify()
        elif row["format"] == "pdf":
            pdf = PdfReader(path)
            item["pages"] = len(pdf.pages)
            item["extracted_text"] = "\n".join(p.extract_text() or "" for p in pdf.pages)[:1000]
        elif row["format"] in ("mp3", "mp4", "webm", "ogg", "wav", "flac"):
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=codec_type,codec_name",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                check=True,
                timeout=15,
            )
            item["ffprobe"] = json.loads(probe.stdout)
        result.append(item)
    return result


def evaluate(case, result, files):
    if case.get("kind") == "blocked":
        if result.status not in {"failed", "needs_input", "empty"} or result.code not in {
            "operation_not_enabled",
            "call_not_configured",
            "calls_not_configured",
            "coop_not_configured",
            "packs_not_configured",
        }:
            return "FAIL", "Expected guard did not deny the capability"
        return "BLOCKED", "Capability deliberately not activated; guard result recorded"
    if result.code in {"operation_not_enabled", "call_not_configured", "calls_not_configured"}:
        return "BLOCKED", result.code
    if result.status not in case.get("statuses", ["ok", "empty"]):
        return "FAIL", "Unexpected result status: " + result.status
    if case.get("codes") and result.code not in case["codes"]:
        return "FAIL", "Unexpected result code: " + result.code
    if case.get("contains") and case["contains"].casefold() not in result.text.casefold():
        return "FAIL", "Expected text absent"
    if case.get("artifact") and not any(a["format"] == case["artifact"] for a in files):
        return "FAIL", "Expected verified artifact absent"
    for key, expected in case.get("data", {}).items():
        if result.data.get(key) != expected:
            return "FAIL", "Unexpected data: " + key
    return "PASS", "Frozen oracle and artifact checks passed"


async def run(
    directory, *, start=False, synthetic_gallery=False, message_budget=175, existing_lab=None
):
    if not start:
        raise ValueError("campaign_no_automatic_resume")
    if existing_lab is not None:
        import sqlite3

        existing_lab = existing_lab.resolve(strict=True)
        if not existing_lab.is_relative_to(ROOT / "private"):
            raise ValueError("own_lab_only")
        scope = json.loads((existing_lab / "campaign-scope.json").read_text())
        if scope.get("production_transition") is not False or not scope.get("simulated_ingress"):
            raise ValueError("own_lab_marker_required")
        root = existing_lab / "app"
        old_settings = Settings.load(root / "config.toml")
        if set(old_settings.allowed_groups) != {scope["target"]}:
            raise ValueError("own_lab_target_changed")
        with (
            sqlite3.connect(old_settings.database) as source,
            sqlite3.connect(directory / "before.sqlite3") as target,
        ):
            source.backup(target)
        shutil.copyfile(root / "private/integrations.json", directory / "profile-before.json")
        profile = read_profile(root / "private/integrations.json")
        profile["permissions"]["gallery"]["send"] = synthetic_gallery
        save(root / "private/integrations.json", profile)
        save(
            directory / "campaign-scope.json",
            {
                **scope,
                "followup_of": str(existing_lab),
                "max_delivery_posts": message_budget,
                "synthetic_gallery": synthetic_gallery,
            },
        )
    else:
        root = prepare(
            directory, synthetic_gallery=synthetic_gallery, message_budget=message_budget
        )
    cases_path = directory / "cases.json"
    cases = json.loads(cases_path.read_text())
    frozen_sha = digest(cases_path)
    settings = Settings.load(root / "config.toml")
    profile_path = root / "private/integrations.json"
    profile = read_profile(profile_path)
    target = next(iter(settings.allowed_groups))
    transport = LabHTTP(
        directory,
        profile["evolution"]["base_url"],
        target,
        [target, settings.owner],
        limit=message_budget,
    )
    observations, previous = [], {}
    async with httpx.AsyncClient(
        transport=transport, trust_env=False, timeout=30, follow_redirects=False
    ) as http:
        providers = Integrations(settings, profile_path, http=http)
        async with providers as app:
            evolution = EvolutionTransport(app, profile["evolution"], http)
            entry = LocalAdapter(settings)
            await evolution.api.send(
                target,
                "text",
                text=(
                    "🧪 Botsky Lab: empieza campaña automática R10. Cuatro sesiones AGY proponen casos; "
                    "el backend determinista de Botsky los ejecuta con datos sintéticos y DB separada. "
                    "Entrada SIMULADA del dueño, no mensajes recibidos desde su teléfono. "
                    "Las respuestas y archivos siguientes son reales. Sin cambios de grupo/servidor, "
                    "llamadas ni transición. PASS de transporte significa ACK del proveedor, no recepción humana."
                ),
            )
            fixture_paths = await fixtures(directory / "fixtures", app)
            if synthetic_gallery:
                import sqlite3
                from uuid import uuid4

                gallery = root / "private/gallery"
                with sqlite3.connect(gallery / "library.db") as db:
                    db.execute(
                        "INSERT INTO albums VALUES('lab-synthetic','LAB: imágenes sintéticas','lab-sintetico',1)"
                    )
                    for _ in range(6):
                        identifier = str(uuid4())
                        name = f"originals/{identifier}.png"
                        shutil.copyfile(fixture_paths["image"], gallery / name)
                        (gallery / name).chmod(0o600)
                        db.execute(
                            "INSERT INTO photos VALUES(?,?,?,NULL,NULL)",
                            (identifier, "image/png", name),
                        )
                        db.execute(
                            "INSERT INTO album_photos VALUES('lab-synthetic',?)", (identifier,)
                        )
            save(
                directory / "fixture-ledger.json",
                {
                    k: {"bytes": p.stat().st_size, "sha256": digest(p)}
                    for k, p in fixture_paths.items()
                },
            )
            for n, frozen_case in enumerate(cases):
                if n % 8 == 0:
                    save(directory / "quota.json", quota())
                if digest(cases_path) != frozen_sha:
                    raise ValueError("campaign_changed_after_freeze")
                case = dict(frozen_case)
                transport.case = case["id"]
                started = time.monotonic()
                row = {
                    "id": case["id"],
                    "family": case["tool"],
                    "kind": case.get("kind", "positive"),
                    "frozen_case_sha256": frozen_sha,
                    "at_ms": clock_ms(),
                }
                observations.append(row)
                save(directory / "results.json", observations)
                try:
                    case["command"] = resolve_command(case["command"], previous)
                    try:
                        parsed = Router().parse(case["command"])
                    except CommandError:
                        if case.get("kind") != "negative":
                            raise
                        parsed = None
                    if parsed and parsed.spec.family != case["tool"] and case["tool"] != "core":
                        raise ValueError("case_family_mismatch")
                    row.update(
                        command=case["command"],
                        operation=parsed.spec.operation if parsed else None,
                        fields=sorted(parsed.arguments) if parsed else [],
                    )
                    chat = settings.owner if case.get("private") else target
                    incoming = replace(
                        entry.incoming(
                            case["id"],
                            settings.owner,
                            chat,
                            case["command"],
                            is_group=not case.get("private", False),
                        ),
                        transport="evolution",
                    )
                    if case.get("fixture"):
                        incoming = app.attach_local(incoming, fixture_paths[case["fixture"]])
                    if case.get("quote"):
                        incoming = replace(incoming, quoted_message_id=case["quote"])
                    receipt = app.receive(incoming)
                    with app.store.transaction() as db:
                        queued = db.execute(
                            "SELECT 1 FROM jobs WHERE id=? AND state='queued'", (receipt.id,)
                        ).fetchone()
                    if queued:
                        await asyncio.wait_for(app.jobs.run_pending(), 180)
                    with app.store.transaction() as db:
                        saved = db.execute(
                            "SELECT result_json FROM inbox WHERE id=?", (receipt.id,)
                        ).fetchone()
                    result = (
                        Result.from_json(saved[0])
                        if saved and saved[0]
                        else Result("failed", "runner_no_result")
                    )
                    verified = artifacts(app, receipt.id)
                    status, reason = evaluate(case, result, verified)
                    row.update(
                        receipt=receipt.id,
                        result=json.loads(result.to_json()),
                        artifacts=verified,
                        verdict=status,
                        reason=reason,
                    )
                    previous[case["id"]] = {"receipt": receipt.id, "data": result.data}
                    row["accepted_parts"] = await deliver_async(
                        app.store,
                        receipt.id,
                        settings,
                        AnnotatedDelivery(evolution, case),
                        app.clock,
                    )
                    if case.get("duplicate"):
                        duplicate = app.receive(incoming)
                        repeated = await deliver_async(
                            app.store, receipt.id, settings, evolution, app.clock
                        )
                        row["duplicate"] = duplicate.duplicate and repeated == 0
                        if not row["duplicate"]:
                            row.update(
                                verdict="FAIL", reason="Duplicate executed or delivered again"
                            )
                    with app.store.transaction() as db:
                        states = [
                            r[0]
                            for r in db.execute(
                                "SELECT state FROM outbox WHERE receipt_id=?", (receipt.id,)
                            )
                        ]
                    row["delivery_states"] = states
                    if "uncertain" in states or "failed" in states:
                        row.update(
                            verdict="FAIL", reason="Product output delivery not accepted; no retry"
                        )
                        if "uncertain" in states:
                            raise RuntimeError("campaign_stopped_uncertain_delivery")
                except MissingCaseDependency as exc:
                    row.update(
                        verdict="BLOCKED",
                        reason="Prerequisite did not produce " + str(exc),
                        dependency_error=True,
                    )
                except Exception as exc:
                    row.update(
                        verdict="FAIL", runner_error=type(exc).__name__, error_code=str(exc)[:160]
                    )
                    if isinstance(exc, RuntimeError) and "campaign_stopped" in str(exc):
                        raise
                finally:
                    row["duration_seconds"] = round(time.monotonic() - started, 3)
                    save(directory / "results.json", observations)
                    print(
                        json.dumps(
                            {
                                k: row.get(k)
                                for k in (
                                    "id",
                                    "family",
                                    "verdict",
                                    "reason",
                                    "duration_seconds",
                                    "error_code",
                                )
                            }
                        ),
                        flush=True,
                    )
            summary = summarize(observations)
            save(directory / "summary.json", summary)
            transport.case = "summary"
            await evolution.api.send(
                target,
                "text",
                text=(
                    "🧪 Campaña automática terminada. " + json.dumps(summary["counts"]) + "\n"
                    "Los bloqueos no son éxitos de herramienta. El informe separa errores del producto, "
                    "del runner, guardias y fronteras pendientes. No se ha hecho transición."
                ),
            )


def summarize(rows):
    from collections import Counter

    registry = Registry()
    operations = {r.get("operation") for r in rows}
    families = sorted({s.family for s in registry.specs if s.family != "core"})
    return {
        "counts": dict(Counter(r["verdict"] for r in rows)),
        "cases": len(rows),
        "families": {
            f: {
                "cases": len([r for r in rows if r["family"] == f]),
                "positive_pass": sum(
                    r["verdict"] == "PASS" and r["kind"] == "positive"
                    for r in rows
                    if r["family"] == f
                ),
            }
            for f in families
        },
        "unobserved_operations": sorted(
            s.operation for s in registry.specs if s.operation not in operations
        ),
        "limits": [
            "simulated owner admission, not phone ingress",
            "provider ACK, not Android/human receipt",
            "no real calls or group/server mutation",
            "synthetic artifacts only",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--start-authorized-campaign", action="store_true")
    parser.add_argument("--synthetic-gallery", action="store_true")
    parser.add_argument("--message-budget", type=int, default=175)
    parser.add_argument(
        "--existing-lab", type=Path, help="continuación revisada explícita; conserva DB y recibos"
    )
    args = parser.parse_args()
    os.umask(0o077)
    if not 1 <= args.message_budget <= 175:
        parser.error("message-budget: 1–175")
    asyncio.run(
        run(
            args.directory.resolve(),
            start=args.start_authorized_campaign,
            synthetic_gallery=args.synthetic_gallery,
            message_budget=args.message_budget,
            existing_lab=args.existing_lab,
        )
    )


if __name__ == "__main__":
    main()
