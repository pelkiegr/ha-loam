"""Constants for the Loam integration."""

from datetime import timedelta
import logging

DOMAIN = "loam"
LOGGER = logging.getLogger(__package__)

CONF_NETWORK_ID = "network_id"
CONF_QUERY = "query"

UPDATE_INTERVAL = timedelta(minutes=30)
ATTRIBUTION = "Trail conditions modeled by Loam (loamrideconditions.com)"
