"""Parser determinista puro. Su salida no contiene identidad ni permisos concedidos."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import get_close_matches
from types import MappingProxyType

from .lexer import SyntaxProblem, next_token, skip_spaces
from .registry import Registry
from .types import ArgumentValue, CommandSpec

PARSER_VERSION = 1
MAX_COMMAND_CHARS = 64000


class CommandError(ValueError):
    def __init__(self, code, message, *, field=None, position=0, spec=None):
        self.code, self.field, self.position, self.spec = code, field, position, spec
        super().__init__(message)

    @property
    def reply(self):
        from .editorial import FIELD_LABELS

        label = FIELD_LABELS.get(self.field, self.field)
        if self.spec and self.field:
            field = next((f for f in self.spec.fields if f.name == self.field), None)
            if field and field.option:
                label = field.option
        message = (f"{label}: " if label else "") + str(self)
        if self.spec:
            message += "\nUso: " + self.spec.usage + "\nEjemplo: " + self.spec.sample
        return message


@dataclass(frozen=True)
class ParsedCommand:
    spec: CommandSpec
    arguments: Mapping[str, ArgumentValue]
    spans: Mapping[str, tuple[tuple[int, int], ...]]
    parser_version: int = PARSER_VERSION

    def canonical(self) -> str:
        return json.dumps(
            {
                "version": self.parser_version,
                "operation": self.spec.operation,
                "arguments": dict(self.arguments),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class Router:
    def __init__(self, registry=None):
        self.registry = registry or Registry()

    def parse(self, text: str) -> ParsedCommand | None:
        if not isinstance(text, str):
            raise TypeError("la entrada debe ser texto")
        start = len(text) - len(text.lstrip())
        if not text[start:].startswith("/"):
            return None
        if len(text) > MAX_COMMAND_CHARS:
            raise CommandError("command_too_long", "El comando excede 64000 caracteres.")
        match = re.match(r"/([A-Za-z][A-Za-z0-9-]*)(?=$|[ \t\r\n])", text[start:])
        if not match:
            raise CommandError("invalid_command", "Comando inválido. Usa /ayuda.", position=start)
        root = match[1].lower()
        root = self.registry.aliases.get(root, root)
        path, position = (root,), start + match.end()
        candidates = [s for s in self.registry.specs if s.path[0] == root]
        if not candidates:
            suggestion = get_close_matches(
                root, sorted({s.path[0] for s in self.registry.specs}), n=1, cutoff=0.7
            )
            suffix = (
                " Tal vez buscabas /" + suggestion[0] + "; vuelve a enviarlo." if suggestion else ""
            )
            raise CommandError(
                "unknown_command", "Comando desconocido. Usa /ayuda." + suffix, position=start
            )
        while True:
            probe = skip_spaces(text, position)
            word = re.match(r"([A-Za-z][A-Za-z0-9-]*)(?=$|[ \t\r\n])", text[probe:])
            longer = path + (word[1].lower(),) if word else ()
            if word and any(s.path[: len(longer)] == longer for s in candidates):
                path, position = longer, probe + word.end()
                continue
            spec = self.registry.paths.get(path)
            if spec is None:
                raise CommandError(
                    "unknown_action",
                    "Falta una acción válida.\n" + self.registry.help(root),
                    position=probe,
                )
            break
        try:
            return self._arguments(text, position, spec)
        except SyntaxProblem as exc:
            raise CommandError(exc.code, str(exc), position=exc.position, spec=spec) from None

    def _arguments(self, text, position, spec):
        values, spans = dict(spec.constants), {}
        options = {f.option: f for f in spec.fields if f.option}
        fields = [f for f in spec.fields if not f.option]
        cursor, seen, literal = 0, set(), False

        def assign(field, value, start, end):
            try:
                converted = field.convert(value)
            except (ValueError, OverflowError) as exc:
                raise CommandError(
                    "invalid_field", str(exc), field=field.name, position=start, spec=spec
                ) from None
            if field.repeated:
                prior = values.get(field.name, ())
                if len(prior) >= field.max_items:
                    raise CommandError(
                        "too_many_values",
                        f"máximo {field.max_items} valores",
                        field=field.name,
                        position=start,
                        spec=spec,
                    )
                values[field.name] = prior + (converted,)
                spans[field.name] = spans.get(field.name, ()) + ((start, end),)
            else:
                values[field.name], spans[field.name] = converted, ((start, end),)

        while (position := skip_spaces(text, position)) < len(text):
            if not literal and text.startswith("--", position):
                tok = next_token(text, position)
                if tok.value == "--":
                    if cursor >= len(fields) or not fields[cursor].tail:
                        raise CommandError(
                            "unexpected_separator",
                            "Usa -- justo antes del texto final.",
                            position=position,
                            spec=spec,
                        )
                    literal, position = True, tok.end
                    continue
                field = options.get(tok.value)
                if not field:
                    raise CommandError(
                        "unknown_option",
                        "Opción desconocida: " + tok.value,
                        position=position,
                        spec=spec,
                    )
                if field.name in seen:
                    raise CommandError(
                        "duplicate_option",
                        "Opción duplicada: " + tok.value,
                        field=field.name,
                        position=position,
                        spec=spec,
                    )
                seen.add(field.name)
                if field.kind == "flag":
                    values[field.name], spans[field.name] = True, ((tok.start, tok.end),)
                    position = tok.end
                    continue
                value_token = next_token(text, tok.end)
                if value_token is None or value_token.value.startswith("--"):
                    raise CommandError(
                        "missing_option_value",
                        "Falta el valor de " + tok.value,
                        field=field.name,
                        position=tok.end,
                        spec=spec,
                    )
                assign(field, value_token.value, value_token.start, value_token.end)
                position = value_token.end
                continue
            if cursor == len(fields):
                raise CommandError(
                    "extra_argument", "Sobran argumentos.", position=position, spec=spec
                )
            field = fields[cursor]
            if field.tail:
                assign(field, text[position:], position, len(text))
                position = len(text)
            else:
                tok = next_token(text, position)
                assign(field, tok.value, tok.start, tok.end)
                position = tok.end
            if not field.repeated:
                cursor += 1
        for field in spec.fields:
            if field.name not in values:
                if field.required:
                    raise CommandError(
                        "missing_field",
                        "Falta el campo requerido.",
                        field=field.name,
                        position=position,
                        spec=spec,
                    )
                if field.default is not None:
                    values[field.name] = field.default
            if field.repeated and len(values.get(field.name, ())) < field.min_items:
                raise CommandError(
                    "missing_values",
                    f"requiere al menos {field.min_items} valores",
                    field=field.name,
                    position=position,
                    spec=spec,
                )
        if (
            spec.operation
            in ("download_media.choose", "manage_drive.choose", "download_media.inspect")
            and "choice" not in values
        ):
            choice_field = next(f for f in spec.fields if f.name == "choice")
            raw = values.pop("view_id")
            try:
                values["choice"] = choice_field.convert(raw)
            except ValueError:
                raise CommandError(
                    "missing_field",
                    "Indica NUMERO o ID_DE_LISTA NUMERO.",
                    field="choice",
                    spec=spec,
                ) from None
            spans["choice"] = spans.pop("view_id")
        self._validate(spec, values)
        return ParsedCommand(spec, MappingProxyType(values), MappingProxyType(spans))

    @staticmethod
    def _validate(spec, args):
        from .validation import validate_arguments
        validate_arguments(spec, args)
