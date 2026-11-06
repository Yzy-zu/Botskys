"""API de grupos Evolution acotada; identidades/roles comprobados, sin transporte activo."""

import json
import re
from urllib.parse import quote, urlsplit

import httpx


class GroupError(Exception):
    def __init__(self, code, uncertain=False):
        self.code, self.uncertain = code, uncertain
        super().__init__(code)


def identity(value, group=False):
    pattern = r"[0-9-]{5,40}@g\.us" if group else r"[A-Za-z0-9_-]{1,128}@(s\.whatsapp\.net|lid)"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError("group_identity_invalid")
    if not group and value.endswith("@s.whatsapp.net"):
        number = value.split("@")[0]
        if not number.isascii() or not number.isdecimal() or not 5 <= len(number) <= 20:
            raise ValueError("group_phone_invalid")
        if len(number) == 13 and number.startswith("521"):
            return "52" + number[3:] + "@s.whatsapp.net"
    return value


class Groups:
    def __init__(self, base_url=None, instance=None, api_key=None, bot_ids=(), *, client=None):
        self.base_url = base_url.rstrip("/") if base_url else None
        if self.base_url:
            url = urlsplit(self.base_url)
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.path
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("group_endpoint_invalid")
        self.instance, self._key = instance, api_key
        self.bot_ids = frozenset(identity(v) for v in bot_ids)
        self.http = client or httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=15)
        self._owned = client is None

    @property
    def available(self):
        return bool(self.base_url and self.instance and self._key and self.bot_ids)

    async def close(self):
        if self._owned:
            await self.http.aclose()

    async def _request(self, method, endpoint, group, body=None):
        if not self.available:
            raise GroupError("groups_not_configured")
        group = identity(group, True)
        try:
            async with self.http.stream(
                method,
                self.base_url + "/group/" + endpoint + "/" + quote(self.instance, safe=""),
                params={"groupJid": group} if method == "GET" else None,
                json={"groupJid": group, **(body or {})} if method == "POST" else None,
                headers={"apikey": self._key},
                follow_redirects=False,
                timeout=15,
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise GroupError(
                        "group_rejected", method == "POST" and not 400 <= response.status_code < 500
                    )
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 128 * 1024:
                        raise GroupError("group_response_too_large", method == "POST")
                    content.extend(chunk)
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError()
                return data
        except httpx.HTTPError, ValueError:
            raise GroupError("group_response_unknown", method == "POST") from None

    async def snapshot(self, group):
        data = await self._request("GET", "findGroupInfos", group)
        data = data.get("group", data)
        if (
            not isinstance(data, dict)
            or identity(data.get("id"), True) != identity(group, True)
            or not isinstance(data.get("participants"), list)
            or len(data["participants"]) > 512
        ):
            raise GroupError("group_metadata_invalid")
        members = []
        seen = set()
        for raw in data["participants"]:
            if not isinstance(raw, dict):
                raise GroupError("group_member_invalid")
            target = identity(raw.get("id"))
            aliases = {
                identity(raw[k]) for k in ("id", "phoneNumber", "lid") if raw.get(k) is not None
            }
            phones = {v for v in aliases if v.endswith("@s.whatsapp.net")}
            if len(phones) > 1 or seen & aliases:
                raise GroupError("group_identity_conflict")
            role = raw.get("admin", "MISSING")
            if role is None:
                admin = False
            elif role in ("admin", "superadmin"):
                admin = True
            elif role in ("member", "participant"):
                admin = False
            elif type(raw.get("isAdmin")) is bool:
                admin = raw["isAdmin"]
            else:
                raise GroupError("group_role_unknown")
            if "isAdmin" in raw and (type(raw["isAdmin"]) is not bool or raw["isAdmin"] != admin):
                raise GroupError("group_role_conflict")
            seen.update(aliases)
            phone = next(iter(phones), None)
            members.append(
                {
                    "actor": phone or target,
                    "id": target,
                    "phone": phone,
                    "aliases": sorted(aliases),
                    "admin": admin,
                }
            )
        return {
            "group_id": identity(group, True),
            "bot_is_admin": any(p["admin"] and self.bot_ids & set(p["aliases"]) for p in members),
            "participants": members,
            "announcement": data.get("announce") if type(data.get("announce")) is bool else None,
            "locked": data.get("restrict") if type(data.get("restrict")) is bool else None,
        }

    async def invite_link(self, group):
        data = await self._request("GET", "inviteCode", group)
        code = data.get("inviteCode", data.get("code"))
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", code):
            raise GroupError("group_invite_invalid")
        return "https://chat.whatsapp.com/" + code

    async def change(self, group, action, target):
        if action not in ("remove", "promote", "demote"):
            raise ValueError("group_action_invalid")
        target = identity(target)
        info = await self.snapshot(group)
        if not info["bot_is_admin"] or not any(
            target in p["aliases"] for p in info["participants"]
        ):
            return "failed"
        member = next(p for p in info["participants"] if target in p["aliases"])
        if self.bot_ids & set(member["aliases"]) or action == "remove" and member["admin"]:
            return "failed"
        try:
            data = await self._request(
                "POST", "updateParticipant", group, {"action": action, "participants": [target]}
            )
        except GroupError as exc:
            return "uncertain" if exc.uncertain else "failed"
        rows = data.get("updateParticipants")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            return "uncertain"
        try:
            if identity(rows[0].get("jid")) != target:
                return "uncertain"
        except ValueError:
            return "uncertain"
        status = rows[0].get("status")
        if status in (200, "200", "success", "ok"):
            return "accepted"
        if str(status) in ("400", "401", "403", "404", "405", "406", "409"):
            return "failed"
        return "uncertain"

    async def setting(self, group, setting, enabled):
        if setting not in ("announcement", "locked") or type(enabled) is not bool:
            raise ValueError("group_setting_invalid")
        before = await self.snapshot(group)
        if not before["bot_is_admin"]:
            return "failed"
        action = (
            ("announcement" if enabled else "not_announcement")
            if setting == "announcement"
            else ("locked" if enabled else "unlocked")
        )
        try:
            await self._request("POST", "updateSetting", group, {"action": action})
            after = await self.snapshot(group)
        except GroupError as exc:
            return "uncertain" if exc.uncertain else "failed"
        return "accepted" if after[setting] is enabled else "uncertain"
