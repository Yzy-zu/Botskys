"""Entrada de laboratorio de operador local. No endpoint remoto ni identidad WhatsApp."""

import re
import time

from ..contracts import DeliveryAck, Incoming, Scope


def clock_ms():
    return time.time_ns() // 1000000


class LocalAdapter:
    def __init__(self, settings, clock=clock_ms):
        self.settings, self.clock = settings, clock

    def incoming(
        self,
        message_id,
        actor,
        chat,
        text,
        *,
        source_ms=None,
        is_group=False,
        historical=False,
        attachments=(),
        quoted_message_id=None,
        mentioned_ids=(),
    ):
        if any(
            not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,128}", v)
            for v in (message_id, actor, chat)
        ):
            raise ValueError("identificador local inválido")
        if not isinstance(text, str) or len(text) > 64000:
            raise ValueError("texto local inválido")
        if type(is_group) is not bool or type(historical) is not bool:
            raise ValueError("metadatos locales inválidos")
        if (
            not isinstance(mentioned_ids, tuple)
            or len(mentioned_ids) > 32
            or any(
                not isinstance(m, str) or not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,128}", m)
                for m in mentioned_ids
            )
        ):
            raise ValueError("menciones locales inválidas")
        if (
            not isinstance(attachments, tuple)
            or len(attachments) > 20
            or len(set(attachments)) != len(attachments)
            or any(
                not isinstance(a, str) or not re.fullmatch(r"[a-f0-9]{32}", a) for a in attachments
            )
        ):
            raise ValueError("referencias de adjuntos locales inválidas")
        if quoted_message_id is not None and (
            not isinstance(quoted_message_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,128}", quoted_message_id)
        ):
            raise ValueError("cita local inválida")
        now = self.clock()
        source_ms = now if source_ms is None else source_ms
        if type(source_ms) is not int or source_ms <= 0:
            raise ValueError("timestamp de origen inválido")
        return Incoming(
            self.settings.instance,
            self.settings.account,
            message_id,
            Scope(actor, chat, is_group),
            text,
            source_ms,
            now,
            historical=historical,
            attachments=attachments,
            quoted_message_id=quoted_message_id,
            mentioned_ids=mentioned_ids,
        )


class CollectingTransport:
    """Doble local: aceptación en memoria, nunca recepción humana."""

    def __init__(self):
        self.parts = []

    def send(self, part):
        self.parts.append(part)
        return DeliveryAck(True, f"local-{part.receipt_id}-{part.position}")
