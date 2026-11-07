"""Cliente de fuentes con habilitación explícita. Ninguna conexión al construirlo."""

from ..engines.process import MediaError


class NetworkDownloads:
    def __init__(self, *, enabled=False, adult_sources_enabled=False):
        self.enabled = enabled
        self.adult_sources_enabled = adult_sources_enabled

    def client(self, directory):
        if not self.enabled:
            raise MediaError("downloads_not_configured")
        from ..engines.downloads import Downloader

        return Downloader(directory / "download", adult_sources_enabled=self.adult_sources_enabled)

    async def search(self, query, source, directory):
        if source not in ("youtube", "pornhub", "xnxx", "adult"):
            raise MediaError("source_search_unavailable")
        return await self.client(directory).search(
            query, "combined" if source == "adult" else source
        )

    async def resolve_spotify(self, url, directory):
        return await self.client(directory).resolve_spotify(url)

    async def download(self, url, options, directory):
        client = self.client(directory)
        if options.container == "srt":
            if options.start_seconds or options.end_seconds is not None:
                raise MediaError("subtitle_clip_unsupported")
            return await client.subtitles(url, options.subtitle_language or "es")
        return await client.download(
            url, "audio" if options.container == "mp3" else "video", options=options
        )

    async def thumbnail(self, thumbnail_url, video_url):
        if not self.enabled:
            return None
        from ..engines.downloads import download_source
        from ..engines.search_collage import fetch_thumbnail

        return await fetch_thumbnail(thumbnail_url, download_source(video_url))
