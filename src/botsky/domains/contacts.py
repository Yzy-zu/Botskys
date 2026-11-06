"""Directorio explícito para R6; no búsqueda difusa ni inferencia de destinatarios."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from ..contracts import canonical


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def valid_name(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 80
        and normalized(value)
        and not any(unicodedata.category(c).startswith("C") for c in value)
    )


@dataclass(frozen=True)
class Contact:
    name: str
    target: str = field(repr=False)
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            not valid_name(self.name)
            or not isinstance(self.aliases, tuple)
            or len(self.aliases) > 8
            or not all(valid_name(a) for a in self.aliases)
        ):
            raise ValueError("invalid_contact_name")
        if not isinstance(self.target, str) or not re.fullmatch(
            r"(?:[0-9]{5,20}@s\.whatsapp\.net|[0-9-]{5,40}@g\.us)", self.target
        ):
            raise ValueError("invalid_contact_target")


class Directory:
    def __init__(self, contacts=()):
        self.contacts = tuple(contacts)
        if len(self.contacts) > 100:
            raise ValueError("directory_limit")
        self._names = {}
        targets = set()
        for contact in self.contacts:
            if not isinstance(contact, Contact) or contact.target in targets:
                raise ValueError("duplicate_or_invalid_contact")
            targets.add(contact.target)
            for name in (contact.name, *contact.aliases):
                key = normalized(name)
                if key in self._names and self._names[key] != contact:
                    raise ValueError("ambiguous_contact_alias")
                self._names[key] = contact

    def resolve(self, names):
        if not isinstance(names, tuple) or not 1 <= len(names) <= 10:
            raise ValueError("invalid_recipients")
        resolved = []
        for name in names:
            if not valid_name(name) or normalized(name) not in self._names:
                raise ValueError("unknown_recipient")
            contact = self._names[normalized(name)]
            if contact not in resolved:
                resolved.append(contact)
        return tuple(resolved)

    def fingerprint(self, names):
        """El futuro envío comprobará de nuevo el directorio mostrado en la vista."""
        contacts = self.resolve(names)
        return hashlib.sha256(
            canonical([(c.name, c.target) for c in contacts]).encode()
        ).hexdigest()
