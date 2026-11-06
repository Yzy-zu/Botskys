"""Normalización técnica adaptada de Zhana inbox; ninguna interpretación de órdenes."""

import re
from typing import Any

from ..contracts import Incoming, Scope


def _invalid() -> ValueError:
    return ValueError("Invalid Evolution event")


def _declared_size(value: Any) -> int | None:
    """Untrusted wire-size hint: only used to reject early, never to allow bytes."""
    if isinstance(value, dict):
        low, high = value.get("low"), value.get("high")
        if (
            type(low) is not int
            or type(high) is not int
            or not -(2**31) <= low < 2**32
            or not 0 <= high < 2**32
        ):
            return None
        value = (high << 32) | (low & 0xFFFFFFFF)
    elif isinstance(value, str):
        if not value.isascii() or not value.isdecimal() or len(value) > 20:
            return None
        value = int(value)
    return value if type(value) is int and 0 <= value < 2**64 else None


def _jid(value: object, *, phone_only: bool = False) -> str:
    if not isinstance(value, str) or len(value) > 256:
        raise _invalid()
    match = re.fullmatch(r"([^\s:@]+)(?::([0-9]+))?@(s\.whatsapp\.net|lid)", value, re.ASCII)
    if not match or (
        phone_only and (match.group(3) != "s.whatsapp.net" or not match.group(1).isdigit())
    ):
        raise _invalid()
    local, domain = match.group(1), match.group(3)
    if (
        domain == "s.whatsapp.net"
        and len(local) == 13
        and local.startswith("521")
        and local.isascii()
        and local.isdigit()
    ):
        local = "52" + local[3:]
    return f"{local}@{domain}"


def _alternate_jid(value: object) -> str:
    jid = _jid(value)
    return _jid(value, phone_only=True) if jid.endswith("@s.whatsapp.net") else jid


