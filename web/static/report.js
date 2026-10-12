// The one-page report (TASK 11): the open plan as a print-ready A4 page, built from plan.js currentPlan() (the
// server's result, the current budget fit and the world map on screen). Every number comes from that snapshot; this
// file selects and formats. Text from the server is inserted as text, never as HTML. Print layout: report.css.

import { $, countryName, fmtInt, fmtUsd, GROUP_LABEL, h, LANG, listText, pct } from "./ui.js";
import { confidence, countryList, formatValue, headline, legendItems, lookalikeEntry, METRICS, qlooAdjustment,
  signedPct } from "./mapdata.js";

const GROUP_ORDER = ["translate_game", "store_page_only", "skip"];
const BLURB = { translate_game: "Fits your budget and reaches the most likely players (estimate).",
  store_page_only: "The whole game didn't fit; a translated store page tests the market with what's left.",
  skip: "Too few likely players, or over the budget, for now." };
const STATUS = { valid: ["badge-ok", "Used: real Qloo fan data"],  // as the Plan screen's evidence cards say it
  "default map": ["badge-warn", "Not used: Qloo has no real data"], "not in Qloo": ["badge-warn", "Not used: Qloo doesn't know it"],
  "no heatmap": ["badge-warn", "Not used: no Qloo fan map"] };
const UNUSED = { "default map": "Qloo has no real fan data for it", "not in Qloo": "Qloo doesn't know it",
  "no heatmap": "Qloo has no fan map for it" };
const SOURCE = { "Qloo data": "src-qloo", "Babel estimate": "src-estimate", "Babel plan": "src-plan",
  Claude: "src-llm", "Written by code": "src-plan" };
const QLOO_NOTE = "Qloo describes the combined taste of many fans, never individual players, and it doesn't guarantee "
  + "sales.";
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
  fitToPage();
  document.fonts?.ready.then(() => fitToPage());
  $("#report-title").focus();
}

function withContext(s) {
  return { ...s, date: fmtDate.format(new Date()), changed: s.fit.costs.budget !== s.original,
    row: (code) => s.model.languages[code], usable: s.model.usable };
}

/** Keep the printed report on one A4 page whatever the fonts and data: measure the sheet in its print layout (the
 * base layout; class r-measure switches the screen-only rules off) and, if it is taller than the page, set --fit,
 * the zoom report.css applies in print. Down to MIN_FIT; beyond that the report runs onto a second page. */
const PAGE_PX = (297 - 2 * 9) * 96 / 25.4 - 6;  // A4 height minus report.css's 9 mm @page margins, in CSS px
const MIN_FIT = 0.8;

function fitToPage() {
  const sheet = $("#view-report .report-sheet");
  if (!sheet || $("#view-report").hidden) return;
  sheet.classList.add("r-measure");
  const height = sheet.getBoundingClientRect().height;
  sheet.classList.remove("r-measure");
  const fit = height > PAGE_PX ? Math.max(MIN_FIT, Math.floor((PAGE_PX / height) * 1000) / 1000) : 1;
  sheet.style.setProperty("--fit", String(fit));  // CSSOM: allowed by the page's CSP
  sheet.dataset.fit = String(fit);
}

window.addEventListener("beforeprint", () => {
  if (document.body.dataset.view !== "report" || !page.title) return;
  fitToPage();
  page.saved = document.title;
  document.title = page.title;
});
window.addEventListener("afterprint", () => {
  if (page.saved !== null) document.title = page.saved;
  page.saved = null;
});

// ---------------------------------------------------------------- small pieces
function source(kind) {
  return h("span", { class: `src ${SOURCE[kind] || ""}`, text: kind });
}

function sectionHead(id, title, ...kinds) {
  return h("div", { class: "r-section-head" }, h("h2", { id, text: title }), kinds.filter(Boolean).map(source));
}

