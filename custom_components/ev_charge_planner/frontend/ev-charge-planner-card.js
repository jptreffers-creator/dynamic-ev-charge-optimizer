/*
 * ev-charge-planner-card
 *
 * Shows the price curve with the planned periods drawn on it, what they cost, and
 * two buttons: start and stop. There is deliberately no way to drag out a period by
 * hand -- the proposal does that job better, and the handles only cluttered the view.
 *
 * The graph is a convenience, not the content. Every number on it is repeated in
 * tables below, the plan is spelled out as switch times, and changes are announced
 * through a live region, so the card is usable without seeing it.
 */

const SUFFIXES = {
  planCost: ["sensor", "plan_cost"],
  planEnergy: ["sensor", "plan_energy"],
  planAvg: ["sensor", "plan_average_price"],
  planPeriods: ["sensor", "plan_periods"],
  suggestedCost: ["sensor", "suggested_cost"],
  suggestedPeriods: ["sensor", "suggested_periods"],
  energyNeeded: ["sensor", "energy_needed"],
  carLevel: ["sensor", "car_charge_level"],
  horizon: ["sensor", "prices_known_until"],
  measuredPower: ["sensor", "measured_charging_power"],
  chargeNow: ["binary_sensor", "charge_now"],
  power: ["number", "charging_power"],
  capacity: ["number", "car_battery_capacity"],
  targetSoc: ["number", "target_charge_level"],
  override: ["number", "fixed_energy_to_add"],
  deadline: ["datetime", "ready_by"],
  start: ["button", "start_charging"],
  stop: ["button", "stop"],
  adopt: ["button", "use_measured_charging_power"],
  now: ["switch", "charge_immediately"],
};

const fmtTime = (d) =>
  d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
const fmtDayTime = (d) =>
  d.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
const eur = (v) =>
  v === null || v === undefined || isNaN(v) ? "–" : "€" + Number(v).toFixed(2);
const eurKwh = (v) =>
  v === null || v === undefined || isNaN(v) ? "–" : "€" + Number(v).toFixed(4);
const num = (state) => {
  const v = Number(state?.state);
  return isNaN(v) ? null : v;
};

class EvChargePlannerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
    this._askedForCar = false;
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 10;
  }

  connectedCallback() {
    // The one and only moment the car is asked for a fresh reading. The integration
    // refuses if the value is still fresh or if it was asked recently, so this stays
    // harmless however often the dashboard is opened.
    if (!this._askedForCar && this._hass) {
      this._askedForCar = true;
      this._hass.callService("ev_charge_planner", "refresh_car", {});
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._resolve();
    if (!this._built) this._build();
    this._render();
    if (!this._askedForCar && this.isConnected) {
      this._askedForCar = true;
      hass.callService("ev_charge_planner", "refresh_car", {});
    }
  }

  /* Work out the entity ids from one known entity, so a plain `type:` with no
     options is enough in the common case of a single planner. */
  _resolve() {
    const prefix =
      this._config.prefix ||
      Object.keys(this._hass.states)
        .map((id) => id.match(/^sensor\.(.+)_prices_known_until$/))
        .filter(Boolean)
        .map((m) => m[1])[0];

    this._ids = {};
    if (!prefix) return;
    for (const [key, [domain, suffix]] of Object.entries(SUFFIXES)) {
      this._ids[key] = `${domain}.${prefix}_${suffix}`;
    }
  }

  _s(key) {
    return this._hass.states[this._ids?.[key]];
  }

  _periodsOf(key) {
    const attrs = this._s(key)?.attributes?.periods || [];
    return attrs.map((p) => ({
      start: new Date(p.start),
      end: new Date(p.end),
      slots: p.slots,
      kwh: p.kwh,
      cost: p.cost,
      avg: p.avg_price,
    }));
  }

  _press(key) {
    const id = this._ids?.[key];
    if (id) this._hass.callService("button", "press", { entity_id: id });
  }

  _setNumber(key, value) {
    const id = this._ids?.[key];
    if (id) this._hass.callService("number", "set_value", { entity_id: id, value });
  }

  _say(msg) {
    if (!this._el) return;
    this._el.live.textContent = "";
    clearTimeout(this._sayTimer);
    this._sayTimer = setTimeout(() => (this._el.live.textContent = msg), 60);
  }

  /* ---------- build ---------- */

  _build() {
    this._built = true;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:16px; }
        h3 { margin:0 0 4px; font-size:1.1rem; font-weight:500; }
        .sub { color:var(--secondary-text-color); font-size:.85rem; margin-bottom:12px; }
        svg { display:block; width:100%; height:180px; }
        .axis { display:flex; justify-content:space-between; font-size:.7rem;
                color:var(--secondary-text-color); margin:2px 0 8px; }
        .legend { display:flex; gap:14px; flex-wrap:wrap; font-size:.78rem;
                  color:var(--secondary-text-color); margin-bottom:12px; }
        .key { display:inline-block; width:12px; height:12px; border-radius:2px;
               vertical-align:-2px; margin-right:4px; }
        .row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:10px 0; }
        label { font-size:.85rem; color:var(--secondary-text-color); }
        input { background:var(--card-background-color); color:var(--primary-text-color);
                border:1px solid var(--divider-color); border-radius:6px; padding:6px 8px;
                font:inherit; font-size:.9rem; }
        input[type=number] { width:5.5em; text-align:right; font-variant-numeric:tabular-nums; }
        .unit { font-size:.85rem; color:var(--secondary-text-color); margin-left:-4px; }
        .now { font-size:.95rem; font-weight:600; }
        .now.stale { color:var(--secondary-text-color); font-weight:500; }
        button { border:0; border-radius:6px; padding:9px 16px; font:inherit;
                 font-size:.95rem; cursor:pointer; }
        #start { background:var(--accent-color,#ff9800); color:#000; font-weight:600; }
        #stop { background:transparent; color:var(--error-color,#db4437);
                border:1px solid var(--error-color,#db4437); }
        button:focus-visible { outline:2px solid var(--accent-color,#ff9800); outline-offset:2px; }
        .summary { font-size:1rem; margin:12px 0 2px; }
        .summary b { font-size:1.15rem; }
        .note { color:var(--secondary-text-color); font-size:.8rem; margin:4px 0; }
        .warn { color:var(--error-color,#db4437); font-size:.82rem; margin:6px 0; }
        table { width:100%; border-collapse:collapse; margin:8px 0 14px; font-size:.86rem; }
        th,td { text-align:left; padding:5px 6px; border-bottom:1px solid var(--divider-color); }
        th { color:var(--secondary-text-color); font-weight:500; }
        td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
        details { margin:8px 0; }
        summary { cursor:pointer; font-size:.88rem; color:var(--secondary-text-color); }
        .sr { position:absolute; width:1px; height:1px; overflow:hidden;
              clip:rect(0 0 0 0); white-space:nowrap; }
      </style>
      <ha-card>
        <h3>Laadplanner</h3>
        <div class="sub" id="sub"></div>
        <svg id="svg" role="img"></svg>
        <div class="axis" id="axis"></div>
        <div class="legend" id="legend"></div>

        <div class="row">
          <span class="now" id="carnow"></span>
          <label for="soc">laden tot</label>
          <input type="number" id="soc" min="10" max="100" step="5" inputmode="numeric">
          <span class="unit">%</span>
          <label for="kwh">of vast</label>
          <input type="number" id="kwh" min="0" max="200" step="0.5" inputmode="decimal">
          <span class="unit">kWh</span>
        </div>
        <div class="row">
          <label for="deadline">Klaar om</label>
          <input type="datetime-local" id="deadline">
        </div>
        <div class="note" id="hint"></div>

        <div class="row">
          <button id="start">Schema laden</button>
          <button id="now" aria-pressed="false">Laad nu</button>
          <button id="stop">Stop</button>
        </div>

        <div id="warnbox"></div>
        <div class="summary" id="planline"></div>
        <div class="note" id="timeline"></div>
        <table id="periods"></table>

        <div class="summary" id="sugline"></div>
        <div class="note" id="sugtimeline"></div>

        <details>
          <summary>Prijs per periode in het plan</summary>
          <table id="slots"></table>
        </details>

        <div class="sr" id="live" aria-live="polite" role="status"></div>
      </ha-card>`;

    this._el = {};
    for (const id of ["sub","svg","axis","legend","soc","kwh","deadline","hint","start",
                      "stop","now","warnbox","planline","timeline","periods","sugline",
                      "sugtimeline","slots","live","carnow"]) {
      this._el[id] = this.shadowRoot.getElementById(id);
    }

    this._el.start.addEventListener("click", () => {
      this._press("start");
      const sug = this._s("suggestedPeriods")?.state;
      this._say(
        sug && sug !== "none"
          ? `Gestart. Ingepland: ${sug}, ${eur(num(this._s("suggestedCost")))}.`
          : "Geen voorstel mogelijk. Controleer de laadbehoefte en het tijdstip."
      );
    });
    this._el.now.addEventListener("click", () => {
      const id = this._ids?.now;
      if (!id) return;
      const on = this._s("now")?.state === "on";
      this._hass.callService("switch", on ? "turn_off" : "turn_on", { entity_id: id });
      this._say(
        on
          ? "Laad nu uit. Het schema bepaalt weer wanneer er geladen wordt."
          : "Laad nu aan. De laadpaal gaat aan, ongeacht de prijs."
      );
    });

    this._el.stop.addEventListener("click", () => {
      this._press("stop");
      this._say("Gestopt en het schema gewist.");
    });
    this._el.soc.addEventListener("change", (e) => {
      const v = Math.min(100, Math.max(10, Number(e.target.value) || 0));
      this._setNumber("targetSoc", v);
      this._say(`Laden tot ${v} procent.`);
    });
    this._el.kwh.addEventListener("change", (e) => {
      const v = Math.max(0, Number(e.target.value) || 0);
      this._setNumber("override", v);
      this._say(v > 0 ? `Vast ingesteld op ${v} kilowattuur.`
                      : "Volgt weer het accuniveau van de auto.");
    });
    this._el.deadline.addEventListener("change", (e) => {
      if (!e.target.value || !this._ids?.deadline) return;
      this._hass.callService("datetime", "set_value", {
        entity_id: this._ids.deadline,
        datetime: e.target.value.replace("T", " ") + ":00",
      });
    });
  }

  /* ---------- render ---------- */

  _render() {
    if (!this._built) return;
    if (!this._ids?.horizon || !this._s("horizon")) {
      this._el.sub.textContent =
        "EV Charge Planner niet gevonden. Is de integratie ingesteld?";
      return;
    }

    const slotMinutes = this._s("horizon")?.attributes?.slot_minutes || 60;
    const prices = (this._s("horizon")?.attributes?.prices || []).map((p) => ({
      t: new Date(p.start),
      p: Number(p.price),
    }));
    const committed = this._periodsOf("planCost");
    const suggested = this._periodsOf("suggestedCost");
    const charging = this._s("chargeNow")?.state === "on";
    const kw = num(this._s("power"));

    const horizonEnd = this._s("horizon")?.state
      ? new Date(this._s("horizon").state)
      : null;
    this._el.sub.textContent =
      `${kw ?? "?"} kW · prijzen bekend tot ${horizonEnd ? fmtDayTime(horizonEnd) : "?"} · ` +
      (committed.length
        ? `${committed.length} periode${committed.length === 1 ? "" : "s"} ingepland`
        : "geen schema — laadpaal met de hand te bedienen") +
      (charging ? " · laadt nu" : "");

    this._drawChart(prices, committed, suggested, slotMinutes);
    this._drawInputs();
    this._drawPlan(committed, suggested, horizonEnd);
    this._drawSlotTable(prices, committed, slotMinutes, kw);
  }

  _drawChart(prices, committed, suggested, slotMinutes) {
    const n = prices.length;
    if (!n) {
      this._el.svg.innerHTML = "";
      this._el.axis.innerHTML = "";
      this._el.legend.innerHTML = "";
      return;
    }
    const W = 960, H = 180, band = 12, chartH = H - band * 2 - 6;
    const max = Math.max(...prices.map((p) => p.p), 0.01);
    const min = Math.min(...prices.map((p) => p.p));
    const bw = W / n;
    const inAny = (t, periods) =>
      periods.some((q) => t >= q.start.getTime() && t < q.end.getTime());
    const nowMs = Date.now();
    const parts = [];

    prices.forEach((s, i) => {
      const h = Math.max(1, (s.p / max) * chartH);
      const shade = 0.25 + 0.55 * (s.p / max);
      const isCommitted = inAny(s.t.getTime(), committed);
      const isSuggested = inAny(s.t.getTime(), suggested);
      const fill = isCommitted
        ? "var(--primary-color)"
        : `color-mix(in srgb, var(--primary-text-color) ${Math.round(shade * 100)}%, transparent)`;
      parts.push(
        `<rect x="${(i * bw).toFixed(2)}" y="${(chartH - h).toFixed(2)}" ` +
          `width="${Math.max(0.6, bw - 0.4).toFixed(2)}" height="${h.toFixed(2)}" fill="${fill}"/>`
      );
      if (isSuggested && !isCommitted)
        parts.push(
          `<rect x="${(i * bw).toFixed(2)}" y="0" width="${Math.max(0.6, bw).toFixed(2)}" ` +
            `height="${chartH}" fill="var(--accent-color,#ff9800)" opacity="0.16"/>`
        );
      if (isCommitted)
        parts.push(
          `<rect x="${(i * bw).toFixed(2)}" y="${chartH + 3}" width="${Math.max(0.6, bw).toFixed(2)}" ` +
            `height="${band}" fill="var(--primary-color)"/>`
        );
      if (isSuggested)
        parts.push(
          `<rect x="${(i * bw).toFixed(2)}" y="${chartH + 3 + band + 3}" ` +
            `width="${Math.max(0.6, bw).toFixed(2)}" height="${band}" ` +
            `fill="var(--accent-color,#ff9800)"/>`
        );
    });

    const nowIdx = prices.findIndex(
      (s) => s.t.getTime() + slotMinutes * 60000 > nowMs
    );
    if (nowIdx >= 0)
      parts.push(
        `<line x1="${(nowIdx * bw).toFixed(2)}" y1="0" x2="${(nowIdx * bw).toFixed(2)}" ` +
          `y2="${chartH}" stroke="var(--error-color,#db4437)" stroke-width="1.5" stroke-dasharray="3,3"/>`
      );

    this._el.svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    this._el.svg.setAttribute(
      "aria-label",
      `Stroomprijs van ${fmtDayTime(prices[0].t)} tot ${fmtDayTime(prices[n - 1].t)}. ` +
        `Laagste ${eurKwh(min)}, hoogste ${eurKwh(max)} per kilowattuur.`
    );
    this._el.svg.innerHTML = parts.join("");

    const marks = [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];
    this._el.axis.innerHTML = marks
      .map((i) => `<span>${fmtDayTime(prices[i].t)}</span>`)
      .join("");
    this._el.legend.innerHTML =
      `<span><span class="key" style="background:var(--primary-color)"></span>ingepland</span>` +
      `<span><span class="key" style="background:var(--accent-color,#ff9800)"></span>voorstel</span>` +
      `<span><span class="key" style="background:var(--error-color,#db4437)"></span>nu</span>`;
  }

  _drawInputs() {
    const soc = num(this._s("targetSoc"));
    const override = num(this._s("override"));
    const needed = num(this._s("energyNeeded"));
    const deadline = this._s("deadline")?.state;

    const active = this.shadowRoot.activeElement;
    if (active !== this._el.soc && soc !== null) this._el.soc.value = soc;
    if (active !== this._el.kwh) this._el.kwh.value = override ? override : "";
    this._el.kwh.placeholder = needed ? needed.toFixed(1) : "";
    if (active !== this._el.deadline && deadline) {
      const d = new Date(deadline);
      this._el.deadline.value = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16);
    }

    // With a car linked, lead with where it actually is. "11.2 kWh needed" tells you
    // nothing about whether that is nearly full or nearly empty.
    const carState = this._s("carLevel");
    const car = carState ? num(carState) : null;
    const stale = carState?.attributes?.stale === true;
    const lastSeen = carState?.attributes?.last_updated;

    if (car === null) {
      this._el.carnow.textContent = "";
      this._el.carnow.classList.remove("stale");
    } else {
      this._el.carnow.textContent = `Auto staat op ${car}%,`;
      this._el.carnow.classList.toggle("stale", stale);
    }

    const age =
      stale && lastSeen
        ? ` Dat cijfer is van ${fmtDayTime(new Date(lastSeen))} — de auto wordt met opzet zelden uitgelezen.`
        : "";

    this._el.hint.textContent =
      override > 0
        ? `Vast op ${override.toFixed(1)} kWh. Het percentage telt niet mee zolang hier een getal staat.`
        : car !== null && needed
        ? `Van ${car}% naar ${soc ?? "?"}% is ${needed.toFixed(1)} kWh.${age}`
        : car !== null
        ? `De auto staat al op ${car}%, dus er is niets te laden tot ${soc ?? "?"}%.${age}`
        : needed
        ? `Tot ${soc ?? "?"}% — ${needed.toFixed(1)} kWh nodig.`
        : `Tot ${soc ?? "?"}% — accuniveau onbekend, vul anders een vast aantal kWh in.`;
  }

  _drawPlan(committed, suggested, horizonEnd) {
    const line = (periods, cost, kwh, avg, label) =>
      periods.length
        ? `${label}: ${periods.length} periode${periods.length === 1 ? "" : "s"} · ` +
          `${Number(kwh).toFixed(1)} kWh · <b>${eur(cost)}</b> · gemiddeld ${eurKwh(avg)}/kWh`
        : "";

    this._el.planline.innerHTML =
      line(committed, num(this._s("planCost")), num(this._s("planEnergy")),
           num(this._s("planAvg")), "Ingepland") || "Nog niets ingepland.";
    this._el.timeline.textContent = committed.length
      ? "Schakelmomenten: " +
        committed
          .flatMap((p) => [`AAN ${fmtDayTime(p.start)}`, `UIT ${fmtDayTime(p.end)}`])
          .join(" · ")
      : "";

    // The proposal has no totals of its own as entities, so add them up from the
    // periods rather than showing a blank where a number belongs.
    const sugCost = num(this._s("suggestedCost"));
    const sugKwh = suggested.reduce((sum, p) => sum + Number(p.kwh || 0), 0);
    this._el.sugline.innerHTML =
      line(suggested, sugCost, sugKwh, sugKwh ? sugCost / sugKwh : null, "Voorstel") ||
      "Geen voorstel — stel een laadbehoefte en een tijdstip in.";
    this._el.sugtimeline.textContent = suggested.length
      ? "Voorstel: " +
        suggested.map((p) => `${fmtDayTime(p.start)}-${fmtTime(p.end)}`).join(" · ")
      : "";

    const over =
      horizonEnd && committed.some((p) => p.end.getTime() > horizonEnd.getTime());
    const nowOn = this._s("now")?.state === "on";
    // Both the label and aria-pressed change, because an override you cannot tell is
    // running is an override you forget, and this one costs money every quarter of an hour.
    this._el.now.textContent = nowOn ? "Laad nu: aan" : "Laad nu";
    this._el.now.setAttribute("aria-pressed", nowOn ? "true" : "false");

    const warns = [];
    if (nowOn) {
      warns.push(
        `<div class="warn">Laad nu staat aan: er wordt geladen ongeacht de prijs, ` +
          `tot je het uitzet. Het schema is zolang buiten werking.</div>`
      );
    }
    if (over) {
      warns.push(
        `<div class="warn">Prijzen zijn bekend tot ${fmtDayTime(horizonEnd)}. Een deel ` +
          `van het plan valt daarbuiten en zit nog niet in het totaal.</div>`
      );
    }
    this._el.warnbox.innerHTML = warns.join("");

    this._el.periods.innerHTML = committed.length
      ? `<thead><tr><th>Van</th><th>Tot</th><th class="num">kWh</th>
         <th class="num">Kosten</th><th class="num">Gem. prijs</th></tr></thead><tbody>` +
        committed
          .map(
            (p) => `<tr><td>${fmtDayTime(p.start)}</td><td>${fmtDayTime(p.end)}</td>
              <td class="num">${Number(p.kwh).toFixed(1)}</td>
              <td class="num">${eur(p.cost)}</td>
              <td class="num">${eurKwh(p.avg)}</td></tr>`
          )
          .join("") +
        "</tbody>"
      : "";
  }

  _drawSlotTable(prices, committed, slotMinutes, kw) {
    const kwhPerSlot = (kw || 0) * (slotMinutes / 60);
    const rows = prices
      .filter((s) =>
        committed.some(
          (q) => s.t.getTime() >= q.start.getTime() && s.t.getTime() < q.end.getTime()
        )
      )
      .map(
        (s) => `<tr><td>${fmtDayTime(s.t)}</td><td class="num">${eurKwh(s.p)}</td>
          <td class="num">${kwhPerSlot.toFixed(2)}</td>
          <td class="num">${eur(s.p * kwhPerSlot)}</td></tr>`
      );
    this._el.slots.innerHTML = rows.length
      ? `<thead><tr><th>Start</th><th class="num">Prijs/kWh</th><th class="num">kWh</th>
         <th class="num">Kosten</th></tr></thead><tbody>${rows.join("")}</tbody>`
      : `<tbody><tr><td>Nog niets ingepland.</td></tr></tbody>`;
  }
}

if (!customElements.get("ev-charge-planner-card")) {
  customElements.define("ev-charge-planner-card", EvChargePlannerCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "ev-charge-planner-card")) {
  window.customCards.push({
    type: "ev-charge-planner-card",
    name: "EV Charge Planner",
    description: "Prijsgrafiek met het laadplan, en knoppen om te starten en stoppen.",
  });
}
