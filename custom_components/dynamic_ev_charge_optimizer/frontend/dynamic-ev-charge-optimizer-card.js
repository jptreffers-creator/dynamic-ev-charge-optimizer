/*
 * dynamic-ev-charge-optimizer-card
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

const num = (state) => {
  const v = Number(state?.state);
  return isNaN(v) ? null : v;
};

/* Every word the card can say, English first because that is the fallback for any
   language we do not have. A bundle is merged over the English one, so a partial
   translation still renders a complete card. Entries that take values are
   functions, which leaves word order to the translator instead of forcing every
   language through English sentence structure. */
const STRINGS = {
  en: {
    title: "Charge planner",
    chargeTo: "charge to",
    orFixed: "or fixed",
    readyBy: "Ready by",
    btnSchedule: "Charge on schedule",
    btnNow: "Charge now",
    btnNowOn: "Charge now: on",
    btnStop: "Stop",
    slotsSummary: "Price per period in the plan",
    notFound: "Dynamic EV Charge Optimizer not found. Is the integration set up?",
    started: (periods, cost) => `Started. Scheduled: ${periods}, ${cost}.`,
    noProposalPossible:
      "No proposal is possible. Check how much is needed and the deadline.",
    nowTurnedOn: "Charge now on. The charger switches on whatever the price.",
    nowTurnedOff: "Charge now off. The schedule decides when charging happens again.",
    stopped: "Stopped, and the schedule cleared.",
    saidTarget: (pct) => `Charging to ${pct} percent.`,
    saidFixed: (kwh) => `Fixed at ${kwh} kilowatt-hours.`,
    saidFollowCar: "Following the car's charge level again.",
    subPrices: (when) => `prices known until ${when}`,
    subScheduled: (n) => `${n} period${n === 1 ? "" : "s"} scheduled`,
    subNoSchedule: "no schedule — the charger is yours to use by hand",
    subCharging: "charging now",
    chartLabel: (from, to, low, high) =>
      `Electricity price from ${from} to ${to}. ` +
      `Lowest ${low}, highest ${high} per kilowatt-hour.`,
    legendScheduled: "scheduled",
    legendProposal: "proposal",
    legendNow: "now",
    carAt: (pct) => `The car is at ${pct}%,`,
    readingAge: (when) =>
      ` That figure is from ${when} — the car is read rarely on purpose.`,
    hintFixed: (kwh) =>
      `Fixed at ${kwh} kWh. The percentage is ignored while there is a number here.`,
    hintFromTo: (car, target, kwh, age) =>
      `From ${car}% to ${target}% is ${kwh} kWh.${age}`,
    hintAlready: (car, target, age) =>
      `The car is already at ${car}%, so there is nothing to add up to ${target}%.${age}`,
    hintNeeded: (target, kwh) => `To ${target}% — ${kwh} kWh needed.`,
    hintUnknown: (target) =>
      `To ${target}% — charge level unknown, enter a fixed number of kWh instead.`,
    labelScheduled: "Scheduled",
    labelProposal: "Proposal",
    planLine: (label, n, kwh, cost, avg) =>
      `${label}: ${n} period${n === 1 ? "" : "s"} · ${kwh} kWh · ` +
      `<b>${cost}</b> · ${avg}/kWh average`,
    nothingScheduled: "Nothing scheduled yet.",
    switchPoints: "Switch points: ",
    on: "ON",
    off: "OFF",
    noProposal: "No proposal — set how much is needed and a deadline.",
    proposalPrefix: "Proposal: ",
    warnNowOn:
      "Charge now is on: charging continues whatever the price, until you turn it " +
      "off. The schedule is suspended meanwhile.",
    warnHorizon: (when) =>
      `Prices are known until ${when}. Part of the plan falls beyond that and is ` +
      `not in the total yet.`,
    thFrom: "From",
    thTo: "To",
    thCost: "Cost",
    thAvgPrice: "Avg. price",
    thStart: "Start",
    thPricePerKwh: "Price/kWh",
  },

  nl: {
    title: "Laadplanner",
    chargeTo: "laden tot",
    orFixed: "of vast",
    readyBy: "Klaar om",
    btnSchedule: "Schema laden",
    btnNow: "Laad nu",
    btnNowOn: "Laad nu: aan",
    btnStop: "Stop",
    slotsSummary: "Prijs per periode in het plan",
    notFound: "Dynamic EV Charge Optimizer niet gevonden. Is de integratie ingesteld?",
    started: (periods, cost) => `Gestart. Ingepland: ${periods}, ${cost}.`,
    noProposalPossible:
      "Geen voorstel mogelijk. Controleer de laadbehoefte en het tijdstip.",
    nowTurnedOn: "Laad nu aan. De laadpaal gaat aan, ongeacht de prijs.",
    nowTurnedOff: "Laad nu uit. Het schema bepaalt weer wanneer er geladen wordt.",
    stopped: "Gestopt en het schema gewist.",
    saidTarget: (pct) => `Laden tot ${pct} procent.`,
    saidFixed: (kwh) => `Vast ingesteld op ${kwh} kilowattuur.`,
    saidFollowCar: "Volgt weer het accuniveau van de auto.",
    subPrices: (when) => `prijzen bekend tot ${when}`,
    subScheduled: (n) => `${n} periode${n === 1 ? "" : "s"} ingepland`,
    subNoSchedule: "geen schema — laadpaal met de hand te bedienen",
    subCharging: "laadt nu",
    chartLabel: (from, to, low, high) =>
      `Stroomprijs van ${from} tot ${to}. ` +
      `Laagste ${low}, hoogste ${high} per kilowattuur.`,
    legendScheduled: "ingepland",
    legendProposal: "voorstel",
    legendNow: "nu",
    carAt: (pct) => `Auto staat op ${pct}%,`,
    readingAge: (when) =>
      ` Dat cijfer is van ${when} — de auto wordt met opzet zelden uitgelezen.`,
    hintFixed: (kwh) =>
      `Vast op ${kwh} kWh. Het percentage telt niet mee zolang hier een getal staat.`,
    hintFromTo: (car, target, kwh, age) =>
      `Van ${car}% naar ${target}% is ${kwh} kWh.${age}`,
    hintAlready: (car, target, age) =>
      `De auto staat al op ${car}%, dus er is niets te laden tot ${target}%.${age}`,
    hintNeeded: (target, kwh) => `Tot ${target}% — ${kwh} kWh nodig.`,
    hintUnknown: (target) =>
      `Tot ${target}% — accuniveau onbekend, vul anders een vast aantal kWh in.`,
    labelScheduled: "Ingepland",
    labelProposal: "Voorstel",
    planLine: (label, n, kwh, cost, avg) =>
      `${label}: ${n} periode${n === 1 ? "" : "s"} · ${kwh} kWh · ` +
      `<b>${cost}</b> · gemiddeld ${avg}/kWh`,
    nothingScheduled: "Nog niets ingepland.",
    switchPoints: "Schakelmomenten: ",
    on: "AAN",
    off: "UIT",
    noProposal: "Geen voorstel — stel een laadbehoefte en een tijdstip in.",
    proposalPrefix: "Voorstel: ",
    warnNowOn:
      "Laad nu staat aan: er wordt geladen ongeacht de prijs, tot je het uitzet. " +
      "Het schema is zolang buiten werking.",
    warnHorizon: (when) =>
      `Prijzen zijn bekend tot ${when}. Een deel van het plan valt daarbuiten en ` +
      `zit nog niet in het totaal.`,
    thFrom: "Van",
    thTo: "Tot",
    thCost: "Kosten",
    thAvgPrice: "Gem. prijs",
    thStart: "Start",
    thPricePerKwh: "Prijs/kWh",
  },
};


