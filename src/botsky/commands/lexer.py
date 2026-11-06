"""Lexer incremental con posiciones originales; nunca evalúa sintaxis de shell."""

from dataclasses import dataclass


class SyntaxProblem(ValueError):
    def __init__(self, code: str, message: str, position: int):
        super().__init__(message)
        self.code, self.position = code, position


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


def skip_spaces(text: str, position: int) -> int:
    # Saltos de línea son datos únicamente dentro del campo de texto final.
    while position < len(text) and text[position] in " \t":
        position += 1
    return position


def next_token(text: str, position: int) -> Token | None:
    position = skip_spaces(text, position)
    if position == len(text):
        return None
    start, value, quote = position, [], None
    while position < len(text):
        char = text[position]
        if quote:
            if char == quote:
                quote = None
            elif char == "\\" and position + 1 < len(text) and text[position + 1] in (quote, "\\"):
                position += 1
                value.append(text[position])
            else:
                value.append(char)
        elif char in " \t":
            break
        elif char in ('"', "'"):
            quote = char
        elif char in "\r\n;`" or text.startswith(("&&", "$("), position):
            raise SyntaxProblem(
                "unexpected_syntax", "No se admiten cadenas de órdenes aquí.", position
            )
        else:
            value.append(char)
        position += 1
    if quote:
        raise SyntaxProblem("unclosed_quote", "Falta cerrar la comilla.", start)
    return Token("".join(value), start, position)
