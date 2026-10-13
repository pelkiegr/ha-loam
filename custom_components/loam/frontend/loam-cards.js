/* Loam Ride Conditions dashboard cards, served by the loam integration. */

const STATUS = {
  PRIME: { color: "#41d47a", label: "Prime" },
  DRY: { color: "#a9c25f", label: "Dry" },
  DUSTY: { color: "#d6b88a", label: "Dusty" },
  CAUTION: { color: "#ebaf28", label: "Caution" },
  "STAY OFF": { color: "#e8604a", label: "Stay off" },
  FROZEN: { color: "#7ac8e8", label: "Frozen" },
};
const UNKNOWN_STATUS = { color: "#8a9887", label: "Unknown" };

const ZONES = [
  { status: "STAY OFF", lo: 0, hi: 0.3 },
  { status: "CAUTION", lo: 0.3, hi: 0.62 },
  { status: "PRIME", lo: 0.62, hi: 0.86 },
  { status: "DRY", lo: 0.86, hi: 0.97 },
  { status: "DUSTY", lo: 0.97, hi: 1 },
];

const RAIN_COLOR = "#7eb8d4";
const HOUR_MS = 3600000;
const DAY_MS = 24 * HOUR_MS;
const REFETCH_MS = 10 * 60 * 1000;
const FONTS_URL =
  "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=National+Park:wght@500;700&display=swap";

function loadFontsOnce() {
  if (document.getElementById("loam-card-fonts")) return;
  const link = document.createElement("link");
  link.id = "loam-card-fonts";
  link.rel = "stylesheet";
  link.href = FONTS_URL;
  document.head.appendChild(link);
}

function statusMeta(status) {
  return STATUS[(status || "").toUpperCase()] || UNKNOWN_STATUS;
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
}

function dateFormatter(hass, options) {
  return new Intl.DateTimeFormat(hass.locale?.language || navigator.language, {
    timeZone: hass.config.time_zone,
    ...options,
  });
}

function usesFahrenheit(hass) {
  return hass.config.unit_system?.temperature === "°F";
}

function usesInches(hass) {
  return hass.config.unit_system?.length !== "km";
}

function formatTemperature(hass, celsius) {
  if (celsius == null) return "";
  const value = usesFahrenheit(hass) ? (celsius * 9) / 5 + 32 : celsius;
  return `${Math.round(value)}°`;
}

function formatRain(hass, inches) {
  if (!inches) return "";
  return usesInches(hass)
    ? `${inches.toFixed(inches < 1 ? 2 : 1).replace(/^0/, "")}″`
    : `${Math.round(inches * 25.4)} mm`;
}

function formatChangeTime(hass, isoTime) {
  const at = new Date(isoTime);
  const sameDay =
    dateFormatter(hass, { dateStyle: "short" }).format(at) ===
    dateFormatter(hass, { dateStyle: "short" }).format(new Date());
  return dateFormatter(
    hass,
    sameDay ? { hour: "numeric" } : { weekday: "short", hour: "numeric" },
  ).format(at);
}

function nextConfirmedChange(data, now = Date.now()) {
  return (data.changes || []).find(
    (change) => change.confirmed && Date.parse(change.at) > now,
  );
}

function todaysWeather(data, now = Date.now()) {
  return (data.daily || []).find((day) => {
    const start = Date.parse(day.starts_at);
    return start <= now && now < start + DAY_MS;
  });
}

function currentDryness(data, now = Date.now()) {
  const timeline = data.timeline;
  if (!timeline) return null;
  const index = Math.floor(
    (now - Date.parse(timeline.start)) / (timeline.step_hours * HOUR_MS),
  );
  return timeline.dryness[index] ?? null;
}

function openMoreInfo(element, entityId) {
  element.dispatchEvent(
    new CustomEvent("hass-more-info", {
      detail: { entityId },
      bubbles: true,
      composed: true,
    }),
  );
}

