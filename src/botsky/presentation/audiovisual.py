"""Estados de la sesión observada, sin comandos inferidos desde mensajes."""

import math

from . import Block, Document, attach_document
from .search import duration

REASONS = {
    "audio_completed": "Terminó el audio preparado",
    "remote_rejected": "Llamada rechazada",
    "not_answered": "No se contestó",
    "answer_timeout": "Se agotó la espera de respuesta",
    "requested": "Terminada a petición del usuario",
    "cancelled": "Cancelada",
    "duration_limit": "Se alcanzó la duración permitida",
    "audience_empty": "Sin oyentes",
    "remote_left": "La otra persona salió",
    "service_restart": "Servicio reiniciado",
    "service_shutdown": "Servicio detenido",
    "recovery_exhausted": "Recuperación agotada",
    "recovery_timeout": "La conexión no se recuperó a tiempo",
    "live_failed": "Conversación en vivo interrumpida",
    "remote_or_native_end": "WhatsApp informó el fin de la llamada",
}


def present_audiovisual(result, zone):
    from .domains import date_time

    data, code = result.data, result.code
    if code == "call_status":
        states = {
            "starting": "Preparando",
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
        blocks = [
            Block("heading", "Llamada"),
            Block("paragraph", states.get(call["state"], "Estado no reconocido")),
        ]
        connected, ended = call.get("connectedAt"), call.get("endedAt")
        if type(connected) is int and connected > 0:
            blocks.append(Block("paragraph", "Conectada desde: " + date_time(connected, zone)))
            if type(ended) is int and ended >= connected:
                blocks.append(
                    Block(
                        "paragraph", "Duración observada: " + duration((ended - connected) / 1000)
                    )
                )
        if call.get("reason"):
            blocks.append(
                Block(
                    "notice",
                    REASONS.get(call["reason"], "El servicio no informó un motivo reconocible."),
                )
            )
        blocks.append(
            Block("notice", "Estado del servicio; no acredita escucha ni recepción humana.")
        )
        return attach_document(result, Document(tuple(blocks)))
    if code not in ("av_control_applied", "av_control_unconfirmed"):
        return result
    if "clips" in data:
        blocks = [Block("heading", "Clips disponibles")]
        for i, clip in enumerate(data["clips"], 1):
            blocks.extend(
                (
                    Block("literal", f"{i}. {clip['name']}"),
                    Block("next_action", "/clip poner " + clip["id"]),
                )
            )
        if not data["clips"]:
            blocks.append(Block("notice", "El catálogo está vacío."))
        return attach_document(result, Document(tuple(blocks)))
    if data.get("presentation_family") == "clip":
        blocks = [Block("heading", "Clip")]
        clip = data.get("clip")
        if isinstance(clip, dict):
            if isinstance(clip.get("name"), str):
                blocks.append(Block("literal", clip["name"]))
            states = {
                "playing": "Reproduciendo",
                "paused": "En pausa",
                "resuming": "Reanudando",
                "ended": "Terminado",
                "stopped": "Detenido",
                "failed": "No disponible",
                "loading": "Preparando",
            }
            if clip.get("state"):
                blocks.append(
                    Block(
                        "paragraph",
                        "Estado del servicio: " + states.get(clip["state"], "Desconocido"),
                    )
                )
            volume = clip.get("volume")
            if (
                data.get("success") is True
                and type(volume) in (float, int)
                and math.isfinite(volume)
                and 0 <= volume <= 1
            ):
                qualifier = (
                    "Volumen para el siguiente clip"
                    if clip.get("state") in ("ended", "stopped", "failed")
                    else "Volumen aplicado"
                )
                blocks.append(Block("paragraph", qualifier + f": {round(volume * 100)} %"))
        blocks.append(Block("notice", result.text))
        return attach_document(result, Document(tuple(blocks)))
    if data.get("presentation_family") == "avatar":
        return attach_document(
            result, Document((Block("heading", "Avatar"), Block("notice", result.text)))
        )
    return result
