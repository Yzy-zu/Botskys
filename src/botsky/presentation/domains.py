"""Presentadores de hechos propios. No parsear texto final ni datos como Markdown."""

import json
import unicodedata
from dataclasses import replace
from datetime import datetime
from pathlib import PurePath
from zoneinfo import ZoneInfo

from . import Block, Document, attach_document
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
    "preparing": "preparando",
    "publishing": "publicando",
    "offered": "oferta pendiente",
    "ready": "preparado",
    "claimed": "reclamado",
    "active": "activo",
    "lobby": "esperando participantes",
    "playing": "en juego",
    "settled": "liquidado",
    "skipped": "omitido",
    "revoked": "retirado",
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
        return attach_document(
            result,
            Document(
                (
                    Block("heading", title),
                    Block("paragraph", intro),
                    Block("notice", "No hay elementos registrados para mostrar."),
                    Block("notice", footer),
                )
            ),
        )
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


def present(result, *, zone="America/Mexico_City", input_mode="command"):
    data, code = result.data, result.code
    from .community import present as present_community

    result = present_community(result, zone)
    data = result.data
    if data.get("document") or data.get("native_tables"):
        return result
    from .audiovisual import present_audiovisual

    result = present_audiovisual(result, zone)
    data = result.data
    if data.get("document") or data.get("native_tables"):
        return result
    if code in ("school_task_completed", "school_task_deleted"):
        text = "completada" if code == "school_task_completed" else "borrada"
        return attach_document(
            result,
            Document(
                (Block("notice", f"Tarea #{data.get('task_id', '')} marcada como {text}."),)
            ),
        )
    if code in ("reminder_cancelled", "reminder_archived") and "state" in data:
        return attach_document(
            result,
            Document(
                (
                    Block(
                        "notice",
                        f"Recordatorio {data['reminder_id']} · {STATES.get(data['state'], data['state'])}.",
                    ),
                )
            ),
        )
    if code == "attachment_required" and "expires_ms" in data:
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Falta el archivo"),
                    Block(
                        "notice",
                        "Adjunta el archivo aquí o responde al mensaje exacto que lo contiene.",
                    ),
                    Block(
                        "notice", "Espera disponible hasta: " + date_time(data["expires_ms"], zone)
                    ),
                    Block("paragraph", "Ejemplo: " + data.get("example", "/ayuda")),
                )
            ),
        )
    if code == "reminder_created" and "text" in data:
        return attach_document(
            result,
            Document(
                (
                    Block("heading", f"Recordatorio {data['reminder_id']} guardado"),
                    Block("paragraph", date_time(data["due_ms"], zone)),
                    Block("literal", data["text"]),
                    Block("notice", "Te avisaré puntualmente en la fecha programada."),
                )
            ),
        )
    if code == "school_task_created" and "due_date" in data:
        return attach_document(
            result,
            Document(
                (
                    Block("heading", f"Tarea {data['task_id']} guardada"),
                    Block(
                        "paragraph",
                        "Entrega: "
                        + data["due_date"]
                        + " "
                        + (data["due_time"] or "(sin hora definida)")
                        + " · "
                        + zone,
                    ),
                    Block("literal", data["subject"]),
                    Block("literal", data["text"]),
                )
            ),
        )
    if code in ("memory_forgotten", "memories_deleted"):
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Memoria actualizada"),
                    Block(
                        "notice",
                        result.text + " Los recuerdos de este chat han sido eliminados.",
                    ),
                )
            ),
        )
    if code in ("bot_status", "bot_mode_updated"):
        blocks = [Block("heading", "Estado de Botsky"), Block("paragraph", "Modo: " + data["mode"])]
        if data.get("paused_until_ms"):
            blocks.append(
                Block("notice", "Pausa hasta: " + date_time(data["paused_until_ms"], zone))
            )
        else:
            blocks.append(Block("notice", "Sin pausa."))
        labels = {
            "comandos": "Comandos explícitos",
            "notas": "Notas",
            "medios_locales": "Archivos locales",
            "gemini_configurado": "IA",
            "tts_configurado": "Voz",
            "asr_configurado": "Transcripción",
            "descargas_configuradas": "Descargas",
        }
        if code == "bot_status":
            blocks.append(
                Block(
                    "paragraph",
                    "Servicios configurados:\n"
                    + "\n".join(
                        labels.get(k, k) + ": " + ("configurado" if v else "sin configurar")
                        for k, v in data["capabilities"].items()
                    ),
                )
            )
        return attach_document(result, Document(tuple(blocks)))
    file_titles = {
        "document_converted": "Documento convertido",
        "media_edited": "Audio o video convertido",
        "download_ready": "Descarga preparada",
        "pdf_assembled": "PDF terminado",
        "pdf_extracted": "Páginas extraídas",
        "drive_downloaded": "Archivo de Drive",
        "task_attachment": "Archivo de tarea",
    }
    if code in file_titles and data.get("artifacts"):
        blocks = [Block("heading", file_titles[code])]
        name = data.get("title") or data.get("name")
        if name:
            blocks.append(Block("literal", name))
        for index, facts in enumerate(data.get("file_facts", ()), 1):
            lines = [
                f"Formato final: {facts.get('extension', 'desconocido').upper()}",
                size(facts.get("bytes")),
            ]
            for field, label in (
                ("pages", "Páginas"),
                ("sheets", "Hojas"),
                ("slides", "Diapositivas"),
                ("files", "Archivos"),
            ):
                if type(facts.get(field)) is int:
                    lines.append(f"{label}: {facts[field]}")
            if facts.get("duration_seconds"):
                from .search import duration

                lines.append("Duración: " + duration(facts["duration_seconds"]))
            if facts.get("status") == "unavailable" or facts.get("pages_status"):
                lines.append("Algunos metadatos complementarios no estuvieron disponibles.")
            blocks.append(Block("paragraph", " · ".join(lines)))
        blocks.append(Block("notice", result.text))
        return attach_document(result, Document(tuple(blocks)))
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
            filters = data.get("filters", {})
            if filters.get("include_closed"):
                footer += " --cerradas"
            if filters.get("kind"):
                footer += " --tipo " + filters["kind"]
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
            blocks = [Block("heading", "Memoria")]
            for row in rows:
                blocks.extend(
                    (
                        Block("paragraph", f"Ref. {row['id']} · {row['kind']}"),
                        Block("literal", row["text"]),
                    )
                )
            blocks.append(Block("notice", footer))
            return attach_document(result, Document(tuple(blocks)))
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
        result = replace(result, data={**result.data, "native_intro_literal": True})
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
            footer="Cuota compartida de tu cuenta de Google (incluye Drive, Gmail y Fotos).",
        )
    if code == "drive_choices":
        return tabular(
            result,
            "Archivos de Drive",
            ("Opción", "Archivo", "Tamaño"),
            [(i, r["name"], size(r.get("size"))) for i, r in enumerate(data["choices"], 1)],
            footer=(
                "Lista de tu ámbito · Vence: " + date_time(data["expires_ms"], zone)
                if "expires_ms" in data
                else "Lista de tu ámbito · Vigencia máxima de 5 minutos desde la preparación."
            )
            + (
                "\nUsa Responder sobre esta lista y escribe el número del archivo que quieres recuperar."
                if input_mode == "natural"
                else "\n/drive elegir NUMERO · Usa Responder sobre esta lista y escribe el número"
            ),
        )
    if code == "notes_found":
        rows = data["items"]
        blocks = [
            Block("heading", "Notas"),
            Block("paragraph", f"{data['total']} notas · Página {data['page']}/{data['pages']}"),
        ]
        for row in rows:
            blocks.extend(
                (
                    Block(
                        "paragraph",
                        f"Nota {row['id']}"
                        + (
                            (" · " + date_time(row["created_ms"], zone))
                            if "created_ms" in row
                            else ""
                        ),
                    ),
                    Block("literal", row["text"]),
                )
            )
        if data["page"] < data["pages"]:
            command = f"/notas --pagina {data['page'] + 1}"
            if data.get("query"):
                command += " -- " + data["query"]
            blocks.append(Block("next_action", command))
        return attach_document(result, Document(tuple(blocks)))
    if data.get("qr_readings") and (code == "ai_reply" or result.status == "failed"):
        blocks = []
        for reading in data["qr_readings"]:
            if reading["status"] == "decoded":
                blocks.extend(
                    (
                        Block(
                            "heading", f"Contenido QR verificado · archivo {reading['attachment']}"
                        ),
                        Block("literal", reading["text"]),
                    )
                )
                if reading.get("truncated"):
                    blocks.append(Block("notice", "Lectura truncada por límite de tamaño."))
            elif reading["status"] == "unavailable":
                blocks.append(
                    Block(
                        "notice", f"No se pudo verificar el QR del archivo {reading['attachment']}."
                    )
                )
        blocks.append(Block("heading", "Análisis de IA"))
        blocks.append(
            Block("paragraph", data.get("analysis_text", "No fue posible generar el análisis de la imagen en este momento."))
        )
        return attach_document(result, Document(tuple(blocks)))
    if code in ("transcript_summary_ready", "summary_unavailable") and "output_mode" in data:
        blocks = []
        if data["output_mode"] == "ambos":
            blocks.extend(
                (Block("heading", "Transcripción literal"), Block("literal", data["transcript"]))
            )
        if code == "transcript_summary_ready":
            blocks.extend(
                (Block("heading", "Resumen generado"), Block("paragraph", data["summary"]))
            )
        else:
            blocks.append(
                Block("notice", "Transcripción lista. El resumen breve no pudo generarse.")
            )
        return attach_document(result, Document(tuple(blocks)))
    if code in ("image_read", "transcript_ready"):
        label = (
            ("Contenido QR" if data.get("mode") == "qr" else "Texto de imagen (OCR)")
            if code == "image_read"
            else "Transcripción literal"
        )
        blocks = [Block("heading", label), Block("literal", result.text)]
        if data.get("truncated"):
            blocks.append(
                Block(
                    "notice",
                    "Texto muy extenso: se muestra la primera parte. El documento adjunto conserva el resto.",
                )
            )
        return attach_document(result, Document(tuple(blocks)))
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
            footer="Puntos XP acumulados en Botsky.",
        )
    if code == "xp_balance":
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Tu saldo"),
                    Block(
                        "paragraph",
                        f"Disponible: {data['balance']} XP\nReservado: {data['reserved']} XP\nNivel: {data['level']}\nCuenta #{data['account_id']}",
                    ),
                    Block("notice", "Cuenta compartida entre tus chats de Botsky."),
                )
            ),
        )
    if code in ("daily_cooldown", "daily_awarded"):
        return replace(
            result, text=result.text + "\nPróximo daily: " + date_time(data["retry_at_ms"], zone)
        )
    if code == "message_preview" and "content" in data:
        blocks = [
            Block("heading", "Vista previa del recado"),
            Block("paragraph", "Destinatarios verificados:"),
        ]
        blocks.extend(Block("literal", name) for name in data["recipients"])
        blocks.extend(
            (Block("paragraph", "Texto que se enviará:"), Block("literal", data["content"]))
        )
        if data.get("attachment"):
            blocks.append(
                Block(
                    "paragraph",
                    "Adjunto: "
                    + data["attachment"]["format"].upper()
                    + " · "
                    + size(data["attachment"]["bytes"]),
                )
            )
        blocks.append(
            Block(
                "notice",
                "Vence: "
                + date_time(data["expires_ms"], zone)
                + ". Al confirmar se enviará este contenido a los destinatarios mostrados.",
            )
        )
        blocks.append(Block("next_action", "/recado enviar " + data["draft_id"]))
        return attach_document(result, Document(tuple(blocks)))
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
            "Mensaje enviado al destinatario."
        )
        return attach_document(
            result,
            Document((Block("heading", "Estado del recado"), Block("paragraph", "\n".join(lines)))),
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
            lines.append('Di «entro en esta partida» o «reparte las cartas».' if input_mode == 'natural' else f"/bj entrar {identifier}\n/bj repartir {identifier}")
        else:
            lines.append(
                (f"Turno: asiento {data['turn']}. Di «pido carta», «me planto» o «doblo la apuesta»." if input_mode == 'natural' else
                 f"Turno: asiento {data['turn']}\n/bj pedir {identifier}\n/bj plantarse {identifier}\n/bj doblar {identifier}")
            )
        return attach_document(
            result,
            Document((Block("heading", "Blackjack"), Block("paragraph", "\n\n".join(lines)))),
        )
    if code == "blackjack_settled":
        from ..domains.blackjack import score

        lines = ["Crupier: " + str(score(data["dealer"])) + " puntos"]
        for player in data["players"]:
            lines.append(
                f"Asiento {player['seat']} · {player['outcome']} · {player['score']} puntos\n"
                f"Apuesta: {player['bet']} XP · pago bruto: {player['payout']} XP · resultado neto: {player['payout'] - player['bet']:+d} XP"
            )
        return attach_document(
            result,
            Document(
                (Block("heading", "Blackjack · final"), Block("paragraph", "\n\n".join(lines)))
            ),
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
                ("\nDi «siguiente página del catálogo»." if input_mode == 'natural' else
                 f"\n/pack catalogo --pagina {data['page'] + 1}"
                 + (" --categoria " + json.dumps(data["category_filter"], ensure_ascii=False) if data.get("category_filter") else ""))
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
        return attach_document(
            result, Document((Block("heading", "Cooperacha"), Block("paragraph", "\n".join(lines))))
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
        return attach_document(
            result, Document((Block("heading", "Hora feliz"), Block("paragraph", "\n".join(lines))))
        )
    if code == "minecraft_completed" and data.get("action") in (
        "config",
        "worlds",
        "backup",
        "players",
        "status",
        "diagnostics",
        "start",
        "stop",
    ):
        from .minecraft import present_minecraft

        return present_minecraft(result)
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
                        date_time(item["dueAt"], zone),
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
                footer="Recordatorio de llamada programada.",
            )
    return result
