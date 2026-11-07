"""Configuration UI for the EV charge planner.

Everything lives in entry.options rather than entry.data, so the options flow can
change any of it later without a reinstall. The two flows share their schema builders
below; duplicating them is how the setup screen and the edit screen drift apart.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import car_adapters, price_adapters
from .const import (
    CONF_BATTERY_CAPACITY,
    CONF_CAR_LAST_FETCH_ENTITY,
    CONF_CAR_PRESET,
    CONF_CAR_REFRESH_BUTTON,
    CONF_CAR_SOC_ENTITY,
    CONF_CAR_STALE_HOURS,
    CONF_CHARGE_POWER,
    CONF_CHARGER_POWER_SENSOR,
    CONF_CHARGER_SWITCH,
    CONF_DEADLINE_TIME,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_PRESET,
    CONF_PRICE_TIME_KEY,
    CONF_PRICE_VALUE_KEY,
    CONF_SESSION_ENERGY_SENSOR,
    CONF_TARGET_SOC,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_CHARGE_POWER,
    DEFAULT_DEADLINE_TIME,
    DEFAULT_STALE_HOURS,
    DEFAULT_TARGET_SOC,
    DOMAIN,
)

TITLE = "EV Charge Planner"


def _entity(domain: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


def _number(minimum: float, maximum: float, step: float, unit: str):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _options(choices: dict[str, str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=key, label=label)
                for key, label in choices.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def price_schema(current: dict[str, Any]) -> vol.Schema:
    labels = {key: shape.label for key, shape in price_adapters.PRESETS.items()}
    return vol.Schema(
        {
            vol.Required(
                CONF_PRICE_PRESET,
                default=current.get(CONF_PRICE_PRESET, price_adapters.PRESET_ENTSOE),
            ): _options(labels),
            vol.Required(
                CONF_PRICE_ENTITY, default=current.get(CONF_PRICE_ENTITY, vol.UNDEFINED)
            ): _entity("sensor"),
        }
    )


def generic_price_schema(current: dict[str, Any]) -> vol.Schema:
    base = price_adapters.PRESETS[price_adapters.PRESET_GENERIC]
    return vol.Schema(
        {
            vol.Required(
                CONF_PRICE_ATTRIBUTE,
                default=current.get(CONF_PRICE_ATTRIBUTE, base.attribute),
            ): str,
            vol.Required(
                CONF_PRICE_TIME_KEY,
                default=current.get(CONF_PRICE_TIME_KEY, base.time_key),
            ): str,
            vol.Required(
                CONF_PRICE_VALUE_KEY,
                default=current.get(CONF_PRICE_VALUE_KEY, base.value_key),
            ): str,
        }
    )


def charger_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_CHARGER_SWITCH,
                default=current.get(CONF_CHARGER_SWITCH, vol.UNDEFINED),
            ): _entity("switch"),
            vol.Optional(
                CONF_CHARGER_POWER_SENSOR,
                description={"suggested_value": current.get(CONF_CHARGER_POWER_SENSOR)},
            ): _entity("sensor"),
            vol.Optional(
                CONF_SESSION_ENERGY_SENSOR,
                description={"suggested_value": current.get(CONF_SESSION_ENERGY_SENSOR)},
            ): _entity("sensor"),
        }
    )


def car_schema(current: dict[str, Any]) -> vol.Schema:
    labels = {key: preset.label for key, preset in car_adapters.PRESETS.items()}
    return vol.Schema(
        {
            vol.Required(
                CONF_CAR_PRESET,
                default=current.get(CONF_CAR_PRESET, car_adapters.PRESET_NONE),
            ): _options(labels)
        }
    )


def car_details_schema(current: dict[str, Any], preset: str) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_CAR_SOC_ENTITY, default=current.get(CONF_CAR_SOC_ENTITY, vol.UNDEFINED)
        ): _entity("sensor")
    }
    if car_adapters.PRESETS[preset].supports_refresh:
        fields[
            vol.Optional(
                CONF_CAR_REFRESH_BUTTON,
                description={"suggested_value": current.get(CONF_CAR_REFRESH_BUTTON)},
            )
        ] = _entity("button")
        fields[
            vol.Optional(
                CONF_CAR_LAST_FETCH_ENTITY,
                description={
                    "suggested_value": current.get(CONF_CAR_LAST_FETCH_ENTITY)
                },
            )
        ] = _entity("sensor")
        fields[
            vol.Required(
                CONF_CAR_STALE_HOURS,
                default=current.get(CONF_CAR_STALE_HOURS, DEFAULT_STALE_HOURS),
            )
        ] = _number(0.5, 48, 0.5, "h")
    return vol.Schema(fields)


def defaults_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_CHARGE_POWER,
                default=current.get(CONF_CHARGE_POWER, DEFAULT_CHARGE_POWER),
            ): _number(1.0, 50.0, 0.1, "kW"),
            vol.Required(
                CONF_BATTERY_CAPACITY,
                default=current.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY),
            ): _number(5.0, 200.0, 0.5, "kWh"),
            vol.Required(
                CONF_TARGET_SOC,
                default=current.get(CONF_TARGET_SOC, DEFAULT_TARGET_SOC),
            ): _number(10, 100, 5, "%"),
            vol.Required(
                CONF_DEADLINE_TIME,
                default=current.get(CONF_DEADLINE_TIME, DEFAULT_DEADLINE_TIME),
            ): selector.TimeSelector(),
        }
    )


class EvChargePlannerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Walk the user through price source, charger, car and defaults."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_PRICE_PRESET] == price_adapters.PRESET_GENERIC:
                return await self.async_step_price_keys()
            return await self.async_step_charger()
        return self.async_show_form(step_id="user", data_schema=price_schema({}))

    async def async_step_price_keys(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_charger()
        return self.async_show_form(
            step_id="price_keys", data_schema=generic_price_schema({})
        )

    async def async_step_charger(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_car()
        return self.async_show_form(step_id="charger", data_schema=charger_schema({}))

    async def async_step_car(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_CAR_PRESET] == car_adapters.PRESET_NONE:
                return await self.async_step_defaults()
            return await self.async_step_car_details()
        return self.async_show_form(step_id="car", data_schema=car_schema({}))

    async def async_step_car_details(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_defaults()
        return self.async_show_form(
            step_id="car_details",
            data_schema=car_details_schema({}, self._data[CONF_CAR_PRESET]),
        )

    async def async_step_defaults(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            await self.async_set_unique_id(self._data[CONF_CHARGER_SWITCH])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=TITLE, data={}, options=self._data)
        return self.async_show_form(step_id="defaults", data_schema=defaults_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return EvChargePlannerOptionsFlow()


class EvChargePlannerOptionsFlow(OptionsFlow):
    """The same four steps again, pre-filled with what is configured now."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.options, **self._data}

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_PRICE_PRESET] == price_adapters.PRESET_GENERIC:
                return await self.async_step_price_keys()
            return await self.async_step_charger()
        return self.async_show_form(
            step_id="init", data_schema=price_schema(self._current)
        )

    async def async_step_price_keys(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_charger()
        return self.async_show_form(
            step_id="price_keys", data_schema=generic_price_schema(self._current)
        )

    async def async_step_charger(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_car()
        return self.async_show_form(
            step_id="charger", data_schema=charger_schema(self._current)
        )

    async def async_step_car(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_CAR_PRESET] == car_adapters.PRESET_NONE:
                return await self.async_step_defaults()
            return await self.async_step_car_details()
        return self.async_show_form(
            step_id="car", data_schema=car_schema(self._current)
        )

    async def async_step_car_details(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_defaults()
        return self.async_show_form(
            step_id="car_details",
            data_schema=car_details_schema(
                self._current, self._current[CONF_CAR_PRESET]
            ),
        )

    async def async_step_defaults(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            merged = {**self.config_entry.options, **self._data}
            # Dropping the car clears its entities, so a later refresh cannot fire
            # against a stale entity id that no longer exists.
            if merged.get(CONF_CAR_PRESET) == car_adapters.PRESET_NONE:
                for key in (
                    CONF_CAR_SOC_ENTITY,
                    CONF_CAR_REFRESH_BUTTON,
                    CONF_CAR_LAST_FETCH_ENTITY,
                ):
                    merged.pop(key, None)
            return self.async_create_entry(title="", data=merged)
        return self.async_show_form(
            step_id="defaults", data_schema=defaults_schema(self._current)
        )
