// The Track record screen (TASK 11): the pre-registered backtest from GET /track-record, which the server recomputes
// from the frozen files in backtest/data (with their SHA-256). It leads with how much of the real non-English audience
// Babel's top 3 languages reached against the usual list, on both measures; then what Qloo adds (the Wikipedia test);
// a game-by-game explorer; and how the test worked (collapsed). Every number comes from the server; this file selects and formats. Text is always inserted as text, never as HTML.

import { $, $$, api, errorText, fmtInt, h, listText } from "./ui.js";

const TRUTHS = ["wikipedia_pageviews", "steam_reviews"];  // display order
const QLOO = "wikipedia_pageviews";  // "What Qloo adds" reads this measure's test
const SMALL = "steam_reviews";       // the small-indie test, described in "How the test worked"
const LABEL = { wikipedia_pageviews: "Wikipedia page views", steam_reviews: "Steam reviews" };
const GAMES = { wikipedia_pageviews: "well-known games", steam_reviews: "small indie games" };
const UNIT = { wikipedia_pageviews: "page views", steam_reviews: "reviews" };
const MEASURE = { wikipedia_pageviews: "Measured by the Wikipedia language editions where these games' pages were read.",
  steam_reviews: "Measured by the languages of these English-only games' Steam reviews." };
// The game table: Babel and the usual list (one ranking for every game)
const DETAIL = [["babel", "Babel"], ["generic", "Usual list"]];

const t = { opts: null, opener: null, data: null, loading: null, truth: QLOO, selected: {}, filter: "all" };

// ---------------------------------------------------------------- formatting (the report's own precision)
const pct1 = (x) => `${(x * 100).toFixed(1)}%`;
const minus = (s) => s.replace(/^-/, "−");
const pts = (x) => minus(`${x > 0 ? "+" : ""}${(x * 100).toFixed(1)}`);
const pText = (p) => (p < 0.001 ? "< 0.001" : `= ${p.toFixed(p < 0.1 ? 3 : 2)}`);
const pKept = (p) => `p ${pText(p)}`.replace(/ /g, "\u00a0");  // "p = 0.50", never split over two lines
const plural = (n, word, many = `${word}s`) => `${fmtInt.format(n)} ${n === 1 ? word : many}`;
const lead = (g) => g.scores.babel.coverage - g.scores.generic.coverage;
const outcome = (g) => (lead(g) > 1e-12 ? "better" : lead(g) < -1e-12 ? "worse" : "tie");  // vs the usual list
const luck = (p) => (p < 0.001 ? "very unlikely to be luck" : p < 0.05 ? "unlikely to be luck" : "could be luck");
const abs1 = (x) => (Math.abs(x) * 100).toFixed(1);

/** A 95% interval of a coverage gain in words: "between 0.1 and 5.4 points better". */
function between(lo, hi) {
  if (lo >= 0) return `between ${abs1(lo)} and ${abs1(hi)} points better`;
  if (hi <= 0) return `between ${abs1(hi)} and ${abs1(lo)} points worse`;
  return `between ${abs1(lo)} points worse and ${abs1(hi)} points better`;
}

/** Babel's and the usual list's top-3 coverage on one measure, and how many times more Babel reached. */
function reach(tr) {
  const cov = (key) => tr.competitors.find((c) => c.key === key).top3_coverage;
  const babel = cov("babel");
  const usual = cov("generic");
  return { babel, usual, ratio: babel / usual };
}

/** The usual list's first three languages, in words ("Chinese, Japanese and Korean"). */
function usualFirst(tr) {
  const label = Object.fromEntries(tr.languages.map((l) => [l.code, l.label]));
  return listText(tr.generic_ranking.slice(0, 3).map((c) => label[c]));
}

function chip(text, cls = "src-ref") {
  return h("span", { class: `src ${cls}`, text });
}

// ---------------------------------------------------------------- open, load, states
/** Show the Track record screen. opts = {onBack}. */
export async function openTrackRecord(opts) {
  t.opts = opts;
  const view = $("#view-track");
  if (!view.contains(document.activeElement)) t.opener = document.activeElement;  // focus returns here on Back
  if (!$("#track-title", view)) view.replaceChildren(shell());
  $("#track-title").focus();
  if (!t.data) await load();
}

