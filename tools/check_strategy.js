/*
 * Smoke test for the dashboard strategy.
 *
 *     node tools/check_strategy.js
 *
 * The strategy generates a whole dashboard from whatever happens to exist in a
 * given Home Assistant, which is exactly the kind of thing that works on the
 * machine it was written on and nowhere else. This runs generate() against three
 * invented installations -- a complete one, one with no car and no charger
 * sensors, and one where the integration is missing -- and checks the result,
 * most importantly that every entity it puts on a card actually exists.
 *
 * It needs no browser: the file is loaded with the few globals it touches stubbed
 * out.
 */

const fs = require("fs");
const path = require("path");
const assert = require("assert");

const CARD = path.join(
  __dirname,
  "..",
  "custom_components",
  "dynamic_ev_charge_optimizer",
  "frontend",
  "dynamic-ev-charge-optimizer-card.js"
);

global.HTMLElement = class {};
global.customElements = {
  _defined: {},
  get(name) {
    return this._defined[name];
  },
  define(name, ctor) {
    this._defined[name] = ctor;
  },
};
global.window = {};

new Function(fs.readFileSync(CARD, "utf8"))();

const Strategy = customElements.get(
  "ll-strategy-dashboard-dynamic-ev-charge-optimizer"
);
assert.ok(Strategy, "the strategy element was never defined");
assert.strictEqual(
  typeof Strategy.generate,
  "function",
  "the strategy has no static generate()"
);

const registered = window.customStrategies.find(
  (s) => s.type === "dynamic-ev-charge-optimizer"
);
assert.ok(registered, "the strategy is not in window.customStrategies");
assert.strictEqual(registered.strategyType, "dashboard");
assert.ok(registered.name && registered.description, "picker entry is incomplete");

const P = "dynamic_ev_charge_optimizer";

function hassWith({ car = true, chargerSensors = true } = {}) {
  const states = {};
  const add = (id, attributes = {}) => {
    states[id] = { state: "0", attributes };
  };

  for (const suffix of [
    "plan_cost",
    "plan_energy",
    "plan_average_price",
    "plan_periods",
    "suggested_cost",
    "suggested_periods",
    "energy_needed",
    "prices_known_until",
    "measured_charging_power",
  ]) {
    add(`sensor.${P}_${suffix}`);
  }
  add(`binary_sensor.${P}_charge_now`);
  add(`number.${P}_charging_power`);
  add(`number.${P}_car_battery_capacity`);
  add(`number.${P}_target_charge_level`);
  add(`number.${P}_fixed_energy_to_add`);
  add(`number.${P}_price_surcharge_per_kwh`);
  add(`number.${P}_vat_on_electricity`);
  add(`datetime.${P}_ready_by`);
  add(`button.${P}_start_charging`);
  add(`button.${P}_stop`);
  add(`button.${P}_use_measured_charging_power`);
  add(`switch.${P}_charge_immediately`);

  const wiring = { price_entity: "sensor.market_price" };
  add("sensor.market_price");
  add("switch.my_charger");
  wiring.charger_switch = "switch.my_charger";

  if (chargerSensors) {
    add("sensor.my_charger_power");
    add("sensor.my_charger_session");
    wiring.charger_power = "sensor.my_charger_power";
    wiring.session_energy = "sensor.my_charger_session";
  }
  if (car) {
    add(`sensor.${P}_car_charge_level`);
    add(`button.${P}_refresh_car`);
    add("sensor.my_car_battery");
    add("sensor.my_car_last_fetch");
    wiring.car_soc = "sensor.my_car_battery";
    wiring.car_last_fetch = "sensor.my_car_last_fetch";
  }

  add(`sensor.${P}_wiring`, wiring);
  return { states, locale: { language: "en" }, config: { currency: "EUR" } };
}

function everyEntity(dashboard) {
  const found = [];
  for (const view of dashboard.views) {
    for (const card of view.cards) {
      for (const row of card.entities || []) found.push(row.entity);
    }
  }
  return found;
}

async function main() {
  // 1. A complete installation.
  const full = await Strategy.generate({}, hassWith());
  assert.ok(full.title, "no dashboard title");
  assert.strictEqual(full.views.length, 3, "expected three views");
  assert.ok(
    full.views[0].cards.some(
      (c) => c.type === "custom:dynamic-ev-charge-optimizer-card"
    ),
    "the planner card is not on the first view"
  );
  assert.ok(
    full.views.every((v) => v.cards.length > 0),
    "a view came out empty"
  );

  const hass = hassWith();
  const used = everyEntity(full);
  assert.ok(used.length > 10, "suspiciously few entities on the dashboard");
  for (const id of used) {
    assert.ok(hass.states[id], `dashboard refers to ${id}, which does not exist`);
  }
  assert.ok(
    used.includes("switch.my_charger"),
    "the configured charger was not picked up from the wiring sensor"
  );
  assert.ok(
    used.includes("sensor.my_car_battery"),
    "the configured car was not picked up from the wiring sensor"
  );

  // 2. No car, no charger sensors: those rows must simply not be there.
  const sparse = await Strategy.generate(
    {},
    hassWith({ car: false, chargerSensors: false })
  );
  const sparseStates = hassWith({ car: false, chargerSensors: false }).states;
  for (const id of everyEntity(sparse)) {
    assert.ok(
      sparseStates[id],
      `sparse dashboard refers to ${id}, which does not exist`
    );
  }
  // Named exactly: "car battery capacity" is a planner setting that belongs there
  // whether or not a car is linked, and an earlier version of this check mistook
  // it for a leftover.
  for (const absent of [
    `sensor.${P}_car_charge_level`,
    `button.${P}_refresh_car`,
    "sensor.my_car_battery",
    "sensor.my_car_last_fetch",
  ]) {
    assert.ok(
      !everyEntity(sparse).includes(absent),
      `${absent} survived on an installation with no car`
    );
  }
  assert.ok(sparse.views.length >= 1, "the sparse dashboard has no views at all");

  // 3. The integration is not installed: say so rather than render nothing.
  const missing = await Strategy.generate({}, { states: {} });
  assert.strictEqual(missing.views.length, 1);
  assert.strictEqual(missing.views[0].cards[0].type, "markdown");
  assert.ok(
    missing.views[0].cards[0].content.length > 40,
    "the not-found message says too little to act on"
  );

  // 4. Dutch comes out Dutch.
  const dutch = await Strategy.generate({}, {
    ...hassWith(),
    locale: { language: "nl" },
  });
  assert.strictEqual(dutch.views[2].title, "Instellingen");

  console.log(
    `strategy ok: ${full.views.length} views, ${used.length} entities, ` +
      `sparse ${everyEntity(sparse).length}, translated`
  );
}

main().catch((err) => {
  console.error("strategy FAILED:", err.message);
  process.exit(1);
});