function section(cls, id, title, kinds, ...body) {
  return h("section", { class: `r-section ${cls}`, "aria-labelledby": id }, sectionHead(id, title, ...kinds), ...body);
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const names = (codes) => listText(codes.map((c) => LANG[c] || c));
const signed = (x) => `${x > 0 ? "+" : ""}${x.toFixed(2)}`;

function toolbar(onBack) {
  return h("div", { class: "report-toolbar" },
    h("button", { type: "button", class: "button button-secondary", onclick: () => onBack?.() },
      h("span", { "aria-hidden": "true", text: "← " }), "Back to the plan"),
    h("p", { class: "help", text: "One A4 page. In the print dialog, choose Save as PDF to share it." }),
    h("button", { type: "button", class: "button button-primary", onclick: () => window.print() },
      "Print or save as PDF"));
}

function sheetFor(s) {
  return h("article", { class: "report-sheet", "aria-labelledby": "report-title" },
    header(s), inputs(s), alerts(s), planSection(s),
    h("div", { class: "r-grid" }, h("div", { class: "r-col" }, mapSection(s), markets(s)),
      h("div", { class: "r-col" }, lookalikes(s), explanation(s), limits(s))),
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
  return section("r-plan", "r-plan-title", "The plan", ["Babel plan", "Babel estimate"],
    h("div", { class: "table-wrap" }, h("table", { class: "r-table" },
      h("caption", { class: "visually-hidden",
        text: "Every target language by group, with its share of your likely players, Qloo adjustment, cost and why" }),
      h("thead", {}, h("tr", {}, ["#", "Language", "Share (est.)", "Qloo adjustment", "Cost (estimate)", "Why"]
        .map((t, i) => h("th", { scope: "col", class: i === 0 || i === 2 ? "num" : null, text: t })))),
      GROUP_ORDER.map((group) => groupBody(s, group)))),
    h("p", { class: "r-key" }, "# rank · Share: of your likely non-English players (estimate, not sales) · Qloo "
      + "adjustment: + where fans of games like yours are more common than usual, − where less (Qloo data); then the "
      + "range across the games:", dotKey("agree", "they agree"), dotKey("mixed", "they disagree or some lack data"),
    dotKey("none", "no data")),
    supported.length || vs ? h("p", { class: "r-versus" },
      supported.length ? `Already in your game: ${names(supported)}. ` : "",
      vs ? `The usual list most developers copy starts with ${names(vs.generic_top3)}; for this game, Babel ranks `
        + `${names(vs.babel_top3)} first.` : "") : null);
}

function dotKey(level, text) {
  return h("span", { class: "r-dot-key" }, h("span", { class: `r-dot conf-${level}`, "aria-hidden": "true" }), text);
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
    h("td", { class: "r-lift" }, h("span", { class: `r-dot conf-${conf.level}`, "aria-hidden": "true" }),
      h("span", { class: "r-phone-label", "aria-hidden": "true", text: "Qloo adjustment: " }),  // phones hide the header
      h("strong", { text: adj.short }),
      x.lift_range && lo !== hi && conf.level !== "none"
        ? h("span", { class: "r-range", text: ` (${signedPct(lo)} to ${signedPct(hi)})` }) : null,
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

/** A short plain reason per language, from the plan's own numbers (the server's wording is the cell's tooltip): for
 * full translations, the usual share and the Qloo adjustment behind Babel's rank; otherwise why it got its group. */
function why(s, code, group) {
  const x = s.row(code);
  const r = s.versus?.rows.find((v) => v.code === code);
  if (group === "translate_game") {
    if (!r) return "Part of the mix of full translations that reaches the most likely players within your budget.";
    const conf = confidence(x, s.usable.length);
    const qloo = conf.level === "none" ? "Qloo has no fan data here"
      : `Qloo adjustment ${qlooAdjustment(r.qloo_lift).short}`;
    return `The usual share: ${pct(r.baseline_share)}, ${ordinal(r.baseline_rank)}`
      + `${r.baseline_rank === r.generic_rank ? ", as on the usual list" : ` (${ordinal(r.generic_rank)} on the usual list)`}. `
      + `${qloo}, ${r.babel_rank === r.baseline_rank ? "so it stays" : "so Babel ranks it"} ${ordinal(r.babel_rank)}.`;
  }
  if (group === "store_page_only") {
    return `The full game (${fmtUsd.format(x.cost_full)}) didn't fit; the store page tests this market.`;
  }
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
  return section("r-map", "r-map-title", title, [spec.source],
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
  const overlap = Object.fromEntries([...p.lookalikes.used, ...p.lookalikes.rejected].map((x) => [x.appid, x.overlap]));
  return section("r-looks", "r-looks-title", "Games like yours", ["Qloo data"],
    looks.length ? h("ul", { class: "r-look-list" }, looks.map((x) => {
      const [cls, text] = STATUS[x.status] || ["badge-warn", `Not used: ${x.status}`];
      const detail = [x.usable && x.countries_with_score ? `${x.countries_with_score} countries with data` : null,
        overlap[x.appid] != null ? `tag match ${overlap[x.appid].toFixed(2)}` : null].filter(Boolean).join(" · ");
      return h("li", { class: x.usable ? "is-used" : "is-unused" },
        h("span", { class: "r-look-name", text: x.name || `Steam ${x.appid}` }),
        h("span", { class: `badge ${cls}`, text }),
        detail ? h("span", { class: "r-look-detail", text: detail }) : null);
    })) : h("p", { class: "r-help", text: "No game like yours was found." }),
    h("p", { class: "r-help", text: "Only real Qloo fan data counts; games without it are listed but never used. Tag "
      + "match: how closely their Steam tags match yours (rare tags count more)." }));
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
    return section("r-explain", "r-explain-title", "Explanation", [],
      h("p", { class: "r-help", text: "No explanation was requested for this plan." }));
  }
  const llm = exp.kind === "llm_text";
  return section("r-explain", "r-explain-title", "Explanation", [llm ? "Claude" : "Written by code"],
    h("p", { class: `r-summary${llm ? " is-llm" : ""}`, text: exp.summary }),
    h("p", { class: "r-help", text: llm ? "Written by Claude from the plan's evidence; code checked every number in it."
      : `Written by code from the plan's evidence (Claude's explanation was not used: ${exp.reason || "unavailable"}).` }),
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
          r.items.slice(0, LOVES_SHOWN).map((i) => i.name).join(" · "))),
        m.note?.status === "ok" ? h("p", { class: "r-llm" }, source("Claude"), " ", m.note.text) : null));
    }
    body.push(h("p", { class: "r-help", text: shown.length
      ? "Films and music these fans also like there: popular in each country, then re-ranked by fans of games like "
        + "yours (Qloo data). Ideas for marketing, not proof of what any one player likes."
      : "Qloo had no market data for this plan's markets, so none are shown." }));
    if (s.changed) {
      body.push(h("p", { class: "r-flag", text: `Markets were chosen for the ${fmtUsd.format(s.original)} plan.` }));
    }
  }
  return section("r-markets", "r-markets-title", "What these fans also like, by market", notes ? ["Qloo data"] : [],
    ...body);
}