function shell() {
  return h("div", { class: "tr-page" },
    h("header", { class: "tr-head" },
      h("button", { type: "button", id: "track-back", class: "button button-secondary button-small",
        onclick: back }, h("span", { "aria-hidden": "true", text: "← " }), "Back"),
      h("p", { class: "eyebrow", text: "Track record" }),
      h("h1", { id: "track-title", class: "display display-page", tabindex: "-1",
        text: "How Babel's language picks did on real games" }),
      h("p", { id: "track-sub", class: "tr-sub", text: "We tested Babel on real games released since 2023, with rules "
        + "written down before any result was seen." }),
      h("ul", { class: "plan-chips tr-chips", "aria-label": "About this test" },
        ["Rules fixed in advance", "Scored once on test games", "Data and fingerprints published"].map((text) =>
          h("li", { class: "chip-info" }, h("span", { class: "chip-dot", "aria-hidden": "true" }), text)))),
    h("div", { id: "track-body", class: "tr-body" }));
}

function back() {
  t.opts?.onBack?.();
  const opener = t.opener;
  if (opener?.isConnected && opener !== document.body && opener.getClientRects().length) opener.focus();
}

async function load() {
  if (t.loading) return t.loading;
  const retried = document.activeElement?.id === "track-retry";  // read before the button is replaced
  const body = $("#track-body");
  body.replaceChildren(h("div", { class: "tr-state", role: "status" },
    h("span", { class: "spinner", "aria-hidden": "true" }), "Loading the track record…"),
  h("div", { class: "tr-skeleton", "aria-hidden": "true" }, h("span"), h("span")));
  t.loading = api("GET", "/track-record");
  const r = await t.loading;
  t.loading = null;
  if (!r.ok) {
    body.replaceChildren(h("div", { class: "tr-state is-bad", role: "alert" },
      h("p", { class: "tr-state-title", text: "The track record could not load." }),
      h("p", { text: errorText(r) }),
      h("button", { type: "button", id: "track-retry", class: "button button-primary", onclick: load }, "Try again")));
    if (retried) $("#track-retry").focus();
    return;
  }
  t.data = r.data;
  render();
  if (retried || document.activeElement === document.body) $("#track-title").focus();
}

function render() {
  const d = t.data;
  const games = TRUTHS.reduce((n, k) => n + d.truths[k].babel_vs_typical_mix.games, 0);
  $("#track-sub").textContent = `We tested Babel on ${plural(games, "real game")} released since 2023. The rules were `
    + "written down before any result was seen, and two independent measures showed where non-English players "
    + "really turned up: Wikipedia page views and Steam reviews.";
  $("#track-body").replaceChildren(results(d), qloo(d), explorer(), method(d));
  renderExplorer();
}

// ---------------------------------------------------------------- the headline: Babel vs the usual list
function results(d) {
  const times = [...new Set(TRUTHS.map((k) => Math.round(reach(d.truths[k]).ratio)))].sort((a, b) => a - b)
    .join(" to ");
  return h("section", { class: "tr-summary", "aria-labelledby": "tr-results-title" },
    h("div", { class: "tr-summary-head" },
      h("p", { class: "eyebrow", text: "The result, on both measures" }),
      h("h2", { id: "tr-results-title", class: "section-title tr-verdict-title",
        text: `About ${times}× the reach of the usual list` }),
      h("p", { class: "tr-about", text: `For each test game, the 3 languages Babel ranked first reached about ${times} `
        + "times as much of its real non-English audience as the usual list, the copy-pasted list most guides give "
        + `(${usualFirst(d.truths[QLOO])} first).` })),
    h("div", { class: "tr-verdicts" }, TRUTHS.map((k) => statCard(k, d.truths[k]))));
}

function statCard(key, tr) {
  const r = reach(tr);
  const id = `tr-card-${key}`;
  return h("article", { class: "panel-card tr-verdict", "data-truth": key, "aria-labelledby": id },
    h("div", { class: "tr-card-top" },
      h("h3", { id, class: "tr-card-title" }, h("span", { class: "tr-card-measure", text: LABEL[key] }),
        h("span", { class: "tr-card-games", text: `${plural(tr.babel_vs_typical_mix.games, "game")}, ${GAMES[key]}` })),
      h("p", { class: "tr-ratio" }, h("strong", { text: `${r.ratio.toFixed(1)}×` }), " the usual list")),
    h("p", { class: "tr-hero" }, h("span", { class: "tr-hero-value", text: pct1(r.babel) }),
      h("span", { class: "tr-hero-label", text: `of each game's non-English ${UNIT[key]}, on average, were in the 3 `
        + "languages Babel ranked first" })),
    h("ul", { class: "tr-compare", "aria-label": `Top-3 coverage on ${LABEL[key]}` },
      compareRow("Babel", r.babel, "babel"), compareRow("The usual list", r.usual, "generic")),
    h("p", { class: "tr-card-note", text: MEASURE[key] }));
}

