"""Parser determinista puro. Su salida no contiene identidad ni permisos concedidos."""

import json
import re
import unicodedata
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
        message = (f"{self.field}: " if self.field else "") + str(self)
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
            spec.operation in ("download_media.choose", "manage_drive.choose")
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
        def reject(field, reason):
            raise CommandError("incompatible_fields", reason, field=field, spec=spec)

        if args.get("end_seconds") is not None and args["end_seconds"] <= args.get(
            "start_seconds", 0
        ):
            reject("end_seconds", "El final debe ser posterior al inicio.")
        if args.get("container") == "srt" and (
            args.get("start_seconds", 0) != 0 or args.get("end_seconds") is not None
        ):
            reject("end_seconds", "SRT extrae subtítulos completos; no admite recorte.")
        if args.get("subtitle_language") and args.get("container") != "srt":
            reject("subtitle_language", "El idioma solo se usa con formato srt.")
        if spec.family == "manage_poll" and spec.original_action == "create":
            options = args["options"]
            if len({unicodedata.normalize("NFKC", v.strip()).casefold() for v in options}) != len(
                options
            ):
                reject("options", "Las opciones de la encuesta deben ser distintas.")
        if spec.family == "audiovisual.clip" and spec.original_action == "play":
            if ("clip_id" in args) == ("query" in args):
                reject("clip_id", "Indica exactamente ID del catálogo o --nombre TEXTO.")
        if spec.family == "manage_admin" and spec.original_action in ("xp_grant", "xp_remove"):
            if ("target" in args) == ("account_id" in args):
                reject("target", "Indica exactamente --objetivo REF o --cuenta ID.")
        if spec.original_action == "configure_digest":
            if bool(args.get("enabled")) != ("digest_time" in args):
                reject("digest_time", "La activación exige --hora HH:MM; al desactivar se omite.")
        if spec.original_action == "set_lesson" and args["end_time"] <= args["start_time"]:
            reject("end_time", "La clase debe terminar después del inicio.")
        if spec.family == "manage_messages" and spec.original_action == "prepare":
            if args["source"] == "cita" and "text" in args:
                reject(
                    "text", "Con --fuente cita se usa exclusivamente el texto de la cita exacta."
                )
            if args["source"] == "actual" and "text" not in args and not args.get("attach"):
                reject("text", "Falta el texto literal o un adjunto solicitado.")
        if spec.family == "audiovisual.agenda" and spec.original_action == "create":
            if args.get("audio_id") and args.get("live_request"):
                reject("audio_id", "Audio preparado y conversación Live son modos excluyentes.")
            if args.get("end_after_audio") and not args.get("audio_id"):
                reject("end_after_audio", "Terminar tras audio requiere un audio preparado propio.")
