"""Constants and configuration keys for the EV charge planner."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ev_charge_planner"

# How often the plan is recomputed. One minute, not five: the switch points sit on
# settlement boundaries, and a five-minute grid made the charger start and stop up to
# five minutes late -- losing the cheap front of a period and taking the expensive
# front of the next.
UPDATE_INTERVAL_SECONDS: Final = 60

# --- configuration keys -------------------------------------------------------

CONF_PRICE_PRESET: Final = "price_preset"
CONF_PRICE_ENTITY: Final = "price_entity"
CONF_PRICE_ATTRIBUTE: Final = "price_attribute"
CONF_PRICE_TIME_KEY: Final = "price_time_key"
CONF_PRICE_VALUE_KEY: Final = "price_value_key"

CONF_CHARGER_SWITCH: Final = "charger_switch"
CONF_CHARGER_POWER_SENSOR: Final = "charger_power_sensor"
CONF_SESSION_ENERGY_SENSOR: Final = "session_energy_sensor"

CONF_CAR_PRESET: Final = "car_preset"
CONF_CAR_SOC_ENTITY: Final = "car_soc_entity"
CONF_CAR_REFRESH_BUTTON: Final = "car_refresh_button"
CONF_CAR_LAST_FETCH_ENTITY: Final = "car_last_fetch_entity"
CONF_CAR_STALE_HOURS: Final = "car_stale_hours"

CONF_BATTERY_CAPACITY: Final = "battery_capacity_kwh"
CONF_CHARGE_POWER: Final = "charge_power_kw"
CONF_TARGET_SOC: Final = "target_soc"
CONF_DEADLINE_TIME: Final = "deadline_time"

# --- defaults -----------------------------------------------------------------

DEFAULT_BATTERY_CAPACITY: Final = 60.0
DEFAULT_CHARGE_POWER: Final = 11.0
DEFAULT_TARGET_SOC: Final = 80.0
DEFAULT_DEADLINE_TIME: Final = "07:00:00"
DEFAULT_STALE_HOURS: Final = 2.0

# Refusing to poll the car more often than this is enforced in Python rather than
# trusted to the frontend. Some cars keep their modem awake to answer, which drains
# the 12V battery; a user who reloads the dashboard ten times must not cause ten
# wake-ups.
MIN_CAR_REFRESH_INTERVAL_MINUTES: Final = 15

# A charging session has to be at least this substantial before it is allowed to
# influence the measured charge power, so a brief plug-in does not skew the average.
MIN_SESSION_MINUTES: Final = 10
MIN_SESSION_KWH: Final = 1.0
MEASURED_POWER_WINDOW: Final = 5  # number of recent sessions averaged

# --- storage ------------------------------------------------------------------

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.schedule"

# --- services -----------------------------------------------------------------

SERVICE_APPLY_SUGGESTION: Final = "apply_suggestion"
SERVICE_STOP: Final = "stop"
SERVICE_REFRESH_CAR: Final = "refresh_car"
SERVICE_ADOPT_MEASURED_POWER: Final = "adopt_measured_power"
