"""Plan propio versionado; datos literales no se convierten en formato ni comandos."""

from dataclasses import dataclass, field

from . import Block
from .splitter import IndivisibleText, needs_file, split, units
from .table import NativeTable

VERSION = 2
LIMIT = 3500


@dataclass(frozen=True)
class Part:
    kind: str
    text: str = ""
    payload: dict = field(default_factory=dict)


def _blocks(document):
    if (
        not isinstance(document, dict)
        or set(document) != {"blocks", "version"}
        or document["version"] != 1
    ):
        raise ValueError("documento inválido")
    blocks = []
    for data in document["blocks"]:
        if (
            not isinstance(data, dict)
            or set(data) != {"kind", "text"}
            or data["kind"]
            not in ("heading", "paragraph", "literal", "quote", "notice", "next_action")
            or not isinstance(data["text"], str)
        ):
            raise ValueError("bloque inválido")
        blocks.append(Block(**data))
    return blocks


def text_parts(blocks, retain):
    """retain recibe texto exacto y devuelve ID de artefacto propio UTF8."""
    result = []
    current = ""
    source = ""

    def flush():
        nonlocal current, source
        if current:
            result.append(Part("text", current, {"source_text": source}))
            current = ""
            source = ""

    def append(rendered, canonical):
        nonlocal current, source
        separator = "\n\n" if current else ""
        if units(current + separator + rendered) > LIMIT:
            flush()
            separator = ""
        current += separator + rendered
        source += separator + canonical

    for block in blocks:
        if not block.text:
            continue
        literal = block.kind == "literal"
        code = literal and any(c in block.text for c in "*_~`\n>")
        budget = LIMIT - 8 if code else LIMIT
        if needs_file(block.text, budget) or (
            block.kind == "next_action" and units(block.text) > LIMIT - 2
        ):
            flush()
            identifier = retain(block.text)
            result.extend(
                (
                    Part(
                        "text",
                        "📄 El texto es muy extenso o contiene caracteres especiales. Te lo comparto en este archivo adjunto:",
                        {"source_text": ""},
                    ),
                    Part(
                        "media",
                        payload={
                            "artifacts": [identifier],
                            "name": "Documento.txt",
                            "caption": "📄 Archivo de texto adjunto",
                            "role": "literal_source",
                        },
                    ),
                )
            )
            continue
        try:
            fragments = split(block.text, budget)
        except IndivisibleText:
            flush()
            identifier = retain(block.text)
            result.append(
                Part(
                    "media",
                    payload={
                        "artifacts": [identifier],
                        "name": "Texto.txt",
                        "caption": "📄 Contenido completo",
                        "role": "literal_source",
                    },
                )
            )
            continue
        for fragment in fragments:
            rendered = (
                ("```\n" + fragment + "\n```") if code else Block(block.kind, fragment).render()
            )
            # El formato de heading añade 2; no dividir a través de marcadores.
            if units(rendered) > LIMIT:
                for tiny in split(fragment, LIMIT - 8):
                    append("```\n" + tiny + "\n```", tiny)
                    flush()
            else:
                append(rendered, fragment)
            if len(fragments) > 1:
                flush()
    flush()
    return result


def compile_result(result, retain, *, native_tables=False):
    data = result.data
    if data.get("reaction"):
        text = "" if result.code == "job_queued" else result.text
        return [Part("text", text, payload={"reaction": data["reaction"], "source_text": text})]
    media_only = {"sticker_created", "reaction_ready", "voice_ready"}
    if result.code in media_only and data.get("artifacts"):
        return [
            Part(
                "media",
                payload={
                    "artifacts": [identifier],
                    "source_text": data.get("spoken_text", "")
                    if result.code == "voice_ready"
                    else "",
                    "caption": "",
                },
            )
            for identifier in data["artifacts"]
        ]
    raw_tables = data.get("native_tables") or (
        [data["native_table"]] if data.get("native_table") else []
    )
    tables = []
    try:
        tables = [NativeTable.parse(raw) for raw in raw_tables]
    except TypeError, ValueError:
        pass
    if tables and native_tables:
        intro, footer = data.get("native_intro", ""), data.get("native_footer", "")
        if isinstance(intro, str) and isinstance(footer, str):
            parts = text_parts(
                [Block("literal" if data.get("native_intro_literal") else "paragraph", intro)],
                retain,
            )
            parts.extend(Part("table", payload=table.payload()) for table in tables)
            parts.extend(text_parts([Block("paragraph", footer)], retain))
        else:
            parts = text_parts([Block("paragraph", result.text)], retain)
    elif data.get("document"):
        parts = text_parts(_blocks(data["document"]), retain)
    elif tables:
        intro, footer = data.get("native_intro", ""), data.get("native_footer", "")
        parts = text_parts(
            [
                Block("literal" if data.get("native_intro_literal") else "paragraph", intro),
                *(Block("paragraph", table.fallback()) for table in tables),
                Block("paragraph", footer),
            ],
            retain,
        )
    else:
        # Texto anterior todavía canónico; sin reescritura global con regex.
        if needs_file(result.text):
            parts = text_parts([Block("literal", result.text)], retain)
        else:
            parts = [
                Part("text", fragment, {"source_text": fragment}) for fragment in split(result.text)
            ]
    media = [
        Part("media", payload={"artifacts": [identifier]})
        for identifier in data.get("artifacts", ())
    ]
    caption_codes = {
        "document_converted",
        "media_edited",
        "download_ready",
        "pdf_assembled",
        "pdf_extracted",
        "drive_downloaded",
        "task_attachment",
        "download_choices",
    }
    caption_limit = 1024 if result.code == "download_choices" else 900
    if (
        result.code in caption_codes
        and len(media) == 1
        and len(parts) == 1
        and parts[0].kind == "text"
        and units(parts[0].text) <= caption_limit
    ):
        return [
            Part(
                "media",
                payload={
                    **media[0].payload,
                    "caption": parts[0].text,
                    "source_text": parts[0].payload.get("source_text", result.text),
                    "caption_frozen": True,
                },
            )
        ]
    return media + parts if data.get("media_first") else parts + media
