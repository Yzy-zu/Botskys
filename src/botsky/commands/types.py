"""Campos tipados declarativos. El parseo valida sintaxis, no autoridad."""

import re
from dataclasses import dataclass
from datetime import date, time
from math import isfinite
from urllib.parse import urlsplit

type ArgumentValue = str | int | float | bool | tuple[str, ...]


@dataclass(frozen=True)
class Field:
    name: str
    kind: str = "text"
    required: bool = True
    default: ArgumentValue | None = None
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    max_length: int = 8000
    option: str | None = None
    tail: bool = False
    repeated: bool = False
    min_items: int = 1
    max_items: int = 10
    original: str | None = None
    example: str = "ejemplo"

    def convert(self, value: str) -> ArgumentValue:
        if len(value) > self.max_length or not value.strip():
            raise ValueError(f"requiere texto de 1 a {self.max_length} caracteres")
        if any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("contiene caracteres de control no admitidos")
        if self.kind in ("enum", "bool"):
            # Solo las palabras de sintaxis son insensibles a mayúsculas.
            val = value.lower()
            if self.kind == "bool":
                if val not in ("si", "no"):
                    raise ValueError("usa si o no")
                return val == "si"
            if val not in self.choices:
                raise ValueError("usa " + "|".join(self.choices))
            return val
        if self.kind in ("int", "float", "duration", "seconds"):
            pattern = r"[0-9]+" if self.kind == "int" else r"[0-9]+(?:\.[0-9]+)?"
            factor = 1
            if self.kind == "duration":
                match = re.fullmatch(r"([0-9]+)([smhd])", value)
                if not match:
                    raise ValueError("usa un intervalo como 30s, 10m, 2h o 1d")
                value, suffix = match.groups()
                factor = {"s": 1, "m": 60, "h": 3600, "d": 86400}[suffix]
                pattern = r"[0-9]+"
            elif self.kind == "seconds" and ":" in value:
                match = re.fullmatch(r"([0-9]{1,2}):([0-5][0-9]):([0-5][0-9](?:\.[0-9]+)?)", value)
                if not match:
                    raise ValueError("usa segundos o HH:MM:SS")
                h, m, s = match.groups()
                value = str(int(h) * 3600 + int(m) * 60 + float(s))
            if not re.fullmatch(pattern, value):
                if self.kind == "int":
                    bounds = (
                        f" entre {self.minimum}–{self.maximum}"
                        if self.minimum is not None and self.maximum is not None
                        else ""
                    )
                    raise ValueError(f"requiere un número entero{bounds}, sin coerciones")
                raise ValueError("requiere un número decimal positivo sin coerciones")
            number = (int(value) if self.kind in ("int", "duration") else float(value)) * factor
            if (
                not isfinite(number)
                or self.minimum is not None
                and number < self.minimum
                or self.maximum is not None
                and number > self.maximum
            ):
                raise ValueError(f"fuera del rango {self.minimum}–{self.maximum}")
            return number
        if self.kind == "id":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
                raise ValueError("copia el ID del resultado real (1–64 letras, números, _ o -)")
        elif self.kind == "date":
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError("usa fecha completa AAAA-MM-DD")
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError("la fecha no existe; usa AAAA-MM-DD") from None
        elif self.kind == "clock":
            if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
                raise ValueError("usa hora HH:MM de 24 horas")
            try:
                hour, minute = map(int, value.split(":"))
                time(hour, minute)
            except ValueError:
                raise ValueError("usa hora entre 00:00 y 23:59") from None
        elif self.kind == "url":
            try:
                parsed = urlsplit(value)
                valid = (
                    parsed.scheme == "https"
                    and parsed.hostname
                    and not parsed.username
                    and not parsed.password
                    and not parsed.fragment
                    and parsed.port in (None, 443)
                )
            except ValueError:
                valid = False
            if not valid or any(c.isspace() for c in value):
                raise ValueError("usa un enlace HTTPS completo sin credenciales ni fragmento")
            # DNS/SSRF se valida en la frontera de red, no en el parser puro.
        elif self.kind == "pages":
            if not re.fullmatch(
                r"[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*", value
            ):
                raise ValueError("usa páginas como 1,3-5")
            for segment in value.split(","):
                parts = [int(v) for v in segment.split("-")]
                if max(parts) > 500 or len(parts) == 2 and parts[0] > parts[1]:
                    raise ValueError("páginas entre 1 y 500 en rangos ascendentes")
        elif self.kind in ("contacts", "terms"):
            contacts = tuple(s.strip() for s in value.split(","))
            limit = self.max_items
            length = 80 if self.kind == "contacts" else 100
            if (
                not 1 <= len(contacts) <= limit
                or len(set(contacts)) != len(contacts)
                or any(not s or len(s) > length for s in contacts)
            ):
                raise ValueError(
                    f"usa de 1 a {limit} valores distintos de hasta {length} caracteres, separados por coma"
                )
            return contacts
        return value


@dataclass(frozen=True)
class CommandSpec:
    path: tuple[str, ...]
    operation: str
    family: str
    original_action: str
    fields: tuple[Field, ...] = ()
    constants: tuple[tuple[str, ArgumentValue], ...] = ()
    permission: str = "friend"
    effect: str = "read"
    confirmation: str = "none"
    attachment: bool = False
    summary: str = ""
    example: str = ""
    block: str = "R2"

    @property
    def command(self) -> str:
        return "/" + " ".join(self.path)

    @property
    def usage(self) -> str:
        parts = [self.command]
        for field in self.fields:
            val = "|".join(field.choices) if field.kind == "enum" else field.name.upper()
            if field.kind == "flag":
                val = field.option
            elif field.option:
                val = field.option + " " + val
            if field.repeated:
                val += " ..."
            parts.append(val if field.required else "[" + val + "]")
        return " ".join(parts) + (" + adjunto o cita exacta" if self.attachment else "")

    @property
    def sample(self) -> str:
        if self.example:
            return self.example
        parts = [self.command]
        for field in self.fields:
            if field.required:
                if field.option:
                    parts.append(field.option)
                parts.append(field.example)
        return " ".join(parts)
