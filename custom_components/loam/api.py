"""Client for the Loam ride conditions website.

Loam has no public per-trail API, so conditions are read from the
server-rendered trail page: the schema.org JSON-LD block and the
share-card image URL in the og:image meta tag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import json
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import aiohttp

BASE_URL = "https://loamrideconditions.com"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)

KNOWN_STATUSES = ("prime", "dry", "dusty", "caution", "stay_off", "frozen")
RIDEABLE_STATUSES = frozenset({"prime", "dry", "dusty"})


class LoamError(Exception):
    """Base error for the Loam client."""


class LoamConnectionError(LoamError):
    """Loam could not be reached."""


class LoamNotFoundError(LoamError):
    """The trail network has no public page."""


class LoamParseError(LoamError):
    """A Loam response did not contain the expected data."""


@dataclass(frozen=True)
class SearchResult:
    """A trail network returned by Loam's search."""

    network_id: str
    name: str
    region: str | None
    state: str | None
    distance_km: float | None


@dataclass(frozen=True)
class TrailConditions:
    """Current modeled conditions for one trail network."""

    network_id: str
    name: str
    status: str
    status_label: str | None
    outlook: str | None
    note: str | None
    last_rain: str | None
    location: str | None
    observed_at: datetime | None
    latitude: float | None
    longitude: float | None

    @property
    def status_key(self) -> str:
        """Status normalized to a Home Assistant state, e.g. 'STAY OFF' -> 'stay_off'."""
        return self.status.strip().lower().replace(" ", "_")

    @property
    def is_known_status(self) -> bool:
        return self.status_key in KNOWN_STATUSES

    @property
    def is_rideable(self) -> bool:
        return self.status_key in RIDEABLE_STATUSES


def trail_url(network_id: str) -> str:
    return f"{BASE_URL}/trails/{quote(network_id, safe='')}"


class LoamClient:
    """Async client for loamrideconditions.com."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_search(self, query: str) -> list[SearchResult]:
        """Search trail networks by zip code, place, or name.

        Only networks with a public page are returned, since those are the
        only ones whose conditions can be read.
        """
        text = await self._get(f"{BASE_URL}/api/search", params={"q": query})
        try:
            results = json.loads(text)["results"]
        except (ValueError, KeyError, TypeError) as err:
            raise LoamParseError("Unexpected search response") from err
        return [_search_result(item) for item in results if item.get("published")]

    async def async_get_conditions(self, network_id: str) -> TrailConditions:
        return parse_trail_page(network_id, await self._get(trail_url(network_id)))

    async def _get(self, url: str, params: dict[str, str] | None = None) -> str:
        try:
            async with self._session.get(
                url, params=params, timeout=REQUEST_TIMEOUT
            ) as response:
                if response.status == 404:
                    raise LoamNotFoundError(f"{url} not found")
                response.raise_for_status()
                return await response.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise LoamConnectionError(f"Error requesting {url}: {err}") from err


def _search_result(item: dict[str, Any]) -> SearchResult:
    return SearchResult(
        network_id=item["id"],
        name=item["name"],
        region=item.get("region"),
        state=item.get("state"),
        distance_km=item.get("distanceKm"),
    )


def parse_trail_page(network_id: str, html: str) -> TrailConditions:
    """Extract conditions from a trail page's HTML."""
    page = _TrailPageParser()
    page.feed(html)
    share_card = _share_card_params(page.meta.get("og:image"))
    attraction = _find_attraction(page.json_ld)
    properties = _additional_properties(attraction)
    condition = properties.get("Trail condition", {})

    status = condition.get("value") or share_card.get("status")
    if not status:
        raise LoamParseError(f"No trail condition found for {network_id}")

    geo = attraction.get("geo") or {}
    return TrailConditions(
        network_id=network_id,
        name=attraction.get("name") or share_card.get("name") or network_id,
        status=status,
        status_label=condition.get("description"),
        outlook=share_card.get("verdict"),
        note=share_card.get("note"),
        last_rain=share_card.get("lastRain"),
        location=share_card.get("location"),
        observed_at=_parse_timestamp(
            properties.get("Condition observed at", {}).get("value")
        ),
        latitude=geo.get("latitude"),
        longitude=geo.get("longitude"),
    )


class _TrailPageParser(HTMLParser):
    """Collects meta tags and JSON-LD blocks from an HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._json_ld_chunks: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if key and content is not None:
                self.meta.setdefault(key, content)
        elif tag == "script" and attributes.get("type") == "application/ld+json":
            self._json_ld_chunks = []

    def handle_data(self, data: str) -> None:
        if self._json_ld_chunks is not None:
            self._json_ld_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_ld_chunks is not None:
            self.json_ld.append("".join(self._json_ld_chunks))
            self._json_ld_chunks = None


def _share_card_params(image_url: str | None) -> dict[str, str]:
    if not image_url:
        return {}
    query = parse_qs(urlparse(image_url).query)
    return {key: values[0] for key, values in query.items() if values}


def _find_attraction(json_ld_blocks: list[str]) -> dict[str, Any]:
    for block in json_ld_blocks:
        try:
            document = json.loads(block)
        except ValueError:
            continue
        for node in _json_ld_nodes(document):
            if node.get("@type") == "TouristAttraction":
                return node
    return {}


def _json_ld_nodes(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [node for node in document if isinstance(node, dict)]
    if isinstance(document, dict):
        return [document, *_json_ld_nodes(document.get("@graph", []))]
    return []


def _additional_properties(attraction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        prop["name"]: prop
        for prop in attraction.get("additionalProperty", [])
        if isinstance(prop, dict) and "name" in prop
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
