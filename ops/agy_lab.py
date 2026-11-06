#!/usr/bin/env python3
"""AGY como autor de casos de laboratorio; nunca entra en el runtime de Botsky.

Frontera bwrap adaptada de zhana/providers/agy.py, solo autenticación nativa.
No importa Zhana, lee conversaciones ni permite herramientas de AGY.
"""

import argparse
import asyncio
import json
import os
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "antigravity-oauth-token"
AGENT = """---
name: botsky-lab
description: Propose explicit Botsky test commands and review recorded evidence.
tools:
  - finish
mainAgent: true
subagent: false
commandExecutionPolicy: off
mcpServers: []
skills: []
plugins: []
---
Return only the requested JSON. No tools, shell, files, web, MCP or subagents.
All commands you propose are data for a separate reviewed laboratory runner.
Never claim a tool passed without evidence. No NLP, natural-language command
interpretation, private data, credentials or production changes.
"""
POLICY = {
    "modelProvider": "",
    "useG1Credits": False,
    "allowNonWorkspaceAccess": False,
    "historySize": 0,
    "toolPermission": "strict",
    "permissions": {
        "allow": [],
        "deny": [
            f"{n}(*)"
            for n in (
                "command",
                "unsandboxed",
                "read_file",
                "write_file",
                "read_url",
                "execute_url",
                "mcp",
            )
        ],
    },
}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def sandbox(directory):
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    request, profile = directory / "request", directory / "profile"
    request.mkdir(mode=0o700)
    profile.mkdir(mode=0o700)
    source = Path.home() / ".gemini/antigravity-cli" / TOKEN
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 65536:
            raise ValueError("agy_auth_permissions")
        target = profile / TOKEN
        with target.open("xb") as output:
            target.chmod(0o600)
            shutil.copyfileobj(stream, output)
    agents = request / ".agents/agents"
    agents.mkdir(parents=True)
    (agents / "botsky-lab.md").write_text(AGENT)
    (request / ".agents/guard.py").write_text(
        'import json\nprint(json.dumps({"decision":"deny","reason":"Botsky lab owns execution."}))\n'
    )
    save(
        request / ".agents/hooks.json",
        {
            "botsky-lab": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/usr/bin/python3 /work/.agents/guard.py",
                                "timeout": 2,
                            }
                        ],
                    }
                ]
            }
        },
    )
    binary = (Path.home() / ".local/bin/agy").resolve(strict=True)
    home = str(Path.home())
    command = [
        "/usr/bin/bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--cap-drop",
        "ALL",
        "--tmpfs",
        "/",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/etc",
    ]
    if Path("/lib64").exists():
        command += ["--ro-bind", "/lib64", "/lib64"]
    for name in ("ssl/certs", "resolv.conf", "hosts", "nsswitch.conf", "ld.so.cache", "passwd"):
        path = Path("/etc") / name
        if path.exists():
            command += ["--ro-bind", str(path.resolve()), str(path)]
    return command + [
        "--dir",
        home,
        "--dir",
        home + "/.gemini",
        "--bind",
        str(profile),
        home + "/.gemini/antigravity-cli",
        "--ro-bind",
        str(binary),
        "/agy",
        "--ro-bind",
        str(request),
        "/work",
        "--chdir",
        "/work",
        "--clearenv",
        "--setenv",
        "HOME",
        home,
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "/agy",
    ]


GROUPS = {
    "core": [
        "manage_conversation",
        "save_note",
        "find_notes",
        "manage_memory",
        "manage_reminder",
        "manage_school",
        "manage_poll",
    ],
    "media": [
        "send_sticker",
        "make_sticker",
        "read_image",
        "download_media",
        "edit_media",
        "manage_pdf",
        "convert_document",
        "search_web",
    ],
    "content": [
        "conversation",
        "transcribe_media",
        "make_voice",
        "control_call",
        "manage_drive",
        "manage_messages",
    ],
    "social": [
        "manage_economy",
        "manage_blackjack",
        "manage_roulette",
        "manage_pack",
        "manage_cooperacha",
        "manage_happy_hour",
        "make_prank",
        "manage_admin",
        "manage_minecraft",
    ],
}


