"""The adjustable settings, as proper entities rather than YAML helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_BATTERY_CAPACITY, CONF_CHARGE_POWER, CONF_TARGET_SOC
from .coordinator import DynamicEvChargeOptimizerCoordinator
from .entity import DynamicEvChargeOptimizerEntity


@dataclass(frozen=True, kw_only=True)
class PlannerNumberDescription(NumberEntityDescription):
    setting: str
    default: float


NUMBERS: tuple[PlannerNumberDescription, ...] = (
    PlannerNumberDescription(
        key="charge_power",
        name="Charging power",
        setting=CONF_CHARGE_POWER,
        default=11.0,
        native_min_value=1.0,
        native_max_value=50.0,
        native_step=0.1,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        mode=NumberMode.BOX,
        icon="mdi:flash",
    ),
    PlannerNumberDescription(
        key="battery_capacity",
        name="Car battery capacity",
        setting=CONF_BATTERY_CAPACITY,
        default=60.0,
        native_min_value=5.0,
        native_max_value=200.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        mode=NumberMode.BOX,
        icon="mdi:car-battery",
    ),
    PlannerNumberDescription(
        key="target_soc",
        name="Target charge level",
        setting=CONF_TARGET_SOC,
        default=80.0,
        native_min_value=10,
        native_max_value=100,
        native_step=5,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        icon="mdi:battery-charging-80",
    ),
    PlannerNumberDescription(
        key="energy_override",
        name="Fixed energy to add",
        setting="energy_override",
        default=0.0,
        native_min_value=0.0,
        native_max_value=200.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        mode=NumberMode.BOX,
        icon="mdi:pencil",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DynamicEvChargeOptimizerCoordinator = entry.runtime_data
    async_add_entities(PlannerNumber(coordinator, desc) for desc in NUMBERS)


class PlannerNumber(DynamicEvChargeOptimizerEntity, NumberEntity):
    """A view on one coordinator setting.

    The value lives in the coordinator's store rather than in the entity, so the
    planner never has to read its own entities back out of the state machine to know
    what it was told.
    """

    entity_description: PlannerNumberDescription

    def __init__(
        self,
        coordinator: DynamicEvChargeOptimizerCoordinator,
        description: PlannerNumberDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return float(
            self.coordinator.settings.get(
                self.entity_description.setting, self.entity_description.default
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_setting(self.entity_description.setting, value)
