"""Tests for parsing Loam trail pages."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from loam_api import LoamParseError, TrailConditions, parse_trail_page

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def conditions_with_status(status: str) -> TrailConditions:
    return TrailConditions(
        network_id="x",
        name="X",
        status=status,
        status_label=None,
        outlook=None,
        note=None,
        last_rain=None,
        location=None,
        observed_at=None,
        latitude=None,
        longitude=None,
    )


def test_parses_real_trail_page() -> None:
    conditions = parse_trail_page(
        "green-mountain-park", load_fixture("green_mountain_park.html")
    )

    assert conditions.name == "Green Mountain Park"
    assert conditions.status == "DRY"
    assert conditions.status_label == "Rideable"
    assert conditions.outlook == "Rideable now"
    assert conditions.note == "Good window for the next ~10 hours."
    assert conditions.last_rain == "No measurable rain in the past week"
    assert conditions.location == "Denver & Golden, CO"
    assert conditions.observed_at == datetime(2026, 10, 13, 15, 21, 42, 678000, UTC)
    assert conditions.latitude == 39.6999
    assert conditions.longitude == -105.1777
    assert conditions.is_rideable


def test_falls_back_to_share_card_when_json_ld_missing() -> None:
    html = (
        '<meta property="og:image" content="https://api.loamrideconditions.com/'
        "share-card?name=Bobsled&amp;status=STAY+OFF&amp;"
        'verdict=Expected+rideable+in+%7E14+hours" />'
    )

    conditions = parse_trail_page("bobsled", html)

    assert conditions.name == "Bobsled"
    assert conditions.status_key == "stay_off"
    assert conditions.outlook == "Expected rideable in ~14 hours"
    assert not conditions.is_rideable


def test_page_without_conditions_raises() -> None:
    with pytest.raises(LoamParseError):
        parse_trail_page("missing", "<html><head></head></html>")


@pytest.mark.parametrize(
    ("status", "key", "rideable"),
    [
        ("PRIME", "prime", True),
        ("DRY", "dry", True),
        ("DUSTY", "dusty", True),
        ("CAUTION", "caution", False),
        ("STAY OFF", "stay_off", False),
        ("FROZEN", "frozen", False),
    ],
)
def test_status_normalization(status: str, key: str, rideable: bool) -> None:
    conditions = conditions_with_status(status)

    assert conditions.status_key == key
    assert conditions.is_known_status
    assert conditions.is_rideable is rideable


def test_unknown_status_is_flagged() -> None:
    assert not conditions_with_status("MUDDY").is_known_status


def test_parses_drying_timeline() -> None:
    conditions = parse_trail_page(
        "green-mountain-park", load_fixture("green_mountain_park.html")
    )
    timeline = conditions.timeline

    assert timeline is not None
    assert timeline.start == datetime(2026, 10, 3, 7, tzinfo=UTC)
    assert len(timeline.dryness) == len(timeline.statuses) == len(timeline.rain_in) == 372
    assert timeline.forecast_from_index == 249
    assert timeline.dryness_at(datetime(2026, 10, 3, 7, 30, tzinfo=UTC)) == 0.725
    assert timeline.dryness_at(datetime(2026, 9, 1, tzinfo=UTC)) is None


def test_next_change_skips_past_and_low_confidence() -> None:
    conditions = parse_trail_page(
        "green-mountain-park", load_fixture("green_mountain_park.html")
    )

    change = conditions.next_change(datetime(2026, 10, 14, 5, tzinfo=UTC))

    assert change is not None
    assert change.at == datetime(2026, 10, 14, 18, tzinfo=UTC)
    assert (change.from_status, change.to_status) == ("CAUTION", "STAY OFF")


def test_daily_weather_uses_local_day_start() -> None:
    conditions = parse_trail_page(
        "green-mountain-park", load_fixture("green_mountain_park.html")
    )
    first_day = conditions.daily[0]

    assert first_day.day.isoformat() == "2026-10-03"
    assert first_day.starts_at == datetime(2026, 10, 3, 7, tzinfo=UTC)
    assert first_day.temp_max_c == 25.4


def test_page_without_chart_still_parses() -> None:
    html = (
        '<meta property="og:image" content="https://x/share-card?status=DRY" />'
    )

    conditions = parse_trail_page("x", html)

    assert conditions.timeline is None
    assert conditions.changes == ()
    assert conditions.next_change(datetime(2026, 1, 1, tzinfo=UTC)) is None
