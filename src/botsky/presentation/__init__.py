"""Presentación determinista propia; nunca interpreta contenido como órdenes."""

from dataclasses import dataclass
from typing import Literal

VERSION = 1


@dataclass(frozen=True)
class Block:
    kind: Literal["heading", "paragraph", "literal", "quote", "notice", "next_action"]
    text: str

    def render(self):
        # Los títulos son del producto. Los datos literales nunca se reescriben.
        if self.kind == "heading" and not any(c in self.text for c in "*_`\n"):
            return "*" + self.text + "*"
        if self.kind == "quote":
            return "\n".join("> " + line for line in self.text.split("\n"))
        if self.kind == "next_action" and "\n" not in self.text and "`" not in self.text:
            return "`" + self.text + "`"
        return self.text


@dataclass(frozen=True)
class Document:
    blocks: tuple[Block, ...]
    version: int = VERSION

    def text(self):
        return "\n\n".join(block.render() for block in self.blocks if block.text)


def split_text(text: str, limit: int = 3500) -> tuple[str, ...]:
    from .splitter import split

    return split(text, limit)


def attach_document(result, document):
    from dataclasses import asdict, replace

    return replace(result, text=document.text(), data={**result.data, "document": asdict(document)})
