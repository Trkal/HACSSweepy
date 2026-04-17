"""The Sweepy integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
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
    client = SweepyApiClient(session)

    token_restored = False
    saved_token = entry.data.get(CONF_TOKEN)
    if saved_token:
        client.set_token_data(saved_token)
        try:
            await client.async_refresh_token()
            token_restored = True
            LOGGER.debug("Restored session using saved refresh token")
        except (SweepyAuthError, Exception):
            LOGGER.debug("Saved refresh token expired, falling back to password login")

    if not token_restored:
        try:
            await client.async_login(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
        except SweepyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise ConfigEntryNotReady(f"Failed to connect: {err}") from err

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_TOKEN: client.get_token_data()}
    )

    coordinator = SweepyCoordinator(hass, client, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SweepyConfigEntry) -> bool:
    """Unload a Sweepy config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
