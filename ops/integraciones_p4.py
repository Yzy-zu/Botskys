"""Explicit operator run: real Drive fixture, reversible Lab setting, Minecraft cycle.

Never called by runtime/tests; does not resume an earlier run or uncertain action.
"""

import asyncio
import hashlib
import json
import shutil
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx

from botsky.adapters.drive import DriveClient
from botsky.adapters.groups import Groups
from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.adapters.minecraft import MinecraftConfig, MinecraftRemote
from botsky.adapters.oauth import OAuthToken
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result
from botsky.operational import OperationalPolicy

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


async def main():
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = ROOT / "private" / ("integraciones-p4-" + stamp)
    root.mkdir(mode=0o700)
    out = ROOT / "docs/evidencia/INTEGRACIONES-P4-20261106" / stamp
    out.mkdir(parents=True)
    profile = json.loads((ROOT / "private/integrations.json").read_text())
    original = Settings.load(ROOT / "private/config.integrations.toml")
    lab = next(iter(original.allowed_groups))
    settings = replace(
        original,
        root=root,
        database=root / "private/lab.sqlite3",
        instance="p4-" + stamp,
        activation_ms=int(time.time() * 1000) - 1000,
        calls=None,
    )
    for block in ("drive", "groups", "minecraft"):
        profile["permissions"][block]["write"] = True
    profile["permissions"]["groups"]["chats"] = [lab]
    policy = OperationalPolicy.build(profile, settings)
    oauth_dir = root / "private/drive"
    oauth_dir.mkdir(parents=True, mode=0o700)
    for name in ("client.json", "token.json"):
        shutil.copyfile(ROOT / "private/drive" / name, oauth_dir / name)
        (oauth_dir / name).chmod(0o600)
    token = OAuthToken(root)
    http = httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False)
    drive = DriveClient(profile["drive"]["folder_id"], token, client=http)
    e = profile["evolution"]
    groups = Groups(e["base_url"], e["instance"], e["api_key"], original.bot_ids, client=http)
    mc = MinecraftRemote(MinecraftConfig(**profile["minecraft"]))
    app = Application(settings, drive=drive, groups=groups, minecraft=mc, operations=policy)
    adapter = LocalAdapter(settings)
    private, cases, checks = [], [], {}
    group_before = None
    mc_before = None
    stopped = False
    created_id = None
    sequence = 0

    def persist():
        path = root / "journal.json"
        path.write_text(json.dumps(private, ensure_ascii=False, indent=2) + "\n")
        path.chmod(0o600)
        (out / "results.json").write_text(
            json.dumps({"cases": cases, "checks": checks}, ensure_ascii=False, indent=2) + "\n"
        )

    async def command(label, text, *, group=False, file=None):
        nonlocal sequence
        sequence += 1
        incoming = adapter.incoming(
            str(sequence), settings.owner, lab if group else settings.owner, text, is_group=group
        )
        if file:
            incoming = app.attach_local(incoming, file)
        private.append({"label": label, "state": "before_dispatch", "text": text})
        persist()
        receipt = app.receive(incoming)
        await app.jobs.run_pending()
        db = app.store.connect()
        try:
            row = db.execute("SELECT result_json FROM inbox WHERE id=?", (receipt.id,)).fetchone()
            result = Result.from_json(row[0])
        finally:
            db.close()
        private[-1].update(
            state="returned", receipt=receipt.id, result=json.loads(result.to_json())
        )
        cases.append(
            {
                "case": label,
                "status": result.status,
                "code": result.code,
                "evidence": "real_provider; simulated_operator_input; no_WhatsApp_delivery",
            }
        )
        persist()
        return receipt, result, incoming

    try:
        # Domain jobs use the real provider and isolated DB; outbox remains local.
        try:
            _, quota, _ = await command("drive_quota", "/drive cuota")
            checks["drive_5TiB"] = quota.data.get("quota", {}).get("limit") == 5 * 1024**4
            fixture = root / "p4-synthetic.txt"
            payload = (
                "Botsky point4 synthetic fixture " + stamp + "\n/daily is literal data.\n"
            ).encode()
            fixture.write_bytes(payload)
            fixture.chmod(0o600)
            receipt, saved, incoming = await command("drive_upload", "/drive guardar", file=fixture)
            db = app.store.connect()
            try:
                upload = db.execute(
                    "SELECT * FROM drive_uploads WHERE receipt_id=?", (receipt.id,)
                ).fetchone()
                created_id = upload["remote_id"] if upload else None
            finally:
                db.close()
            if saved.code == "drive_saved":
                assert app.receive(incoming).duplicate
                await app.jobs.run_pending()
                search_receipt, search, _ = await command(
                    "drive_search", "/drive buscar " + saved.data["name"]
                )
                if search.code == "drive_choices":
                    choices = search.data["choices"]
                    selected = next(
                        i for i, item in enumerate(choices, 1) if item["id"] == created_id
                    )
                    app.deliver(search_receipt.id, CollectingTransport())
                    _, recovered, _ = await command(
                        "drive_choose", f"/drive elegir {search.data['view_id']} {selected}"
                    )
                    if recovered.code == "drive_downloaded":
                        content = app.artifacts.path(recovered.data["artifacts"][0]).read_bytes()
                        checks["drive_roundtrip_sha256"] = (
                            hashlib.sha256(content).hexdigest()
                            == hashlib.sha256(payload).hexdigest()
                        )
                        checks["drive_fixture_bytes"] = len(payload)
                        checks["drive_duplicate_received_without_second_upload"] = True
        except Exception as exc:
            cases.append(
                {"case": "drive_flow_error", "exception": getattr(exc, "code", type(exc).__name__)}
            )
        finally:
            if created_id:
                # Only the generated ID registered by this run may be trashed.
                try:
                    meta = await drive._get(
                        "/files/" + created_id, {"fields": "id,appProperties,trashed"}
                    )
                    db = app.store.connect()
                    try:
                        own = db.execute(
                            "SELECT scope_hash FROM drive_uploads WHERE remote_id=?", (created_id,)
                        ).fetchone()
                    finally:
                        db.close()
                    if own and meta.get("appProperties", {}).get("botsky_scope") == own[0]:
                        access = await token()
                        response = await http.patch(
                            "https://www.googleapis.com/drive/v3/files/" + created_id,
                            params={"fields": "id,trashed"},
                            json={"trashed": True},
                            headers={"Authorization": "Bearer " + access},
                        )
                        checks["drive_fixture_trashed"] = (
                            response.status_code == 200 and response.json().get("trashed") is True
                        )
                except Exception as exc:
                    checks["drive_cleanup_error"] = getattr(exc, "code", type(exc).__name__)
            persist()

        try:
            raw = await groups._request("GET", "findGroupInfos", lab)
            assert raw.get("group", raw).get("subject") == "Botsky Lab"
            group_before = await groups.snapshot(lab)
            assert group_before["bot_is_admin"] and type(group_before["locked"]) is bool
            private.append({"label": "group_before", "snapshot": group_before})
            persist()
            target = not group_before["locked"]
            _, changed, _ = await command(
                "group_toggle_lock", "/admin cerrar" if target else "/admin abrir", group=True
            )
            observed = await groups.snapshot(lab)
            checks["group_setting_changed"] = (
                changed.code == "admin_completed" and observed["locked"] is target
            )
        except Exception as exc:
            cases.append(
                {"case": "group_flow_error", "exception": getattr(exc, "code", type(exc).__name__)}
            )
        finally:
            if group_before:
                state = await groups.snapshot(lab)
                if state["locked"] != group_before["locked"]:
                    await command(
                        "group_restore_lock",
                        "/admin cerrar" if group_before["locked"] else "/admin abrir",
                        group=True,
                    )
                state = await groups.snapshot(lab)
                if state["locked"] != group_before["locked"]:
                    await groups.setting(lab, "locked", group_before["locked"])
                    state = await groups.snapshot(lab)
                checks["group_setting_restored"] = state["locked"] == group_before["locked"]
                checks["group_members_and_roles_unchanged"] = digest(
                    state["participants"]
                ) == digest(group_before["participants"])
                checks["group_announcement_unchanged"] = (
                    state["announcement"] == group_before["announcement"]
                )
                persist()

        try:
            mc_before = await mc.query("status")
            for suffix in ("estado", "jugadores", "mundos", "mods", "config"):
                await command("mc_query_" + suffix, "/mc " + suffix)
            _, console, _ = await command("mc_console_list", "/mc consola list")
            checks["mc_console_bridge_ack"] = console.code == "minecraft_completed"
            players = await mc.query("players")
            private.append({"label": "mc_pre_stop", "status": mc_before, "players": players})
            persist()
            if (
                mc_before.get("online") is True
                and players.get("players_known") is True
                and players.get("count") == 0
            ):
                _, stop, _ = await command("mc_stop", "/mc parar")
                state = await mc.query("status")
                stopped = state.get("online") is False
                checks["mc_stopped"] = stopped and stop.code == "minecraft_completed"
                if stopped:
                    _, backup, _ = await command("mc_backup", "/mc backup")
                    response = backup.data.get("response", {})
                    checks["mc_backup_created"] = (
                        backup.code == "minecraft_completed"
                        and response.get("status") == "ok"
                        and response.get("files", 0) > 0
                    )
                    checks["mc_backup_source_bytes"] = response.get("bytes")
                    checks["mc_backup_entries"] = response.get("files")
            else:
                checks["mc_cycle_skipped"] = (
                    "Requires initially running server and fresh verified zero players"
                )
        except Exception as exc:
            cases.append(
                {"case": "mc_flow_error", "exception": getattr(exc, "code", type(exc).__name__)}
            )
        finally:
            if mc_before and mc_before.get("online") is True:
                state = await mc.query("status")
                if state.get("online") is False:
                    # Recovery is a distinct start action, never retrying stop/backup.
                    receipt, started, _ = await command("mc_restore_start", "/mc iniciar")
                    if started.code == "minecraft_resource_busy":
                        # The app denied dispatch; a direct recovery start is distinct.
                        private.append(
                            {"label": "mc_recovery_start", "result": await mc.change("start")}
                        )
                state = await mc.query("status")
                checks["mc_initial_online_state_restored"] = state.get("online") is True
                checks["mc_active_world_unchanged"] = state.get("active_world") == mc_before.get(
                    "active_world"
                )
                players = await mc.query("players")
                checks["mc_after_players_verified"] = players.get("players_known") is True
                checks["mc_after_player_count"] = players.get("count")
            persist()
    finally:
        persist()
        await http.aclose()
        await token.close()
    print(str(out.relative_to(ROOT)), flush=True)
    print(json.dumps({"cases": cases, "checks": checks}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
