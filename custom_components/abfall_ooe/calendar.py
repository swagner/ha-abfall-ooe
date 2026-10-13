"""Calendar entity with all pickups of an address."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AbfallOoeConfigEntry, AbfallOoeCoordinator
from .entity import AbfallOoeEntity
from .parser import Pickup

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AbfallOoeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AbfallOoeCalendar(entry.runtime_data)])


def _event(pickup: Pickup) -> CalendarEvent:
    return CalendarEvent(
        start=pickup.date,
        end=pickup.date + timedelta(days=1),
        summary=pickup.waste_type,
        description=pickup.interval or None,
        uid=f"{pickup.waste_type_id}-{pickup.date.isoformat()}",
    )


class AbfallOoeCalendar(AbfallOoeEntity, CalendarEntity):
    """All-day events, one per waste type and pickup day."""

    _attr_name = None

    def __init__(self, coordinator: AbfallOoeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_calendar"

    @property
    def event(self) -> CalendarEvent | None:
        upcoming = self.coordinator.upcoming(dt_util.now().date())
        return _event(upcoming[0]) if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = []
        for pickup in self.coordinator.data or []:
            day_start = dt_util.start_of_local_day(pickup.date)
            if day_start < end_date and day_start + timedelta(days=1) > start_date:
                events.append(_event(pickup))
        return events
