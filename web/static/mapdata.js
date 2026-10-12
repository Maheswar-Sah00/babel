// Pure data transforms for the Plan screen's map: which value and colour a country gets for a metric, legends,
// the country list, and plain labels. Every number comes from the server (babel/explore.py and babel/plan.py);
// this file only selects, bins and formats them. No DOM, no D3: the browser tests call these functions directly.

import { GROUP_LABEL, LANG, listText, pct } from "./ui.js";

// Palettes checked with the dataviz validator (light surface #ffffff): sequential blue (ordinal checks), a blue/red
// diverging pair with a neutral midpoint, and three categorical hues for the plan (all-pairs CVD check).
export const SEQ = ["#86b6ef", "#5598e7", "#2a78d6", "#184f95", "#0d366b"];
export const DIV = ["#b3302c", "#ec9890", "#dcdfdd", "#86b6ef", "#1c5cab"];
export const PLAN = { translate_game: "#2a78d6", store_page_only: "#eb6834", already_supported: "#1baf7a",
  skip: "#cfd4d2" };
export const NOT_COUNTED = "#eceeed";
export const HATCH = "url(#map-hatch)";
const HATCH_INK = { fill: "#f4f6f6", stroke: "#aab4b8" };  // the no-score pattern; .swatch-hatch in app.css matches

// Dark theme: monochrome (the owner's choice: no blue), only true greys (R = G = B) besides the red "fewer" arm and
// the plan's orange and green. Validated with the dataviz validator against the dark map surface #0e0e0e
// (--map-surface in app.css); its chroma-floor and lightness-band checks fail for every grey by design (they test
// hues), so greys are told apart by lightness alone (OKLab L below). Sequential: dark grey to near-white, low values
// near the surface (ordinal PASS: monotone, L .40 .52 .64 .77 .91, steps 0.12 to 0.14, darkest #484848 2.11:1).
// Diverging: the red arm as before (far end brightest), the "more" arm light grey to near-white, from a dark grey
// midpoint #3a3a3a that recedes like the light one (1.70:1, which the ordinal light-end check flags, as it did the
// old #333c41 at 1.62:1). Arms ordinal dL PASS; all pairs CVD worst 9.4 (protan, midpoint vs #b3302c), normal worst
// 18.2 (the two far ends); weak ends CVD 11.6, normal 19.0, both >= 3:1; midpoint vs the hatch's fill dE 15.7.
// Plan: translate near-white, skip mid grey (3.07:1), store page and supported keep their hues: all pairs CVD worst
// 9.4 (store vs supported, unchanged), normal worst 18.4 (supported vs skip); "not counted" #1b1b1b recedes (1.12:1,
// like the light #eceeed) and is dE 26.7 from skip and 18.0 from the lowest sequential step; hatch fill #141414
// with #404040 lines (dE 21.0 from the lowest step). Map outlines get a dark halo on the near-white fills (app.css).
const DARK = {
  seq: ["#484848", "#696969", "#8c8c8c", "#b4b4b4", "#e1e1e1"],
  div: ["#ec9890", "#b3302c", "#3a3a3a", "#808080", "#e2e2e2"],
  plan: { translate_game: "#e8e8e8", store_page_only: "#d95926", already_supported: "#199e70", skip: "#606060" },
  notCounted: "#1b1b1b",
  hatch: { fill: "#141414", stroke: "#404040" },
};
const PALETTES = { light: { seq: SEQ, div: DIV, plan: PLAN, notCounted: NOT_COUNTED, hatch: HATCH_INK }, dark: DARK };

/** The map colours for a theme ("light" or "dark"; anything else is light). */
export function palette(theme = "light") {
  return PALETTES[theme] || PALETTES.light;
}

// ---------------------------------------------------------------- plain wording of the server's ratios
const off = (x) => Math.round(Math.abs(x - 1) * 100);  // ×1.16 -> 16, ×0.70 -> 30
/** ×1.16 -> "+16%", ×0.70 -> "−30%" (a change from usual, rounded to a whole percent). */
export function signedPct(x) {
  const p = Math.round((x - 1) * 100);
  return p > 0 ? `+${p}%` : p < 0 ? `−${-p}%` : "±0%";
}

