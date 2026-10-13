"""Constants for the Abfall OÖ integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "abfall_ooe"
LOGGER = logging.getLogger(__package__)

CONF_DISTRICT = "district"
CONF_CITY = "city"
CONF_STREET = "street"
CONF_HOUSE_NUMBER = "house_number"
CONF_INTERVAL = "interval"
# Display names stored alongside the IDs above, e.g. "city_name".
NAME_SUFFIX = "_name"
# {interval_id: title} offered for this address, kept for the options flow.
CONF_INTERVALS = "intervals"

UPDATE_INTERVAL = timedelta(hours=12)
UPCOMING_COUNT = 5

ICONS = {
    "restabfall": "mdi:trash-can",
    "bioabfall": "mdi:leaf",
    "biotonne": "mdi:leaf",
    "gelb": "mdi:recycle",
    "papier": "mdi:newspaper-variant-outline",
    "glas": "mdi:bottle-wine",
    "metall": "mdi:silverware-fork-knife",
    "sperr": "mdi:sofa",
    "problemstoff": "mdi:biohazard",
    "christbaum": "mdi:pine-tree",
}
DEFAULT_ICON = "mdi:delete"


def icon_for(waste_type: str) -> str:
    """Pick an icon by matching keywords in the German waste type name."""
    name = waste_type.lower()
    for keyword, icon in ICONS.items():
        if keyword in name:
            return icon
    return DEFAULT_ICON
