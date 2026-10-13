"""Client for the Loam ride conditions website.

Loam has no public per-trail API, so conditions are read from the
server-rendered trail page: the schema.org JSON-LD block, the share-card
image URL in the og:image meta tag, and the JSON that feeds the page's
drying chart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
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


def status_key(status: str) -> str:
    """Normalize a Loam status to a Home Assistant state, e.g. 'STAY OFF' -> 'stay_off'."""
    return status.strip().lower().replace(" ", "_")


@dataclass(frozen=True)
class StatusChange:
    """A modeled transition between statuses."""

    at: datetime
    from_status: str
    to_status: str
    confirmed: bool


@dataclass(frozen=True)
class DailyWeather:
    day: date
    starts_at: datetime | None
    precipitation_in: float | None
    temp_max_c: float | None
    weather_code: int | None


@dataclass(frozen=True)
class Timeline:
    """Hourly modeled dryness (0 wet to 1 dry), past and forecast."""

    start: datetime
    step: timedelta
    forecast_from_index: int
    dryness: tuple[float | None, ...]
    statuses: tuple[str | None, ...]
    rain_in: tuple[float | None, ...]
    drier_bound: tuple[float | None, ...] | None
    wetter_bound: tuple[float | None, ...] | None

    def index_at(self, moment: datetime) -> int | None:
        index = int((moment - self.start) / self.step)
        return index if 0 <= index < len(self.dryness) else None

    def dryness_at(self, moment: datetime) -> float | None:
        index = self.index_at(moment)
        return None if index is None else self.dryness[index]


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
    timeline: Timeline | None = None
    changes: tuple[StatusChange, ...] = ()
    daily: tuple[DailyWeather, ...] = ()

    @property
    def status_key(self) -> str:
        return status_key(self.status)

    @property
    def is_known_status(self) -> bool:
        return self.status_key in KNOWN_STATUSES

    @property
    def is_rideable(self) -> bool:
        return self.status_key in RIDEABLE_STATUSES

    def next_change(self, after: datetime) -> StatusChange | None:
        """The first confirmed status change after a moment.

        Loam also lists low-confidence flickers; those are skipped.
        """
        return next(
            (
                change
                for change in self.changes
                if change.confirmed and change.at > after
            ),
            None,
        )


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
    chart = _drying_chart(page.json_scripts)
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
        timeline=_timeline(chart),
        changes=_status_changes(chart),
        daily=_daily_weather(chart),
    )


class _TrailPageParser(HTMLParser):
    """Collects meta tags, JSON-LD blocks, and id'd JSON scripts from a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.json_scripts: dict[str, str] = {}
        self._script_target: tuple[str, str] | None = None
        self._script_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if key and content is not None:
                self.meta.setdefault(key, content)
        elif tag == "script":
            self._start_script(attributes)

    def _start_script(self, attributes: dict[str, str | None]) -> None:
        script_type = attributes.get("type")
        if script_type == "application/ld+json":
            self._script_target = ("ld", "")
        elif script_type == "application/json" and attributes.get("id"):
            self._script_target = ("json", attributes["id"])
        else:
            return
        self._script_chunks = []

    def handle_data(self, data: str) -> None:
        if self._script_target is not None:
            self._script_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or self._script_target is None:
            return
        kind, script_id = self._script_target
        content = "".join(self._script_chunks)
        if kind == "ld":
            self.json_ld.append(content)
        else:
            self.json_scripts[script_id] = content
        self._script_target = None


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


def _drying_chart(json_scripts: dict[str, str]) -> dict[str, Any]:
    """The data behind the trail page's drying chart, or {} if absent."""
    for script_id, content in json_scripts.items():
        if not script_id.startswith("tidal-"):
            continue
        try:
            chart = json.loads(content)
        except ValueError:
            return {}
        return chart if isinstance(chart, dict) else {}
    return {}


def _timeline(chart: dict[str, Any]) -> Timeline | None:
    start = _parse_timestamp(chart.get("from"))
    dryness = chart.get("dryness")
    if start is None or not isinstance(dryness, list) or not dryness:
        return None
    band = chart.get("band") or {}
    return Timeline(
        start=start,
        step=timedelta(hours=chart.get("stepHours") or 1),
        forecast_from_index=chart.get("forecastFromIndex") or len(dryness),
        dryness=tuple(dryness),
        statuses=tuple(chart.get("status") or ()),
        rain_in=tuple(chart.get("rainIn") or ()),
        drier_bound=_optional_series(band.get("upper")),
        wetter_bound=_optional_series(band.get("lower")),
    )


def _optional_series(values: Any) -> tuple[float | None, ...] | None:
    return tuple(values) if isinstance(values, list) and values else None


def _status_changes(chart: dict[str, Any]) -> tuple[StatusChange, ...]:
    changes = []
    for crossing in chart.get("crossings") or ():
        if not isinstance(crossing, dict):
            continue
        at = _parse_timestamp(crossing.get("at"))
        if at is None or not crossing.get("to"):
            continue
        changes.append(
            StatusChange(
                at=at,
                from_status=crossing.get("from") or "",
                to_status=crossing["to"],
                confirmed=crossing.get("confidence") == "confirmed",
            )
        )
    return tuple(sorted(changes, key=lambda change: change.at))


def _daily_weather(chart: dict[str, Any]) -> tuple[DailyWeather, ...]:
    daily = chart.get("daily") or {}
    days = daily.get("time") or []
    precipitation = daily.get("precip") or []
    temp_max = daily.get("tempMax") or []
    weather_codes = daily.get("weatherCode") or []
    offset_hours = daily.get("offsetHours")
    day_timezone = (
        timezone(timedelta(hours=offset_hours))
        if isinstance(offset_hours, (int, float))
        else None
    )

    def value_at(values: list[Any], index: int) -> Any:
        return values[index] if index < len(values) else None

    weather = []
    for index, day in enumerate(days):
        try:
            parsed_day = date.fromisoformat(day)
        except (TypeError, ValueError):
            continue
        weather.append(
            DailyWeather(
                day=parsed_day,
                starts_at=None
                if day_timezone is None
                else datetime.combine(parsed_day, time(0), tzinfo=day_timezone),
                precipitation_in=value_at(precipitation, index),
                temp_max_c=value_at(temp_max, index),
                weather_code=value_at(weather_codes, index),
            )
        )
    return tuple(weather)
