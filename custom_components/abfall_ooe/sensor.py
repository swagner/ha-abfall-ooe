"""Sensors: next pickup date per waste type, plus the next pickup overall."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import UPCOMING_COUNT, icon_for
from .coordinator import AbfallOoeConfigEntry, AbfallOoeCoordinator
from .entity import AbfallOoeEntity
from .parser import Pickup

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AbfallOoeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one sensor per waste type; add types that show up later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_types() -> None:
        new = [
            WasteTypeSensor(coordinator, type_id, name)
            for type_id, name in coordinator.waste_types().items()
            if type_id not in known
        ]
        known.update(sensor.waste_type_id for sensor in new)
        if new:
            async_add_entities(new)

    async_add_entities([NextPickupSensor(coordinator)])
    _add_new_types()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_types))


def _attributes(today: date, upcoming: list[Pickup]) -> dict[str, Any]:
    if not upcoming:
        return {"days_until": None, "upcoming": []}
    return {
        "days_until": (upcoming[0].date - today).days,
        "upcoming": [p.date.isoformat() for p in upcoming[:UPCOMING_COUNT]],
    }


class WasteTypeSensor(AbfallOoeEntity, SensorEntity):
    """Next pickup date of one waste type."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: AbfallOoeCoordinator, waste_type_id: str, name: str) -> None:
        super().__init__(coordinator)
        self.waste_type_id = waste_type_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{waste_type_id}"
        self._attr_name = name
        self._attr_icon = icon_for(name)

    def _upcoming(self) -> tuple[date, list[Pickup]]:
        today = dt_util.now().date()
        return today, self.coordinator.upcoming(today, self.waste_type_id)

    @property
    def native_value(self) -> date | None:
        _, upcoming = self._upcoming()
        return upcoming[0].date if upcoming else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        today, upcoming = self._upcoming()
        attrs = _attributes(today, upcoming)
        attrs["interval"] = upcoming[0].interval if upcoming else None
        return attrs


class NextPickupSensor(AbfallOoeEntity, SensorEntity):
    """The next pickup of any waste type, listing every type collected that day."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_translation_key = "next_pickup"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: AbfallOoeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_next_pickup"

    def _next_day(self) -> tuple[date, list[Pickup]]:
        today = dt_util.now().date()
        upcoming = self.coordinator.upcoming(today)
        if not upcoming:
            return today, []
        return today, [p for p in upcoming if p.date == upcoming[0].date]

    @property
    def native_value(self) -> date | None:
        _, pickups = self._next_day()
        return pickups[0].date if pickups else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        today, pickups = self._next_day()
        return {
            "days_until": (pickups[0].date - today).days if pickups else None,
            "waste_types": [p.waste_type for p in pickups],
        }
