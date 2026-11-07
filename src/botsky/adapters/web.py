"""Cliente RSS acotado; endpoint fijo, sin seguir enlaces de resultados."""

import asyncio

from ..engines.process import MediaError


class NetworkWeb:
    def __init__(self, *, enabled=False, client=None):
        self.enabled, self.client = enabled, client

    async def search(self, query, required_terms):
        if not self.enabled:
            raise MediaError("web_not_configured")
        import httpx

        from ..engines.web_results import MAX_RESPONSE, SearchError, parse_results

        client = self.client or httpx.AsyncClient(trust_env=False, follow_redirects=False)
        # Pass explicit ALL-terms constraints to Bing as quoted literals too.
        # Keep the caller's query intact (including any site: operator); the
        # parser still enforces the same constraints against returned text.
        provider_query = query
        if required_terms:
            quoted_terms = " ".join(
                '"' + term.replace("\\", "\\\\").replace('"', '\\"') + '"'
                for term in required_terms
            )
            provider_query = f"{query} {quoted_terms}"
        try:
            async with asyncio.timeout(15):
                async with client.stream(
                    "GET",
                    "https://www.bing.com/search",
                    params={"q": provider_query, "format": "rss"},
                    headers={"User-Agent": "Botsky/0.1 personal RSS search"},
                    follow_redirects=False,
                    timeout=12,
                ) as response:
                    if response.status_code != 200:
                        raise MediaError("web_unavailable")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE:
                            raise MediaError("web_response_too_large")
                return parse_results(bytes(raw), query, list(required_terms))
        except httpx.HTTPError, TimeoutError, SearchError:
            raise MediaError("web_unavailable") from None
        finally:
            if self.client is None:
                await client.aclose()
