"""Configuración explícita; sin descubrir secretos ni leer el entorno de Zhana."""

import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    root: Path
    instance: str
    account: str
    epoch: int
    database: Path
    activation_ms: int
    owner: str
    friends: frozenset[str]
    allowed_groups: frozenset[str]
    timezone: str = "America/Mexico_City"
    max_age_seconds: int = 300
    max_future_seconds: int = 30
    transport: str = "local"
    bot_ids: frozenset[str] = frozenset({"botsky-local"})

    calls: object | None = None

    @classmethod
    def load(cls, path: Path):
        path = path.resolve(strict=True)
        data = tomllib.loads(path.read_text())
        allowed = {
            "instance",
            "account",
            "epoch",
            "database",
            "activation_at",
            "owner",
            "friends",
            "allowed_groups",
            "timezone",
            "max_age_seconds",
            "max_future_seconds",
            "transport",
            "bot_ids",
            "calls",
        }
        if data.keys() - allowed:
            raise ValueError("configuración contiene campos desconocidos")
        required = {
            "instance",
            "epoch",
            "database",
            "activation_at",
            "owner",
            "friends",
            "allowed_groups",
        }
        if not required <= data.keys():
            raise ValueError("configuración incompleta")
        for key in ("instance", "owner", "database", "activation_at"):
            if not isinstance(data[key], str) or not data[key].strip():
                raise ValueError(f"configuración inválida: {key}")
        account = data.get("account", "local-account")
        if not isinstance(account, str) or not account.strip():
            raise ValueError("account inválida")
        for key in ("epoch", "max_age_seconds", "max_future_seconds"):
            value = data.get(key, {"max_age_seconds": 300, "max_future_seconds": 30}.get(key))
            if type(value) is not int or not 1 <= value <= (1000000 if key == "epoch" else 86400):
                raise ValueError(f"configuración entera inválida: {key}")
        for key in ("friends", "allowed_groups", "bot_ids"):
            values = data.get(key, ["botsky-local"])
            if not isinstance(values, list) or any(
                not isinstance(v, str) or not v.strip() or v == "*" for v in values
            ):
                raise ValueError(f"{key} requiere lista explícita de identidades")
        if data.get("transport", "local") != "local":
            raise ValueError("Transporte real todavía no habilitado.")
        zone = data.get("timezone", "America/Mexico_City")
        if zone != "America/Mexico_City":
            raise ValueError("zona v1 requerida: America/Mexico_City")
        ZoneInfo(zone)
        cut = datetime.fromisoformat(data["activation_at"].replace("Z", "+00:00"))
        if cut.tzinfo is None:
            raise ValueError("activation_at requiere zona explícita")
        database = (path.parent / data["database"]).resolve()
        if not database.is_relative_to(path.parent) or database == path.parent:
            raise ValueError("la DB debe estar dentro del proyecto propio")
        settings = cls(
            path.parent,
            data["instance"],
            account,
            data["epoch"],
            database,
            int(cut.timestamp() * 1000),
            data["owner"],
            frozenset(data["friends"]),
            frozenset(data["allowed_groups"]),
            zone,
            data.get("max_age_seconds", 300),
            data.get("max_future_seconds", 30),
            bot_ids=frozenset(data.get("bot_ids", ["botsky-local"])),
        )
        if "calls" in data:
            from dataclasses import replace

            from .call_policy import CallPolicy

            settings = replace(settings, calls=CallPolicy.build(data["calls"], settings))
        return settings