function compareRow(name, value, key) {
  const fill = h("span", { class: "tr-compare-fill" });
  fill.style.width = `${value * 100}%`;  // CSSOM: allowed by the page's CSP; the scale is 0 to 100%
  return h("li", { class: `tr-compare-row is-${key}`, "data-key": key },
    h("span", { class: "tr-compare-name", text: name }),
    h("span", { class: "tr-compare-value", text: pct1(value) }),
    h("span", { class: "tr-compare-track", "aria-hidden": "true" }, fill));
}

// ---------------------------------------------------------------- what Qloo adds (the Wikipedia test)
function qloo(d) {
  const tr = d.truths[QLOO];
  const x = tr.babel_vs_typical_mix;
  const title = x.worse > 0
    ? `Qloo's fan maps improved Babel's picks ${(x.better / x.worse).toFixed(1)} times as often as they hurt them`
    : `Qloo's fan maps improved Babel's picks for ${plural(x.better, "game")} and hurt none`;
  return h("section", { class: "panel-card tr-qloo", "data-truth": QLOO, "aria-labelledby": "tr-qloo-title" },
    h("div", { class: "tr-qloo-text" },
      h("p", { class: "eyebrow tr-eyebrow" }, "What Qloo adds", " ",
        chip(`${LABEL[QLOO]} · ${plural(x.games, "game")}`)),
      h("h2", { id: "tr-qloo-title", class: "section-title", text: title }),
      h("p", { class: "tr-about", text: "Babel ranks languages in two steps: a starting point from data (each "
        + "language's usual share across games), then Qloo's fan maps of games like yours. Game by game, we compared "
        + "Babel's top 3 with the starting point's." })),
    h("div", { class: "tr-qloo-figures" }, counts(x),
      h("ul", { class: "tr-facts" },
        fact(x.significant, [`${luck(x.sign_test_p).replace(/^./, (c) => c.toUpperCase())} `,
          h("span", { class: "tr-p", text: `(${pKept(x.sign_test_p)})` })]),
        fact(true, ["Verdict under the rules fixed in advance: ", h("strong", { text: tr.verdict })]))));
}

function counts(x) {
  const parts = [["better", "▲", "Better"], ["tie", "=", "The same"], ["worse", "▼", "Worse"]];
  const bar = h("div", { class: "tr-btw-bar", "aria-hidden": "true" }, parts.map(([k, , word]) => {
    const seg = h("span", { class: `tr-btw-seg is-${k}`, title: `${x[k]} games: ${word.toLowerCase()}` });
    seg.style.flexGrow = String(x[k]);  // CSSOM: allowed by the page's CSP
    return seg;
  }));
  return h("div", { class: "tr-btw" },
    h("p", { class: "tr-btw-title", text: "Babel's top 3 with Qloo, against the starting point" }),
    h("ul", { class: "tr-counts" }, parts.map(([k, mark, word]) =>
      h("li", { class: `is-${k}`, "data-count": k },
        h("span", { class: "tr-count-label" }, h("span", { class: "tr-count-mark", "aria-hidden": "true", text: mark }),
          ` ${word}`),
        h("strong", { class: "tr-count-value", text: fmtInt.format(x[k]) }),
        h("span", { class: "tr-count-unit", text: x[k] === 1 ? "game" : "games" })))),
    bar);
}

function fact(ok, body) {
  return h("li", { class: ok ? "is-yes" : "is-no" },
    h("span", { class: "tr-fact-mark", "aria-hidden": "true", text: ok ? "✓" : "·" }), h("span", {}, body));
}

