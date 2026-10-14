// The report (TASK 11): the open plan as a print-ready A4 document (one or two pages, set for easy reading), built from
// plan.js currentPlan() (the server's result, the current budget fit and the world map on screen). Every number comes
// from that snapshot; this file selects and formats. Text from the server is inserted as text, never as HTML.
// Print layout: report.css.

import { $, countryName, fmtInt, fmtUsd, GROUP_LABEL, h, LANG, listText, pct } from "./ui.js";
import { confidence, countryList, formatValue, headline, legendItems, lookalikeEntry, METRICS, qlooAdjustment }
  from "./mapdata.js";

const GROUP_ORDER = ["translate_game", "store_page_only", "skip"];
const BLURB = { translate_game: "Fits your budget and reaches the most likely players (estimate).",
  store_page_only: "The whole game didn't fit; a translated store page tests the market with what's left.",
  skip: "Too few likely players, or over the budget, for now." };
const STATUS = { valid: ["badge-ok", "Used: real Qloo fan data"],  // as the Plan screen's evidence cards say it
  "default map": ["badge-warn", "Not used: Qloo has no real data"], "not in Qloo": ["badge-warn", "Not used: Qloo doesn't know it"],
  "no heatmap": ["badge-warn", "Not used: no Qloo fan map"] };
const UNUSED = { "default map": "Qloo has no real fan data for it", "not in Qloo": "Qloo doesn't know it",
  "no heatmap": "Qloo has no fan map for it" };
const ESTIMATE_NOTE = "Costs and shares are estimates, not quotes or sales.";
const LOVES_SHOWN = 3;  // "also loves" titles per list: highlights (the Plan screen has them all)
const fmtDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" });

const page = { title: null, saved: null };  // the document title while printing: the default "Save as PDF" file name

/** Show the report for a plan snapshot (plan.js currentPlan()). opts = {onBack}. */
export function openReport(snapshot, opts = {}) {
  const root = $("#view-report");
  const s = snapshot?.res && snapshot.plan && snapshot.fit ? withContext(snapshot) : null;
  const sheet = s ? sheetFor(s) : h("article", { class: "report-sheet" },
    h("h1", { id: "report-title", class: "r-title", tabindex: "-1", text: "No plan to report yet" }),
    h("p", { text: "Run a plan first, then export it from the Plan screen." }));
  root.replaceChildren(h("div", { class: "report" }, toolbar(opts.onBack), sheet));
  page.title = s ? `Babel report - ${s.plan.game.name || "Your game"} - ${s.date}` : null;
  $("#report-title").focus();
}

function withContext(s) {
  return { ...s, date: fmtDate.format(new Date()), changed: s.fit.costs.budget !== s.original,
    row: (code) => s.model.languages[code], usable: s.model.usable };
}

window.addEventListener("beforeprint", () => {
  if (document.body.dataset.view !== "report" || !page.title) return;
  page.saved = document.title;
  document.title = page.title;
});
window.addEventListener("afterprint", () => {
  if (page.saved !== null) document.title = page.saved;
  page.saved = null;
});

