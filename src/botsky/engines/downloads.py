# Componente técnico de Zhana 7e12d54; origen y límites en docs/portados/motores-origen.json.
"""Bounded downloads from a small, unauthenticated source allowlist."""

import asyncio
import html
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, quote_plus, urljoin, urlsplit

import httpx

from .formats import FORMAT_TARGETS
from .limits import (
    MAX_VIDEO_BYTES,
    MAX_VIDEO_SOURCE_BYTES,
    MEDIA_INPUT_BYTES,
    MULTIMEDIA_CHOICES,
)
from .media_edit import MediaEditor, MediaOptions
from .process import MediaError, run_process

MAX_BYTES = 16 * 1024 * 1024
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_W3_PATH = "/2010/05/bunny/trailer.mp4"
DownloadSource = Literal[
    "youtube",
    "w3",
    "xnxx",
    "pornhub",
    "dailymotion",
    "vimeo",
    "spotify",
    "facebook",
    "instagram",
    "tiktok",
]
SOCIAL_SOURCES = frozenset({"facebook", "instagram", "tiktok"})


def _social_url(host: str, path: str, query: str) -> str | None:
    """Accept single public video references, never profile/catalog/login URLs."""
    params = parse_qs(query, keep_blank_values=True, strict_parsing=True)
    if host in {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"}:
        if path in {"/watch", "/watch/", "/video.php"}:
            video = params.get("v", [])
            if len(video) == 1 and re.fullmatch(r"[0-9]+", video[0]):
                return f"https://www.facebook.com/watch/?v={video[0]}"
        if re.fullmatch(
            r"/(?:reel/[0-9]+|share/[vr]/[A-Za-z0-9]+|[A-Za-z0-9_.-]+/videos/(?:[A-Za-z0-9_-]+/)?[0-9]+)/?",
            path,
        ):
            return f"https://www.facebook.com{path}"
    if host == "fb.watch" and re.fullmatch(r"/[A-Za-z0-9_-]+/?", path):
        return f"https://fb.watch{path}"
    if host in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
        if "img_index" in params:
            return None
        if re.fullmatch(r"/(?:p|reel|reels|tv|share/reel)/[A-Za-z0-9_-]+/?", path):
            return f"https://www.instagram.com{path}"
    if host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
        if re.fullmatch(r"/(?:@[A-Za-z0-9_.]+/video/[0-9]+|t/[A-Za-z0-9]+)/?", path):
            return f"https://www.tiktok.com{path}"
    if host in {"vm.tiktok.com", "vt.tiktok.com"}:
        if re.fullmatch(r"/[A-Za-z0-9]+/?", path):
            return f"https://{host}{path}"
    return None


def _social_short_url(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.hostname in {"fb.watch", "vm.tiktok.com", "vt.tiktok.com"}
        or (parts.hostname == "www.facebook.com" and parts.path.startswith("/share/"))
        or (parts.hostname == "www.tiktok.com" and parts.path.startswith("/t/"))
        or (parts.hostname == "www.instagram.com" and parts.path.startswith("/share/"))
    )


@dataclass(frozen=True)
class DownloadOption:
    url: str
    title: str
    duration: float | None = None
    author: str | None = None
    thumbnail_url: str | None = None


class SearchOptions(tuple[DownloadOption, ...]):
    """Options with source failure metadata, scoped to a single search."""

    failed_sources: tuple[str, ...]

    def __new__(
        cls, options: tuple[DownloadOption, ...], failed_sources: tuple[str, ...] = ()
    ) -> SearchOptions:
        result = super().__new__(cls, options)
        result.failed_sources = failed_sources
        return result


SEARCH_ADULT_KEYWORDS = (
    r"videos?\s+nopor",
    r"video\s+nopor",
    r"videos?\s+porno?",
    r"video\s+porno?",
    r"videos?\s+xxx",
    r"videos?\s+de\s+sexo",
    r"videos?\s+er[oó]ticos?",
    r"porno\s+de",
    r"nopor\s+de",
    r"nopor",
    r"porno?",
    r"porn",
    r"xxx+",
    r"nsfw",
    r"rule\s*34",
    r"hentai",
    r"ecchi",
    r"er[oó]tico[sa]?",
    r"pornhub",
    r"xnxx",
    r"xvideos",
    r"redtube",
    r"youporn",
    r"brazzers",
    r"onlyfans",
    r"chaturbate",
)

SEARCH_FILLER_PATTERNS = (
    r"^\s*(?:oye\s+)?(?:por\s+fa(?:vor)?\s+)?(?:busca(?:r)?|encuentra|pon(?:me)?|quiero\s+ver|mu[eé]strame|dame)\s+",
    r"^\s*(?:videos?|rolas?|cancion(?:es)?|tracks?|audios?)\s+(?:de|del|sobre|en)\s+",
    r"\b(?:en|de|por|para)?\s*(?:youtube|yt)\b",
    r"\b(?:en\s+)?(?:formato\s+)?(?:mp4|mp3|webm|srt)\b",
    r"\b(?:en\s+)?(?:hd|1080p|720p|4k)\b",
)


def sanitize_search_query(query: str, source: str = "youtube") -> str:
    original = query.strip()
    text = original
    if source in ("adult", "pornhub", "xnxx", "combined"):
        for pattern in SEARCH_ADULT_KEYWORDS:
            text = re.sub(r"\b" + pattern + r"\b", " ", text, flags=re.IGNORECASE)
    for pattern in SEARCH_FILLER_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:videos?|audios?)\s+(?:de|del)?\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:cancion(?:es)?|rolas?|tracks?)\s+(?:de|del)?\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:de|del|en|para|sobre|con)\s+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:en|de|del|para|sobre|con|por)\s*$", "", text, flags=re.IGNORECASE)
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        if source in ("adult", "pornhub", "xnxx", "combined"):
            return "popular"
        return original
    return cleaned


def clean_display_title(title: str) -> str:
    t = html.unescape(title).strip()
    t = re.sub(
        r"[\s\-_|]*(?:aplica\s+el\s+c[oó]digo|c[oó]digo\s+[a-z0-9]+).*$",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"[\s\-_|]*videos?\s+completos?\s+en\s+enlace.*$", "", t, flags=re.IGNORECASE
    )
    t = re.sub(r"[\s\-_|]*sub\s+espa[ñn]ol.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^[A-Za-z0-9_]+\s*4K\s*\|\s*", "", t)
    words = t.split()
    if (
        len(words) >= 4
        and sum(1 for w in words if w.isupper() and len(w) > 1) / len(words) > 0.5
    ):
        t = t.capitalize()
    t = " ".join("".join(c for c in t if c.isprintable() or c.isspace()).split())[:300]
    return t.strip(" -_|:,")


