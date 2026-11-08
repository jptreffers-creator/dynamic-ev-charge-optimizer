"""Binary sensors: whether the plan wants the charger on, and whether it is costed."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DynamicEvChargeOptimizerCoordinator
from .entity import DynamicEvChargeOptimizerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DynamicEvChargeOptimizerCoordinator = entry.runtime_data
    async_add_entities([ChargeNowSensor(coordinator), PlanCompleteSensor(coordinator)])


class ChargeNowSensor(DynamicEvChargeOptimizerEntity, BinarySensorEntity):
    """Whether this moment falls inside a scheduled period.

    A lamp, not a switch: it says what the plan wants, which is not the same as what
    the charger is doing. Those can differ briefly around a boundary, or for longer
    if someone is charging by hand with no schedule set.
    """

    _attr_name = "Charge now"
    _attr_icon = "mdi:ev-plug-type2"

    def __init__(self, coordinator: DynamicEvChargeOptimizerCoordinator) -> None:
        super().__init__(coordinator, "charge_now")

    @property
    def is_on(self) -> bool:
        return bool(self.plan and self.plan.charge_now)


class PlanCompleteSensor(DynamicEvChargeOptimizerEntity, BinarySensorEntity):
    """Off when part of the schedule falls beyond the last known price.

    Tomorrow's prices usually appear in the early afternoon, so a plan made before
    then can reach past the horizon. Saying so is better than quoting a total that
    silently omits the uncosted hours.
    """

    _attr_name = "Plan fully priced"
    _attr_icon = "mdi:check-decagram"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: DynamicEvChargeOptimizerCoordinator) -> None:
        super().__init__(coordinator, "plan_complete")

    @property
    def is_on(self) -> bool:
        return bool(self.plan and self.plan.committed.complete)
