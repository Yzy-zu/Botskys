"""Contratos propios. Solo los adaptadores construyen Incoming con identidad verificada."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Literal


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Scope:
    actor: str
    chat: str
    is_group: bool = False


@dataclass(frozen=True)
class Incoming:
    instance: str
    account: str
    message_id: str
    scope: Scope
    text: str
    source_ms: int
    received_ms: int
    transport: Literal["local", "evolution"] = "local"
    historical: bool = False
    attachments: tuple[str, ...] = ()
    quoted_message_id: str | None = None

    @property
    def id(self):
        return hashlib.sha256(
            canonical([self.instance, self.account, self.message_id]).encode()
        ).hexdigest()[:32]

    @property
    def fingerprint(self):
        data = asdict(self)
        del data["received_ms"]
        # Compatibilidad con los recibos R2 previos a las referencias de archivo.
        if not self.attachments:
            del data["attachments"]
        if self.quoted_message_id is None:
            del data["quoted_message_id"]
        return hashlib.sha256(canonical(data).encode()).hexdigest()


@dataclass(frozen=True)
class CommandContext:
    receipt_id: str
    instance: str
    account: str
    scope: Scope
    epoch: int
    revision: int

    @property
    def scope_key(self):
        return (
            self.instance,
            self.account,
            self.scope.actor,
            self.scope.chat,
            int(self.scope.is_group),
            self.epoch,
        )


@dataclass(frozen=True)
class Result:
    status: Literal["ok", "empty", "needs_input", "failed", "cancelled", "uncertain"]
    code: str
    text: str = ""
    data: dict = field(default_factory=dict)

    def to_json(self):
        return canonical(asdict(self))

    @classmethod
    def from_json(cls, value):
        return cls(**json.loads(value))


@dataclass(frozen=True)
class Receipt:
    id: str
    state: str
    result: Result | None
    duplicate: bool = False


@dataclass(frozen=True)
class DeliveryAck:
    accepted: bool
    message_id: str | None = None


@dataclass(frozen=True)
class DeliveryPart:
    receipt_id: str
    position: int
    context: CommandContext
    text: str
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactRef:
    id: str
    scope: Scope
    instance: str
    account: str
    epoch: int
    source_message_id: str
    format: str
    size: int
    sha256: str
    expires_ms: int
