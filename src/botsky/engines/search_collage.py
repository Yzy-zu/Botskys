"""Collage propio. Layout de referencia Zhana; fronteras de red/decodificación nuevas.

No consulta el runtime antiguo. Miniaturas opcionales: el fallo conserva el índice.
"""

import asyncio
import io
import math
import os
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..presentation.search import duration, source_label

MAX_THUMB_BYTES = 2 * 1024 * 1024
MAX_THUMB_PIXELS = 8_000_000


def layout(count):
    if count not in range(1, 7):
        raise ValueError("se requieren de 1 a 6 opciones")
    rows = (
        (1,)
        if count == 1
        else (2,)
        if count == 2
        else (2, 1)
        if count == 3
        else (2, 2)
        if count == 4
        else (3, 2)
        if count == 5
        else (3, 3)
    )
    cells = []
    for r, columns in enumerate(rows):
        top, bottom = r * 720 // len(rows), (r + 1) * 720 // len(rows)
        for col in range(columns):
            left, right = col * 1280 // columns, (col + 1) * 1280 // columns
            cells.append((left, top, right - left, bottom - top))
    return cells


def font(size):
    # Pillow empaqueta fuente de fallback; no exige rutas privadas ni del sistema.
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def decode_thumbnail(raw):
    if not raw or len(raw) > MAX_THUMB_BYTES:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > MAX_THUMB_PIXELS or image.width < 1 or image.height < 1:
                return None
            image.load()
            return ImageOps.exif_transpose(image).convert("RGB")
    except OSError, ValueError, Image.DecompressionBombError:
        return None


async def fetch_thumbnail(url, source, *, client=None):
    """CONNECT con DNS público fijado; sin cookies, entorno o redirecciones."""
    import httpx

    from .downloads import _allowed_host, _proxy

    try:
        parts = urlsplit(url)
        if (
            len(url) > 2000
            or parts.scheme != "https"
            or parts.username is not None
            or parts.password is not None
            or parts.port is not None
            or parts.fragment
            or not parts.hostname
            or not _allowed_host(parts.hostname, source)
            or any(ord(c) <= 32 or ord(c) >= 127 for c in url)
        ):
            return None

        async def read(http):
            async with http.stream("GET", url, timeout=5, follow_redirects=False) as response:
                if response.status_code != 200:
                    return None
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > MAX_THUMB_BYTES:
                        return None
                    raw.extend(chunk)
                return bytes(raw)

        async with asyncio.timeout(6):
            if client is not None:
                return await read(client)
            async with _proxy(source) as proxy:
                async with httpx.AsyncClient(
                    proxy=proxy, trust_env=False, follow_redirects=False
                ) as http:
                    return await read(http)
    except httpx.HTTPError, TimeoutError, ValueError, TypeError:
        return None


def _fit_text(draw, text, x, y, width, *, size=30, lines=3):
    face = font(size)
    # Cortar por ancho medido, incluso palabras/autor largos; no usar variables
    # de otra rama como el placeholder histórico de referencia.
    rest = " ".join(str(text).split())[:600]
    for _ in range(lines):
        if not rest:
            break
        end = len(rest)
        while end > 1 and draw.textlength(rest[:end], font=face) > width:
            end -= 1
        if end < len(rest):
            space = rest.rfind(" ", 0, end)
            if space > end // 2:
                end = space
        draw.text((x, y), rest[:end], font=face, fill="#f4f2fa")
        rest = rest[end:].lstrip()
        y += size + 7


def render(choices, thumbnails, path):
    if len(choices) != len(thumbnails):
        raise ValueError("índices de miniaturas diferentes")
    canvas = Image.new("RGB", (1280, 720), "#10121b")
    for number, (choice, raw, cell) in enumerate(
        zip(choices, thumbnails, layout(len(choices)), strict=True), 1
    ):
        x, y, width, height = cell
        image = decode_thumbnail(raw)
        if image is None:
            card = Image.new("RGB", (width, height), "#202432")
            draw = ImageDraw.Draw(card)
            _fit_text(draw, choice["title"], 22, 100 if height > 400 else 86, width - 44)
            _fit_text(
                draw,
                choice.get("author") or "Autor desconocido",
                22,
                height - 96,
                width - 44,
                size=20,
                lines=1,
            )
        else:
            card = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(card)
        draw.rectangle((0, 0, width - 1, height - 1), outline="#10121b", width=2)
        # Número mayor que la referencia: legible al reducir a 390px.
        draw.rounded_rectangle(
            (14, 14, 82, 82), radius=12, fill="#e11d48", outline="white", width=2
        )
        draw.text((32, 19), str(number), font=font(42), fill="white")
        label = source_label(choice["url"])
        face = font(36)
        tw = math.ceil(draw.textlength(label, font=face))
        draw.rounded_rectangle((width - tw - 34, 16, width - 12, 69), radius=7, fill="#10121b")
        draw.text((width - tw - 23, 18), label, font=face, fill="white")
        label = duration(choice.get("duration"))
        if label != "Duración desconocida":
            tw = math.ceil(draw.textlength(label, font=face))
            draw.rounded_rectangle(
                (width - tw - 34, height - 68, width - 12, height - 12), radius=7, fill="#10121b"
            )
            draw.text((width - tw - 23, height - 66), label, font=face, fill="white")
        canvas.paste(card, (x, y))
    canvas.save(path, "JPEG", quality=88, optimize=True)
    os.chmod(path, 0o600)
    return path


async def create(choices, path, thumbnail_provider=None):
    semaphore = asyncio.Semaphore(2)

    async def get(choice):
        if thumbnail_provider is None or not choice.get("thumbnail_url"):
            return None
        async with semaphore:
            try:
                async with asyncio.timeout(7):
                    return await thumbnail_provider(choice["thumbnail_url"], choice["url"])
            except OSError, ValueError, TimeoutError:
                return None

    thumbnails = await asyncio.gather(*(get(choice) for choice in choices))
    task = asyncio.create_task(asyncio.to_thread(render, choices, thumbnails, path))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # No retirar scratch mientras un render acotado sigue escribiendo.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()
        raise
