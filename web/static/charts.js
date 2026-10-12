// "Your plan at a glance": four small charts on the Plan screen, drawn with D3 (vendored, window.d3) in SVG.
//  1. share of your likely non-English players per language (estimate), coloured by plan group, with the usual share
//  2. the Qloo adjustment per language, around "as usual", with the spread between the games like yours
//  3. Babel's order vs the usual list (a slope chart)
//  4. where the budget goes (one stacked bar)
// Every number comes from the plan the server sent; the *Rows/*Segments functions only select and sort it (no DOM,
// so tests can call them). Colours come from CSS classes (charts.css) on the shared plan tokens, so a theme change
// needs no redraw. The plan's lists and the "Babel vs the usual list" table stay the table view of these charts.

import { fmtUsd, GROUP_LABEL, h, LANG, pct } from "./ui.js";
import { qlooAdjustment, signedPct } from "./mapdata.js";

const d3 = window.d3;
const ROW = 24;          // px per language row
const BAR = 14;          // bar thickness
const LABEL_W = 146;     // language names ("Traditional Chinese")
const VALUE_W = 54;      // values after the bars
const GROUP_ORDER = ["translate_game", "store_page_only", "skip", "already_supported"];

// ---------------------------------------------------------------- data (pure)
/** Languages by estimated share, high to low: {code, name, share, usual, group}. usual = the share before Qloo. */
export function shareRows(plan, groupOf, versus) {
  const usual = Object.fromEntries((versus?.rows || []).map((r) => [r.code, r.baseline_share]));
  return plan.languages
    .map((x) => ({ code: x.code, name: LANG[x.code] || x.code, share: x.estimated_share, usual: usual[x.code] ?? null,
      group: groupOf[x.code] || x.group }))
    .sort((a, b) => b.share - a.share);
}

/** Languages by Qloo adjustment, most "more fans" first: {code, name, lift, lo, hi, hasData, group}. */
export function liftRows(plan, groupOf) {
  return plan.languages
    .map((x) => ({ code: x.code, name: LANG[x.code] || x.code, lift: x.qloo_lift, lo: x.lift_range?.[0] ?? null,
      hi: x.lift_range?.[1] ?? null, hasData: x.lookalikes_with_data > 0, group: groupOf[x.code] || x.group }))
    .sort((a, b) => (b.hasData - a.hasData) || (b.lift - a.lift));
}

/** Babel vs the usual list: {code, name, usual, babel, places, group}, by Babel's rank. */
export function slopeRows(versus, groupOf) {
  return (versus?.rows || [])
    .map((r) => ({ code: r.code, name: r.language || LANG[r.code] || r.code, usual: r.generic_rank, babel: r.babel_rank,
      places: r.places, group: groupOf[r.code] }))
    .sort((a, b) => a.babel - b.babel);
}

/** The budget as segments: one per full translation, the store pages together, then what is left over. */
export function budgetSegments(plan, groups, costs) {
  const row = Object.fromEntries(plan.languages.map((x) => [x.code, x]));
  const full = groups.translate_game.map((code) => ({ key: code, group: "translate_game", label: LANG[code] || code,
    amount: row[code].cost_full }));
  const fullSum = full.reduce((s, x) => s + x.amount, 0);
  // the server's group total is the truth; if per-language costs don't add up to it, show the group as one block
  const segs = Math.abs(fullSum - costs.translate_game) < 1 ? full
    : (costs.translate_game > 0 ? [{ key: "translate_game", group: "translate_game", label: GROUP_LABEL.translate_game,
      amount: costs.translate_game }] : []);
  if (costs.store_page_only > 0) {
    const n = groups.store_page_only.length;
    segs.push({ key: "store_page_only", group: "store_page_only", amount: costs.store_page_only,
      label: `${n} store page${n === 1 ? "" : "s"}` });
  }
  if (costs.unspent > 0) segs.push({ key: "left", group: "left", label: "Left over", amount: costs.unspent });
  return segs;
}

