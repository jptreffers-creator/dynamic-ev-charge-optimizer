# Dynamic EV Charge Optimizer

<img src="custom_components/dynamic_ev_charge_optimizer/brand/icon.png" width="96" align="right" alt="">

Charge your car in the cheapest settlement periods of the next 48 hours.

You say how much energy you want and by when. The planner reads your dynamic
electricity prices, picks the cheapest periods before your deadline, and switches your
charger on and off at those moments. The periods do not have to be contiguous — it
will happily charge from 02:45 to 03:00, pause through an expensive quarter, and pick
up again at 03:30, because that is where the money is.

![The planner card: a day of quarter-hourly prices with the booked periods marked, the car's charge level, and what the plan will cost](docs/card.png)

That is a real day: seven separate periods between 09:30 and 15:15, skipping the
expensive quarters in between, 35 kWh for EUR 14.00 at an average of EUR 0.4001/kWh.

## What you need

Two things, and only the first is required.

**A price entity that publishes future prices.** Not just the current price — the
planner needs the upcoming periods in an attribute. In practice that means one of the
integrations below, or anything else that works the same way.

**An entity that turns charging on and off.** Usually a `switch` from your charger's
integration. The planner never talks to your charger directly: it flips that entity,
and your charger's own integration does the rest. That is why it works with a Peblar,
an Easee, a Wallbox, a go-e, a smart plug, or a relay behind a contactor — anything
that appears in Home Assistant as something switchable.

Optionally, a power sensor and a session-energy sensor from the charger. They are used
only to measure your real charging speed, which you can then adopt with one button.

And optionally a car integration, so the planner can work out how much energy is still
needed from the actual charge level instead of you typing a number.

## Price sources

Price integrations publish the upcoming day in one of two ways, and this reads both.
Some put the whole list in a sensor attribute. The ones built into Home Assistant do
not: their sensors carry only the current price and the day's extremes, and the full
list comes from an action that returns it. An adapter that could only read attributes
would be unable to use any of them.

| Source | Kind | Status |
|---|---|---|
| ENTSO-e (HACS) | Attribute | Verified against a live instance |
| EnergyZero (built in) | Action | Built from the action's source, not yet seen live |
| easyEnergy (built in) | Action | Built from the action's source, not yet seen live |
| Nord Pool (HACS) | Attribute | Written from its documented shape, untested |
| Anything else | Attribute | Use **Other** and name the attribute and keys yourself |

For an action source, pick which configuration of that integration to ask; it is
called at most once every fifteen minutes, because day-ahead prices change twice a
day. Install that integration first — the setup refuses with an explanation rather
than showing you an empty picker.

Note that the built-in Nord Pool integration is *not* the one listed above. It keeps
its prices behind an action whose response is keyed by bidding area, which does not
fit this shape yet; the preset is for the older HACS integration that publishes
`raw_today`.

If your source is not listed, pick **Other**. You will be asked for the name of the
attribute holding the price list, and the keys inside each entry. Look them up under
*Developer tools → States*, select your price sensor, and read its attributes. If you
get it working for a source not listed here, an issue with the three names is enough
for it to become a preset.

### Taxes and surcharges

Market prices are not what you pay. Two settings turn one into the other:

    what you pay = (market price + surcharge) × (1 + VAT / 100)

**Surcharge per kWh** covers energy tax and your supplier's margin; **VAT** is a
percentage. Both default to zero, so a source that already quotes all-in prices needs
neither touched. Neither can change *which* periods are cheapest — the transform is
monotonic, so the plan is identical either way. They only make the euros on the card
match the bill.

### If your price source goes quiet

It happens. The ENTSO-e Transparency Platform went down three times in one month
during development. When a source stops answering, the planner keeps the prices and
the schedule it already had rather than erasing them, and **Laad nu** charges
regardless of price. If one source is unreliable where you live, switching to another
is a matter of reopening the setup.

## Installing

### Through HACS

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/jptreffers-creator/dynamic-ev-charge-optimizer`, category **Integration**
3. Install **Dynamic EV Charge Optimizer**, then restart Home Assistant
4. Settings → Devices & services → **Add integration** → *Dynamic EV Charge Optimizer*

### By hand

Copy `custom_components/dynamic_ev_charge_optimizer` into your `config/custom_components/`
directory and restart Home Assistant.

The card comes with the integration and registers itself. There is nothing to add
under Dashboards → Resources.

## Setting it up

Four steps, all with entity pickers:

1. **Electricity prices** — your price integration and the sensor carrying the
   upcoming prices. For most sources that is the "average price" sensor rather than
   the "current price" one, because that is where the whole day lives.
2. **Charger** — the switch that starts and stops charging. The two sensors are
   optional.
3. **Car** — optional. Choose *No car linked* and you simply enter kWh yourself.
4. **Defaults** — charging power, battery capacity, target level, and the time you
   normally want the car ready.

All of it can be changed afterwards under the integration's **Configure** button.

## Using it

Add the card to any dashboard:

```yaml
type: custom:dynamic-ev-charge-optimizer-card
```

No options needed; it finds its own entities. If you run more than one planner, give
each card a `prefix:` matching its entity names.

### A whole dashboard, without typing entity ids

*Settings → Dashboards → Add dashboard*, then **EV charge planner** under *Community
dashboards*. That builds a three-view dashboard — the planner, the details, the
settings — from whatever you have configured, in your own language, and it leaves out
what does not apply: no car linked means no car rows.

Nothing in it is typed by hand. The planner's own entities are named identically on
every installation, so they are derived from one predictable name; your charger, car
and price integration are read from `sensor.*_wiring`, a diagnostic entity that
reports what this planner is pointed at. That is also the first place to look when
something is not working.

This needs Home Assistant 2026.5 or newer, which is when dashboard strategies
arrived. On anything older, copy [docs/example-dashboard.yaml](docs/example-dashboard.yaml)
and replace the handful of lines marked `REPLACE` with your own entities.

If **EV charge planner** is not in that dialog, reload the page with Ctrl+Shift+R
first. The dialog only sees strategies whose module is registered as a Lovelace
*resource*, and this integration registers its own on startup — but if that failed,
the log says so. You can then add it by hand under *Settings → Dashboards →
Resources* (that menu needs Advanced Mode on your profile), as a **JavaScript
module** pointing at:

    /dynamic_ev_charge_optimizer/dynamic-ev-charge-optimizer-card.js

Being loaded as an extra frontend module, which is how the card itself gets in, is
enough to render the card but not enough for the dialog to find the strategy. That
is not written down anywhere; it was found the hard way.

Then: set how full you want the car, or a fixed number of kWh, set when it should be
ready, and press **Schema laden**. The planner books the cheapest periods and charges
there. **Stop** clears the schedule and switches off.

**With no schedule, the planner does not touch your charger at all.** That is
deliberate — it means you can always charge by hand without the planner fighting you
for the switch.

### Charging now, whatever the price

**Laad nu** ignores the schedule and the prices and switches the charger on straight
away. Use it when you need the car charged more than you need it charged cheaply.

It stays on until you turn it off. It does not expire by itself, and that is a choice
rather than an omission: the obvious expiry would be "stop at the target charge level",
but the car is polled rarely by design, so during a session that figure barely moves
and the override would outlive its own promise. One rule that holds beats a clever one
that does not. While it is on, the card says so.

Turning it off is not the same as stopping. Off hands the decision back to the
schedule, which may well want to carry on charging; **Stop** clears the schedule and
switches off.

It is also a switch, `switch.*_charge_immediately`, so an automation or a voice command
can flip it.

## Language and currency

The card speaks English by default and Dutch where Home Assistant is set to Dutch.
Any other language falls back to English rather than showing blanks, while dates,
times and numbers still follow that language's own conventions.

Amounts use the currency from Home Assistant's own setting (*Settings -> System ->
General*), not a hard-coded euro sign, so a Nord Pool user sees kroner.

Adding a language means adding one block to `STRINGS` at the top of
`custom_components/dynamic_ev_charge_optimizer/frontend/dynamic-ev-charge-optimizer-card.js`. Entries
are plain strings or small functions, so word order stays yours. A partial
translation is fine: anything you leave out comes through in English. To see the
result without a Home Assistant to hand, `python tools/make_harness.py` writes a
standalone page per language.

## About polling your car

Several car integrations wake the vehicle to answer, which drains its 12V battery.
Owners often set a slow poll interval on purpose, and an integration that quietly
polls more often undoes that choice.

So this one never polls on a timer. A refresh is requested **only when the planner
card is opened**, and even then only if the reading is older than the threshold you
set, and never twice within fifteen minutes. All of those conditions are enforced in
the integration, not in the card, so reloading your dashboard twenty times still wakes
the car at most once.

If you would rather it never asked at all, leave the refresh button empty during
setup.

## Calibrating the charging speed

The planner reserves periods based on the charging power you configured. If that
number is wrong, so is every cost estimate.

While charging, the integration measures what your charger actually delivers and
averages it over recent sessions, publishing it as *Measured charging power*. Press
**Use measured charging power** to adopt it. On a nominal 11 kW charger, 9.9 kW is a
perfectly normal real-world figure.

## What it does not do

- **On and off only.** It does not modulate current, so no "charge at 10 A instead
  of 16". If your charger exposes only a current limit and no on/off entity, this
  integration cannot drive it.
- **No load balancing** against the rest of the house.
- **No solar surplus following.**
- **No control of a home battery.** If you want your house battery to stop discharging
  while the car charges, write a small automation that reacts to the same charging
  switch. That keeps the two concerns apart and works regardless of which battery you
  have.

## Entities

| Entity | What it is |
|---|---|
| `sensor.*_plan_periods` | The scheduled periods, as readable text |
| `sensor.*_plan_cost` / `_plan_energy` | What the schedule costs and delivers |
| `sensor.*_suggested_periods` / `_suggested_cost` | What pressing Start would book |
| `sensor.*_energy_needed` | kWh still to add |
| `sensor.*_car_charge_level` | The car's level, with its age as an attribute |
| `sensor.*_measured_charging_power` | Measured over recent sessions |
| `sensor.*_prices_known_until` | End of the priced horizon |
| `binary_sensor.*_charge_now` | Whether now falls inside a scheduled period |
| `binary_sensor.*_plan_fully_priced` | Off when the plan runs past the priced horizon |
| `switch.*_charge_immediately` | Charge now, ignoring schedule and prices |
| `number.*` | Charging power, battery capacity, target level, fixed kWh |
| `datetime.*_ready_by` | The deadline |
| `button.*` | Start charging, Stop, adopt measured power, refresh car |

Services mirror the buttons: `dynamic_ev_charge_optimizer.apply_suggestion`, `.stop`,
`.refresh_car` and `.adopt_measured_power`. With more than one planner configured,
pass `entry_id`.

## Troubleshooting

**No proposal.** Check that something is actually needed — if the car is already above
the target, there is nothing to plan. Check the deadline is in the future. Check
*Prices known until*: tomorrow's prices usually appear in the early afternoon, so a
deadline past that horizon has fewer periods to choose from.

**The card says "Custom element doesn't exist".** Reload with Ctrl+Shift+R. The card
is served by the integration with its version in the URL, so an upgrade normally
retires the cached copy by itself.

**Prices unavailable.** The planner keeps its last good plan rather than blanking, but
it cannot price anything new. Look at your price integration first.

## Licence

MIT. See [LICENSE](LICENSE).
