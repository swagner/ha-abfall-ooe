"""Data update coordinator for Abfall OÖ."""

from __future__ import annotations

from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AbfallOoeClient, AbfallOoeError, Location
from .const import (
    CONF_CITY,
    CONF_DISTRICT,
    CONF_HOUSE_NUMBER,
    CONF_INTERVAL,
    CONF_STREET,
    DOMAIN,
    LOGGER,
    NAME_SUFFIX,
    UPDATE_INTERVAL,
)
from .parser import Pickup

type AbfallOoeConfigEntry = ConfigEntry[AbfallOoeCoordinator]


def _find_by_name(choices: dict[str, str], name: str | None) -> str | None:
    if not name:
        return None
    matches = [uid for uid, title in choices.items() if title.casefold() == name.casefold()]
    return matches[0] if len(matches) == 1 else None


class AbfallOoeCoordinator(DataUpdateCoordinator[list[Pickup]]):
    """Fetches the pickup calendar for one address."""

    config_entry: AbfallOoeConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: AbfallOoeConfigEntry, client: AbfallOoeClient
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    @property
    def location(self) -> Location:
        data = self.config_entry.data
        return Location(
            district=data[CONF_DISTRICT],
            city=data[CONF_CITY],
            street=data[CONF_STREET],
            house_number=data[CONF_HOUSE_NUMBER],
        )

    def _setting(self, key: str) -> str | None:
        """Options (from the options flow) take precedence over setup data."""
        if key in self.config_entry.options:
            return self.config_entry.options[key]
        return self.config_entry.data.get(key)

    @property
    def interval(self) -> str | None:
        return self._setting(CONF_INTERVAL)

    @property
    def interval_name(self) -> str | None:
        return self._setting(CONF_INTERVAL + NAME_SUFFIX)

    async def _async_update_data(self) -> list[Pickup]:
        try:
            pickups = await self.client.get_pickups(
                self.location, self.interval, self.interval_name
            )
            if not pickups and await self._async_relocate():
                pickups = await self.client.get_pickups(
                    self.location, self.interval, self.interval_name
                )
        except AbfallOoeError as err:
            raise UpdateFailed(str(err)) from err
        return pickups

    async def _async_relocate(self) -> bool:
        """Look the address up again by name if its IDs stopped returning data.

        The site's city/street/house-number IDs are database keys that may be
        regenerated when new data is imported; the names are stable.
        """
        data = self.config_entry.data
        city = _find_by_name(
            await self.client.get_cities(data[CONF_DISTRICT]), data.get(CONF_CITY + NAME_SUFFIX)
        )
        if city is None:
            return False
        street = _find_by_name(
            await self.client.get_streets(city), data.get(CONF_STREET + NAME_SUFFIX)
        )
        if street is None:
            return False
        house_number = _find_by_name(
            await self.client.get_house_numbers(street),
            data.get(CONF_HOUSE_NUMBER + NAME_SUFFIX),
        )
        if house_number is None:
            return False

        new_ids = {CONF_CITY: city, CONF_STREET: street, CONF_HOUSE_NUMBER: house_number}
        if all(data[key] == value for key, value in new_ids.items()):
            return False
        LOGGER.info("Address IDs of %s changed on umweltprofis.at, updating", self.config_entry.title)
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**data, **new_ids}, unique_id=house_number
        )
        return True

    def waste_types(self) -> dict[str, str]:
        """{waste_type_id: name} of all types in the current data."""
        return {p.waste_type_id: p.waste_type for p in self.data or []}

    def upcoming(self, today: date, waste_type_id: str | None = None) -> list[Pickup]:
        """Pickups from today on, optionally for a single waste type."""
        return [
            p
            for p in self.data or []
            if p.date >= today
            and (waste_type_id is None or p.waste_type_id == waste_type_id)
        ]
