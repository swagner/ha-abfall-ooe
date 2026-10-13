"""Async client for the umweltprofis.at pickup calendar.

The site is a TYPO3/Extbase app without a public API. The flow is:

1. GET the calendar page -> session cookie, hidden form tokens and the
   ``ajax*Url`` lookup endpoints (signed with a cHash; the ``###REPLACE###``
   placeholder may be substituted without invalidating it).
2. Lookups return JSON lists of ``{"uid": ..., "title": ...}``.
3. POST the chosen location to the form action; the location is stored in
   the session (``fe_typo_user`` cookie).
4. GET the calendar page again -> the pickup table is rendered server side.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urljoin

import aiohttp

from .parser import (
    PLACEHOLDER,
    PLACEHOLDER2,
    Pickup,
    filter_pickups,
    parse_ajax_urls,
    parse_districts,
    parse_location_form,
    parse_pickups,
    parse_redirect,
    parse_type_intervals,
)

BASE_URL = "https://www.umweltprofis.at"
CALENDAR_PAGE = f"{BASE_URL}/linz-land/module/wann-wird-mein-abfall-abgeholt.html"
FORM_PREFIX = "tx_ecxumweltprofis_pi2"
TIMEOUT = aiohttp.ClientTimeout(total=30)
HEADERS = {"User-Agent": "HomeAssistant-abfall_ooe"}


class AbfallOoeError(Exception):
    """Base error."""


class AbfallOoeConnectionError(AbfallOoeError):
    """The site could not be reached or answered with an error."""


class AbfallOoeParseError(AbfallOoeError):
    """The site's markup changed and could not be parsed."""


@dataclass(frozen=True)
class Location:
    """IDs of a fully selected address."""

    district: str
    city: str
    street: str
    house_number: str


@dataclass(frozen=True)
class CalendarData:
    """Result of a calendar fetch."""

    pickups: list[Pickup]
    type_intervals: dict[str, dict[str, str]]


class AbfallOoeClient:
    """Talks to umweltprofis.at.

    The session must have its own cookie jar: the selected location lives in
    the server-side session, so it must not be shared with other users of the
    session.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._page: str | None = None

    async def _request(self, method: str, url: str, **kwargs) -> str:
        try:
            async with self._session.request(
                method, url, headers=HEADERS, timeout=TIMEOUT, **kwargs
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AbfallOoeConnectionError(f"{method} {url} failed: {err}") from err

    async def _load_page(self, force: bool = False) -> str:
        if self._page is None or force:
            self._page = await self._request("GET", CALENDAR_PAGE)
        return self._page

    async def _lookup(self, name: str, value: str, value2: str | None = None) -> dict[str, str]:
        urls = parse_ajax_urls(await self._load_page())
        if name not in urls:
            raise AbfallOoeParseError(f"Lookup endpoint {name} not found on page")
        url = urls[name].replace(PLACEHOLDER, str(value))
        if value2 is not None:
            url = url.replace(PLACEHOLDER2, str(value2))
        body = await self._request("GET", url)
        try:
            items = json.loads(body)
        except ValueError as err:
            raise AbfallOoeParseError(f"{name} did not return JSON") from err
        return {
            str(item["uid"]): str(item["title"]).strip()
            for item in items
            if str(item.get("title", "")).strip()
        }

    async def get_districts(self) -> dict[str, str]:
        districts = parse_districts(await self._load_page())
        if not districts:
            raise AbfallOoeParseError("District list not found on page")
        return districts

    async def get_cities(self, district: str) -> dict[str, str]:
        return await self._lookup("ajaxCityUrl", district)

    async def get_streets(self, city: str) -> dict[str, str]:
        return await self._lookup("ajaxStreetUrl", city)

    async def get_house_numbers(self, street: str) -> dict[str, str]:
        return await self._lookup("ajaxHouseNumberUrl", street)

    async def get_intervals(self, street: str, house_number: str) -> dict[str, str]:
        return await self._lookup("ajaxIntervalUrl", house_number, street)

    async def get_calendar(self, location: Location) -> CalendarData:
        """Select the location in the session and return its pickups."""
        page = await self._load_page(force=True)
        form = parse_location_form(page)
        if form is None:
            raise AbfallOoeParseError("Location form not found on page")

        data = dict(form.hidden_fields)
        data.update(
            {
                f"{FORM_PREFIX}[location][district]": location.district,
                f"{FORM_PREFIX}[location][city]": location.city,
                f"{FORM_PREFIX}[location][street]": location.street,
                f"{FORM_PREFIX}[location][houseNumber]": location.house_number,
            }
        )
        body = await self._request("POST", urljoin(BASE_URL, form.action), data=data)

        calendar_url = parse_redirect(body) or CALENDAR_PAGE
        page = await self._request("GET", calendar_url)
        return CalendarData(
            pickups=parse_pickups(page),
            type_intervals=parse_type_intervals(page),
        )

    async def get_pickups(
        self, location: Location, interval: str | None, interval_title: str | None = None
    ) -> list[Pickup]:
        """Pickups for the location, reduced to the chosen interval."""
        calendar = await self.get_calendar(location)
        return filter_pickups(
            calendar.pickups, calendar.type_intervals, interval, interval_title
        )
