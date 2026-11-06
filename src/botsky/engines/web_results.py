# Helpers RSS adaptados de Zhana 7e12d54; sin Backend/Args ni interpretación.
import ipaddress
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

MAX_RESPONSE = 256 * 1024


class SearchError(Exception):
    pass


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean(value: str, limit: int) -> str:
    parser = _Text()
    parser.feed(value)
    text = " ".join(" ".join(parser.parts).split())
    return "".join(c for c in text if not unicodedata.category(c).startswith("C"))[:limit]


def safe_url(value: str) -> str | None:
    if len(value) > 2000 or re.search(r"[\s\x00-\x1f\x7f<>\\]", value):
        return None
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        if (
            url.scheme not in {"https", "http"}
            or url.username
            or url.password
            or url.port not in {None, 80, 443}
        ):
            return None
        if not host or "." not in host or host.endswith((".local", ".internal", ".localhost")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}", host):
                return None
        return value
    except ValueError:
        return None


@dataclass(frozen=True)
class SearchItem:
    title: str
    url: str
    snippet: str


def parse_results(
    raw: bytes, query: str, required_terms: list[str] | None = None
) -> list[SearchItem]:
    if len(raw) > MAX_RESPONSE:
        raise SearchError("response_too_large")
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text or "<!doctype" in text.lower() or "<!entity" in text.lower():
            raise SearchError("unsafe_xml")
        root = ET.fromstring(text)
    except UnicodeError, ET.ParseError:
        raise SearchError("invalid_response") from None
    channel = root.find("channel") if root.tag == "rss" else None
    if channel is None:
        raise SearchError("invalid_response")
    sites = []
    for token in re.findall(r"(?:^|\s)site:([^\s]+)", query):
        site = safe_url(token if token.startswith(("https://", "http://")) else "https://" + token)
        if site:
            sites.append(urlsplit(site))
    items: list[SearchItem] = []
    seen: set[str] = set()
    terms = [term.casefold() for term in (required_terms or [])]
    for item in channel.findall("item")[:10]:
        url = safe_url(item.findtext("link", "").strip())
        title = clean(item.findtext("title", ""), 160)
        if not url or not title or url in seen:
            continue
        host = (urlsplit(url).hostname or "").lower()
        if sites and not any(
            (host == s.hostname or host.endswith("." + str(s.hostname)))
            and urlsplit(url).path.startswith(s.path)
            for s in sites
        ):
            continue
        snippet = clean(item.findtext("description", ""), 400)
        # Explicit literal constraints supplied by command arguments;
        # this does not classify language, relevance or official status.
        evidence = (title + " " + snippet).casefold()
        if not all(term in evidence for term in terms):
            continue
        seen.add(url)
        items.append(SearchItem(title, url, snippet))
        if len(items) == 5:
            break
    if channel.findall("item") and not items and not sites and not terms:
        raise SearchError("invalid_results")
    return items
