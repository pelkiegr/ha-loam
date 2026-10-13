"""Websocket API that feeds the Loam dashboard cards.

The hourly timeline is a few hundred points per trail, so it is served on
demand here instead of as entity attributes, which the recorder would store
on every update.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .api import TrailConditions, trail_url
from .const import DOMAIN
from .coordinator import LoamConfigEntry


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_trail)


@websocket_api.websocket_command(
    {vol.Required("type"): "loam/trail", vol.Required("entity_id"): cv.entity_id}
)
@callback
def websocket_trail(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the full conditions for the trail that owns an entity."""
    entry = _loaded_entry_for_entity(hass, msg["entity_id"])
    if entry is None or entry.runtime_data.data is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"{msg['entity_id']} is not a loaded Loam trail entity",
        )
        return
    connection.send_result(msg["id"], serialize_conditions(entry.runtime_data.data))


def _loaded_entry_for_entity(
    hass: HomeAssistant, entity_id: str
) -> LoamConfigEntry | None:
    registry_entry = er.async_get(hass).async_get(entity_id)
    if registry_entry is None or registry_entry.platform != DOMAIN:
        return None
    entry = hass.config_entries.async_get_entry(registry_entry.config_entry_id)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        return None
    return entry


def serialize_conditions(conditions: TrailConditions) -> dict[str, Any]:
    timeline = conditions.timeline
    return {
        "network_id": conditions.network_id,
        "name": conditions.name,
        "url": trail_url(conditions.network_id),
        "status": conditions.status,
        "status_label": conditions.status_label,
        "outlook": conditions.outlook,
        "note": conditions.note,
        "last_rain": conditions.last_rain,
        "location": conditions.location,
        "observed_at": _isoformat(conditions.observed_at),
        "timeline": None
        if timeline is None
        else {
            "start": timeline.start.isoformat(),
            "step_hours": timeline.step.total_seconds() / 3600,
            "forecast_from_index": timeline.forecast_from_index,
            "dryness": timeline.dryness,
            "statuses": timeline.statuses,
            "rain_in": timeline.rain_in,
            "drier_bound": timeline.drier_bound,
            "wetter_bound": timeline.wetter_bound,
        },
        "changes": [
            {
                "at": change.at.isoformat(),
                "from": change.from_status,
                "to": change.to_status,
                "confirmed": change.confirmed,
            }
            for change in conditions.changes
        ],
        "daily": [
            {
                "day": day.day.isoformat(),
                "starts_at": _isoformat(day.starts_at),
                "precipitation_in": day.precipitation_in,
                "temp_max_c": day.temp_max_c,
                "weather_code": day.weather_code,
            }
            for day in conditions.daily
        ],
    }


def _isoformat(value: Any) -> str | None:
    return None if value is None else value.isoformat()