/** The plan's standing caveats (babel/plan.py) in plain words; one this page doesn't know is shown as the server
 * sent it. The small-indie test result is said by the track record line, from its own numbers. */
function plainCaveat(text) {
  if (text.startsWith("Shares are estimates")) {
    return "Shares are estimates of where your likely non-English players are, not sales, wishlists or player counts.";
  }
  if (text.startsWith("The baseline comes from")) {
    return "The usual share comes from Steam reviews of English-only games, which miss players who only buy "
      + "translated games (especially Chinese, Japanese and Korean speakers).";
  }
  if (text.startsWith("On small English-only indie games")) return null;
  if (text.startsWith("Costs are estimates")) return "Costs are estimates from per-word rates you can edit, not quotes.";
  return text;
}

/** The backtest in one plain sentence, from the plan's track record (p values as the server wrote them). */
function trackLine(tr) {
  const below = (x) => String(x).trim().startsWith("<");
  const value = (x) => Number(String(x).trim().replace(/^</, ""));
  const p = (x) => (below(x) ? `p ${x}` : `p = ${x}`);
  const luck = (x) => (value(x) <= 0.001 && (below(x) || value(x) < 0.001) ? "very unlikely to be luck"
    : value(x) < 0.05 ? "unlikely to be luck" : "could be luck");
  const w = tr.wikipedia_pageviews;
  const st = tr.steam_reviews;
  return `Track record: on ${w.test_games} well-known games, Babel's top 3 languages reached `
    + `${pct(w.babel_top3_coverage)} of the real non-English audience, and Qloo's fan maps made the picks better `
    + `(${luck(w.sign_test_p)}, ${p(w.sign_test_p)}). On ${st.test_games} small indie games, they reached `
    + `${pct(st.babel_top3_coverage)} of non-English reviews.`;
}

function limits(s) {
  const p = s.plan;
  const budgetNote = p.status === "ok" ? null : p.messages.at(-1);
  const partial = s.res.status === "ok" ? null : "Some data could not be read, so parts of this plan rest on less evidence.";
  const items = [partial, ...p.messages.filter((m) => m !== budgetNote), ...p.uncertainty.caveats.map(plainCaveat)]
    .filter(Boolean);
  return section("r-limits", "r-limits-title", "Good to know", [],
    h("p", { class: "r-callout" }, h("strong", { text: QLOO_NOTE }), ` ${ESTIMATE_NOTE} Babel doesn't predict `
      + "revenue or return on investment."),
    h("ul", { class: "r-limit-list" }, items.map((t) => h("li", { text: t }))),
    h("p", { class: "r-help", text: trackLine(p.track_record) }));
}

function footer(s) {
  const src = s.plan.sources;
  const baseline = src.baseline.includes(": ") ? src.baseline.slice(src.baseline.indexOf(": ") + 2) : src.baseline;
  return h("footer", { class: "r-foot" },
    h("p", { class: "r-provenance" },
      h("strong", { text: `Babel · plan ${s.res.plan_id || "not saved"} · ${s.date}. ` }),
      `Sources: ${src.qloo}; the usual share: ${baseline}; rates: ${src.rates}. Every number was computed by Babel's `
      + "code; text marked Claude was written by Claude from this evidence."));
}
