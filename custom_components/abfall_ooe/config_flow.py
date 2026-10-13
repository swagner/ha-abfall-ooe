"""Config flow for Abfall OÖ: district -> city -> street -> house number -> interval."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import create_client
from .api import AbfallOoeClient, AbfallOoeError, Location
from .const import (
    CONF_CITY,
    CONF_DISTRICT,
    CONF_HOUSE_NUMBER,
    CONF_INTERVAL,
    CONF_INTERVALS,
    CONF_STREET,
    DOMAIN,
    LOGGER,
    NAME_SUFFIX,
)
from .coordinator import AbfallOoeConfigEntry


def _select_schema(key: str, choices: dict[str, str], sort: bool = True) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(key): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=value, label=label)
                        for value, label in choices.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    sort=sort,
                )
            )
        }
    )


class AbfallOoeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Walk the user through the same cascade as the website."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: AbfallOoeClient | None = None
        self._data: dict[str, Any] = {}
        self._choices: dict[str, str] = {}
        self._intervals: dict[str, str] = {}

    @property
    def client(self) -> AbfallOoeClient:
        if self._client is None:
            self._client = create_client(self.hass)
        return self._client

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: AbfallOoeConfigEntry) -> OptionsFlow:
        return AbfallOoeOptionsFlow()

    async def _step(
        self,
        step_id: str,
        key: str,
        user_input: dict[str, Any] | None,
        load,
        next_step,
        empty_reason: str,
    ) -> ConfigFlowResult:
        """Shared logic: show a dropdown, store the pick, move to the next step."""
        if user_input is not None and user_input.get(key) in self._choices:
            value = user_input[key]
            self._data[key] = value
            self._data[key + NAME_SUFFIX] = self._choices[value]
            return await next_step()

        try:
            self._choices = await load()
        except AbfallOoeError as err:
            LOGGER.warning("Lookup for %s failed: %s", step_id, err)
            return self.async_abort(reason="cannot_connect")
        if not self._choices:
            return self.async_abort(reason=empty_reason)
        return self.async_show_form(
            step_id=step_id,
            data_schema=_select_schema(key, self._choices),
            description_placeholders=self._placeholders(),
        )

    def _placeholders(self) -> dict[str, str]:
        return {
            key: self._data.get(key + NAME_SUFFIX, "")
            for key in (CONF_DISTRICT, CONF_CITY, CONF_STREET, CONF_HOUSE_NUMBER)
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step(
            "user", CONF_DISTRICT, user_input,
            self.client.get_districts, self.async_step_city, "no_districts",
        )

    async def async_step_city(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step(
            "city", CONF_CITY, user_input,
            lambda: self.client.get_cities(self._data[CONF_DISTRICT]),
            self.async_step_street, "no_cities",
        )

    async def async_step_street(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step(
            "street", CONF_STREET, user_input,
            lambda: self.client.get_streets(self._data[CONF_CITY]),
            self.async_step_house_number, "no_streets",
        )

    async def async_step_house_number(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._step(
            "house_number", CONF_HOUSE_NUMBER, user_input,
            lambda: self.client.get_house_numbers(self._data[CONF_STREET]),
            self._async_validate_address, "no_house_numbers",
        )

    async def _async_validate_address(self) -> ConfigFlowResult:
        """Make sure the address has pickup data and collect its intervals."""
        await self.async_set_unique_id(self._data[CONF_HOUSE_NUMBER])
        self._abort_if_unique_id_configured()

        location = Location(
            district=self._data[CONF_DISTRICT],
            city=self._data[CONF_CITY],
            street=self._data[CONF_STREET],
            house_number=self._data[CONF_HOUSE_NUMBER],
        )
        try:
            calendar = await self.client.get_calendar(location)
            intervals = await self.client.get_intervals(
                self._data[CONF_STREET], self._data[CONF_HOUSE_NUMBER]
            )
        except AbfallOoeError as err:
            LOGGER.warning("Fetching the calendar failed: %s", err)
            return self.async_abort(reason="cannot_connect")
        if not calendar.pickups:
            return self.async_abort(
                reason="no_pickups", description_placeholders=self._placeholders()
            )

        # The calendar's per-type dropdowns are authoritative; the interval
        # lookup only fills in titles if a type dropdown lacks one.
        for choices in calendar.type_intervals.values():
            for interval_id, title in choices.items():
                intervals.setdefault(interval_id, title)
        self._intervals = intervals
        if not intervals:
            return self._create_entry(None)
        return await self.async_step_interval()

    async def async_step_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None and user_input.get(CONF_INTERVAL) in self._intervals:
            return self._create_entry(user_input[CONF_INTERVAL])
        return self.async_show_form(
            step_id="interval",
            data_schema=_select_schema(CONF_INTERVAL, self._intervals),
            description_placeholders=self._placeholders(),
        )

    def _create_entry(self, interval: str | None) -> ConfigFlowResult:
        data = {
            **self._data,
            CONF_INTERVAL: interval,
            CONF_INTERVAL + NAME_SUFFIX: self._intervals.get(interval) if interval else None,
            CONF_INTERVALS: self._intervals,
        }
        title = (
            f"{data[CONF_STREET + NAME_SUFFIX]} {data[CONF_HOUSE_NUMBER + NAME_SUFFIX]}, "
            f"{data[CONF_CITY + NAME_SUFFIX]}"
        )
        return self.async_create_entry(title=title, data=data)


class AbfallOoeOptionsFlow(OptionsFlowWithReload):
    """Change the pickup interval of an existing address."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        intervals: dict[str, str] = self.config_entry.data.get(CONF_INTERVALS) or {}
        if not intervals:
            return self.async_abort(reason="no_intervals")
        if user_input is not None and user_input.get(CONF_INTERVAL) in intervals:
            interval = user_input[CONF_INTERVAL]
            return self.async_create_entry(
                data={CONF_INTERVAL: interval, CONF_INTERVAL + NAME_SUFFIX: intervals[interval]}
            )

        current = self.config_entry.options.get(
            CONF_INTERVAL, self.config_entry.data.get(CONF_INTERVAL)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _select_schema(CONF_INTERVAL, intervals), {CONF_INTERVAL: current}
            ),
        )
