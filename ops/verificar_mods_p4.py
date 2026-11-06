"""Operator-only NEW real Minecraft probe; never imported by runtime or tests.

Creates one synthetic behavior pack, verifies an in-game function from logs,
then removes it and restores the exact original world configuration. No sends.
"""

import asyncio
import base64
import hashlib
import json
import shlex
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from botsky.adapters.local import LocalAdapter
from botsky.adapters.minecraft import MinecraftConfig, MinecraftRemote
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result
from botsky.operational import OperationalPolicy

ROOT = Path(__file__).resolve().parents[1]


async def main():
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    private = ROOT / "private" / ("mods-p4-" + stamp)
    private.mkdir(mode=0o700)
    evidence = ROOT / "docs/evidencia/MODS-P4-20261106" / stamp
    evidence.mkdir(parents=True)
    profile = json.loads((ROOT / "private/integrations.json").read_text())
    config = MinecraftConfig(**profile["minecraft"])
    mc = MinecraftRemote(config)
    settings = Settings.load(ROOT / "private/config.integrations.toml")
    settings = replace(
        settings,
        root=private,
        database=private / "private/lab.sqlite3",
        instance="mods-" + stamp,
        activation_ms=int(time.time() * 1000) - 1000,
        calls=None,
    )
    profile["permissions"]["minecraft"]["write"] = True
    app = Application(settings, minecraft=mc, operations=OperationalPolicy.build(profile, settings))
    adapter = LocalAdapter(settings)
    results = []
    checks = {}
    pack_id = str(uuid.uuid4())
    resource_id = str(uuid.uuid4())
    folder = "botsky-probe-" + stamp
    marker = "Successfully executed 1 function entries."
    probe = "botsky_probe_" + uuid.uuid4().hex
    manifest = {
        "format_version": 2,
        "header": {
            "name": "Botsky synthetic acceptance probe",
            "description": "Temporary own fixture",
            "uuid": pack_id,
            "version": [1, 0, 0],
            "min_engine_version": [1, 21, 0],
        },
        "modules": [{"type": "data", "uuid": str(uuid.uuid4()), "version": [1, 0, 0]}],
    }
    manifest["dependencies"] = [{"uuid": resource_id, "version": [1, 0, 0]}]
    resource_manifest = {
        "format_version": 2,
        "header": {
            "name": "Botsky synthetic resources probe",
            "description": "Temporary own fixture",
            "uuid": resource_id,
            "version": [1, 0, 0],
            "min_engine_version": [1, 21, 0],
        },
        "modules": [{"type": "resources", "uuid": str(uuid.uuid4()), "version": [1, 0, 0]}],
        "dependencies": [{"uuid": pack_id, "version": [1, 0, 0]}],
    }
    stopped = False
    prepared = False
    original_status = None
    world = None

    def persist():
        doc = {
            "cases": results,
            "checks": checks,
            "fixture_pack_id": pack_id,
            "fixture_resource_id": resource_id,
            "fixture_function": probe,
            "oracle": "unique installed function executes list; game reports one executed function entry; zero players independently verified",
            "scope": "real Bedrock; own synthetic pack; simulated owner; no WhatsApp sends",
        }
        for target in (private / "journal.json", evidence / "results.json"):
            target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
            target.chmod(0o600)

    async def remote(program):
        compile(program, "operator_remote", "exec")
        prefix = "sudo -n " if config.use_sudo else ""
        proc = await asyncio.create_subprocess_exec(
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            config.host_alias,
            prefix + "python3 -I -c " + shlex.quote(program),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), 40)
        if proc.returncode:
            raise RuntimeError("operator_remote_failed")
        return json.loads(stdout)

    async def command(text):
        row = {"command": text, "state": "before_dispatch"}
        results.append(row)
        persist()
        receipt = app.receive(
            adapter.incoming(str(len(results)), settings.owner, settings.owner, text)
        )
        await app.jobs.run_pending()
        db = app.store.connect()
        try:
            result = Result.from_json(
                db.execute("SELECT result_json FROM inbox WHERE id=?", (receipt.id,)).fetchone()[0]
            )
        finally:
            db.close()
        row.update(state="returned", receipt=receipt.id, result=json.loads(result.to_json()))
        persist()
        if result.status != "ok":
            raise RuntimeError("command_not_confirmed_" + result.code)
        return result

    async def healthy():
        for _ in range(20):
            state = await mc.query("status")
            players = await mc.query("players")
            if state.get("online") is True and players.get("players_known") is True:
                if players.get("count") != 0:
                    raise RuntimeError("players_present")
                return state
            await asyncio.sleep(2)
        raise RuntimeError("health_not_verified")

    def location():
        return f"from pathlib import Path\nimport json,hashlib,base64,shutil,subprocess,time\nroot=Path({config.base_path!r})\nworld=root/'data/worlds'/{world!r}\npack=root/'data/behavior_packs'/{folder!r}\npack2=root/'data/resource_packs'/{folder!r}\np=world/'world_behavior_packs.json'\nrp=world/'world_resource_packs.json'\nbackup=root/{('.botsky-mods-' + stamp)!r}\n"

    try:
        # Deploy only the already authorized own worker, never the Zhana worker.
        worker = (ROOT / "ops/minecraft_worker.py").read_bytes()
        deployment = await remote(
            "from pathlib import Path\nimport base64,os,json,hashlib\np=Path("
            + repr(config.worker_path)
            + ")\nassert '/botsky/' in str(p)\nb=base64.b64decode("
            + repr(base64.b64encode(worker).decode())
            + ")\nt=p.with_suffix('.new')\nt.write_bytes(b)\nt.chmod(0o700)\nos.replace(t,p)\nprint(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
        )
        checks["worker_sha256"] = deployment["sha256"]
        assert deployment["sha256"] == hashlib.sha256(worker).hexdigest()
        original_status = await healthy()
        world = original_status["active_world"]
        await command("/mc mods")
        await command("/mc parar")
        stopped = True
        assert (await mc.query("status"))["online"] is False
        # Exact bytes and existence saved privately on the configured server.
        prepared_result = await remote(
            location()
            + "assert not pack.exists() and not pack2.exists() and not backup.exists()\nbackup.mkdir(mode=0o700)\nexists=p.exists()\nraw=p.read_bytes() if exists else b'[]'\n(backup/'original').write_bytes(raw)\n(backup/'exists').write_text(str(int(exists)))\n(backup/'original').chmod(0o600)\n(backup/'resource-exists').write_text(str(int(rp.exists())))\n(backup/'resource').write_bytes(rp.read_bytes() if rp.exists() else b'[]')\n(backup/'resource').chmod(0o600)\npack2.mkdir(mode=0o755)\n(pack2/'manifest.json').write_text("
            + repr(json.dumps(resource_manifest))
            + ")\nh=world/'.botsky-disabled-packs.json'\n(backup/'history-exists').write_text(str(int(h.exists())))\n(backup/'history').write_bytes(h.read_bytes() if h.exists() else b'[]')\n(backup/'history').chmod(0o600)\npack.mkdir(mode=0o755)\n(pack/'functions').mkdir()\n(pack/'manifest.json').write_text("
            + repr(json.dumps(manifest))
            + ")\n(pack/'functions'/"
            + repr(probe + ".mcfunction")
            + ").write_text("
            + repr("list\n")
            + ")\nprint(json.dumps({'original_sha256':hashlib.sha256(raw).hexdigest()}))"
        )
        prepared = True
        checks.update(prepared_result)
        await command("/mc mod activar " + pack_id)
        listing = await command("/mc mods")
        assert any(
            p["pack_id"] == pack_id and p["active"] for p in listing.data["response"]["installed"]
        )
        assert any(
            p["pack_id"] == resource_id and p["active"]
            for p in listing.data["response"]["installed"]
        )
        checks["mutual_dependency_pair_configured"] = True
        await command("/mc iniciar")
        stopped = False
        first = await healthy()
        loaded = await mc.query("mods")
        checks["fixture_load_observed"] = any(
            pack["pack_id"] == pack_id and pack.get("loaded") is True
            for pack in loaded["installed"]
        )
        assert checks["fixture_load_observed"]
        # Own fixture function is the oracle: bridge ACK alone is insufficient.
        proof = await remote(
            location()
            + "since=str(time.time())\nsubprocess.run(['docker','exec',"
            + repr(config.container)
            + ",'send-command',"
            + repr("function " + probe)
            + "],check=True,stdout=subprocess.DEVNULL)\nverified=False\nfor delay in (0.5,1,2,3):\n time.sleep(delay)\n r=subprocess.run(['docker','logs','--since',since,"
            + repr(config.container)
            + "],capture_output=True,text=True,check=True)\n verified="
            + repr(marker)
            + " in (r.stdout+r.stderr)\n if verified: break\nprint(json.dumps({'function_execution_confirmed':verified,'game_confirmation':'Successfully executed 1 function entries.' if verified else None}))"
        )
        checks.update(proof)
        assert proof["function_execution_confirmed"]
        await command("/mc reiniciar")
        restarted = await healthy()
        checks["restart_observed"] = restarted["started_at"] != first["started_at"]
        assert checks["restart_observed"]
        await command("/mc parar")
        stopped = True
        await command("/mc mod desactivar " + pack_id)
        listing = await command("/mc mods")
        assert not any(p["pack_id"] == pack_id for p in listing.data["response"]["behavior"])
        assert not any(p["pack_id"] == resource_id for p in listing.data["response"]["resource"])
        checks["enable_disable_verified"] = True
    finally:
        # Reconcile current state; never retry a mutation whose receipt is uncertain.
        if prepared:
            state = await mc.query("status")
            if state.get("container_status") == "running":
                players = await mc.query("players")
                if players.get("players_known") is not True or players.get("count") != 0:
                    raise RuntimeError("restoration_requires_operator_players_unknown_or_present")
                await mc.change("stop")
                stopped = True
            restored = await remote(
                location()
                + "raw=(backup/'original').read_bytes()\ncurrent=json.loads(p.read_text()) if p.exists() else []\noriginal=json.loads(raw)\nwithout=[row for row in current if row.get('pack_id') != "
                + repr(pack_id)
                + "]\nassert without==original, 'concurrent_configuration_change'\nassert json.loads((pack/'manifest.json').read_text())['header']['uuid']=="
                + repr(pack_id)
                + "\nassert json.loads((pack2/'manifest.json').read_text())['header']['uuid']=="
                + repr(resource_id)
                + "\nrr=(backup/'resource').read_bytes()\nrc=json.loads(rp.read_text()) if rp.exists() else []\nassert [row for row in rc if row.get('pack_id') != "
                + repr(resource_id)
                + "]==json.loads(rr), 'concurrent_resource_change'\nif (backup/'resource-exists').read_text()=='1':\n rp.write_bytes(rr)\n rp.chmod(0o644)\nelse:\n rp.unlink(missing_ok=True)\nif (backup/'exists').read_text()=='1':\n p.write_bytes(raw)\n p.chmod(0o644)\nelse:\n p.unlink(missing_ok=True)\nh=world/'.botsky-disabled-packs.json'\nold=(backup/'history').read_bytes()\ncurrent=json.loads(h.read_text()) if h.exists() else []\nassert [row for row in current if row.get('pack_id') not in "
                + repr([pack_id, resource_id])
                + "]==json.loads(old), 'concurrent_history_change'\nif (backup/'history-exists').read_text()=='1':\n h.write_bytes(old)\n h.chmod(0o600)\nelse:\n h.unlink(missing_ok=True)\nshutil.rmtree(pack)\nshutil.rmtree(pack2)\nprint(json.dumps({'configuration_restored_exactly': (p.read_bytes()==raw) if p.exists() else (backup/'exists').read_text()=='0','fixture_removed':not pack.exists() and not pack2.exists(), 'resource_configuration_restored_exactly':rp.read_bytes()==rr if rp.exists() else (backup/'resource-exists').read_text()=='0'}))"
            )
            checks.update(restored)
        if stopped and original_status and original_status.get("online"):
            # Fresh recovery operation, separately journaled from application receipts.
            checks["recovery_start"] = await mc.change("start")
            stopped = False
            final = await healthy()
            checks["online_restored"] = final.get("online") is True
            checks["world_unchanged"] = final.get("active_world") == world
        with app.store.transaction() as db:
            db.execute("UPDATE outbox SET state='cancelled' WHERE state='pending'")
        persist()
        (private / "CLOSED").write_text("No automatic resumption or retries.\n")
        (private / "CLOSED").chmod(0o600)
    print(json.dumps({"evidence": str(evidence.relative_to(ROOT)), "checks": checks}))


if __name__ == "__main__":
    asyncio.run(main())
