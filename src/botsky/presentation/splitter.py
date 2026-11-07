"""División exacta en unidades UTF-16 y fronteras Unicode, sin interpretar órdenes."""

import unicodedata


class IndivisibleText(ValueError):
    pass


def units(text):
    return len(text.encode("utf-16-le")) // 2


def boundary(text, index):
    if index == 0 or index == len(text):
        return True
    previous, following = text[index - 1], text[index]
    # No separar diacríticos, variaciones, pares regionales, modificadores o ZWJ.
    if (
        previous == "\u200d"
        or following == "\u200d"
        or unicodedata.category(following).startswith("M")
    ):
        return False
    if 0x1F3FB <= ord(following) <= 0x1F3FF or 0xE0020 <= ord(following) <= 0xE007F:
        return False
    if 0x1F1E6 <= ord(following) <= 0x1F1FF and 0x1F1E6 <= ord(previous) <= 0x1F1FF:
        count = 0
        for char in reversed(text[:index]):
            if not 0x1F1E6 <= ord(char) <= 0x1F1FF:
                break
            count += 1
        return count % 2 == 0
    return previous != "\r" or following != "\n"


def split(text, limit=3500):
    if limit < 1:
        raise ValueError("límite inválido")
    parts = []
    while text:
        end, used = 0, 0
        for char in text:
            cost = 2 if ord(char) > 0xFFFF else 1
            if used + cost > limit:
                break
            used += cost
            end += 1
        if end == len(text):
            parts.append(text)
            break
        for separator in ("\n\n", "\n", " "):
            found = text.rfind(separator, 0, end)
            if found >= end // 3:
                end = found + len(separator)
                break
        while end and not boundary(text, end):
            end -= 1
        if end == 0:
            raise IndivisibleText("grupo Unicode indivisible")
        parts.append(text[:end])
        text = text[end:]
    return tuple(parts)


def needs_file(text, limit=3500):
    # URLs/tokens largos se conservan en archivo; código con delimitadores propios
    # tampoco se reescribe o escapa para caber en una cerca externa.
    return (
        "```" in text
        or any(units(word) > limit for word in text.split())
        or any(char in text for char in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
    )
