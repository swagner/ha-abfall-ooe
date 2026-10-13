"""Shared fixtures."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.abfall_ooe.api import CalendarData
from custom_components.abfall_ooe.parser import Pickup

PICKUPS = [
    Pickup("t432", "Bioabfall", date(2026, 10, 14), "o1", "zum angegebenem Datum"),
    Pickup("t430", "Restabfall", date(2026, 10, 19), "o2w", "2-wöchentlich"),
    Pickup("t430", "Restabfall", date(2026, 11, 2), "o4w", "4-wöchentlich"),
    Pickup("t433", "Gelber Sack", date(2026, 11, 16), "o2", "zum angegebenem Datum"),
]
TYPE_INTERVALS = {"t430": {"o2w": "2-wöchentlich", "o4w": "4-wöchentlich"}}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/ in every test."""
    return


@pytest.fixture
def mock_client():
    """Patch the client factory used by both the flow and the entry setup."""
    client = AsyncMock()
    client.get_districts.return_value = {"10": "Perg", "9": "Linz-Land"}
    client.get_cities.return_value = {"93290": "Perg"}
    client.get_streets.return_value = {"5662262": "Aisthofen"}
    client.get_house_numbers.return_value = {"97941052": "1"}
    client.get_intervals.return_value = {}
    client.get_calendar.return_value = CalendarData(PICKUPS, TYPE_INTERVALS)

    async def _get_pickups(location, interval, interval_title=None):
        from custom_components.abfall_ooe.parser import filter_pickups

        return filter_pickups(PICKUPS, TYPE_INTERVALS, interval, interval_title)

    client.get_pickups.side_effect = _get_pickups
    with (
        patch("custom_components.abfall_ooe.create_client", return_value=client),
        patch("custom_components.abfall_ooe.config_flow.create_client", return_value=client),
    ):
        yield client
