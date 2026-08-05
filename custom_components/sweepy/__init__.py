"""The Sweepy integration."""

from __future__ import annotations

from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SweepyApiClient, SweepyAuthError
from .const import CONF_EMAIL, CONF_PASSWORD, CONF_TOKEN, DOMAIN, LOGGER
from .coordinator import SweepyCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.TODO]

type SweepyConfigEntry = ConfigEntry[SweepyCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SweepyConfigEntry) -> bool:
    """Set up Sweepy from a config entry."""
    session = async_get_clientsession(hass)

    @callback
    def _persist_token(token_data: dict[str, Any]) -> None:
        """Write a rotated token back to the entry the moment it changes.

        Persisting eagerly (rather than after a successful poll) means a
        rotation is never lost when a later request in the same cycle fails.
        """
        if entry.data.get(CONF_TOKEN) != token_data:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_TOKEN: token_data}
            )

    client = SweepyApiClient(
        session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        token_callback=_persist_token,
    )

    if saved_token := entry.data.get(CONF_TOKEN):
        client.set_token_data(saved_token)
        LOGGER.debug("Restored saved Sweepy token from config entry")

    # Only hits the network if the saved token is missing or near expiry, and
    # falls back to a password login by itself if the refresh chain is broken.
    try:
        await client.async_ensure_authenticated()
    except SweepyAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (aiohttp.ClientError, TimeoutError) as err:
        raise ConfigEntryNotReady(f"Failed to connect: {err}") from err

    coordinator = SweepyCoordinator(hass, client, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SweepyConfigEntry) -> bool:
    """Unload a Sweepy config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