const REL_EDGES = [0.67, 0.91, 1.1, 1.5];  // "Fans compared with usual": the map's bins (the middle one is "about the same")
export const METRICS = {
  affinity: {
    label: "Fan interest", source: "Qloo data", unit: "Qloo's score from 0 to 1", byLookalike: true,
    about: "How strongly fans of games like yours gather in each country, on Qloo's scale from 0 to 1 (higher means "
      + "more of them than you would expect there). It is not a player count. Countries where Qloo has too little data "
      + "have no score.",
    edges: [0.2, 0.4, 0.6, 0.8], ramp: "seq",
    labels: ["Very low (under 0.2)", "Low (0.2 to 0.4)", "Medium (0.4 to 0.6)", "High (0.6 to 0.8)", "Very high (0.8 and up)"],
    details: ["Affinity under 0.2", "Affinity 0.2 to 0.4", "Affinity 0.4 to 0.6", "Affinity 0.6 to 0.8", "Affinity 0.8 and up"],
  },
  relative: {
    label: "Fans compared with usual", source: "Qloo data", unit: "% more or fewer than usual",
    byLookalike: true,
    about: "How common fans of games like yours are in each country, compared with the usual there: the average for "
      + "172 other games Babel uses as a yardstick. Above 0%, games like yours have more fans there than usual.",
    edges: REL_EDGES, ramp: "div",
    labels: [`Far fewer (over ${off(REL_EDGES[0])}% fewer)`, `Fewer (${off(REL_EDGES[1])}–${off(REL_EDGES[0])}% fewer)`,
      "About the same", `More (${off(REL_EDGES[2])}–${off(REL_EDGES[3])}% more)`, `Far more (over ${off(REL_EDGES[3])}% more)`],
    details: REL_EDGES.map((e, i, a) => (i === 0 ? `Under ×${e}` : `×${a[i - 1]} to ×${e}`)).concat(`×${REL_EDGES.at(-1)} and up`),
  },
  demand: {
    label: "Share of likely players", source: "Babel estimate", unit: "your likely non-English players, per language",
    byLookalike: false,
    about: "Babel's estimate of how your likely non-English players split between languages: the usual share, adjusted "
      + "by Qloo. It belongs to the language, so every country Babel counts for that language gets the same colour. "
      + "An estimate, not a player count or a sales forecast.",
    edges: [0.01, 0.03, 0.06, 0.12], ramp: "seq",
    labels: ["Under 1% (too few to plan for)", "1% to 3%", "3% to 6%", "6% to 12%", "12% and up"],
  },
  plan: {
    label: "Your plan", source: "Babel plan", unit: "what the plan does for each country's language", byLookalike: false,
    about: "What the plan does for the language Babel counts in each country, at the budget you set.",
    classes: ["translate_game", "store_page_only", "skip", "already_supported"],
  },
};
export const METRIC_ORDER = ["relative", "affinity", "demand", "plan"];

/** A "fans compared with usual" ratio, short for lists: ×1.16 -> "+16%", ×0.70 -> "−30%", ×7.77 -> "7.8× usual". */
export function relativeShort(x) {
  return x >= 2 ? `${x.toFixed(1)}× usual` : signedPct(x);
}

/** The same ratio in words, as [lead, rest]: ["16% more", "fans than usual"], ["30% fewer", ...],
 * ["7.8 times", "as many fans as usual"], ["about the same", "as usual (+4%)"] (the map's middle bin). */
export function relativeParts(x) {
  if (x >= 2) return [`${x.toFixed(1)} times`, "as many fans as usual"];
  if (x >= REL_EDGES[1] && x < REL_EDGES[2]) return ["about the same", `as usual (${signedPct(x)})`];
  return [`${off(x)}% ${x > 1 ? "more" : "fewer"}`, "fans than usual"];
}

/** "16% more fans than usual", "about the same as usual (+4%)". */
export function relativeText(x) {
  return relativeParts(x).join(" ");
}

const NEAR = 0.05;  // a Qloo adjustment within 1 ± NEAR is "about average" (as babel/explore.py words it)
/**
 * A language's Qloo adjustment (the server's qloo_lift) in words. hasData: whether any game like yours has Qloo data
 * for its countries. {short: "+16%" | "−9%" | "about average" | "no data", text: a sentence, exact: "×1.16"}.
 */
