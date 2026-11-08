"""Pure planning logic for the Dynamic EV charge optimizer.

Deliberately free of Home Assistant imports: everything here is plain Python so it can
be exercised by unit tests in milliseconds. All the HA plumbing lives in
coordinator.py. This split exists because the Jinja version of this logic shipped
several bugs that a single test would have caught -- epoch integers compared against
timezone-aware datetimes, a template that silently kept its previous value, and a
sandbox rejection that masked the real failure for an hour.

Everything below works in timezone-aware datetimes. Naive input is rejected rather
than guessed at, because guessing is how the Jinja version went wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

#: Periods that finished longer ago than this are dropped from the schedule. The grace
#: matters: the control loop needs a chance to switch the charger off at the end of the
#: last period before the schedule empties out from under it.
PRUNE_GRACE = timedelta(minutes=10)

#: Used when the price list is too short to derive a cadence from.
DEFAULT_SLOT_MINUTES = 60


@dataclass(frozen=True)
class Slot:
    """One settlement period: when it starts and what a kWh costs during it."""

    start: datetime
    price: float


@dataclass(frozen=True)
class Period:
    """A contiguous block the charger should be on for."""

    start: datetime
    end: datetime
    slots: int
    kwh: float
    cost: float
    avg_price: float


@dataclass(frozen=True)
class SwitchPoint:
    """A moment the charger changes state. action is "on" or "off"."""

    at: datetime
    action: str


@dataclass(frozen=True)
class PlanPart:
    """A set of periods with its totals. Used for both the schedule and the proposal."""

    periods: tuple[Period, ...]
    switch_points: tuple[SwitchPoint, ...]
    cost: float
    kwh: float
    avg_price: float
    complete: bool


EMPTY_PART = PlanPart(
    periods=(), switch_points=(), cost=0.0, kwh=0.0, avg_price=0.0, complete=True
)


@dataclass(frozen=True)
class Plan:
    """Everything the UI and the control loop need, computed in one pass."""

    ok: bool
    reason: str | None
    slot_minutes: int
    kw: float
    kwh_per_slot: float
    horizon_start: datetime | None
    horizon_end: datetime | None
    deadline: datetime | None
    deadline_past: bool
    energy_needed: float
    charge_now: bool
    has_schedule: bool
    committed: PlanPart
    suggested: PlanPart
    #: The schedule with finished periods removed, for the caller to persist.
    pruned_schedule: tuple[tuple[datetime, datetime], ...]


def _require_aware(value: datetime, what: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{what} must be timezone-aware, got {value!r}")


def slot_minutes_of(slots: list[Slot]) -> int:
    """Derive the cadence from the data rather than assuming hourly.

    Dutch day-ahead prices moved to quarter-hour settlement, and assuming 60 minutes
    would quietly price every plan four times too high.
    """
    if len(slots) < 2:
        return DEFAULT_SLOT_MINUTES
    delta = (slots[1].start - slots[0].start).total_seconds() / 60
    return int(round(delta)) or DEFAULT_SLOT_MINUTES


def merge_ranges(
    ranges: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Sort and merge overlapping or touching ranges into a clean, ordered list."""
    out: list[tuple[datetime, datetime]] = []
    for start, end in sorted(ranges, key=lambda r: r[0]):
        if end <= start:
            continue
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _part_from_indexes(
    slots: list[Slot],
    indexes: list[int],
    kwh_per_slot: float,
    slot_len: timedelta,
    complete: bool,
) -> PlanPart:
    """Turn a set of slot indexes into merged periods with costs attached."""
    if not indexes:
        return EMPTY_PART

    runs: list[tuple[int, int]] = []
    start = prev = indexes[0]
    for i in indexes[1:]:
        if i != prev + 1:
            runs.append((start, prev))
            start = i
        prev = i
    runs.append((start, prev))

    periods: list[Period] = []
    switch_points: list[SwitchPoint] = []
    total_cost = 0.0
    for first, last in runs:
        count = last - first + 1
        cost = sum(slots[i].price for i in range(first, last + 1)) * kwh_per_slot
        kwh = count * kwh_per_slot
        period_start = slots[first].start
        period_end = slots[last].start + slot_len
        periods.append(
            Period(
                start=period_start,
                end=period_end,
                slots=count,
                kwh=round(kwh, 2),
                cost=round(cost, 2),
                avg_price=round(cost / kwh, 4) if kwh else 0.0,
            )
        )
        switch_points.append(SwitchPoint(at=period_start, action="on"))
        switch_points.append(SwitchPoint(at=period_end, action="off"))
        total_cost += cost

    total_kwh = len(indexes) * kwh_per_slot
    return PlanPart(
        periods=tuple(periods),
        switch_points=tuple(switch_points),
        cost=round(total_cost, 2),
        kwh=round(total_kwh, 2),
        avg_price=round(total_cost / total_kwh, 4) if total_kwh else 0.0,
        complete=complete,
    )


