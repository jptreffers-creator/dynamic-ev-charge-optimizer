"""Reading future electricity prices out of whatever integration supplies them.

Every Dutch and Nordic price integration publishes the same thing -- a list of
upcoming settlement periods with a price each -- but every one of them picks
different attribute and key names. Rather than hard-wire one, the user picks a preset
in the config flow and this module turns the attribute into a list of Slot.

Only the ENTSO-e adapter has been exercised against a live instance. The others are
written from their documented attribute shapes and are marked as such in the README;
the generic adapter exists so anyone can point the planner at a source we got wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .planner import Slot

PRESET_ENTSOE = "entsoe"
PRESET_NORDPOOL = "nordpool"
PRESET_ENERGYZERO = "energyzero"
PRESET_GENERIC = "generic"


@dataclass(frozen=True)
class PriceShape:
    """Where to find the prices on the source entity, and what the keys are called."""

    attribute: str
    time_key: str
    value_key: str
    label: str
    tested: bool


PRESETS: dict[str, PriceShape] = {
    # Verified against a live instance: the `prices` attribute spans today 00:00
    # through tomorrow 23:45, with "time" as a space-separated local timestamp.
    PRESET_ENTSOE: PriceShape(
        attribute="prices",
        time_key="time",
        value_key="price",
        label="ENTSO-e",
        tested=True,
    ),
    PRESET_NORDPOOL: PriceShape(
        attribute="raw_today",
        time_key="start",
        value_key="value",
        label="Nord Pool",
        tested=False,
    ),
    PRESET_ENERGYZERO: PriceShape(
        attribute="prices",
        time_key="time",
        value_key="price",
        label="EnergyZero",
        tested=False,
    ),
    PRESET_GENERIC: PriceShape(
        attribute="prices",
        time_key="time",
        value_key="price",
        label="Other (name the attribute yourself)",
        tested=False,
    ),
}


class PriceReadError(Exception):
    """The source entity did not yield usable prices."""


def parse_timestamp(value: Any) -> datetime:
    """Accept the several spellings integrations use for a moment in time.

    Seen in the wild: "2026-11-07 00:00:00+01:00" (ENTSO-e, space separated),
    full ISO-8601 with a T, and epoch numbers. Anything without a timezone is
    rejected -- guessing a zone is how the template version lost an hour.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        raise PriceReadError(
            "price timestamps given as epoch numbers carry no timezone; "
            "use an integration that publishes offsets"
        )
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace(" ", "T", 1))
        except ValueError as err:
            raise PriceReadError(f"cannot read timestamp {value!r}") from err
    else:
        raise PriceReadError(f"cannot read timestamp {value!r}")

    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise PriceReadError(f"timestamp {value!r} has no timezone")
    return parsed


def slots_from_attribute(raw: Any, shape: PriceShape) -> list[Slot]:
    """Turn the raw attribute value into sorted, de-duplicated slots."""
    if not isinstance(raw, (list, tuple)):
        raise PriceReadError(
            f"attribute {shape.attribute!r} is not a list of prices"
        )

    seen: dict[datetime, float] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if shape.time_key not in entry or shape.value_key not in entry:
            continue
        try:
            start = parse_timestamp(entry[shape.time_key])
            price = float(entry[shape.value_key])
        except (PriceReadError, TypeError, ValueError):
            continue
        # Later entries win, which is what you want when a source republishes a
        # corrected price for a period it already sent.
        seen[start] = price

    if not seen:
        raise PriceReadError(
            f"no usable entries in {shape.attribute!r} using keys "
            f"{shape.time_key!r}/{shape.value_key!r}"
        )
    return [Slot(start=start, price=price) for start, price in sorted(seen.items())]


def shape_from_config(config: dict[str, Any]) -> PriceShape:
    """Build the shape from a config entry, honouring generic overrides."""
    from .const import (
        CONF_PRICE_ATTRIBUTE,
        CONF_PRICE_PRESET,
        CONF_PRICE_TIME_KEY,
        CONF_PRICE_VALUE_KEY,
    )

    preset = config.get(CONF_PRICE_PRESET, PRESET_ENTSOE)
    base = PRESETS.get(preset, PRESETS[PRESET_GENERIC])
    return PriceShape(
        attribute=config.get(CONF_PRICE_ATTRIBUTE) or base.attribute,
        time_key=config.get(CONF_PRICE_TIME_KEY) or base.time_key,
        value_key=config.get(CONF_PRICE_VALUE_KEY) or base.value_key,
        label=base.label,
        tested=base.tested,
    )
