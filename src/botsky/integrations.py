"""Composición optativa con secretos propios importados por encargo explícito.

No lee Zhana, entorno global, DB ajena ni sesiones. Servicios solo al invocar serve.
"""

import json
import os
import stat
from pathlib import Path

import httpx

from .adapters.calls import CallsClient
from .adapters.downloads import NetworkDownloads
from .adapters.drive import DriveClient, DriveError
from .adapters.gallery import PublishedLibrary
from .adapters.gemini import GeminiContent
from .adapters.groups import GroupError, Groups
from .adapters.messenger import MessageError, Messenger
from .adapters.minecraft import MinecraftConfig, MinecraftRemote, MinecraftRemoteError
from .adapters.oauth import OAuthToken
from .adapters.tts import EdgeTTS
from .adapters.web import NetworkWeb
from .adapters.whisper import WhisperProvider
from .app import Application
from .domains.contacts import Contact, Directory
from .operational import OperationalPolicy, PermissionGate


def read_profile(path):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        mode = os.fstat(stream.fileno())
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077 or mode.st_size > 65536:
            raise ValueError("integration_profile_permissions")
        value = json.load(stream)
    allowed = {
        "version",
        "gemini",
        "asr",
        "evolution",
        "tts",
        "downloads",
        "web",
        "contacts",
        "minecraft",
        "live",
        "drive",
        "call_service",
        "mutations_enabled",
        "runtime",
        "permissions",
    }
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value.get("version") != 1
        or set(value) - allowed
    ):
        raise ValueError("integration_profile_invalid")
    if (
        any(not isinstance(value.get(k), dict) for k in ("gemini", "asr", "evolution", "drive"))
        or type(value.get("mutations_enabled", False)) is not bool
    ):
        raise ValueError("integration_profile_invalid")
    if set(value["gemini"]) != {"key", "model"} or not all(
        isinstance(v, str) and v.strip() for v in value["gemini"].values()
    ):
        raise ValueError("single_explicit_gemini_required")
    for key in ("live", "call_service", "runtime"):
        if key in value and not isinstance(value[key], dict):
            raise ValueError("integration_profile_invalid")
    if "live" in value and (
        set(value["live"]) != {"key", "model"}
        or not all(isinstance(v, str) and v.strip() for v in value["live"].values())
    ):
        raise ValueError("single_explicit_live_required")
    for block, keys in (
        (value["evolution"], ("delivery_enabled", "native_tables_enabled")),
        (value.get("call_service", {}), ("enabled", "allow_browser_launch", "agenda_timers")),
    ):
        if any(k in block and type(block[k]) is not bool for k in keys):
            raise ValueError("integration_profile_invalid")
    return value


