"""EV Charge Planner: schedule car charging into the cheapest settlement periods."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_ADOPT_MEASURED_POWER,
    SERVICE_APPLY_SUGGESTION,
    SERVICE_REFRESH_CAR,
    SERVICE_STOP,
)
from .coordinator import EvChargePlannerCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATETIME,
    Platform.NUMBER,
    Platform.SENSOR,
]

SERVICE_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = EvChargePlannerCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Changing the options rebuilds everything, so new entity pickers take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinator_for(hass: HomeAssistant, call: ServiceCall) -> EvChargePlannerCoordinator:
    """Resolve which planner a service call is aimed at.

    With a single planner the entry_id can be left out, which is what the card does.
    With several, leaving it out is an error rather than a guess.
    """
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]

    if entry_id := call.data.get("entry_id"):
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry.runtime_data
        raise ServiceValidationError(f"No EV Charge Planner with entry_id {entry_id}")

    if len(entries) == 1:
        return entries[0].runtime_data
    raise ServiceValidationError(
        "More than one EV Charge Planner is configured; name one with entry_id"
    )


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_APPLY_SUGGESTION):
        return

    async def apply_suggestion(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_apply_suggestion()

    async def stop(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_stop()

    async def refresh_car(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_refresh_car()

    async def adopt_measured_power(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_adopt_measured_power()

    for name, handler in (
        (SERVICE_APPLY_SUGGESTION, apply_suggestion),
        (SERVICE_STOP, stop),
        (SERVICE_REFRESH_CAR, refresh_car),
        (SERVICE_ADOPT_MEASURED_POWER, adopt_measured_power),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=SERVICE_SCHEMA)
