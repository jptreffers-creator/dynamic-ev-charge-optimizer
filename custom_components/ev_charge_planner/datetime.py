"""The deadline: an absolute moment that looks after itself."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import EvChargePlannerCoordinator
from .entity import EvChargePlannerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DeadlineEntity(entry.runtime_data)])


class DeadlineEntity(EvChargePlannerEntity, DateTimeEntity):
    """When the car should be ready.

    Set it to any moment you like. Once that moment has passed it falls back to the
    next occurrence of the time configured during setup -- so with 07:00 in there it
    is always the coming morning, and nobody has to edit a date every day.
    """

    _attr_name = "Ready by"
    _attr_icon = "mdi:clock-end"

    def __init__(self, coordinator: EvChargePlannerCoordinator) -> None:
        super().__init__(coordinator, "deadline")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.effective_deadline(dt_util.now())

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.async_set_setting(
            "deadline", dt_util.as_local(value).isoformat()
        )
