"""Compare the Python planner against the live Jinja implementation.

Not a unit test: it reads a snapshot taken from the running Home Assistant instance
(inputs and outputs together, so they are consistent with each other) and checks that
the port produces the same periods. Run it whenever the planner changes, as long as
the YAML package is still live.

    python tests/compare_with_live.py tests/live_snapshot.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.ev_charge_planner.planner import Slot, build_plan  # noqa: E402


def fmt(periods) -> list[tuple[str, str, int]]:
    return [(p.start.strftime("%H:%M"), p.end.strftime("%H:%M"), p.slots) for p in periods]


def fmt_live(periods) -> list[tuple[str, str, int]]:
    return [(p["start"][11:16], p["end"][11:16], p["slots"]) for p in periods]


def main(path: str) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    live = data["plan"]
    slots = [
        Slot(start=datetime.fromisoformat(p["time"]), price=float(p["price"]))
        for p in data["prices"]
    ]
    tz = slots[0].start.tzinfo

    deadline = datetime.fromtimestamp(data["deadline_ts"], tz=timezone.utc).astimezone(tz)
    schedule = []
    for part in (data["periods_raw"] or "").split(","):
        if "-" not in part:
            continue
        a, b = part.split("-")
        schedule.append(
            (
                datetime.fromtimestamp(int(a), tz=timezone.utc).astimezone(tz),
                datetime.fromtimestamp(int(b), tz=timezone.utc).astimezone(tz),
            )
        )

    print(f"slots        : {len(slots)} x {(slots[1].start - slots[0].start)}")
    print(f"kw / needed  : {live['kw']} kW / {live['energy_needed']} kWh")
    print(f"deadline     : {deadline:%Y-%m-%d %H:%M}")
    print(f"schedule     : " + ", ".join(f"{s:%H:%M}-{e:%H:%M}" for s, e in schedule))
    print()

    live_sug = fmt_live(live["suggested"]["periods"])
    live_com = fmt_live(live["manual"]["periods"])

    # The snapshot does not record the exact moment the template ran, so try the
    # window of plausible values: any of them must reproduce the live result.
    failures = 0
    matched_now = None
    for minute in range(0, 60, 5):
        now = slots[0].start.replace(hour=11, minute=minute)
        plan = build_plan(
            slots,
            now,
            schedule,
            kw=live["kw"],
            energy_needed=live["energy_needed"],
            deadline=deadline,
        )
        if fmt(plan.suggested.periods) == live_sug and matched_now is None:
            matched_now = now
    if matched_now is None:
        print("GEEN ENKEL moment reproduceert het live voorstel")
        failures += 1
        matched_now = slots[0].start.replace(hour=11, minute=40)

    plan = build_plan(
        slots,
        matched_now,
        schedule,
        kw=live["kw"],
        energy_needed=live["energy_needed"],
        deadline=deadline,
    )
    print(f"gereproduceerd met now = {matched_now:%H:%M}")
    print()

    checks = [
        ("voorstel periodes", fmt(plan.suggested.periods), live_sug),
        ("voorstel kosten", plan.suggested.cost, live["suggested"]["cost"]),
        ("voorstel kwh", plan.suggested.kwh, live["suggested"]["kwh"]),
        ("voorstel compleet", plan.suggested.complete, live["suggested"]["complete"]),
        ("schema periodes", fmt(plan.committed.periods), live_com),
        ("schema kosten", plan.committed.cost, live["manual"]["cost"]),
        ("schema kwh", plan.committed.kwh, live["manual"]["kwh"]),
        ("charge_now", plan.charge_now, live["charge_now"]),
        ("slot_minutes", plan.slot_minutes, live["slot_minutes"]),
        ("kwh_per_slot", plan.kwh_per_slot, live["kwh_per_slot"]),
    ]
    width = max(len(name) for name, _, _ in checks)
    for name, mine, theirs in checks:
        same = mine == theirs
        failures += 0 if same else 1
        mark = "ok " if same else "FOUT"
        print(f"{mark} {name:<{width}}  python={mine!r}")
        if not same:
            print(f"     {'':<{width}}  jinja ={theirs!r}")

    print()
    print("ALLES GELIJK" if failures == 0 else f"{failures} verschil(len)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "tests/live_snapshot.json"))
