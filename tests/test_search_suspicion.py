import unittest
from pathlib import Path

import httpx

from botsky.adapters.web import NetworkWeb
from botsky.engines.web_results import parse_results


def rss(*items: tuple[str, str, str]) -> bytes:
    body = "".join(
        f"<item><title>{title}</title><link>{url}</link><description>{snippet}</description></item>"
        for title, url, snippet in items
    )
    return f"<rss><channel>{body}</channel></rss>".encode()


class SearchFilterTests(unittest.TestCase):
    def test_required_terms_match_across_cleaned_title_and_snippet_and_keep_site(self):
        result = parse_results(
            rss(
                (
                    "Python &amp; Tutorial",
                    "https://docs.example.org/guide",
                    "&lt;p&gt;Botsky &amp;amp; testing&lt;/p&gt;",
                ),
                (
                    "Python Tutorial",
                    "https://elsewhere.example/guide",
                    "Botsky testing",
                ),
            ),
            "site:example.org Python guide",
            ["python", "TUTORIAL", "Botsky"],
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Python & Tutorial")
        self.assertEqual(result[0].snippet, "Botsky & testing")
        self.assertEqual(result[0].url, "https://docs.example.org/guide")

    def test_every_required_term_must_appear_in_title_or_snippet(self):
        result = parse_results(
            rss(
                (
                    "Python tutorial",
                    "https://docs.example.org/partial",
                    "Testing guide",
                ),
                (
                    "Python tutorial",
                    "https://docs.example.org/match",
                    "Testing guide for Botsky",
                ),
            ),
            "Python tutorial",
            ["Python", "testing", "Botsky"],
        )

        self.assertEqual([item.url for item in result], ["https://docs.example.org/match"])

    def test_only_first_ten_rss_items_are_considered(self):
        items = [(f"Noise {n}", f"https://example.org/{n}", "unrelated") for n in range(10)]
        items.append(("W3C HTML standards", "https://example.org/11", "specification"))

        result = parse_results(rss(*items), "standards", ["W3C", "HTML"])

        self.assertEqual(result, [])


class SearchCaptureReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_query_terms_enable_positive_result_without_weakening_all_filter(self):
        query = "asyncio tutorial"
        terms = ["Python", "docs"]
        seen = []

        def respond(request):
            provider_query = request.url.params["q"]
            seen.append(provider_query)
            if all(f'"{term}"' in provider_query for term in terms):
                return httpx.Response(
                    200,
                    content=rss(
                        (
                            "Python asyncio tutorial",
                            "https://docs.example.org/asyncio",
                            "Official docs",
                        ),
                        (
                            "Python asyncio tutorial",
                            "https://docs.example.org/partial",
                            "Missing required word",
                        ),
                    ),
                )
            return httpx.Response(200, content=rss())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            results = await NetworkWeb(enabled=True, client=client).search(query, terms)

        self.assertEqual(seen, ['asyncio tutorial "Python" "docs"'])
        self.assertEqual([item.url for item in results], ["https://docs.example.org/asyncio"])

    async def test_captured_provider_responses_replay_as_empty_with_same_filter(self):
        capture = Path(__file__).parents[1] / "docs/evidencia/SOSPECHAS-20261106/20261106T211144Z"
        cases = {
            "c02": ("Botsky testing guide", ["Python", "tutorial"]),
            "c03": ("HTML standards specification", ["W3C", "HTML"]),
        }
        seen = []

        def respond(request):
            seen.append(request)
            case = "c02" if "Botsky" in request.url.params["q"] else "c03"
            return httpx.Response(200, content=(capture / f"{case}.rss").read_bytes())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            backend = NetworkWeb(enabled=True, client=client)
            for query, required_terms in cases.values():
                self.assertEqual(await backend.search(query, required_terms), [])

        self.assertEqual(len(seen), 2)
        self.assertEqual(
            [request.url.params["q"] for request in seen],
            [
                'Botsky testing guide "Python" "tutorial"',
                'HTML standards specification "W3C" "HTML"',
            ],
        )

    async def test_provider_query_keeps_site_and_escapes_literal_terms(self):
        seen = []

        def respond(request):
            seen.append(request)
            return httpx.Response(200, content=rss())

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            backend = NetworkWeb(enabled=True, client=client)
            await backend.search('site:docs.example.org "release"', ["C++", 'a "quote"'])

        self.assertEqual(
            seen[0].url.params["q"],
            'site:docs.example.org "release" "C++" "a \\"quote\\""',
        )


if __name__ == "__main__":
    unittest.main()
