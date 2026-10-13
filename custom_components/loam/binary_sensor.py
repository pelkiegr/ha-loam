"""Binary sensors for the Loam integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LoamConfigEntry, LoamCoordinator
from .entity import LoamEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LoamConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LoamRideableBinarySensor(entry.runtime_data)])


class LoamRideableBinarySensor(LoamEntity, BinarySensorEntity):
    """On when Loam rates the trail PRIME, DRY, or DUSTY."""

    _attr_translation_key = "rideable"

    def __init__(self, coordinator: LoamCoordinator) -> None:
        super().__init__(coordinator, "rideable")

    @property
    def is_on(self) -> bool | None:
        conditions = self.coordinator.data
        return conditions.is_rideable if conditions.is_known_status else None
