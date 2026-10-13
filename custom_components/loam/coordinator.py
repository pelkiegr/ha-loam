"""Data update coordinator for the Loam integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LoamClient, LoamError, TrailConditions
from .const import CONF_NETWORK_ID, DOMAIN, LOGGER, UPDATE_INTERVAL

type LoamConfigEntry = ConfigEntry[LoamCoordinator]


class LoamCoordinator(DataUpdateCoordinator[TrailConditions]):
    """Fetches conditions for one trail network."""

    config_entry: LoamConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: LoamConfigEntry, client: LoamClient
    ) -> None:
        self.network_id: str = entry.data[CONF_NETWORK_ID]
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.network_id}",
            update_interval=UPDATE_INTERVAL,
        )
        self._client = client
        self._reported_statuses: set[str] = set()

    async def _async_update_data(self) -> TrailConditions:
        try:
            conditions = await self._client.async_get_conditions(self.network_id)
        except LoamError as err:
            raise UpdateFailed(str(err)) from err
        self._warn_once_about_unknown_status(conditions)
        return conditions

    def _warn_once_about_unknown_status(self, conditions: TrailConditions) -> None:
        if conditions.is_known_status or conditions.status in self._reported_statuses:
            return
        self._reported_statuses.add(conditions.status)
        LOGGER.warning(
            "Loam reported an unrecognized status %r for %s; please add it to "
            "KNOWN_STATUSES",
            conditions.status,
            self.network_id,
        )