/* Shared fetch cache so several cards showing one trail make one call. */
const TrailData = {
  cache: new Map(),

  refreshKey(hass, entityId) {
    const state = hass.states[entityId];
    return `${state?.last_updated}|${Math.floor(Date.now() / REFETCH_MS)}`;
  },

  get(hass, entityId) {
    const key = this.refreshKey(hass, entityId);
    const cached = this.cache.get(entityId);
    if (cached && cached.key === key) return cached.promise;
    const promise = hass.callWS({ type: "loam/trail", entity_id: entityId });
    this.cache.set(entityId, { key, promise });
    promise.catch(() => this.cache.delete(entityId));
    return promise;
  },
};

function findLoamStatusEntities(hass) {
  return Object.values(hass.entities || {})
    .filter((entry) => entry.platform === "loam" && entry.entity_id.endsWith("_status"))
    .map((entry) => entry.entity_id);
}

/* ---------- Charts ---------- */

function chartWindow(timeline, now, hoursBack, hoursAhead) {
  const stepMs = timeline.step_hours * HOUR_MS;
  const startMs = Date.parse(timeline.start);
  const nowIndex = (now - startMs) / stepMs;
  const last = timeline.dryness.length - 1;
  const first = Math.max(0, Math.floor(nowIndex - hoursBack / timeline.step_hours));
  const end =
    hoursAhead == null
      ? last
      : Math.min(last, Math.ceil(nowIndex + hoursAhead / timeline.step_hours));
  return { first, end, nowIndex, startMs, stepMs };
}

function statusLinePaths(timeline, view, x, y) {
  const segments = [];
  let current = null;
  let previousPoint = null;
  for (let i = view.first; i <= view.end; i++) {
    const dryness = timeline.dryness[i];
    if (dryness == null) {
      current = null;
      previousPoint = null;
      continue;
    }
    const status = timeline.statuses[i] || "";
    const forecast = i >= timeline.forecast_from_index;
    const point = `${x(i).toFixed(1)},${y(dryness).toFixed(1)}`;
    if (!current || current.status !== status || current.forecast !== forecast) {
      current = { status, forecast, points: previousPoint ? [previousPoint] : [] };
      segments.push(current);
    }
    current.points.push(point);
    previousPoint = point;
  }
  return segments
    .map(
      (segment) => `<polyline points="${segment.points.join(" ")}"
        fill="none" stroke="${statusMeta(segment.status).color}"
        stroke-width="${segment.forecast ? 2 : 2.5}" stroke-linejoin="round" stroke-linecap="round"
        ${segment.forecast ? 'stroke-dasharray="5 4" opacity="0.75"' : ""}/>`,
    )
    .join("");
}

function sectionsBand(timeline, view, x, y) {
  const upper = timeline.drier_bound;
  const lower = timeline.wetter_bound;
  if (!upper || !lower) return "";
  const top = [];
  const bottom = [];
  for (let i = view.first; i <= view.end; i++) {
    if (upper[i] == null || lower[i] == null) continue;
    top.push(`${x(i).toFixed(1)},${y(upper[i]).toFixed(1)}`);
    bottom.unshift(`${x(i).toFixed(1)},${y(lower[i]).toFixed(1)}`);
  }
  if (!top.length) return "";
  return `<polygon points="${top.concat(bottom).join(" ")}" fill="#f3f6f2" opacity="0.07"/>`;
}

function rainBars(timeline, view, x, plotBottom, maxHeight) {
  const width = Math.max(1, (x(view.first + 1) - x(view.first)) * 0.8);
  let bars = "";
  for (let i = view.first; i <= view.end; i++) {
    const rain = timeline.rain_in[i];
    if (!rain) continue;
    const height = Math.max(1.5, Math.min(1, rain / 0.15) * maxHeight);
    bars += `<rect x="${(x(i) - width / 2).toFixed(1)}" y="${(plotBottom - height).toFixed(1)}"
      width="${width.toFixed(1)}" height="${height.toFixed(1)}" fill="${RAIN_COLOR}" opacity="0.55"/>`;
  }
  return bars;
}