class DynamicEvChargeOptimizerCard extends HTMLElement {
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

  /* ---------- language, dates and money ---------- */

  _lang() {
    const raw = this._hass?.locale?.language || this._hass?.language || "en";
    return String(raw).slice(0, 2).toLowerCase();
  }

  /* English underneath, the chosen language on top, so a partial translation
     still renders a complete card. */
  _t() {
    return { ...STRINGS.en, ...(STRINGS[this._lang()] || {}) };
  }

  _time(d) {
    return d.toLocaleTimeString(this._lang(), {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  _dayTime(d) {
    return d.toLocaleString(this._lang(), {
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  /* The currency comes from Home Assistant's own setting rather than a euro sign
     baked into the card: a Nord Pool user is billed in kroner, and a card that
     insists on euros is simply wrong for them. */
  _money(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    const currency = this._hass?.config?.currency || "EUR";
    try {
      return new Intl.NumberFormat(this._lang(), {
        style: "currency",
        currency,
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(Number(v));
    } catch (e) {
      // An unknown currency code makes Intl throw rather than fall back itself.
      return `${Number(v).toFixed(digits)} ${currency}`;
    }
  }

  _cost(v) {
    return this._money(v, 2);
  }

  _price(v) {
    return this._money(v, 4);
  }

  connectedCallback() {
    // The one and only moment the car is asked for a fresh reading. The integration
    // refuses if the value is still fresh or if it was asked recently, so this stays
    // harmless however often the dashboard is opened.
    if (!this._askedForCar && this._hass) {
      this._askedForCar = true;
      this._hass.callService("dynamic_ev_charge_optimizer", "refresh_car", {});
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._resolve();
    if (!this._built) this._build();
    this._render();
    if (!this._askedForCar && this.isConnected) {
      this._askedForCar = true;
      hass.callService("dynamic_ev_charge_optimizer", "refresh_car", {});
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
    const t = this._t();
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
        /* A table of five columns full of dates is as wide as the language makes
           it: Norwegian renders "man. kl. 10:30" where Dutch gets "ma 10:30".
           The wrapper keeps that inside the card instead of stretching the
           dashboard, and nowrap stops a date breaking across three lines. */
        .tablewrap { overflow-x:auto; }
        table { width:100%; border-collapse:collapse; margin:8px 0 14px; font-size:.86rem; }
        td:first-child, td:nth-child(2) { white-space:nowrap; }
        th,td { text-align:left; padding:5px 6px; border-bottom:1px solid var(--divider-color); }
        th { color:var(--secondary-text-color); font-weight:500; }
        td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
        details { margin:8px 0; }
        summary { cursor:pointer; font-size:.88rem; color:var(--secondary-text-color); }
        .sr { position:absolute; width:1px; height:1px; overflow:hidden;
              clip:rect(0 0 0 0); white-space:nowrap; }
      </style>
      <ha-card>
        <h3>${t.title}</h3>
        <div class="sub" id="sub"></div>
        <svg id="svg" role="img"></svg>
        <div class="axis" id="axis"></div>
        <div class="legend" id="legend"></div>

        <div class="row">
          <span class="now" id="carnow"></span>
          <label for="soc">${t.chargeTo}</label>
          <input type="number" id="soc" min="10" max="100" step="5" inputmode="numeric">
          <span class="unit">%</span>
          <label for="kwh">${t.orFixed}</label>
          <input type="number" id="kwh" min="0" max="200" step="0.5" inputmode="decimal">
          <span class="unit">kWh</span>
        </div>
        <div class="row">
          <label for="deadline">${t.readyBy}</label>
          <input type="datetime-local" id="deadline">
        </div>
        <div class="note" id="hint"></div>

        <div class="row">
          <button id="start">${t.btnSchedule}</button>
          <button id="now" aria-pressed="false">${t.btnNow}</button>
          <button id="stop">${t.btnStop}</button>
        </div>

        <div id="warnbox"></div>
        <div class="summary" id="planline"></div>
        <div class="note" id="timeline"></div>
        <div class="tablewrap"><table id="periods"></table></div>

        <div class="summary" id="sugline"></div>
        <div class="note" id="sugtimeline"></div>

        <details>
          <summary>${t.slotsSummary}</summary>
          <div class="tablewrap"><table id="slots"></table></div>
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
      const s = this._t();
      this._say(
        sug && sug !== "none"
          ? s.started(sug, this._cost(num(this._s("suggestedCost"))))
          : s.noProposalPossible
      );
    });
    this._el.now.addEventListener("click", () => {
      const id = this._ids?.now;
      if (!id) return;
      const on = this._s("now")?.state === "on";
      this._hass.callService("switch", on ? "turn_off" : "turn_on", { entity_id: id });
      this._say(on ? this._t().nowTurnedOff : this._t().nowTurnedOn);
    });

    this._el.stop.addEventListener("click", () => {
      this._press("stop");
      this._say(this._t().stopped);
    });
    this._el.soc.addEventListener("change", (e) => {
      const v = Math.min(100, Math.max(10, Number(e.target.value) || 0));
      this._setNumber("targetSoc", v);
      this._say(this._t().saidTarget(v));
    });
    this._el.kwh.addEventListener("change", (e) => {
      const v = Math.max(0, Number(e.target.value) || 0);
      this._setNumber("override", v);
      const s = this._t();
      this._say(v > 0 ? s.saidFixed(v) : s.saidFollowCar);
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
    const t = this._t();
    if (!this._built) return;
    if (!this._ids?.horizon || !this._s("horizon")) {
      this._el.sub.textContent = t.notFound;
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
      `${kw ?? "?"} kW · ` +
      t.subPrices(horizonEnd ? this._dayTime(horizonEnd) : "?") +
      " · " +
      (committed.length ? t.subScheduled(committed.length) : t.subNoSchedule) +
      (charging ? " · " + t.subCharging : "");

    this._drawChart(prices, committed, suggested, slotMinutes);
    this._drawInputs();
    this._drawPlan(committed, suggested, horizonEnd);
    this._drawSlotTable(prices, committed, slotMinutes, kw);
  }

  _drawChart(prices, committed, suggested, slotMinutes) {
    const t = this._t();
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
      t.chartLabel(
        this._dayTime(prices[0].t),
        this._dayTime(prices[n - 1].t),
        this._price(min),
        this._price(max)
      )
    );
    this._el.svg.innerHTML = parts.join("");

    const marks = [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];
    this._el.axis.innerHTML = marks
      .map((i) => `<span>${this._dayTime(prices[i].t)}</span>`)
      .join("");
    this._el.legend.innerHTML =
      `<span><span class="key" style="background:var(--primary-color)"></span>${t.legendScheduled}</span>` +
      `<span><span class="key" style="background:var(--accent-color,#ff9800)"></span>${t.legendProposal}</span>` +
      `<span><span class="key" style="background:var(--error-color,#db4437)"></span>${t.legendNow}</span>`;
  }

  _drawInputs() {
    const t = this._t();
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
      this._el.carnow.textContent = t.carAt(car);
      this._el.carnow.classList.toggle("stale", stale);
    }

    const age =
      stale && lastSeen
        ? t.readingAge(this._dayTime(new Date(lastSeen)))
        : "";

    this._el.hint.textContent =
      override > 0
        ? t.hintFixed(override.toFixed(1))
        : car !== null && needed
        ? t.hintFromTo(car, soc ?? "?", needed.toFixed(1), age)
        : car !== null
        ? t.hintAlready(car, soc ?? "?", age)
        : needed
        ? t.hintNeeded(soc ?? "?", needed.toFixed(1))
        : t.hintUnknown(soc ?? "?");
  }

  _drawPlan(committed, suggested, horizonEnd) {
    const t = this._t();
    const line = (periods, cost, kwh, avg, label) =>
      periods.length
        ? t.planLine(
            label,
            periods.length,
            Number(kwh).toFixed(1),
            this._cost(cost),
            this._price(avg)
          )
        : "";

    this._el.planline.innerHTML =
      line(committed, num(this._s("planCost")), num(this._s("planEnergy")),
           num(this._s("planAvg")), t.labelScheduled) || t.nothingScheduled;
    this._el.timeline.textContent = committed.length
      ? t.switchPoints +
        committed
          .flatMap((p) => [
            `${t.on} ${this._dayTime(p.start)}`,
            `${t.off} ${this._dayTime(p.end)}`,
          ])
          .join(" · ")
      : "";

    // The proposal has no totals of its own as entities, so add them up from the
    // periods rather than showing a blank where a number belongs.
    const sugCost = num(this._s("suggestedCost"));
    const sugKwh = suggested.reduce((sum, p) => sum + Number(p.kwh || 0), 0);
    this._el.sugline.innerHTML =
      line(suggested, sugCost, sugKwh, sugKwh ? sugCost / sugKwh : null,
           t.labelProposal) || t.noProposal;
    this._el.sugtimeline.textContent = suggested.length
      ? t.proposalPrefix +
        suggested.map((p) => `${this._dayTime(p.start)}-${this._time(p.end)}`).join(" · ")
      : "";

    const over =
      horizonEnd && committed.some((p) => p.end.getTime() > horizonEnd.getTime());
    const nowOn = this._s("now")?.state === "on";
    // Both the label and aria-pressed change, because an override you cannot tell is
    // running is an override you forget, and this one costs money every quarter of an hour.
    this._el.now.textContent = nowOn ? t.btnNowOn : t.btnNow;
    this._el.now.setAttribute("aria-pressed", nowOn ? "true" : "false");

    const warns = [];
    if (nowOn) {
      warns.push(
        `<div class="warn">${t.warnNowOn}</div>`
      );
    }
    if (over) {
      warns.push(
        `<div class="warn">${t.warnHorizon(this._dayTime(horizonEnd))}</div>`
      );
    }
    this._el.warnbox.innerHTML = warns.join("");

    this._el.periods.innerHTML = committed.length
      ? `<thead><tr><th>${t.thFrom}</th><th>${t.thTo}</th><th class="num">kWh</th>
         <th class="num">${t.thCost}</th><th class="num">${t.thAvgPrice}</th></tr></thead><tbody>` +
        committed
          .map(
            (p) => `<tr><td>${this._dayTime(p.start)}</td><td>${this._dayTime(p.end)}</td>
              <td class="num">${Number(p.kwh).toFixed(1)}</td>
              <td class="num">${this._cost(p.cost)}</td>
              <td class="num">${this._price(p.avg)}</td></tr>`
          )
          .join("") +
        "</tbody>"
      : "";
  }

  _drawSlotTable(prices, committed, slotMinutes, kw) {
    const t = this._t();
    const kwhPerSlot = (kw || 0) * (slotMinutes / 60);
    const rows = prices
      .filter((s) =>
        committed.some(
          (q) => s.t.getTime() >= q.start.getTime() && s.t.getTime() < q.end.getTime()
        )
      )
      .map(
        (s) => `<tr><td>${this._dayTime(s.t)}</td><td class="num">${this._price(s.p)}</td>
          <td class="num">${kwhPerSlot.toFixed(2)}</td>
          <td class="num">${this._cost(s.p * kwhPerSlot)}</td></tr>`
      );
    this._el.slots.innerHTML = rows.length
      ? `<thead><tr><th>${t.thStart}</th><th class="num">${t.thPricePerKwh}</th>
         <th class="num">kWh</th><th class="num">${t.thCost}</th></tr></thead>` +
        `<tbody>${rows.join("")}</tbody>`
      : `<tbody><tr><td>${t.nothingScheduled}</td></tr></tbody>`;
  }
}

if (!customElements.get("dynamic-ev-charge-optimizer-card")) {
  customElements.define("dynamic-ev-charge-optimizer-card", DynamicEvChargeOptimizerCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "dynamic-ev-charge-optimizer-card")) {
  window.customCards.push({
    type: "dynamic-ev-charge-optimizer-card",
    name: "Dynamic EV Charge Optimizer",
    description:
      "Price chart with the charging plan on it, and buttons to start and stop.",
  });
}
