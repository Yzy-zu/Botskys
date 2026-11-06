# Componente técnico de Zhana 7e12d54; origen y límites en docs/portados/motores-origen.json.
"""Fetch existing, public subtitle tracks through the download proxy."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from .process import MediaError, run_process

if TYPE_CHECKING:
    from .downloads import Downloader

MAX_SUBTITLE_BYTES = 1024 * 1024


def _validate_srt(path: Path) -> None:
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_SUBTITLE_BYTES
        ):
            raise ValueError
        text = path.read_text(encoding="utf-8-sig")
        if not re.search(
            r"(?m)^\d+\s*\r?\n\d{2,}:\d{2}:\d{2},\d{3} --> "
            r"\d{2,}:\d{2}:\d{2},\d{3}(?:\s.*)?$",
            text,
        ):
            raise ValueError
    except (OSError, UnicodeError, ValueError) as exc:
        raise MediaError("invalid_subtitles") from exc


async def fetch_subtitles(downloader: Downloader, url: str, language: str) -> Path:
    from .downloads import _proxy, download_source, validate_download_url

    if language not in ("es", "en"):
        raise MediaError("unsupported_subtitles")
    url = validate_download_url(url)
    source = download_source(url)
    if source not in ("youtube", "vimeo"):
        raise MediaError("unsupported_subtitles")
    workspace = Path(tempfile.mkdtemp(prefix="subtitle-", dir=downloader.work))
    try:
        async with _proxy(source) as proxy:
            args = downloader._base(proxy, source)
            args = [
                f"--fsize={MAX_SUBTITLE_BYTES}" if arg.startswith("--fsize=") else arg
                for arg in args
            ]
            args += [
                "--skip-download",
                "--write-subs",
                "--sub-langs",
                language,
                "--sub-format",
                "vtt/srt",
                "--output",
                str(workspace / "subtitle.%(ext)s"),
                "--",
                url,
            ]
            try:
                await run_process(args, 45, env={"PATH": os.environ.get("PATH", "")})
            except MediaError as exc:
                if exc.code == "process_timeout":
                    raise
                raise MediaError("subtitles_failed") from exc
        candidates = [workspace / f"subtitle.{language}.{ext}" for ext in ("srt", "vtt")]
        sidecar = next((p for p in candidates if p.is_file() and not p.is_symlink()), None)
        if sidecar is None:
            raise MediaError("subtitles_unavailable")
        if not 0 < sidecar.stat().st_size <= MAX_SUBTITLE_BYTES:
            raise MediaError("invalid_subtitles")
        output = workspace / "output.srt"
        if sidecar.suffix == ".vtt":
            try:
                if not sidecar.read_text(encoding="utf-8-sig").lstrip().startswith("WEBVTT"):
                    raise ValueError
            except (OSError, UnicodeError, ValueError) as exc:
                raise MediaError("invalid_subtitles") from exc
            try:
                await run_process(
                    [
                        "prlimit",
                        f"--fsize={MAX_SUBTITLE_BYTES}",
                        "--",
                        "ffmpeg",
                        "-v",
                        "error",
                        "-nostdin",
                        "-threads",
                        "1",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-f",
                        "webvtt",
                        "-i",
                        str(sidecar),
                        "-c:s",
                        "srt",
                        "-f",
                        "srt",
                        str(output),
                    ],
                    15,
                )
            except MediaError as exc:
                if exc.code == "process_timeout":
                    raise
                raise MediaError("invalid_subtitles") from exc
        else:
            output = sidecar
        _validate_srt(output)
        output.chmod(0o600)
        artifact = downloader.artifacts / f"{uuid.uuid4().hex}.srt"
        output.replace(artifact)
        return artifact
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
