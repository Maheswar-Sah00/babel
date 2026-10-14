// The Plan screen: the world map of where fans of games like yours are (Qloo data, aggregated per country by the
// server), the translation plan with a budget that re-fits on the server (babel.plan.fit_budget, the engine's own
// optimizer), Babel vs the usual list, and the evidence. Every number shown comes from the server; this file selects
// and formats it, and words it plainly (secondary detail stays behind a "+", in tooltips and in Why?).
// Text from the server is always inserted as text.

import { $, $$, api, countryName, errorText, fmtInt, fmtUsd, fmtUsd2, GROUP_LABEL, h, LANG, listText, pct,
  reducedMotion, short } from "./ui.js";
import { confidence, countryList, countryValue, fillFor, formatValue, headline, languageCountries, legendItems,
  lookalikeEntry, METRIC_ORDER, METRICS, model, qlooAdjustment, relativeParts, relativeText } from "./mapdata.js";
import { createWorldMap } from "./map.js";
import { renderCharts } from "./charts.js";

// a game like yours, by its Qloo status: [badge class, badge text, note in the game picker]
const STATUS_BADGE = { valid: ["badge-ok", "Used: real Qloo fan data", "used"],
  "default map": ["badge-warn", "Not used: Qloo has no real data", "no real Qloo data"],
  "not in Qloo": ["badge-warn", "Not used: Qloo doesn't know it", "Qloo doesn't know it"],
  "no heatmap": ["badge-warn", "Not used: no Qloo fan map", "no Qloo fan map"] };
// where a number or a sentence comes from: [class, label]; Qloo data, Babel's own figures and AI text stay apart
const SOURCES = { "Qloo data": ["src-qloo", "Qloo data"], "Babel estimate": ["src-estimate", "Babel estimate"],
  "Babel plan": ["src-plan", "Babel plan"], "Reference data": ["src-ref", "Public data"],
  "Steam reviews": ["", "Steam reviews"] };
const GROUP_ORDER = ["translate_game", "store_page_only", "skip"];
const LANGUAGE_NOTES = {
  spanish: "One translation for Spain and Latin America (Steam has two Spanish options; Babel plans one).",
  brazilian: "Brazil's Portuguese. Portugal's Portuguese is a separate Steam language and not one of the 14 targets.",
  tchinese: "Traditional characters, as read in Taiwan, Hong Kong and Macau.",
  schinese: "Simplified characters, as read in mainland China and Singapore.",
};
const LIST_SHOWN = 15;  // countries listed before "Show all"
const v = { worldState: "idle", worldMap: null, metric: "affinity", lookalike: "all", country: null, language: null,
  legendKey: null, fitTimer: 0, fitController: null, allCountries: false };

// ---------------------------------------------------------------- open
/** Show a finished plan. res = the API's result event {plan_id, status, result}; opts = {onBack, onTrace, errors}. */
export function openPlan(res, opts) {
  const r = res.result;
  Object.assign(v, {
    res, opts, plan: r.plan, map: r.explore?.map || null, vs: r.explore?.versus_generic || null,
    costs: r.explore?.costs || {}, notes: r.market_notes || null, explanation: r.explanation || null,
    index: r.evidence_index || {}, original: r.plan.costs.budget, country: null, language: null, legendKey: null,
    lookalike: "all", allCountries: false,
  });
  v.metric = v.map?.status !== "ok" ? "plan" : v.map.reference?.available ? "relative" : "affinity";
  v.fit = { status: r.plan.status, message: r.plan.status === "ok" ? null : r.plan.messages.at(-1),
    groups: r.plan.groups, costs: r.plan.costs, estimated_coverage: r.plan.estimated_coverage,
    reasons: Object.fromEntries(r.plan.languages.map((x) => [x.code, x.reason])) };
  v.m = model(v.map, v.plan, v.fit.groups);
  clearTimeout(v.fitTimer);
  v.fitController?.abort();

  renderHead();
  renderAlerts();
  renderToolbar();
  renderMethod();
  setupBudget();
  renderPlan();
  renderVersus();
  renderGlance();
  renderEvidence();
  ensureMap();
  repaint();
}

const scrollMode = () => (reducedMotion() ? "auto" : "smooth");
let printing = false;  // printed pages are always light (app.css keys its dark colours on @media screen)
const theme = () => (printing ? "light" : window.babelTheme?.get() || "light");
const nameOf = (cc) => countryName(cc, v.worldMap?.nameOf(cc));
const usable = () => v.m.usable;
const langRow = (code) => v.m.languages[code];
const budgetChanged = () => v.fit.costs.budget !== v.original;
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
const ordinal = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
const minShare = () => v.plan.allocation?.min_share ?? v.plan.inputs.min_share;
const minText = () => pct(minShare(), Number.isInteger(Math.round(minShare() * 1e6) / 1e4) ? 0 : 1);  // 0.01 -> "1%"
const adjustment = (code) => qlooAdjustment(langRow(code).qloo_lift, langRow(code).lookalikes_with_data > 0);

function badge(cls, text, title) {
  return h("span", { class: `badge ${cls}`, text, title });
}

function source(kind) {
  const [cls, text] = SOURCES[kind] || ["", kind];
  return h("span", { class: `src ${cls}`, text });
}

/** The exact figures behind a plain sentence, one click away. */
function exact(summary, ...body) {
  return h("details", { class: "exact" }, h("summary", { text: summary }), ...body);
}

/** Secondary detail kept off the first view: a small "+" that opens it. */
function plus(label, ...body) {
  return h("details", { class: "plus" }, h("summary", { "aria-label": label, title: label },
    h("span", { class: "plus-icon", "aria-hidden": "true" })), h("div", { class: "plus-body" }, ...body));
}

// ---------------------------------------------------------------- header and alerts
function renderHead() {
  const p = v.plan;
  const head = headline(v.fit.status, v.fit.groups, v.fit.costs);
  $("#plan-eyebrow").textContent = `Your plan · ${p.game.name}`;
  $("#plan-title").textContent = head.title;
  $("#plan-sub").textContent = `${head.sub} Text to translate: ${fmtInt.format(p.inputs.word_count)} words.`;
  const level = p.lookalikes.evidence_level;
  const n = p.lookalikes.used.length;
  $("#plan-chips").replaceChildren(...[
    h("li", { class: `chip-info level-${level}` }, h("span", { class: "chip-dot", "aria-hidden": "true" }),
      level === "none" ? "Qloo has no real fan data for games like yours: the usual share only"
        : `Based on ${plural(n, "game")} like yours with Qloo fan data${level === "low" ? " (fewer than usual)" : ""}`),
    budgetChanged() ? h("li", { class: "chip-info chip-changed" }, `Budget changed from ${fmtUsd.format(v.original)}`) : null,
  ].filter(Boolean));
}

/**
 * The plan's notes, plainly. The server's messages are [notes from finding the game..., notes about the evidence...,
 * the budget's note (if the status is not ok)]; the evidence notes are re-worded here from the plan's own fields, with
 * the server's wording as their tooltip. The budget's note is shown under the budget.
 */
