#!/usr/bin/env python3
"""Aislador para una nueva ronda AGY por herramienta; no publica mensajes."""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import campana_lab as lab
import stress_agy as agy
import stress_backend as backend
from agy_lab import save

ROOT = Path(__file__).resolve().parents[1]
PROD_CONFIG = ROOT / "private/production/config.toml"
PROD_PROFILE = ROOT / "private/integrations.production.json"
CAPACITY = asyncio.Semaphore(3)


async def isolated_prepare(base):
    """Use the production integration references as inputs, writing only to base."""
    original_load, lab_read, backend_read = (
        lab.Settings.load,
        lab.read_profile,
        backend.read_profile,
    )

    def load(path):
        return original_load(
            PROD_CONFIG if Path(path) == ROOT / "private/config.integrations.toml" else path
        )

    def read(path):
        return lab_read(PROD_PROFILE if Path(path) == ROOT / "private/integrations.json" else path)

    lab.Settings.load, lab.read_profile = load, read
    backend.read_profile = read
    try:
        result = await backend.prepare(base)
    finally:
        lab.Settings.load, lab.read_profile, backend.read_profile = (
            original_load,
            lab_read,
            backend_read,
        )
    app = base / "app"
    config_path = app / "config.toml"
    config = config_path.read_text().replace(
        'instance = "botsky-lab-20261106"', 'instance = "botsky-retest-20261107"'
    )
    config_path.write_text(config)
    config_path.chmod(0o600)
    profile_path = app / "private/integrations.json"
    profile = lab.read_profile(profile_path)
    profile["permissions"]["drive"]["write"] = False
    profile["permissions"]["groups"]["write"] = False
    profile["permissions"]["minecraft"]["write"] = False
    save(profile_path, profile)
    return result


class CaptureOnlyToolHTTP(backend.ToolHTTP):
    """Existing message route sees live=False even if backend tries to enable it."""

    @property
    def live(self):
        return False

    @live.setter
    def live(self, value):
        pass


async def worker(args):
    backend.ToolHTTP = CaptureOnlyToolHTTP
    tool = args.tool
    await backend.execute_tool(args.directory / f"batch{args.batch}", tool, args.directory / "base")


def prompt_for(tool):
    value = agy.prompt(tool)
    retained = [
        rule
        for rule in value["rules"]
        if "Drive tiene invalid_grant conocido" not in rule
        and "Máximo2casos publish=true" not in rule
        and "entre20 y32casos" not in rule
        and "fixture admite" not in rule
    ]
    value["rules"] = [
        "Propón entre 8 y 16 casos variados, cubriendo las operaciones principales del catálogo, campos y límites; usa casos negativos solo cuando la entrada es realmente inválida.",
        *retained,
        "En esta campaña ningún mensaje se publica: incluso publish=true se captura localmente; no cuentes ACK humano/proveedor.",
        "fixture es null o un nombre permitido del catálogo; null significa sin archivo. Nunca es una ruta.",
        "No uses fixture output:cNN ni recorridos que dependan de adjuntar un archivo producido por otro caso; esa cadena queda NOT_TESTED.",
        "Drive está en solo lectura; no propongas escrituras positivas ni intentes crear/subir/borrar archivos.",
        "Minecraft, grupos y llamadas: solo consultas permitidas; no mutaciones, invitaciones, kick, comandos, llamadas ni Live.",
        "No uses la limitación invalid_grant de campañas anteriores como supuesto: deja que proveedor actual se observe; no inventes tokens.",
    ]
    return value