// ---------------------------------------------------------------- drawing helpers
/** A horizontal bar from x0 to x1 with a rounded data end (the end away from the baseline). */
function barPath(x0, x1, y, hgt, r = 4) {
  const w = Math.abs(x1 - x0);
  if (w < 0.5) return "";
  const rr = Math.min(r, w, hgt / 2);
  const dir = x1 >= x0 ? 1 : -1;
  const end = x1 - dir * rr;
  return `M${x0},${y}H${end}A${rr},${rr} 0 0 ${dir > 0 ? 1 : 0} ${x1},${y + rr}V${y + hgt - rr}`
    + `A${rr},${rr} 0 0 ${dir > 0 ? 1 : 0} ${end},${y + hgt}H${x0}Z`;
}

function svgFor(host, width, height, label) {
  return d3.select(host).append("svg").attr("class", "chart-svg").attr("width", width).attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`).attr("role", "group").attr("aria-label", label);
}

/** Hover / focus a row: tooltip near it; click or Enter: show the language on the map. */
function interactive(sel, ctx, tip, onLanguage) {
  sel.attr("data-lang", (d) => d.code).attr("tabindex", 0).attr("role", "button").style("cursor", onLanguage ? "pointer" : null)
    .attr("aria-label", (d) => tip(d).replace(/\n/g, ". "))
    .on("mouseenter focus", function (e, d) { ctx.show(this, tip(d)); d3.select(this).classed("is-hot", true); })
    .on("mousemove", (e) => ctx.move(e))
    .on("mouseleave blur", function () { ctx.hide(); d3.select(this).classed("is-hot", false); })
    .on("click", (e, d) => onLanguage?.(d.code))
    .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onLanguage?.(d.code); } });
}

function tooltipFor(card) {
  const box = h("div", { class: "chart-tooltip", hidden: true });
  card.append(box);
  const place = (x, y) => {
    const r = card.getBoundingClientRect();
    const left = Math.min(Math.max(8, x - r.left + 14), r.width - box.offsetWidth - 8);
    box.style.left = `${left}px`;
    box.style.top = `${y - r.top + 14}px`;
  };
  return {
    show(el, text) {
      box.replaceChildren(...text.split("\n").map((line, i) => h("span", { class: i ? "muted" : "", text: line })));
      box.hidden = false;
      const r = el.getBoundingClientRect();
      place(r.left + Math.min(r.width, 220), r.top + r.height / 2);
    },
    move(e) { place(e.clientX, e.clientY); },
    hide() { box.hidden = true; },
  };
}

// ---------------------------------------------------------------- the four charts
function shareChart(host, rows, width, ctx, onLanguage) {
  const plotW = width - LABEL_W - VALUE_W;
  const max = d3.max(rows, (d) => Math.max(d.share, d.usual ?? 0)) || 1;
  const x = d3.scaleLinear().domain([0, max]).range([0, plotW]).nice();
  const height = rows.length * ROW + 4;
  const svg = svgFor(host, width, height, "Share of your likely non-English players by language, an estimate. "
    + rows.slice(0, 3).map((d) => `${d.name} ${pct(d.share)}`).join(", ") + ".");
  const g = svg.selectAll("g.row").data(rows).join("g").attr("class", "row")
    .attr("transform", (d, i) => `translate(0,${i * ROW + 2})`);
  g.append("rect").attr("class", "hit").attr("x", 0).attr("width", width).attr("height", ROW);
  g.append("text").attr("class", "label").attr("x", LABEL_W - 10).attr("y", ROW / 2).attr("text-anchor", "end")
    .text((d) => d.name);
  g.append("path").attr("class", (d) => `mark mark-${d.group}`)
    .attr("d", (d) => barPath(LABEL_W, LABEL_W + x(d.share), (ROW - BAR) / 2, BAR));
  g.filter((d) => d.usual != null).append("line").attr("class", "usual-halo")
    .attr("x1", (d) => LABEL_W + x(d.usual)).attr("x2", (d) => LABEL_W + x(d.usual))
    .attr("y1", (ROW - BAR) / 2 - 3).attr("y2", (ROW + BAR) / 2 + 3);
  g.filter((d) => d.usual != null).append("line").attr("class", "usual")
    .attr("x1", (d) => LABEL_W + x(d.usual)).attr("x2", (d) => LABEL_W + x(d.usual))
    .attr("y1", (ROW - BAR) / 2 - 3).attr("y2", (ROW + BAR) / 2 + 3);
  g.append("text").attr("class", "value").attr("x", (d) => LABEL_W + Math.max(x(d.share), d.usual != null ? x(d.usual) : 0) + 6)
    .attr("y", ROW / 2).text((d) => pct(d.share));
  interactive(g, ctx, (d) => `${d.name}: ${pct(d.share)} (estimate)\n${d.usual != null ? `Usual share before Qloo: ${pct(d.usual)}\n` : ""}`
    + `${GROUP_LABEL[d.group] || ""}`, onLanguage);
}

function liftChart(host, rows, width, ctx, onLanguage) {
  const plotW = width - LABEL_W - VALUE_W - 8;
  const vals = rows.filter((d) => d.hasData).flatMap((d) => [d.lift, d.lo ?? d.lift, d.hi ?? d.lift].map((v) => v - 1));
  const x = d3.scaleLinear().domain([Math.min(-0.15, d3.min(vals) ?? 0), Math.max(0.15, d3.max(vals) ?? 0)])
    .range([LABEL_W, LABEL_W + plotW]).nice();
  const height = rows.length * ROW + 26;
  const svg = svgFor(host, width, height, "Qloo adjustment per language: how much more or less common fans of games "
    + "like yours are where it's spoken.");
  const zero = x(0);
  svg.append("line").attr("class", "baseline").attr("x1", zero).attr("x2", zero).attr("y1", 0).attr("y2", rows.length * ROW + 4);
  svg.append("text").attr("class", "axis").attr("x", zero).attr("y", rows.length * ROW + 20).attr("text-anchor", "middle")
    .text("as usual");
  svg.append("text").attr("class", "axis").attr("x", LABEL_W).attr("y", rows.length * ROW + 20).text("← fewer fans");
  svg.append("text").attr("class", "axis").attr("x", LABEL_W + plotW).attr("y", rows.length * ROW + 20)
    .attr("text-anchor", "end").text("more fans →");
  const g = svg.selectAll("g.row").data(rows).join("g").attr("class", "row")
    .attr("transform", (d, i) => `translate(0,${i * ROW + 2})`);
  g.append("rect").attr("class", "hit").attr("x", 0).attr("width", width).attr("height", ROW);
  g.append("text").attr("class", "label").attr("x", LABEL_W - 10).attr("y", ROW / 2).attr("text-anchor", "end")
    .text((d) => d.name);
  const has = g.filter((d) => d.hasData);
  has.append("path").attr("class", (d) => `mark ${d.lift >= 1 ? "mark-more" : "mark-fewer"}`)
    .attr("d", (d) => barPath(zero, x(d.lift - 1), (ROW - BAR) / 2, BAR));
  has.filter((d) => d.lo != null && d.hi != null && d.lo !== d.hi).append("line").attr("class", "spread")
    .attr("x1", (d) => x(d.lo - 1)).attr("x2", (d) => x(d.hi - 1)).attr("y1", ROW / 2).attr("y2", ROW / 2);
  g.append("text").attr("class", "value")
    .attr("x", (d) => (d.hasData ? Math.max(zero, x(d.lift - 1), x((d.hi ?? d.lift) - 1)) : zero) + 6)
    .attr("y", ROW / 2).text((d) => qlooAdjustment(d.lift, d.hasData).short);
  interactive(g, ctx, (d) => {
    const adj = qlooAdjustment(d.lift, d.hasData);
    const spread = d.hasData && d.lo != null && d.lo !== d.hi ? `\nGames like yours range from ${signedPct(d.lo)} to ${signedPct(d.hi)}` : "";
    return `${d.name}: Qloo adjustment ${adj.short}\n${adj.text.charAt(0).toUpperCase()}${adj.text.slice(1)}${spread}`;
  }, onLanguage);
}

function slopeChart(host, rows, width, ctx, onLanguage) {
  const n = rows.length;
  const longest = d3.max(rows, (d) => d.name.length + 3) || 12;
  const side = Math.min(width * 0.42, longest * 7.2 + 22);  // room for "Simplified Chinese 1"
  const x0 = side;
  const x1 = width - side;
  const y = (rank) => 28 + (rank - 1) * ROW + ROW / 2;
  const height = 28 + n * ROW + 4;
  const svg = svgFor(host, width, height, "Babel's order of languages compared with the usual list.");
  svg.append("text").attr("class", "axis axis-head").attr("x", x0 + 4).attr("y", 14).attr("text-anchor", "end").text("The usual list");
  svg.append("text").attr("class", "axis axis-head").attr("x", x1 - 4).attr("y", 14).text("Babel, for your game");
  const g = svg.selectAll("g.row").data(rows).join("g")
    .attr("class", (d) => `row ${Math.abs(d.places) >= 3 ? "is-moved" : ""}`);
  g.append("line").attr("class", (d) => `slope slope-${d.group}`)
    .attr("x1", x0).attr("x2", x1).attr("y1", (d) => y(d.usual)).attr("y2", (d) => y(d.babel));
  g.append("circle").attr("class", (d) => `dot mark-${d.group}`).attr("cx", x0).attr("cy", (d) => y(d.usual)).attr("r", 4.5);
  g.append("circle").attr("class", (d) => `dot mark-${d.group}`).attr("cx", x1).attr("cy", (d) => y(d.babel)).attr("r", 4.5);
  g.append("text").attr("class", "label").attr("x", x0 - 10).attr("y", (d) => y(d.usual)).attr("text-anchor", "end")
    .text((d) => `${d.name} ${d.usual}`);
  g.append("text").attr("class", "label").attr("x", x1 + 10).attr("y", (d) => y(d.babel)).text((d) => `${d.babel} ${d.name}`);
  // a wide invisible stroke along each line, so a line is easy to hover
  g.append("line").attr("class", "hit-line").attr("x1", x0).attr("x2", x1).attr("y1", (d) => y(d.usual)).attr("y2", (d) => y(d.babel));
  interactive(g, ctx, (d) => `${d.name}: #${d.usual} on the usual list, #${d.babel} for your game\n`
    + `${d.places > 0 ? `${d.places} place${d.places === 1 ? "" : "s"} higher` : d.places < 0 ? `${-d.places} place${d.places === -1 ? "" : "s"} lower` : "Same place"}`
    + ` · ${GROUP_LABEL[d.group] || ""}`, onLanguage);
}