function planNotes() {
  const p = v.plan;
  const look = p.lookalikes;
  const n = look.used.length;
  const plain = [];
  if (look.evidence_level === "none") {
    plain.push("Qloo has no real fan data for games like yours, so this plan uses the usual share for English-only indie games.");
  } else if (look.evidence_level === "low") {
    plain.push(`Only ${plural(n, "game")} like yours ${n === 1 ? "has" : "have"} Qloo fan data, fewer than usual, so the evidence is weaker.`);
  }
  if (look.widened_search) plain.push("Babel had to search wider than in its tests to find games like yours.");
  const messages = p.messages.slice(0, p.status === "ok" ? undefined : -1);
  if (messages.length < plain.length) return plain.map((text) => ({ text }));
  const cut = messages.length - plain.length;
  return [...messages.slice(0, cut).map((text) => ({ text: plainNote(text), exact: text })),
    ...plain.map((text, i) => ({ text, exact: messages[cut + i] }))];
}

/** A note from finding the game or its games like yours (babel/plan.py), plainly when it is a known one. */
function plainNote(text) {
  const d = v.plan.discovery;
  const reasons = d?.confidence?.reasons?.join(" ") || "";
  if (text.startsWith("Tags and candidate look-alikes were inferred") || text.startsWith("SteamSpy had only")) return null;
  if (d && text.startsWith("Weak evidence:")) {
    const alts = (d.alternatives || []).slice(0, 4).map((a) => a.name);
    return `Weak evidence: ${reasons} Pick the games like yours yourself${alts.length ? `, for example ${listText(alts)}` : ""}.`;
  }
  if (d && text.startsWith("Check the look-alikes:")) return `Check the games like yours: ${reasons}`;
  if (text === "Look-alikes chosen by you.") return "You chose the games like yours.";
  if (text.startsWith("No Steam tags found")) return "Steam has no tags for this game, so Babel found no games like yours: add tags or pick games yourself.";
  return text;
}

function renderAlerts() {
  const out = [];
  if (v.res.status !== "ok") {
    const errors = v.opts.errors?.length ? ` ${v.opts.errors.join(" ")}` : "";
    out.push(h("p", { class: "note", text: `Some data could not be read, so parts of this plan rest on less evidence.${errors}` }));
  }
  if (!v.map) out.push(h("p", { class: "note", text: "The world map could not be built for this plan; the plan itself is unaffected." }));
  for (const m of planNotes().filter((x) => x.text)) out.push(h("p", { class: "note is-info", text: m.text, title: m.exact }));
  $("#plan-alerts").replaceChildren(...out);
}

// ---------------------------------------------------------------- toolbar, legend, overlay
function renderToolbar() {
  const box = $("#metric-switch");
  box.replaceChildren(box.querySelector("legend"), ...METRIC_ORDER.map((key) => {
    const spec = METRICS[key];
    const input = h("input", { type: "radio", name: "metric", value: key, class: "visually-hidden",
      onchange: () => { v.metric = key; v.legendKey = null; renderToolbarState(); repaint(); } });
    input.checked = key === v.metric;
    return h("label", { class: "metric-option" }, input, h("span", { class: "metric-name", text: spec.label }),
      h("span", { class: "metric-src", text: SOURCES[spec.source]?.[1] || spec.source }));
  }));
  const select = $("#lookalike-select");
  const all = usable();
  const unused = (v.map?.lookalikes || []).filter((x) => !x.usable);
  select.replaceChildren(
    h("option", { value: "all", text: all.length ? `All ${plural(all.length, "game")} like yours (average)` : "No game like yours has Qloo fan data" }),
    ...all.map((x) => h("option", { value: String(x.appid), text: short(x.name, 40) })),
    unused.length ? h("optgroup", { label: "Not used by the plan" }, unused.map((x) =>
      h("option", { value: String(x.appid), text: `${short(x.name, 34)} (${STATUS_BADGE[x.status]?.[2] || x.status})` }))) : null);
  select.value = v.lookalike;
  select.onchange = () => { v.lookalike = select.value; v.legendKey = null; repaint(); };
  renderToolbarState();
}

function renderToolbarState() {
  const per = METRICS[v.metric].byLookalike;
  $("#lookalike-select").disabled = !per || !v.map;
  $(".lookalike-pick").classList.toggle("is-off", !per);
  $(".lookalike-pick").title = per ? "" : "This view is per language, not per game.";
}

function renderLegend() {
  const spec = METRICS[v.metric];
  const items = legendItems(v.metric, theme()).map((it) => {
    const swatch = h("span", { class: `swatch${it.pattern ? " swatch-hatch" : ""}`, "aria-hidden": "true" });
    if (!it.pattern) swatch.style.background = it.color;  // CSSOM: allowed by the page's CSP
    return h("button", { type: "button", class: "legend-item", "aria-pressed": String(v.legendKey === it.key),
      "data-key": it.key, title: it.detail || null,
      onclick: () => { v.legendKey = v.legendKey === it.key ? null : it.key; v.language = null; repaint(); } },
    swatch, it.label);
  });
  $("#map-legend").replaceChildren(
    h("p", { class: "legend-title", id: "legend-title" }, h("strong", { text: spec.label }), ` · ${spec.unit} · `,
      source(spec.source)), ...items);
  const ref = v.map?.reference?.lookalikes;
  $("#map-about").textContent = `${spec.about.replace("172", ref || "the")} Click a colour above to pick out its countries.`;
}

function overlayMessage() {
  if (v.worldState === "loading") return { text: "Loading the map…" };
  if (v.worldState === "failed") return { text: "The map could not load. The country list and the plan still work.", retry: true };
  if (!v.map) return { text: "The map data could not be built for this plan." };
  const spec = METRICS[v.metric];
  if (spec.byLookalike && v.map.status !== "ok") {
    return { text: "Qloo has no real fan data for any of the games like yours, so the plan uses the usual share for "
      + `English-only indie games. The “${METRICS.demand.label}” and “${METRICS.plan.label}” views still work.` };
  }
  const entry = lookalikeEntry(v.m, v.lookalike);
  if (spec.byLookalike && entry && !entry.usable) {
    return { text: `${entry.name}: ${countryValue(v.m, v.metric, "", v.lookalike).reason} Nothing is drawn for it.` };
  }
  return null;
}

function renderOverlay() {
  const msg = overlayMessage();
  const box = $("#map-overlay");
  $("#map-canvas").dataset.state = v.worldState === "ready" ? (msg ? "message" : "ready") : v.worldState;
  box.hidden = !msg;
  box.replaceChildren(...(msg ? [h("p", { text: msg.text }),
    msg.retry ? h("button", { type: "button", class: "button button-secondary", onclick: loadWorld }, "Try again") : null]
    .filter(Boolean) : []));
}

// ---------------------------------------------------------------- the map
function ensureMap() {
  if (!v.worldMap && window.d3) {
    v.worldMap = createWorldMap($("#map-svg-host"), {
      onSelect: (cc) => selectCountry(cc),
      onHover: showTooltip,
      theme: theme(),
    });
    wireMapControls();
  }
  if (v.worldState === "idle" || v.worldState === "failed") loadWorld();
}

async function loadWorld() {
  if (!v.worldMap) {
    v.worldState = "failed";
    return repaint();
  }
  v.worldState = "loading";
  renderOverlay();
  try {
    const res = await fetch("/static/world.json");
    if (!res.ok) throw new Error(String(res.status));
    v.worldMap.draw(await res.json());
    v.worldState = "ready";
  } catch {
    v.worldState = "failed";
  }
  repaint();
}