// ---------------------------------------------------------------- predicted vs observed, game by game
function explorer() {
  const d = t.data;
  const search = h("input", { id: "tr-search", type: "search", autocomplete: "off", placeholder: "e.g. Hades",
    "aria-controls": "tr-game-list", "aria-describedby": "tr-count" });
  search.addEventListener("input", renderList);
  search.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown") return;
    e.preventDefault();
    $(".tr-game-row", $("#tr-game-list"))?.focus();
  });
  return h("section", { class: "panel-card tr-games", "aria-labelledby": "tr-games-title" },
    h("p", { class: "eyebrow tr-eyebrow", text: "Babel's picks vs what really happened" }),
    h("h2", { id: "tr-games-title", class: "section-title", text: "Game by game" }),
    h("p", { class: "tr-about", text: "Pick a test game to see Babel's ranking next to where its non-English players "
      + "really showed up. The examples are picked by a fixed rule, not by hand." }),
    h("fieldset", { class: "metric-switch tr-truth-switch" },
      h("legend", { class: "visually-hidden", text: "Measure" }),
      TRUTHS.map((k) => {
        const input = h("input", { type: "radio", name: "tr-truth", value: k, class: "visually-hidden",
          onchange: () => { t.truth = k; t.filter = "all"; renderExplorer(); } });
        input.checked = k === t.truth;
        return h("label", { class: "metric-option" }, input, h("span", { class: "metric-name", text: LABEL[k] }),
          h("span", { class: "metric-src", text: `${plural(d.truths[k].games.length, "game")}, ${GAMES[k]}` }));
      })),
    h("div", { id: "tr-examples", class: "tr-examples", role: "group", "aria-label": "Examples" }),
    h("div", { class: "tr-games-body" },
      h("div", { class: "tr-browse" },
        h("label", { class: "panel-label", for: "tr-search", text: "Find a test game" }), search,
        h("p", { id: "tr-count", class: "help", "aria-live": "polite" }),
        h("ul", { id: "tr-game-list", class: "tr-game-list", "aria-label": "Test games" })),
      h("div", { id: "tr-game", class: "tr-game", "aria-labelledby": "tr-game-title", role: "region" })),
    h("p", { id: "tr-game-live", class: "visually-hidden", "aria-live": "polite" }));
}

function truthData() {
  return t.data.truths[t.truth];
}

/** Rule-picked examples (each a different game): the median game for Babel and its largest lead over the usual
 * list. */
function examples(games) {
  const by = (f) => [...games].sort((a, b) => f(b) - f(a) || a.name.localeCompare(b.name));
  const median = by((g) => g.scores.babel.coverage);
  const rules = [["Typical result for Babel", [median[Math.floor((median.length - 1) / 2)]]],
    ["Biggest lead over the usual list", by(lead)]];
  const used = new Set();
  return rules.map(([label, ranked]) => {
    const g = ranked.find((x) => !used.has(x.appid));
    used.add(g.appid);
    return [label, g];
  });
}

function renderExplorer() {
  const tr = truthData();
  const picks = examples(tr.games);
  t.selected[t.truth] ??= picks[0][1].appid;
  $("#tr-examples").replaceChildren(h("span", { class: "tr-examples-label", text: "Examples" }),
    ...picks.map(([label, g]) => h("button", { type: "button", class: "pill tr-example", "data-appid": String(g.appid),
      onclick: () => select(g.appid, { focusDetail: true }) }, h("span", { class: "tr-example-rule", text: label }),
    h("span", { class: "tr-example-name", text: g.name }))));
  renderList();
  renderGame();
}

function renderList() {
  const tr = truthData();
  const q = $("#tr-search").value.trim().toLowerCase();
  const games = [...tr.games].sort((a, b) => a.name.localeCompare(b.name))
    .filter((g) => !q || g.name.toLowerCase().includes(q));
  const list = $("#tr-game-list");
  list.replaceChildren(...games.map((g) => {
    const o = outcome(g);
    const mark = { better: "▲", tie: "=", worse: "▼" }[o];
    return h("li", {}, h("button", { type: "button", class: "tr-game-row", "data-appid": String(g.appid),
      "aria-pressed": String(g.appid === t.selected[t.truth]), onclick: () => select(g.appid) },
    h("span", { class: "tr-game-name", text: g.name }),
    h("span", { class: "tr-game-meta", text: `Babel ${pct1(g.scores.babel.coverage)} · usual list `
      + `${pct1(g.scores.generic.coverage)}` }),
    h("span", { class: `delta delta-${o === "better" ? "up" : o === "worse" ? "down" : "same"} tr-game-delta`,
      text: o === "tie" ? "= same" : `${mark} ${pts(lead(g))}` })));
  }));
  $("#tr-count").textContent = games.length ? `${plural(games.length, "game")}${q ? " match" : ""}`
    : "No test game matches.";
  list.onkeydown = (e) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    const rows = $$(".tr-game-row", list);
    const i = rows.indexOf(document.activeElement);
    e.preventDefault();
    if (e.key === "ArrowUp" && i <= 0) return $("#tr-search").focus();
    const next = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: rows.length - 1 }[e.key];
    rows[Math.max(0, Math.min(rows.length - 1, next))]?.focus();
  };
}

