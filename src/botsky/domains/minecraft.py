"""Minecraft solo por cliente cerrado; consola no es shell del host."""

import json

from ..contracts import Result, canonical

READS = {"status", "players", "worlds", "mods", "config"}


def execute(db, context, spec, args, now, app):
    backend = app.minecraft
    if backend is None:
        return Result(
            "failed",
            "minecraft_not_configured",
            "El servidor Minecraft no está configurado para Botsky.",
        )
    action = spec.original_action
    if action not in READS:
        from ..adapters.minecraft import MinecraftLocalValidationError

        params = {k: v for k, v in args.items() if v is not None}
        try:
            params = backend.validate_change(action, params)
        except ValueError, MinecraftLocalValidationError:
            return Result(
                "needs_input",
                "minecraft_local_validation",
                "El cambio no es admisible. Consola: list, save, time query daytime o weather query; no comandos del host.",
            )
        if db.execute(
            "SELECT 1 FROM external_operations WHERE domain='minecraft' AND resource=? AND state IN ('reserved','sending','uncertain')",
            (backend.server_id,),
        ).fetchone():
            return Result(
                "needs_input",
                "minecraft_resource_busy",
                "Hay un cambio pendiente o incierto en el servidor. Consulta estado y pide revisión antes de otro cambio.",
            )
    else:
        params = {}
    result = app.jobs.reserve(
        db,
        context,
        spec.operation,
        {"server_id": backend.server_id, "params": params},
        [],
        now,
        resource="minecraft-" + backend.server_id,
    )
    if result.code == "job_queued" and action not in READS:
        db.execute(
            "INSERT INTO external_operations(receipt_id,domain,resource,action,args_json) VALUES(?,?,?,?,?)",
            (context.receipt_id, "minecraft", backend.server_id, action, canonical(params)),
        )
    return result


def retire_job(db, receipt_id, now):
    db.execute(
        "UPDATE external_operations SET state=CASE WHEN state='sending' THEN 'uncertain' ELSE 'cancelled' END WHERE receipt_id=? AND state IN ('reserved','sending')",
        (receipt_id,),
    )


def public(value, depth=0):
    if depth > 6:
        return "[recortado]"
    if isinstance(value, dict):
        return {
            k: public(v, depth + 1)
            for k, v in list(value.items())[:100]
            if isinstance(k, str)
            and not any(
                word in k.casefold()
                for word in (
                    "token",
                    "password",
                    "secret",
                    "key",
                    "credential",
                    "authorization",
                    "path",
                    "host",
                )
            )
        }
    if isinstance(value, list):
        return [public(v, depth + 1) for v in value[:100]]
    if isinstance(value, str):
        return value[:500]
    if value is None or type(value) in (int, float, bool):
        return value
    return "[omitido]"