function wireMapControls() {
  $("#map-zoom-in").addEventListener("click", () => v.worldMap.zoomBy(1.6));
  $("#map-zoom-out").addEventListener("click", () => v.worldMap.zoomBy(1 / 1.6));
  $("#map-reset").addEventListener("click", () => v.worldMap.reset());
  $("#map-canvas").addEventListener("keydown", (e) => {
    if (e.target !== e.currentTarget || v.worldState !== "ready") return;
    const step = 60;
    const act = { ArrowLeft: () => v.worldMap.pan(step, 0), ArrowRight: () => v.worldMap.pan(-step, 0),
      ArrowUp: () => v.worldMap.pan(0, step), ArrowDown: () => v.worldMap.pan(0, -step),
      "+": () => v.worldMap.zoomBy(1.6), "=": () => v.worldMap.zoomBy(1.6), "-": () => v.worldMap.zoomBy(1 / 1.6),
      0: () => v.worldMap.reset() }[e.key];
    if (!act) return;
    e.preventDefault();
    act();
  });
}

function highlighted() {
  if (v.language) {
    const { model: counted, officialOnly } = languageCountries(v.m, v.language);
    return [counted, officialOnly];
  }
  if (v.legendKey) {
    const codes = Object.keys(v.map?.countries || {}).filter((cc) => fillFor(v.m, v.metric, cc, v.lookalike).key === v.legendKey);
    return [codes, []];
  }
  return [null, []];
}

function repaint() {
  if (v.worldState === "ready") {
    v.worldMap.paint((cc) => fillFor(v.m, v.metric, cc, v.lookalike, theme()));
    const [codes, alt] = highlighted();
    v.worldMap.highlight(codes, alt);
    v.worldMap.select(v.country);
  }
  renderLegend();
  renderOverlay();
  renderSummary();
  renderPanel();
}

/** The theme changed (or printing starts / ends): repaint the map, legend and country list; view, selection and
 * zoom stay as they are. */
function retheme() {
  v.worldMap?.setTheme(theme());
  if (v.m) repaint();
}

/** The map for the report, a printed (light) page: the live map, or a light copy of it in the dark theme. */
function reportMap() {
  const live = $("#map-svg-host svg");
  if (!live || v.worldState !== "ready" || theme() === "light") return live;
  return v.worldMap.snapshot((cc) => fillFor(v.m, v.metric, cc, v.lookalike, "light"), "light");
}

function renderSummary() {
  const spec = METRICS[v.metric];
  const top = countryList(v.m, v.metric, v.lookalike, nameOf).filter((r) => r.status === "value").slice(0, 3);
  $("#map-summary").textContent = top.length
    ? `Map of ${spec.label.toLowerCase()} (${spec.source}). Highest: ${top.map((r) => `${r.name} ${formatValue(v.metric, r.value)}`).join(", ")}.`
    : `Map of ${spec.label.toLowerCase()}: no values to show.`;
}

/** A country's value for the current view, as a short sentence (tooltip). */
function describeValue(val, metric = v.metric) {
  const spec = METRICS[metric];
  if (val.status !== "value") return val.reason;
  const n = spec.byLookalike && v.lookalike === "all" && usable().length > 1
    ? ` (from ${val.n} of ${usable().length} games like yours)` : "";
  if (metric === "relative") return `${cap(relativeText(val.value))}${n}`;
  if (metric === "affinity") return `Fan interest ${formatValue(metric, val.value)} on Qloo's 0–1 scale${n}`;
  if (metric === "demand") return `${pct(val.value)} of your likely non-English players (estimate)`;
  return `${spec.label}: ${formatValue(metric, val.value)}`;
}

function showTooltip(cc, e) {
  const tip = $("#map-tooltip");
  if (!cc) { tip.hidden = true; return; }
  const val = countryValue(v.m, v.metric, cc, v.lookalike);
  const lang = v.map?.countries?.[cc]?.model_language;
  tip.replaceChildren(h("strong", { text: nameOf(cc) }), h("span", { text: describeValue(val) }),
    lang ? h("span", { class: "muted", text: `Counts toward ${LANG[lang]}: ${GROUP_LABEL[v.m.groupOf[lang]].toLowerCase()}` }) : null,
    h("span", { class: "tip-hint", text: "Click for details" }));
  tip.hidden = false;
  const box = $("#map-canvas").getBoundingClientRect();
  const x = e.clientX - box.left;
  const y = e.clientY - box.top;
  tip.style.left = `${Math.min(x + 14, box.width - tip.offsetWidth - 8)}px`;
  tip.style.top = `${y + tip.offsetHeight + 24 > box.height ? y - tip.offsetHeight - 12 : y + 16}px`;
}

// ---------------------------------------------------------------- the side panel
function selectCountry(cc, { focus = false, zoom = false } = {}) {
  v.country = cc;
  v.language = null;
  v.legendKey = null;
  if (zoom && v.worldState === "ready") v.worldMap.zoomTo(cc);
  repaint();
  if (focus) $("#panel-title")?.focus();
}

function selectLanguage(code, { focus = false, scroll = false } = {}) {
  v.language = code;
  v.country = null;
  v.legendKey = null;
  if (v.worldState === "ready") v.worldMap.reset();
  repaint();
  if (scroll) $("#explore-title").scrollIntoView({ block: "start", behavior: scrollMode() });
  if (focus) $("#panel-title")?.focus({ preventScroll: scroll });
}

function backToWorld() {
  v.country = null;
  v.language = null;
  if (v.worldState === "ready") v.worldMap.reset();
  repaint();
  $("#country-search")?.focus();
}

function renderPanel() {
  const panel = $("#map-panel");
  const keep = panel.querySelector("#country-search");
  const query = keep?.value || "";
  const hadFocus = document.activeElement === keep;
  panel.replaceChildren(...(v.country ? countryPanel(v.country) : v.language ? languagePanel(v.language) : worldPanel(query)));
  if (hadFocus && !v.country && !v.language) {
    const input = $("#country-search");
    input.focus();
    input.setSelectionRange(query.length, query.length);
  }
}

function back() {
  return h("button", { type: "button", class: "link-button panel-back", onclick: backToWorld }, "← All countries");
}

function swatch(fill) {
  const el = h("span", { class: `swatch${fill === "url(#map-hatch)" ? " swatch-hatch" : ""}`, "aria-hidden": "true" });
  if (fill !== "url(#map-hatch)") el.style.background = fill;
  return el;
}

/** A value from fewer games like yours than the plan has (only in the all-games view of a Qloo metric). */
const thin = (r) => METRICS[v.metric].byLookalike && v.lookalike === "all" && r.n < usable().length;

