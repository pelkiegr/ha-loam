"""Sensors for the Loam integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import KNOWN_STATUSES, TrailConditions
from .coordinator import LoamConfigEntry, LoamCoordinator
from .entity import LoamEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LoamSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[TrailConditions], StateType | datetime]
    attributes_fn: Callable[[TrailConditions], dict[str, Any]] | None = None


def _known_status(conditions: TrailConditions) -> str | None:
    return conditions.status_key if conditions.is_known_status else None


def _status_attributes(conditions: TrailConditions) -> dict[str, Any]:
    return {"label": conditions.status_label, "raw_status": conditions.status}


SENSORS: tuple[LoamSensorEntityDescription, ...] = (
    LoamSensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=list(KNOWN_STATUSES),
        value_fn=_known_status,
        attributes_fn=_status_attributes,
    ),
    LoamSensorEntityDescription(
        key="outlook",
        translation_key="outlook",
        value_fn=lambda conditions: conditions.outlook,
    ),
    LoamSensorEntityDescription(
        key="note",
        translation_key="note",
        value_fn=lambda conditions: conditions.note,
    ),
    LoamSensorEntityDescription(
        key="last_rain",
        translation_key="last_rain",
        value_fn=lambda conditions: conditions.last_rain,
    ),
    LoamSensorEntityDescription(
        key="observed_at",
        translation_key="observed_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda conditions: conditions.observed_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LoamConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LoamSensor(coordinator, description) for description in SENSORS)


class LoamSensor(LoamEntity, SensorEntity):
    entity_description: LoamSensorEntityDescription

    def __init__(
        self, coordinator: LoamCoordinator, description: LoamSensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