function dayColumns(hass, data, view, xAtTime, plot, now) {
  const weekday = dateFormatter(hass, { weekday: "short" });
  let svg = "";
  for (const day of data.daily || []) {
    const startMs = Date.parse(day.starts_at);
    if (Number.isNaN(startMs)) continue;
    const left = Math.max(plot.left, xAtTime(startMs));
    const right = Math.min(plot.right, xAtTime(startMs + DAY_MS));
    if (right - left < 22) continue;
    if (xAtTime(startMs) > plot.left) {
      svg += `<line x1="${left}" x2="${left}" y1="${plot.top}" y2="${plot.bottom + 34}"
        stroke="#f0f8ec" opacity="0.08"/>`;
    }
    const center = (left + right) / 2;
    const isToday = startMs <= now && now < startMs + DAY_MS;
    const name = isToday ? "TODAY" : weekday.format(new Date(startMs + DAY_MS / 2)).toUpperCase();
    const rain = formatRain(hass, day.precipitation_in >= 0.05 ? day.precipitation_in : 0);
    svg += `<text x="${center}" y="${plot.bottom + 16}" class="day ${isToday ? "today" : ""}">${escapeHtml(name)}</text>
      <text x="${center}" y="${plot.bottom + 31}" class="wx">
        <tspan class="temp">${formatTemperature(hass, day.temp_max_c)}</tspan>${
          rain ? ` <tspan class="rain">${escapeHtml(rain)}</tspan>` : ""
        }</text>`;
  }
  return svg;
}

function renderDryingChart(hass, data, { daysBack = 3, now = Date.now() } = {}) {
  const timeline = data.timeline;
  if (!timeline) return "";
  const view = chartWindow(timeline, now, daysBack * 24, null);
  const width = 600;
  const plot = { left: 6, right: width - 2, top: 14, bottom: 124 };
  const height = plot.bottom + 40;
  const span = Math.max(1, view.end - view.first);
  const x = (i) => plot.left + ((i - view.first) / span) * (plot.right - plot.left);
  const y = (dryness) => plot.top + (1 - dryness) * (plot.bottom - plot.top);
  const xAtTime = (ms) => x((ms - view.startMs) / view.stepMs);

  const zones = ZONES.map(
    (zone) => `<rect x="${plot.left}" y="${y(zone.hi)}" width="${plot.right - plot.left}"
      height="${y(zone.lo) - y(zone.hi)}" fill="${statusMeta(zone.status).color}" opacity="0.06"/>
      <rect x="0" y="${y(zone.hi)}" width="3" height="${y(zone.lo) - y(zone.hi)}"
      fill="${statusMeta(zone.status).color}" opacity="0.85"/>`,
  ).join("");

  const forecastX = x(Math.max(view.first, timeline.forecast_from_index));
  const forecastShade =
    forecastX < plot.right
      ? `<rect x="${forecastX}" y="${plot.top}" width="${plot.right - forecastX}"
          height="${plot.bottom - plot.top}" fill="#f0f8ec" opacity="0.025"/>
         <text x="${plot.right - 4}" y="${plot.top - 4}" class="label" text-anchor="end">FORECAST</text>`
      : "";

  const nowX = x(view.nowIndex);
  const nowDryness = currentDryness(data, now);
  const nowMarker = `<line x1="${nowX}" x2="${nowX}" y1="${plot.top}" y2="${plot.bottom}"
      stroke="#f3f6f2" opacity="0.5" stroke-dasharray="2 3"/>
    <text x="${nowX}" y="${plot.top - 4}" class="label" text-anchor="middle">NOW</text>
    ${
      nowDryness == null
        ? ""
        : `<circle cx="${nowX}" cy="${y(nowDryness)}" r="5" fill="${statusMeta(data.status).color}"
            stroke="#191f1a" stroke-width="2.5"/>`
    }`;

  return `<svg viewBox="0 0 ${width} ${height}" class="drying-chart" role="img"
      aria-label="Modeled trail dryness, past ${daysBack} days and forecast">
    ${zones}
    ${forecastShade}
    ${dayColumns(hass, data, view, xAtTime, plot, now)}
    ${sectionsBand(timeline, view, x, y)}
    ${rainBars(timeline, view, x, plot.bottom, 26)}
    ${statusLinePaths(timeline, view, x, y)}
    ${nowMarker}
  </svg>`;
}

