"""Operator-only real check. Own paired fixtures; no automatic resumption/retries.

Requires a fresh explicit operator assignment. Never imported by runtime/tests.
Snapshots configuration privately, exercises normal rollback and one interrupted
write while offline, then removes only its own fixtures. No messages or world restore.
"""

import asyncio
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
    private = ROOT / "private" / ("native-recovery-" + stamp)
    private.mkdir(mode=0o700)
    evidence = ROOT / "docs/evidencia/NATIVE-RECOVERY-20261106" / stamp
    evidence.mkdir(parents=True)
    profile = json.loads((ROOT / "private/integrations.json").read_text())
    config = MinecraftConfig(**profile["minecraft"])
    mc = MinecraftRemote(config)
    settings = Settings.load(ROOT / "private/config.integrations.toml")
    settings = replace(
        settings,
        root=private,
        database=private / "private/lab.sqlite3",
        instance="recovery-" + stamp,
        activation_ms=int(time.time() * 1000) - 1000,
        calls=None,
    )
    profile["permissions"]["minecraft"]["write"] = True
    app = Application(settings, minecraft=mc, operations=OperationalPolicy.build(profile, settings))
    adapter = LocalAdapter(settings)
    document = {
        "scope": "new explicit real check; own fixtures; disposable DB; no sends",
        "oracles": [
            "paired activation loaded; restart changes StartedAt and is game ready, or native failure retained",
            "recover offline restores exact bytes/modes/existence of both world JSONs and history",
            "injected exception after first atomic replacement leaves durable pending across worker processes",
            "pending blocks start before dispatch; explicit recover restores all original configuration",
            "repeat offline recover is unchanged; fixtures removed; same world ready and zero players",
        ],
        "cases": [],
        "checks": {},
    }
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    folder = "botsky-recovery-" + stamp
    document["fixture_ids"] = [a, b]

    def save():
        for path in (private / "journal.json", evidence / "results.json"):
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            path.chmod(0o600)

    async def remote(code):
        compile(code, "operator_check", "exec")
        process = await asyncio.create_subprocess_exec(
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            config.host_alias,
            ("sudo -n " if config.use_sudo else "") + "python3 -I -c " + shlex.quote(code),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), 45)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise RuntimeError(
                "operator_check_failed; inspect private snapshots before any further mutation"
            )
        return json.loads(stdout)

    async def command(text, *, expected="ok"):
        row = {"command": text, "state": "before_dispatch"}
        document["cases"].append(row)
        save()
        receipt = app.receive(
            adapter.incoming(str(len(document["cases"])), settings.owner, settings.owner, text)
        )
        await app.jobs.run_pending()
        with app.store.connect() as db:
            result = Result.from_json(
                db.execute("SELECT result_json FROM inbox WHERE id=?", (receipt.id,)).fetchone()[0]
            )
        row.update(state="returned", receipt=receipt.id, result=json.loads(result.to_json()))
        save()
        if expected and result.status != expected:
            raise RuntimeError("unexpected_command_result_" + result.code)
        return result

    async def healthy():
        state = await mc.query("status")
        players = await mc.query("players")
        if (
            state.get("game_status") != "ready"
            or players.get("players_known") is not True
            or players.get("count") != 0
        ):
            raise RuntimeError("game_ready_and_zero_players_not_verified")
        return state

    # All remote file access derives from the own worker's validated discovery.
    prefix = (
        "import importlib.util,json,base64,hashlib,stat,shutil,os\nfrom pathlib import Path\n"
        + "s=importlib.util.spec_from_file_location('ownworker',"
        + repr(config.worker_path)
        + ")\n"
        + "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
        + "layout=m.discover("
        + repr(config.container)
        + ",Path("
        + repr(config.base_path)
        + "))\n"
        + "data=layout['data_path'];world=data/'worlds'/layout['active_world']\n"
        + "backup=Path("
        + repr(config.base_path)
        + ")/"
        + repr(".botsky-check-" + stamp)
        + "\n"
        + "names=['world_behavior_packs.json','world_resource_packs.json','.botsky-disabled-packs.json']\n"
        + "folders=[data/'behavior_packs'/"
        + repr(folder)
        + ",data/'resource_packs'/"
        + repr(folder)
        + "]\n"
    )
    verify = """
old=json.loads((backup/'snapshots.json').read_text())
checks={}
for name in names:
 p=world/name; entry=old[name]
 raw=p.read_bytes() if p.exists() else None
 assert (base64.b64encode(raw).decode() if raw is not None else None)==entry['bytes'], 'configuration_bytes_drift'
 assert (stat.S_IMODE(p.stat().st_mode) if p.exists() else None)==entry['mode'], 'configuration_mode_drift'
 checks[name]={'exact':True,'exists':p.exists(),'sha256':hashlib.sha256(raw).hexdigest() if raw is not None else None}
"""
    save()
    initial = await healthy()
    if initial.get("reconciliation") not in {"no_pending_change", "recovered"}:
        raise RuntimeError("prior_journal_requires_separate_review_before_stop")
    document["checks"]["initial"] = initial
    document["checks"]["discover"] = await mc.query("discover")
    save()
    await command("/mc parar")
    prepared = await remote(
        prefix
        + """
assert not backup.exists() and all(not p.exists() for p in folders)
prior=m._journal_read(world)
assert prior is None or prior['phase']=='recovered', 'prior_journal_requires_separate_review'
backup.mkdir(mode=0o700)
if prior is not None:
 p=backup/'prior-recovery.json';p.write_text(json.dumps(prior));p.chmod(0o600)
snapshots={}
for name in names:
 p=world/name
 snapshots[name]={'bytes':base64.b64encode(p.read_bytes()).decode() if p.exists() else None,'mode':stat.S_IMODE(p.stat().st_mode) if p.exists() else None}
p=backup/'snapshots.json';p.write_text(json.dumps(snapshots));p.chmod(0o600)
"""
        + "ids="
        + repr([a, b])
        + "\n"
        + """
for index,(kind,module) in enumerate([('behavior','data'),('resource','resources')]):
 p=folders[index];p.mkdir(mode=0o755)
 manifest={'format_version':2,'header':{'name':'Botsky recovery synthetic '+kind,'description':'Temporary own fixture','uuid':ids[index],'version':[1,0,0],'min_engine_version':[1,21,0]},'modules':[{'type':module,'uuid':str(m.uuid.uuid4()),'version':[1,0,0]}],'dependencies':[{'uuid':ids[1-index],'version':[1,0,0]}]}
 (p/'manifest.json').write_text(json.dumps(manifest));(p/'manifest.json').chmod(0o644)
print(json.dumps({'prepared':True,'world':world.name}))
"""
    )
    document["checks"]["prepared"] = prepared
    save()
    await command("/mc mod activar " + a)
    await command("/mc iniciar")
    first = await healthy()
    mods = await mc.query("mods")
    assert any(p["pack_id"] == a and p.get("loaded") is True for p in mods["installed"])
    document["checks"]["pair_behavior_loaded"] = True
    save()
    restart = await command("/mc reiniciar", expected=None)
    state = await mc.query("status")
    document["checks"]["restart_state"] = state
    document["checks"]["restart_result"] = restart.status
    save()
    if restart.status == "ok":
        current = await healthy()
        assert current["started_at"] != first["started_at"]
        document["checks"]["paired_restart_verified"] = True
    elif state.get("game_status") != "failed":
        raise RuntimeError("restart_uncertain_needs_separate_observation_no_retry")
    # Explicit new stop after observed state, never a repeated restart.
    await command("/mc parar")
    await command("/mc recuperar")
    document["checks"]["normal_recovery"] = await remote(
        prefix + verify + "print(json.dumps(checks))\n"
    )
    again = await command("/mc recuperar")
    assert again.data["response"]["changed"] is False
    save()
    # One synthetic crash while OFFLINE, using this deployed worker and real files.
    fault = await remote(
        prefix
        + """
assert json.loads(m._run(['docker','inspect','--format','{{json .State}}',CONTAINER]))['Status']=='exited'
original=m._atomic_json
written=[]
def interrupted(path,value,**kwargs):
 original(path,value,**kwargs)
 if path.name=='world_behavior_packs.json':
  written.append(path.name)
  raise OSError('own synthetic interruption after first replacement')
m._atomic_json=interrupted
try:
 m.handle(REQUEST)
except OSError as exc:
 assert str(exc)=='own synthetic interruption after first replacement'
else:
 raise RuntimeError('fault_not_injected')
assert written==['world_behavior_packs.json']
record=m._journal_read(world)
assert record['phase']=='pending'
print(json.dumps({'injected_after_atomic_replacement':True,'phase':record['phase'],'id':record['id']}))
""".replace("CONTAINER", repr(config.container)).replace(
            "REQUEST",
            repr(
                {
                    "action": "enable_mod",
                    "params": {"name": a},
                    "container": config.container,
                    "base_path": config.base_path,
                }
            ),
        )
    )
    document["checks"]["fault"] = fault
    save()
    blocked = await command("/mc iniciar", expected="needs_input")
    assert blocked.data["response"]["code"] == "recovery_required"
    await command("/mc recuperar")
    document["checks"]["interrupted_recovery"] = await remote(
        prefix + verify + "print(json.dumps(checks))\n"
    )
    removed = await remote(
        prefix
        + verify
        + "ids="
        + repr([a, b])
        + "\n"
        + """
for p,identity in zip(folders,ids):
 assert json.loads((p/'manifest.json').read_text())['header']['uuid']==identity
 shutil.rmtree(p)
print(json.dumps({'own_fixtures_removed':all(not p.exists() for p in folders)}))
"""
    )
    document["checks"].update(removed)
    await command("/mc iniciar")
    final = await healthy()
    assert final["active_world"] == initial["active_world"]
    document["checks"]["final"] = final
    document["checks"]["same_world_ready_zero_players"] = True
    with app.store.transaction() as db:
        db.execute("UPDATE outbox SET state='cancelled' WHERE state='pending'")
        document["checks"]["active_jobs"] = db.execute(
            "SELECT count(*) FROM jobs WHERE state IN ('queued','running')"
        ).fetchone()[0]
    save()
    (private / "CLOSED").write_text("Finished. Never resume automatically.\n")
    (private / "CLOSED").chmod(0o600)
    print(
        json.dumps(
            {"evidence": str(evidence.relative_to(ROOT)), "checks": document["checks"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