function worldPanel(query) {
  const rows = countryList(v.m, v.metric, v.lookalike, nameOf);
  const q = query.trim().toLowerCase();
  const shown = q ? rows.filter((r) => r.name.toLowerCase().includes(q) || r.cc.toLowerCase() === q) : rows;
  const listed = q || v.allCountries ? shown : shown.slice(0, LIST_SHOWN);
  const more = listed.length < shown.length ? h("button", { type: "button", class: "link-button country-more",
    onclick: () => { v.allCountries = true; renderPanel(); $$(".country-row", $("#map-panel"))[LIST_SHOWN]?.focus(); } },
  `Show all ${shown.length} countries`) : null;
  const list = h("ul", { id: "country-list", class: "country-list", "aria-label": "Countries" },
    listed.map((r) => h("li", {}, h("button", { type: "button", class: "country-row", "data-cc": r.cc,
      onclick: () => selectCountry(r.cc, { focus: true, zoom: true }) },
    swatch(fillFor(v.m, v.metric, r.cc, v.lookalike, theme()).fill), h("span", { class: "country-name", text: r.name }),
    h("span", { class: "country-value", title: thin(r) ? `Only ${r.n} of the ${usable().length} games like yours have a score here` : null,
      text: r.status === "value" ? formatValue(v.metric, r.value) + (thin(r) ? ` · ${r.n} of ${usable().length}` : "")
        : r.status === "not_counted" ? "not counted" : "no score" })))));
  const search = h("input", { id: "country-search", type: "search", autocomplete: "off", placeholder: "e.g. Brazil",
    "aria-controls": "country-list", "aria-describedby": "country-count" });
  search.value = query;
  search.addEventListener("input", () => renderPanel());
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && shown.length) { e.preventDefault(); selectCountry($(".country-row", $("#map-panel")).dataset.cc, { focus: true, zoom: true }); }
    if (e.key === "ArrowDown") { e.preventDefault(); $(".country-row", $("#map-panel"))?.focus(); }
  });
  list.addEventListener("keydown", (e) => {
    if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
    const buttons = $$(".country-row", list);
    const i = buttons.indexOf(document.activeElement);
    e.preventDefault();
    if (e.key === "ArrowUp" && i <= 0) return $("#country-search").focus();
    buttons[Math.max(0, Math.min(buttons.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
  });
  const chips = GROUP_ORDER.concat("already_supported").filter((g) => v.fit.groups[g].length).map((g) =>
    h("div", { class: "lang-chip-group" }, h("span", { class: "lang-chip-label", text: GROUP_LABEL[g] }),
      h("div", { class: "lang-chips" }, v.fit.groups[g].map((code) => h("button", { type: "button",
        class: `lang-chip group-${g}`, onclick: () => selectLanguage(code, { focus: true }),
        "aria-label": `${LANG[code]}: show its countries` }, LANG[code])))));
  return [
    h("h3", { id: "panel-title", class: "panel-title", tabindex: "-1", text: "All countries" }),
    h("p", { class: "panel-help", text: "Pick a language to see which countries count for it, or a country to see its details." }),
    h("div", { class: "panel-block" }, chips),
    h("label", { class: "panel-label", for: "country-search", text: "Find a country" }), search,
    h("p", { id: "country-count", class: "help", text: q ? `${shown.length} match${shown.length === 1 ? "" : "es"}`
      : `${rows.filter((r) => r.status === "value").length} countries with a score, highest first` }),
    shown.length ? list : h("p", { class: "muted", text: "No country matches." }), more,
  ];
}

function lookalikeRows(cc) {
  const row = v.map.countries[cc];
  return usable().map((x) => {
    const s = row?.by_lookalike?.[String(x.appid)];
    return h("tr", {}, h("th", { scope: "row", text: short(x.name, 30) }),
      s ? [h("td", { text: s.affinity.toFixed(2) }), h("td", { text: s.relative == null ? "–" : `×${s.relative.toFixed(2)}` }),
        h("td", { text: fmtInt.format(s.cells) }), h("td", { text: s.popularity == null ? "–" : s.popularity.toFixed(2) })]
        : h("td", { colspan: "4", class: "muted", text: `No score (fewer than ${v.map.min_cells} map squares)` }));
  });
}

function marketFor(cc) {
  return (v.notes?.markets || []).find((m) => m.country === cc && Object.values(m.also_loves).some((r) => r.status === "ok"));
}

function marketBlock(m) {
  const lists = Object.entries(m.also_loves).filter(([, r]) => r.status === "ok").map(([domain, r]) =>
    h("div", { class: "loves" }, h("span", { class: "loves-label", text: domain === "films" ? "Films" : "Music" }),
      h("ul", {}, r.items.map((i) => h("li", { text: i.name })))));
  return h("div", { class: "panel-block" },
    h("h4", {}, "What these fans also like here ", source("Qloo data")),
    h("p", { class: "help", title: "Two Qloo steps: what is popular in the country, then re-ranked by fans of the games like yours.",
      text: `Popular in ${m.country_name}, then sorted by how much fans of games like yours like them. Background for marketing: it doesn't show what any one player likes.` }),
    lists,
    m.note?.status === "ok" ? h("p", { class: "llm-note", text: m.note.text }) : null,
    budgetChanged() ? h("p", { class: "help", text: `Markets were chosen for the ${fmtUsd.format(v.original)} plan.` }) : null);
}

function countryPanel(cc) {
  const row = v.map?.countries?.[cc] || { official_languages: [], by_lookalike: {} };
  const name = nameOf(cc);
  const out = [back(), h("h3", { id: "panel-title", class: "panel-title", tabindex: "-1", text: name })];
  if (!v.worldMap?.has(cc)) out.push(h("p", { class: "help", text: "Too small to draw at this map's scale." }));

  // Qloo evidence: compared with usual first, fan interest and the per-game numbers after
  const qloo = [h("h4", {}, "Fans of games like yours here ", source("Qloo data"))];
  if (!v.map || v.map.status !== "ok") {
    qloo.push(h("p", { class: "muted", text: "Qloo has no real fan data for any of the games like yours, so there is nothing to show for this country." }));
  } else {
    const a = countryValue(v.m, "affinity", cc);
    const r = countryValue(v.m, "relative", cc);
    const from = (x) => (usable().length > 1 ? ` (from ${x.n} of ${usable().length} games like yours)` : "");
    if (r.status === "value") {
      const [lead, rest] = relativeParts(r.value);
      qloo.push(h("p", { class: "panel-stat" }, h("strong", { text: cap(lead) }), ` ${rest}${from(r)}`));
      qloo.push(h("p", { class: "help", text: `Fan interest ${a.value.toFixed(2)} on Qloo's 0–1 scale; the usual here is ${row.reference.affinity.toFixed(2)}, the average of ${row.reference.lookalikes} yardstick games.` }));
    } else if (a.status === "value") {
      qloo.push(h("p", { class: "panel-stat" }, h("strong", { text: a.value.toFixed(2) }), ` fan interest on Qloo's 0–1 scale${from(a)}`));
      qloo.push(h("p", { class: "help", text: r.reason }));
    } else qloo.push(h("p", { class: "panel-stat" }, a.reason));
    qloo.push(exact("The exact numbers, per game",
      h("div", { class: "table-wrap" }, h("table", { class: "mini-table" },
        h("caption", { class: "visually-hidden", text: `Qloo data per game like yours in ${name}` }),
        h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Game" }), h("th", { scope: "col", text: "Fan interest" }),
          h("th", { scope: "col", text: "vs usual" }), h("th", { scope: "col", text: "Map squares" }),
          h("th", { scope: "col", text: "Qloo activity" }))),
        h("tbody", {}, lookalikeRows(cc)))),
      h("p", { class: "help", text: "Fan interest is Qloo's affinity score (0 to 1). “vs usual” is the exact ratio (×1.10 means 10% more fans than usual). Map squares are Qloo's areas, about 156 km wide, in this country. Qloo activity (popularity) is how much activity the game has in them: it weights the average and is not a player count." })));
  }

  // languages: Babel's mapping, and other official languages (display only)
  const langs = [h("h4", {}, "Language ", source("Reference data"))];
  const model = row.model_language;
  const others = row.official_languages.filter((l) => l !== model);
  if (model) {
    const x = langRow(model);
    const spread = v.map.languages[model].countries;
    langs.push(h("p", {}, `Babel counts ${name} for `, h("strong", { text: LANG[model] }),
      spread.length > 1 ? `, one of ${spread.length} countries in that language's score, weighted by population (${name} ${row.population_m}M people; the others: ${listText(spread.filter((c) => c !== cc).map((c) => `${nameOf(c)} ${v.map.languages[model].population_m[c]}M`))}).`
        : ", the only country in that language's score."),
    h("div", { class: "lang-card" },
      h("span", { class: `group-tag group-${v.m.groupOf[model]}`, text: GROUP_LABEL[v.m.groupOf[model]] }),
      h("span", { text: ` ${pct(x.estimated_share)} of your likely non-English players (estimate) · full game ${fmtUsd.format(x.cost_full)}` }),
      h("div", { class: "lang-actions" },
        h("button", { type: "button", class: "button button-secondary button-small", onclick: (e) => openWhy(model, e.currentTarget) }, "Why this recommendation?"),
        h("button", { type: "button", class: "link-button", onclick: () => selectLanguage(model, { focus: true }) }, `All ${LANG[model]} countries`))));
    if (others.length) {
      langs.push(h("p", { class: "help", text: `${listText(others.map((l) => LANG[l]))} ${others.length > 1 ? "are" : "is"} also official here, but Babel counts ${name} only for ${LANG[model]} (the same rule Babel was tested with).` }));
    }
  } else if (others.length) {
    langs.push(h("p", {}, `${listText(others.map((l) => LANG[l]))} ${others.length > 1 ? "are" : "is"} official here, but Babel's score for ${others.length > 1 ? "them uses" : "it uses"} other countries: `,
      others.map((l, i) => [i ? "; " : "", `${LANG[l]}: ${listText(v.map.languages[l].countries.map((c) => nameOf(c)))}`]), ". Fans here still show on the map."));
  } else {
    langs.push(h("p", { class: "muted", text: "None of Babel's 14 languages is official here, so this country only shows Qloo fan data." }));
  }

  const market = marketFor(cc);
  const audience = v.notes?.audience?.status === "ok"
    ? h("p", { class: "help", text: "Who these fans are (age and gender) is measured worldwide, not per country: see “Who the fans are” below." }) : null;
  return [...out, h("div", { class: "panel-block" }, qloo), h("div", { class: "panel-block" }, langs),
    market ? marketBlock(market) : null, audience].filter(Boolean);
}

