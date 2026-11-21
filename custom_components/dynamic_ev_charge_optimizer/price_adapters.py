"""Reading future electricity prices out of whatever integration supplies them.

Every price integration publishes the same thing -- a list of upcoming settlement
periods with a price each -- but they disagree about almost everything else, and
in two ways rather than one.

Some publish the list as an attribute on a sensor. ENTSO-e does this, and it is
the easy case: read the attribute, map two key names, done.

The integrations built into Home Assistant do not. Nord Pool, EnergyZero,
easyEnergy and Zonneplan all keep their sensors to the current price, the next
price and the day's extremes; the full list is only available by calling an
action that returns response data. An adapter that can only read attributes
therefore cannot use any of them, which is why this module knows about both.

Only the ENTSO-e adapter has been exercised against a live instance. The action
specs are taken from the action implementations in Home Assistant core rather
than from documentation, which is a step better than guessing but still not the
same as having seen one answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .planner import Slot

PRESET_ENTSOE = "entsoe"
PRESET_ENERGYZERO = "energyzero"
PRESET_EASYENERGY = "easyenergy"
PRESET_NORDPOOL_HACS = "nordpool_hacs"
PRESET_GENERIC = "generic"


@dataclass(frozen=True)
class ActionSpec:
    """An action to call, and how to read what comes back.

    `data` holds the parameters that never change. The config entry to act on and
    the time window are filled in at call time, because only the coordinator knows
    them.
    """

    domain: str
    service: str
    data: dict[str, Any] = field(default_factory=dict)
    #: Key in the response holding the list of periods.
    response_key: str = "prices"
    #: Name of the parameter taking the config entry id of the source integration.
    entry_param: str = "config_entry"
    #: Names of the start and end parameters, or None when the action takes neither.
    start_param: str | None = "start"
    end_param: str | None = "end"
    #: Multiplied into every price. Sources quoting per MWh need 0.001.
    scale: float = 1.0


@dataclass(frozen=True)
class PriceShape:
    """Where the prices live, and what the keys are called."""

    attribute: str
    time_key: str
    value_key: str
    label: str
    tested: bool
    #: Set when the source answers an action instead of publishing an attribute.
    action: ActionSpec | None = None

    @property
    def is_action(self) -> bool:
        return self.action is not None


PRESETS: dict[str, PriceShape] = {
    # Verified against a live instance: the `prices` attribute spans today 00:00
    # through tomorrow 23:45, with "time" as a space-separated local timestamp.
    PRESET_ENTSOE: PriceShape(
        attribute="prices",
        time_key="time",
        value_key="price",
        label="ENTSO-e (HACS)",
        tested=True,
    ),
    # Core integration. Its action serialises each period as
    # {"price": .., "timestamp": .., "start": .., "end": ..}; `start` is used
    # because `timestamp` is documented as a duplicate of it and could drift.
    # Taken from homeassistant/components/energyzero/services.py.
    PRESET_ENERGYZERO: PriceShape(
        attribute="",
        time_key="start",
        value_key="price",
        label="EnergyZero (built in)",
        tested=False,
        action=ActionSpec(
            domain="energyzero",
            service="get_energy_prices",
            data={"incl_vat": False, "price_type": "market", "interval": "quarter"},
        ),
    ),
    # Core integration. Its action answers {"prices": [{"timestamp": .., "price": ..}]}
    # with no start/end, so the period length is derived from the cadence as usual.
    PRESET_EASYENERGY: PriceShape(
        attribute="",
        time_key="timestamp",
        value_key="price",
        label="easyEnergy (built in)",
        tested=False,
        action=ActionSpec(
            domain="easyenergy",
            service="get_energy_usage_prices",
            data={"incl_vat": False, "granularity": "quarter", "price_type": "market"},
        ),
    ),
    # The custom integration, not the one built into Home Assistant: this is the
    # one that publishes raw_today. The built-in Nord Pool keeps its list behind
    # an action whose response is keyed by bidding area, which does not fit the
    # shape below and is not supported yet.
    PRESET_NORDPOOL_HACS: PriceShape(
        attribute="raw_today",
        time_key="start",
        value_key="value",
        label="Nord Pool (HACS custom integration)",
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
    """The source did not yield usable prices."""


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


def slots_from_entries(raw: Any, shape: PriceShape, *, where: str) -> list[Slot]:
    """Turn a list of period dicts into sorted, de-duplicated slots.

    Shared by both kinds of source, because once the list is in hand an attribute
    and an action answer look identical.
    """
    if not isinstance(raw, (list, tuple)):
        raise PriceReadError(f"{where} is not a list of prices")

    scale = shape.action.scale if shape.action else 1.0
    seen: dict[datetime, float] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if shape.time_key not in entry or shape.value_key not in entry:
            continue
        try:
            start = parse_timestamp(entry[shape.time_key])
            price = float(entry[shape.value_key]) * scale
        except (PriceReadError, TypeError, ValueError):
            continue
        # Later entries win, which is what you want when a source republishes a
        # corrected price for a period it already sent.
        seen[start] = price

    if not seen:
        raise PriceReadError(
            f"no usable entries in {where} using keys "
            f"{shape.time_key!r}/{shape.value_key!r}"
        )
    return [Slot(start=start, price=price) for start, price in sorted(seen.items())]


def slots_from_attribute(raw: Any, shape: PriceShape) -> list[Slot]:
    """Read the list out of a sensor attribute."""
    return slots_from_entries(raw, shape, where=f"attribute {shape.attribute!r}")


def slots_from_response(response: Any, shape: PriceShape) -> list[Slot]:
    """Read the list out of an action's response data."""
    if shape.action is None:
        raise PriceReadError("this source does not answer an action")
    if not isinstance(response, dict):
        raise PriceReadError("the action returned no response data")
    key = shape.action.response_key
    if key not in response:
        raise PriceReadError(
            f"the action's response has no {key!r} key "
            f"(it has {sorted(response)!r})"
        )
    return slots_from_entries(response[key], shape, where=f"response key {key!r}")


def adjust(slots: list[Slot], *, surcharge: float = 0.0, vat_percent: float = 0.0) -> list[Slot]:
    """Turn market prices into what you actually pay.

    `(market + surcharge) * (1 + vat/100)`, which is the order every Dutch supplier
    bills in: energy tax and the supplier's own margin are added per kWh first, and
    VAT applies to the total. Both default to zero, so a source that already quotes
    all-in prices passes through untouched.

    It cannot change which periods are cheapest -- the transform is monotonic -- so
    the plan is the same either way. It only makes the euros on the card match the
    bill.
    """
    if not surcharge and not vat_percent:
        return slots
    factor = 1.0 + (vat_percent / 100.0)
    return [
        Slot(start=slot.start, price=(slot.price + surcharge) * factor)
        for slot in slots
    ]


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
    # The overrides exist for the generic preset; an action source has no
    # attribute to override, so its keys are left alone.
    if base.is_action:
        return base
    return PriceShape(
        attribute=config.get(CONF_PRICE_ATTRIBUTE) or base.attribute,
        time_key=config.get(CONF_PRICE_TIME_KEY) or base.time_key,
        value_key=config.get(CONF_PRICE_VALUE_KEY) or base.value_key,
        label=base.label,
        tested=base.tested,
    )
