"""Constants for the Sweepy integration."""

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "sweepy"

API_BASE_URL: Final = "https://api.sweepy.com"
OAUTH_TOKEN_URL: Final = "/oauth/token"

CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"

DEFAULT_SCAN_INTERVAL: Final = 300  # 5 minutes
