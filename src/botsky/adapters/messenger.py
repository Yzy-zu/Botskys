"""Cliente acotado de recados Evolution, inyectado explícitamente y sin reintentos."""

import base64
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from ..domains.contacts import Contact


class MessageError(Exception):
    def __init__(self, code, uncertain=True):
        super().__init__(code)
        self.code, self.uncertain = code, uncertain


class Messenger:
    def __init__(self, base_url=None, instance=None, api_key=None, *, client=None):
        self.base_url = base_url.rstrip("/") if base_url else None
        if self.base_url:
            url = urlsplit(self.base_url)
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path
            ):
                raise ValueError("invalid_messenger_endpoint")
        self.instance, self._key = instance, api_key
        self.http = client or httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10)
        self._owned = client is None

    @property
    def available(self):
        return bool(self.base_url and self.instance and self._key)

    async def close(self):
        if self._owned:
            await self.http.aclose()

    async def send(self, target, kind, *, text="", path=None):
        if not self.available:
            raise MessageError("messenger_not_configured", False)
        Contact("destino", target)
        if kind == "text" and isinstance(text, str) and 0 < len(text) <= 4000:
            endpoint = "sendText"
            body = {"number": target, "text": text, "linkPreview": False}
        elif (
            kind == "asset"
            and isinstance(path, Path)
            and 0 < path.stat().st_size <= 10 * 1024 * 1024
        ):
            endpoint = "sendMedia"
            body = {
                "number": target,
                "mediatype": "document",
                "mimetype": "application/octet-stream",
                "fileName": "adjunto.bin",
                "media": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
        else:
            raise MessageError("invalid_message_part", False)
        return await self._post(endpoint, body)

    async def send_table(self, target, payload):
        from ..contracts import canonical
        from ..presentation.table import NativeTable

        try:
            Contact("destino", target)
            table = NativeTable.parse(payload)
        except ValueError:
            raise MessageError("native_table_invalid", False) from None
        body = {"number": target, "table": table.payload()}
        if not self.available or len(canonical(body).encode()) > 64 * 1024:
            raise MessageError("native_table_invalid", False)
        # La ruta puede haber enviado antes de fallar. Solo rechazos tipados
        # previos al relay son concluyentes; nunca fallback tras timeout.
        return await self._post("sendNativeTable", body, native_table=True)

    async def send_photo(self, target, data, mime, *, view_once=False, caption=""):
        if not self.available:
            raise MessageError("messenger_not_configured", False)
        try:
            Contact("destino", target)
        except ValueError:
            raise MessageError("photo_target_invalid", False) from None
        if (
            not isinstance(data, bytes)
            or not 0 < len(data) <= 10 * 1024 * 1024
            or mime not in ("image/jpeg", "image/png", "image/webp")
            or type(view_once) is not bool
            or not isinstance(caption, str)
            or len(caption) > 1000
        ):
            raise MessageError("photo_invalid", False)
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
        body = {
            "number": target,
            "mediatype": "image",
            "mimetype": mime,
            "fileName": "foto." + extension,
            "media": base64.b64encode(data).decode("ascii"),
            "viewOnce": view_once,
            "caption": caption,
        }
        return await self._post("sendMedia", body)

    async def send_reaction(self, target, message_id, reaction):
        if not self.available:
            raise MessageError("messenger_not_configured", False)
        Contact("destino", target)
        if not isinstance(message_id, str) or not message_id:
            raise MessageError("invalid_reaction_target", False)
        if not isinstance(reaction, str) or not reaction:
            raise MessageError("invalid_reaction_emoji", False)
        body = {
            "key": {
                "remoteJid": target,
                "fromMe": False,
                "id": message_id,
            },
            "reaction": reaction,
        }
        return await self._post("sendReaction", body)

    async def _post(self, endpoint, body, *, native_table=False):
        try:
            async with self.http.stream(
                "POST",
                self.base_url + "/message/" + endpoint + "/" + quote(self.instance, safe=""),
                headers={"apikey": self._key},
                json=body,
                follow_redirects=False,
                timeout=10,
            ) as response:
                if native_table and response.status_code == 404:
                    raise MessageError("native_table_unavailable", False)
                if (
                    not native_table
                    and 400 <= response.status_code < 500
                    and response.status_code != 409
                ):
                    raise MessageError("message_rejected", False)
                if not 200 <= response.status_code < 300 and not (
                    native_table and response.status_code == 400
                ):
                    raise MessageError("message_uncertain")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 65536:
                        raise MessageError("message_invalid_ack")
                    content.extend(chunk)
                import json

                result = json.loads(content)
                if native_table and response.status_code == 400:
                    if isinstance(result, dict) and result.get("code") in (
                        "NATIVE_TABLE_INVALID",
                        "NATIVE_TABLE_UNSUPPORTED",
                    ):
                        raise MessageError("native_table_rejected", False)
                    raise MessageError("message_uncertain")
                identifier = result.get("key", {}).get("id")
                if not isinstance(identifier, str) or not identifier or len(identifier) > 256:
                    raise MessageError("message_invalid_ack")
                return identifier
        except httpx.HTTPError, ValueError, TypeError, AttributeError:
            raise MessageError("message_uncertain") from None
