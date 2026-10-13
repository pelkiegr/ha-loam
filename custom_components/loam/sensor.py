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
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .api import KNOWN_STATUSES, TrailConditions, status_key
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


def _dryness_percent(conditions: TrailConditions) -> float | None:
    if conditions.timeline is None:
        return None
    dryness = conditions.timeline.dryness_at(dt_util.utcnow())
    return None if dryness is None else round(dryness * 100, 1)


def _next_change_at(conditions: TrailConditions) -> datetime | None:
    change = conditions.next_change(dt_util.utcnow())
    return None if change is None else change.at


def _next_change_attributes(conditions: TrailConditions) -> dict[str, Any]:
    change = conditions.next_change(dt_util.utcnow())
    if change is None:
        return {"to_status": None, "from_status": None}
    return {
        "to_status": status_key(change.to_status),
        "from_status": status_key(change.from_status),
    }


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
        key="dryness",
        translation_key="dryness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_dryness_percent,
    ),
    LoamSensorEntityDescription(
        key="next_change",
        translation_key="next_change",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_change_at,
        attributes_fn=_next_change_attributes,
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