def validate_download_url(url: str) -> str:
    try:
        if len(url) > 2000 or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
            raise ValueError
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.username is not None or parts.password is not None:
            raise ValueError
        if parts.port is not None or parts.fragment or not parts.hostname:
            raise ValueError
        host = parts.hostname.lower()
        if parts.netloc.lower() != host:
            raise ValueError
        social = _social_url(host, parts.path, parts.query)
        if social is not None:
            return social
        if host == "media.w3.org" and parts.path == _W3_PATH and not parts.query:
            return f"https://media.w3.org{_W3_PATH}"
        if host in ("dailymotion.com", "www.dailymotion.com") and not parts.query:
            if re.fullmatch(r"/video/[A-Za-z0-9]+", parts.path):
                return f"https://www.dailymotion.com{parts.path}"
        if host == "dai.ly" and not parts.query:
            if re.fullmatch(r"/[A-Za-z0-9]+", parts.path):
                return f"https://www.dailymotion.com/video{parts.path}"
        if host in ("vimeo.com", "www.vimeo.com") and not parts.query:
            if re.fullmatch(r"/[0-9]+", parts.path):
                return f"https://vimeo.com{parts.path}"
        if host in ("xnxx.com", "www.xnxx.com", "video.xnxx.com", "xnxx.es", "www.xnxx.es"):
            match = re.fullmatch(r"/video-?([0-9a-z]+)/([A-Za-z0-9_-]*)", parts.path)
            if not match or parts.query:
                raise ValueError
            return f"https://www.xnxx.com/video-{match[1]}/{match[2]}"
        if host in ("pornhub.com", "www.pornhub.com", "fr.pornhub.com", "es.pornhub.com"):
            if parts.path == "/view_video.php":
                query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
                if set(query) != {"viewkey"} or len(query["viewkey"]) != 1:
                    raise ValueError
                video_id = query["viewkey"][0]
                if parts.query != f"viewkey={video_id}":
                    raise ValueError
            else:
                match = re.fullmatch(r"/embed/([0-9a-z]+)", parts.path)
                if not match or parts.query:
                    raise ValueError
                video_id = match[1]
            if not re.fullmatch(r"[0-9a-z]+", video_id):
                raise ValueError
            return f"https://www.pornhub.com/view_video.php?viewkey={video_id}"
        if host in ("youtube.com", "www.youtube.com", "m.youtube.com") and parts.path == "/watch":
            query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
            if (
                set(query) - {"v", "si", "feature"}
                or len(query.get("v", [])) != 1
                or any(
                    len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", values[0])
                    for key, values in query.items()
                    if key != "v"
                )
            ):
                raise ValueError
            video_id = query["v"][0]
        elif host == "youtu.be" and parts.path.count("/") == 1:
            query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
            if set(query) - {"si", "feature"} or any(
                len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", values[0])
                for values in query.values()
            ):
                raise ValueError
            video_id = parts.path[1:]
        else:
            raise ValueError
        if not _VIDEO_ID.fullmatch(video_id):
            raise ValueError
        return f"https://www.youtube.com/watch?v={video_id}"
    except (ValueError, TypeError) as exc:
        raise MediaError("unsupported_url") from exc


def validate_spotify_url(url: str) -> str:
    try:
        if len(url) > 2000 or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
            raise ValueError
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "open.spotify.com" or parts.fragment:
            raise ValueError
        query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
        if set(query) - {"si"} or any(
            len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", values[0])
            for values in query.values()
        ):
            raise ValueError
        match = re.fullmatch(r"/(?:intl-[a-z]{2}/)?track/([A-Za-z0-9]{22})", parts.path)
        if not match:
            raise ValueError
        return f"https://open.spotify.com/track/{match[1]}"
    except (ValueError, TypeError) as exc:
        raise MediaError("unsupported_url") from exc


def is_spotify_url(url: str) -> bool:
    try:
        validate_spotify_url(url)
        return True
    except MediaError:
        return False


