"""Builds a standalone page per language so the card can be looked at without
Home Assistant.

    python tools/make_harness.py
    python -m http.server 8777 --directory .harness

Then open http://localhost:8777/harness-en.html. It serves over HTTP rather than
opening the file directly because the card is a custom element, and browsers
refuse to run scripts from a file:// page in some contexts.

The point of this is the languages. The card takes its words from Home
Assistant's language and its currency from Home Assistant's currency setting,
and neither is visible to someone developing in one locale. The Norwegian page
in particular is worth looking at: nothing is translated into Norwegian, so it
falls back to English while dates and money follow Norwegian convention, and
that combination is where layout breaks. It is how the table overflow was found.

The data is invented but shaped like a real day: quarter-hourly prices with a
dip around midday, a car at 51%, and a plan that sits in the dip.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARD = ROOT / "custom_components" / "ev_charge_planner" / "frontend" / "ev-charge-planner-card.js"
OUT = ROOT / ".harness"

#: language, and a currency that is not the developer's own
LOCALES = (("en", "GBP"), ("nl", "EUR"), ("nb", "NOK"))

START = dt.datetime(2026, 11, 9, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=1)))
SLOTS = 96
SLOT_MINUTES = 15
KW = 10.0


def build_prices() -> list[dict]:
    prices = []
    for i in range(SLOTS):
        t = START + dt.timedelta(minutes=SLOT_MINUTES * i)
        base = 0.42 + 0.12 * math.sin((i / SLOTS) * 2 * math.pi - 1.2)
        dip = -0.09 if 40 <= i <= 60 else 0.0
        prices.append({"start": t.isoformat(), "price": round(base + dip, 5)})
    return prices


def build_period(prices: list[dict], i0: int, i1: int) -> dict:
    kwh_per_slot = KW * (SLOT_MINUTES / 60)
    kwh = (i1 - i0) * kwh_per_slot
    cost = sum(p["price"] for p in prices[i0:i1]) * kwh_per_slot
    return {
        "start": (START + dt.timedelta(minutes=SLOT_MINUTES * i0)).isoformat(),
        "end": (START + dt.timedelta(minutes=SLOT_MINUTES * i1)).isoformat(),
        "slots": i1 - i0,
        "kwh": round(kwh, 2),
        "cost": round(cost, 2),
        "avg_price": round(cost / kwh, 4),
    }


def build_states() -> dict:
    prices = build_prices()
    periods = [
        build_period(prices, 42, 46),
        build_period(prices, 48, 54),
        build_period(prices, 56, 60),
    ]
    total_kwh = sum(p["kwh"] for p in periods)
    total_cost = sum(p["cost"] for p in periods)
    horizon = (START + dt.timedelta(minutes=SLOT_MINUTES * SLOTS)).isoformat()

    def st(state, attrs=None):
        return {"state": state, "attributes": attrs or {}}

    return {
        "sensor.evcp_prices_known_until": st(
            horizon, {"prices": prices, "slot_minutes": SLOT_MINUTES}
        ),
        "sensor.evcp_plan_cost": st(round(total_cost, 2), {"periods": periods}),
        "sensor.evcp_plan_energy": st(round(total_kwh, 1)),
        "sensor.evcp_plan_average_price": st(round(total_cost / total_kwh, 4)),
        "sensor.evcp_plan_periods": st("Mon 10:30-11:30"),
        "sensor.evcp_suggested_cost": st(round(total_cost, 2), {"periods": periods}),
        "sensor.evcp_suggested_periods": st("Mon 10:30-11:30"),
        "sensor.evcp_energy_needed": st(34.3),
        "sensor.evcp_car_charge_level": st(
            51, {"last_updated": "2026-11-08T07:14:00+01:00", "stale": True}
        ),
        "sensor.evcp_measured_charging_power": st(9.89),
        "binary_sensor.evcp_charge_now": st("off"),
        "number.evcp_charging_power": st(KW),
        "number.evcp_car_battery_capacity": st(71),
        "number.evcp_target_charge_level": st(100),
        "number.evcp_fixed_energy_to_add": st(0),
        "datetime.evcp_ready_by": st("2026-11-09T05:00:00+01:00"),
        "button.evcp_start_charging": st("unknown"),
        "button.evcp_stop": st("unknown"),
        "button.evcp_use_measured_charging_power": st("unknown"),
        "switch.evcp_charge_immediately": st("off"),
    }


PAGE = """<!doctype html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EV Charge Planner card &mdash; %(lang)s</title>
<style>
  :root {
    --primary-text-color: #e1e1e1;
    --secondary-text-color: #9b9b9b;
    --primary-color: #03a9f4;
    --accent-color: #ff9800;
    --error-color: #db4437;
    --card-background-color: #1c1c1c;
    --divider-color: #333;
    color-scheme: dark;
  }
  body {
    margin: 0; padding: 16px; background: #111; color: var(--primary-text-color);
    font-family: Roboto, system-ui, sans-serif;
  }
  .label { font: 12px monospace; color: #888; margin-bottom: 8px; }
  ha-card {
    display: block; max-width: 760px; padding: 16px; border-radius: 12px;
    background: var(--card-background-color);
  }
</style>
</head>
<body>
<div class="label">language=%(lang)s currency=%(currency)s</div>
<div id="host"></div>
<script>
%(card)s
</script>
<script>
  const hass = {
    states: %(states)s,
    locale: { language: "%(lang)s" },
    language: "%(lang)s",
    config: { currency: "%(currency)s" },
    callService: (domain, service) => console.log("callService", domain, service),
  };
  const el = document.createElement("ev-charge-planner-card");
  el.setConfig({});
  document.getElementById("host").appendChild(el);
  el.hass = hass;
</script>
</body>
</html>
"""


def main() -> None:
    card = CARD.read_text(encoding="utf-8")
    states = json.dumps(build_states())
    OUT.mkdir(exist_ok=True)
    for lang, currency in LOCALES:
        path = OUT / f"harness-{lang}.html"
        path.write_text(
            PAGE % {"lang": lang, "currency": currency, "card": card, "states": states},
            encoding="utf-8",
        )
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