def render(data, action):
    if action == "console":
        return "Comando enviado al puente Minecraft; no hay confirmación de ejecución dentro del juego."
    if action == "players":
        if data.get("online") is not True or data.get("players_known") is not True:
            return "No hay una lista actual verificada de jugadores."
        return "Jugadores: " + ", ".join(str(v)[:80] for v in data.get("players", [])[:100])
    if action == "mods":
        lines = ["Mods del servidor"]
        world = data.get("active_world") or data.get("world") or data.get("world_name")
        lines.append(
            f"Mundo: {str(world)[:160]}"
            if isinstance(world, str) and world
            else "Mundo: desconocido"
        )
        raw_entries = data.get(
            "installed", data.get("mods", data.get("packages", data.get("items")))
        )
        entries = list(raw_entries) if isinstance(raw_entries, list) else []

        def is_base(name):
            return name.startswith("resourcePack.") or ".vanilla." in name

        base_names = {
            str(item.get("name", ""))
            for item in entries
            if isinstance(item, dict) and is_base(str(item.get("name", "")))
        }
        base_count = data.get("base_pack_count", 0)
        base_count = (
            max(base_count, len(base_names)) if isinstance(base_count, int) else len(base_names)
        )
        if base_count:
            lines.append(
                f"Paquetes base del servidor: {base_count} (omitidos del listado de mods)."
            )

        configured = data.get("behavior", []) + data.get("resource", [])
        installed_keys = {
            (str(row.get("pack_id", "")).casefold(), str(row.get("version")))
            for row in entries
            if isinstance(row, dict)
        }
        if isinstance(configured, list):
            for row in configured:
                if not isinstance(row, dict):
                    continue
                key = (str(row.get("pack_id", "")).casefold(), str(row.get("version")))
                if key not in installed_keys:
                    entries.append(
                        {
                            **row,
                            "name": row.get("name") or row.get("pack_id"),
                            "pack_type": row.get("pack_type") or "behavior/resource",
                            "configured": True,
                            "missing": True,
                            "version_mismatch": any(
                                candidate[0] == key[0] and candidate[1] != key[1]
                                for candidate in installed_keys
                            ),
                        }
                    )
        if not isinstance(raw_entries, list):
            lines.append("No se recibió una lista de mods verificable.")
        elif not entries:
            lines.append("No hay mods instalados/configurados.")
        else:
            uuid_counts = {}
            for item in entries:
                if isinstance(item, dict):
                    key = item.get("pack_id") or item.get("uuid") or item.get("id")
                    if isinstance(key, str) and key:
                        uuid_counts[key] = uuid_counts.get(key, 0) + 1
            entries.sort(
                key=lambda item: (
                    not bool(item.get("configured", item.get("active", False)))
                    if isinstance(item, dict)
                    else True,
                    str(item.get("name", "")).casefold()
                    if isinstance(item, dict)
                    else str(item).casefold(),
                )
            )
            visible_entries = [
                item
                for item in entries
                if not (isinstance(item, dict) and is_base(str(item.get("name", ""))))
            ]
            for entry in visible_entries[:100]:
                if isinstance(entry, str):
                    name, enabled, kind, version, identifier = entry[:160], None, None, None, None
                elif isinstance(entry, dict):
                    name = (
                        entry.get("name")
                        or entry.get("mod")
                        or entry.get("package")
                        or "(sin nombre)"
                    )
                    name = str(name)[:160]
                    enabled = entry.get("enabled", entry.get("configured", entry.get("active")))
                    kind = entry.get("pack_type") or entry.get("type") or entry.get("loader")
                    version = entry.get("version")
                    identifier = entry.get("pack_id") or entry.get("uuid") or entry.get("id")
                    if isinstance(version, list):
                        version = ".".join(str(part) for part in version)
                    enabled = entry.get("configured", entry.get("active", enabled))
                else:
                    continue
                label = (
                    "configurado"
                    if enabled is True
                    else "desactivado"
                    if enabled is False
                    else "estado desconocido"
                )
                type_labels = {"behavior": "comportamiento", "resource": "recursos"}
                kind_text = type_labels.get(kind, str(kind)) if kind else "tipo desconocido"
                version_text = str(version)[:80] if version else "versión desconocida"
                line = f"• {name}: {label} · {kind_text} · v{version_text}"
                if isinstance(entry, dict):
                    if entry.get("loaded") is True:
                        if enabled is False:
                            line += " · pendiente de reinicio; aún cargado"
                        else:
                            line += " · carga observada"
                    dependencies = entry.get("dependencies")
                    if isinstance(dependencies, list) and dependencies:
                        requirements = []
                        for dependency in dependencies[:20]:
                            if not isinstance(dependency, dict):
                                continue
                            dep_id = dependency.get("uuid") or dependency.get("pack_id")
                            dep_version = dependency.get("version")
                            if isinstance(dep_version, list):
                                dep_version = ".".join(str(part) for part in dep_version)
                            if isinstance(dep_id, str) and dep_id:
                                requirements.append(
                                    f"{dep_id[:80]}@{str(dep_version)[:40]}"
                                    if dep_version is not None
                                    else dep_id[:80]
                                )
                        if requirements:
                            line += " · Requiere: " + ", ".join(requirements)
                if isinstance(identifier, str) and identifier:
                    folder = entry.get("folder") if isinstance(entry, dict) else None
                    selector = identifier
                    if uuid_counts.get(identifier) != 1:
                        if isinstance(folder, str) and folder:
                            selector = folder
                            line += " · UUID repetido; selector por carpeta"
                        else:
                            selector = None
                            line += " · Aviso: UUID repetido sin carpeta, selector ambiguo"
                    if isinstance(entry, dict) and entry.get("missing") is True:
                        line += " · Requiere revisión del paquete ausente; no hay selector instalado seguro"
                    elif selector is not None and enabled in (True, False):
                        verb = "desactivar" if enabled is True else "activar"
                        command = f"/mc mod {verb} {json.dumps(selector, ensure_ascii=False)}"
                        line += f" · `{command}`"
                    elif selector is not None:
                        line += " · Aviso: estado desconocido; no hay comando seguro"
                else:
                    line += " · Aviso: falta ID/UUID; selector no disponible"
                lines.append(line)
                if isinstance(entry, dict) and (not kind or not version):
                    lines.append("  Aviso: tipo o versión no informados.")
                if isinstance(entry, dict) and entry.get("missing") is True:
                    lines.append("  Aviso: archivo/paquete ausente.")
                if isinstance(entry, dict) and entry.get("version_mismatch") is True:
                    lines.append("  Aviso: versión discordante.")
            installed_total = data.get("installed_total")
            if data.get("installed_truncated") is True:
                total_label = f" de {installed_total}" if isinstance(installed_total, int) else ""
                lines.append(f"Aviso: lista truncada; se muestran hasta 100 mods{total_label}.")
            elif len(visible_entries) > 100:
                lines.append(
                    f"Aviso: lista truncada; se muestran 100 de al menos {len(visible_entries)} mods."
                )
            elif len(visible_entries) == 100:
                lines.append(
                    "Aviso: se recibieron exactamente 100 elementos; el límite del puente puede haber recortado el total."
                )
        loaded = data.get("loaded", data.get("loaded_in_game"))
        if loaded is None and data.get("loaded_known") is False:
            loaded = None
        observed_count = sum(
            isinstance(item, dict) and item.get("loaded") is True for item in entries
        )
        lines.append(
            "Carga en juego: observada en los paquetes indicados; el resto sigue sin confirmar."
            if observed_count and loaded is not True
            else "Carga en juego: confirmada."
            if loaded is True
            else "Carga en juego: no confirmada."
            if loaded is False
            else "Carga en juego: desconocida (el puente no la informa)."
        )
        return "\n".join(lines)
    if action in {"enable_mod", "disable_mod"}:
        name = data.get("name") or data.get("mod") or "mod"
        changed = data.get("changed")
        verb = "Activación" if action == "enable_mod" else "Desactivación"
        result = (
            "cambió"
            if changed is True
            else "ya estaba así"
            if changed is False
            else "solicitada; cambio no informado"
        )
        restart = data.get("restart_required")
        restart_note = (
            "Requiere /mc reiniciar para aplicarse; el reinicio desconecta jugadores."
            if restart is True or (restart is not False and changed is True)
            else "Sin cambio nuevo; si había cambios pendientes, usa /mc reiniciar."
        )
        affected = data.get("affected", [])
        group_note = ""
        if isinstance(affected, list) and len(affected) > 1:
            group_note = (
                " Conjunto de dependencias mutuas: "
                + ", ".join(
                    str(pack.get("name", "paquete"))[:128]
                    + " ("
                    + str(pack.get("pack_type", ""))
                    + ")"
                    for pack in affected
                    if isinstance(pack, dict)
                )
                + "."
            )
        return f"{verb} de {str(name)[:160]}: {result}.{group_note} {restart_note} Carga en juego no confirmada."
    if action == "restart":
        return "El puente confirmó la solicitud de reinicio del servidor. Esto confirma solo la aceptación del puente; no la disponibilidad posterior ni la carga de mods."
    if action == "status":
        if data.get("game_status") == "failed":
            return "Minecraft: fallo del juego durante el arranque. El contenedor puede seguir activo; requiere revisión."
        if data.get("game_status") == "starting":
            return "Minecraft: el contenedor está activo, pero el juego todavía no confirmó su arranque."
        return (
            "Minecraft: "
            + (
                "en línea"
                if data.get("online") is True
                else "apagado"
                if data.get("online") is False
                else "estado desconocido"
            )
            + "."
        )
    return "Minecraft " + action + ":\n" + json.dumps(data, ensure_ascii=False)[:5000]


