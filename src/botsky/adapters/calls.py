"""Bounded local calls-service client. This module never starts a service or a call on import."""

import asyncio
import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from ..contracts import Scope

_KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
_CALL_ID = re.compile(r"[A-Za-z0-9-]{1,80}\Z")
_REVISION = re.compile(r"[a-f0-9]{64}\Z")
_NOTICE_LEASE = re.compile(r"[a-f0-9-]{36}\Z")
_MAX_RESPONSE = 64 * 1024
# Only explicit protocol codes cross this boundary, never service messages.
_SERVICE_ERRORS = {
    "POLICY_MISMATCH": "policy_mismatch",
    "CANCELLED": "cancelled",
    "KEY_CONFLICT": "key_conflict",
    "CALL_BUSY": "busy",
    "DESTINATION_NOT_ENABLED": "not_allowed",
    "CALL_DESTINATION_DENIED": "not_allowed",
    "OUTGOING_DISABLED": "calls_disabled",
    "LIVE_DISABLED": "calls_disabled",
}


def _valid_call(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("id"), str)
        and _CALL_ID.fullmatch(value["id"]) is not None
        and isinstance(value.get("state"), str)
        and 0 < len(value["state"]) <= 64
    )


class CallsError(Exception):
    """Stable code only: provider messages and response bodies never escape as errors."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CallRequest:
    key: str
    origin: Scope
    target_ref: str
    mode: Literal["live", "prepared_audio"]
    video: bool = False
    topic: str | None = None
    audio_id: str | None = None
    max_seconds: int = 300
    source_receipt: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key):
            raise ValueError("Invalid request key")
        if not self.target_ref or not self.origin.chat or not self.origin.actor:
            raise ValueError("Missing resolved identity")
        if self.mode not in ("live", "prepared_audio") or not isinstance(self.video, bool):
            raise ValueError("Invalid call mode")
        if self.mode == "live" and self.audio_id is not None:
            raise ValueError("Live cannot use prepared audio")
        if self.mode == "prepared_audio" and (not self.audio_id or self.topic or self.video):
            raise ValueError("Invalid prepared audio call")
        if (
            not isinstance(self.max_seconds, int)
            or isinstance(self.max_seconds, bool)
            or not 5 <= self.max_seconds <= 3600
        ):
            raise ValueError("Invalid call duration")
        if self.topic is not None and (not self.topic.strip() or len(self.topic) > 8000):
            raise ValueError("Invalid call topic")
        if self.source_receipt is not None:
            if (
                not isinstance(self.source_receipt, dict)
                or set(self.source_receipt) != {"chatId", "messageKey"}
                or self.source_receipt.get("chatId") != self.origin.chat
                or not isinstance(self.source_receipt.get("messageKey"), dict)
            ):
                raise ValueError("Invalid call source receipt")


class CallsClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: str,
        policy_revision: str,
        allowed_targets: frozenset[str],
        *,
        all_groups_enabled: bool = False,
        is_fixture: bool = False,
        timeout: float = 8.0,
        max_seconds: int = 3600,
    ) -> None:
        url = urlsplit(base_url)
        try:
            loopback = (
                url.hostname == "localhost" or ipaddress.ip_address(url.hostname or "").is_loopback
            )
        except ValueError:
            loopback = False
        if (
            url.scheme != "http"
            or not loopback
            or url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError("Calls service must use a loopback HTTP origin")
        if not token or "\n" in token or "\r" in token or not _REVISION.fullmatch(policy_revision):
            raise ValueError("Invalid calls credentials or policy revision")
        if (
            not isinstance(all_groups_enabled, bool)
            or not 0 < timeout <= 30
            or not allowed_targets
            or not 5 <= max_seconds <= 3600
        ):
            raise ValueError("Invalid calls client configuration")
        if type(is_fixture) is not bool:
            raise ValueError("Explicit fixture flag required")
        self.is_fixture = is_fixture
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._revision = policy_revision
        self._targets = allowed_targets
        if all_groups_enabled:
            raise ValueError("Botsky requires explicit destination allowlists")
        self._all_groups_enabled = False
        self._timeout = timeout
        self._max_seconds = max_seconds

    @property
    def policy_revision(self) -> str:
        return self._revision

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Authorization": f"Bearer {self._token}", **(headers or {})}
        try:
            async with asyncio.timeout(self._timeout):
                async with self._client.stream(
                    method,
                    self._base_url + path,
                    json=payload,
                    headers=request_headers,
                    params=params,
                    follow_redirects=False,
                    timeout=self._timeout,
                ) as response:
                    data = bytearray()
                    async for part in response.aiter_bytes():
                        data.extend(part)
                        if len(data) > _MAX_RESPONSE:
                            raise CallsError("invalid_provider_result")
                    if not 200 <= response.status_code < 300:
                        code = {
                            401: "not_allowed",
                            403: "not_allowed",
                            404: "not_found",
                            409: "busy",
                            429: "rate_limited",
                        }.get(response.status_code, "provider_unavailable")
                        try:
                            error_body = json.loads(data)
                            error = (
                                error_body.get("error") if isinstance(error_body, dict) else None
                            )
                            remote_code = error.get("code") if isinstance(error, dict) else None
                            if isinstance(remote_code, str):
                                code = _SERVICE_ERRORS.get(remote_code, code)
                        except ValueError, UnicodeError:
                            pass
                        raise CallsError(code)
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise CallsError("invalid_provider_result")
                    return result
        except CallsError:
            raise
        except httpx.HTTPError, TimeoutError, ValueError, UnicodeError:
            raise CallsError("provider_unavailable") from None

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/status")

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/healthz")

    async def operation(self, key: str) -> dict[str, Any]:
        if not _KEY.fullmatch(key):
            raise ValueError("Invalid request key")
        result = await self._request("GET", "/v1/calls/by-key", params={"key": key})
        if (
            "call" not in result
            or not isinstance(result.get("cancelled"), bool)
            or not (result.get("call") is None or _valid_call(result.get("call")))
        ):
            raise CallsError("invalid_provider_result")
        return result

    async def start(self, request: CallRequest) -> dict[str, Any]:
        try:
            return await self._start(request)
        except asyncio.CancelledError:
            # Includes cancellation during reconciliation after an uncertain POST.
            try:
                await asyncio.shield(self.cancel_preparation(request.key))
            except CallsError, asyncio.CancelledError:
                pass
            raise

    async def _start(self, request: CallRequest) -> dict[str, Any]:
        if request.max_seconds > self._max_seconds:
            raise CallsError("not_allowed")
        if request.target_ref != request.origin.chat or request.target_ref not in self._targets:
            raise CallsError("not_allowed")
        payload: dict[str, Any] = {
            "inputTransport": "local" if self.is_fixture else "evolution",
            "targetJid": request.target_ref,
            "origin": {"chatId": request.origin.chat, "requesterId": request.origin.actor},
            "live": request.mode == "live",
            "video": request.video,
            "maxSeconds": request.max_seconds,
        }
        if request.topic is not None:
            payload["liveRequest"] = request.topic
        if request.source_receipt is not None:
            payload["sourceReceipt"] = request.source_receipt
        if request.audio_id is not None:
            payload["audioId"] = request.audio_id
        try:
            result = await self._request(
                "POST",
                "/v1/calls",
                payload=payload,
                headers={
                    "Idempotency-Key": request.key,
                    "X-Call-Job-Key": request.key,
                    "X-Calls-Policy-Revision": self._revision,
                },
            )
        except CallsError as exc:
            if exc.code not in ("provider_unavailable", "invalid_provider_result"):
                raise
            # A lost response may already have dispatched the offer. Never retry POST.
            try:
                observed = await self.operation(request.key)
            except CallsError:
                raise CallsError("delivery_uncertain") from None
            if observed["call"] is not None or observed["cancelled"]:
                return observed
            raise CallsError("delivery_uncertain") from None
        if not _valid_call(result.get("call")):
            try:
                observed = await self.operation(request.key)
            except CallsError:
                raise CallsError("delivery_uncertain") from None
            if observed["call"] is not None or observed["cancelled"]:
                return observed
            raise CallsError("delivery_uncertain")
        return result

    async def cancel_preparation(self, key: str) -> dict[str, Any]:
        if not _KEY.fullmatch(key):
            raise ValueError("Invalid request key")
        try:
            result = await self._request("POST", "/v1/calls/cancel", payload={"key": key})
            if result.get("cancelled") is not True:
                raise CallsError("invalid_provider_result")
            return result
        except CallsError as exc:
            if exc.code not in ("provider_unavailable", "invalid_provider_result"):
                raise
            try:
                observed = await self.operation(key)
            except CallsError:
                raise CallsError("delivery_uncertain") from None
            if observed["cancelled"]:
                return observed
            raise CallsError("delivery_uncertain") from None

    async def call_by_id(self, call_id: str) -> dict[str, Any]:
        if not _CALL_ID.fullmatch(call_id):
            raise ValueError("A valid call ID is required")
        result = await self._request("GET", "/v1/calls/by-id", params={"callId": call_id})
        if (
            not _valid_call(result.get("call"))
            or not isinstance(result.get("key"), str)
            or not _KEY.fullmatch(result["key"])
        ):
            raise CallsError("invalid_provider_result")
        return result

    async def cancel_call(self, call_id: str, *, only_preparing: bool = False) -> dict[str, Any]:
        if not _CALL_ID.fullmatch(call_id):
            raise ValueError("A valid call ID is required")
        try:
            payload: dict[str, Any] = {"callId": call_id}
            if only_preparing:
                payload["onlyPreparing"] = True
            result = await self._request("POST", "/v1/calls/cancel-by-id", payload=payload)
        except CallsError as exc:
            if exc.code in ("provider_unavailable", "invalid_provider_result"):
                raise CallsError("delivery_uncertain") from None
            raise
        if result.get("cancelled") is not True and not (
            only_preparing and result.get("cancelled") is False and result.get("skipped") is True
        ):
            raise CallsError("delivery_uncertain")
        return result

    async def hangup(self, call_id: str) -> dict[str, Any]:
        if not _CALL_ID.fullmatch(call_id):
            raise ValueError("A valid call ID is required")
        return await self._request("POST", "/v1/hangup", payload={"callId": call_id})

    async def claim_failure_notices(self) -> list[dict[str, Any]]:
        """Claim at most one validated origin receipt from the calls journal."""
        result = await self._request("POST", "/v1/notices/claim", payload={})
        notices = result.get("notices")
        if not isinstance(notices, list) or len(notices) > 1:
            raise CallsError("invalid_provider_result")
        validated = []
        for notice in notices:
            if (
                not isinstance(notice, dict)
                or set(notice) != {"callId", "lease", "chatId", "requesterId", "messageKey"}
                or not isinstance(notice.get("callId"), str)
                or not _CALL_ID.fullmatch(notice["callId"])
                or not isinstance(notice.get("lease"), str)
                or not _NOTICE_LEASE.fullmatch(notice["lease"])
                or not isinstance(notice.get("chatId"), str)
                or len(notice["chatId"]) > 128
                or not isinstance(notice.get("requesterId"), str)
                or len(notice["requesterId"]) > 128
            ):
                raise CallsError("invalid_provider_result")
            key = notice["messageKey"]
            if (
                not isinstance(key, dict)
                or set(key) - {"id", "remoteJid", "fromMe", "participant"}
                or not isinstance(key.get("id"), str)
                or not key["id"]
                or len(key["id"]) > 200
                or not isinstance(key.get("remoteJid"), str)
                or not key["remoteJid"]
                or key.get("fromMe") is not False
                or (
                    "participant" in key
                    and (not isinstance(key["participant"], str) or len(key["participant"]) > 128)
                )
            ):
                raise CallsError("invalid_provider_result")
            validated.append(notice)
        return validated

    async def begin_failure_notice(self, call_id: str, lease: str) -> bool:
        if not _CALL_ID.fullmatch(call_id) or not _NOTICE_LEASE.fullmatch(lease):
            raise ValueError("A valid call ID and notice lease are required")
        result = await self._request(
            "POST", "/v1/notices/begin", payload={"callId": call_id, "lease": lease}
        )
        if not isinstance(result.get("begun"), bool):
            raise CallsError("invalid_provider_result")
        return result["begun"]

    async def ack_failure_notice(self, call_id: str, lease: str, outcome: str) -> None:
        if not _CALL_ID.fullmatch(call_id) or not _NOTICE_LEASE.fullmatch(lease):
            raise ValueError("A valid call ID and notice lease are required")
        if outcome not in {"accepted", "failed", "uncertain", "rejected"}:
            raise ValueError("A valid notice outcome is required")
        result = await self._request(
            "POST",
            "/v1/notices/ack",
            payload={"callId": call_id, "lease": lease, "outcome": outcome},
        )
        if result.get("acknowledged") is not True:
            raise CallsError("invalid_provider_result")

    async def command(self, action, payload=None, *, key=None):
        routes = {
            "agenda.create": "/v1/schedules",
            "agenda.list": "/v1/schedules/list",
            "agenda.update": "/v1/schedules/update",
            "agenda.cancel": "/v1/schedules/cancel",
            "agenda.get": "/v1/schedules/get",
            "clip.list": "/v1/clips",
            "clip.play": "/v1/clips/play",
            "clip.command": "/v1/clips/command",
            "avatar.control": "/v1/avatar/control",
        }
        if action not in routes or (key is not None and not _KEY.fullmatch(key)):
            raise ValueError("Invalid audiovisual operation")
        headers = {"X-Calls-Policy-Revision": self._revision}
        if key is not None:
            headers["Idempotency-Key"] = key
        payload = dict(payload or {})
        if action == "agenda.create":
            payload["inputTransport"] = "local" if self.is_fixture else "evolution"
        return await self._request(
            "GET" if action == "clip.list" else "POST",
            routes[action],
            payload=None if action == "clip.list" else payload,
            headers=headers,
        )