// ---------------------------------------------------------------- small pieces
function section(cls, id, title, ...body) {
  return h("section", { class: `r-section ${cls}`, "aria-labelledby": id },
    h("div", { class: "r-section-head" }, h("h2", { id, text: title })), ...body);
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const names = (codes) => listText(codes.map((c) => LANG[c] || c));
const signed = (x) => `${x > 0 ? "+" : ""}${x.toFixed(2)}`;

function toolbar(onBack) {
  return h("div", { class: "report-toolbar" },
    h("button", { type: "button", class: "button button-secondary", onclick: () => onBack?.() },
      h("span", { "aria-hidden": "true", text: "← " }), "Back to the plan"),
    h("p", { class: "help", text: "In the print dialog, choose Save as PDF to share it." }),
    h("button", { type: "button", class: "button button-primary", onclick: () => window.print() },
      "Print or save as PDF"));
}

function sheetFor(s) {
  return h("article", { class: "report-sheet", "aria-labelledby": "report-title" },
    header(s), inputs(s), alerts(s), planSection(s), explanation(s), mapSection(s), lookalikes(s), markets(s),
    footer(s));
}

// ---------------------------------------------------------------- header and inputs
function header(s) {
  const p = s.plan;
  const head = headline(s.fit.status, s.fit.groups, s.fit.costs);
  const level = p.lookalikes.evidence_level;
  const n = p.lookalikes.used.length;
  const facts = [
    ["Date", s.date],
    ["Plan ID", s.res.plan_id || "not saved"],
    p.game.appid ? ["Steam app", String(p.game.appid)] : null,
    ["Evidence", level === "none" ? "Qloo has no real fan data for games like this: the usual share only"
      : `${plural(n, "game")} like yours with Qloo fan data${level === "low" ? " (little evidence)" : ""}`],
  ].filter(Boolean);
  const logo = $(".logo .logo-mark")?.cloneNode(true);
  logo?.setAttribute("class", "logo-mark r-logo");
  return h("header", { class: "r-head" },
    h("div", { class: "r-brand" }, logo, h("span", { class: "r-brand-name", text: "Babel" }),
      h("span", { class: "r-brand-doc", text: "Translation plan" })),
    h("div", { class: "r-head-main" },
      h("div", {},
        h("h1", { id: "report-title", class: "r-title", tabindex: "-1", text: p.game.name || "Your game" }),
        h("p", { class: "r-headline", text: head.title })),
      h("dl", { class: "r-meta" }, facts.map(([k, v]) => h("div", {}, h("dt", { text: k }), h("dd", { text: v }))))));
}

function inputs(s) {
  const p = s.plan;
  const c = s.fit.costs;
  const cov = s.fit.estimated_coverage;
  const cells = [
    ["Words to translate", fmtInt.format(p.inputs.word_count),
      `+ a ${fmtInt.format(p.rates.store_page_words)}-word store page`],
    ["Budget", fmtUsd.format(s.original), s.changed ? "When the plan was run" : "As you entered it"],
    s.changed ? ["Current budget", fmtUsd.format(c.budget), "Moved on the Plan screen", "is-changed"] : null,
    ["Estimated cost", fmtUsd.format(c.total), "An estimate, not a quote"],
    ["Left over", fmtUsd.format(c.unspent), "Of the budget"],
    ["Full translations reach", pct(cov.translate_game), "Of likely non-English players (est.)"],
    ["Store pages reach", pct(cov.store_page_only), "A test: the game stays in English"],
  ].filter(Boolean);
  return h("dl", { class: "r-inputs", "aria-label": "Inputs and totals" },
    cells.map(([k, v, note, cls]) => h("div", { class: cls || null },
      h("dt", { text: k }), h("dd", { text: v }), h("dd", { class: "r-cell-note", text: note }))));
}

function alerts(s) {
  const out = [];
  if (s.changed) {
    out.push(`This report is for the current budget, ${fmtUsd.format(s.fit.costs.budget)}, set on the Plan screen. `
      + `The explanation and market notes were written for the ${fmtUsd.format(s.original)} plan.`);
  }
  if (s.fit.message) out.push(s.fit.message);
  return out.length ? h("div", { class: "r-alerts" }, out.map((t) => h("p", { class: "r-alert", text: t }))) : null;
}

// ---------------------------------------------------------------- the plan
function planSection(s) {
  const supported = s.fit.groups.already_supported;
  const vs = s.versus;
  return section("r-plan", "r-plan-title", "The plan",
    h("div", { class: "table-wrap" }, h("table", { class: "r-table" },
      h("caption", { class: "visually-hidden",
        text: "Every target language by group, with its share of your likely players, Qloo adjustment, cost and why" }),
      h("thead", {}, h("tr", {}, ["#", "Language", "Share (est.)", "Qloo", "Cost (est.)", "Why"]
        .map((t, i) => h("th", { scope: "col", class: i === 0 || i === 2 ? "num" : null, text: t })))),
      GROUP_ORDER.map((group) => groupBody(s, group)))),
    h("p", { class: "r-key", text: "Share: of your likely non-English players. Qloo: how much more (+) or less (−) "
      + "common fans of games like yours are where the language is spoken." }),
    supported.length || vs ? h("p", { class: "r-versus" },
      supported.length ? `Already in your game: ${names(supported)}. ` : "",
      vs ? `The usual list most developers copy starts with ${names(vs.generic_top3)}; for this game, Babel ranks `
        + `${names(vs.babel_top3)} first.` : "") : null);
}

function groupBody(s, group) {
  const codes = s.fit.groups[group];
  const total = group === "skip" ? "" : ` · ${fmtUsd.format(s.fit.costs[group])}`;
  return h("tbody", { class: `r-group r-group-${group}`, "data-group": group },
    h("tr", { class: "r-group-row" }, h("th", { colspan: "6", scope: "rowgroup" },
      h("span", { class: `group-tag group-${group}`, text: GROUP_LABEL[group] }),
      h("span", { class: "r-group-sum", text: `${plural(codes.length, "language")}${total}` }),
      h("span", { class: "r-group-blurb", text: BLURB[group] }))),
    codes.length ? codes.map((code) => languageRow(s, code, group))
      : h("tr", {}, h("td", { colspan: "6", class: "r-empty", text: "None at this budget." })));
}

function languageRow(s, code, group) {
  const x = s.row(code);
  const conf = confidence(x, s.usable.length);
  const adj = qlooAdjustment(x.qloo_lift, conf.level !== "none");
  const [lo, hi] = x.lift_range || [];
  const cost = group === "store_page_only" ? [fmtUsd.format(x.cost_store_page), " page"]
    : [fmtUsd.format(x.cost_full), " game"];
  return h("tr", { "data-lang": code },
    h("td", { class: "num r-rank", text: String(x.rank) }),
    h("th", { scope: "row", class: "r-lang", text: LANG[code] }),
    h("td", { class: "num r-share", text: pct(x.estimated_share) }),
    h("td", { class: "r-lift" },
      h("span", { class: "r-phone-label", "aria-hidden": "true", text: "Qloo: " }),  // phones hide the header
      h("strong", { text: adj.short }),
      h("span", { class: "visually-hidden", text: `. Exact: ${adj.exact}${conf.range && lo !== hi ? `, ${conf.range}` : ""}. `
        + `${conf.text}.` })),
    h("td", { class: `r-cost${group === "skip" ? " is-muted" : ""}` }, h("strong", { text: cost[0] }), cost[1]),
    h("td", { class: "r-why", title: (group === "translate_game" && s.versus?.rows.find((r) => r.code === code)?.why)
      || s.fit.reasons[code] || null, text: why(s, code, group) }));
}

function ordinal(n) {
  const end = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${end[(v - 20) % 10] || end[v] || end[0]}`;
}

/** A short plain reason per language, from the plan's own numbers (the server's wording is the cell's tooltip). */
function why(s, code, group) {
  const x = s.row(code);
  const r = s.versus?.rows.find((v) => v.code === code);
  if (group === "translate_game") {
    if (!r) return "Best value within your budget.";
    return `Babel ranks it ${ordinal(r.babel_rank)} (usual list: ${ordinal(r.generic_rank)}).`;
  }
  if (group === "store_page_only") return `Full game (${fmtUsd.format(x.cost_full)}) is over budget.`;
  const a = s.plan.allocation;
  if (group === "skip" && a?.min_share != null) {
    return (a.shares?.[code] ?? x.estimated_share) < a.min_share ? `Too few likely players: under ${pct(a.min_share)}.`
      : `Not enough budget left for its store page (${fmtUsd.format(x.cost_store_page)}).`;
  }
  return s.fit.reasons[code];
}

// ---------------------------------------------------------------- the map
function mapSection(s) {
  const metric = METRICS[s.metric] ? s.metric : "plan";
  const spec = METRICS[metric];
  const entry = spec.byLookalike ? lookalikeEntry(s.model, s.lookalike) : null;
  const title = spec.byLookalike ? "Where fans of games like yours are"
    : metric === "plan" ? "The plan on the world map" : "Likely players on the world map";
  const notes = [];
  if (spec.byLookalike && s.map && s.map.status !== "ok") {
    notes.push("Qloo has no real fan data for any game like yours, so this view is empty; the plan uses the usual "
      + "share.");
  } else if (entry && !entry.usable) {
    notes.push(`This view shows ${entry.name} only, which Babel doesn't use (${UNUSED[entry.status] || entry.status}), `
      + "so nothing is drawn.");
  }
  const top = spec.byLookalike && s.map ? countryList(s.model, metric, s.lookalike, (cc) => countryName(cc))
    .filter((r) => r.status === "value").slice(0, 3) : [];
  const highest = top.length ? `Highest: ${top.map((r) => `${r.name} ${formatValue(metric, r.value)}`).join(", ")}.` : "";
  const fansOf = entry ? `fans of ${entry.name} only` : `average of ${plural(s.usable.length, "game")} like yours`;
  return section("r-map", "r-map-title", title,
    h("p", { class: "r-map-view" }, h("strong", { text: spec.label }), ` · ${spec.unit}`,
      spec.byLookalike ? ` · ${fansOf}` : ""),
    h("figure", { class: "r-figure" }, mapPicture(s),
      h("figcaption", { class: "visually-hidden", text: `World map of ${spec.label.toLowerCase()}. ${highest}` })),
    h("ul", { class: "r-legend", "aria-label": `Legend: ${spec.label}` }, legendItems(metric).map((it) => {
      const swatch = h("span", { class: `swatch${it.pattern ? " swatch-hatch" : ""}`, "aria-hidden": "true" });
      if (!it.pattern) swatch.style.background = it.color;  // CSSOM: allowed by the page's CSP
      return h("li", {}, swatch, it.label);
    })),
    notes.map((t) => h("p", { class: "r-alert", text: t })),
    highest ? h("p", { class: "r-help", text: highest }) : null);
}

