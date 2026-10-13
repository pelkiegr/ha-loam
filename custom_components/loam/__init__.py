"""The Loam ride conditions integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import LoamClient
from .const import DOMAIN
from .coordinator import LoamConfigEntry, LoamCoordinator
from .cards import async_register_cards
from .websocket import async_register_websocket_commands

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_websocket_commands(hass)
    await async_register_cards(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LoamConfigEntry) -> bool:
    client = LoamClient(async_get_clientsession(hass))
    coordinator = LoamCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LoamConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