function languagePanel(code) {
  const x = langRow(code);
  const lang = v.map?.languages?.[code];
  const group = v.m.groupOf[code];
  const conf = confidence(x, usable().length);
  const adj = adjustment(code);
  const out = [back(),
    h("h3", { id: "panel-title", class: "panel-title", tabindex: "-1", text: LANG[code] }),
    h("span", { class: `group-tag group-${group}`, text: GROUP_LABEL[group] }),
    h("p", { class: "panel-stat" }, h("strong", { text: pct(x.estimated_share) }), " of your likely non-English players ", source("Babel estimate")),
    h("p", { class: "help", title: `Qloo adjustment ${adj.exact}${conf.range ? `; per game ${conf.range}` : ""}`,
      text: `Qloo: ${adj.text}. ${conf.text}.` }),
    h("p", { class: "help", text: `Full game ${fmtUsd.format(x.cost_full)}, store page only ${fmtUsd.format(x.cost_store_page)} (estimates).` }),
    h("p", { class: "lang-reason", text: shortReason(code, group) }),
    h("button", { type: "button", class: "button button-secondary button-small", onclick: (e) => openWhy(code, e.currentTarget) }, "Why this recommendation?")];
  if (lang) {
    const counted = lang.countries;
    const extra = lang.official_in.filter((c) => !counted.includes(c));
    const block = [h("h4", {}, "Countries ", source("Reference data"))];
    if (LANGUAGE_NOTES[code]) block.push(h("p", { class: "help", text: LANGUAGE_NOTES[code] }));
    block.push(h("p", { text: counted.length > 1
      ? `Babel's ${LANG[code]} score uses ${counted.length} countries, each weighted by its population:`
      : `Babel's ${LANG[code]} score uses one country:` }));
    block.push(h("ul", { class: "pill-list" }, counted.map((cc) => {
      const a = countryValue(v.m, "affinity", cc);
      return h("li", {}, h("button", { type: "button", class: "pill", onclick: () => selectCountry(cc, { focus: true, zoom: true }) },
        `${nameOf(cc)} · ${lang.population_m[cc]}M people`, a.status === "value" ? ` · fan interest ${a.value.toFixed(2)}` : " · no Qloo score"));
    })));
    if (extra.length) {
      block.push(h("p", { class: "help", text: `Also official in ${plural(extra.length, "more country", "more countries")} (dashed outline on the map) that the score doesn't count: ${listText(extra.map((cc) => nameOf(cc)))}.` }));
    }
    out.push(h("div", { class: "panel-block" }, block));
  }
  const market = (v.notes?.markets || []).find((m) => m.language === code && Object.values(m.also_loves).some((r) => r.status === "ok"));
  if (market) out.push(marketBlock(market));
  return out;
}

// ---------------------------------------------------------------- the plan and its budget
function setupBudget() {
  const input = $("#plan-budget");
  const range = $("#plan-budget-range");
  const all = v.plan.languages.filter((x) => x.group !== "already_supported").reduce((s, x) => s + x.cost_full, 0);
  range.max = String(Math.max(1000, Math.ceil(Math.max(all, v.original) / 1000) * 1000));
  input.value = String(v.original);
  range.value = String(v.original);
  const can = Boolean(v.plan.allocation);
  input.disabled = !can;
  range.disabled = !can;
  input.oninput = () => { if (input.value !== "") range.value = String(Math.min(Number(range.max), Number(input.value))); queueFit(); };
  range.oninput = () => { input.value = range.value; queueFit(); };
  $("#budget-status").textContent = can ? "" : "Run the plan again to change the budget here.";
  renderBudgetStats();
}

function queueFit() {
  clearTimeout(v.fitTimer);
  v.fitTimer = setTimeout(fit, 140);
}

async function fit() {
  const raw = $("#plan-budget").value;
  const budget = Number(raw);
  if (raw === "" || !Number.isFinite(budget) || budget < 0 || budget > 10000000) {
    $("#budget-status").textContent = "Enter a budget from $0 to $10,000,000.";
    $("#plan-budget").setAttribute("aria-invalid", "true");
    return;
  }
  $("#plan-budget").setAttribute("aria-invalid", "false");
  v.fitController?.abort();
  const controller = new AbortController();
  v.fitController = controller;
  $("#plan-groups").setAttribute("aria-busy", "true");
  let r;
  try {
    r = await api("POST", "/fit-budget", { budget, allocation: v.plan.allocation }, controller.signal);
  } catch {
    return;  // a newer budget replaced this one
  }
  if (controller !== v.fitController) return;
  $("#plan-groups").removeAttribute("aria-busy");
  if (!r.ok) {
    $("#budget-status").textContent = `${errorText(r)} The plan below is still for ${fmtUsd.format(v.fit.costs.budget)}.`;
    return;
  }
  v.fit = r.data;
  v.m = model(v.map, v.plan, v.fit.groups);
  $("#budget-status").textContent = `Updated for ${fmtUsd.format(budget)}: ${headline(v.fit.status, v.fit.groups, v.fit.costs).title}`;
  renderHead();
  renderPlan();
  renderVersus();
  renderGlance();
  renderEvidence();
  repaint();
}

