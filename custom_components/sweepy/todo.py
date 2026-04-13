"""Todo platform for the Sweepy integration."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import LOGGER
from .coordinator import SweepyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sweepy todo lists."""
    coordinator: SweepyCoordinator = entry.runtime_data
    entities: list[TodoListEntity] = []

    for profile in coordinator.data.get("profiles", []):
        entities.append(
            SweepyTodoList(
                coordinator,
                profile_id=profile["id"],
                profile_name=profile["name"],
            )
        )

    async_add_entities(entities)


class SweepyTodoList(CoordinatorEntity[SweepyCoordinator], TodoListEntity):
    """A todo list representing a Sweepy profile's tasks for today."""

    _attr_has_entity_name = True
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(
        self,
        coordinator: SweepyCoordinator,
        profile_id: str,
        profile_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._profile_id = profile_id
        self._attr_name = f"{profile_name} tasks"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_todo_{profile_id}"
        )

    def _get_today_schedule(self) -> dict[str, Any] | None:
        """Find today's schedule for this profile."""
        today = date.today().isoformat()
        for sched in self.coordinator.data.get("schedules", []):
            if sched.get("date") == today and sched.get("profile_id") == self._profile_id:
                return sched
        return None

    def _is_task_done_today(self, task: dict[str, Any]) -> bool:
        """Check if a task was completed today."""
        last_event = task.get("last_event_date") or task.get("last_event")
        if not last_event:
            return False
        try:
            event_date = datetime.fromisoformat(last_event.replace("Z", "+00:00")).date()
            return event_date == date.today()
        except (ValueError, AttributeError):
            return False

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return today's tasks as todo items."""
        schedule = self._get_today_schedule()
        if not schedule:
            return []

        items: list[TodoItem] = []
        tasks_by_id = self.coordinator.data.get("tasks_by_id", {})

        for assignment in schedule.get("task_assignments", []):
            task_id = assignment["task_id"]
            # First check full task data from schedules, then fallback to tasks_by_id
            task = None
            for t in schedule.get("tasks", []):
                if t["id"] == task_id:
                    task = t
                    break
            if task is None:
                task = tasks_by_id.get(task_id)
            if task is None:
                continue

            done = self._is_task_done_today(task)
            status = TodoItemStatus.COMPLETED if done else TodoItemStatus.NEEDS_ACTION

            description_parts = []
            if task.get("effort"):
                effort_labels = {1: "Light", 2: "Medium", 3: "Heavy"}
                description_parts.append(f"Effort: {effort_labels.get(task['effort'], task['effort'])}")
            if task.get("due_date"):
                description_parts.append(f"Due: {task['due_date']}")

            items.append(
                TodoItem(
                    uid=task_id,
                    summary=task["name"],
                    status=status,
                    description=" | ".join(description_parts) if description_parts else None,
                )
            )

        return items

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Mark a task as done when checked off in HA."""
        if item.status == TodoItemStatus.COMPLETED and item.uid:
            LOGGER.info("Marking task %s as done", item.uid)
            await self.coordinator.client.async_mark_task_done(item.uid)
            await self.coordinator.async_request_refresh()
