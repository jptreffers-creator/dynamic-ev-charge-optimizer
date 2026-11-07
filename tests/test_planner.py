"""Tests for the pure planning logic.

Plain unittest so they run with `python -m unittest` on a bare interpreter; they are
also valid pytest tests. Several cases here exist because the earlier Jinja
implementation got them wrong in production.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import planner  # noqa: E402

PRUNE_GRACE = planner.PRUNE_GRACE
Slot = planner.Slot
build_plan = planner.build_plan
charger_target = planner.charger_target
cheapest_indexes = planner.cheapest_indexes
energy_needed_from_soc = planner.energy_needed_from_soc
merge_ranges = planner.merge_ranges
slot_minutes_of = planner.slot_minutes_of

CET = timezone(timedelta(hours=1))
MIDNIGHT = datetime(2026, 10, 29, 0, 0, tzinfo=CET)


def quarter_slots(prices: list[float], start: datetime = MIDNIGHT) -> list[Slot]:
    """Quarter-hourly slots, the shape ENTSO-e actually delivers for NL."""
    return [
        Slot(start=start + timedelta(minutes=15 * i), price=p)
        for i, p in enumerate(prices)
    ]


def hourly_slots(prices: list[float], start: datetime = MIDNIGHT) -> list[Slot]:
    return [
        Slot(start=start + timedelta(hours=i), price=p) for i, p in enumerate(prices)
    ]


class TestCadence(unittest.TestCase):
    def test_quarter_hour_detected(self):
        self.assertEqual(slot_minutes_of(quarter_slots([0.4] * 8)), 15)

    def test_hourly_detected(self):
        self.assertEqual(slot_minutes_of(hourly_slots([0.4] * 8)), 60)

    def test_too_few_slots_falls_back(self):
        self.assertEqual(slot_minutes_of([]), 60)

    def test_energy_per_slot_follows_cadence(self):
        """11 kW over a quarter of an hour is 2.75 kWh, not 11."""
        plan = build_plan(
            quarter_slots([0.4] * 8), MIDNIGHT, [], kw=11, energy_needed=0
        )
        self.assertEqual(plan.slot_minutes, 15)
        self.assertAlmostEqual(plan.kwh_per_slot, 2.75)

        hourly = build_plan(hourly_slots([0.4] * 8), MIDNIGHT, [], kw=11, energy_needed=0)
        self.assertAlmostEqual(hourly.kwh_per_slot, 11.0)


class TestMergeRanges(unittest.TestCase):
    def test_sorts_and_merges_touching(self):
        a = (MIDNIGHT, MIDNIGHT + timedelta(hours=1))
        b = (MIDNIGHT + timedelta(hours=1), MIDNIGHT + timedelta(hours=2))
        self.assertEqual(merge_ranges([b, a]), [(a[0], b[1])])

    def test_merges_overlapping(self):
        a = (MIDNIGHT, MIDNIGHT + timedelta(hours=2))
        b = (MIDNIGHT + timedelta(hours=1), MIDNIGHT + timedelta(hours=3))
        self.assertEqual(merge_ranges([a, b]), [(a[0], b[1])])

    def test_keeps_separate_ranges_apart(self):
        a = (MIDNIGHT, MIDNIGHT + timedelta(hours=1))
        b = (MIDNIGHT + timedelta(hours=2), MIDNIGHT + timedelta(hours=3))
        self.assertEqual(merge_ranges([a, b]), [a, b])

    def test_drops_empty_ranges(self):
        self.assertEqual(merge_ranges([(MIDNIGHT, MIDNIGHT)]), [])


class TestCommittedSchedule(unittest.TestCase):
    def test_single_period_is_costed(self):
        slots = quarter_slots([0.40, 0.50, 0.60, 0.70])
        window = (MIDNIGHT, MIDNIGHT + timedelta(minutes=30))
        plan = build_plan(slots, MIDNIGHT, [window], kw=11, energy_needed=0)

        self.assertEqual(len(plan.committed.periods), 1)
        period = plan.committed.periods[0]
        self.assertEqual(period.slots, 2)
        self.assertAlmostEqual(period.kwh, 5.5)
        # (0.40 + 0.50) * 2.75
        self.assertAlmostEqual(period.cost, 2.48, places=2)

    def test_touching_windows_become_one_period(self):
        slots = quarter_slots([0.4] * 8)
        windows = [
            (MIDNIGHT + timedelta(minutes=30), MIDNIGHT + timedelta(minutes=45)),
            (MIDNIGHT, MIDNIGHT + timedelta(minutes=30)),
        ]
        plan = build_plan(slots, MIDNIGHT, windows, kw=11, energy_needed=0)
        self.assertEqual(len(plan.committed.periods), 1)
        self.assertEqual(plan.committed.periods[0].slots, 3)

    def test_gap_keeps_two_periods_and_four_switch_points(self):
        slots = quarter_slots([0.4] * 8)
        windows = [
            (MIDNIGHT, MIDNIGHT + timedelta(minutes=15)),
            (MIDNIGHT + timedelta(minutes=45), MIDNIGHT + timedelta(minutes=60)),
        ]
        plan = build_plan(slots, MIDNIGHT, windows, kw=11, energy_needed=0)
        self.assertEqual(len(plan.committed.periods), 2)
        self.assertEqual(
            [sp.action for sp in plan.committed.switch_points],
            ["on", "off", "on", "off"],
        )

    def test_charge_now_only_inside_a_period(self):
        slots = quarter_slots([0.4] * 8)
        window = (MIDNIGHT + timedelta(minutes=30), MIDNIGHT + timedelta(minutes=60))
        inside = build_plan(
            slots, MIDNIGHT + timedelta(minutes=35), [window], kw=11, energy_needed=0
        )
        outside = build_plan(
            slots, MIDNIGHT + timedelta(minutes=20), [window], kw=11, energy_needed=0
        )
        self.assertTrue(inside.charge_now)
        self.assertFalse(outside.charge_now)

    def test_schedule_past_the_horizon_is_incomplete(self):
        slots = quarter_slots([0.4] * 4)  # horizon ends at 01:00
        window = (MIDNIGHT, MIDNIGHT + timedelta(hours=3))
        plan = build_plan(slots, MIDNIGHT, [window], kw=11, energy_needed=0)
        self.assertFalse(plan.committed.complete)

    def test_has_schedule_drives_hands_off(self):
        """With nothing scheduled the caller must leave the charger alone."""
        slots = quarter_slots([0.4] * 8)
        self.assertFalse(build_plan(slots, MIDNIGHT, [], kw=11, energy_needed=0).has_schedule)


class TestPruning(unittest.TestCase):
    def test_finished_period_is_dropped_after_the_grace(self):
        slots = quarter_slots([0.4] * 8)
        window = (MIDNIGHT, MIDNIGHT + timedelta(minutes=15))
        now = MIDNIGHT + timedelta(minutes=15) + PRUNE_GRACE + timedelta(minutes=1)
        plan = build_plan(slots, now, [window], kw=11, energy_needed=0)
        self.assertEqual(plan.pruned_schedule, ())
        self.assertFalse(plan.has_schedule)

    def test_just_finished_period_survives_the_grace(self):
        """Without this window the control loop would never switch the charger off."""
        slots = quarter_slots([0.4] * 8)
        window = (MIDNIGHT, MIDNIGHT + timedelta(minutes=15))
        now = MIDNIGHT + timedelta(minutes=16)
        plan = build_plan(slots, now, [window], kw=11, energy_needed=0)
        self.assertEqual(len(plan.pruned_schedule), 1)
        self.assertTrue(plan.has_schedule)
        self.assertFalse(plan.charge_now)


class TestSuggestion(unittest.TestCase):
    def test_picks_the_cheapest_slots(self):
        slots = quarter_slots([0.90, 0.10, 0.80, 0.20])
        idx = cheapest_indexes(slots, MIDNIGHT, MIDNIGHT + timedelta(hours=1), 2)
        self.assertEqual(idx, [1, 3])

    def test_result_is_in_time_order(self):
        slots = quarter_slots([0.50, 0.10, 0.30, 0.20])
        self.assertEqual(
            cheapest_indexes(slots, MIDNIGHT, MIDNIGHT + timedelta(hours=1), 3),
            [1, 2, 3],
        )

    def test_skips_an_expensive_middle(self):
        """The proposal is allowed to be non-contiguous; that is the whole point."""
        slots = quarter_slots([0.10, 0.90, 0.90, 0.10])
        plan = build_plan(
            slots,
            MIDNIGHT,
            [],
            kw=11,
            energy_needed=5.5,  # two slots
            deadline=MIDNIGHT + timedelta(hours=1),
        )
        self.assertEqual(len(plan.suggested.periods), 2)
        self.assertEqual(plan.suggested.periods[0].start, MIDNIGHT)
        self.assertEqual(
            plan.suggested.periods[1].start, MIDNIGHT + timedelta(minutes=45)
        )

    def test_slot_count_rounds_up(self):
        """10.24 kWh at 2.75 per slot needs four slots, not three and a bit."""
        slots = quarter_slots([0.4] * 16)
        plan = build_plan(
            slots,
            MIDNIGHT,
            [],
            kw=11,
            energy_needed=10.24,
            deadline=MIDNIGHT + timedelta(hours=4),
        )
        self.assertEqual(sum(p.slots for p in plan.suggested.periods), 4)
        self.assertAlmostEqual(plan.suggested.kwh, 11.0)

    def test_never_proposes_slots_in_the_past(self):
        slots = quarter_slots([0.10, 0.10, 0.90, 0.90])
        now = MIDNIGHT + timedelta(minutes=30)
        plan = build_plan(
            slots,
            now,
            [],
            kw=11,
            energy_needed=2.75,
            deadline=MIDNIGHT + timedelta(hours=1),
        )
        self.assertTrue(all(p.start >= now for p in plan.suggested.periods))

    def test_deadline_in_the_past_yields_nothing(self):
        slots = quarter_slots([0.4] * 8)
        plan = build_plan(
            slots,
            MIDNIGHT + timedelta(hours=1),
            [],
            kw=11,
            energy_needed=11,
            deadline=MIDNIGHT,
        )
        self.assertTrue(plan.deadline_past)
        self.assertEqual(plan.suggested.periods, ())

    def test_not_enough_cheap_slots_is_marked_incomplete(self):
        slots = quarter_slots([0.4] * 2)
        plan = build_plan(
            slots,
            MIDNIGHT,
            [],
            kw=11,
            energy_needed=100,
            deadline=MIDNIGHT + timedelta(hours=5),
        )
        self.assertFalse(plan.suggested.complete)

    def test_zero_demand_proposes_nothing(self):
        slots = quarter_slots([0.4] * 8)
        plan = build_plan(slots, MIDNIGHT, [], kw=11, energy_needed=0)
        self.assertEqual(plan.suggested.periods, ())


class TestDegradedInput(unittest.TestCase):
    def test_no_prices_is_reported_not_crashed(self):
        plan = build_plan([], MIDNIGHT, [], kw=11, energy_needed=10)
        self.assertFalse(plan.ok)
        self.assertFalse(plan.charge_now)

    def test_naive_datetimes_are_rejected(self):
        """The Jinja version compared epochs with aware datetimes and lost an hour."""
        with self.assertRaises(ValueError):
            build_plan(
                quarter_slots([0.4] * 4),
                datetime(2026, 10, 29, 0, 0),
                [],
                kw=11,
                energy_needed=0,
            )

    def test_zero_power_proposes_nothing_without_dividing_by_zero(self):
        slots = quarter_slots([0.4] * 8)
        plan = build_plan(
            slots, MIDNIGHT, [], kw=0, energy_needed=10,
            deadline=MIDNIGHT + timedelta(hours=2),
        )
        self.assertEqual(plan.suggested.periods, ())


class TestEnergyNeeded(unittest.TestCase):
    def test_derived_from_state_of_charge(self):
        self.assertAlmostEqual(energy_needed_from_soc(17, 80, 64), 40.32)

    def test_override_wins(self):
        self.assertAlmostEqual(energy_needed_from_soc(17, 80, 64, override_kwh=25), 25.0)

    def test_unknown_charge_level_yields_zero(self):
        self.assertEqual(energy_needed_from_soc(None, 80, 64), 0.0)

    def test_already_above_target_needs_nothing(self):
        self.assertEqual(energy_needed_from_soc(90, 80, 64), 0.0)


class TestChargerTarget(unittest.TestCase):
    """Who gets to hold the switch, and when nobody does."""

    def test_no_schedule_means_hands_off(self):
        # Not False. False would switch the charger off, which would make charging
        # by hand impossible — the bug this None exists to prevent.
        self.assertIsNone(
            charger_target(has_schedule=False, charge_now=False, override=False)
        )

    def test_scheduled_and_inside_a_period(self):
        self.assertIs(
            charger_target(has_schedule=True, charge_now=True, override=False), True
        )

    def test_scheduled_but_between_periods(self):
        self.assertIs(
            charger_target(has_schedule=True, charge_now=False, override=False), False
        )

    def test_override_wins_over_an_empty_schedule(self):
        self.assertIs(
            charger_target(has_schedule=False, charge_now=False, override=True), True
        )

    def test_override_wins_over_a_schedule_that_says_off(self):
        # The whole point: the schedule has reserved cheap periods and we are not in
        # one, and the override charges anyway.
        self.assertIs(
            charger_target(has_schedule=True, charge_now=False, override=True), True
        )


if __name__ == "__main__":
    unittest.main()