class Integrations:
    def __init__(self, settings, profile, *, http=None):
        self.settings = settings
        self.path = Path(profile).absolute()
        self.profile = read_profile(self.path)
        self.policy = OperationalPolicy.build(self.profile, settings)
        self.http = http or httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=20)
        self._owned_http = http is None
        self.app = None
        self.call_process = None

    async def __aenter__(self):
        p = self.profile
        try:
            gemini = GeminiContent(p["gemini"]["key"], p["gemini"]["model"])
            asr = WhisperProvider(
                self.http, p["asr"].get("key", ""), p["asr"].get("model", "whisper-large-v3-turbo")
            )
            e = p["evolution"]
            messenger = Messenger(
                e.get("base_url"), e.get("instance"), e.get("api_key"), client=self.http
            )
            groups = Groups(
                e.get("base_url"),
                e.get("instance"),
                e.get("api_key"),
                self.settings.bot_ids,
                client=self.http,
            )
            m = p.get("minecraft", {})
            minecraft = (
                MinecraftRemote(MinecraftConfig(**m))
                if all(m.get(k) for k in ("host_alias", "container", "base_path", "worker_path"))
                else None
            )
            oauth = OAuthToken(self.path.parent.parent, client=self.http)
            drive = (
                DriveClient(p["drive"].get("folder_id"), oauth, client=self.http)
                if p["drive"].get("folder_id")
                else None
            )
            permissions = self.policy.document

            def message_target(target, *args, **kwargs):
                return (
                    permissions["messages"]["send"] and target in permissions["messages"]["targets"]
                )

            photo_targets = {
                self.settings.owner,
                *self.settings.friends,
                *permissions["gallery"]["chats"],
            }

            def photo_target(target, *args, **kwargs):
                return permissions["gallery"]["send"] and target in photo_targets

            photo_transport = PermissionGate(
                messenger,
                {"send_photo": photo_target},
                MessageError,
                available=permissions["gallery"]["send"],
            )
            messenger = PermissionGate(
                messenger,
                {"send": message_target, "send_photo": False},
                MessageError,
                available=permissions["messages"]["send"],
            )

            def group_read(group, *args, **kwargs):
                return permissions["groups"]["read"] and group in permissions["groups"]["chats"]

            def group_write(group, *args, **kwargs):
                return permissions["groups"]["write"] and group in permissions["groups"]["chats"]

            groups = PermissionGate(
                groups,
                {
                    "snapshot": group_read,
                    "invite_link": group_read,
                    "change": group_write,
                    "setting": group_write,
                },
                GroupError,
                available=permissions["groups"]["read"],
            )
            if minecraft:
                minecraft = PermissionGate(
                    minecraft,
                    {
                        "query": permissions["minecraft"]["read"],
                        "change": permissions["minecraft"]["write"],
                        "change_validated": permissions["minecraft"]["write"],
                    },
                    MinecraftRemoteError,
                )
            if drive:
                drive = PermissionGate(
                    drive,
                    {
                        **dict.fromkeys(
                            ("storage_quota", "folder", "search", "metadata", "download"),
                            permissions["drive"]["read"],
                        ),
                        **dict.fromkeys(
                            ("generate_id", "upload", "upload_file"), permissions["drive"]["write"]
                        ),
                    },
                    DriveError,
                    available=permissions["drive"]["read"],
                )
            contacts = Directory(
                tuple(
                    Contact(v["name"], v["jid"], tuple(v.get("aliases", ())))
                    for v in p.get("contacts", ())
                )
            )
            self.app = Application(
                self.settings,
                gemini=gemini,
                tts=EdgeTTS(enabled=p.get("tts", {}).get("enabled", False)),
                asr=asr,
                drive=drive,
                directory=contacts,
                messenger=messenger,
                groups=groups,
                minecraft=minecraft,
                downloads=NetworkDownloads(**p.get("downloads", {})),
                web=NetworkWeb(**p.get("web", {})),
                calls=self.calls_client(),
                operations=self.policy,
                gallery=PublishedLibrary(self.settings.root)
                if permissions["gallery"]["enabled"]
                else None,
                photo_transport=photo_transport,
                gallery_chats=permissions["gallery"]["chats"],
                roulette_chats=permissions["roulette"]["chats"],
                allow_roulette_admins=permissions["roulette"]["allow_admins"],
                nuclear_enabled=permissions["nuclear"]["enabled"],
            )
            return self.app
        except BaseException:
            await self.aclose()
            raise

    def calls_client(self, base_url=None):
        c = self.profile.get("call_service", {})
        if c.get("enabled", False) is not True:
            return None
        if set(c) - {
            "enabled",
            "mode",
            "base_url",
            "token",
            "port",
            "executable",
            "allow_browser_launch",
            "agenda_timers",
        } or c.get("mode", "external") not in ("external", "managed"):
            raise ValueError("call_service_configuration_invalid")
        if self.settings.calls is None or self.settings.transport != "evolution":
            raise ValueError("call_policy_required")
        if c.get("mode") == "managed" and base_url is None:
            return None  # starting services is reserved to the explicit serve command
        return CallsClient(
            self.http,
            base_url or c.get("base_url", ""),
            c.get("token", ""),
            self.settings.calls.revision,
            self.settings.calls.targets,
        )

    async def start_calls(self):
        c = self.profile.get("call_service", {})
        if c.get("enabled") is not True:
            return
        if c.get("mode") == "managed":
            from .call_service import ManagedCalls

            self.call_process = ManagedCalls(self.settings, c, self.profile.get("live"))
            self.app.calls = self.calls_client(await self.call_process.start())
        status = await self.app.calls.status()
        health = await self.app.calls.health()
        if (
            status.get("policyRevision") != self.settings.calls.revision
            or health.get("ready") is not True
        ):
            raise ValueError("call_service_not_ready")

    async def aclose(self):
        try:
            if self.call_process:
                await self.call_process.close()
        finally:
            if self._owned_http:
                await self.http.aclose()

    async def __aexit__(self, *args):
        await self.aclose()
