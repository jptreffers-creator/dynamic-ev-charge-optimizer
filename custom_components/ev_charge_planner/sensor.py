"""Sensors: what the plan costs, when it runs, and how fast charging really is."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import EvChargePlannerCoordinator
from .entity import EvChargePlannerEntity
from .planner import Plan, PlanPart


def _periods_text(part: PlanPart) -> str:
    """A compact, readable summary. Deliberately a state, not an attribute: a state
    is visible in history, in logbooks and in a plain entities card."""
    if not part.periods:
        return "none"
    return ", ".join(
        f"{dt_util.as_local(p.start):%a %H:%M}-{dt_util.as_local(p.end):%H:%M}"
        for p in part.periods
    )


@dataclass(frozen=True, kw_only=True)
class PlannerSensorDescription(SensorEntityDescription):
    value: Callable[[EvChargePlannerCoordinator, Plan | None], Any]
    attributes: Callable[[Plan | None], dict[str, Any]] | None = None


def _part_attrs(part: PlanPart) -> dict[str, Any]:
    return {
        "periods": [
            {
                "start": p.start.isoformat(),
                "end": p.end.isoformat(),
                "slots": p.slots,
                "kwh": p.kwh,
                "cost": p.cost,
                "avg_price": p.avg_price,
            }
            for p in part.periods
        ],
        "switch_points": [
            {"at": sp.at.isoformat(), "action": sp.action} for sp in part.switch_points
        ],
        "complete": part.complete,
    }


SENSORS: tuple[PlannerSensorDescription, ...] = (
    PlannerSensorDescription(
        key="plan_cost",
        name="Plan cost",
        icon="mdi:currency-eur",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda c, p: p.committed.cost if p else None,
        attributes=lambda p: _part_attrs(p.committed) if p else {},
    ),
    PlannerSensorDescription(
        key="plan_energy",
        name="Plan energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        value=lambda c, p: p.committed.kwh if p else None,
    ),
    PlannerSensorDescription(
        key="plan_average_price",
        name="Plan average price",
        icon="mdi:chart-line",
        value=lambda c, p: p.committed.avg_price if p else None,
    ),
    PlannerSensorDescription(
        key="plan_periods",
        name="Plan periods",
        icon="mdi:calendar-range",
        value=lambda c, p: _periods_text(p.committed) if p else "none",
    ),
    PlannerSensorDescription(
        key="suggested_cost",
        name="Suggested cost",
        icon="mdi:currency-eur",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda c, p: p.suggested.cost if p else None,
        attributes=lambda p: _part_attrs(p.suggested) if p else {},
    ),
    PlannerSensorDescription(
        key="suggested_periods",
        name="Suggested periods",
        icon="mdi:lightbulb-on-outline",
        value=lambda c, p: _periods_text(p.suggested) if p else "none",
    ),
    PlannerSensorDescription(
        key="energy_needed",
        name="Energy needed",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-charging",
        value=lambda c, p: p.energy_needed if p else None,
    ),
    PlannerSensorDescription(
        key="prices_known_until",
        name="Prices known until",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda c, p: p.horizon_end if p and p.horizon_end else None,
        # Carries the parsed price list so the card can draw its graph without
        # knowing which price integration supplied it.
        attributes=lambda p: {},
    ),
    PlannerSensorDescription(
        key="measured_charge_power",
        name="Measured charging power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        icon="mdi:speedometer",
        value=lambda c, p: c.measured_power,
        attributes=lambda p: {},
    ),
    PlannerSensorDescription(
        key="price_status",
        name="Price status",
        icon="mdi:cash-clock",
        entity_registry_enabled_default=False,
        value=lambda c, p: c.price_error or "ok",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EvChargePlannerCoordinator = entry.runtime_data
    async_add_entities(PlannerSensor(coordinator, desc) for desc in SENSORS)


class PlannerSensor(EvChargePlannerEntity, SensorEntity):
    entity_description: PlannerSensorDescription

    def __init__(
        self,
        coordinator: EvChargePlannerCoordinator,
        description: PlannerSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value(self.coordinator, self.plan)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        if self._key == "measured_charge_power":
            return {"sessions": list(self.coordinator.measured_sessions)}
        if self._key == "prices_known_until":
            return {
                "slot_minutes": self.plan.slot_minutes if self.plan else None,
                "prices": [
                    {"start": slot.start.isoformat(), "price": slot.price}
                    for slot in self.coordinator.slots
                ],
            }
        return self.entity_description.attributes(self.plan)
