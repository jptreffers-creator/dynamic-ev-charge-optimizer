"""The override: charge now, whatever the prices say."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DynamicEvChargeOptimizerCoordinator
from .entity import DynamicEvChargeOptimizerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DynamicEvChargeOptimizerCoordinator = entry.runtime_data
    async_add_entities([ChargeImmediatelySwitch(coordinator)])


class ChargeImmediatelySwitch(DynamicEvChargeOptimizerEntity, SwitchEntity):
    """Charge right now, ignoring the schedule and the prices.

    A switch and not a button, because this has a state worth seeing. An override
    you cannot tell is running is an override you forget, and forgetting this one
    costs money every quarter of an hour.

    Switching it off does not stop the charger: it hands the decision back to the
    schedule, which may well want to keep charging. Stopping is what Stop is for.
    """

    _attr_name = "Charge immediately"
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator: DynamicEvChargeOptimizerCoordinator) -> None:
        super().__init__(coordinator, "charge_immediately")

    @property
    def is_on(self) -> bool:
        return self.coordinator.charge_now_override

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_charge_now(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_charge_now(False)