async def run(job, directory, manager):
    from ..jobs import EngineOutput

    backend = manager.minecraft()
    action = job["operation"].split(".")[-1]
    mutating = action not in READS
    dispatched = False
    state = "failed"
    try:
        if backend is None or backend.server_id != job["arguments"]["server_id"]:
            raise ValueError("minecraft_configuration_changed")
        if mutating:
            clean = backend.validate_change(action, job["arguments"]["params"])
            manager.mark_provider(job)
            with manager.store.transaction() as db:
                if not manager.current(job):
                    raise ValueError("job_retired")
                changed = db.execute(
                    "UPDATE external_operations SET state='sending' WHERE receipt_id=? AND state='reserved'",
                    (job["id"],),
                ).rowcount
                if changed != 1:
                    raise ValueError("operation_retired")
            dispatched = True
            data = await backend.change_validated(action, clean)
        else:
            data = await backend.query(action)
        if not isinstance(data, dict) or not isinstance(data.get("status"), str):
            raise ValueError("minecraft_invalid_response")
        status = data["status"]
        state = (
            "completed"
            if status in ("ok", "completed", "accepted", "online", "offline", "unknown")
            else "failed"
            if data.get("dispatched") is False
            else "uncertain"
            if mutating
            else "failed"
        )
        safe = public(data)
        if action == "mods":
            installed = data.get("installed", [])
            custom = [
                pack
                for pack in installed
                if not str(pack.get("name", "")).startswith("resourcePack.")
            ]
            safe["installed"] = public(custom)
            safe["base_pack_count"] = len(installed) - len(custom)
            safe["installed_total"] = len(custom)
            safe["installed_truncated"] = len(custom) > len(safe["installed"])
        if status == "needs_input" and data.get("dispatched") is False:
            messages = {
                "pack_not_unique_or_installed": "No encuentro un paquete único con ese nombre. Consulta /mc mods y usa el identificador o la carpeta exacta; comportamiento y recursos pueden compartir nombre.",
                "pack_dependency_not_configured": "Falta configurar una dependencia del paquete. Activa primero sus paquetes requeridos; no cambié la configuración.",
                "pack_version_conflict": "La versión configurada difiere de la instalada. Revisa /mc mods antes de cambiarla; no cambié la configuración.",
                "pack_required_by_configured": "Otro paquete configurado necesita este paquete. Desactiva primero el dependiente; no cambié la configuración.",
                "duplicate_installed_pack": "Hay copias instaladas indistinguibles del paquete. Revisa sus carpetas antes de cambiarlo; no cambié la configuración.",
                "duplicate_configured_pack": "El paquete aparece repetido en la configuración y necesita revisión; no cambié la configuración.",
            }
            result = Result(
                "needs_input",
                "minecraft_change_rejected",
                messages.get(
                    data.get("code"),
                    data.get("message", "El cambio necesita revisión; no se ejecutó."),
                ),
                {"action": action, "response": safe},
            )
        else:
            result = Result(
                "ok" if state == "completed" else "uncertain" if state == "uncertain" else "failed",
                "minecraft_" + state,
                render(safe, action)
                if state == "completed"
                else "Minecraft: resultado " + state + ". No se repetirá automáticamente.",
                {"action": action, "response": safe},
            )
    except BaseException as exc:
        state = "uncertain" if mutating and dispatched else "failed"
        result = Result(
            "uncertain" if state == "uncertain" else "failed",
            "minecraft_" + state,
            "No pude confirmar la operación Minecraft. No la repetiré automáticamente.",
        )
        if not isinstance(exc, Exception):
            with manager.store.transaction() as db:
                db.execute(
                    "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
                    (state, result.to_json(), job["id"]),
                )
            raise
    if mutating:
        with manager.store.transaction() as db:
            db.execute(
                "UPDATE external_operations SET state=?,result_json=? WHERE receipt_id=?",
                (state, result.to_json(), job["id"]),
            )
    return EngineOutput(result)