async def run_tool(root, batch, tool):
    async with CAPACITY:
        if (root / "STOP").exists():
            return
        directory = root / f"batch{batch}" / tool
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
            quota = lab.quota()
        except Exception as exc:
            save(
                root / "STOP",
                {
                    "reason": "quota_unavailable_or_at_stop_threshold",
                    "tool": tool,
                    "error": type(exc).__name__,
                },
            )
            return
        save(directory / "quota-before.json", quota)
        remaining = [
            w["remaining_percent"]
            for b in quota["buckets"]
            for n in ("primary", "secondary")
            if (w := b.get(n))
        ]
        if not remaining or min(remaining) <= 5:
            save(root / "STOP", {"reason": "quota_le_5_percent", "tool": tool})
            return
        print(
            json.dumps({"batch": batch, "tool": tool, "phase": "starting", "model": agy.MODEL}),
            flush=True,
        )
        session = agy.Session(directory)
        started = time.monotonic()
        state = {"tool": tool, "model": agy.MODEL, "phase": "starting"}
        proc = None
        try:
            await session.start()
            save(directory / "state.json", {**state, "phase": "proposing"})
            proposal_task = asyncio.create_task(session.turn(prompt_for(tool)))
            while not proposal_task.done():
                if (root / "STOP").exists():
                    proposal_task.cancel()
                    raise RuntimeError("campaign_explicit_stop")
                await asyncio.sleep(2)
            proposal = await proposal_task
            save(directory / "proposal-original.json", proposal)
            cases = proposal.get("cases")
            if not isinstance(cases, list) or any(not isinstance(c, dict) for c in cases):
                raise ValueError("proposal_cases_must_be_objects")
            excluded = [
                c
                for c in cases
                if isinstance(c.get("fixture"), str) and c["fixture"].startswith("output:")
            ]
            if excluded:
                save(
                    directory / "excluded-output-fixtures.json",
                    {
                        "status": "NOT_TESTED",
                        "cases": excluded,
                        "reason": "generated-output attachment/citation chain unsupported by this harness",
                    },
                )
                cases = [c for c in cases if c not in excluded]
                proposal["cases"] = cases
            if not isinstance(cases, list) or not 8 <= len(cases) <= 16:
                raise ValueError("proposal_must_have_8_to_16_cases")
            for case in cases:
                case["publish"] = False
            save(directory / "proposal.json", proposal)
            print(
                json.dumps(
                    {"batch": batch, "tool": tool, "phase": "proposal_frozen", "cases": len(cases)}
                ),
                flush=True,
            )
            save(
                directory / "state.json",
                {**state, "phase": "waiting_for_execution", "proposed_cases": len(cases)},
            )
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--directory",
                str(root),
                "--batch",
                str(batch),
                "--tool",
                tool,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            log = directory / "backend-worker.log"
            with log.open("wb") as out:
                last_progress, started = time.monotonic(), time.monotonic()
                while proc.returncode is None:
                    if (
                        (root / "STOP").exists()
                        or time.monotonic() - started > 900
                        or time.monotonic() - last_progress > 210
                    ):
                        os.killpg(proc.pid, 15)
                        try:
                            await asyncio.wait_for(proc.wait(), 5)
                        except TimeoutError:
                            os.killpg(proc.pid, 9)
                            await proc.wait()
                        break
                    try:
                        line = await asyncio.wait_for(proc.stdout.readline(), 5)
                    except TimeoutError:
                        continue
                    if not line:
                        break
                    out.write(line)
                    out.flush()
                    last_progress = time.monotonic()
                await proc.wait()
            if proc.returncode not in (0, None) or not (directory / "feedback.json").exists():
                raise RuntimeError("isolated_backend_failed")
            feedback = json.loads((directory / "feedback.json").read_text())
            result_rows = json.loads((directory / "execution/results.json").read_text())
            if tool == "manage_minecraft":
                for row in result_rows:
                    row.pop("result", None)
                    row["result_note"] = (
                        "Read-only query output withheld; inspect private backend evidence."
                    )
            feedback["full_execution_evidence"] = [
                {
                    "case": row.get("case"),
                    "verdict": row.get("verdict"),
                    "reason": backend.safe_text(row.get("reason", "")),
                    "result": backend.safe_text(
                        json.dumps(row.get("result", {}), ensure_ascii=False)
                    )[:12000],
                    "artifacts": row.get("artifacts", []),
                    "evidence_level": row.get("evidence_level"),
                }
                for row in result_rows
            ]
            save(directory / "state.json", {**state, "phase": "reporting"})
            report = await session.turn(
                {
                    "task": "Redacta informe con solo evidencia; separa sospechas, runner, bloqueos y efectos observados. No corrijas producto ni declares validación humana. JSON {tool,works,suspected_errors,oracle_issues,blocked,coverage_gaps,recommendations}.",
                    "evidence": feedback,
                }
            )
            save(directory / "report.json", report)
            state["phase"] = "complete"
        except Exception as exc:
            state.update(phase="error", error=type(exc).__name__ + ": " + str(exc)[:200])
        finally:
            if proc is not None and proc.returncode is None:
                try:
                    os.killpg(proc.pid, 15)
                    await asyncio.wait_for(proc.wait(), 5)
                except ProcessLookupError, TimeoutError:
                    try:
                        os.killpg(proc.pid, 9)
                    except ProcessLookupError:
                        pass
                    await proc.wait()
            await session.close()
            state.update(
                turns=session.turns,
                conversations=sorted(x for x in session.conversations if x),
                elapsed_seconds=round(time.monotonic() - started, 1),
            )
            save(directory / "state.json", state)
            print(
                json.dumps(
                    {
                        "batch": batch,
                        "tool": tool,
                        "phase": state["phase"],
                        "seconds": state["elapsed_seconds"],
                    }
                ),
                flush=True,
            )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--batch", type=int, choices=(1, 2, 3))
    parser.add_argument("--tool", choices=tuple(t for group in agy.BATCHES for t in group))
    args = parser.parse_args()
    args.directory = args.directory.resolve()
    if args.worker:
        if not args.batch or not args.tool:
            parser.error("worker necesita --batch y --tool")
        await worker(args)
        return
    if not args.run:
        parser.error("ejecución explícita requerida: --run")
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    save(
        args.directory / "campaign.json",
        {
            "model": agy.MODEL,
            "tools": [t for g in agy.BATCHES for t in g],
            "messages": "captured locally",
            "drive_write": False,
        },
    )
    await isolated_prepare(args.directory / "base")
    for batch, tools in enumerate(agy.BATCHES, 1):
        try:
            quota = lab.quota()
        except Exception as exc:
            save(
                args.directory / "STOP",
                {"reason": "quota_unavailable_or_at_stop_threshold", "error": type(exc).__name__},
            )
            return
        save(args.directory / f"batch{batch}-quota.json", quota)
        if (
            min(
                w["remaining_percent"]
                for b in quota["buckets"]
                for n in ("primary", "secondary")
                if (w := b.get(n))
            )
            <= 5
        ):
            save(args.directory / "STOP", {"reason": "quota_le_5_percent"})
            return
        await asyncio.gather(*(run_tool(args.directory, batch, tool) for tool in tools))
        if (args.directory / "STOP").exists():
            return


if __name__ == "__main__":
    os.umask(0o077)
    asyncio.run(main())