function select(appid, { focusDetail = false } = {}) {
  t.selected[t.truth] = appid;
  for (const row of $$(".tr-game-row")) row.setAttribute("aria-pressed", String(Number(row.dataset.appid) === appid));
  renderGame();
  if (focusDetail) $("#tr-game-title").focus();
}

function renderGame() {
  const tr = truthData();
  const g = tr.games.find((x) => x.appid === t.selected[t.truth]) || tr.games[0];
  $("#tr-game").replaceChildren(...gameDetail(tr, g));
  $("#tr-game-live").textContent = `Showing ${g.name}.`;
}

function gameDetail(tr, g) {
  const label = Object.fromEntries(tr.languages.map((l) => [l.code, l.label]));
  const ranking = { babel: g.rankings.babel, generic: tr.generic_ranking };
  const observedTop = new Set(g.real_top3);
  const codes = tr.languages.map((l) => l.code).sort((a, b) => g.observed_share[b] - g.observed_share[a]
    || observedTop.has(label[b]) - observedTop.has(label[a]));
  const top = Math.max(...codes.map((c) => g.observed_share[c]), 1e-9);
  const few = g.observed_n < tr.sample.small_sample_below;
  const hits = Math.round(g.scores.babel.hit3 * 3);
  return [
    h("h3", { id: "tr-game-title", class: "panel-title", tabindex: "-1", text: g.name }),
    h("p", { class: "help tr-game-facts", text: [g.released ? `Released ${g.released}` : null,
      `${g.released ? "based on" : "Based on"} ${fmtInt.format(g.observed_n)} ${tr.observed_unit}`]
      .filter(Boolean).join(" · ") }),
    few ? h("p", { class: "help tr-small", text: `Few ${UNIT[t.truth]} (under `
      + `${fmtInt.format(tr.sample.small_sample_below)}), so this game's real shares are rough.` }) : null,
    h("dl", { class: "tr-game-stats", "aria-label": "Share reached by each top 3, for this game" },
      DETAIL.map(([k, name]) => h("div", { class: k === "babel" ? "is-babel" : null },
        h("dt", { text: k === "generic" ? "The usual list" : name }),
        h("dd", { "data-key": k, text: pct1(g.scores[k].coverage) })))),
    h("p", { class: "help", text: "How much of this game's real non-English audience each top 3 reached." }),
    h("p", { class: "tr-match" }, `Real top 3: ${listText(g.real_top3)}. Babel's top 3: ${listText(g.babel_top3)}, `,
      h("strong", { text: `${hits} of 3` }), " of them in the real top 3."),
    h("div", { class: "table-wrap" }, h("table", { class: "tr-game-table" },
      h("caption", { class: "visually-hidden", text: `${g.name}: real share and each ranking, by language` }),
      h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Language" }),
        h("th", { scope: "col", text: "Real share" }),
        DETAIL.map(([k, name]) => h("th", { scope: "col", class: "num", "data-key": k, text: name })))),
      h("tbody", {}, codes.map((code) => {
        const share = g.observed_share[code];
        const fill = h("span", { class: "tr-share-fill" });
        fill.style.width = `${(share / top) * 100}%`;
        const isTop = observedTop.has(label[code]);
        return h("tr", { "data-lang": code, class: isTop ? "is-observed-top" : null },
          h("th", { scope: "row" }, label[code], isTop ? h("span", { class: "tr-tag", text: "real top 3" }) : null),
          h("td", { class: "tr-share" }, h("span", { class: "tr-share-cell" },
            h("span", { class: "tr-share-track", "aria-hidden": "true" }, fill),
            h("span", { class: "tr-share-value", text: pct1(share) }))),
          DETAIL.map(([k, name]) => {
            const r = ranking[k].indexOf(code) + 1;
            return h("td", { class: "num", "data-key": k, "data-label": name },
              h("span", { class: `tr-rank${r <= 3 ? " is-top" : ""}`, text: `#${r}` }),
              r <= 3 ? h("span", { class: "visually-hidden", text: " (top 3)" }) : null);
          }));
      })))),
    h("p", { class: "help", text: "How to read it: #1 is the language a list would translate first, and highlighted "
      + `ranks are its top 3. Real share is how this game's ${tr.observed_unit} split across the languages. The `
      + "usual list does not change from game to game." }),
    lookalikeNote(g),
  ].filter(Boolean);
}

