"""Tests for the config and options flow."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abfall_ooe.api import AbfallOoeConnectionError, CalendarData
from custom_components.abfall_ooe.const import CONF_INTERVAL, DOMAIN


async def _walk_to_interval(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    for step, key, value in (
        ("user", "district", "10"),
        ("city", "city", "93290"),
        ("street", "street", "5662262"),
        ("house_number", "house_number", "97941052"),
    ):
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == step
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {key: value}
        )
    return result


async def test_full_flow(hass: HomeAssistant, mock_client) -> None:
    result = await _walk_to_interval(hass)
    assert result["step_id"] == "interval"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_INTERVAL: "o4w"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Aisthofen 1, Perg"
    assert result["result"].unique_id == "97941052"
    data = result["data"]
    assert data["district"] == "10"
    assert data["district_name"] == "Perg"
    assert data[CONF_INTERVAL] == "o4w"
    assert data["interval_name"] == "4-wöchentlich"
    assert data["intervals"] == {"o2w": "2-wöchentlich", "o4w": "4-wöchentlich"}


async def test_flow_without_intervals_skips_step(hass: HomeAssistant, mock_client) -> None:
    mock_client.get_calendar.return_value = CalendarData(
        [p for p in mock_client.get_calendar.return_value.pickups if p.waste_type_id != "t430"],
        {},
    )
    result = await _walk_to_interval(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_INTERVAL] is None


async def test_flow_aborts_without_pickups(hass: HomeAssistant, mock_client) -> None:
    mock_client.get_calendar.return_value = CalendarData([], {})
    result = await _walk_to_interval(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_pickups"


async def test_flow_cannot_connect(hass: HomeAssistant, mock_client) -> None:
    mock_client.get_districts.side_effect = AbfallOoeConnectionError("boom")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_flow_already_configured(hass: HomeAssistant, mock_client) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="97941052").add_to_hass(hass)
    result = await _walk_to_interval(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, mock_client) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="97941052",
        title="Aisthofen 1, Perg",
        data={
            "district": "10", "city": "93290", "street": "5662262",
            "house_number": "97941052", CONF_INTERVAL: "o2w",
            "intervals": {"o2w": "2-wöchentlich", "o4w": "4-wöchentlich"},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_INTERVAL: "o4w"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_INTERVAL: "o4w", "interval_name": "4-wöchentlich"}
    # The entry was reloaded and fetched with the new interval.
    mock_client.get_pickups.assert_called_with(
        entry.runtime_data.location, "o4w", "4-wöchentlich"
    )
