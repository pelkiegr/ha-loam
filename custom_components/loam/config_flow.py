"""Config flow for the Loam integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import LoamClient, LoamError, SearchResult
from .const import CONF_NETWORK_ID, CONF_QUERY, DOMAIN

SEARCH_SCHEMA = vol.Schema({vol.Required(CONF_QUERY): TextSelector()})


class LoamConfigFlow(ConfigFlow, domain=DOMAIN):
    """Search Loam and add one trail network per config entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._results: dict[str, SearchResult] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = LoamClient(async_get_clientsession(self.hass))
            try:
                results = await client.async_search(user_input[CONF_QUERY].strip())
            except LoamError:
                errors["base"] = "cannot_connect"
            else:
                self._results = self._unconfigured(results)
                if self._results:
                    return await self.async_step_network()
                errors["base"] = "no_results"

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SEARCH_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            result = self._results[user_input[CONF_NETWORK_ID]]
            await self.async_set_unique_id(result.network_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=result.name, data={CONF_NETWORK_ID: result.network_id}
            )

        options = [
            SelectOptionDict(value=result.network_id, label=_describe(result))
            for result in self._results.values()
        ]
        return self.async_show_form(
            step_id="network",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NETWORK_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    def _unconfigured(self, results: list[SearchResult]) -> dict[str, SearchResult]:
        configured = self._async_current_ids(include_ignore=False)
        return {
            result.network_id: result
            for result in results
            if result.network_id not in configured
        }


def _describe(result: SearchResult) -> str:
    place = ", ".join(part for part in (result.region, result.state) if part)
    label = f"{result.name} — {place}" if place else result.name
    if result.distance_km is not None:
        label += f" ({result.distance_km:g} km)"
    return label