function budgetChart(host, segs, costs, width, ctx) {
  const total = d3.sum(segs, (d) => d.amount) || 1;
  const height = 34;
  const x = d3.scaleLinear().domain([0, total]).range([0, width]);
  const svg = svgFor(host, width, height, `Budget ${fmtUsd.format(costs.budget)}: `
    + segs.map((d) => `${d.label} ${fmtUsd.format(d.amount)}`).join(", ") + ".");
  let at = 0;
  const placed = segs.map((d) => { const s = { ...d, x: x(at), w: x(d.amount) }; at += d.amount; return s; });
  const g = svg.selectAll("g.seg").data(placed).join("g").attr("class", "seg");
  // 2px surface gaps between segments; only the outer ends are rounded
  g.append("rect").attr("class", (d) => `mark mark-${d.group}`)
    .attr("x", (d, i) => d.x + (i ? 1 : 0)).attr("y", 0).attr("height", height)
    .attr("width", (d, i) => Math.max(0, d.w - (i ? 1 : 0) - (i < placed.length - 1 ? 1 : 0)))
    .attr("rx", 0);
  svg.insert("clipPath", ":first-child").attr("id", "budget-clip").append("rect")
    .attr("width", width).attr("height", height).attr("rx", 6);
  svg.selectAll("g.seg").attr("clip-path", "url(#budget-clip)");
  g.filter((d) => d.w > 64).append("text").attr("class", (d) => `seg-label seg-on-${d.group}`).attr("x", (d) => d.x + 10)
    .attr("y", height / 2).text((d) => (d.w > 150 ? `${d.label} ${fmtUsd.format(d.amount)}` : d.label));
  g.attr("tabindex", 0).attr("aria-label", (d) => `${d.label}: ${fmtUsd.format(d.amount)}`)
    .on("mouseenter focus", function (e, d) { ctx.show(this, `${d.label}: ${fmtUsd.format(d.amount)}\n${pct(d.amount / costs.budget, 0)} of your budget`); })
    .on("mousemove", (e) => ctx.move(e))
    .on("mouseleave blur", () => ctx.hide());
}