export function qlooAdjustment(lift, hasData = true) {
  const exact = `×${lift.toFixed(2)}`;
  if (!hasData) return { short: "no data", exact, text: "Qloo has no fan data for its countries, so it changes nothing" };
  if (Math.abs(lift - 1) < NEAR) {
    return { short: "about average", exact, text: "fans of games like yours are about as common where it's spoken as usual" };
  }
  return { short: signedPct(lift), exact,
    text: `fans of games like yours are ${off(lift)}% ${lift > 1 ? "more" : "less"} common where it's spoken` };
}

const UNUSED = {
  "default map": "Qloo has no real fan data for this game (it returned its default map), so Babel doesn't use it.",
  "not in Qloo": "Qloo doesn't know this game, so there is no fan map.",
  "no heatmap": "Qloo returned no fan map for this game.",
};

export function binIndex(value, edges) {
  let i = 0;
  while (i < edges.length && value >= edges[i]) i += 1;
  return i;
}

/** {language: group} from the plan's groups. */
export function groupOf(groups) {
  const out = {};
  for (const [group, codes] of Object.entries(groups)) for (const code of codes) out[code] = group;
  return out;
}

/** The view model the map functions read: the server's map data, the plan's languages and the current groups. */
export function model(map, plan, groups) {
  return { map, languages: Object.fromEntries(plan.languages.map((x) => [x.code, x])), groups,
    groupOf: groupOf(groups), usable: map ? map.lookalikes.filter((x) => x.usable) : [] };
}

export function lookalikeEntry(m, key) {
  return key === "all" ? null : (m.map?.lookalikes || []).find((x) => String(x.appid) === key) || null;
}

/**
 * One country's value for a metric and look-alike ("all" or an app ID):
 * {status: "value" | "no_score" | "no_reference" | "not_counted" | "unused_map" | "no_map", value, bin, n, reason}.
 */
export function countryValue(m, metric, cc, lookalike = "all") {
  const spec = METRICS[metric];
  const row = m.map?.countries?.[cc];
  if (spec.byLookalike) {
    if (!m.map || m.map.status !== "ok") {
      return { status: "no_map", reason: "Qloo has no real fan data for any of the games like yours." };
    }
    const entry = lookalikeEntry(m, lookalike);
    if (entry && !entry.usable) {
      return { status: "unused_map", reason: UNUSED[entry.status] || `Not used: ${entry.status}.` };
    }
    const source = entry ? row?.by_lookalike?.[lookalike] : row;
    const n = entry ? (source ? 1 : 0) : row?.lookalikes_with_score || 0;
    if (!source || source.affinity == null) {
      return { status: "no_score", n,
        reason: `No score: Qloo has too little data here (fewer than ${m.map.min_cells} map squares).` };
    }
    const value = source[metric];
    if (value == null) {
      return { status: "no_reference", n, affinity: source.affinity,
        reason: "Too few of the yardstick games have Qloo data here to say what is usual." };
    }
    return { status: "value", value, bin: binIndex(value, spec.edges), n, affinity: source.affinity };
  }
  const lang = row?.model_language;
  if (!lang) return { status: "not_counted", reason: "Babel doesn't count this country for any of its 14 languages." };
  if (metric === "demand") {
    const value = m.languages[lang].estimated_share;
    return { status: "value", value, bin: binIndex(value, spec.edges), language: lang };
  }
  const group = m.groupOf[lang];
  return { status: "value", value: group, bin: spec.classes.indexOf(group), language: lang };
}

/** {fill, key}: the colour (or hatch) for a country in a theme, and its legend key (the same in both themes). */
export function fillFor(m, metric, cc, lookalike = "all", theme = "light") {
  const v = countryValue(m, metric, cc, lookalike);
  const p = palette(theme);
  if (v.status === "value") {
    const spec = METRICS[metric];
    return { fill: spec.classes ? p.plan[v.value] : p[spec.ramp][v.bin], key: `b${v.bin}` };
  }
  if (v.status === "not_counted") return { fill: p.notCounted, key: "other" };
  return { fill: HATCH, key: "none" };
}

