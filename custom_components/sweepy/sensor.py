"""Sensor platform for the Sweepy integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SweepyCoordinator


@dataclass(frozen=True, kw_only=True)
class SweepyRoomSensorDescription(SensorEntityDescription):
    """Describes a Sweepy room sensor."""

    room_id: str
    room_name: str


@dataclass(frozen=True, kw_only=True)
class SweepyProfileSensorDescription(SensorEntityDescription):
    """Describes a Sweepy profile sensor."""

    profile_id: str
    profile_name: str
    value_fn: Callable[[dict[str, Any]], StateType]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sweepy sensors."""
    coordinator: SweepyCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    # Room cleanliness sensors
    for room in coordinator.data.get("rooms", []):
        entities.append(
            SweepyRoomSensor(
                coordinator,
                SweepyRoomSensorDescription(
                    key=f"room_{room['id']}_cleanliness",
                    name=f"{room['name']} cleanliness",
                    icon="mdi:broom",
                    native_unit_of_measurement="%",
                    state_class=SensorStateClass.MEASUREMENT,
                    room_id=room["id"],
                    room_name=room["name"],
                ),
            )
        )

    # Profile sensors
    for profile in coordinator.data.get("profiles", []):
        pid = profile["id"]
        pname = profile["name"]

        entities.append(
            SweepyProfileSensor(
                coordinator,
                SweepyProfileSensorDescription(
                    key=f"profile_{pid}_daily_points",
                    name=f"{pname} daily points",
                    icon="mdi:star",
                    state_class=SensorStateClass.TOTAL,
                    profile_id=pid,
                    profile_name=pname,
                    value_fn=lambda p: p.get("daily_points", 0),
                ),
            )
        )
        entities.append(
            SweepyProfileSensor(
                coordinator,
                SweepyProfileSensorDescription(
                    key=f"profile_{pid}_streak",
                    name=f"{pname} streak",
                    icon="mdi:fire",
                    state_class=SensorStateClass.MEASUREMENT,
                    profile_id=pid,
                    profile_name=pname,
                    value_fn=lambda p: p.get("streak", 0),
                ),
            )
        )
        entities.append(
            SweepyProfileSensor(
                coordinator,
                SweepyProfileSensorDescription(
                    key=f"profile_{pid}_total_points",
                    name=f"{pname} total points",
                    icon="mdi:trophy",
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    profile_id=pid,
                    profile_name=pname,
                    value_fn=lambda p: p.get("total_points", 0),
                ),
            )
        )

    # Today's task count sensor
    entities.append(SweepyTodayTaskCountSensor(coordinator))

    async_add_entities(entities)


class SweepyRoomSensor(CoordinatorEntity[SweepyCoordinator], SensorEntity):
    """Sensor showing a room's cleanliness percentage."""

    entity_description: SweepyRoomSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SweepyCoordinator,
        description: SweepyRoomSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{description.key}"
        )

    @property
    def native_value(self) -> StateType:
        for room in self.coordinator.data.get("rooms", []):
            if room["id"] == self.entity_description.room_id:
                pct = room.get("displayed_percent_clean", room.get("percent_clean", 0))
                return round(pct * 100, 1)
        return None


class SweepyProfileSensor(CoordinatorEntity[SweepyCoordinator], SensorEntity):
    """Sensor showing a profile metric (points, streak)."""

    entity_description: SweepyProfileSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SweepyCoordinator,
        description: SweepyProfileSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{description.key}"
        )

    @property
    def native_value(self) -> StateType:
        for profile in self.coordinator.data.get("profiles", []):
            if profile["id"] == self.entity_description.profile_id:
                return self.entity_description.value_fn(profile)
        return None


class SweepyTodayTaskCountSensor(CoordinatorEntity[SweepyCoordinator], SensorEntity):
    """Sensor showing how many tasks are scheduled today."""

    _attr_has_entity_name = True
    _attr_name = "Today's tasks"
    _attr_icon = "mdi:clipboard-list"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SweepyCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_today_task_count"
        )

    @property
    def native_value(self) -> StateType:
        today = date.today().isoformat()
        count = 0
        for sched in self.coordinator.data.get("schedules", []):
            if sched.get("date") == today:
                count += len(sched.get("task_assignments", []))
        return count
