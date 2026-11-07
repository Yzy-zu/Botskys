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
        return self.text


@dataclass(frozen=True)
class Document:
    blocks: tuple[Block, ...]
    version: int = VERSION

    def text(self):
        return "\n\n".join(block.render() for block in self.blocks if block.text)


def split_text(text: str, limit: int = 3500) -> tuple[str, ...]:
    """Partes exactas, preferentemente por párrafo/línea/espacio. Sin strip ni regex.

    Las partes se fijan en outbox antes del primer envío. El caso indivisible aún
    usa fragmentos exactos: la alternativa de archivo se integra con los artefactos.
    """
    if limit < 1:
        raise ValueError("límite inválido")
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        end = 0
        for separator in ("\n\n", "\n", " "):
            found = text.rfind(separator, 0, limit)
            if found >= limit // 3:
                end = found + len(separator)
                break
        end = end or limit
        parts.append(text[:end])
        text = text[end:]
    return tuple(parts)
