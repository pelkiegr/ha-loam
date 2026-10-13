"""Serves the Loam dashboard cards and loads them on every dashboard."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

CARDS_FILE = Path(__file__).parent / "frontend" / "loam-cards.js"
CARDS_URL = f"/{DOMAIN}/loam-cards.js"


async def async_register_cards(hass: HomeAssistant) -> None:
    """Register the card script; the version query busts browser caches on upgrade."""
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARDS_URL, str(CARDS_FILE), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARDS_URL}?v={integration.version}")