function lookalikeNote(g) {
  if (!g.lookalikes.length) {
    return h("p", { class: "help", text: "No game like it had a Qloo fan map, so Babel's ranking here is the "
      + "starting point." });
  }
  const names = listText(g.lookalikes.map((x) => x.name));
  if (g.untagged) {
    return h("p", { class: "help", text: "This game had no Steam tags in the test data, so it was matched to the same "
      + `games as the other untagged games: ${names}. Babel now requires games like yours to share a Steam tag.` });
  }
  return h("p", { class: "help", text: "To rank languages for this game, Babel looked at where Qloo says fans of these "
    + `similar games are: ${listText(g.lookalikes.map((x) => `${x.name} (tag match ${x.overlap.toFixed(2)} out of 1)`))}`
    + ". Similar means they share Steam tags with this game; a rare tag counts for more than a common one." });
}

// ---------------------------------------------------------------- how the test worked (collapsed)
function method(d) {
  const w = d.truths[QLOO];
  const wx = w.babel_vs_typical_mix;
  const sx = d.truths[SMALL].babel_vs_typical_mix;
  const total = TRUTHS.reduce((n, k) => n + d.truths[k].babel_vs_typical_mix.games, 0);
  const defs = [
    ["Rules fixed in advance", "The plan, the measures and the pass mark were written down in "
      + "backtest/PREREGISTRATION.md before any result was seen. Babel's settings were chosen on separate dev games; "
      + `the ${fmtInt.format(total)} test games were scored once.`],
    ["Top-3 coverage", "For each test game, the share of its real non-English page views or reviews that fall in the "
      + "3 languages a method ranks first, averaged over the games. If a game's non-English audience were 30% Russian, "
      + "20% Spanish and 10% German, a top 3 of Russian, German and Japanese would reach 40%."],
    ["The usual list and the starting point", `The usual list is the copy-pasted list most guides give, with `
      + `${usualFirst(w)} first; both measures under-count players of those three languages. The starting point is `
      + "Babel without Qloo: each language's average share across the dev games of the same measure."],
    ["Luck or not: the sign test", "Game by game: did Babel's top 3 reach more, the same or less than the starting "
      + "point? Ties are set aside, and the test asks whether “more” happens more often than luck would give. On "
      + `${LABEL[QLOO]}: ${pKept(wx.sign_test_p)}, ${luck(wx.sign_test_p)} (under ${d.alpha} counts as `
      + "statistically significant)."],
    ["Likely range", `We re-drew the test games at random ${fmtInt.format(wx.bootstrap_resamples)} times (a `
      + `bootstrap). On ${LABEL[QLOO]}, Qloo's fan maps added ${pts(wx.mean_difference)} points on average, likely `
      + `${between(...wx.ci95)} (95% interval).`],
  ];
  return h("section", { class: "tr-method", "aria-label": "How the test worked" },
    h("details", { class: "panel-card tr-how" },
      h("summary", {}, h("span", { class: "tr-how-text" }, h("span", { class: "tr-how-title", text: "How the test worked" }),
        h("span", { class: "tr-how-hint", text: "The rules, the measures and the statistics" })),
      h("span", { class: "tr-how-icon", "aria-hidden": "true" })),
      h("div", { class: "tr-how-body" },
        h("dl", { class: "tr-defs" }, defs.map(([k, v]) => h("div", {}, h("dt", { text: k }), h("dd", { text: v })))),
        h("div", { class: "tr-how-notes" },
          h("p", { "data-note": "small-indie", text: `On the ${sx.games} small indie games (the Steam reviews test), `
            + `Qloo's own addition was small (${pts(sx.mean_difference)} points vs the starting point) and not `
            + `statistically significant (${pKept(sx.sign_test_p)}).` }),
          h("p", { "data-note": "not-sales", text: "Both measures are signs of demand, not sales." })))));
}
