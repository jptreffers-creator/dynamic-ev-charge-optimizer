"""Tests for reading prices out of a source integration's attribute."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import price_adapters  # noqa: E402

PRESET_ENTSOE = price_adapters.PRESET_ENTSOE
PRESET_ENERGYZERO = price_adapters.PRESET_ENERGYZERO
PRESET_EASYENERGY = price_adapters.PRESET_EASYENERGY
PRESETS = price_adapters.PRESETS
PriceReadError = price_adapters.PriceReadError
ActionSpec = price_adapters.ActionSpec
PriceShape = price_adapters.PriceShape
adjust = price_adapters.adjust
parse_timestamp = price_adapters.parse_timestamp
shape_from_config = price_adapters.shape_from_config
slots_from_attribute = price_adapters.slots_from_attribute
slots_from_response = price_adapters.slots_from_response

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
        from _support import const

        CONF_PRICE_ATTRIBUTE = const.CONF_PRICE_ATTRIBUTE
        CONF_PRICE_PRESET = const.CONF_PRICE_PRESET
        CONF_PRICE_TIME_KEY = const.CONF_PRICE_TIME_KEY
        CONF_PRICE_VALUE_KEY = const.CONF_PRICE_VALUE_KEY

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
        from _support import const

        CONF_PRICE_PRESET = const.CONF_PRICE_PRESET

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


# Shaped like the real answers. The EnergyZero one is taken from the serialiser in
# homeassistant/components/energyzero/services.py, which emits all four keys;
# easyEnergy emits only timestamp and price.
ENERGYZERO_RESPONSE = {
    "prices": [
        {
            "price": 0.17962,
            "timestamp": "2026-11-21 00:00:00+01:00",
            "start": "2026-11-21 00:00:00+01:00",
            "end": "2026-11-21 00:15:00+01:00",
        },
        {
            "price": 0.17104,
            "timestamp": "2026-11-21 00:15:00+01:00",
            "start": "2026-11-21 00:15:00+01:00",
            "end": "2026-11-21 00:30:00+01:00",
        },
        {
            "price": 0.16550,
            "timestamp": "2026-11-21 00:30:00+01:00",
            "start": "2026-11-21 00:30:00+01:00",
            "end": "2026-11-21 00:45:00+01:00",
        },
    ]
}

EASYENERGY_RESPONSE = {
    "prices": [
        {"timestamp": "2026-11-21 00:00:00+01:00", "price": 0.08418},
        {"timestamp": "2026-11-21 00:15:00+01:00", "price": 0.08201},
    ]
}


class TestActionResponses(unittest.TestCase):
    """Sources that answer an action instead of publishing an attribute."""

    def test_energyzero_reads_start_and_price(self):
        slots = slots_from_response(ENERGYZERO_RESPONSE, PRESETS[PRESET_ENERGYZERO])
        self.assertEqual(len(slots), 3)
        self.assertEqual(slots[0].start, datetime(2026, 11, 21, 0, 0, tzinfo=CET))
        self.assertAlmostEqual(slots[0].price, 0.17962)
        self.assertEqual(slots, sorted(slots, key=lambda s: s.start))

    def test_easyenergy_reads_timestamp(self):
        """It has no start key at all, so the timestamp one has to be right."""
        slots = slots_from_response(EASYENERGY_RESPONSE, PRESETS[PRESET_EASYENERGY])
        self.assertEqual(len(slots), 2)
        self.assertAlmostEqual(slots[1].price, 0.08201)

    def test_quarter_hour_cadence_survives(self):
        slots = slots_from_response(ENERGYZERO_RESPONSE, PRESETS[PRESET_ENERGYZERO])
        self.assertEqual(slots[1].start - slots[0].start, timedelta(minutes=15))

    def test_missing_key_says_what_was_there(self):
        """The message has to name the keys present, or diagnosing this is guesswork."""
        with self.assertRaises(PriceReadError) as caught:
            slots_from_response({"something_else": []}, PRESETS[PRESET_ENERGYZERO])
        self.assertIn("something_else", str(caught.exception))

    def test_no_response_data(self):
        with self.assertRaises(PriceReadError):
            slots_from_response(None, PRESETS[PRESET_ENERGYZERO])

    def test_attribute_source_cannot_read_a_response(self):
        with self.assertRaises(PriceReadError):
            slots_from_response(ENERGYZERO_RESPONSE, PRESETS[PRESET_ENTSOE])

    def test_per_mwh_source_is_scaled(self):
        """Nord Pool quotes per MWh; a source like that must come out per kWh."""
        shape = PriceShape(
            attribute="",
            time_key="start",
            value_key="price",
            label="per MWh",
            tested=False,
            action=ActionSpec(domain="x", service="y", scale=0.001),
        )
        response = {"prices": [{"start": "2026-11-21 00:00:00+01:00", "price": 179.62}]}
        slots = slots_from_response(response, shape)
        self.assertAlmostEqual(slots[0].price, 0.17962)

    def test_action_preset_ignores_generic_overrides(self):
        """A stale attribute override must not corrupt an action source."""
        from _support import price_adapters as pa

        shape = shape_from_config(
            {
                "price_preset": PRESET_ENERGYZERO,
                "price_attribute": "leftover",
                "price_time_key": "leftover",
            }
        )
        self.assertTrue(shape.is_action)
        self.assertEqual(shape.time_key, pa.PRESETS[PRESET_ENERGYZERO].time_key)


class TestAdjust(unittest.TestCase):
    """Market price in, what you actually pay out."""

    def slots(self):
        return slots_from_response(ENERGYZERO_RESPONSE, PRESETS[PRESET_ENERGYZERO])

    def test_dutch_bill_shape(self):
        """Jille's own ENTSO-e formula: (market + 0.01 + 0.111) * 1.21."""
        got = adjust(self.slots(), surcharge=0.121, vat_percent=21.0)
        self.assertAlmostEqual(got[0].price, (0.17962 + 0.121) * 1.21, places=6)

    def test_zero_is_a_no_op(self):
        original = self.slots()
        self.assertIs(adjust(original), original)

    def test_order_is_never_changed(self):
        """The transform is monotonic, so the cheapest period stays the cheapest."""
        original = self.slots()
        adjusted = adjust(original, surcharge=0.121, vat_percent=21.0)
        rank = lambda s: [i for i, _ in sorted(enumerate(s), key=lambda p: p[1].price)]
        self.assertEqual(rank(original), rank(adjusted))

    def test_surcharge_without_vat(self):
        got = adjust(self.slots(), surcharge=0.05)
        self.assertAlmostEqual(got[0].price, 0.17962 + 0.05, places=6)

    def test_vat_without_surcharge(self):
        got = adjust(self.slots(), vat_percent=21.0)
        self.assertAlmostEqual(got[0].price, 0.17962 * 1.21, places=6)

    def test_timestamps_are_untouched(self):
        original = self.slots()
        adjusted = adjust(original, surcharge=0.1, vat_percent=21.0)
        self.assertEqual([s.start for s in original], [s.start for s in adjusted])


if __name__ == "__main__":
    unittest.main()
