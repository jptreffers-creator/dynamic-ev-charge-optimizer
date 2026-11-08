"""The actions: start, stop, adopt the measured speed, and refresh the car."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import car_adapters
from .const import CONF_CAR_PRESET, CONF_CAR_REFRESH_BUTTON
from .coordinator import DynamicEvChargeOptimizerCoordinator
from .entity import DynamicEvChargeOptimizerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: DynamicEvChargeOptimizerCoordinator = entry.runtime_data
    buttons: list[ButtonEntity] = [
        StartChargingButton(coordinator),
        StopButton(coordinator),
        AdoptMeasuredPowerButton(coordinator),
    ]

    # Only offer the refresh button when there is actually something to press, so an
    # unconfigured car does not leave a dead control on the dashboard.
    preset = car_adapters.PRESETS.get(
        entry.options.get(CONF_CAR_PRESET, car_adapters.PRESET_NONE)
    )
    if preset and preset.supports_refresh and entry.options.get(CONF_CAR_REFRESH_BUTTON):
        buttons.append(RefreshCarButton(coordinator))

    async_add_entities(buttons)


class StartChargingButton(DynamicEvChargeOptimizerEntity, ButtonEntity):
    """Work out the cheapest moments and commit them as the schedule.

    It does not start the charger there and then: it books the cheap periods, and
    charging begins when the first one arrives.
    """

    _attr_name = "Start charging"
    _attr_icon = "mdi:play"

    def __init__(self, coordinator: DynamicEvChargeOptimizerCoordinator) -> None:
        super().__init__(coordinator, "start_charging")

    async def async_press(self) -> None:
        await self.coordinator.async_apply_suggestion()


class StopButton(DynamicEvChargeOptimizerEntity, ButtonEntity):
    """Clear the schedule and switch off.

    Both halves are needed. Clearing alone would leave the charger running, because
    with no schedule the planner deliberately keeps its hands off the switch.
    """

    _attr_name = "Stop"
    _attr_icon = "mdi:stop"

    def __init__(self, coordinator: DynamicEvChargeOptimizerCoordinator) -> None:
        super().__init__(coordinator, "stop")

    async def async_press(self) -> None:
        await self.coordinator.async_stop()


class AdoptMeasuredPowerButton(DynamicEvChargeOptimizerEntity, ButtonEntity):
    """Calibrate: replace the configured charging power with the measured one."""

    _attr_name = "Use measured charging power"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: DynamicEvChargeOptimizerCoordinator) -> None:
        super().__init__(coordinator, "adopt_measured_power")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.measured_power is not None

    async def async_press(self) -> None:
        await self.coordinator.async_adopt_measured_power()


class RefreshCarButton(DynamicEvChargeOptimizerEntity, ButtonEntity):
    """Ask the car for a fresh charge level, subject to the guards.

    Pressing it when the reading is still fresh, or again straight away, does
    nothing: the rate limit lives in the coordinator so no caller can talk the
    integration into waking a vehicle repeatedly.
    """

    _attr_name = "Refresh car"
    _attr_icon = "mdi:car-connected"

    def __init__(self, coordinator: DynamicEvChargeOptimizerCoordinator) -> None:
        super().__init__(coordinator, "refresh_car")

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_car()
