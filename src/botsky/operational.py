"""Permisos explícitos por integración. No concede identidad, consentimiento o roles."""

import json
from dataclasses import dataclass

from .contracts import Result, canonical


def closed(value, keys):
    if not isinstance(value, dict) or set(value) - keys:
        raise ValueError("operational_policy_fields")


def identities(value, allowed):
    if (
        not isinstance(value, list)
        or len(value) > 200
        or any(not isinstance(v, str) or v not in allowed for v in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("operational_policy_scope")
    return value


@dataclass(frozen=True)
class OperationalPolicy:
    serialized: str

    @classmethod
    def build(cls, profile, settings):
        # Legacy false remains readable; the old global switch cannot enable effects.
        if profile.get("mutations_enabled", False) is not False:
            raise ValueError("global_mutation_switch_removed")
        groups = set(settings.allowed_groups)
        private = {settings.owner, *settings.friends}
        contacts = {v.get("jid") for v in profile.get("contacts", []) if isinstance(v, dict)}
        targets = groups | private | contacts
        defaults = {
            "version": 1,
            "messages": {"send": False, "targets": []},
            "drive": {"read": True, "write": False},
            "groups": {"read": True, "write": False, "chats": sorted(groups)},
            "minecraft": {"read": True, "write": False},
            "gallery": {"enabled": False, "send": False, "chats": []},
            "roulette": {"chats": [], "allow_admins": False},
            "nuclear": {"enabled": False, "chats": []},
            "delivery": {
                "send": profile.get("evolution", {}).get("delivery_enabled", False),
                "chats": sorted(groups | private),
            },
        }
        value = profile.get("permissions", {})
        closed(value, set(defaults))
        if type(value.get("version", 1)) is not int or value.get("version", 1) != 1:
            raise ValueError("operational_policy_version")
        for name, default in defaults.items():
            if name == "version":
                continue
            override = value.get(name, {})
            closed(override, set(default))
            merged = {**default, **override}
            for key, item in merged.items():
                if isinstance(default[key], bool) and type(item) is not bool:
                    raise ValueError("operational_policy_bool")
                if isinstance(default[key], list):
                    identities(
                        item,
                        groups
                        if name in ("groups", "roulette", "nuclear")
                        else targets
                        if name == "messages"
                        else groups | private,
                    )
            defaults[name] = merged
        for name in ("groups", "drive", "minecraft"):
            if defaults[name]["write"] and not defaults[name]["read"]:
                raise ValueError("operational_read_required")
        if defaults["gallery"]["send"] and not defaults["gallery"]["enabled"]:
            raise ValueError("gallery_read_required")
        if defaults["roulette"]["chats"] and (
            not defaults["groups"]["write"]
            or not defaults["messages"]["send"]
            or not set(defaults["roulette"]["chats"]) <= set(defaults["groups"]["chats"])
        ):
            raise ValueError("roulette_effects_required")
        if defaults["nuclear"]["enabled"] and (
            not defaults["nuclear"]["chats"]
            or not defaults["groups"]["write"]
            or not set(defaults["nuclear"]["chats"]) <= set(defaults["groups"]["chats"])
        ):
            raise ValueError("nuclear_scope_required")
        if (
            "permissions" in profile
            and "delivery_enabled" in profile.get("evolution", {})
            and defaults["delivery"]["send"] != profile["evolution"]["delivery_enabled"]
        ):
            raise ValueError("delivery_permission_conflict")
        return cls(canonical(defaults))

    @property
    def document(self):
        return json.loads(self.serialized)

    def authorize(self, context, operation):
        p, chat = self.document, context.scope.chat
        family, _, action = operation.partition(".")
        allowed = True
        if family == "manage_drive":
            allowed = p["drive"]["write" if action == "save" else "read"]
        elif family == "manage_minecraft":
            allowed = p["minecraft"][
                "read" if action in {"status", "players", "worlds", "mods", "config"} else "write"
            ]
        elif family == "manage_messages" and action == "send":
            allowed = p["messages"]["send"]
        elif family == "manage_pack" and action != "status":
            allowed = (
                p["gallery"]["enabled"]
                and chat in p["gallery"]["chats"]
                and (action == "catalog" or p["gallery"]["send"])
            )
        elif family == "manage_happy_hour" and action in {"rain", "claim", "reward"}:
            allowed = p["gallery"]["send"] and chat in p["gallery"]["chats"]
        elif family == "manage_roulette" and action not in {"status", "cancel"}:
            allowed = chat in p["roulette"]["chats"]
        elif family == "manage_admin":
            if action == "nuclear_cancel":
                return None
            allowed = p["groups"]["read"] and chat in p["groups"]["chats"]
            if action in {"kick", "ban", "promote", "demote", "mute", "unmute", "lock", "unlock"}:
                allowed = allowed and p["groups"]["write"]
            elif action.startswith("nuclear_"):
                allowed = (
                    allowed
                    and chat in p["nuclear"]["chats"]
                    and (action == "nuclear_prepare" or p["nuclear"]["enabled"])
                )
        if not allowed:
            return Result(
                "failed",
                "operation_not_enabled",
                "Esta función o este chat no está habilitado en la configuración de Botsky. No se ejecutó la acción.",
            )
        return None

    def delivers(self, target):
        p = self.document["delivery"]
        return p["send"] and target in p["chats"]


class PermissionGate:
    """Comprueba el método y su destino antes del backend, OAuth o SSH."""

    def __init__(self, backend, rules, error, *, available=True):
        self._backend, self._rules, self._error, self._available = backend, rules, error, available

    @property
    def available(self):
        return bool(self._available and getattr(self._backend, "available", True))

    def __getattr__(self, name):
        original = getattr(self._backend, name)
        if name not in self._rules:
            return original

        async def guarded(*args, **kwargs):
            rule = self._rules[name]
            if not (rule(*args, **kwargs) if callable(rule) else rule):
                raise self._error("integration_permission_denied", uncertain=False)
            return await original(*args, **kwargs)

        return guarded
