"""Base entity for Abfall OÖ."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CALENDAR_PAGE
from .const import DOMAIN
from .coordinator import AbfallOoeCoordinator


class AbfallOoeEntity(CoordinatorEntity[AbfallOoeCoordinator]):
    """Groups all entities of one address under a service device."""

    _attr_has_entity_name = True
    _attr_attribution = "Daten: umweltprofis.at"

    def __init__(self, coordinator: AbfallOoeCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Umweltprofis OÖ",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CALENDAR_PAGE,
        )
