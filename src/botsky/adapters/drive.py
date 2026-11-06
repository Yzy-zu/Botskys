"""Cliente Drive acotado; R6 en construcción, sin conexión al despachador.

Adaptación técnica de Zhana drive.py; origen/hash en docs/portados/drive-origen.json.
Sin lectura de configuración o tokens antiguos. Scope obligatorio en archivos.
"""

import json
import os
import re
import stat
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

DRIVE_UPLOAD_BYTES = 2_000_000_000
MAX_FILE_BYTES = 16 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
_API = "https://www.googleapis.com/drive/v3"
_FIELDS = (
    "id,name,mimeType,size,webViewLink,parents,appProperties,trashed,capabilities(canAddChildren)"
)


class DriveError(Exception):
    def __init__(self, code: str, uncertain: bool = False, *, http_status: int | None = None):
        super().__init__(code)
        self.code = code
        self.uncertain = uncertain
        self.http_status = http_status


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    size: int | None
    web_view_link: str


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DriveError("invalid_file_id")
    return value


def _file(data: dict) -> DriveFile:
    try:
        fid = _identifier(data.get("id"))
        name, mime = data["name"], data["mimeType"]
        if not isinstance(name, str) or len(name) > 1024 or not isinstance(mime, str):
            raise ValueError()
        raw_size = data.get("size")
        if raw_size is not None and (
            not isinstance(raw_size, str)
            or not raw_size.isascii()
            or not raw_size.isdecimal()
            or len(raw_size) > 19
        ):
            raise ValueError()
        size = int(raw_size) if raw_size is not None else None
        if size is not None and not 0 <= size <= 2**63 - 1:
            raise ValueError()
        # Do not trust URLs supplied in metadata; derive an official view URL.
        return DriveFile(fid, name, mime, size, f"https://drive.google.com/file/d/{fid}/view")
    except KeyError, TypeError, ValueError:
        raise DriveError("invalid_provider_result") from None