function renderBudgetStats() {
  const c = v.fit.costs;
  const cov = v.fit.estimated_coverage;
  const stat = (label, value, cls = "") => h("div", {}, h("dt", { text: label }), h("dd", { class: cls, text: value }));
  $("#budget-stats").replaceChildren(stat("Estimated cost", fmtUsd.format(c.total)), stat("Left over", fmtUsd.format(c.unspent)),
    stat("Full translations reach (estimate)", `${pct(cov.translate_game, 0)} of your likely non-English players`, "is-estimate"));
}

/** Why a language is in its group, in a sentence, from the plan's own numbers (the optimizer's wording is in "Why?"). */
function shortReason(code, group) {
  const x = langRow(code);
  if (group === "translate_game") return "Part of the mix of full translations that reaches the most likely players within your budget.";
  if (group === "store_page_only") {
    return `The full game (${fmtUsd.format(x.cost_full)}) didn't fit the budget; translating just the store page is a cheap way to test this market.`;
  }
  if (group === "already_supported") return "Your game already has this language.";
  const share = v.plan.allocation?.shares?.[code] ?? x.estimated_share;
  return share < minShare() ? `Too few likely players: under ${minText()}.`
    : `Not enough budget left for its store page (${fmtUsd.format(x.cost_store_page)}).`;
}

function languageItem(code, group) {
  const x = langRow(code);
  const conf = confidence(x, usable().length);
  const adj = adjustment(code);
  const cost = group === "store_page_only" ? `Store page ${fmtUsd.format(x.cost_store_page)}`
    : group === "translate_game" ? `Full game ${fmtUsd.format(x.cost_full)}`
      : `Full game ${fmtUsd.format(x.cost_full)}, store page ${fmtUsd.format(x.cost_store_page)}`;
  return h("li", { class: "lang-row", "data-lang": code },
    h("div", { class: "lang-top" }, h("span", { class: "lang-name", text: LANG[code] }),
      h("span", { class: "lang-share", title: "Share of your likely non-English players (estimate)", text: pct(x.estimated_share) })),
    h("p", { class: "lang-cost" }, h("strong", { text: cost })),
    h("p", { class: "lang-meta", title: `${cap(adj.text)} (${adj.exact}).` }, "Qloo adjustment: ", h("strong", { text: adj.short })),
    h("p", { class: `lang-conf conf-${conf.level}`, title: conf.range ? `Qloo adjustment per game: ${conf.range}` : null, text: conf.text }),
    plus(`More about ${LANG[code]}`,
      h("p", { class: "lang-reason", text: shortReason(code, group) }),
      h("div", { class: "lang-actions" },
        h("button", { type: "button", class: "button button-secondary button-small", "aria-label": `Why this recommendation for ${LANG[code]}?`,
          onclick: (e) => openWhy(code, e.currentTarget) }, "Why?"),
        h("button", { type: "button", class: "link-button", "aria-label": `Show ${LANG[code]} on the map`,
          onclick: () => selectLanguage(code, { focus: true, scroll: true }) }, "On the map"))));
}

function renderPlan() {
  const g = v.fit.groups;
  const blurb = { translate_game: "The best mix of full translations your budget can pay for.",
    store_page_only: "A cheap test: translate just the Steam store page, with the budget that is left.",
    skip: `Too few likely players (under ${minText()}) or no budget left, for now.` };
  const total = { translate_game: v.fit.costs.translate_game, store_page_only: v.fit.costs.store_page_only };
  $("#plan-groups").replaceChildren(
    ...GROUP_ORDER.map((group) => h("section", { class: `plan-group plan-group-${group}`, "aria-labelledby": `pg-${group}` },
      h("div", { class: "plan-group-head" },
        h("h3", { id: `pg-${group}`, text: GROUP_LABEL[group] }),
        h("p", { class: "help", text: blurb[group] }),
        h("span", { class: "plan-group-count", text: group in total
          ? `${plural(g[group].length, "language")} · ${fmtUsd.format(total[group])}` : plural(g[group].length, "language") })),
      g[group].length ? h("ul", { class: "lang-list" }, g[group].map((code) => languageItem(code, group)))
        : h("p", { class: "muted plan-empty", text: "None at this budget." }))));
  $("#plan-supported").textContent = g.already_supported.length
    ? `Already in your game: ${listText(g.already_supported.map((c) => LANG[c]))}.` : "";
  $("#budget-reset")?.remove();
  if (budgetChanged()) {
    $("#budget-status").after(h("button", { type: "button", id: "budget-reset", class: "link-button",
      onclick: () => { $("#plan-budget").value = String(v.original); $("#plan-budget-range").value = String(v.original); fit(); } },
    `Back to ${fmtUsd.format(v.original)}`));
  }
  if (v.fit.message) {  // the engine's note on the budget; one is re-worded plainly (its wording stays as the tooltip)
    $("#budget-status").textContent = v.fit.status === "nothing_to_translate"
      ? "Every language is already in your game or has too few likely players." : v.fit.message;
  }
  $("#budget-status").title = v.fit.message || "";
  renderBudgetStats();
}

// ---------------------------------------------------------------- Babel vs the usual list
/** Why Babel ranks a language where it does, from the row's numbers (the server's wording is the cell's tooltip). */
function versusWhy(r) {
  const has = langRow(r.code).lookalikes_with_data > 0;
  const adj = qlooAdjustment(r.qloo_lift, has);
  const moved = has && adj.short !== "about average";
  const fans = !has ? "No Qloo data" : moved ? `Fans ${adj.short}` : "Fans about average";
  const way = r.babel_rank < r.baseline_rank ? "up" : "down";
  if (r.babel_rank === r.baseline_rank) return `${fans}: stays ${ordinal(r.babel_rank)}.`;
  return moved && (r.qloo_lift > 1) === (r.babel_rank < r.baseline_rank) ? `${fans}: ${way} to ${ordinal(r.babel_rank)}.`
    : `${fans}; others moved: ${way} to ${ordinal(r.babel_rank)}.`;
}

function renderVersus() {
  if (!v.vs) { $(".versus").hidden = true; return; }
  $(".versus").hidden = false;
  const names = (codes) => listText(codes.map((c) => LANG[c]));
  $("#versus-about").textContent = `The usual list starts with ${names(v.vs.generic_top3)} for every game: it's the order many `
    + "developers copy. Babel starts from what English-only indie games usually see (the share of their non-English Steam "
    + `reviews in each language) and adjusts it with Qloo's fan maps of games like yours. For this game, Babel starts with ${names(v.vs.babel_top3)}.`;
  const change = (r) => (r.places > 0 ? ["up", `▲ ${r.places}`, `${r.places} place${r.places === 1 ? "" : "s"} higher than on the usual list`]
    : r.places < 0 ? ["down", `▼ ${-r.places}`, `${-r.places} place${r.places === -1 ? "" : "s"} lower than on the usual list`]
      : ["same", "=", "same place as on the usual list"]);
  $("#versus-table").replaceChildren(
    h("caption", { class: "visually-hidden", text: "Babel's ranking compared with the usual list" }),
    h("thead", {}, h("tr", {}, ["Babel", "Language", "Usual list", "Change", "Share (estimate)", "Qloo adjustment", "Plan now", "Why the difference"]
      .map((t) => h("th", { scope: "col", text: t })))),
    h("tbody", {}, v.vs.rows.map((r) => {
      const [cls, text, label] = change(r);
      const group = v.m.groupOf[r.code];
      const adj = adjustment(r.code);
      return h("tr", {},
        h("td", { class: "num", "data-label": "Babel", text: `#${r.babel_rank}` }),
        h("th", { scope: "row", text: r.language }),
        h("td", { class: "num", "data-label": "Usual list", text: `#${r.generic_rank}` }),
        h("td", { "data-label": "Change" }, h("span", { class: `delta delta-${cls}`, "aria-label": label, text })),
        h("td", { class: "num", "data-label": "Share (estimate)", text: pct(r.estimated_share) }),
        h("td", { class: "num", "data-label": "Qloo adjustment", title: `${cap(adj.text)} (${adj.exact}).`, text: adj.short }),
        h("td", { "data-label": "Plan now" }, h("span", { class: `group-tag group-${group}`, text: GROUP_LABEL[group] })),
        h("td", { class: "why-cell", "data-label": "Why", title: r.why, text: versusWhy(r) }));
    })));
  $("#versus-caveat").textContent = "The usual share comes from Steam reviews of English-only games, so it under-counts "
    + "players who only buy translated games (especially Chinese, Japanese and Korean speakers).";
  $("#versus-caveat").title = v.vs.caveat;
}