/** A static copy of the live map: zoom reset, no dimming or outlines, its own hatch pattern id. */
function mapPicture(s) {
  if (!s.map) return placeholder("The world map data could not be built for this plan; the plan itself is unaffected.");
  if (!s.worldReady || !s.mapSvg) {
    return placeholder("The world map was not ready when this report was made (it was still loading or could not "
      + "load). Go back to the plan, wait for the map, then export the report again.");
  }
  const svg = s.mapSvg.cloneNode(true);
  svg.removeAttribute("style");
  svg.setAttribute("class", "r-map-svg");
  svg.querySelector(".map-zoom")?.removeAttribute("transform");
  for (const el of svg.querySelectorAll(".map-outlines > *")) el.remove();
  for (const el of svg.querySelectorAll(".is-dim")) el.classList.remove("is-dim");
  // the live map's pattern sits in a hidden view, where a reference to it would not paint: rename this copy's
  svg.querySelector("pattern#map-hatch")?.setAttribute("id", "report-map-hatch");
  for (const el of svg.querySelectorAll('[fill="url(#map-hatch)"]')) el.setAttribute("fill", "url(#report-map-hatch)");
  return svg;
}

function placeholder(text) {
  return h("div", { class: "r-map-missing", role: "note" }, h("p", { text }));
}

