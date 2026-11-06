"""Allowlist propia revisionada; no consulta entornos, perfiles ni cuentas antiguas."""

import hashlib
import json
import re
from dataclasses import dataclass

PHONE = re.compile(r"[1-9]\d{9,14}@s\.whatsapp\.net\Z")
GROUP = re.compile(r"\d+(?:-\d+)?@g\.us\Z")


@dataclass(frozen=True)
class CallPolicy:
    serialized: str

    @classmethod
    def build(cls, document, settings):
        expected = {
            "version",
            "instance",
            "account",
            "epoch",
            "owner",
            "actors",
            "privateChats",
            "groups",
            "features",
            "schedule",
        }
        if not isinstance(document, dict) or set(document) != expected:
            raise ValueError("call_policy_fields")
        if (
            type(document["version"]) is not int
            or document["version"] != 1
            or type(document["epoch"]) is not int
            or document["epoch"] != settings.epoch
            or document["instance"] != settings.instance
            or document["account"] != settings.account
            or document["owner"] != settings.owner
            or not PHONE.fullmatch(settings.owner)
        ):
            raise ValueError("call_policy_identity")
        actors, chats, groups = document["actors"], document["privateChats"], document["groups"]
        for values in (actors, chats):
            if (
                not isinstance(values, list)
                or len(values) > 100
                or any(
                    not isinstance(v, str)
                    or not PHONE.fullmatch(v)
                    or (len(v.split("@")[0]) == 13 and v.startswith("521"))
                    for v in values
                )
                or len(set(values)) != len(values)
            ):
                raise ValueError("call_policy_allowlist")
        if not actors or not set(actors) <= {settings.owner, *settings.friends}:
            raise ValueError("call_policy_actors")
        if not isinstance(groups, list) or len(groups) > 50:
            raise ValueError("call_policy_groups")
        ids = []
        for group in groups:
            if (
                not isinstance(group, dict)
                or set(group) != {"id", "name", "maxParticipants"}
                or not isinstance(group["id"], str)
                or not GROUP.fullmatch(group["id"])
                or not isinstance(group["name"], str)
                or not group["name"].strip()
                or type(group["maxParticipants"]) is not int
                or not 2 <= group["maxParticipants"] <= 32
            ):
                raise ValueError("call_policy_group")
            ids.append(group["id"])
        if len(set(ids)) != len(ids) or not set(ids) <= settings.allowed_groups:
            raise ValueError("call_policy_group_scope")
        features = document["features"]
        if (
            not isinstance(features, dict)
            or set(features) != {"agenda", "incoming", "live", "outgoing"}
            or any(type(v) is not bool for v in features.values())
            or features["incoming"]
        ):
            raise ValueError("call_policy_features")
        schedule = document["schedule"]
        if (
            not isinstance(schedule, dict)
            or set(schedule) != {"timeZone", "startHour", "endHour"}
            or schedule["timeZone"] != "America/Mexico_City"
            or any(type(schedule[k]) is not int for k in ("startHour", "endHour"))
            or not 0 <= schedule["startHour"] < schedule["endHour"] <= 24
        ):
            raise ValueError("call_policy_schedule")
        return cls(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False))

    @property
    def document(self):
        return json.loads(self.serialized)

    @property
    def revision(self):
        return hashlib.sha256(self.serialized.encode()).hexdigest()

    @property
    def targets(self):
        d = self.document
        return frozenset([*d["privateChats"], *(g["id"] for g in d["groups"])])

    def allows(self, context):
        d = self.document
        s = context.scope
        return (
            context.instance == d["instance"]
            and context.account == d["account"]
            and context.epoch == d["epoch"]
            and s.actor in d["actors"]
            and s.chat in self.targets
            and (s.is_group or s.chat == s.actor)
        )
