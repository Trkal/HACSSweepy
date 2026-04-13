"""DataUpdateCoordinator for the Sweepy integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SweepyApiClient, SweepyAuthError, SweepyApiError
from .const import DEFAULT_SCAN_INTERVAL, LOGGER


class SweepyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch Sweepy data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: SweepyApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name="Sweepy",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=config_entry,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Sweepy API."""
        try:
            schedule, rooms, profiles, schedules = await asyncio.gather(
                self.client.async_get_today_schedule(),
                self.client.async_get_rooms(),
                self.client.async_get_profiles(),
                self.client.async_get_schedules(),
            )
        except SweepyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SweepyApiError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

        # Build a task lookup from the full schedules data
        tasks_by_id: dict[str, dict] = {}
        for sched in schedules:
            for task in sched.get("tasks", []):
                tasks_by_id[task["id"]] = task

        return {
            "today_schedule": schedule,
            "rooms": rooms,
            "profiles": profiles,
            "schedules": schedules,
            "tasks_by_id": tasks_by_id,
        }