// ---------------------------------------------------------------- evidence
function lookalikes(s) {
  const p = s.plan;
  const looks = s.map?.lookalikes || [...p.lookalikes.used.map((x) => ({ ...x, usable: true })),
    ...p.lookalikes.rejected.map((x) => ({ ...x, usable: false }))];
  return section("r-looks", "r-looks-title", "Games like yours",
    looks.length ? h("ul", { class: "r-look-list" }, looks.map((x) => {
      const [cls, text] = STATUS[x.status] || ["badge-warn", `Not used: ${x.status}`];
      const detail = x.usable && x.countries_with_score ? `${x.countries_with_score} countries with data` : "";
      return h("li", { class: x.usable ? "is-used" : "is-unused" },
        h("span", { class: "r-look-name", text: x.name || `Steam ${x.appid}` }),
        h("span", { class: `badge ${cls}`, text }),
        detail ? h("span", { class: "r-look-detail", text: detail }) : null);
    })) : h("p", { class: "r-help", text: "No game like yours was found." }),
    h("p", { class: "r-help", text: "Only games with real Qloo fan data are used." }));
}

/** Who the fans of games like yours are, against Qloo's average audience (aggregate Qloo data, from the notes). */
function audience(a) {
  if (a?.status !== "ok") return null;
  const skews = [...a.age.map((x) => [x.band, x.skew]), ...Object.entries(a.gender)];
  return h("p", { class: "r-audience" }, h("strong", { text: "Who the fans are: " }),
    skews.map(([label, v]) => `${label} ${signed(v)}`).join(" · "),
    h("span", { class: "r-help-inline", text: " (compared with Qloo's average audience: + more, − fewer)" }));
}