function renderSparkline(data, { now = Date.now() } = {}) {
  const timeline = data.timeline;
  if (!timeline) return "";
  const view = chartWindow(timeline, now, 12, 72);
  const width = 140;
  const height = 34;
  const span = Math.max(1, view.end - view.first);
  const x = (i) => 1 + ((i - view.first) / span) * (width - 2);
  const y = (dryness) => 3 + (1 - dryness) * (height - 6);
  const nowX = x(view.nowIndex);
  const rideableY = y(0.62);
  const nowDryness = currentDryness(data, now);
  return `<svg viewBox="0 0 ${width} ${height}" class="sparkline" aria-hidden="true">
    <line x1="0" x2="${width}" y1="${rideableY}" y2="${rideableY}" stroke="#f0f8ec"
      opacity="0.12" stroke-dasharray="2 3"/>
    <line x1="${nowX}" x2="${nowX}" y1="0" y2="${height}" stroke="#f3f6f2" opacity="0.3"/>
    ${statusLinePaths(timeline, view, x, y)}
    ${
      nowDryness == null
        ? ""
        : `<circle cx="${nowX}" cy="${y(nowDryness)}" r="3" fill="${statusMeta(data.status).color}"/>`
    }
  </svg>`;
}

/* ---------- Styles ---------- */

const CARD_STYLES = `
  :host {
    --loam-bg: #191f1a;
    --loam-ink: #f3f6f2;
    --loam-soft: #c1cec3;
    --loam-muted: #8a9887;
    --loam-line: rgba(240, 248, 236, 0.09);
    --loam-display: "National Park", system-ui, sans-serif;
    --loam-cond: "Barlow Condensed", "Arial Narrow", system-ui, sans-serif;
  }
  ha-card {
    background: var(--loam-bg);
    color: var(--loam-ink);
    overflow: hidden;
    border: 1px solid var(--loam-line);
  }
  .loam { padding: 16px 18px 14px; }
  .muted { color: var(--loam-muted); }
  header {
    display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
  }
  .name {
    font: 700 18px/1.2 var(--loam-display); cursor: pointer;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .place {
    font: 600 12px/1 var(--loam-cond); letter-spacing: 1.2px; text-transform: uppercase;
    color: var(--loam-muted); text-decoration: none; white-space: nowrap;
  }
  .place:hover { color: var(--loam-ink); }
  .verdict { margin: 14px 0 12px; }
  .status { display: flex; align-items: center; gap: 12px; }
  .dot {
    width: 14px; height: 14px; border-radius: 50%; flex: none;
    background: var(--accent); box-shadow: 0 0 14px var(--accent);
  }
  .word {
    font: 700 44px/0.95 var(--loam-cond); letter-spacing: 1px; color: var(--accent);
    text-transform: uppercase;
  }
  .outlook { margin-top: 6px; font-size: 15px; color: var(--loam-soft); }
  .next { margin-top: 6px; font-size: 13px; color: var(--loam-muted); }
  .next strong { color: var(--loam-ink); font-weight: 600; }
  .next .to { font-weight: 600; }
  .facts {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 10px; margin: 0 0 12px; padding: 10px 0; border-block: 1px solid var(--loam-line);
  }
  .facts dt {
    font: 600 11px/1 var(--loam-cond); letter-spacing: 1.4px; text-transform: uppercase;
    color: var(--loam-muted); margin-bottom: 4px;
  }
  .facts dd { margin: 0; font-size: 13px; color: var(--loam-ink); }
  .drying-chart { display: block; width: 100%; height: auto; }
  .drying-chart text { font-family: var(--loam-cond); fill: var(--loam-muted); }
  .drying-chart .label { font-size: 10px; font-weight: 600; letter-spacing: 1.2px; }
  .drying-chart .day { font-size: 12px; font-weight: 600; letter-spacing: 1px; text-anchor: middle; }
  .drying-chart .day.today { fill: var(--loam-ink); }
  .drying-chart .wx { font-size: 12px; text-anchor: middle; }
  .drying-chart .temp { fill: var(--loam-soft); }
  .drying-chart .rain { fill: ${RAIN_COLOR}; }
  footer {
    display: flex; justify-content: space-between; gap: 12px; margin-top: 8px;
    font-size: 12px; color: var(--loam-muted);
  }
  footer a { color: inherit; }
  .message { padding: 18px; color: var(--loam-muted); font-size: 14px; }

  .list { padding: 6px 0; container-type: inline-size; }
  .title {
    padding: 10px 18px 6px; font: 600 13px/1 var(--loam-cond); letter-spacing: 1.6px;
    text-transform: uppercase; color: var(--loam-muted);
  }
  .row {
    display: grid; grid-template-columns: 12px minmax(0, 1fr) 120px 76px; align-items: center;
    gap: 12px; width: 100%; padding: 10px 18px; background: none; border: 0;
    border-top: 1px solid var(--loam-line); color: inherit; font: inherit; text-align: left;
    cursor: pointer;
  }
  .row:first-of-type { border-top: 0; }
  .row:hover { background: rgba(240, 248, 236, 0.03); }
  .row .dot { width: 10px; height: 10px; box-shadow: 0 0 10px var(--accent); }
  .row .name { font-size: 15px; cursor: inherit; }
  .row .sub {
    margin-top: 3px; font-size: 12px; color: var(--loam-muted);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .row .word { font-size: 20px; text-align: right; }
  .sparkline { display: block; width: 100%; height: 34px; }
  @container (max-width: 380px) {
    .row { grid-template-columns: 12px minmax(0, 1fr) 76px; }
    .row .spark { display: none; }
  }
`;

