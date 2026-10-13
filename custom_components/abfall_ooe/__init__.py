"""The Abfall OÖ integration: waste pickup dates from umweltprofis.at."""

from __future__ import annotations

import aiohttp
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import AbfallOoeClient
from .coordinator import AbfallOoeConfigEntry, AbfallOoeCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]


def create_client(hass: HomeAssistant) -> AbfallOoeClient:
    """Client with its own cookie jar; the site keeps the address in the session."""
    return AbfallOoeClient(
        async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    )


async def async_setup_entry(hass: HomeAssistant, entry: AbfallOoeConfigEntry) -> bool:
    """Set up Abfall OÖ from a config entry."""
    coordinator = AbfallOoeCoordinator(hass, entry, create_client(hass))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _midnight(_now) -> None:
        # "Next pickup" depends on today's date, not only on fetched data.
        coordinator.async_update_listeners()

    entry.async_on_unload(
        async_track_time_change(hass, _midnight, hour=0, minute=0, second=1)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AbfallOoeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
