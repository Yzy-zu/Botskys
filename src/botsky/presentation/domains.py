"""Presentadores de hechos propios. No parsear texto final ni datos como Markdown."""

import unicodedata
from dataclasses import replace
from datetime import datetime
from pathlib import PurePath
from zoneinfo import ZoneInfo

from . import Block, Document
from .table import NativeTable

STATES = {
    "pending": "pendiente",
    "emitted": "aviso emitido",
    "sent": "aceptado por el servicio",
    "completed": "completada",
    "deleted": "borrada",
    "archived": "archivado",
    "expired": "vencido",
    "uncertain": "incierto",
    "failed": "fallido",
    "cancelled": "cancelado",
    "accepted": "aceptado por el servicio",
    "sending": "enviando",
    "draft": "borrador",
    "scheduled": "programada",
    "open": "abierta",
    "closed": "cerrada",
    "partial": "parcial",
}


def date_time(value, zone):
    return (
        datetime.fromtimestamp(value / 1000, ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M:%S")
        + " · "
        + zone
    )


def size(value, *, decimal=False):
    if type(value) is not int or value < 0:
        return "Desconocido"
    base = 1000 if decimal else 1024
    units = ("B", "kB", "MB", "GB", "TB") if decimal else ("B", "KiB", "MiB", "GiB", "TiB")
    scaled = float(value)
    for unit in units:
        if scaled < base or unit == units[-1]:
            return f"{scaled:.2f} {unit} ({value} bytes)" if unit != "B" else f"{value} B"
        scaled /= base


def filename(name, extension):
    name = str(name or "Botsky").replace("\\", "/").split("/")[-1]
    name = "".join(c for c in name if unicodedata.category(c)[0] != "C" and c not in '<>:"|?*')
    stem = PurePath(name).stem.strip(" .")[:100] or "Botsky"
    return stem + "." + extension


def tabular(result, title, headers, rows, *, intro="", footer=""):
    if not rows:
        return result
    try:
        tables = [
            NativeTable(
                title, tuple(headers), tuple(tuple(str(c) for c in row) for row in rows[i : i + 20])
            )
            for i in range(0, len(rows), 20)
        ]
    except ValueError:
        # Mantener TODOS los campos aunque una celda no pueda ir en tabla.
        text = "\n\n".join(
            filter(
                None,
                [
                    intro,
                    title,
                    *[
                        "\n".join(
                            f"{label}: {value}" for label, value in zip(headers, row, strict=True)
                        )
                        for row in rows
                    ],
                    footer,
                ],
            )
        )
        return replace(result, text=text)
    text = "\n\n".join(filter(None, [intro, *(table.fallback() for table in tables), footer]))
    return replace(
        result,
        text=text,
        data={
            **result.data,
            "native_tables": [t.payload() for t in tables],
            "native_intro": intro,
            "native_footer": footer,
        },
    )


def present(result, *, zone="America/Mexico_City"):
    data, code = result.data, result.code
    if code == "organization_list" and data.get("list_kind") in (
        "reminders",
        "school_tasks",
        "memories",
    ):
        rows = data.get("items", [])
        footer = f"Página {data['page']}/{data['pages']} · {data['total']} registros."
        if data["page"] < data["pages"]:
            commands = {
                "memories": "/mem listar",
                "reminders": "/recordatorios",
                "school_tasks": "/tareas",
            }
            footer += "\n" + commands[data["list_kind"]] + f" --pagina {data['page'] + 1}"
        if data.get("list_kind") == "reminders":
            return tabular(
                result,
                "Recordatorios",
                ("Ref.", "Fecha", "Estado", "Texto"),
                [
                    (
                        r["id"],
                        date_time(r["due_ms"], zone),
                        STATES.get(r["state"], r["state"]),
                        r["text"],
                    )
                    for r in rows
                ],
                footer=footer,
            )
        if data.get("list_kind") == "school_tasks":
            return tabular(
                result,
                "Tareas",
                ("Ref.", "Estado", "Entrega", "Tarea"),
                [
                    (
                        r["id"],
                        STATES.get(r["state"], r["state"]),
                        r["due_date"]
                        + " "
                        + (r["due_time"] or "(sin hora definida)")
                        + " · "
                        + zone,
                        (r["subject"] + " · " if r["subject"] else "")
                        + r["text"]
                        + (f"\n/tarea archivo {r['id']}" if r["artifact_id"] else ""),
                    )
                    for r in rows
                ],
                footer=footer,
            )
        if data.get("list_kind") == "memories":
            return replace(
                result,
                text=Document(
                    (
                        Block("heading", "Memoria"),
                        Block(
                            "paragraph",
                            "\n\n".join(f"Ref. {r['id']} · {r['kind']}\n{r['text']}" for r in rows),
                        ),
                        Block("notice", footer),
                    )
                ).text(),
            )
    if code == "school_schedule":
        days = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
        return tabular(
            result,
            "Horario",
            ("Ref.", "Día", "Horario", "Materia"),
            [
                (
                    r["id"],
                    days[r["weekday"] - 1],
                    r["start_time"] + "–" + r["end_time"],
                    r["subject"],
                )
                for r in data["items"]
            ],
            footer="Zona: " + zone,
        )
    if code == "poll_results" and "question" in data and "state" in data:
        return tabular(
            result,
            "Resultados de encuesta",
            ("Opción", "Respuesta", "Votos"),
            [(r["choice"], r["text"], r["votes"]) for r in data["options"]],
            intro=data["question"],
            footer=f"{data['participants']} participantes · {STATES.get(data['state'], data['state'])} · Encuesta {data['poll_id']}",
        )
    if code == "drive_capacity":
        labels = {
            "limit": "Capacidad",
            "usage": "Usado",
            "usageInDrive": "Usado en Drive",
            "usageInDriveTrash": "Papelera de Drive",
        }
        quota = data["quota"]
        rows = [(labels.get(k, k), size(v, decimal=True)) for k, v in quota.items()]
        if (
            type(quota.get("limit")) is int
            and type(quota.get("usage")) is int
            and quota["limit"] >= quota["usage"]
        ):
            rows.append(("Disponible", size(quota["limit"] - quota["usage"], decimal=True)))
        return tabular(
            result,
            "Espacio de Google",
            ("Concepto", "Espacio"),
            rows,
            footer="Cuota compartida con otros servicios de Google; no es una cuota exclusiva de Botsky.",
        )
    if code == "drive_choices":
        return tabular(
            result,
            "Archivos de Drive",
            ("Opción", "Archivo", "Tamaño"),
            [(i, r["name"], size(r.get("size"))) for i, r in enumerate(data["choices"], 1)],
            footer="Lista de tu ámbito · disponible durante 5 minutos.\n/drive elegir NUMERO",
        )
    if code == "notes_found":
        rows = data["items"]
        blocks = [
            Block("heading", "Notas"),
            Block("paragraph", f"{data['total']} notas · Página {data['page']}/{data['pages']}"),
        ]
        for row in rows:
            blocks.extend(
                (Block("paragraph", f"Nota {row['id']}"), Block("paragraph", row["text"]))
            )
        if data["page"] < data["pages"]:
            blocks.append(Block("next_action", f"/notas --pagina {data['page'] + 1}"))
        return replace(result, text=Document(tuple(blocks)).text())
    if code in ("image_read", "transcript_ready"):
        label = "Lectura de imagen" if code == "image_read" else "Transcripción literal"
        return replace(
            result, text=Document((Block("heading", label), Block("literal", result.text))).text()
        )
    if code == "xp_top":
        return tabular(
            result,
            "Top de XP",
            ("Puesto", "Cuenta", "XP", "Nivel"),
            [
                (
                    i,
                    ("Tú" if r["self"] else "Jugador") + f" · #{r['account_id']}",
                    r["balance"],
                    r["level"],
                )
                for i, r in enumerate(data["items"], 1)
            ],
            footer="Saldo global de Botsky, compartido entre tus chats. No incluye apuestas reservadas.",
        )
    if code == "xp_balance":
        return replace(
            result,
            text=Document(
                (
                    Block("heading", "Tu saldo"),
                    Block(
                        "paragraph",
                        f"Disponible: {data['balance']} XP\nReservado: {data['reserved']} XP\nNivel: {data['level']}\nCuenta #{data['account_id']}",
                    ),
                    Block("notice", "Cuenta compartida entre tus chats de Botsky."),
                )
            ).text(),
        )
    if code in ("daily_cooldown", "daily_awarded"):
        return replace(
            result, text=result.text + "\nPróximo daily: " + date_time(data["retry_at_ms"], zone)
        )
    if code == "message_status":
        lines = [STATES.get(data["state"], data["state"])]
        lines += [
            p["contact_name"]
            + " · "
            + ("Texto" if p["kind"] == "text" else "Archivo")
            + ": "
            + STATES.get(p["state"], p["state"])
            for p in data["parts"]
        ]
        lines.append(
            "Aceptado por el servicio no acredita lectura. Si una parte es incierta, revisa antes de repetir."
        )
        return replace(
            result,
            text=Document(
                (Block("heading", "Estado del recado"), Block("paragraph", "\n".join(lines)))
            ).text(),
        )
    if code == "blackjack_board" and "dealer_visible" in data:
        identifier = data["game_id"]
        states = {
            "lobby": "Esperando jugadores",
            "playing": "En juego",
            "stood": "se plantó",
            "busted": "se pasó",
            "blackjack": "blackjack",
        }
        lines = [
            f"Mesa {identifier} · {states.get(data['state'], data['state'])}",
            f"Apuesta: {data['bet']} XP por persona",
        ]
        if data["dealer_visible"]:
            card = data["dealer_visible"][0]
            lines.append("Crupier: " + card["rank"] + card["suit"] + " · carta oculta")
        for player in data["players"]:
            lines.append(
                f"Asiento {player['seat']} · "
                + " ".join(c["rank"] + c["suit"] for c in player["hand"])
                + f" · {player['score']} puntos · "
                + states.get(player["state"], player["state"])
            )
        if data["state"] == "lobby":
            lines.append(f"/bj entrar {identifier}\n/bj repartir {identifier}")
        else:
            lines.append(
                f"Turno: asiento {data['turn']}\n/bj pedir {identifier}\n/bj plantarse {identifier}\n/bj doblar {identifier}"
            )
        return replace(
            result,
            text=Document(
                (Block("heading", "Blackjack"), Block("paragraph", "\n\n".join(lines)))
            ).text(),
        )
    if code == "blackjack_settled":
        from ..domains.blackjack import score

        lines = ["Crupier: " + str(score(data["dealer"])) + " puntos"]
        for player in data["players"]:
            lines.append(
                f"Asiento {player['seat']} · {player['outcome']} · {player['score']} puntos\n"
                f"Apuesta: {player['bet']} XP · pago bruto: {player['payout']} XP · resultado neto: {player['payout'] - player['bet']:+d} XP"
            )
        return replace(
            result,
            text=Document(
                (Block("heading", "Blackjack · final"), Block("paragraph", "\n\n".join(lines)))
            ).text(),
        )
    if code == "pack_catalog":
        return tabular(
            result,
            "Packs publicados",
            ("Categoría", "Referencia", "Fotos"),
            [(r["name"], r["category"], r["count"]) for r in data["items"]],
            footer="150 XP · hora feliz 75 XP. Entrega privada bajo oferta y confirmación vigentes.\nEl stock 0 indica que no hay fotos disponibles."
            + (f"\nPágina {data['page']}/{data['pages']}" if "page" in data else "")
            + (
                f"\n/pack catalogo --pagina {data['page'] + 1}"
                if data.get("page", 1) < data["pages"]
                else ""
            ),
        )
    if code == "coop_status" and "category" in data:
        lines = [
            f"Categoría: {data['category']}",
            f"Estado: {STATES.get(data['state'], data['state'])}",
            f"Avance: {data['total']}/{data['target']} XP",
            f"Devuelto: {data['refund']} XP",
        ]
        if data.get("expires_ms"):
            lines.append("Vence: " + date_time(data["expires_ms"], zone))
        if data["state"] == "open":
            lines.append(f"/coop aportar {data['challenge_id']} CANTIDAD")
        return replace(
            result,
            text=Document(
                (Block("heading", "Cooperacha"), Block("paragraph", "\n".join(lines)))
            ).text(),
        )
    if code == "happy_status":
        lines = [STATES.get(data["state"], data["state"])]
        if data.get("expires_ms"):
            lines.append("Vence: " + date_time(data["expires_ms"], zone))
        drop = data.get("drop")
        if drop:
            lines.append("AirDrop: " + STATES.get(drop["state"], drop["state"]))
            if drop["state"] == "open":
                lines.append("/hh reclamar " + drop["id"])
        return replace(
            result,
            text=Document(
                (Block("heading", "Hora feliz"), Block("paragraph", "\n".join(lines)))
            ).text(),
        )
    if code == "minecraft_completed" and data.get("action") == "mods":
        response = data["response"]
        installed = response.get("installed")
        if isinstance(installed, list):
            rows = []
            for pack in installed:
                if not isinstance(pack, dict):
                    continue
                version = pack.get("version")
                version = (
                    ".".join(str(v) for v in version)
                    if isinstance(version, list)
                    else str(version or "Desconocida")
                )
                configured = pack.get("enabled", pack.get("configured", pack.get("active")))
                rows.append(
                    (
                        str(pack.get("name") or "(sin nombre)")
                        + " · "
                        + str(pack.get("pack_type") or pack.get("type") or "tipo desconocido"),
                        version,
                        "Sí"
                        if configured is True
                        else "No"
                        if configured is False
                        else "Desconocido",
                        "Observada"
                        if pack.get("loaded") is True
                        else "No confirmada"
                        if pack.get("loaded") is False
                        else "Desconocida",
                    )
                )
            return tabular(
                result,
                "Paquetes del servidor",
                ("Paquete", "Versión", "Configurado", "Carga"),
                rows,
                footer="Detalles, advertencias y comandos verificados:\n" + result.text,
            )
    if code in ("agenda_list", "agenda_create", "agenda_update", "agenda_cancel"):
        schedules = data.get("schedules") if code == "agenda_list" else [data.get("schedule")]
        if isinstance(schedules, list) and all(
            isinstance(item, dict) and type(item.get("dueAt")) is int for item in schedules
        ):
            return tabular(
                result,
                "Agenda de llamadas",
                ("Referencia", "Fecha", "Modo y duración", "Estado"),
                [
                    (
                        item["id"],
                        date_time(item["dueAt"], item.get("timeZone") or zone),
                        (
                            "En vivo"
                            if item.get("live") is True
                            else "Audio preparado"
                            if item.get("live") is False
                            else "Modo no informado"
                        )
                        + (
                            " · " + str(item["maxSeconds"]) + " s"
                            if type(item.get("maxSeconds")) is int
                            else " · duración no informada"
                        ),
                        STATES.get(item["state"], item["state"]),
                    )
                    for item in schedules
                ],
                footer="La programación no acredita una llamada conectada ni recepción humana.",
            )
    if code == "call_status":
        states = {
            "preparing": "Preparando",
            "dialing": "Marcando",
            "ringing": "Esperando respuesta",
            "connected": "Conectada según el servicio",
            "ending": "Terminando",
            "ended": "Terminada",
            "failed": "No se pudo completar",
            "interrupted": "Interrumpida",
            "cancelled": "Cancelada",
        }
        call = data["call"]
        return replace(
            result,
            text=Document(
                (
                    Block("heading", "Llamada"),
                    Block("paragraph", states.get(call["state"], "Estado no reconocido")),
                    Block(
                        "notice", "Estado del servicio; no acredita escucha ni recepción humana."
                    ),
                )
            ).text(),
        )
    return result
