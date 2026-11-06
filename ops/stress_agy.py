#!/usr/bin/env python3
"""Tres tandas de diez testers AGY, un dominio por proceso y conversación.

Propuestas y feedback por archivos privados. Las sesiones no acceden al ejecutor:
el orquestador entrega cada caso revisado al harness y devuelve evidencia saneada.
"""

import argparse
import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from agy_lab import POLICY, sandbox, save
from campana_lab import quota

MODEL = "gemini-3.8-flash-medium"
BATCHES = (
    (
        "download_media",
        "convert_document",
        "edit_media",
        "manage_pdf",
        "make_sticker",
        "read_image",
        "transcribe_media",
        "make_voice",
        "conversation",
        "search_web",
    ),
    (
        "manage_conversation",
        "save_note",
        "find_notes",
        "manage_memory",
        "manage_reminder",
        "manage_school",
        "manage_poll",
        "manage_drive",
        "manage_messages",
        "send_sticker",
    ),
    (
        "manage_pack",
        "manage_cooperacha",
        "manage_happy_hour",
        "manage_economy",
        "manage_blackjack",
        "manage_roulette",
        "manage_admin",
        "manage_minecraft",
        "make_prank",
        "control_call",
    ),
)
FIXTURES = (
    "image",
    "jpg",
    "webp",
    "qr",
    "blank_image",
    "wide_image",
    "large_image",
    "animated_webp",
    "broken_png",
    "pdf",
    "scan_pdf",
    "encrypted_pdf",
    "broken_pdf",
    "many_pages_pdf",
    "txt",
    "large_txt",
    "oversized",
    "empty",
    "docx",
    "xlsx",
    "multisheet_xlsx",
    "csv",
    "json",
    "invalid_json",
    "html",
    "md",
    "pptx",
    "video",
    "long_video",
    "noaudio_video",
    "audio",
    "silence",
    "large_audio",
    "broken_audio",
    "srt",
    "broken_srt",
)


