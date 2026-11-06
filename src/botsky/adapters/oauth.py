"""Refresh OAuth explícito en almacenamiento propio; sin descubrir claves o sesiones."""

import asyncio
import json
import math
import os
import stat
import tempfile
import time
from pathlib import Path

import httpx

from ..local_files import private_directory
from .drive import DriveError


def read_secret(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 65536:
                raise ValueError()
            data = json.loads(source.read(65537))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except OSError, ValueError:
        raise DriveError("oauth_private_file_invalid") from None


class OAuthToken:
    def __init__(self, root, credentials="client.json", tokens="token.json", *, client=None):
        self.directory = private_directory(Path(root), "private/drive")
        for name in (credentials, tokens):
            if not isinstance(name, str) or Path(name).name != name or name in (".", ".."):
                raise ValueError("oauth_filename_invalid")
        self.credentials_path, self.tokens_path = (
            self.directory / credentials,
            self.directory / tokens,
        )
        self.http = client or httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=20)
        self._owned = client is None
        self._access, self._expires = None, 0
        self._lock = asyncio.Lock()

    async def close(self):
        if self._owned:
            await self.http.aclose()

    def persist(self, tokens):
        descriptor, name = tempfile.mkstemp(prefix=".token-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w") as target:
                json.dump(tokens, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, self.tokens_path)
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            raise DriveError("oauth_storage_error") from None
        finally:
            Path(name).unlink(missing_ok=True)

    async def __call__(self):
        async with self._lock:
            if self._access and time.monotonic() < self._expires:
                return self._access
            credentials = read_secret(self.credentials_path)
            tokens = read_secret(self.tokens_path)
            values = (
                credentials.get("client_id"),
                credentials.get("client_secret"),
                tokens.get("refresh_token"),
            )
            if not all(
                isinstance(v, str) and 0 < len(v) <= 16384 and not any(c in v for c in "\r\n")
                for v in values
            ):
                raise DriveError("oauth_credentials_invalid")
            try:
                async with self.http.stream(
                    "POST",
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": values[0],
                        "client_secret": values[1],
                        "refresh_token": values[2],
                    },
                    follow_redirects=False,
                ) as response:
                    if response.status_code != 200:
                        raise DriveError("oauth_refresh_rejected")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > 65536:
                            raise DriveError("oauth_invalid_response")
                        content.extend(chunk)
                    data = json.loads(content)
                access = data.get("access_token")
                expiry = data.get("expires_in", 3600)
                if (
                    not isinstance(access, str)
                    or not 0 < len(access) <= 16384
                    or any(c in access for c in "\r\n")
                    or type(expiry) not in (float, int)
                    or not math.isfinite(expiry)
                    or expiry <= 0
                ):
                    raise DriveError("oauth_invalid_response")
                refresh = data.get("refresh_token", values[2])
                if not isinstance(refresh, str) or not refresh or len(refresh) > 16384:
                    raise DriveError("oauth_invalid_response")
                self.persist({"refresh_token": refresh})
                self._access, self._expires = (
                    access,
                    time.monotonic() + max(0, min(expiry, 3600) - 60),
                )
                return access
            except httpx.HTTPError, ValueError, AttributeError, TypeError:
                raise DriveError("oauth_unavailable") from None
