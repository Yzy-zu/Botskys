"""Decisiones del frontend; nunca contienen autoridad del ejecutor."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionRequest:
    action_key: str
    arguments: dict


@dataclass(frozen=True)
class ReplyDecision:
    text: str


@dataclass(frozen=True)
class ClarifyDecision:
    question: str
    action_key: str | None = None
    partial_arguments: dict = field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class NoActionDecision:
    reason: str