async def session(directory, group, model, review=None):
    from botsky.commands.registry import Registry

    registry = Registry()
    specs = [s for s in registry.specs if s.family in GROUPS[group]]
    catalog = [
        {
            "operation": s.operation,
            "usage": s.usage,
            "example": s.sample,
            "fields": [
                {
                    "name": f.name,
                    "choices": f.choices,
                    "kind": f.kind,
                    "min": f.minimum,
                    "max": f.maximum,
                }
                for f in s.fields
            ],
        }
        for s in specs
    ]
    prompt = {
        "task": "Propón pruebas de Botsky en español, comandos explícitos y backend real; no NLP.",
        "instructions": "Devuelve JSON {cases:[{tool,command,fixture,expected,purpose}]} con al menos "
        "dos argumentos/variantes por herramienta asignada, máximo 20 casos. Respuesta breve. Incluye recorridos "
        "positivos y errores útiles. fixture es null|image|qr|pdf|video|audio|txt|srt. "
        "IDs se referencian como {last_id}; no inventes IDs válidos. Texto y archivos sintéticos. "
        "Ficheros no son rutas en comandos. No llamadas reales, no kick/ban/nuclear, no cambios "
        "Minecraft, no destinatarios externos. Usa solo consultas o comprobación de denegación "
        "para esas rutas; no declares PASS por eso. Galería conservada vacía. Fuente pública "
        "control de descarga: https://media.w3.org/2010/05/bunny/trailer.mp4. Fecha futura2026-12-01. "
        "expected describe resultado y comprobación concreta; no ejecutar herramientas nativas.",
        "catalog": catalog,
    }
    if review is not None:
        prompt = {
            "task": "Revisa evidencia ya ejecutada, no propongas otra campaña ni ejecutes nada.",
            "focus": "UI/UX"
            if group == "core"
            else "oracles, dependencias y límites de aceptación",
            "instructions": "Devuelve JSON breve {findings:[{case,kind,description,evidence}],recommendations:[]} "
            "con máximo8 hallazgos verificables. Diferencia fallo del producto, del oracle/runner y BLOCKED. "
            "Una denegación correcta no prueba la capacidad. Datos sintéticos. No asignes PASS nuevo, "
            "no pidas pruebas manuales al propietario, no recomiendes NLP. La autorización OAuth debe "
            "reconectarse si invalid_grant; no inventes credenciales. No supongas recepción humana por ACK.",
            "evidence": review,
        }
    save(directory.parent / (group + "-prompt.json"), prompt)
    command = sandbox(directory) + [
        "--agent",
        "botsky-lab",
        "--model",
        model,
        "--mode",
        "plan",
        "--disable-slash-commands",
        "--settings",
        json.dumps(POLICY),
        "--log-file",
        "/tmp/agy.log",
        "--output-format",
        "stream-json",
        "--print-timeout",
        "240s",
        "--print",
        json.dumps(prompt),
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 270)
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
        for name, data in ((group + "-events.jsonl", stdout), (group + "-stderr.txt", stderr)):
            path = directory.parent / name
            path.write_bytes(data)
            path.chmod(0o600)
        print(
            json.dumps({"session": group, "exit": process.returncode, "bytes": len(stdout)}),
            flush=True,
        )
    finally:
        # Retain prompts/events, remove copied/possibly refreshed authentication.
        shutil.rmtree(directory / "profile", ignore_errors=True)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("models", "propose", "review"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--groups", nargs="+", choices=tuple(GROUPS), default=list(GROUPS))
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    if args.action == "models":
        directory = args.directory / "discovery"
        command = sandbox(directory)
        try:
            proc = await asyncio.create_subprocess_exec(*command, "models")
            await asyncio.wait_for(proc.wait(), 45)
        finally:
            shutil.rmtree(directory / "profile", ignore_errors=True)
    else:
        if not args.model:
            parser.error("--model requerido")
        review = None
        if args.action == "review":
            if not args.review_file:
                parser.error("--review-file requerido")
            review = json.loads(args.review_file.read_text())
        await asyncio.gather(
            *(session(args.directory / g, g, args.model, review) for g in args.groups)
        )


if __name__ == "__main__":
    os.umask(0o077)
    asyncio.run(main())