// ---------------------------------------------------------------- the section
function chartCard(id, title, note, legend) {
  const plot = h("div", { class: "chart-plot", id: `${id}-plot` });
  const card = h("article", { class: "chart-card", "aria-labelledby": `${id}-title` },
    h("h3", { id: `${id}-title`, class: "chart-title", text: title }),
    note ? h("p", { class: "help chart-note", text: note }) : null,
    legend ? h("ul", { class: "chart-legend" }, legend) : null,
    plot);
  return { card, plot };
}

const key = (cls, text) => h("li", {}, h("span", { class: `key ${cls}`, "aria-hidden": "true" }), text);
const groupKeys = (groups) => GROUP_ORDER.filter((g) => groups.includes(g)).map((g) => key(`mark-${g}`, GROUP_LABEL[g]));

let state = null;
let observer = null;

/** Draw (or redraw) the four charts. data = {plan, groups, groupOf, versus, costs, coverage}; onLanguage(code). */
export function renderCharts(host, data, { onLanguage } = {}) {
  if (!host || !d3) return;
  state = { host, data, onLanguage };
  draw();
  if (!observer && "ResizeObserver" in window) {
    let last = host.clientWidth;
    observer = new ResizeObserver(() => {
      if (Math.abs(host.clientWidth - last) < 8 || !state) return;
      last = host.clientWidth;
      draw();
    });
    observer.observe(host);
  }
}