def prompt(tool):
    from dataclasses import asdict

    from botsky.commands.registry import Registry

    specs = [
        s
        for s in Registry().specs
        if s.family == tool or (tool == "control_call" and s.family.startswith("audiovisual."))
    ]
    return {
        "role": "Tester independiente de una sola herramienta de Botsky: " + tool,
        "mission": "Detectar lo que funciona y errores sospechados, sin modificar el producto. "
        "Backend real ejecutará tus casos y recibirás evidencia para redactar tu informe.",
        "output": {
            "cases": [
                {
                    "id": "c01",
                    "command": "/comando explícito",
                    "fixture": None,
                    "kind": "positive|negative|blocked",
                    "statuses": ["ok"],
                    "codes": [],
                    "artifact": None,
                    "contains": None,
                    "purpose": "Qué compruebas y por qué",
                    "expected": "Criterio verificable previo a ejecutar",
                    "publish": False,
                }
            ]
        },
        "rules": [
            "Propón entre20 y32casos variados, máximo40. Incluye TODAS las acciones de tu catálogo, "
            "argumentos opcionales/no válidos, límites, duplicados, corruptos, tamaños, faltantes y cadenas.",
            "Solo comandos del dominio asignado; /ayuda, /estado, /cancelar y /confirmar son auxiliares. "
            "No shell, herramientas nativas, archivos/rutas, web, MCP, NLP ni decisiones sobre comandos en prosa.",
            "Cada caso id c01..c40. IDs reales se enlazan {c01.task_id}, {c01.view_id}, {c01.receipt}, "
            "etc. Usa data del resultado, nunca inventes IDs para un recorrido positivo.",
            "fixture admite nombres de fixtures o output:c01 para usar un archivo producido antes; "
            "null indica sin archivo. Todas las entradas son sintéticas del operador. No rutas.",
            "statuses es la lista ESPERADA, no aceptes todos los estados. ok/empty/needs_input/failed/"
            "cancelled/uncertain. kind positive implica tarea resuelta o vista previa válida; negative "
            "comprueba un rechazo específico. Un comando inválido no prueba la función de negocio.",
            "artifact opcional enum pdf/docx/xlsx/txt/png/jpg/webp/zip/mp3/mp4/webm/ogg. "
            "contains opcional substring verificable. codes opcional lista de códigos esperados; "
            "si desconoces el código usa lista vacía, no lo inventes. Puedes añadir pages y seconds.",
            "Máximo2casos publish=true para muestras naturales en Botsky Lab; resto evidencia local "
            "con proveedores reales donde corresponda. Todas las salidas finales serán informadas.",
            "Texto de imagen/PDF: BOTSKY LAB 31415 y segunda página27182. QR: BOTSKY-LAB-27182. "
            "DOCX/TXT: Botsky Lab31415; hoja tabular con columnas nombre,cantidad y valores alpha,3 beta,7.",
            "No asumas PDF->Word->Excel compatible: registra qué transformaciones se admiten; "
            "unsupported_conversion puede ser rechazo correcto. Prueba rutas y cadena en vez de fingir éxito.",
            "Publicaciones adultas optativas NO se activan. Descargas: fuentes existentes y enlaces "
            "públicos cortos conocidos; usa recortes <=5s y calidades variadas. Presupuesto de red/plazo "
            "lo fija backend. Fuente W3C https://media.w3.org/2010/05/bunny/trailer.mp4, "
            "YouTube https://www.youtube.com/watch?v=aqz-KE-bpKQ y https://youtu.be/YE7VzlLtp-4. "
            "Otros enlaces propuestos se anotarán como no verificados hasta ejecutar el proveedor.",
            "Fechas futuras2026-12-01. Contacto único Lab. Datos de XP/fotos sintéticos en DB independiente. "
            "No mensajes a terceros; grupo/servidor no mutables. Drive tiene invalid_grant conocido: "
            "comprueba límites y registra bloqueo de funcionalidad; no inventes OAuth.",
            "Llamadas/Live/avatar/clip/agenda no tienen sesión propia: controles remotos BLOCKED. "
            "No navegador, llamada, vinculación ni tocar servicios activos. Ruleta consecuencias remotas "
            "bloqueadas; no suplantar participantes. Admin consultas/XP locales sí, cambios grupo no.",
            "No declares PASS: proponer expectativa no acredita ejecución. Al final emitirás informe "
            "con evidence IDs, reproducibilidad y nivel local/proveedor/transporte. No corregir producto.",
        ],
        "fixtures": FIXTURES,
        "catalog": [
            {
                "operation": s.operation,
                "usage": s.usage,
                "example": s.sample,
                "fields": [asdict(f) for f in s.fields],
            }
            for s in specs
        ],
    }


def decode(response):
    # Preserve contradictory or malformed output as a session error; never silently pick a winner.
    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(response)
    if not isinstance(value, dict):
        raise ValueError("agy_json_object_required")
    return value


