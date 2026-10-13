"""HTML/JSON parsing for umweltprofis.at.

Kept free of Home Assistant and aiohttp imports so it can be unit tested
with plain pytest.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime

# The page embeds the lookup endpoints as JS variables, e.g.
#   var ajaxCityUrl = 'https://...district%5D=%23%23%23REPLACE%23%23%23&cHash=...';
_AJAX_URL_RE = re.compile(r"var (ajax\w+Url) = '([^']+)'")
_FORM_ACTION_RE = re.compile(r'id="choose-location-form"[^>]*action="([^"]+)"')
_HIDDEN_INPUT_RE = re.compile(r'<input type="hidden" name="([^"]+)" value="([^"]*)"')
_TYPE_SELECT_RE = re.compile(
    r'<select[^>]*id="type-selector-(t\d+)"[^>]*>(.*?)</select>', re.S
)
_OPTION_RE = re.compile(r'<option value="([^"]*)"[^>]*>([^<]*)</option>')
_ROW1_RE = re.compile(r'data-value="([^"]*)" id="row1-(\d+)" class="([^"]*)"')
_ROW2_RE = re.compile(r'data-value="([^"]*)" id="row2-(\d+)"')
_ROW3_RE = re.compile(r'data-value="([^"]*)" id="row3-(\d+)"')
_WASTE_TYPE_CLASS_RE = re.compile(r"\bwaste-type-(t\d+)\b")
_INTERVAL_CLASS_RE = re.compile(r"\binterval-type-(o\d+)\b")

PLACEHOLDER = "%23%23%23REPLACE%23%23%23"
PLACEHOLDER2 = "%23%23%23REPLACE2%23%23%23"


@dataclass(frozen=True)
class Pickup:
    """A single pickup as listed in the calendar table."""

    waste_type_id: str
    waste_type: str
    date: date
    interval_id: str | None
    interval: str


@dataclass(frozen=True)
class LocationForm:
    """The location-chooser form: POST target and hidden Extbase tokens."""

    action: str
    hidden_fields: dict[str, str]


def parse_ajax_urls(page: str) -> dict[str, str]:
    """Return {'ajaxCityUrl': url, ...} from the page's inline script."""
    return dict(_AJAX_URL_RE.findall(page))


def parse_districts(page: str) -> dict[str, str]:
    """Return {district_id: name} from the district dropdown.

    The placeholder ("Bezirk auswählen", id 1) and empty options are skipped.
    """
    match = re.search(r'<select[^>]*id="district-selector"[^>]*>(.*?)</select>', page, re.S)
    if match is None:
        return {}
    return {
        value: html.unescape(label).strip()
        for value, label in _OPTION_RE.findall(match.group(1))
        if value not in ("", "1") and label.strip()
    }


def parse_redirect(body: str) -> str | None:
    """The location POST answers ``redirect: <url>`` when the district changes."""
    body = body.strip()
    if body.startswith("redirect:"):
        return body[len("redirect:") :].strip() or None
    return None


def parse_location_form(page: str) -> LocationForm | None:
    """Extract the location form action and its hidden fields."""
    match = _FORM_ACTION_RE.search(page)
    if match is None:
        return None
    return LocationForm(
        action=html.unescape(match.group(1)),
        hidden_fields={
            name: html.unescape(value)
            for name, value in _HIDDEN_INPUT_RE.findall(page)
        },
    )


def parse_type_intervals(page: str) -> dict[str, dict[str, str]]:
    """Return the selectable intervals per waste type.

    Only types with real interval choices (option values starting with ``o``)
    are included, e.g. ``{"t430": {"o386999": "2-wöchentlich", ...}}``.
    """
    result: dict[str, dict[str, str]] = {}
    for type_id, options in _TYPE_SELECT_RE.findall(page):
        intervals = {
            value: html.unescape(label).strip()
            for value, label in _OPTION_RE.findall(options)
            if value.startswith("o")
        }
        if intervals:
            result[type_id] = intervals
    return result


def parse_pickups(page: str) -> list[Pickup]:
    """Parse the three-column calendar table (type / date / interval)."""
    dates = {row: value for value, row in _ROW2_RE.findall(page)}
    intervals = {row: value for value, row in _ROW3_RE.findall(page)}

    pickups: list[Pickup] = []
    for name, row, classes in _ROW1_RE.findall(page):
        type_match = _WASTE_TYPE_CLASS_RE.search(classes)
        raw_date = dates.get(row)
        if type_match is None or raw_date is None:
            continue
        try:
            pickup_date = datetime.strptime(raw_date.strip(), "%d.%m.%Y").date()
        except ValueError:
            continue
        interval_match = _INTERVAL_CLASS_RE.search(classes)
        pickups.append(
            Pickup(
                waste_type_id=type_match.group(1),
                waste_type=html.unescape(name).strip(),
                date=pickup_date,
                interval_id=interval_match.group(1) if interval_match else None,
                interval=html.unescape(intervals.get(row, "")).strip(),
            )
        )
    return pickups


def _wanted_interval(
    choices: dict[str, str] | None, interval_id: str | None, interval_title: str | None
) -> str | None:
    """Resolve the chosen interval within one waste type's choices.

    Matches by ID first and falls back to the label (e.g. "4-wöchentlich"),
    in case the site re-numbers its intervals when it publishes new data.
    """
    if not choices:
        return None
    if interval_id in choices:
        return interval_id
    if interval_title:
        for choice_id, title in choices.items():
            if title.casefold() == interval_title.casefold():
                return choice_id
    return None


def filter_pickups(
    pickups: list[Pickup],
    type_intervals: dict[str, dict[str, str]],
    interval_id: str | None,
    interval_title: str | None = None,
) -> list[Pickup]:
    """Keep only the pickups that apply to the chosen interval.

    Waste types offering several intervals (typically Restabfall) list every
    variant in the table; those are reduced to the selected one. Types with a
    single schedule are kept as is. Duplicates (same type and date) are removed.
    """
    wanted = {
        type_id: _wanted_interval(choices, interval_id, interval_title)
        for type_id, choices in type_intervals.items()
    }
    seen: set[tuple[str, date]] = set()
    result: list[Pickup] = []
    for pickup in sorted(pickups, key=lambda p: (p.date, p.waste_type)):
        type_interval = wanted.get(pickup.waste_type_id)
        if type_interval is not None and pickup.interval_id != type_interval:
            continue
        key = (pickup.waste_type_id, pickup.date)
        if key in seen:
            continue
        seen.add(key)
        result.append(pickup)
    return result