// ---------------------------------------------------------------- the plan at a glance (static/charts.js)
function renderGlance() {
  renderCharts($("#plan-charts"), { plan: v.plan, groups: v.fit.groups, groupOf: v.m.groupOf, versus: v.vs,
    costs: v.fit.costs, coverage: v.fit.estimated_coverage }, { onLanguage: (code) => selectLanguage(code, { focus: true, scroll: true }) });
}

// ---------------------------------------------------------------- evidence cards
function card(title, kind, ...body) {
  return h("article", { class: "evidence-card-item" }, h("h3", {}, title, " ", kind ? source(kind) : null), ...body);
}

/** Why a market's country was chosen, plainly (the server's reason is its tooltip). */
function choiceText(choice) {
  if (choice.kind === "qloo_measured") return "Chosen because most of the Qloo fan activity for games like yours in this language's countries is here.";
  if (choice.reason.startsWith("Most populous")) return "The language's most populous country (Qloo had no fan data to choose by).";
  return choice.reason;
}

function renderEvidence() {
  const cards = [];
  const looks = v.map?.lookalikes || [...v.plan.lookalikes.used.map((x) => ({ ...x, usable: true })),
    ...v.plan.lookalikes.rejected.map((x) => ({ ...x, usable: false }))];
  cards.push(card("Games like yours", "Qloo data",
    h("p", { class: "help", text: "Only games with real Qloo fan data count. Games Qloo doesn't know, or has no real data for, are listed here but never used." }),
    h("ul", { class: "look-list" }, looks.map((x) => {
      const [cls, text] = STATUS_BADGE[x.status] || ["badge-bad", `Not used: ${x.status}`];
      return h("li", {}, h("div", { class: "look-top" }, h("strong", { text: x.name || `Steam ${x.appid}` }), badge(cls, text, x.reason)),
        x.usable && x.countries_with_score != null ? h("span", { class: "help", text: `Qloo has a score for ${x.countries_with_score} countries` }) : null);
    }))));

  const exp = v.explanation;
  if (exp) {
    cards.push(card("Explanation", null,
      budgetChanged() ? h("p", { class: "note", text: `Written for the ${fmtUsd.format(v.original)} plan; the budget has changed since.` }) : null,
      h("p", { class: "explain-summary", text: exp.summary }),
      exp.points.length ? plus("More of the explanation",
        h("ul", { class: "explain-points" }, exp.points.map((pt) => h("li", { text: pt.text })))) : null));
  }

  const aud = v.notes?.audience;
  if (aud?.status === "ok") {
    const max = Math.max(0.01, ...aud.age.map((a) => Math.abs(a.skew)), ...Object.values(aud.gender).map(Math.abs));
    const bar = (label, value) => {
      const fill = h("span", { class: `skew-fill ${value < 0 ? "is-neg" : ""}` });
      fill.style.width = `${(Math.abs(value) / max) * 50}%`;
      return h("li", { class: "skew-row" }, h("span", { class: "skew-label", text: label }),
        h("span", { class: "skew-bar", role: "img", "aria-label": `${label}: ${value > 0 ? "+" : ""}${value.toFixed(2)}` }, fill),
        h("span", { class: "skew-value", text: `${value > 0 ? "+" : ""}${value.toFixed(2)}` }));
    };
    cards.push(card("Who the fans are", "Qloo data",
      h("p", { class: "help", title: aud.meaning, text: "How fans of games like yours differ from Qloo's average audience: a bar to the right means more of them than average, to the left fewer. It describes groups of fans, never individuals, and it is not used in the language scores." }),
      h("ul", { class: "skew-list", "aria-label": "Age" }, aud.age.map((a) => bar(a.band, a.skew))),
      Object.keys(aud.gender).length ? h("ul", { class: "skew-list", "aria-label": "Gender" },
        Object.entries(aud.gender).map(([g, val]) => bar(g, val))) : null));
  }

  const markets = (v.notes?.markets || []).filter((m) => Object.values(m.also_loves).some((r) => r.status === "ok"));
  if (markets.length) {
    cards.push(card("What these fans also like, by market", "Qloo data",
      h("p", { class: "help", text: "Films and music popular in each market, sorted by how much fans of games like yours like them. Background for marketing, not what any one player likes." }),
      budgetChanged() ? h("p", { class: "note", text: `Markets were chosen for the ${fmtUsd.format(v.original)} plan.` }) : null,
      ...markets.map((m) => h("div", { class: "market" },
        h("h4", {}, h("button", { type: "button", class: "link-button", onclick: () => { selectCountry(m.country, { focus: true, zoom: true }); $("#explore-title").scrollIntoView({ block: "start", behavior: scrollMode() }); } },
          `${m.language_name} → ${m.country_name}`)),
        h("p", { class: "help", title: m.country_choice.reason, text: choiceText(m.country_choice) }),
        Object.entries(m.also_loves).filter(([, r]) => r.status === "ok").map(([d, r]) =>
          h("p", { class: "loves-line" }, h("span", { class: "loves-label", text: d === "films" ? "Films" : "Music" }), r.items.map((i) => i.name).join(" · "))),
        m.note?.status === "ok" ? h("p", { class: "llm-note", text: m.note.text }) : null))));
  } else if (v.notes) {
    cards.push(card("What these fans also like, by market", null, h("p", { class: "muted", text: "Qloo had no market data for this plan's markets, so none are shown." })));
  }

  $("#evidence-grid").replaceChildren(...cards);
}

// ---------------------------------------------------------------- how the map is made
function renderMethod() {
  const m = v.map;
  const tech = $("#map-method-tech");
  if (!m) {
    $("#map-method").replaceChildren(h("li", { text: "No map data for this plan." }));
    tech.replaceChildren();
    return;
  }
  const ref = m.reference || {};
  const items = [
    "Fan interest: for each game like yours, Qloo scores how strongly its fans gather in each map square (about 156 km "
      + "wide). Babel averages the squares in each country, giving busier squares more weight, then averages the games "
      + `like yours. Countries with fewer than ${m.min_cells} squares get no score.`,
    `Fans compared with usual: a country's fan interest divided by the usual there, the average for ${ref.lookalikes || "the"} `
      + `yardstick games from Babel's tests${ref.min_lookalikes ? ` (shown only where at least ${ref.min_lookalikes} of them have a score)` : ""}.`,
    "Qloo activity (Qloo calls it popularity, 0 to 1): how much activity a game has in a square compared with other "
      + "squares. It only weights the average; it is not a player count.",
    "Share of likely players: Babel's estimate for each language (the usual share × the Qloo adjustment). It belongs to "
      + "the language, so it is drawn on every country Babel counts for that language.",
    "Country outlines: Natural Earth 1:110m (public domain). Countries are coloured as whole shapes: Qloo's squares are "
      + "about 156 km wide, so nothing finer is implied.",
  ];
  $("#map-method").replaceChildren(...items.map((t) => h("li", { text: t })));
  tech.replaceChildren(exact("Technical notes", h("ul", { class: "method-list" },
    [m.method.affinity, m.method.relative, m.method.popularity, m.method.demand,
      `Sources: ${Object.values(m.sources).join("; ")}.`].map((t) => h("li", { text: t })))));
}

