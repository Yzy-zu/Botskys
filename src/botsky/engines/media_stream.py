"""Bounded file transfers for Evolution's JSON/base64 wire format.

This is a technical codec, never a natural-language recognizer. The large string
is decoded incrementally; the remaining JSON is validated by the standard parser.
"""

import base64
import binascii
import json
import os
import stat
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import BinaryIO

CHUNK = 192 * 1024  # Divisible by three for independently encoded chunks.


class StreamMediaError(ValueError):
    pass


async def json_file_body(
    payload: dict[str, object], path: Path, *, field="media"
) -> AsyncGenerator[bytes]:
    if field not in ("media", "audio", "sticker") or field in payload:
        raise StreamMediaError("invalid media field")
    prefix = json.dumps(payload, ensure_ascii=True).encode()[:-1] + b', "' + field.encode() + b'":"'
    yield prefix
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise StreamMediaError("invalid file")
        total = 0
        while block := stream.read(CHUNK):
            total += len(block)
            if total > 2_000_000_000:
                raise StreamMediaError("too large")
            yield base64.b64encode(block)
    yield b'"}'


class Base64JSONWriter:
    """Extract exactly one top-level base64 string with bounded memory."""

    def __init__(self, output: BinaryIO, maximum: int):
        self.output, self.maximum = output, maximum
        self.metadata = bytearray()
        self.string = bytearray()
        self.in_string = self.escaped = self.key_string = False
        self.depth = 0
        self.last = 0
        self.await_value = 0
        self.media = self.media_escape = self.finished = False
        self.found = 0
        self.pending = b""
        self.padded = False
        self.size = 0

    def _write(self, block: bytes, final: bool = False) -> None:
        block = self.pending + block
        count = len(block) if final else max(0, (len(block) // 4 - 1) * 4)
        data, self.pending = block[:count], block[count:]
        if not data:
            return
        if self.padded:
            raise StreamMediaError("trailing base64")
        try:
            decoded = base64.b64decode(data, validate=True)
        except binascii.Error as exc:
            raise StreamMediaError("invalid base64") from exc
        self.padded = b"=" in data
        self.size += len(decoded)
        if self.size > self.maximum:
            raise StreamMediaError("too large")
        self.output.write(decoded)

    def feed(self, block: bytes) -> None:
        pos = 0
        while pos < len(block):
            if self.media:
                if self.media_escape:
                    if block[pos] != 47:  # JSON permits escaped slash.
                        raise StreamMediaError("invalid base64 escape")
                    self._write(b"/")
                    self.media_escape = False
                    pos += 1
                    continue
                quote, slash = block.find(b'"', pos), block.find(b"\\", pos)
                ends = [n for n in (quote, slash) if n >= 0]
                end = min(ends) if ends else len(block)
                self._write(block[pos:end])
                pos = end
                if pos == len(block):
                    continue
                if block[pos] == 92:
                    self.media_escape = True
                else:
                    self._write(b"", final=True)
                    self.media = False
                    self.finished = True
                    self.metadata.extend(b'"')
                    self.last = 34
                pos += 1
                continue
            value = block[pos]
            pos += 1
            self.metadata.append(value)
            if len(self.metadata) > 128 * 1024:
                raise StreamMediaError("metadata too large")
            if self.in_string:
                self.string.append(value)
                if self.escaped:
                    self.escaped = False
                elif value == 92:
                    self.escaped = True
                elif value == 34:
                    self.in_string = False
                    if self.key_string and json.loads(self.string) == "base64":
                        self.await_value = 1
                    self.last = 34
                continue
            if value in b" \r\n\t":
                continue
            if self.await_value:
                expected = 58 if self.await_value == 1 else 34
                if value != expected:
                    raise StreamMediaError("base64 must be a string")
                if self.await_value == 1:
                    self.await_value = 2
                else:
                    self.found += 1
                    if self.found != 1:
                        raise StreamMediaError("duplicate base64")
                    self.await_value = 0
                    self.media = True
                continue
            if value == 34:
                self.in_string = True
                self.key_string = self.depth == 1 and self.last in (123, 44)
                self.string = bytearray(b'"')
            elif value in (123, 91):
                self.depth += 1
            elif value in (125, 93):
                self.depth -= 1
            self.last = value

    def finish(self) -> int:
        try:
            value = json.loads(self.metadata)
        except (ValueError, UnicodeError) as exc:
            raise StreamMediaError("invalid JSON") from exc
        if (
            not self.finished
            or self.media
            or self.found != 1
            or not self.size
            or not isinstance(value, dict)
            or value.get("base64") != ""
        ):
            raise StreamMediaError("missing base64")
        return self.size
