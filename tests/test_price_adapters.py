"""Tests for reading prices out of a source integration's attribute."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.ev_charge_planner.price_adapters import (  # noqa: E402
    PRESET_ENTSOE,
    PRESETS,
    PriceReadError,
    parse_timestamp,
    shape_from_config,
    slots_from_attribute,
)

SNAPSHOT = Path(__file__).with_name("live_snapshot.json")
CET = timezone(timedelta(hours=1))


class TestTimestamps(unittest.TestCase):
    def test_space_separated_with_offset(self):
        """The spelling ENTSO-e actually publishes."""
        got = parse_timestamp("2026-11-07 00:00:00+01:00")
        self.assertEqual(got, datetime(2026, 11, 7, 0, 0, tzinfo=CET))

    def test_iso_with_t(self):
        got = parse_timestamp("2026-11-07T00:00:00+01:00")
        self.assertEqual(got, datetime(2026, 11, 7, 0, 0, tzinfo=CET))

    def test_datetime_passes_through(self):
        when = datetime(2026, 11, 7, tzinfo=CET)
        self.assertEqual(parse_timestamp(when), when)

    def test_naive_is_rejected(self):
        with self.assertRaises(PriceReadError):
            parse_timestamp("2026-11-07 00:00:00")

    def test_epoch_is_rejected_with_a_reason(self):
        with self.assertRaises(PriceReadError) as ctx:
            parse_timestamp(1794042900)
        self.assertIn("timezone", str(ctx.exception))

    def test_nonsense_is_rejected(self):
        with self.assertRaises(PriceReadError):
            parse_timestamp("tomorrow-ish")


class TestSlotsFromAttribute(unittest.TestCase):
    shape = PRESETS[PRESET_ENTSOE]

    def test_reads_and_sorts(self):
        raw = [
            {"time": "2026-11-07 01:00:00+01:00", "price": 0.5},
            {"time": "2026-11-07 00:00:00+01:00", "price": 0.4},
        ]
        slots = slots_from_attribute(raw, self.shape)
        self.assertEqual([s.price for s in slots], [0.4, 0.5])

    def test_skips_unusable_entries_without_failing(self):
        raw = [
            {"time": "2026-11-07 00:00:00+01:00", "price": 0.4},
            {"time": "broken", "price": 0.9},
            {"price": 0.9},
            "not a dict",
            {"time": "2026-11-07 01:00:00+01:00", "price": "0.6"},
        ]
        slots = slots_from_attribute(raw, self.shape)
        self.assertEqual(len(slots), 2)
        self.assertAlmostEqual(slots[1].price, 0.6)

    def test_later_duplicate_wins(self):
        """A corrected price for a period already sent should replace it."""
        raw = [
            {"time": "2026-11-07 00:00:00+01:00", "price": 0.4},
            {"time": "2026-11-07 00:00:00+01:00", "price": 0.7},
        ]
        slots = slots_from_attribute(raw, self.shape)
        self.assertEqual(len(slots), 1)
        self.assertAlmostEqual(slots[0].price, 0.7)

    def test_empty_attribute_is_an_error(self):
        with self.assertRaises(PriceReadError):
            slots_from_attribute([], self.shape)

    def test_wrong_type_is_an_error(self):
        with self.assertRaises(PriceReadError):
            slots_from_attribute({"prices": []}, self.shape)

    def test_wrong_keys_name_the_keys_in_the_message(self):
        raw = [{"start": "2026-11-07 00:00:00+01:00", "value": 0.4}]
        with self.assertRaises(PriceReadError) as ctx:
            slots_from_attribute(raw, self.shape)
        self.assertIn("time", str(ctx.exception))


class TestGenericOverrides(unittest.TestCase):
    def test_generic_keys_are_honoured(self):
        from custom_components.ev_charge_planner.const import (
            CONF_PRICE_ATTRIBUTE,
            CONF_PRICE_PRESET,
            CONF_PRICE_TIME_KEY,
            CONF_PRICE_VALUE_KEY,
        )

        shape = shape_from_config(
            {
                CONF_PRICE_PRESET: "generic",
                CONF_PRICE_ATTRIBUTE: "raw_tomorrow",
                CONF_PRICE_TIME_KEY: "start",
                CONF_PRICE_VALUE_KEY: "value",
            }
        )
        raw = [{"start": "2026-11-07 00:00:00+01:00", "value": 0.33}]
        slots = slots_from_attribute(raw, shape)
        self.assertAlmostEqual(slots[0].price, 0.33)

    def test_preset_defaults_fill_the_gaps(self):
        from custom_components.ev_charge_planner.const import CONF_PRICE_PRESET

        shape = shape_from_config({CONF_PRICE_PRESET: PRESET_ENTSOE})
        self.assertEqual(shape.attribute, "prices")
        self.assertTrue(shape.tested)


@unittest.skipUnless(SNAPSHOT.exists(), "no live snapshot available")
class TestAgainstRealEntsoeData(unittest.TestCase):
    """Parse the attribute exactly as a live ENTSO-e instance published it."""

    def test_real_attribute_parses(self):
        raw = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["prices"]
        slots = slots_from_attribute(raw, PRESETS[PRESET_ENTSOE])

        self.assertEqual(len(slots), len(raw))
        self.assertEqual(slots[1].start - slots[0].start, timedelta(minutes=15))
        self.assertTrue(all(s.start.tzinfo is not None for s in slots))
        self.assertEqual(slots, sorted(slots, key=lambda s: s.start))


if __name__ == "__main__":
    unittest.main()
