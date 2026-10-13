"""Tests for the HTML parser (no Home Assistant needed)."""

from datetime import date
from pathlib import Path

import pytest

from custom_components.abfall_ooe.parser import (
    filter_pickups,
    parse_ajax_urls,
    parse_districts,
    parse_location_form,
    parse_pickups,
    parse_redirect,
    parse_type_intervals,
)

PAGE = (Path(__file__).parent / "fixtures" / "calendar.html").read_text(encoding="utf-8")


def test_parse_pickups() -> None:
    pickups = parse_pickups(PAGE)
    assert len(pickups) == 7
    first = pickups[0]
    assert first.waste_type == "Bioabfall"
    assert first.waste_type_id == "t432"
    assert first.date == date(2026, 10, 14)
    assert pickups[1].interval == "2-wöchentlich"
    assert pickups[1].interval_id == "o386999"


def test_parse_type_intervals_only_lists_real_choices() -> None:
    assert parse_type_intervals(PAGE) == {
        "t430": {
            "o386999": "2-wöchentlich",
            "o387000": "4-wöchentlich",
            "o387056": "6-wöchentlich",
        }
    }


@pytest.mark.parametrize(
    ("interval", "restabfall_dates"),
    [
        ("o386999", [date(2026, 10, 19), date(2026, 11, 2)]),
        ("o387000", [date(2026, 11, 2)]),
        # No / unknown interval: keep every variant, but only once per day.
        (None, [date(2026, 10, 19), date(2026, 11, 2)]),
    ],
)
def test_filter_pickups(interval, restabfall_dates) -> None:
    result = filter_pickups(parse_pickups(PAGE), parse_type_intervals(PAGE), interval)
    assert [p.date for p in result if p.waste_type == "Restabfall"] == restabfall_dates
    # Single-schedule types are never filtered.
    assert [p.date for p in result if p.waste_type == "Bioabfall"] == [
        date(2026, 10, 14),
        date(2026, 10, 21),
    ]
    assert result == sorted(result, key=lambda p: (p.date, p.waste_type))


def test_filter_pickups_falls_back_to_interval_title() -> None:
    # The stored ID no longer exists (site re-numbered); the label still matches.
    result = filter_pickups(
        parse_pickups(PAGE), parse_type_intervals(PAGE), "o999", "4-Wöchentlich"
    )
    assert [p.interval for p in result if p.waste_type == "Restabfall"] == ["4-wöchentlich"]


def test_parse_page_metadata() -> None:
    assert "ajaxCityUrl" in parse_ajax_urls(PAGE)
    assert parse_districts(PAGE) == {"9": "Linz-Land", "10": "Perg"}
    form = parse_location_form(PAGE)
    assert form is not None
    assert "&cHash=def" in form.action
    assert form.hidden_fields["tx_ecxumweltprofis_pi2[__trustedProperties]"].startswith(
        '{"location"'
    )


def test_parse_redirect() -> None:
    assert parse_redirect(" redirect: https://x/perg.html\n") == "https://x/perg.html"
    assert parse_redirect("") is None