class DriveClient:
    def __init__(self, folder_id=None, token_provider=None, *, client=None):
        self.folder_id = _identifier(folder_id) if folder_id else None
        self._token_provider = token_provider
        self.http = client or httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=20)
        self._owned = client is None

    @property
    def available(self):
        return bool(self.folder_id and self._token_provider)

    async def close(self):
        if self._owned:
            await self.http.aclose()

    async def _token(self):
        if not self.available:
            raise DriveError("drive_not_configured")
        access = await self._token_provider()
        if (
            not isinstance(access, str)
            or not access
            or len(access) > 16384
            or any(c in access for c in "\r\n")
        ):
            raise DriveError("invalid_oauth_response")
        return access

    @staticmethod
    def _json(response: httpx.Response, code: str = "drive_rejected") -> dict:
        if not 200 <= response.status_code < 300:
            raise DriveError("not_found" if response.status_code == 404 else code)
        if len(response.content) > 65536:
            raise DriveError("invalid_provider_result")
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except ValueError:
            raise DriveError("invalid_provider_result") from None

    async def _get(self, suffix: str, params: dict) -> dict:
        access = await self._token()
        try:
            async with self.http.stream(
                "GET",
                _API + suffix,
                params=params,
                headers={"Authorization": "Bearer " + access},
                follow_redirects=False,
            ) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 65536:
                        raise DriveError("invalid_provider_result")
                    content.extend(chunk)
                return self._json(httpx.Response(response.status_code, content=bytes(content)))
        except httpx.HTTPError:
            raise DriveError("drive_unavailable") from None

    async def storage_quota(self) -> dict[str, int | None]:
        data = await self._get(
            "/about", {"fields": "storageQuota(limit,usage,usageInDrive,usageInDriveTrash)"}
        )
        quota = data.get("storageQuota")
        if not isinstance(quota, dict):
            raise DriveError("invalid_provider_result")
        result: dict[str, int | None] = {}
        for field in ("limit", "usage", "usageInDrive", "usageInDriveTrash"):
            value = quota.get(field)
            if value is None:
                result[field] = None
            elif (
                isinstance(value, str)
                and value.isascii()
                and value.isdecimal()
                and len(value) <= 19
            ):
                number = int(value)
                if number > 2**63 - 1:
                    raise DriveError("invalid_provider_result")
                result[field] = number
            else:
                raise DriveError("invalid_provider_result")
        return result

    async def folder(self) -> DriveFile:
        data = await self._get(
            "/files/" + self.folder_id, {"fields": _FIELDS, "supportsAllDrives": "true"}
        )
        if (
            data.get("id") != self.folder_id
            or data.get("mimeType") != "application/vnd.google-apps.folder"
            or data.get("trashed") is not False
            or data.get("capabilities", {}).get("canAddChildren") is not True
        ):
            raise DriveError("folder_not_writable")
        return _file(data)

    async def search(self, query: str | None, *, scope_key: str | None = None) -> list[DriveFile]:
        self._scope(scope_key)
        if query is not None and (
            not isinstance(query, str) or not query.strip() or len(query) > 200
        ):
            raise DriveError("invalid_query")
        escaped = (
            query.strip().replace("\\", "\\\\").replace("'", "\\'") if query is not None else None
        )
        name_query = " and name contains '" + escaped + "'" if escaped is not None else ""
        scope_query = (
            ""
            if scope_key is None
            else " and appProperties has { key='botsky_scope' and value='" + scope_key + "' }"
        )
        data = await self._get(
            "/files",
            {
                "q": f"'{self.folder_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'"
                + name_query
                + scope_query,
                "fields": "files(" + _FIELDS + ")",
                "pageSize": 5,
                "orderBy": "modifiedTime desc",
            },
        )
        rows = data.get("files")
        if (
            not isinstance(rows, list)
            or len(rows) > 5
            or any(not isinstance(x, dict) for x in rows)
        ):
            raise DriveError("invalid_provider_result")
        if scope_key is not None and any(not self._matches_scope(x, scope_key) for x in rows):
            raise DriveError("file_outside_scope")
        return [_file(x) for x in rows]

    async def generate_id(self) -> str:
        data = await self._get(
            "/files/generateIds", {"count": 1, "space": "drive", "type": "files"}
        )
        ids = data.get("ids")
        if not isinstance(ids, list) or len(ids) != 1:
            raise DriveError("invalid_provider_result")
        return _identifier(ids[0])

    @staticmethod
    def _scope(scope_key: str | None) -> None:
        if not isinstance(scope_key, str) or not re.fullmatch(r"[a-f0-9]{64}", scope_key):
            raise DriveError("invalid_scope")

    def _matches_scope(self, data: dict, scope_key: str) -> bool:
        properties = data.get("appProperties")
        parents = data.get("parents")
        return (
            isinstance(parents, list)
            and self.folder_id in parents
            and isinstance(properties, dict)
            and properties.get("botsky_scope") == scope_key
            and data.get("trashed") is False
        )

    async def metadata(self, file_id: str, *, scope_key: str | None = None) -> DriveFile:
        self._scope(scope_key)
        data = await self._get(
            "/files/" + _identifier(file_id), {"fields": _FIELDS, "supportsAllDrives": "true"}
        )
        if (
            data.get("id") != file_id
            or data.get("trashed") is not False
            or self.folder_id not in data.get("parents", [])
        ):
            raise DriveError("file_outside_folder")
        if scope_key is not None and not self._matches_scope(data, scope_key):
            raise DriveError("file_outside_scope")
        return _file(data)

    async def upload(
        self,
        file_id: str,
        name: str,
        mime: str,
        data: bytes | Path,
        *,
        scope_key: str | None = None,
    ) -> DriveFile:
        self._scope(scope_key)
        file_id = _identifier(file_id)
        if isinstance(data, Path):
            try:
                fd = os.open(data, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as source:
                    info = os.fstat(source.fileno())
                    if not stat.S_ISREG(info.st_mode):
                        raise DriveError("file_too_large")
                    data_size = info.st_size
            except OSError:
                raise DriveError("file_too_large") from None
        elif isinstance(data, bytes):
            data_size = len(data)
        else:
            raise DriveError("file_too_large")
        if not 0 < data_size <= DRIVE_UPLOAD_BYTES:
            raise DriveError("file_too_large")
        if (
            not name
            or len(name) > 255
            or any(c in name for c in "\r\n/\\")
            or not re.fullmatch(r"[a-zA-Z0-9.+_-]+/[a-zA-Z0-9.+_-]+", mime)
        ):
            raise DriveError("invalid_file_metadata")
        access = await self._token()
        # Multipart-related, not form-data; generated ID is reserved durably by caller.
        import uuid

        boundary = "botsky-" + uuid.uuid4().hex
        fields: dict = {"id": file_id, "name": name, "parents": [self.folder_id]}
        if scope_key is not None:
            fields["appProperties"] = {"botsky_scope": scope_key}
        if isinstance(data, Path):
            return await self._upload_resumable(
                file_id, mime, data, data_size, fields, access, scope_key
            )
        metadata = json.dumps(fields).encode()
        prefix = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode()
        )
        suffix = f"\r\n--{boundary}--\r\n".encode()

        body = prefix + data + suffix
        try:
            r = await self.http.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                params={"uploadType": "multipart", "fields": _FIELDS, "supportsAllDrives": "true"},
                headers={
                    "Authorization": "Bearer " + access,
                    "Content-Type": "multipart/related; boundary=" + boundary,
                },
                content=body,
                timeout=3600,
                follow_redirects=False,
            )
            if 200 <= r.status_code < 300:
                try:
                    result = _file(self._json(r))
                    if (
                        result.id == file_id
                        and result.size == data_size
                        and self.folder_id in r.json().get("parents", [])
                        and (scope_key is None or self._matches_scope(r.json(), scope_key))
                    ):
                        return result
                except DriveError:
                    pass
                # A successful POST with malformed metadata still may have created the file.
                result = await self.metadata(file_id, scope_key=scope_key)
                if result.size != data_size:
                    raise DriveError("upload_uncertain", True)
                return result
            if r.status_code < 500 and r.status_code != 409:
                raise DriveError("upload_rejected")
        except httpx.HTTPError:
            pass
        except DriveError as exc:
            if exc.code == "upload_rejected":
                raise
            raise DriveError("upload_uncertain", True) from None
        try:
            result = await self.metadata(file_id, scope_key=scope_key)
            if result.size != data_size:
                raise DriveError("upload_uncertain", True)
            return result
        except DriveError:
            raise DriveError("upload_uncertain", True) from None

    async def _upload_resumable(
        self,
        file_id: str,
        mime: str,
        path: Path,
        size: int,
        fields: dict,
        access: str,
        scope_key: str | None,
    ) -> DriveFile:
        # One initialization POST and one content PUT. On ambiguity, only GET
        # the durably reserved ID; never start a second upload or resend content.
        async def chunks() -> AsyncGenerator[bytes]:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                    raise DriveError("upload_uncertain", True)
                remaining = size
                while remaining:
                    block = stream.read(min(192 * 1024, remaining))
                    if not block:
                        raise DriveError("upload_uncertain", True)
                    remaining -= len(block)
                    yield block

        body = chunks()
        try:
            init = await self.http.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                params={"uploadType": "resumable", "fields": _FIELDS, "supportsAllDrives": "true"},
                headers={
                    "Authorization": "Bearer " + access,
                    "X-Upload-Content-Type": mime,
                    "X-Upload-Content-Length": str(size),
                },
                json=fields,
                timeout=30,
                follow_redirects=False,
            )
            if not 200 <= init.status_code < 300:
                if 400 <= init.status_code < 500 and init.status_code != 409:
                    raise DriveError("upload_rejected")
                raise DriveError("upload_uncertain", True)
            location = init.headers.get("location", "")
            target = urlsplit(location)
            if (
                target.scheme != "https"
                or target.hostname != "www.googleapis.com"
                or target.port not in (None, 443)
                or target.username
                or target.password
                or target.path != "/upload/drive/v3/files"
                or target.fragment
            ):
                raise DriveError("upload_uncertain", True)
            response = await self.http.put(
                location,
                headers={
                    "Authorization": "Bearer " + access,
                    "Content-Type": mime,
                    "Content-Length": str(size),
                },
                content=body,
                timeout=3600,
                follow_redirects=False,
            )
            if 200 <= response.status_code < 300:
                payload = self._json(response)
                result = _file(payload)
                if (
                    result.id == file_id
                    and result.size == size
                    and self.folder_id in payload.get("parents", [])
                    and (scope_key is None or self._matches_scope(payload, scope_key))
                ):
                    return result
            elif 400 <= response.status_code < 500 and response.status_code != 409:
                raise DriveError("upload_rejected")
        except httpx.HTTPError, OSError, ValueError:
            pass
        except DriveError as exc:
            if exc.code == "upload_rejected":
                raise
        finally:
            await body.aclose()
        try:
            result = await self.metadata(file_id, scope_key=scope_key)
            if result.size == size:
                return result
        except DriveError:
            pass
        raise DriveError("upload_uncertain", True)

    async def upload_file(
        self, file_id: str, name: str, mime: str, path: Path, *, scope_key: str | None = None
    ) -> DriveFile:
        return await self.upload(file_id, name, mime, path, scope_key=scope_key)

    async def download(self, file_id: str, *, scope_key: str | None = None) -> bytes:
        meta = await self.metadata(file_id, scope_key=scope_key)
        if (
            meta.size is None
            or meta.size > MAX_FILE_BYTES
            or meta.size <= 0
            or meta.mime_type.startswith("application/vnd.google-apps.")
        ):
            raise DriveError("file_unsupported_or_too_large")
        access = await self._token()
        try:
            async with self.http.stream(
                "GET",
                _API + "/files/" + meta.id,
                params={"alt": "media", "supportsAllDrives": "true"},
                headers={"Authorization": "Bearer " + access},
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise DriveError("download_rejected")
                result = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(result) + len(chunk) > MAX_FILE_BYTES:
                        raise DriveError("file_too_large")
                    result.extend(chunk)
                if len(result) != meta.size:
                    raise DriveError("download_size_mismatch")
                return bytes(result)
        except httpx.HTTPError:
            raise DriveError("download_unavailable") from None
