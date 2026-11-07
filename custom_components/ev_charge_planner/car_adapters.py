"""Optional coupling to a car integration for its state of charge.

The planner works without a car: you tell it how many kWh you want and it plans them.
Linking a car only replaces that number with one derived from its charge level.

Polling deserves care. Several car integrations wake the vehicle's modem to answer,
which drains the 12V battery, so some owners deliberately set a slow interval. This
module therefore never polls on a schedule. A refresh happens only when the dashboard
is opened, and only if the reading is genuinely old -- and the decision lives here, in
Python, rather than being trusted to the frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

PRESET_NONE = "none"
PRESET_TOYOTA = "toyota"
PRESET_ENTITY = "entity"

UNUSABLE_STATES = {"unknown", "unavailable", "none", "", None}


@dataclass(frozen=True)
class CarPreset:
    """What a preset knows about an integration's entity naming."""

    key: str
    label: str
    #: Whether this preset can ask the car for a fresh reading at all.
    supports_refresh: bool
    #: Substrings used to pre-select likely entities in the config flow. They are
    #: hints for the picker, never a hard requirement: the user can always override.
    soc_hints: tuple[str, ...] = ()
    refresh_hints: tuple[str, ...] = ()
    last_fetch_hints: tuple[str, ...] = ()


PRESETS: dict[str, CarPreset] = {
    PRESET_NONE: CarPreset(
        key=PRESET_NONE,
        label="No car linked (enter kWh yourself)",
        supports_refresh=False,
    ),
    PRESET_TOYOTA: CarPreset(
        key=PRESET_TOYOTA,
        label="Toyota",
        supports_refresh=True,
        soc_hints=("battery_level",),
        refresh_hints=("refresh_electric_realtime_status", "refresh_vehicle_status"),
        last_fetch_hints=("last_successful_fetch",),
    ),
    PRESET_ENTITY: CarPreset(
        key=PRESET_ENTITY,
        label="Other car (pick the charge level entity)",
        supports_refresh=False,
        soc_hints=("battery_level", "state_of_charge", "soc"),
    ),
}


def read_soc(raw: str | float | None) -> float | None:
    """Turn a reported charge level into a number, or None if it is not usable.

    Returning None rather than a guess matters: the planner treats None as "no idea"
    and proposes nothing, instead of confidently planning around a made-up figure.
    """
    if raw in UNUSABLE_STATES:
        return None
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not 0 <= value <= 100:
        return None
    return value


def parse_last_fetch(raw: str | datetime | None) -> datetime | None:
    """Read the 'last updated' timestamp a car integration exposes, if any."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else None
    if raw in UNUSABLE_STATES or not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip().replace(" ", "T", 1))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def is_stale(last_fetch: datetime | None, now: datetime, stale_hours: float) -> bool:
    """Whether the charge level is old enough to be worth a refresh.

    An unknown age counts as stale: if the integration will not say when it last
    heard from the car, one refresh on opening the page is the lesser evil.
    """
    if last_fetch is None:
        return True
    return (now - last_fetch) > timedelta(hours=stale_hours)


def may_refresh(
    last_attempt: datetime | None, now: datetime, min_interval_minutes: int
) -> bool:
    """Rate limit, enforced here so reloading the page ten times wakes the car once."""
    if last_attempt is None:
        return True
    return (now - last_attempt) >= timedelta(minutes=min_interval_minutes)


def should_refresh(
    *,
    preset: CarPreset,
    has_refresh_entity: bool,
    last_fetch: datetime | None,
    last_attempt: datetime | None,
    now: datetime,
    stale_hours: float,
    min_interval_minutes: int,
) -> bool:
    """The single decision point. Every condition must hold."""
    return (
        preset.supports_refresh
        and has_refresh_entity
        and is_stale(last_fetch, now, stale_hours)
        and may_refresh(last_attempt, now, min_interval_minutes)
    )


def suggest_entities(
    candidates: list[str], hints: tuple[str, ...]
) -> list[str]:
    """Order candidate entity ids so the likely ones surface first in the picker."""
    if not hints:
        return sorted(candidates)
    matching = [e for e in candidates if any(h in e for h in hints)]
    rest = [e for e in candidates if e not in matching]
    return sorted(matching) + sorted(rest)