/* ---------- Cards ---------- */

class LoamCardBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    loadFontsOnce();
  }

  set hass(hass) {
    this._hass = hass;
    this._refresh();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._refresh(), REFETCH_MS / 2);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  get _entityIds() {
    return [];
  }

  async _refresh() {
    if (!this._hass || !this._config) return;
    const keys = this._entityIds.map((id) => TrailData.refreshKey(this._hass, id)).join(",");
    if (keys === this._lastKeys) return;
    this._lastKeys = keys;
    this._results = await Promise.all(
      this._entityIds.map((entityId) =>
        TrailData.get(this._hass, entityId).then(
          (data) => ({ entityId, data }),
          (error) => ({ entityId, error: error.message || String(error) }),
        ),
      ),
    );
    this._render();
  }

  _paint(body) {
    this.shadowRoot.innerHTML = `<style>${CARD_STYLES}</style><ha-card>${body}</ha-card>`;
  }
}

class LoamTrailCard extends LoamCardBase {
  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { integration: "loam", domain: "sensor" } },
        },
        { name: "days_back", selector: { number: { min: 1, max: 10, mode: "box" } } },
      ],
    };
  }

  static getStubConfig(hass) {
    return { entity: findLoamStatusEntities(hass)[0] || "", days_back: 3 };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Set entity to a Loam trail sensor");
    this._config = { days_back: 3, ...config };
    this._lastKeys = null;
    this._refresh();
  }

  get _entityIds() {
    return [this._config.entity];
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _render() {
    const [result] = this._results || [];
    if (!result) return this._paint(`<div class="message">Loading trail conditions…</div>`);
    if (result.error) return this._paint(`<div class="message">${escapeHtml(result.error)}</div>`);
    this._paint(this._trailHtml(result.data));
    this.shadowRoot.querySelector(".name").addEventListener("click", () =>
      openMoreInfo(this, this._config.entity),
    );
  }

  _trailHtml(data) {
    const hass = this._hass;
    const meta = statusMeta(data.status);
    const change = nextConfirmedChange(data);
    const today = todaysWeather(data);
    const dryness = currentDryness(data);
    const modeled = data.observed_at
      ? dateFormatter(hass, { hour: "numeric", minute: "2-digit" }).format(new Date(data.observed_at))
      : null;
    const todayText = today
      ? [formatTemperature(hass, today.temp_max_c), formatRain(hass, today.precipitation_in)]
          .filter(Boolean)
          .join(" · ")
      : "";

    return `<div class="loam" style="--accent:${meta.color}">
      <header>
        <div class="name">${escapeHtml(data.name)}</div>
        <a class="place" href="${escapeHtml(data.url)}" target="_blank" rel="noreferrer">${escapeHtml(
          data.location || "",
        )}</a>
      </header>
      <div class="verdict">
        <div class="status"><span class="dot"></span><span class="word">${escapeHtml(
          data.status,
        )}</span></div>
        <div class="outlook">${escapeHtml(data.outlook || data.status_label || "")}</div>
        ${
          change
            ? `<div class="next"><strong>${escapeHtml(formatChangeTime(hass, change.at))}</strong>
                turns <span class="to" style="color:${statusMeta(change.to).color}">${escapeHtml(
                  statusMeta(change.to).label,
                )}</span></div>`
            : ""
        }
      </div>
      <dl class="facts">
        <div><dt>Recent rain</dt><dd>${escapeHtml(data.last_rain || "—")}</dd></div>
        ${todayText ? `<div><dt>Today</dt><dd>${escapeHtml(todayText)}</dd></div>` : ""}
        ${dryness == null ? "" : `<div><dt>Dryness</dt><dd>${Math.round(dryness * 100)}%</dd></div>`}
      </dl>
      ${renderDryingChart(hass, data, { daysBack: Number(this._config.days_back) || 3 })}
      <footer>
        <span>${escapeHtml(data.note || "")}</span>
        <span>${modeled ? `Modeled ${escapeHtml(modeled)} · ` : ""}<a href="${escapeHtml(
          data.url,
        )}" target="_blank" rel="noreferrer">Loam</a></span>
      </footer>
    </div>`;
  }
}

