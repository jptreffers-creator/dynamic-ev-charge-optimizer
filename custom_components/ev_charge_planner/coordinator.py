"""The engine: reads prices, computes the plan, drives the charger.

One object does all of it once a minute, and every entity reads from the result. The
alternative -- each of a dozen sensors doing its own lookup -- costs the same work a
dozen times over and lets entities disagree with each other across a boundary.

Side effects live here too, deliberately. In the YAML version the computing and the
switching sat in separate places that each woke on their own schedule, and the race
between them made the charger start up to five minutes late. Here the plan is
computed and acted on in the same pass.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

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
    CONF_PRICE_ENTITY,
    CONF_SESSION_ENERGY_SENSOR,
    CONF_TARGET_SOC,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_CHARGE_POWER,
    DEFAULT_DEADLINE_TIME,
    DEFAULT_STALE_HOURS,
    DEFAULT_TARGET_SOC,
    DOMAIN,
    MEASURED_POWER_WINDOW,
    MIN_CAR_REFRESH_INTERVAL_MINUTES,
    MIN_SESSION_KWH,
    MIN_SESSION_MINUTES,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_INTERVAL_SECONDS,
)
from .planner import Plan, build_plan, energy_needed_from_soc

_LOGGER = logging.getLogger(__name__)

UNUSABLE = {"unknown", "unavailable", None}


def _as_float(state: State | None) -> float | None:
    if state is None or state.state in UNUSABLE:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


class EvChargePlannerCoordinator(DataUpdateCoordinator[Plan]):
    """Computes the plan and keeps the charger in step with it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self.schedule: list[tuple[datetime, datetime]] = []
        #: Last parsed price list, kept so the card can draw the graph from whatever
        #: source was configured instead of knowing about ENTSO-e specifically.
        self.slots: list = []
        self.settings: dict[str, Any] = {}
        self.measured_sessions: list[float] = []
        self.last_car_refresh: datetime | None = None
        self.price_error: str | None = None
        self._session_started: datetime | None = None
        self._session_start_energy: float | None = None
        self._session_kwh: float = 0.0
        self._last_sample: datetime | None = None
        self._charger_was_on: bool = False

    # --- persistence ----------------------------------------------------------

    async def async_load(self) -> None:
        """Restore the schedule and settings, seeding from the config on first run."""
        stored = await self._store.async_load() or {}
        options = self.entry.options

        self.settings = {
            CONF_CHARGE_POWER: DEFAULT_CHARGE_POWER,
            CONF_BATTERY_CAPACITY: DEFAULT_BATTERY_CAPACITY,
            CONF_TARGET_SOC: DEFAULT_TARGET_SOC,
            "energy_override": 0.0,
            "deadline": None,
        }
        for key in (CONF_CHARGE_POWER, CONF_BATTERY_CAPACITY, CONF_TARGET_SOC):
            if key in options:
                self.settings[key] = float(options[key])
        self.settings.update(stored.get("settings") or {})

        self.schedule = []
        for start, end in stored.get("schedule") or []:
            parsed_start = dt_util.parse_datetime(start)
            parsed_end = dt_util.parse_datetime(end)
            if parsed_start and parsed_end:
                self.schedule.append((parsed_start, parsed_end))

        self.measured_sessions = [float(v) for v in stored.get("measured_sessions") or []]
        last = stored.get("last_car_refresh")
        self.last_car_refresh = dt_util.parse_datetime(last) if last else None

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "schedule": [[s.isoformat(), e.isoformat()] for s, e in self.schedule],
                "settings": self.settings,
                "measured_sessions": self.measured_sessions,
                "last_car_refresh": self.last_car_refresh.isoformat()
                if self.last_car_refresh
                else None,
            }
        )

    # --- inputs ---------------------------------------------------------------

    def _state(self, key: str) -> State | None:
        entity_id = self.entry.options.get(key)
        return self.hass.states.get(entity_id) if entity_id else None

    def _read_slots(self) -> list:
        entity = self._state(CONF_PRICE_ENTITY)
        if entity is None:
            self.price_error = "price sensor not found"
            return []
        shape = price_adapters.shape_from_config(dict(self.entry.options))
        try:
            slots = price_adapters.slots_from_attribute(
                entity.attributes.get(shape.attribute), shape
            )
        except price_adapters.PriceReadError as err:
            self.price_error = str(err)
            return []
        self.price_error = None
        return slots

    @property
    def car_soc(self) -> float | None:
        return car_adapters.read_soc(
            state.state if (state := self._state(CONF_CAR_SOC_ENTITY)) else None
        )

    @property
    def energy_needed(self) -> float:
        return energy_needed_from_soc(
            self.car_soc,
            float(self.settings[CONF_TARGET_SOC]),
            float(self.settings[CONF_BATTERY_CAPACITY]),
            float(self.settings.get("energy_override") or 0.0),
        )

    def effective_deadline(self, now: datetime) -> datetime:
        """The stored moment, or the next occurrence of the configured time.

        Falling back rather than returning something in the past is what keeps the
        proposal working the next morning without anyone editing a date.
        """
        stored = self.settings.get("deadline")
        parsed = dt_util.parse_datetime(stored) if stored else None
        if parsed and parsed > now:
            return parsed

        raw = self.entry.options.get(CONF_DEADLINE_TIME, DEFAULT_DEADLINE_TIME)
        parsed_time = dt_util.parse_time(raw) or time(7, 0)
        candidate = datetime.combine(now.date(), parsed_time, tzinfo=now.tzinfo)
        if candidate <= now:
            candidate = datetime.combine(
                now.date() + timedelta(days=1), parsed_time, tzinfo=now.tzinfo
            )
        return candidate

    # --- the pass -------------------------------------------------------------

    async def _async_update_data(self) -> Plan:
        now = dt_util.now()
        slots = self._read_slots()
        self.slots = slots

        plan = build_plan(
            slots,
            now,
            self.schedule,
            kw=float(self.settings[CONF_CHARGE_POWER]),
            energy_needed=self.energy_needed,
            deadline=self.effective_deadline(now),
        )

        if list(plan.pruned_schedule) != self.schedule:
            self.schedule = list(plan.pruned_schedule)
            await self._async_save()

        self._track_session(now)
        await self._apply_to_charger(plan)
        return plan

    async def _apply_to_charger(self, plan: Plan) -> None:
        """Hands off entirely when nothing is scheduled.

        That is what makes charging by hand possible: with an empty schedule the
        planner never touches the switch, so it cannot fight the person holding it.
        """
        if not plan.has_schedule:
            return
        switch = self.entry.options.get(CONF_CHARGER_SWITCH)
        state = self.hass.states.get(switch) if switch else None
        if state is None or state.state in UNUSABLE:
            return

        wanted = "on" if plan.charge_now else "off"
        if state.state == wanted:
            return
        # homeassistant.turn_on/off dispatches to whatever domain the entity is in,
        # so a charger exposed as something other than a switch still works.
        await self.hass.services.async_call(
            "homeassistant",
            f"turn_{wanted}",
            {"entity_id": switch},
            blocking=False,
        )

    # --- measured charging speed ---------------------------------------------

    def _track_session(self, now: datetime) -> None:
        """Follow one charging session so the real speed can be measured."""
        switch = self._state(CONF_CHARGER_SWITCH)
        is_on = switch is not None and switch.state == "on"
        session_energy = _as_float(self._state(CONF_SESSION_ENERGY_SENSOR))
        power_w = _as_float(self._state(CONF_CHARGER_POWER_SENSOR))

        if is_on and not self._charger_was_on:
            self._session_started = now
            self._session_start_energy = session_energy
            self._session_kwh = 0.0
            self._last_sample = now
        elif is_on:
            if session_energy is None and power_w is not None and self._last_sample:
                hours = (now - self._last_sample).total_seconds() / 3600
                self._session_kwh += power_w / 1000 * hours
            self._last_sample = now
        elif self._charger_was_on and self._session_started:
            self._finish_session(now, session_energy)

        self._charger_was_on = is_on

    def _finish_session(self, now: datetime, session_energy: float | None) -> None:
        minutes = (now - self._session_started).total_seconds() / 60
        if session_energy is not None and self._session_start_energy is not None:
            kwh = session_energy - self._session_start_energy
        else:
            kwh = self._session_kwh

        self._session_started = None
        self._session_start_energy = None
        self._session_kwh = 0.0

        # Short or tiny sessions say more about plugging in than about charging speed.
        if minutes < MIN_SESSION_MINUTES or kwh < MIN_SESSION_KWH:
            return
        self.measured_sessions.append(round(kwh / (minutes / 60), 2))
        del self.measured_sessions[:-MEASURED_POWER_WINDOW]
        self.hass.async_create_task(self._async_save())

    @property
    def measured_power(self) -> float | None:
        if not self.measured_sessions:
            return None
        return round(sum(self.measured_sessions) / len(self.measured_sessions), 2)

    # --- actions --------------------------------------------------------------

    async def async_apply_suggestion(self) -> None:
        """Commit the proposal as the schedule. This is the "Start charging" button."""
        plan = self.data
        if plan is None or not plan.suggested.periods:
            _LOGGER.warning("No suggestion to apply; check demand and deadline")
            return
        self.schedule = [(p.start, p.end) for p in plan.suggested.periods]
        await self._async_save()
        await self.async_refresh()

    async def async_stop(self) -> None:
        """Clear the schedule and switch off, in that order.

        Order matters: clearing first means the control pass sees no schedule and
        keeps its hands off, so nothing turns the charger back on behind us.
        """
        self.schedule = []
        await self._async_save()
        switch = self.entry.options.get(CONF_CHARGER_SWITCH)
        if switch:
            await self.hass.services.async_call(
                "homeassistant", "turn_off", {"entity_id": switch}, blocking=False
            )
        await self.async_refresh()

    async def async_set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        await self._async_save()
        await self.async_refresh()

    async def async_adopt_measured_power(self) -> None:
        if (measured := self.measured_power) is not None:
            await self.async_set_setting(CONF_CHARGE_POWER, measured)

    async def async_refresh_car(self) -> bool:
        """Ask the car for a fresh reading, if and only if that is warranted.

        Every guard is checked here rather than in the frontend, so reloading a
        dashboard repeatedly cannot turn into repeated wake-ups of the vehicle.
        """
        preset_key = self.entry.options.get(CONF_CAR_PRESET, car_adapters.PRESET_NONE)
        preset = car_adapters.PRESETS.get(preset_key, car_adapters.PRESETS[car_adapters.PRESET_NONE])
        button = self.entry.options.get(CONF_CAR_REFRESH_BUTTON)
        last_fetch = car_adapters.parse_last_fetch(
            state.state if (state := self._state(CONF_CAR_LAST_FETCH_ENTITY)) else None
        )
        now = dt_util.now()

        if not car_adapters.should_refresh(
            preset=preset,
            has_refresh_entity=bool(button),
            last_fetch=last_fetch,
            last_attempt=self.last_car_refresh,
            now=now,
            stale_hours=float(
                self.entry.options.get(CONF_CAR_STALE_HOURS, DEFAULT_STALE_HOURS)
            ),
            min_interval_minutes=MIN_CAR_REFRESH_INTERVAL_MINUTES,
        ):
            return False

        self.last_car_refresh = now
        await self._async_save()
        await self.hass.services.async_call(
            "button", "press", {"entity_id": button}, blocking=False
        )
        _LOGGER.debug("Asked the car for a fresh charge level")
        return True