export function legendItems(metric, theme = "light") {
  const spec = METRICS[metric];
  const p = palette(theme);
  const items = spec.classes
    ? spec.classes.map((g, i) => ({ key: `b${i}`, label: GROUP_LABEL[g], color: p.plan[g] }))
    : spec.labels.map((label, i) => ({ key: `b${i}`, label, color: p[spec.ramp][i], detail: spec.details?.[i] }));
  if (spec.byLookalike) items.push({ key: "none", label: "No score (too little Qloo data)", pattern: true });
  else items.push({ key: "other", label: "Not counted for any of the 14 languages", color: p.notCounted });
  return items;
}

/** A value for lists and tooltips: fan interest 0.55, "+16%" against usual, a share, or the plan's group. */
export function formatValue(metric, value) {
  if (value == null) return "no score";
  if (metric === "affinity") return value.toFixed(2);
  if (metric === "relative") return relativeShort(value);
  if (metric === "demand") return pct(value);
  return GROUP_LABEL[value] || String(value);
}

/** Every country with something to show, highest value first (no-score and not-counted ones after, by name). */
export function countryList(m, metric, lookalike, nameOf) {
  const codes = Object.keys(m.map?.countries || {});
  const rows = codes.map((cc) => ({ cc, name: nameOf(cc), ...countryValue(m, metric, cc, lookalike) }));
  const order = (r) => (r.status === "value" ? 0 : r.status === "no_reference" ? 1 : 2);
  const sortable = (r) => (METRICS[metric].classes ? -r.bin : r.value);
  rows.sort((a, b) => order(a) - order(b) || (order(a) === 0 ? sortable(b) - sortable(a) : 0)
    || a.name.localeCompare(b.name));
  return rows;
}

/** Countries Babel counts for a language, and the other countries where it is official (display only). */
export function languageCountries(m, code) {
  const lang = m.map?.languages?.[code];
  if (!lang) return { model: [], officialOnly: [] };
  return { model: lang.countries, officialOnly: lang.official_in.filter((cc) => !lang.countries.includes(cc)) };
}

/**
 * How sure the plan is about a language: how many games like yours have Qloo data for its countries and whether
 * they point the same way. {level: "agree" | "partial" | "mixed" | "none", text (plain), range (exact, "×0.87 to ×1.10")}.
 */
export function confidence(row, total) {
  const n = row.lookalikes_with_data;
  const [lo, hi] = row.lift_range || [];
  const range = lo == null ? null : lo === hi ? `×${lo.toFixed(2)}` : `×${lo.toFixed(2)} to ×${hi.toFixed(2)}`;
  if (!n) return { level: "none", text: "No Qloo data for its countries: the usual share only", range };
  if (lo < 1 && hi > 1) {
    return { level: "mixed", text: `Games like yours disagree (${off(lo)}% fewer to ${off(hi)}% more fans)`, range };
  }
  const way = lo >= 1 ? "more" : "fewer";
  if (n < total) return { level: "partial", text: `${n} of ${total} games like yours have data here: ${way} fans`, range };
  return { level: "agree", text: n === 1 ? `Based on 1 game like yours (${way} fans)` : `All ${n} games like yours agree: ${way} fans there`, range };
}

/** The plan in one sentence and a subtitle, for the current groups and costs. */
export function headline(status, groups, costs) {
  const names = (codes) => listText(codes.map((c) => LANG[c] || c));
  const full = groups.translate_game;
  const store = groups.store_page_only;
  const spend = `Estimated cost: ${fmtMoney(costs.total)} of your ${fmtMoney(costs.budget)} budget.`;
  if (full.length) {
    return { title: `Translate ${names(full)}.`,
      sub: `${store.length ? `Then translate just the store pages for ${names(store)}.` : "No store pages fit in what is left."} ${spend}` };
  }
  if (store.length) return { title: `Start with store pages for ${names(store)}.`, sub: `No full translation fits yet. ${spend}` };
  if (status === "nothing_to_translate") {
    return { title: "Your game already speaks the languages that matter.",
      sub: "Every other language is already in your game or has too few likely players." };
  }
  return { title: "Nothing fits this budget yet.", sub: spend };
}

function fmtMoney(x) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(x);
}
