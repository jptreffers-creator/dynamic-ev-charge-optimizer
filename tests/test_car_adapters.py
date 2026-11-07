"""Tests for the optional car coupling, especially the refusal to poll."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.ev_charge_planner.car_adapters import (  # noqa: E402
    PRESET_ENTITY,
    PRESET_NONE,
    PRESET_TOYOTA,
    PRESETS,
    is_stale,
    may_refresh,
    parse_last_fetch,
    read_soc,
    should_refresh,
    suggest_entities,
)

CET = timezone(timedelta(hours=1))
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=CET)


class TestReadSoc(unittest.TestCase):
    def test_reads_numbers_and_numeric_strings(self):
        self.assertEqual(read_soc("17"), 17.0)
        self.assertEqual(read_soc(42), 42.0)
        self.assertEqual(read_soc("17.5"), 17.5)

    def test_unusable_states_give_none(self):
        for raw in ("unknown", "unavailable", "", None, "none"):
            self.assertIsNone(read_soc(raw), raw)

    def test_nonsense_gives_none_rather_than_a_guess(self):
        self.assertIsNone(read_soc("half full"))

    def test_out_of_range_is_rejected(self):
        """A percentage outside 0-100 means the entity is not what we think."""
        self.assertIsNone(read_soc(-5))
        self.assertIsNone(read_soc(140))

    def test_boundaries_are_allowed(self):
        self.assertEqual(read_soc(0), 0.0)
        self.assertEqual(read_soc(100), 100.0)


class TestLastFetch(unittest.TestCase):
    def test_reads_an_iso_timestamp(self):
        got = parse_last_fetch("2026-11-07T10:00:00+01:00")
        self.assertEqual(got, datetime(2026, 11, 7, 10, 0, tzinfo=CET))

    def test_naive_is_refused(self):
        self.assertIsNone(parse_last_fetch("2026-11-07T10:00:00"))

    def test_unusable_states_give_none(self):
        self.assertIsNone(parse_last_fetch("unknown"))
        self.assertIsNone(parse_last_fetch(None))


class TestStaleness(unittest.TestCase):
    def test_recent_reading_is_fresh(self):
        self.assertFalse(is_stale(NOW - timedelta(minutes=30), NOW, 2))

    def test_old_reading_is_stale(self):
        self.assertTrue(is_stale(NOW - timedelta(hours=3), NOW, 2))

    def test_unknown_age_counts_as_stale(self):
        self.assertTrue(is_stale(None, NOW, 2))


class TestRateLimit(unittest.TestCase):
    def test_first_attempt_is_allowed(self):
        self.assertTrue(may_refresh(None, NOW, 15))

    def test_too_soon_is_refused(self):
        self.assertFalse(may_refresh(NOW - timedelta(minutes=5), NOW, 15))

    def test_exactly_at_the_interval_is_allowed(self):
        self.assertTrue(may_refresh(NOW - timedelta(minutes=15), NOW, 15))


class TestShouldRefresh(unittest.TestCase):
    """Every condition must hold; this is the only place that decides to wake a car."""

    def base(self, **over):
        args = dict(
            preset=PRESETS[PRESET_TOYOTA],
            has_refresh_entity=True,
            last_fetch=NOW - timedelta(hours=5),
            last_attempt=None,
            now=NOW,
            stale_hours=2,
            min_interval_minutes=15,
        )
        args.update(over)
        return should_refresh(**args)

    def test_stale_and_allowed_refreshes(self):
        self.assertTrue(self.base())

    def test_fresh_reading_does_not_refresh(self):
        self.assertFalse(self.base(last_fetch=NOW - timedelta(minutes=10)))

    def test_rate_limit_blocks_a_reload_storm(self):
        """Ten dashboard reloads in a minute must wake the car at most once."""
        self.assertFalse(self.base(last_attempt=NOW - timedelta(minutes=1)))

    def test_preset_without_refresh_never_polls(self):
        self.assertFalse(self.base(preset=PRESETS[PRESET_ENTITY]))

    def test_no_car_linked_never_polls(self):
        self.assertFalse(self.base(preset=PRESETS[PRESET_NONE]))

    def test_missing_refresh_entity_never_polls(self):
        self.assertFalse(self.base(has_refresh_entity=False))


class TestEntitySuggestions(unittest.TestCase):
    def test_hinted_entities_come_first(self):
        candidates = [
            "sensor.car_odometer",
            "sensor.car_battery_level",
            "sensor.car_range",
        ]
        ordered = suggest_entities(candidates, ("battery_level",))
        self.assertEqual(ordered[0], "sensor.car_battery_level")
        self.assertEqual(len(ordered), 3)

    def test_without_hints_it_just_sorts(self):
        self.assertEqual(suggest_entities(["b", "a"], ()), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