def cheapest_indexes(
    slots: list[Slot], now: datetime, deadline: datetime, wanted: int
) -> list[int]:
    """Pick the `wanted` cheapest slots between now and the deadline.

    Returned in time order. The result is deliberately allowed to be non-contiguous:
    skipping an expensive hour in the middle of the night is the entire point.
    """
    if wanted <= 0:
        return []
    candidates = [
        (slot.price, i)
        for i, slot in enumerate(slots)
        if slot.start >= now and slot.start < deadline
    ]
    # Sort by price, then by time so equal prices resolve to the earlier slot - which
    # keeps the result stable instead of reshuffling on every recompute.
    candidates.sort(key=lambda c: (c[0], c[1]))
    return sorted(i for _, i in candidates[:wanted])


def build_plan(
    slots: list[Slot],
    now: datetime,
    schedule: list[tuple[datetime, datetime]],
    *,
    kw: float,
    energy_needed: float,
    deadline: datetime | None = None,
) -> Plan:
    """Compute the whole plan in one pass.

    `schedule` is what the user has committed; `suggested` is what the planner would
    propose for `energy_needed` before the deadline. Both are costed against `slots`.
    """
    _require_aware(now, "now")
    if deadline is not None:
        _require_aware(deadline, "deadline")

    if len(slots) < 2:
        return Plan(
            ok=False,
            reason="not enough price data",
            slot_minutes=DEFAULT_SLOT_MINUTES,
            kw=kw,
            kwh_per_slot=0.0,
            horizon_start=None,
            horizon_end=None,
            deadline=deadline,
            deadline_past=bool(deadline and deadline <= now),
            energy_needed=max(0.0, energy_needed),
            charge_now=False,
            has_schedule=bool(schedule),
            committed=EMPTY_PART,
            suggested=EMPTY_PART,
            pruned_schedule=tuple(merge_ranges(list(schedule))),
        )

    slots = sorted(slots, key=lambda s: s.start)
    for slot in slots:
        _require_aware(slot.start, "slot start")

    minutes = slot_minutes_of(slots)
    slot_len = timedelta(minutes=minutes)
    kwh_per_slot = max(0.0, kw) * minutes / 60
    horizon_start = slots[0].start
    horizon_end = slots[-1].start + slot_len

    # Drop what is already over, so a schedule shows only what is still to come and
    # empties itself once it is done.
    kept = [r for r in merge_ranges(list(schedule)) if r[1] > now - PRUNE_GRACE]

    committed_idx = [
        i for i, slot in enumerate(slots) if any(s <= slot.start < e for s, e in kept)
    ]
    committed_complete = not kept or max(e for _, e in kept) <= horizon_end
    committed = _part_from_indexes(
        slots, committed_idx, kwh_per_slot, slot_len, committed_complete
    )

    effective_deadline = deadline or horizon_end
    deadline_past = effective_deadline <= now
    needed = max(0.0, energy_needed)
    if deadline_past or kwh_per_slot <= 0 or needed <= 0:
        suggested = EMPTY_PART
    else:
        wanted = math.ceil(needed / kwh_per_slot)
        chosen = cheapest_indexes(slots, now, effective_deadline, wanted)
        suggested = _part_from_indexes(
            slots, chosen, kwh_per_slot, slot_len, len(chosen) == wanted
        )

    charge_now = any(p.start <= now < p.end for p in committed.periods)

    return Plan(
        ok=True,
        reason=None,
        slot_minutes=minutes,
        kw=kw,
        kwh_per_slot=round(kwh_per_slot, 3),
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        deadline=effective_deadline,
        deadline_past=deadline_past,
        energy_needed=round(needed, 2),
        charge_now=charge_now,
        has_schedule=bool(kept),
        committed=committed,
        suggested=suggested,
        pruned_schedule=tuple(kept),
    )


def energy_needed_from_soc(
    current_soc: float | None,
    target_soc: float,
    capacity_kwh: float,
    override_kwh: float = 0.0,
) -> float:
    """kWh still to add. A positive override wins; otherwise derive it from the car.

    Returns 0.0 when there is no override and no usable reading, which leaves the
    proposal empty rather than inventing a number.
    """
    if override_kwh and override_kwh > 0:
        return round(override_kwh, 2)
    if current_soc is None:
        return 0.0
    return round(max(0.0, (target_soc - current_soc) / 100 * capacity_kwh), 2)


def charger_target(
    *, has_schedule: bool, charge_now: bool, override: bool
) -> bool | None:
    """What the charger should be doing, or None to leave it alone.

    Three answers, and the third is the important one. True and False are
    instructions; None means the planner has no opinion and must not touch the
    switch. That is what keeps charging by hand possible, and it is why this is a
    function rather than an if-statement buried in the coordinator.
    """
    if override:
        return True
    if not has_schedule:
        return None
    return charge_now
