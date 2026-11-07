"""Fichas propias: datos canónicos íntegros y previews explícitas."""

import math
from urllib.parse import urlsplit

from . import Block, Document


def duration(seconds):
    if (
        not isinstance(seconds, (float, int))
        or isinstance(seconds, bool)
        or not math.isfinite(seconds)
        or seconds <= 0
    ):
        return "Duración desconocida"
    total = max(1, round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def preview(text, limit=180):
    return text if len(text) <= limit else text[:limit] + "… [vista previa]"


def source_label(url):
    from ..engines.downloads import download_source

    labels = {
        "youtube": "YouTube",
        "pornhub": "Pornhub",
        "xnxx": "XNXX",
        "w3": "W3C",
        "vimeo": "Vimeo",
        "dailymotion": "Dailymotion",
    }
    source = download_source(url)
    return labels.get(source, source)


def video_document(choices, expires_ms, now, *, intro="Videos", short=True, view_id=""):
    blocks = [Block("heading", intro)]
    for i, choice in enumerate(choices, 1):
        blocks.append(
            Block(
                "literal",
                f"{i}. {preview(choice['title'])}\n"
                + duration(choice.get("duration"))
                + " · "
                + preview(choice.get("author") or "Autor desconocido", 100)
                + " · "
                + source_label(choice["url"])
                + "\n"
                + choice["url"],
            )
        )
    seconds = max(0, (expires_ms - now) // 1000)
    minutes, remaining = divmod(seconds, 60)
    blocks.append(
        Block(
            "notice",
            f"Lista disponible durante {minutes}:{remaining:02d}. Opciones 1–{len(choices)}.",
        )
    )
    if any(
        len(choice["title"]) > 180 or len(choice.get("author") or "") > 100 for choice in choices
    ):
        blocks.append(Block("next_action", "Título y autor completos: /dl detalle NUMERO"))
    command = "/dl elegir " + ("" if short else view_id + " ")
    blocks.append(Block("next_action", command + "NUMERO"))
    return Document(tuple(blocks))


def videos(choices, expires_ms, now, **kwargs):
    return video_document(choices, expires_ms, now, **kwargs).text()


def web_document(items, query):
    if not items:
        return Document(
            (
                Block(
                    "notice",
                    "No encontré resultados que cumplan los términos y las fuentes solicitadas.",
                ),
            )
        )
    blocks = [Block("heading", "Resultados de búsqueda"), Block("literal", query)]
    for i, item in enumerate(items, 1):
        blocks.append(
            Block(
                "literal",
                f"{i}. {item.title}\nExtracto: {item.snippet}\n{item.url}\nFuente: {urlsplit(item.url).hostname}",
            )
        )
    blocks.append(
        Block(
            "notice",
            "Resultados candidatos. No se han abierto ni verificado las páginas completas.",
        )
    )
    return Document(tuple(blocks))


def web(items, query):
    return web_document(items, query).text()
