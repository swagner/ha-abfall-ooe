"""Tests for entity setup, sensors and calendar."""

from datetime import datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.abfall_ooe.const import CONF_INTERVAL, DOMAIN


@pytest.fixture
async def entry(hass: HomeAssistant, mock_client, freezer: FrozenDateTimeFactory):
    await hass.config.async_set_time_zone("Europe/Vienna")
    freezer.move_to(datetime(2026, 10, 15, 8, 0, tzinfo=dt_util.get_default_time_zone()))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="97941052",
        title="Aisthofen 1, Perg",
        data={
            "district": "10", "city": "93290", "street": "5662262",
            "house_number": "97941052", CONF_INTERVAL: "o4w",
            "intervals": {"o2w": "2-wöchentlich", "o4w": "4-wöchentlich"},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensors(hass: HomeAssistant, entry) -> None:
    # Bioabfall on 14.10 is in the past (today is 15.10) and has no later date.
    assert hass.states.get("sensor.aisthofen_1_perg_bioabfall").state == "unknown"

    # The 2-weekly Restabfall date (19.10) is filtered out by the 4-weekly choice.
    rest = hass.states.get("sensor.aisthofen_1_perg_restabfall")
    assert rest.state == "2026-11-02"
    assert rest.attributes["days_until"] == 18
    assert rest.attributes["interval"] == "4-wöchentlich"

    nxt = hass.states.get("sensor.aisthofen_1_perg_next_pickup")
    assert nxt.state == "2026-11-02"
    assert nxt.attributes["waste_types"] == ["Restabfall"]


async def test_midnight_rollover(hass: HomeAssistant, entry, freezer) -> None:
    freezer.move_to(datetime(2026, 11, 3, 0, 0, 2, tzinfo=dt_util.get_default_time_zone()))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.aisthofen_1_perg_next_pickup").state == "2026-11-16"
    assert hass.states.get("sensor.aisthofen_1_perg_restabfall").state == "unknown"


async def test_calendar(hass: HomeAssistant, entry) -> None:
    state = hass.states.get("calendar.aisthofen_1_perg")
    assert state.attributes["message"] == "Restabfall"

    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.aisthofen_1_perg",
            "start_date_time": "2026-10-01T00:00:00+02:00",
            "end_date_time": "2026-11-16T00:00:00+01:00",
        },
        blocking=True,
        return_response=True,
    )
    events = result["calendar.aisthofen_1_perg"]["events"]
    # 16.11 starts exactly at the end of the range and is excluded.
    assert [(e["start"], e["summary"]) for e in events] == [
        ("2026-10-14", "Bioabfall"),
        ("2026-11-02", "Restabfall"),
    ]


async def test_unload(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_relocate_when_ids_change(hass: HomeAssistant, mock_client) -> None:
    """If the stored IDs return nothing, the address is looked up again by name."""
    from custom_components.abfall_ooe.parser import filter_pickups

    from .conftest import PICKUPS, TYPE_INTERVALS

    async def _get_pickups(location, interval, interval_title=None):
        if location.house_number != "new-house":
            return []
        return filter_pickups(PICKUPS, TYPE_INTERVALS, interval, interval_title)

    mock_client.get_pickups.side_effect = _get_pickups
    mock_client.get_cities.return_value = {"new-city": "Perg"}
    mock_client.get_streets.return_value = {"new-street": "Aisthofen"}
    mock_client.get_house_numbers.return_value = {"new-house": "1", "x": "1a"}

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="97941052",
        title="Aisthofen 1, Perg",
        data={
            "district": "10", "city": "93290", "street": "5662262", "house_number": "97941052",
            "city_name": "Perg", "street_name": "Aisthofen", "house_number_name": "1",
            CONF_INTERVAL: "o4w", "interval_name": "4-wöchentlich",
            "intervals": {"o2w": "2-wöchentlich", "o4w": "4-wöchentlich"},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data["city"] == "new-city"
    assert entry.data["street"] == "new-street"
    assert entry.data["house_number"] == "new-house"
    assert entry.unique_id == "new-house"
    assert entry.runtime_data.data