def download_source(url: str) -> DownloadSource:
    host = urlsplit(validate_download_url(url)).hostname
    if host in {"www.facebook.com", "fb.watch"}:
        return "facebook"
    if host == "www.instagram.com":
        return "instagram"
    if host in {"www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}:
        return "tiktok"
    if host == "www.dailymotion.com":
        return "dailymotion"
    if host == "vimeo.com":
        return "vimeo"
    if host == "media.w3.org":
        return "w3"
    if host in ("www.xnxx.com", "xnxx.com", "www.xnxx.es", "xnxx.es"):
        return "xnxx"
    if host in ("www.pornhub.com", "pornhub.com", "es.pornhub.com", "fr.pornhub.com"):
        return "pornhub"
    return "youtube"


def _allowed_host(host: str, source: DownloadSource | None = None) -> bool:
    youtube = any(
        host == domain or host.endswith("." + domain)
        for domain in (
            "youtube.com",
            "youtube-nocookie.com",
            "googlevideo.com",
            "ytimg.com",
            "youtubei.googleapis.com",
            "youtube.googleapis.com",
        )
    )
    # CDN hosts observed in yt-dlp issue reports; unknown edges fail closed.
    xnxx = host in ("xnxx.com", "www.xnxx.com", "video.xnxx.com", "xnxx.es", "www.xnxx.es") or bool(
        re.match(r"^[a-z0-9_-]+\.xnxx-cdn\.com$", host)
    )
    pornhub = bool(
        re.match(
            r"^(?:[a-z]v|[a-z]v-[a-z0-9]+|pix-[a-z0-9]+|di-[a-z0-9]+|ci-[a-z0-9]+|ei-[a-z0-9]+|bi-[a-z0-9]+|ai-[a-z0-9]+|hls-[a-z0-9]+|[a-z0-9]+-vid)\.phncdn\.com$",
            host,
        )
    ) or host in (
        "pornhub.com",
        "www.pornhub.com",
        "fr.pornhub.com",
        "es.pornhub.com",
        "ev.phncdn.com",
        "ev-h.phncdn.com",
        "iv-h.phncdn.com",
        "pix-fl.phncdn.com",
        "di-fl.phncdn.com",
        "ci.phncdn.com",
        "ei.phncdn.com",
        "bi.phncdn.com",
        "ai.phncdn.com",
        "phncdn.com",
    )
    dailymotion = host in (
        "www.dailymotion.com",
        "dailymotion.com",
        "dai.ly",
        "geo.dailymotion.com",
        "graphql.api.dailymotion.com",
        "cdndirector.dailymotion.com",
        "vod3.cf.dmcdn.net",
        "www.dmcdn.net",
        "proxy-01.dailymotion.com",
    )
    vimeo = host in (
        "vimeo.com",
        "www.vimeo.com",
        "player.vimeo.com",
        "api.vimeo.com",
        "vod-progressive.akamaized.net",
    )

    def domain(*roots: str) -> bool:
        return any(host == root or host.endswith("." + root) for root in roots)

    facebook = domain("facebook.com", "fb.watch", "fbcdn.net")
    instagram = domain("instagram.com", "cdninstagram.com", "fbcdn.net")
    tiktok = domain(
        "tiktok.com",
        "tiktokv.com",
        "tiktokcdn.com",
        "tiktokcdn-us.com",
        "tiktokcdn-eu.com",
        "byteoversea.com",
        "ibytedtos.com",
        "ibyteimg.com",
        "muscdn.com",
        "musical.ly",
    )
    if source is None:
        return youtube or host == "media.w3.org"
    return {
        "youtube": youtube,
        "w3": host == "media.w3.org",
        "xnxx": xnxx,
        "pornhub": pornhub,
        "dailymotion": dailymotion,
        "vimeo": vimeo,
        "spotify": host == "open.spotify.com",
        "facebook": facebook,
        "instagram": instagram,
        "tiktok": tiktok,
    }[source]


MAX_WORKSPACE_BYTES = MAX_VIDEO_SOURCE_BYTES


def _workspace_size(workspace: Path, max_bytes: int = MAX_BYTES) -> int:
    total = 0
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise MediaError("input_size")
        if path.is_file():
            total += path.stat().st_size
            if total > max_bytes:
                raise MediaError("input_size")
    return total


def youtube_failure_code(stderr: bytes) -> str:
    """Map bounded extractor diagnostics to content-free codes, never user language."""
    text = stderr.decode("utf-8", errors="replace").casefold()
    if (
        "sign in to confirm you’re not a bot" in text
        or "sign in to confirm you're not a bot" in text
    ):
        return "source_verification_required"
    if "http error 429" in text:
        return "source_rate_limited"
    if "private video" in text or "sign in to confirm your age" in text:
        return "source_auth_required"
    if "this video is unavailable" in text or "video unavailable" in text:
        return "source_content_unavailable"
    if "requested format is not available" in text:
        return "source_format_unavailable"
    return "source_failed"


def social_failure_code(stderr: bytes) -> str:
    """Interpret only extractor diagnostics; retain no page or source identifiers."""
    text = stderr.decode("utf-8", errors="replace").casefold()
    if "ip address is blocked" in text:
        return "social_access_blocked"
    if "http error 429" in text or "rate-limit" in text:
        return "social_rate_limited"
    if any(
        marker in text
        for marker in (
            "login required",
            "log in",
            "login to",
            "sign in",
            "private video",
            "registered users",
        )
    ):
        return "social_auth_required"
    if "requested format is not available" in text:
        return "social_format_unavailable"
    return "source_failed"


def adult_failure_code(stderr: bytes) -> str:
    """Content-free extractor diagnostics; never return URLs, titles or output."""
    text = stderr.decode('utf-8', errors='replace').casefold()
    if 'http error 403' in text or '403 forbidden' in text:
        return 'source_access_denied'
    if 'http error 404' in text or 'video has been removed' in text:
        return 'source_content_unavailable'
    if 'impersonat' in text and ('not available' in text or 'unavailable' in text):
        return 'source_client_unavailable'
    if any(marker in text for marker in ('unable to download', 'connection reset', 'connection refused', 'timed out', 'name resolution')):
        return 'source_network_failed'
    return youtube_failure_code(stderr)


async def _bounded_network_process(
    args: list[str],
    workspace: Path,
    max_bytes: int = MAX_BYTES,
    timeout_seconds: int = 180,
    failure_code: Callable[[bytes], str] | None = None,
) -> None:
    """Cancel the process group if the total download workspace exceeds the limit."""
    task = asyncio.create_task(
        run_process(
            args,
            timeout_seconds,
            env={"PATH": os.environ.get("PATH", "")},
            failure_code=failure_code,
        )
    )
    try:
        while True:
            _workspace_size(workspace, max_bytes)
            done, _ = await asyncio.wait({task}, timeout=0.25)
            if done:
                await task
                _workspace_size(workspace, max_bytes)
                return
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@asynccontextmanager
async def _proxy(source: DownloadSource | None = None) -> AsyncIterator[str]:
    """CONNECT-only proxy: restrict hosts and pin each connection to public DNS results."""
    tasks: set[asyncio.Task[None]] = set()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        remote: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(10):
                header = await reader.readuntil(b"\r\n\r\n")
                if len(header) > 8192:
                    return
                line = header.split(b"\r\n", 1)[0].decode("ascii").split(" ")
                if len(line) != 3 or line[0] != "CONNECT" or line[2] != "HTTP/1.1":
                    return
                host, port = line[1].rsplit(":", 1)
                if port != "443" or not _allowed_host(host.lower(), source) or host != host.lower():
                    return
                infos = await asyncio.get_running_loop().getaddrinfo(
                    host, 443, type=socket.SOCK_STREAM
                )
                addresses = [info[4][0] for info in infos]
                if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
                    return
                rr, remote = await asyncio.open_connection(addresses[0], 443)
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await writer.drain()

            async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
                while data := await src.read(65536):
                    dst.write(data)
                    await dst.drain()

            await asyncio.gather(pump(reader, remote), pump(rr, writer))
        except (
            OSError,
            ValueError,
            UnicodeError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
        ):
            pass
        finally:
            if remote is not None:
                remote.close()
            writer.close()

    def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(handle(reader, writer))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    server = await asyncio.start_server(accept, "127.0.0.1", 0, limit=8193)
    try:
        assert server.sockets
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    finally:
        server.close()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await server.wait_closed()


def _parse_clock_duration(text: str) -> float | None:
    parts = text.strip().split(":")
    try:
        if len(parts) == 2:
            secs = int(parts[0]) * 60 + int(parts[1])
            return float(secs) if 0 < secs <= 14400 else None
        if len(parts) == 3:
            secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return float(secs) if 0 < secs <= 14400 else None
    except ValueError:
        return None
    return None


def _parse_xnxx_duration(text: str) -> float | None:
    h_m = re.search(r"(\d+)\s*h", text)
    min_m = re.search(r"(\d+)\s*min", text)
    sec_m = re.search(r"(\d+)\s*sec", text)
    if not (h_m or min_m or sec_m):
        return None
    total = 0.0
    if h_m:
        total += int(h_m.group(1)) * 3600
    if min_m:
        total += int(min_m.group(1)) * 60
    if sec_m:
        total += int(sec_m.group(1))
    return total if 0 < total <= 14400 else None


class Downloader:
    def __init__(self, root: Path, *, adult_sources_enabled: bool = False) -> None:
        self.adult_sources_enabled = adult_sources_enabled
        self.root = root.resolve()
        self.work = self.root / "work"
        self.artifacts = self.root / "artifacts"
        for directory in (self.root, self.work, self.artifacts):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self._leases: dict[Path, int] = {}
        self._pending: set[Path] = set()

    async def available(self) -> bool:
        return all(shutil.which(tool) for tool in ("yt-dlp", "ffmpeg", "ffprobe", "prlimit"))

    def _owned(self, path: Path) -> Path:
        candidate = Path(os.path.abspath(path))
        if (
            candidate.parent != self.artifacts
            or candidate.is_symlink()
            or candidate.suffix
            not in {
                ".mp3",
                ".mp4",
                ".webm",
                ".srt",
                ".ogg",
                ".zip",
                ".bin",
                *("." + fmt for fmt in FORMAT_TARGETS),
            }
        ):
            raise MediaError("not_owned")
        try:
            if uuid.UUID(hex=candidate.stem).hex != candidate.stem:
                raise ValueError
        except ValueError as exc:
            raise MediaError("not_owned") from exc
        return candidate

    def release(self, path: Path) -> None:
        owned = self._owned(path)
        if self._leases.get(owned, 0):
            self._pending.add(owned)
        else:
            owned.unlink(missing_ok=True)
            self._pending.discard(owned)

    @asynccontextmanager
    async def lease(self, path: Path) -> AsyncIterator[Path]:
        owned = self._owned(path)
        if owned in self._pending or not owned.is_file():
            raise MediaError("artifact_unavailable")
        self._leases[owned] = self._leases.get(owned, 0) + 1
        try:
            yield owned
        finally:
            self._leases[owned] -= 1
            if not self._leases[owned]:
                del self._leases[owned]
                if owned in self._pending:
                    self.release(owned)

    def sweep(self, referenced: set[Path] | None = None) -> None:
        keep = set(self._leases)
        for path in referenced or set():
            try:
                keep.add(self._owned(path))
            except MediaError:
                continue
        for path in (
            *self.work.glob("download-*"),
            *self.work.glob("subtitle-*"),
            *self.work.glob("speech-*"),
            *self.work.glob("document-*"),
        ):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
        for path in self.artifacts.iterdir():
            try:
                owned = self._owned(path)
            except MediaError:
                continue
            if owned not in keep:
                owned.unlink(missing_ok=True)

    def _base(
        self,
        proxy: str,
        source: DownloadSource = "youtube",
        *,
        max_bytes: int = MAX_BYTES,
    ) -> list[str]:
        return [
            "prlimit",
            f"--fsize={max_bytes}",
            "--",
            "yt-dlp",
            "--ignore-config",
            "--no-plugin-dirs",
            "--no-js-runtimes",
            "--no-remote-components",
            "--no-cache-dir",
            "--no-cookies",
            "--no-cookies-from-browser",
            "--use-extractors",
            {
                "youtube": "youtube,youtube:search",
                "xnxx": "xnxx",
                "pornhub": "pornhub",
                "w3": "",
                "dailymotion": "dailymotion",
                "vimeo": "vimeo",
                "spotify": "",
                "facebook": "facebook,facebook:reel",
                "instagram": "instagram",
                "tiktok": "tiktok",
            }[source],
            "--proxy",
            proxy,
            "--no-playlist",
            "--no-progress",
            "--no-warnings",
            "--retries",
            "0",
            "--socket-timeout",
            "10",
        ]

    async def search(
        self, query: str, source: DownloadSource | Literal["combined"] = "youtube"
    ) -> tuple[DownloadOption, ...]:
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise MediaError("invalid_query")
        if source in ("pornhub", "xnxx", "combined") and not self.adult_sources_enabled:
            raise MediaError("unsupported_source")
        clean_query = sanitize_search_query(query, source)
        if source == "combined":
            return await self.search_combined(clean_query)
        if source == "pornhub":
            return await self._search_pornhub(clean_query)
        if source == "xnxx":
            return await self._search_xnxx(clean_query)
        return await self._search_youtube(clean_query)

    async def search_combined(self, query: str) -> tuple[DownloadOption, ...]:
        clean_query = sanitize_search_query(query, "combined")
        results = await asyncio.gather(
            self._search_pornhub(clean_query),
            self._search_xnxx(clean_query),
            return_exceptions=True,
        )
        failed_sources = tuple(
            source
            for source, result in zip(("Pornhub", "XNXX"), results, strict=True)
            if isinstance(result, BaseException)
        )
        logging.getLogger(__name__).info(
            "search_combined completed_sources=%d failed_sources=%d",
            2 - len(failed_sources),
            len(failed_sources),
        )
        ph_options: tuple[DownloadOption, ...] = results[0] if isinstance(results[0], tuple) else ()
        xn_options: tuple[DownloadOption, ...] = results[1] if isinstance(results[1], tuple) else ()
        combined: list[DownloadOption] = []
        max_len = max(len(ph_options), len(xn_options))
        for i in range(max_len):
            if i < len(ph_options):
                combined.append(ph_options[i])
            if len(combined) >= MULTIMEDIA_CHOICES:
                break
            if i < len(xn_options):
                combined.append(xn_options[i])
            if len(combined) >= MULTIMEDIA_CHOICES:
                break
        if not combined and failed_sources:
            raise MediaError("search_failed")
        return SearchOptions(tuple(combined[:MULTIMEDIA_CHOICES]), failed_sources)

    async def _search_youtube(self, query: str) -> tuple[DownloadOption, ...]:
        clean_query = sanitize_search_query(query, "youtube")
        try:
            async with asyncio.timeout(120), _proxy("youtube") as proxy:
                output = await run_process(
                    self._base(proxy)
                    + ["--flat-playlist", "--dump-single-json", "--", f"ytsearch20:{clean_query}"],
                    115,
                    env={"PATH": os.environ.get("PATH", "")},
                )
            data = json.loads(output)
            options: list[DownloadOption] = []
            for item in data.get("entries", [])[:20]:
                if not isinstance(item, dict) or item.get("ie_key") not in (None, "Youtube"):
                    continue
                if (
                    item.get("is_live") is True
                    or item.get("live_status") in {"is_live", "is_upcoming"}
                    or item.get("availability") not in {None, "public", "unlisted"}
                ):
                    continue
                video_id = item.get("id")
                title = item.get("title")
                duration = item.get("duration")
                author = item.get("channel") or item.get("uploader")
                author = (
                    " ".join("".join(c for c in author if c.isprintable() or c.isspace()).split())[
                        :160
                    ]
                    if isinstance(author, str)
                    else None
                )
                if (
                    not isinstance(video_id, str)
                    or not _VIDEO_ID.fullmatch(video_id)
                    or not isinstance(title, str)
                    or not title.strip()
                ):
                    continue
                if duration is not None and (
                    isinstance(duration, bool)
                    or not isinstance(duration, (int, float))
                    or not 0 < duration <= 14400
                ):
                    continue
                thumb_url = (
                    item.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
                )
                options.append(
                    DownloadOption(
                        f"https://www.youtube.com/watch?v={video_id}",
                        " ".join(title.split())[:300],
                        float(duration) if duration is not None else None,
                        author or None,
                        thumbnail_url=thumb_url,
                    )
                )
                if len(options) == MULTIMEDIA_CHOICES:
                    break
            logging.getLogger(__name__).info(
                "search_youtube candidates=%d accepted=%d",
                len(data.get("entries", [])[:20]),
                len(options),
            )
            if not options and data.get("entries"):
                raise MediaError("search_filtered")
            return tuple(options)
        except (ValueError, TypeError, AttributeError, TimeoutError) as exc:
            raise MediaError("search_failed") from exc

    async def _search_pornhub(self, query: str) -> tuple[DownloadOption, ...]:
        clean_query = sanitize_search_query(query, "pornhub")
        query_stems = [w.lower().rstrip("s") for w in clean_query.split() if len(w) > 2]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "es-MX,es;q=0.9,es-ES;q=0.8,en;q=0.1",
            "Cookie": "accessAgeDisclaimerPH=1; platform=pc; language=es; il=es",
        }
        # Direct web HTML parsing from videoBoxesSearch using es.pornhub.com with &o=mv (Most Viewed / popular)
        try:
            async with asyncio.timeout(15), _proxy("pornhub") as proxy:
                async with httpx.AsyncClient(proxy=proxy, trust_env=False, timeout=10, headers=headers) as client:
                    resp = await client.get(
                        f"https://es.pornhub.com/video/search?search={quote_plus(clean_query)}&o=mv"
                    )
                    if resp.status_code == 200:
                        chunks = (
                            resp.text.split("videoBoxesSearch")[1:]
                            if "videoBoxesSearch" in resp.text
                            else resp.text.split('class="videoBox"')[1:]
                        )
                        preferred: list[DownloadOption] = []
                        others: list[DownloadOption] = []
                        seen_urls: set[str] = set()
                        for b_html in chunks:
                            vk_m = re.search(
                                r'data-video-vkey="([a-zA-Z0-9]+)"', b_html
                            ) or re.search(r"viewkey=([a-zA-Z0-9]+)", b_html)
                            if not vk_m:
                                continue
                            vk = vk_m.group(1)
                            try:
                                valid_url = validate_download_url(
                                    f"https://www.pornhub.com/view_video.php?viewkey={vk}"
                                )
                            except MediaError:
                                continue
                            if valid_url in seen_urls:
                                continue

                            title_m = (
                                re.search(
                                    r'<span class="title"[^>]*>.*?<a[^>]+title="([^"]+)"',
                                    b_html,
                                    re.DOTALL,
                                )
                                or re.search(
                                    r'<a[^>]+href="/view_video\.php\?viewkey=[^"]+"[^>]+title="([^"]+)"',
                                    b_html,
                                )
                                or re.search(
                                    r'<a[^>]+class="[^"]*linkVideoThumb[^"]*"[^>]+title="([^"]+)"',
                                    b_html,
                                )
                            )
                            if not title_m:
                                continue
                            raw_title = html.unescape(title_m.group(1)).strip()
                            title = clean_display_title(raw_title)
                            if not title:
                                continue

                            dur_m = re.search(
                                r'<var[^>]+class="[^"]*duration[^"]*"[^>]*>([^<]+)</var>', b_html
                            )
                            duration = _parse_clock_duration(dur_m.group(1)) if dur_m else None

                            user_m = re.search(
                                r'class="usernameWrap"[^>]*>.*?<a[^>]*>([^<]+)</a>',
                                b_html,
                                re.DOTALL,
                            )
                            raw_author = html.unescape(user_m.group(1)) if user_m else ""
                            author = (
                                " ".join(
                                    "".join(
                                        c for c in raw_author if c.isprintable() or c.isspace()
                                    ).split()
                                )[:160]
                                or None
                            )

                            img_m = re.search(
                                r'<img[^>]+src="([^" ]+\.phncdn\.com/[^" ]+)"', b_html
                            ) or re.search(
                                r'data-(?:image|src|medium|mediumthumb)="([^" ]+\.phncdn\.com/[^" ]+)"',
                                b_html,
                            )
                            thumb = html.unescape(img_m.group(1)) if img_m else None

                            seen_urls.add(valid_url)
                            opt = DownloadOption(
                                valid_url, title, duration, author, thumbnail_url=thumb
                            )
                            has_kw = (
                                any(
                                    st in title.lower() or (author and st in author.lower())
                                    for st in query_stems
                                )
                                if query_stems
                                else True
                            )
                            if has_kw and (duration is None or (isinstance(duration, (int, float)) and 0 < duration <= 1800)):
                                preferred.append(opt)
                            else:
                                others.append(opt)
                        direct_options = (preferred + others)[:MULTIMEDIA_CHOICES]
                        if direct_options:
                            return tuple(direct_options)
        except Exception:
            pass

        # Fallback to extractor
        try:
            async with asyncio.timeout(120), _proxy("pornhub") as proxy:
                cmd = self._base(proxy, "pornhub")
                ext_idx = cmd.index("--use-extractors")
                cmd[ext_idx + 1] = "pornhub,PornHubPagedVideoList"
                cmd.extend(
                    [
                        "--flat-playlist",
                        "--dump-single-json",
                        "--playlist-items",
                        "1:6",
                        f"https://es.pornhub.com/video/search?search={quote_plus(clean_query)}&o=mv",
                    ]
                )
                output = await run_process(cmd, 115, env={"PATH": os.environ.get("PATH", "")})
            data = json.loads(output)
            thumb_map: dict[str, str] = {}
            dur_map: dict[str, float] = {}
            author_map: dict[str, str] = {}
            try:
                async with asyncio.timeout(15), _proxy("pornhub") as proxy:
                    async with httpx.AsyncClient(
                        proxy=proxy, trust_env=False, timeout=10, headers=headers
                    ) as client:
                        resp = await client.get(
                            f"https://es.pornhub.com/video/search?search={quote_plus(clean_query)}&o=mv"
                        )
                        if resp.status_code == 200:
                            for box in re.finditer(
                                r'<li[^>]+class="[^"]*videoBox[^"]*".*?</li>',
                                resp.text,
                                re.DOTALL,
                            ):
                                b_html = box.group(0)
                                vk_m = re.search(
                                    r'data-video-vkey="([a-zA-Z0-9]+)"', b_html
                                ) or re.search(r"viewkey=([a-zA-Z0-9]+)", b_html)
                                if not vk_m:
                                    continue
                                vk = vk_m.group(1)
                                img_m = re.search(
                                    r'<img[^>]+src="([^" ]+\.phncdn\.com/[^" ]+)"', b_html
                                ) or re.search(
                                    r'data-(?:medium|src|image)="([^" ]+\.phncdn\.com/[^" ]+)"',
                                    b_html,
                                )
                                if img_m:
                                    thumb_map[vk] = html.unescape(img_m.group(1))
                                dur_m = re.search(r'<var class="duration">([^<]+)</var>', b_html)
                                if dur_m:
                                    parsed_dur = _parse_clock_duration(dur_m.group(1))
                                    if parsed_dur is not None:
                                        dur_map[vk] = parsed_dur
                                user_m = re.search(
                                    r'class="usernameWrap"[^>]*>.*?<a[^>]*>([^<]+)</a>',
                                    b_html,
                                    re.DOTALL,
                                )
                                if user_m:
                                    raw_author = html.unescape(user_m.group(1))
                                    clean_author = " ".join(
                                        "".join(
                                            c for c in raw_author if c.isprintable() or c.isspace()
                                        ).split()
                                    )[:160]
                                    if clean_author:
                                        author_map[vk] = clean_author
            except Exception:
                pass
            options: list[DownloadOption] = []
            for item in data.get("entries", [])[:MULTIMEDIA_CHOICES]:
                if not isinstance(item, dict):
                    continue
                raw_url = item.get("url")
                raw_title = item.get("title")
                if (
                    not isinstance(raw_url, str)
                    or not isinstance(raw_title, str)
                    or not raw_title.strip()
                ):
                    continue
                url = "https://" + raw_url[7:] if raw_url.startswith("http://") else raw_url
                try:
                    valid_url = validate_download_url(url)
                except MediaError:
                    continue
                title = html.unescape(raw_title)
                title = " ".join(
                    "".join(c for c in title if c.isprintable() or c.isspace()).split()
                )[:300]
                if not title:
                    continue
                vk_match = re.search(r"viewkey=([a-zA-Z0-9]+)", valid_url)
                vk = vk_match.group(1) if vk_match else None
                duration = item.get("duration")
                if duration is not None and not (
                    isinstance(duration, (int, float))
                    and not isinstance(duration, bool)
                    and 0 < duration <= 14400
                ):
                    duration = None
                if duration is None and vk and vk in dur_map:
                    duration = dur_map[vk]
                uploader = item.get("uploader") or item.get("channel")
                author = (
                    " ".join(
                        "".join(c for c in uploader if c.isprintable() or c.isspace()).split()
                    )[:160]
                    if isinstance(uploader, str)
                    else None
                )
                if author is None and vk and vk in author_map:
                    author = author_map[vk]
                thumb = thumb_map.get(vk) if vk else None
                options.append(
                    DownloadOption(
                        valid_url,
                        title,
                        float(duration) if duration is not None else None,
                        author or None,
                        thumbnail_url=thumb,
                    )
                )
            return tuple(options)
        except (ValueError, TypeError, AttributeError, TimeoutError) as exc:
            raise MediaError("search_failed") from exc

    async def _search_xnxx(self, query: str) -> tuple[DownloadOption, ...]:
        clean_query = sanitize_search_query(query, "xnxx")
        query_stems = [w.lower().rstrip("s") for w in clean_query.split() if len(w) > 2]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "es-MX,es;q=0.9,es-ES;q=0.8,en;q=0.1",
        }
        try:
            async with asyncio.timeout(60), _proxy("xnxx") as proxy:
                async with httpx.AsyncClient(
                    proxy=proxy, trust_env=False, timeout=20, follow_redirects=True, headers=headers
                ) as client:
                    resp = await client.get(
                        f"https://www.xnxx.es/search/hits/{quote_plus(clean_query)}"
                    )
                    if resp.status_code != 200:
                        resp = await client.get(
                            f"https://www.xnxx.com/search/hits/{quote_plus(clean_query)}"
                        )
                    if resp.status_code != 200:
                        raise MediaError("search_failed")
                    html_text = resp.text
            if '<div id="video_' in html_text:
                chunks = html_text.split('<div id="video_')[1:]
                preferred: list[DownloadOption] = []
                others: list[DownloadOption] = []
                seen_urls: set[str] = set()
                for c in chunks:
                    path_m = re.search(r'href="(/video-[0-9a-z]+/[A-Za-z0-9_-]*)"', c)
                    if not path_m:
                        continue
                    path = path_m.group(1)
                    title_m = re.search(
                        r'<a[^>]+href="/video-[^"]+"[^>]+title="([^"]+)"', c
                    ) or re.search(r'title="([^"]*)"', c)
                    title_raw = title_m.group(1) if title_m else ""
                    title = clean_display_title(title_raw)
                    if not title:
                        continue
                    try:
                        valid_url = validate_download_url(f"https://www.xnxx.com{path}")
                    except MediaError:
                        continue
                    if not title or valid_url in seen_urls:
                        continue
                    meta_m = re.search(r'<p class="metadata">(.*?)</p>', c, re.DOTALL)
                    duration = _parse_xnxx_duration(meta_m.group(1)) if meta_m else None
                    author_m = re.search(
                        r'class="uploader"[^>]*>.*?<span class="name">([^<]+)</span>', c, re.DOTALL
                    ) or re.search(
                        r'class="uploader"[^>]*>.*?<a[^>]*>(?:<span[^>]*>)?([^<]+)', c, re.DOTALL
                    )
                    raw_author = html.unescape(author_m.group(1)) if author_m else ""
                    author = (
                        " ".join(
                            "".join(
                                ch for ch in raw_author if ch.isprintable() or ch.isspace()
                            ).split()
                        )[:160]
                        or None
                    )
                    thumb_m = re.search(
                        r'data-(?:src|sfwthumb)="([^" ]*xnxx-cdn\.com[^" ]*)"', c
                    ) or re.search(r'src="([^" ]*xnxx-cdn\.com[^" ]*)"', c)
                    thumb = thumb_m.group(1) if thumb_m else None
                    seen_urls.add(valid_url)
                    opt = DownloadOption(valid_url, title, duration, author, thumbnail_url=thumb)
                    has_kw = (
                        any(
                            st in title.lower() or (author and st in author.lower())
                            for st in query_stems
                        )
                        if query_stems
                        else True
                    )
                    if has_kw and (duration is None or (isinstance(duration, (int, float)) and 0 < duration <= 1800)):
                        preferred.append(opt)
                    else:
                        others.append(opt)
                return tuple((preferred + others)[:MULTIMEDIA_CHOICES])
            pattern = re.compile(
                r"""<div class="thumb-under">\s*<p><a href="(/video-[0-9a-z]+/[A-Za-z0-9_-]*)" title="([^"]*)">([^<]*)</a></p>.*?<p class="metadata">(.*?)</p>""",
                re.DOTALL,
            )
            fallback_options: list[DownloadOption] = []
            for m in pattern.finditer(html_text):
                if len(fallback_options) >= MULTIMEDIA_CHOICES:
                    break
                path, title1, title2, meta = m.groups()
                title = html.unescape(title1 or title2).strip()
                title = " ".join(
                    "".join(c for c in title if c.isprintable() or c.isspace()).split()
                )[:300]
                try:
                    valid_url = validate_download_url(f"https://www.xnxx.com{path}")
                except MediaError:
                    continue
                if not title:
                    continue
                duration = _parse_xnxx_duration(meta)
                fallback_options.append(DownloadOption(valid_url, title, duration, None))
            return tuple(fallback_options)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, TimeoutError) as exc:
            raise MediaError("search_failed") from exc

    async def subtitles(self, url: str, language: str) -> Path:
        from .remote_subtitles import fetch_subtitles

        return await fetch_subtitles(self, url, language)

    async def resolve_spotify(self, url: str) -> str:
        url = validate_spotify_url(url)
        try:
            async with asyncio.timeout(20), _proxy("spotify") as proxy:
                async with httpx.AsyncClient(
                    proxy=proxy, trust_env=False, follow_redirects=False, timeout=15
                ) as client:
                    async with client.stream(
                        "GET", "https://open.spotify.com/oembed", params={"url": url}
                    ) as response:
                        if response.status_code != 200:
                            raise MediaError("spotify_metadata_unavailable")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 65536:
                                raise MediaError("spotify_metadata_unavailable")
            data = json.loads(body)
            title = data.get("title")
            if not isinstance(title, str):
                raise MediaError("spotify_metadata_unavailable")
            title = " ".join("".join(c for c in title if c.isprintable() or c.isspace()).split())[
                :300
            ]
            if not title:
                raise MediaError("spotify_metadata_unavailable")
            return title
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, AttributeError) as exc:
            raise MediaError("spotify_metadata_unavailable") from exc

    async def _fitting_adult_video_format(
        self, proxy: str, source: DownloadSource, url: str
    ) -> str | None:
        """Prefer the highest stream estimated to fit, avoiding needless encoding."""
        try:
            data = json.loads(
                await run_process(
                    self._base(proxy, source)
                    + [
                        "--impersonate",
                        "",
                        "--skip-download",
                        "--dump-single-json",
                        "--",
                        url,
                    ],
                    20,
                    env={"PATH": os.environ.get("PATH", "")},
                )
            )
            duration = data.get("duration")
            candidates = []
            for item in data.get("formats", []):
                height, rate = item.get("height"), item.get("tbr")
                identifier = item.get("format_id")
                if (
                    not isinstance(height, (int, float))
                    or not 0 < height <= 720
                    or item.get("protocol") not in {"https", "m3u8_native"}
                    or item.get("acodec") == "none"
                    or not isinstance(identifier, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier)
                ):
                    continue
                size = item.get("filesize") or item.get("filesize_approx")
                if (
                    not size
                    and isinstance(rate, (int, float))
                    and isinstance(duration, (int, float))
                ):
                    size = rate * 1000 * duration / 8
                if isinstance(size, (int, float)) and 0 < size <= MAX_VIDEO_BYTES * 0.9:
                    candidates.append((height, rate or 0, identifier))
            return max(candidates)[2] if candidates else None
        except MediaError, ValueError, TypeError, AttributeError, KeyError:
            return None

    async def _resolve_social_url(self, url: str, proxy: str, source: DownloadSource) -> str:
        """Resolve bounded share redirects; validate every hop before any request."""
        seen: set[str] = set()
        try:
            async with httpx.AsyncClient(
                proxy=proxy, trust_env=False, follow_redirects=False, timeout=15
            ) as client:
                for _ in range(5):
                    if not _social_short_url(url):
                        return url
                    if url in seen:
                        break
                    seen.add(url)
                    async with client.stream("GET", url) as response:
                        if response.status_code not in (301, 302, 303, 307, 308):
                            break
                        location = response.headers.get("location")
                        if not location:
                            break
                        target = validate_download_url(urljoin(url, location))
                        if download_source(target) != source:
                            raise MediaError("source_redirect_invalid")
                        url = target
                if not _social_short_url(url):
                    return url
        except (httpx.HTTPError, ValueError) as exc:
            raise MediaError("source_failed") from exc
        except MediaError as exc:
            raise MediaError("source_redirect_invalid") from exc
        raise MediaError("source_failed")

    async def download(
        self, url: str, format: Literal["audio", "video"], *, options: MediaOptions | None = None
    ) -> Path:
        url = validate_download_url(url)
        source_kind = download_source(url)
        if source_kind in ("xnxx", "pornhub") and not self.adult_sources_enabled:
            raise MediaError("unsupported_url")
        if format not in ("audio", "video"):
            raise MediaError("invalid_format")
        workspace = Path(tempfile.mkdtemp(prefix="download-", dir=self.work))
        try:
            async with asyncio.timeout(10_800 if options else 360), _proxy(source_kind) as proxy:
                if source_kind in SOCIAL_SOURCES and _social_short_url(url):
                    url = await self._resolve_social_url(url, proxy, source_kind)
                max_output_bytes = MAX_VIDEO_BYTES if format == "video" else MAX_BYTES
                source = workspace / "source"
                max_dl_bytes = (
                    MEDIA_INPUT_BYTES
                    if options
                    else (MAX_WORKSPACE_BYTES if format == "video" else MAX_BYTES)
                )
                if url.startswith("https://media.w3.org/"):
                    async with httpx.AsyncClient(
                        proxy=proxy, trust_env=False, follow_redirects=False, timeout=20
                    ) as client:
                        async with client.stream("GET", url) as response:
                            if response.status_code != 200:
                                raise MediaError("download_failed")
                            size = 0
                            with source.open("xb") as file:
                                async for chunk in response.aiter_bytes():
                                    size += len(chunk)
                                    if size > max_dl_bytes:
                                        raise MediaError("input_size")
                                    file.write(chunk)
                else:
                    # yt-dlp labels progressive HTTPS streams as protocol "http".
                    # Require the actual URL to be HTTPS as well; the CONNECT proxy
                    # independently blocks plaintext and destinations outside the source.
                    max_dl_bytes = (
                        MEDIA_INPUT_BYTES
                        if options
                        else (MAX_WORKSPACE_BYTES if format == "video" else MAX_BYTES)
                    )
                    if source_kind in ("dailymotion", "vimeo") or source_kind in SOCIAL_SOURCES:
                        progressive = [
                            f'[protocol={p}][url^="https://"]' for p in ("http", "https")
                        ]
                        selector = "/".join(
                            [f"best{p}[height<=720]" for p in progressive]
                            + [f"best{p}" for p in progressive]
                            if format == "video"
                            else [f"bestaudio{p}" for p in progressive]
                            + [f"best{p}" for p in progressive]
                        )
                        if source_kind == "dailymotion" or source_kind in SOCIAL_SOURCES:
                            hls = '[protocol=m3u8_native][url^="https://"]'
                            selector += (
                                f"/best{hls}[height<=720]"
                                if format == "video"
                                else f"/bestaudio{hls}/best{hls}"
                            )
                    elif source_kind in ("pornhub", "xnxx"):
                        selector = (
                            "best[protocol*=m3u8][height<=720]/best[protocol=https][height<=720]"
                            if format == "video"
                            else "bestaudio[protocol*=m3u8]/bestaudio[protocol=https]/best[protocol*=m3u8]/best[protocol=https]"
                        )
                    else:
                        selector = (
                            "best[protocol=https][height<=720]/best[protocol=https]"
                            if format == "video"
                            else "bestaudio[protocol=https]/best[protocol=https]"
                        )
                    if format == "video" and source_kind in {"pornhub", "xnxx"}:
                        fitting_format = await self._fitting_adult_video_format(
                            proxy, source_kind, url
                        )
                        if fitting_format:
                            selector = fitting_format
                    try:
                        args = self._base(proxy, source_kind, max_bytes=max_dl_bytes) + [
                            "--format",
                            selector,
                            "--max-filesize",
                            str(max_dl_bytes),
                            "--match-filters",
                            "duration > 0 & duration <= 10800 & !is_live"
                            if options
                            else "duration > 0 & duration <= 14400 & !is_live"
                            if format == "video"
                            else "duration > 0 & duration <= 600 & !is_live",
                            "--output",
                            str(source),
                            "--",
                            url,
                        ]
                        if source_kind in ("pornhub", "xnxx"):
                            args[args.index("--format") : args.index("--format")] = [
                                "--impersonate",
                                "",
                                "--concurrent-fragments",
                                "16",
                                "--no-keep-fragments",
                            ]
                        if source_kind in SOCIAL_SOURCES:
                            # --no-playlist alone does not reject Instagram carousels.
                            # Entry metadata from any collection is never downloaded.
                            filter_idx = args.index("--match-filters") + 1
                            # Instagram can omit duration. The bounded file is then
                            # measured by ffprobe below before conversion/delivery.
                            args[filter_idx] = (
                                args[filter_idx]
                                .replace("duration > 0", "duration >? 0")
                                .replace("duration <= ", "duration <=? ")
                                + " & !playlist_id"
                            )
                            args[args.index("--format") : args.index("--format")] = [
                                "--extractor-retries",
                                "0",
                            ]
                        if source_kind == "dailymotion" or source_kind in SOCIAL_SOURCES:
                            args[args.index("--format") : args.index("--format")] = [
                                "--downloader",
                                "m3u8:native",
                                "--hls-use-mpegts",
                                "--fixup",
                                "never",
                                "--fragment-retries",
                                "0",
                                "--concurrent-fragments",
                                "1",
                                "--no-keep-fragments",
                            ]
                        await _bounded_network_process(
                            args,
                            workspace,
                            max_bytes=max_dl_bytes * 2 if format == "video" else max_dl_bytes,
                            failure_code=(
                                youtube_failure_code
                                if source_kind == "youtube"
                                else social_failure_code
                                if source_kind in SOCIAL_SOURCES
                                else adult_failure_code
                                if source_kind in ("pornhub", "xnxx")
                                else None
                            ),
                            **({"timeout_seconds": 10_800} if options else {}),
                        )
                    except MediaError as exc:
                        if exc.code == "process_failed":
                            raise MediaError("source_failed") from None
                        if exc.code == "process_timeout":
                            raise MediaError("source_timeout") from None
                        raise
                if source_kind in SOCIAL_SOURCES and not source.is_file():
                    raise MediaError("social_video_unavailable")
                if not source.is_file() or not 0 < source.stat().st_size <= max_dl_bytes:
                    raise MediaError("input_size")
                # Native HLS may leave MPEG-TS. Remux from a fixed local file only;
                # neither ffmpeg input nor protocol selection can fetch the network.
                with source.open("rb") as stream:
                    header = stream.read(377)
                if len(header) > 188 and header[0] == header[188] == 0x47:
                    remuxed = workspace / "remuxed.mp4"
                    await run_process(
                        [
                            "prlimit",
                            f"--fsize={max_dl_bytes}",
                            "--",
                            "ffmpeg",
                            "-v",
                            "error",
                            "-nostdin",
                            "-protocol_whitelist",
                            "file,pipe",
                            "-format_whitelist",
                            "mpegts",
                            "-f",
                            "mpegts",
                            "-i",
                            str(source),
                            "-map",
                            "0:v:0?",
                            "-map",
                            "0:a:0?",
                            "-c",
                            "copy",
                            "-f",
                            "mp4",
                            str(remuxed),
                        ],
                        30,
                    )
                    if not remuxed.is_file() or not 0 < remuxed.stat().st_size <= max_dl_bytes:
                        raise MediaError("input_size")
                    source = remuxed
                if options is not None:
                    return await MediaEditor(self.root).convert_file(source, options)
                with source.open("rb") as source_file:
                    mov_options = (
                        ["-enable_drefs", "0", "-use_absolute_path", "0"]
                        if source_file.read(8)[4:8] == b"ftyp"
                        else []
                    )
                probe = await run_process(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-format_whitelist",
                        "mov,matroska,mp3,ogg,wav,aac,flac",
                        *mov_options,
                        "-show_entries",
                        "format=duration:stream=codec_type,codec_name,width,height,pix_fmt",
                        "-of",
                        "json",
                        str(source),
                    ],
                    10,
                )
                info = json.loads(probe)
                duration = float(info["format"]["duration"])
                max_dur = 14400 if format == "video" else 600
                if not 0 < duration <= max_dur:
                    raise MediaError("duration_limit")
                output = workspace / ("output.mp3" if format == "audio" else "output.mp4")
                streams = info.get("streams", [])
                videos = [x for x in streams if x.get("codec_type") == "video"]
                audios = [x for x in streams if x.get("codec_type") == "audio"]
                compatible = (
                    format == "video"
                    and len(videos) == 1
                    and len(audios) <= 1
                    and videos[0].get("codec_name") == "h264"
                    and videos[0].get("pix_fmt") == "yuv420p"
                    and 0 < videos[0].get("width", 0) <= 1280
                    and 0 < videos[0].get("height", 0) <= 720
                    and all(x.get("codec_name") == "aac" for x in audios)
                    and source.stat().st_size <= max_output_bytes
                )
                if compatible:
                    try:
                        await run_process(
                            [
                                "prlimit",
                                f"--fsize={max_output_bytes}",
                                "--",
                                "ffmpeg",
                                "-v",
                                "error",
                                "-nostdin",
                                "-protocol_whitelist",
                                "file,pipe",
                                "-format_whitelist",
                                "mov,matroska,mp3,ogg,wav,aac,flac",
                                *mov_options,
                                "-i",
                                str(source),
                                "-map",
                                "0:v:0",
                                "-map",
                                "0:a:0?",
                                "-sn",
                                "-dn",
                                "-c",
                                "copy",
                                "-movflags",
                                "+faststart",
                                str(output),
                            ],
                            60,
                        )
                    except MediaError:
                        if not output.is_file() or output.stat().st_size < max_output_bytes:
                            raise
                    else:
                        if output.is_file() and 0 < output.stat().st_size <= max_output_bytes:
                            output.chmod(0o600)
                            artifact = self.artifacts / f"{uuid.uuid4().hex}.mp4"
                            output.replace(artifact)
                            return artifact
                    # A remux can grow slightly at the boundary. Compress the
                    # original instead of accepting a truncated copy.
                    output.unlink(missing_ok=True)
                eff_dur = max(duration, 1.0)
                total_br = int((max_output_bytes * 0.94 * 8) / eff_dur)
                audio_br = min(128000, max(8000, total_br // 4))
                max_v_br = max(1000, total_br - audio_br)
                codec = (
                    ["-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-b:a", "128k"]
                    if format == "audio"
                    else [
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a:0?",
                        "-pix_fmt",
                        "yuv420p",
                        "-vf",
                        (
                            "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
                        ),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "superfast",
                        "-b:v",
                        str(max_v_br),
                        "-maxrate",
                        str(max_v_br),
                        "-bufsize",
                        str(max_v_br * 2),
                        "-c:a",
                        "aac",
                        "-b:a",
                        str(audio_br),
                        "-movflags",
                        "+faststart",
                    ]
                )
                try:
                    await run_process(
                        [
                            "prlimit",
                            f"--fsize={max_output_bytes}",
                            "--",
                            "ffmpeg",
                            "-v",
                            "error",
                            "-nostdin",
                            "-protocol_whitelist",
                            "file,pipe",
                            "-format_whitelist",
                            "mov,matroska,mp3,ogg,wav,aac,flac",
                            *mov_options,
                            "-threads",
                            "1",
                            "-filter_threads",
                            "1",
                            "-i",
                            str(source),
                            "-sn",
                            "-dn",
                            *codec,
                            str(output),
                        ],
                        180,
                    )
                except MediaError:
                    if output.is_file() and output.stat().st_size >= max_output_bytes:
                        raise MediaError("output_size") from None
                    raise
                if not output.is_file() or not 0 < output.stat().st_size <= max_output_bytes:
                    raise MediaError("output_size")
                output.chmod(0o600)
                artifact = self.artifacts / f"{uuid.uuid4().hex}{output.suffix}"
                output.replace(artifact)
                return artifact
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, OSError) as exc:
            raise MediaError("download_failed") from exc
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