function explanation(s) {
  const exp = s.explanation;
  if (!exp) {
    return section("r-explain", "r-explain-title", "Explanation",
      h("p", { class: "r-help", text: "No explanation was requested for this plan." }));
  }
  return section("r-explain", "r-explain-title", "Explanation",
    h("p", { class: "r-summary", text: exp.summary }),
    s.changed ? h("p", { class: "r-flag", text: `Written for the ${fmtUsd.format(s.original)} plan.` }) : null);
}

function markets(s) {
  const notes = s.notes;
  const body = [];
  if (!notes) {
    body.push(h("p", { class: "r-help", text: "Market notes were not requested for this plan." }));
  } else {
    body.push(audience(notes.audience));
    const shown = notes.markets.filter((m) => Object.values(m.also_loves).some((r) => r.status === "ok"));
    for (const m of shown) {
      const lists = Object.entries(m.also_loves).filter(([, r]) => r.status === "ok");
      body.push(h("div", { class: "r-market" },
        h("p", { class: "r-market-name" }, h("strong", { text: `${m.language_name} → ${m.country_name}` }),
          h("span", { class: "r-help-inline", text: ` (${GROUP_LABEL[m.group].toLowerCase()})` })),
        lists.map(([d, r]) => h("p", { class: "r-loves" },
          h("span", { class: "r-loves-label", text: d === "films" ? "Films" : "Music" }),
          r.items.slice(0, LOVES_SHOWN).map((i) => i.name).join(" · ")))));
    }
    body.push(h("p", { class: "r-help", text: shown.length ? "Ideas for marketing (Qloo data)."
      : "Qloo had no market data for this plan's markets, so none are shown." }));
    if (s.changed) {
      body.push(h("p", { class: "r-flag", text: `Markets were chosen for the ${fmtUsd.format(s.original)} plan.` }));
    }
  }
  return section("r-markets", "r-markets-title", "What these fans also like", ...body);
}

function footer(s) {
  const src = s.plan.sources;
  const baseline = src.baseline.includes(": ") ? src.baseline.slice(src.baseline.indexOf(": ") + 2) : src.baseline;
  return h("footer", { class: "r-foot" },
    h("p", { class: "r-provenance" },
      h("strong", { text: `Babel · plan ${s.res.plan_id || "not saved"} · ${s.date}. ` }),
      `${ESTIMATE_NOTE} Sources: ${src.qloo}; the usual share: ${baseline}; rates: ${src.rates}.`));
}