function draw() {
  const { host, data, onLanguage } = state;
  const shares = shareRows(data.plan, data.groupOf, data.versus);
  const lifts = liftRows(data.plan, data.groupOf);
  const slopes = slopeRows(data.versus, data.groupOf);
  const segs = budgetSegments(data.plan, data.groups, data.costs);
  const present = [...new Set(shares.map((d) => d.group))];

  const c1 = chartCard("chart-share", "Who your likely players are",
    "Share of your likely non-English players who speak each language (estimate).",
    [...groupKeys(present), key("key-usual", "Usual share, before Qloo")]);
  const c2 = chartCard("chart-lift", "What Qloo changed",
    "The Qloo adjustment: how much more or less common fans of games like yours are where each language is spoken. "
      + "The thin line spans the games like yours.",
    [key("mark-more", "More fans than usual"), key("mark-fewer", "Fewer fans than usual")]);
  const c3 = slopes.length ? chartCard("chart-slope", "Babel vs the usual list",
    "The usual list is the same for every game. Lines that cross show where your game is different.", groupKeys(present)) : null;
  const c4 = chartCard("chart-budget", "Where your budget goes",
    `${fmtUsd.format(data.costs.total)} of ${fmtUsd.format(data.costs.budget)} planned (estimates, not quotes).`,
    [...groupKeys(segs.map((d) => d.group)), ...(segs.some((d) => d.group === "left") ? [key("mark-left", "Left over")] : [])]);
  const reach = h("p", { class: "chart-big" },
    h("strong", { text: pct(data.coverage.translate_game, 0) }),
    " of your likely non-English players could play in their language with the full translations (estimate).");
  const list = h("dl", { class: "chart-breakdown" }, segs.map((d) => h("div", {},
    h("dt", {}, h("span", { class: `key mark-${d.group}`, "aria-hidden": "true" }),
      d.group === "translate_game" && d.key !== "translate_game" ? `${d.label}, full game` : d.label),
    h("dd", { text: fmtUsd.format(d.amount) }))));
  c4.card.append(list, reach);

  host.replaceChildren(h("div", { class: "chart-grid" }, c1.card, c2.card, ...(c3 ? [c3.card] : []), c4.card));
  const width = (el) => Math.max(260, Math.floor(el.clientWidth));
  shareChart(c1.plot, shares, width(c1.plot), tooltipFor(c1.card), onLanguage);
  liftChart(c2.plot, lifts, width(c2.plot), tooltipFor(c2.card), onLanguage);
  if (c3) slopeChart(c3.plot, slopes, width(c3.plot), tooltipFor(c3.card), onLanguage);
  budgetChart(c4.plot, segs, data.costs, width(c4.plot), tooltipFor(c4.card));
}
