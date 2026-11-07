"""Shared base for every entity this integration publishes."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EvChargePlannerCoordinator


class EvChargePlannerEntity(CoordinatorEntity[EvChargePlannerCoordinator]):
    """Groups everything under one service device so it is tidy in the UI."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EvChargePlannerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="EV Charge Planner",
            manufacturer="EV Charge Planner",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def plan(self):
        return self.coordinator.data
