"""Base entity for the Loam integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import trail_url
from .const import ATTRIBUTION, DOMAIN
from .coordinator import LoamCoordinator


class LoamEntity(CoordinatorEntity[LoamCoordinator]):
    """An entity belonging to one trail network's device."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: LoamCoordinator, key: str) -> None:
        super().__init__(coordinator)
        network_id = coordinator.network_id
        self._attr_unique_id = f"{network_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, network_id)},
            name=coordinator.config_entry.title,
            manufacturer="Loam",
            model="Trail network",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=trail_url(network_id),
        )