class Session:
    def __init__(self, directory, resume_id=None):
        self.directory, self.process, self.stderr_task = directory, None, None
        self.turns, self.conversations = 0, set()
        self.resume_id = resume_id

    async def start(self):
        command = sandbox(self.directory / "sandbox") + [
            "--agent",
            "botsky-lab",
            "--model",
            MODEL,
            "--mode",
            "plan",
            "--disable-slash-commands",
            "--settings",
            json.dumps(POLICY),
            "--log-file",
            "/tmp/agy.log",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--print-timeout",
            "0s",
        ]
        if self.resume_id:
            command += ["--conversation", self.resume_id]
        self.process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=2 * 1024 * 1024,
        )
        self.stderr_task = asyncio.create_task(self._stderr())

    async def _stderr(self):
        with (self.directory / "stderr.txt").open("wb") as out:
            while block := await self.process.stderr.read(8192):
                out.write(block)

    async def turn(self, payload):
        self.turns += 1
        save(self.directory / f"turn{self.turns}-request.json", payload)
        encoded = (
            json.dumps(
                {"event": "user", "message": {"content": json.dumps(payload, ensure_ascii=False)}}
            ).encode()
            + b"\n"
        )
        self.process.stdin.write(encoded)
        await self.process.stdin.drain()
        with (self.directory / f"turn{self.turns}-events.jsonl").open("wb") as out:
            async with asyncio.timeout(600):
                while line := await self.process.stdout.readline():
                    out.write(line)
                    out.flush()
                    event = json.loads(line)
                    if event.get("event") == "init" and event["init"].get("model") != MODEL:
                        raise ValueError("agy_model_mismatch")
                    update = event.get("step_update", {})
                    if update.get("step_type") == "tool":
                        raise ValueError("unexpected_native_tool_attempt")
                    if event.get("event") == "result":
                        result = event["result"]
                        self.conversations.add(result.get("conversation_id"))
                        if result.get("status") != "SUCCESS":
                            raise ValueError("agy_turn_not_success")
                        return decode(result["response"])
        raise RuntimeError("agy_eof_before_result")

    async def close(self):
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 8)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
            await self.stderr_task
        shutil.rmtree(self.directory / "sandbox/profile", ignore_errors=True)


async def tester(directory, tool):
    directory.mkdir(mode=0o700)
    session = Session(directory)
    started = time.time()
    state = {"tool": tool, "model": MODEL, "phase": "starting", "started_at": started}
    try:
        await session.start()
        state["phase"] = "proposing"
        save(directory / "state.json", state)
        proposal = await session.turn(prompt(tool))
        save(directory / "proposal.json", proposal)
        state.update(phase="waiting_for_execution", proposed_cases=len(proposal.get("cases", [])))
        save(directory / "state.json", state)
        print(
            json.dumps({"tool": tool, "phase": state["phase"], "cases": state["proposed_cases"]}),
            flush=True,
        )
        while not (directory / "feedback.json").exists():
            await asyncio.sleep(2)
            if (directory.parent / "STOP").exists():
                raise RuntimeError("campaign_explicit_stop")
        feedback = json.loads((directory / "feedback.json").read_text())
        state["phase"] = "reporting"
        save(directory / "state.json", state)
        report = await session.turn(
            {
                "task": "Redacta informe final de tu herramienta usando solo evidencia adjunta. "
                "No corrijas código. Se contrastará con otro agente después. Distingue errores sospechados, "
                "errores de expectativa/runner, bloqueos y casos que funcionaron. Cita IDs concretos. "
                "Devuelve JSON {tool,works:[{claim,cases}],suspected_errors:[{title,cases,reproduce,expected,"
                "observed,confidence,level}],oracle_issues:[],blocked:[],coverage_gaps:[],recommendations:[]}. "
                "Máximo12hallazgos. No cambies resultados originales ni certifiques límites no ejecutados.",
                "evidence": feedback,
            }
        )
        save(directory / "report.json", report)
        state["phase"] = "complete"
    except Exception as exc:
        state.update(phase="error", error=type(exc).__name__ + ": " + str(exc))
        print(json.dumps({"tool": tool, "phase": "error", "error": state["error"]}), flush=True)
    finally:
        await session.close()
        state.update(
            turns=session.turns,
            conversations=sorted(x for x in session.conversations if x),
            elapsed_seconds=round(time.time() - started, 2),
        )
        save(directory / "state.json", state)
        print(
            json.dumps(
                {"tool": tool, "phase": state["phase"], "seconds": state["elapsed_seconds"]}
            ),
            flush=True,
        )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--batch", type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    save(args.directory / "quota-before.json", quota())
    await asyncio.gather(*(tester(args.directory / tool, tool) for tool in BATCHES[args.batch - 1]))


if __name__ == "__main__":
    os.umask(0o077)
    asyncio.run(main())