def _timestamp(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise _invalid()
    if isinstance(value, str) and (not value.isascii() or not value.isdigit()):
        raise _invalid()
    number = int(value)
    if 1_000_000_000 <= number < 10_000_000_000:
        return number * 1000
    if 1_000_000_000_000 <= number < 10_000_000_000_000:
        return number
    raise _invalid()


def _content(message: object) -> tuple[str, dict[str, Any], str | None] | None:
    if not isinstance(message, dict):
        raise _invalid()
    current = message
    wrappers = (
        "ephemeralMessage",
        "viewOnceMessage",
        "viewOnceMessageV2",
        "viewOnceMessageV2Extension",
        "documentWithCaptionMessage",
    )
    for _ in range(8):
        present = [name for name in wrappers if name in current]
        if not present:
            break
        if len(present) != 1 or any(
            key in current
            for key in (
                "conversation",
                "extendedTextMessage",
                "imageMessage",
                "audioMessage",
                "videoMessage",
                "documentMessage",
                "stickerMessage",
                "reactionMessage",
            )
        ):
            raise _invalid()
        wrapper = current[present[0]]
        if not isinstance(wrapper, dict) or not isinstance(wrapper.get("message"), dict):
            raise _invalid()
        current = wrapper["message"]
    else:
        if any(name in current for name in wrappers):
            raise _invalid()
    kinds = {
        "imageMessage": "image",
        "audioMessage": "audio",
        "videoMessage": "video",
        "documentMessage": "document",
        "stickerMessage": "sticker",
    }
    present = [
        name
        for name in ("conversation", "extendedTextMessage", "reactionMessage", *kinds)
        if name in current
    ]
    if len(present) > 1:
        raise _invalid()
    if not present:
        return None
    name = present[0]
    if name == "reactionMessage":
        body = current[name]
        if not isinstance(body, dict):
            raise _invalid()
        return "", body, "reaction"
    if name == "conversation":
        text, body, kind = current[name], {}, None
    else:
        body = current[name]
        if not isinstance(body, dict):
            raise _invalid()
        kind = kinds.get(name)
        text = body.get("text" if name == "extendedTextMessage" else "caption", "")
    if text is None and name != "conversation":
        text = ""
    if not isinstance(text, str) or len(text) > 8000:
        raise _invalid()
    if not text.strip() and kind is None:
        return None
    return text, body, kind


def _context(body: dict[str, Any]) -> tuple[str | None, tuple[str, ...], str | None, str | None]:
    context = body.get("contextInfo", {})
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise _invalid()
    quote = context.get("stanzaId")
    if quote is not None and (not isinstance(quote, str) or not quote.strip() or len(quote) > 256):
        raise _invalid()
    mentions = context.get("mentionedJid", [])
    if mentions is None:
        mentions = []
    if not isinstance(mentions, list) or len(mentions) > 32:
        raise _invalid()
    actor = context.get("participant")
    quoted = context.get("quotedMessage")
    quoted_text = None
    if quoted is not None:
        result = _content(quoted)
        if result is not None:
            quoted_text = result[0] or None
    return (
        quote,
        tuple(_jid(item) for item in mentions),
        _jid(actor) if actor is not None else None,
        quoted_text,
    )


def normalize(payload, settings, provider_instance, now):
    if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
        raise _invalid()
    if payload["event"].lower().replace("_", ".") != "messages.upsert":
        return None
    if payload.get("instance") != provider_instance:
        raise _invalid()
    # Token secreto + instancia configurada identifican la cuenta del webhook.
    # Si el proveedor también declara sender, debe coincidir con la cuenta fijada.
    if (
        payload.get("sender") is not None
        and _jid(payload["sender"], phone_only=True) != settings.account
    ):
        raise _invalid()
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("key"), dict):
        raise _invalid()
    key = data["key"]
    if type(key.get("fromMe")) is not bool:
        raise _invalid()
    if key["fromMe"]:
        return None
    chat, identifier = key.get("remoteJid"), key.get("id")
    if (
        not isinstance(chat, str)
        or len(chat) > 256
        or not isinstance(identifier, str)
        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", identifier)
    ):
        raise _invalid()
    group = chat.endswith("@g.us")
    if group:
        if not re.fullmatch(r"[0-9]+(?:-[0-9]+)?@g\.us", chat, re.ASCII):
            raise _invalid()
        primary, fields = key.get("participant"), ("participantAlt", "participantPn")
    else:
        primary, fields = chat, ("remoteJidAlt", "remoteJidPn")
    candidates = {_jid(primary)} if primary is not None else set()
    for name in fields:
        if key.get(name) is not None:
            candidates.add(_jid(key[name], phone_only=name.endswith("Pn")))
    phones = {v for v in candidates if v.endswith("@s.whatsapp.net")}
    lids = {v for v in candidates if v.endswith("@lid")}
    if len(phones) > 1 or len(lids) > 1 or not candidates:
        raise _invalid()
    actor = next(iter(phones or lids))
    if not group:
        chat = actor
    content = _content(data.get("message"))
    if content is None or content[2] == "reaction":
        return None
    text, body, kind = content
    event_context = data.get("contextInfo")
    if event_context is not None:
        nested = body.get("contextInfo") or {}
        if (
            not isinstance(event_context, dict)
            or not isinstance(nested, dict)
            or any(k in nested and nested[k] != v for k, v in event_context.items())
        ):
            raise _invalid()
        body = {**body, "contextInfo": {**event_context, **nested}}
    quote, mentions, _, _ = _context(body)
    source_ms = _timestamp(data.get("messageTimestamp"))
    if source_ms is None:
        raise _invalid()
    historical = data.get("type") in ("append", "history") or data.get("historical") is True
    incoming = Incoming(
        settings.instance,
        settings.account,
        identifier,
        Scope(actor, chat, group),
        text,
        source_ms,
        now,
        transport="evolution",
        historical=historical,
        quoted_message_id=quote,
        mentioned_ids=mentions,
    )
    # Solo material técnico del evento autenticado; jamás descargar una URL del texto.
    record = {"key": key, "message": data["message"]} if kind else None
    size = _declared_size(body.get("fileLength")) if kind else None
    return incoming, record, size
