"""Tabla nativa propia, límites locales contrastados con instalación observada."""

from dataclasses import dataclass

from ..contracts import canonical


def utf16_length(value):
    return len(value.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class NativeTable:
    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self):
        cells = (*self.headers, *(cell for row in self.rows for cell in row))
        if (
            not isinstance(self.title, str)
            or utf16_length(self.title) > 300
            or not 1 <= len(self.headers) <= 20
            or not 1 <= len(self.rows) <= 100
            or any(len(row) != len(self.headers) for row in self.rows)
            or any(not isinstance(cell, str) or utf16_length(cell) > 3500 for cell in cells)
        ):
            raise ValueError("tabla inválida")
        if len(canonical(self.payload()).encode()) > 60 * 1024:
            raise ValueError("tabla demasiado grande")

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or set(data) != {"title", "headers", "rows"}:
            raise ValueError("campos de tabla inválidos")
        if (
            not isinstance(data["headers"], (tuple, list))
            or not isinstance(data["rows"], (tuple, list))
            or any(not isinstance(r, (list, tuple)) for r in data["rows"])
        ):
            raise ValueError("filas inválidas")
        return cls(data["title"], tuple(data["headers"]), tuple(tuple(row) for row in data["rows"]))

    def payload(self):
        return {
            "title": self.title,
            "headers": list(self.headers),
            "rows": [list(row) for row in self.rows],
        }

    def fallback(self):
        return "\n\n".join(
            [self.title]
            + [
                "\n".join(
                    f"{label}: {value}" for label, value in zip(self.headers, row, strict=True)
                )
                for row in self.rows
            ]
        )