// ---------------------------------------------------------------- Why this recommendation?
function step(n, title, ...body) {
  return h("li", { class: "why-step" }, h("span", { class: "why-num", "aria-hidden": "true", text: String(n) }),
    h("div", {}, h("h3", { text: title }), ...body));
}

const EVIDENCE_LEVEL = {
  normal: (n) => `${plural(n, "game")} like yours with Qloo fan data, as usual`,
  low: (n) => `only ${plural(n, "game")} like yours with Qloo fan data, fewer than usual`,
  none: () => "no game like yours has Qloo fan data",
};

function openWhy(code, opener) {
  const x = langRow(code);
  const lang = v.map?.languages?.[code];
  const c = v.costs[code];
  const group = v.m.groupOf[code];
  const conf = confidence(x, usable().length);
  const looks = usable();
  const adj = adjustment(code);
  const steps = [];
  steps.push(step(1, `The usual share: ${pct(x.baseline_share)}`, source("Steam reviews"),
    h("p", { text: `On average, English-only indie games get ${pct(x.baseline_share)} of their non-English Steam reviews in ${LANG[code]}. That is Babel's starting point.` })));
  if (lang && looks.length) {
    steps.push(step(2, `Qloo adjustment: ${adj.short}`, source("Qloo data"),
      h("p", { text: `Babel reads Qloo's fan maps of ${listText(looks.map((g) => g.name))} in the ${plural(lang.countries.length, "country", "countries")} where ${LANG[code]} is counted (${listText(lang.countries.map((cc) => nameOf(cc)))}), weighting each country by its population, and compares them with the usual.` }),
      h("p", { text: `Result: ${adj.text}.` })));
  } else {
    steps.push(step(2, "Qloo adjustment: none", source("Qloo data"),
      h("p", { text: "Qloo has no real fan data for any game like yours, so Babel keeps the usual share." })));
  }
  if (lang) {
    steps.push(step(3, `Share of your likely non-English players: ${pct(lang.estimated_share)}`, source("Babel estimate"),
      h("p", { text: "Babel multiplies the usual share by the Qloo adjustment, then rescales the 14 languages so they add up to 100%." }),));
  }
  if (c) {
    steps.push(step(4, `Cost: ${fmtUsd.format(c.cost_full)} for the whole game`, source("Babel estimate"),
      h("p", { text: `${fmtInt.format(c.game_words + c.store_page_words)} words (your game plus a ${fmtInt.format(c.store_page_words)}-word store page) at ${fmtUsd2.format(c.rate_per_word)} a word${c.min_fee_applies ? `, raised to the ${fmtUsd.format(c.min_fee)} minimum fee` : ""}, plus ${Math.round(c.qa_overhead * 100)}% for review and testing. Just the store page: ${fmtUsd.format(c.cost_store_page)}.` }),));
  }
  steps.push(step(5, `Budget decision: ${GROUP_LABEL[group]}`, source("Babel plan"),
    h("p", { text: shortReason(code, group) })));
  steps.push(step(6, "How sure is this?", null,
    h("p", { text: `${conf.text}. For the whole plan: ${EVIDENCE_LEVEL[v.plan.lookalikes.evidence_level]?.(v.plan.lookalikes.used.length) || v.plan.lookalikes.evidence_level}.` }),
    conf.level === "mixed" ? h("p", { class: "help", text: "Some games like yours have more fans than usual where it's spoken and some fewer, so this estimate is less certain." }) : null));
  const cites = (v.explanation?.points || []).filter((pt) => pt.evidence.includes(`lang:${code}`));
  $("#why-title").textContent = `Why ${LANG[code]}: ${GROUP_LABEL[group].toLowerCase()}`;
  $("#why-body").replaceChildren(
    h("ol", { class: "why-steps" }, steps),
    cites.length ? h("div", { class: "why-cites" }, h("h3", { text: "From the explanation" }),
      cites.map((pt) => h("blockquote", { text: pt.text }))) : null);
  showDialog(opener);
}

function showDialog(opener) {
  const dialog = $("#why-dialog");
  dialog.onclose = () => opener?.isConnected && opener.focus();
  dialog.showModal();
  $("#why-body").scrollTop = 0;
}

/** The open plan as the report needs it (read-only): the server's result, the current budget fit, the map view. */
export function currentPlan() {
  return { res: v.res, plan: v.plan, fit: v.fit, map: v.map, versus: v.vs, costs: v.costs, notes: v.notes,
    explanation: v.explanation, index: v.index, original: v.original, metric: v.metric, lookalike: v.lookalike,
    model: v.m, get mapSvg() { return reportMap(); }, worldReady: v.worldState === "ready", country: v.country,
    language: v.language };
}

/** What the assistant and the tour may do on the open Plan screen (app.js registers them; arguments are checked). */
export const planActions = {
  set_budget: ({ budget }) => {
    if (!Number.isFinite(budget) || budget < 0 || budget > 10000000) throw new Error("The budget must be $0 to $10,000,000.");
    $("#plan-budget").value = String(budget);
    $("#plan-budget-range").value = String(Math.min(Number($("#plan-budget-range").max), budget));
    $(".localize").scrollIntoView({ block: "start", behavior: scrollMode() });
    clearTimeout(v.fitTimer);
    return fit();
  },
  show_country: ({ country }) => {
    if (!v.map?.countries?.[country] && !v.worldMap?.has(country)) throw new Error(`No data for country "${country}".`);
    $("#explore-title").scrollIntoView({ block: "start", behavior: scrollMode() });
    selectCountry(country, { zoom: true });
  },
  show_language: ({ language }) => {
    if (!LANG[language]) throw new Error(`"${language}" is not one of Babel's 14 languages.`);
    selectLanguage(language, { scroll: true });
  },
  set_metric: ({ metric }) => {
    if (!METRICS[metric]) throw new Error(`Unknown map view "${metric}".`);
    const input = $$('input[name="metric"]').find((i) => i.value === metric);
    input.checked = true;
    input.dispatchEvent(new Event("change"));
    $("#explore-title").scrollIntoView({ block: "start", behavior: scrollMode() });
  },
  open_why: ({ language }) => {
    if (!LANG[language]) throw new Error(`"${language}" is not one of Babel's 14 languages.`);
    openWhy(language, null);
  },
  reset_map: () => backToWorld(),
};

export function wirePlanScreen({ onBack, onTrace }) {
  $("#plan-change").addEventListener("click", () => onBack());
  $("#plan-trace").addEventListener("click", () => onTrace());
  document.addEventListener("babel:theme", retheme);
  window.addEventListener("beforeprint", () => { printing = true; retheme(); });
  window.addEventListener("afterprint", () => { printing = false; retheme(); });
}