class LoamTrailsCard extends LoamCardBase {
  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        {
          name: "entities",
          required: true,
          selector: { entity: { multiple: true, integration: "loam", domain: "sensor" } },
        },
      ],
    };
  }

  static getStubConfig(hass) {
    return { title: "Trail conditions", entities: findLoamStatusEntities(hass) };
  }

  setConfig(config) {
    const entities = (config.entities || []).map((item) =>
      typeof item === "string" ? item : item.entity,
    );
    if (!entities.length) throw new Error("Add at least one Loam trail sensor to entities");
    this._config = { ...config, entities };
    this._lastKeys = null;
    this._refresh();
  }

  get _entityIds() {
    return this._config.entities;
  }

  getCardSize() {
    return 1 + (this._config?.entities.length || 1);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _render() {
    const rows = (this._results || []).map((result) => this._rowHtml(result)).join("");
    const title = this._config.title
      ? `<div class="title">${escapeHtml(this._config.title)}</div>`
      : "";
    this._paint(
      `<div class="loam list">${title}${rows || `<div class="message">Loading…</div>`}</div>`,
    );
    this.shadowRoot.querySelectorAll(".row").forEach((row) =>
      row.addEventListener("click", () => openMoreInfo(this, row.dataset.entity)),
    );
  }

  _rowHtml({ entityId, data, error }) {
    if (error) {
      return `<button class="row" data-entity="${escapeHtml(entityId)}" style="--accent:${UNKNOWN_STATUS.color}">
        <span class="dot"></span><div><div class="name">${escapeHtml(entityId)}</div>
        <div class="sub">${escapeHtml(error)}</div></div></button>`;
    }
    const meta = statusMeta(data.status);
    const change = nextConfirmedChange(data);
    const sub = [
      data.outlook,
      change && `${formatChangeTime(this._hass, change.at)} → ${statusMeta(change.to).label}`,
    ]
      .filter(Boolean)
      .join(" · ");
    return `<button class="row" data-entity="${escapeHtml(entityId)}" style="--accent:${meta.color}">
      <span class="dot"></span>
      <div><div class="name">${escapeHtml(data.name)}</div><div class="sub">${escapeHtml(sub)}</div></div>
      <div class="spark">${renderSparkline(data)}</div>
      <div class="word">${escapeHtml(data.status)}</div>
    </button>`;
  }
}

customElements.get("loam-trail-card") || customElements.define("loam-trail-card", LoamTrailCard);
customElements.get("loam-trails-card") || customElements.define("loam-trails-card", LoamTrailsCard);

window.customCards = window.customCards || [];
window.customCards.push(
  {
    type: "loam-trail-card",
    name: "Loam trail",
    description: "One trail's status, outlook, and drying chart.",
    preview: true,
    documentationURL: "https://github.com/pelkiegr/ha-loam",
  },
  {
    type: "loam-trails-card",
    name: "Loam trails",
    description: "Compact list of trails with status and a forecast sparkline.",
    preview: true,
    documentationURL: "https://github.com/pelkiegr/ha-loam",
  },
);
