// The guided walkthrough (static/tour.css): a spotlight and a popover that walk through the whole product over the
// real UI. It runs the real WEBFISHING demo with the same buttons and actions a person uses (actions.js) and waits for
// the server's real events, so it never shows progress or numbers of its own: every number on screen comes from the
// server. A step whose target is missing is skipped after a short wait; a demo that cannot run ends the tour with a
// plain message. Text is always inserted as text.

import { $, $$, GROUP_LABEL, h, reducedMotion } from "./ui.js";
import { perform } from "./actions.js";
import { METRIC_ORDER, METRICS } from "./mapdata.js";

const DEMO_APPID = "3146520";  // WEBFISHING: its plan is cached locally
const DEMO_VALUES = { "#words": "30000", "#budget": "10000" };  // the form's standard values, as the cached demo ran
const WAIT = { target: 2500, lookup: 30000, enable: 8000, run: 120000, page: 15000 };  // ms
const STORE_KEY = "babel.tour";  // localStorage: "seen" once the invitation is dismissed or the tour is taken
const GAP = 14;  // px between a target and the popover
const EDGE = 12;  // px kept free at the viewport's edges
const PAD = 6;  // px of spotlight around a target
const MIN_SIDE = 280;  // the narrowest popover placed beside a target

class Stale extends Error {}  // the tour moved on or ended while a step was getting ready
class Stop extends Error {}  // the demo cannot run: say so and end

const tour = { active: false, ui: null, steps: [], index: -1, token: 0, opener: null, busy: false, failed: false,
  spec: null, targets: [], key: "", version: 0, raf: 0, timers: [], busyTimer: 0, found: false, filled: false,
  ran: false, opened: false };

// ---------------------------------------------------------------- the steps
const STEPS = [
  { id: "welcome", title: "Welcome to Babel",
    body: "Babel tells you which languages to translate your Steam game into, and what that would cost, by looking at "
      + "where fans of games like yours are on Qloo's fan maps. This tour runs a real demo plan and walks you through it.",
    note: "Use the arrow keys to move between steps, and Esc to end the tour at any time." },
  { id: "input", target: "#game-form", prepare: toStart, title: "Three ways in",
    body: () => `Paste your game's Steam link, type its name, or describe a game that has no store page yet. Then press `
      + `${label("#find-button", "Find similar games")} and Babel looks for well-known games like it.` },
  { id: "demo", target: ".strip", prepare: toStart, title: "Try a demo",
    body: () => (tour.found ? "The tour has already loaded the WEBFISHING demo. Next shows the games like it that Babel found."
      : "Each demo runs a real plan. When you press Next, the tour clicks WEBFISHING for you and waits for Babel's "
        + "answer.") },
  { id: "comparables", target: ["#cards", "#rejected-note"], prepare: loadDemo, title: "Games like yours",
    body: "A new game has no fan data of its own yet, so Babel picks well-known games that share its Steam tags and reads "
      + "Qloo's fan maps for them. Swap any that don't feel like your game.",
    note: "Each card says whether Qloo has real fan data for that game; a game without it never counts." },
  { id: "words", target: ["#controls-title", "#plan-form .control"], prepare: fillDemo, title: "Words and budget",
    body: "Tell Babel how many words players read and how much you can spend. Costs are estimates from sample per-word "
      + "prices, not quotes, and the plan never goes over your budget.",
    note: "For the demo, the tour keeps the form's standard values." },
  { id: "run", target: "#run-button", prepare: loadDemo, title: "Run the plan",
    body: () => (tour.ran ? "This demo plan has already run. Next shows its steps again, without running it twice."
      : `Next presses ${label("#run-button", "Run the plan")} for you. Babel then works through its steps, and you watch `
        + "each one as it happens.") },
  { id: "trace", target: ".run-card", prepare: runDemo, title: "Every step, as it happened",
    body: "This is what Babel did for the plan, from finding games like yours to double-checking the plan. Each line "
      + "appeared the moment Babel finished that step.",
    note: () => `On the plan, ${label("#plan-trace", "See every step")} brings you back here.` },
  { id: "headline", target: ".plan-head-text", prepare: toPlan, title: "Your plan in one line",
    body: "The headline says which languages to translate and what that costs (an estimate). The labels under it say "
      + "how many games like yours with Qloo data stand behind the plan, and who wrote its explanation." },
  { id: "map", target: [".explore-head", ".explore-toolbar", "#map-canvas"], prepare: showWorld,
    title: "Where the fans are",
    body: () => "The map colours each country using Qloo's fan maps of games like yours. Switch views above it: "
      + `${views()}.`,
    note: "The note at the top always stays: Qloo shows the combined taste of many fans, never individual players, "
      + "and it can't promise sales." },
  { id: "country", target: "#map-panel", prepare: () => perform({ type: "show_country", country: "JP" }),
    title: "One country: Japan",
    body: "Pick any country on the map or in the list. The panel shows Qloo's data for it, game by game, and the "
      + "language Babel counts it for." },
  { id: "language", target: "#map-panel", prepare: () => perform({ type: "show_language", language: "spanish" }),
    title: "One language: Spanish",
    body: "Pick a language and the map outlines the countries Babel counts for it, each weighted by how many people live "
      + "there. Dashed outlines mark countries where it is also an official language but which Babel leaves out." },
  { id: "plan", target: [".localize-head", ".plan-group-translate_game"], prepare: toPlan,
    title: "Three groups, one budget",
    body: () => `Babel sorts the languages into ${GROUP_LABEL.translate_game}, ${GROUP_LABEL.store_page_only} and `
      + `${GROUP_LABEL.skip}. Move the budget and Babel picks the best mix that fits it again, with no new Qloo or `
      + "Claude calls." },
  { id: "why", target: "#why-dialog", prepare: openWhy, leave: closeWhy, title: "Why this recommendation?",
    body: "Why? shows how Babel got there for any language: the usual share, the Qloo adjustment from each game like "
      + "yours, the share of likely players, the cost and the budget decision. The sources, with Qloo's request IDs, are "
      + "listed at the end." },
  { id: "versus", prepare: toPlan, title: "Babel vs the usual list",
    target: [".versus > .eyebrow", "#versus-title", "#versus-about", "#versus-table thead",
      "#versus-table tbody tr:nth-child(-n+3)"],
    body: "Most advice is one copy-pasted list of languages for every game. This table shows where Babel's ranking for "
      + "your game differs from it, and why." },
  { id: "evidence", target: [".evidence > .eyebrow", "#evidence-title",
    "#evidence-grid > .evidence-card-item:nth-child(-n+2)"],
    prepare: toPlan, title: "What this plan is based on",
    body: "Every game like yours is listed with what Qloo knows about it; games without real fan data are shown but "
      + "never used. The explanation says who wrote it: Claude, citing this evidence, with every number checked by "
      + "Babel's code." },
  { id: "report", target: [".report-toolbar", "#view-report .r-head", "#view-report .r-inputs"],
    prepare: () => perform({ type: "open_report" }), title: "Export report",
    body: () => `${label("#plan-export", "Export report")} turns your plan into one printable page with the same numbers, `
      + "the map and the limits. Print it, or save it as a PDF to share." },
  { id: "track", target: ["#view-track .tr-summary", "#view-track .tr-verdict-title"], prepare: openTrack,
    title: "The track record",
    body: "Babel was tested on real games, with rules written down before any result was seen. Its top languages "
      + "reached about three times more of the real non-English audience than the usual list, and on well-known games "
      + "Qloo's fan maps made its picks better, very unlikely to be luck.",
    note: "Both measures are signs of where players are, not sales." },
  { id: "assistant", target: "#assistant-launcher", when: () => Boolean($("#assistant-launcher")),
    title: "Ask the assistant",
    body: "Ask Babel anything about your plan. It answers from your plan's data, with the numbers checked by Babel's "
      + "code, and can use the app for you: change the budget, show a country, open Why?, export the report.",
    note: "Open it with the Babel button at the side of the screen." },
  { id: "done", prepare: backToPlan, title: "That's Babel",
    body: () => "Your demo plan stays open, so explore it, or plan your own game with "
      + `${label('.nav [data-action="focus-start"]', "Plan a game")}. Replay this tour any time with `
      + `${label('.nav [data-action="tour"]', "Take the tour")} at the top of the page.` },
];

/** A button's current label on the page (the tour names the buttons a person sees), else the fallback. */
function label(sel, fallback) {
  return $(sel)?.textContent.replace(/\s+/g, " ").trim() || fallback;
}

/** The map's views, as the Plan screen names them (mapdata.js): "fans compared with usual, ..., or your plan". */
function views() {
  const names = METRIC_ORDER.map((k) => METRICS[k].label.toLowerCase());
  return `${names.slice(0, -1).join(", ")} or ${names.at(-1)}`;
}

// ---------------------------------------------------------------- what the steps do (the app's own buttons and actions)
const view = () => document.body.dataset.view;

async function toStart() {
  if (view() !== "start") await perform({ type: "go_start" });
}

function demoLoaded() {
  return tour.found && !$("#setup").hidden && $$("#cards .card").length > 0
    && $("#game-input").value.includes(DEMO_APPID);
}

/** Click the WEBFISHING demo (unless the tour already did) and wait for the server's comparable games. */
async function loadDemo(ctx) {
  await toStart();
  if (demoLoaded()) return;
  const tab = $(`.strip-tab[data-demo-appid="${DEMO_APPID}"]`);
  if (!tab) throw new Stop("The WEBFISHING demo isn't on this page, so the tour can't run it.");
  ctx.busy("Finding games like WEBFISHING",
    "The tour clicked WEBFISHING. Babel is looking for well-known games like it that Qloo has data for.", ".strip");
  tab.click();  // app.js marks the Find button busy at once, until the server answers
  const find = $("#find-button");
  if (!(await ctx.wait(() => find.getAttribute("aria-busy") !== "true", WAIT.lookup))) {
    throw new Stop("Babel took too long to find games like WEBFISHING for the demo.");
  }
  const error = $("#game-error");
  if (!error.hidden && error.textContent) throw new Stop(`The demo couldn't start: ${error.textContent}`);
  if (!(await ctx.wait(() => !$("#setup").hidden && $("#cards .card"), WAIT.target))) {
    throw new Stop("Babel found no games like WEBFISHING for the demo.");
  }
  tour.found = true;
}

/** The demo's inputs: the form's standard values (once, so a person's own changes during the tour are kept). */
async function fillDemo(ctx) {
  await loadDemo(ctx);
  if (tour.filled) return;
  for (const [sel, value] of Object.entries(DEMO_VALUES)) {
    const input = $(sel);
    if (input.value === value) continue;
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));  // app.js syncs the chips and the slider
  }
  for (const sel of ["#opt-markets", "#opt-explain"]) $(sel).checked = true;
  tour.filled = true;
}

/** Press Run the plan (once), wait for the server's result, then show that run's trace. */
async function runDemo(ctx) {
  if (!tour.ran) {
    await fillDemo(ctx);
    const run = $("#run-button");
    if (!(await ctx.wait(() => !run.disabled, WAIT.enable))) {
      throw new Stop("Babel can't run a plan right now. Wait a moment, then take the tour again.");
    }
    ctx.busy("Running the plan", "Babel is working on the plan. Each line of the checklist appears when Babel "
      + "finishes that step.", ".run-card");
    run.click();
    if (view() !== "working") {
      const error = $$("#plan-form .field-error").find((e) => !e.hidden && e.textContent);
      throw new Stop(`The demo couldn't run: ${error ? error.textContent : "the form was not accepted."}`);
    }
    const outcome = $("#run-outcome");
    const end = await ctx.wait(() => (view() === "plan" ? "plan"
      : view() === "working" && !outcome.hidden ? "stopped" : null), WAIT.run);
    if (end !== "plan") {
      throw new Stop(end ? `The demo plan didn't finish: ${$("p", outcome)?.textContent || "the run stopped."}`
        : "The demo plan is taking too long, so the tour stopped here. The plan opens by itself when it is ready.");
    }
    tour.ran = true;
  }
  if (view() !== "working") $("#plan-trace").click();
}

async function toPlan() {
  if (view() === "plan") return;
  const back = $$("#run-outcome button").find((b) => b.textContent === "Back to the plan");
  if (view() === "working" && back) back.click();
  else await perform({ type: "reset_map" });  // the plan actions open the Plan screen first
}

async function backToPlan() {
  await toPlan();
  window.scrollTo({ top: 0, behavior: "instant" });
}

async function showWorld(ctx) {
  await toPlan();
  if ($("#panel-title")?.textContent !== "All countries") await perform({ type: "reset_map" });
  await ctx.wait(() => $("#map-canvas").dataset.state !== "loading", 4000);
}

async function openWhy() {
  await toPlan();
  const code = $(".plan-group-translate_game .lang-row")?.dataset.lang || "russian";
  tour.opened = true;
  await perform({ type: "open_why", language: code });
}

function closeWhy() {
  const dialog = $("#why-dialog");
  tour.opened = false;
  if (dialog?.open) dialog.close();
}

async function openTrack(ctx) {
  if (view() !== "track") await perform({ type: "open_track_record" });
  await ctx.wait(() => $("#view-track .tr-verdict") || $("#view-track .tr-state.is-bad"), WAIT.page);
  if (!$("#view-track .tr-verdict")) throw new Error("The track record did not load.");
}

/** The tour needs the whole page: close the assistant's panel (a modal sheet on narrow screens) with its own button. */
function closeAssistant() {
  const panel = $("#assistant-panel");
  if (panel && !panel.hidden && visible(panel)) $('#assistant-panel [aria-label="Close the assistant"]')?.click();
}

/** Is Babel's server ready? null if so, else what to tell the person. */
async function checkReady() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const res = await fetch("/health/ready", { signal: controller.signal });
    let data = {};
    try { data = await res.json(); } catch { /* not JSON */ }
    if (res.ok && data.ready) return null;
    const checks = data.checks || {};
    const failed = String(checks.runtime_data || "").startsWith("failed") || checks.qloo_key_configured === false;
    return failed ? "Babel couldn't load its data, so the tour can't run its demo. Please try again later."
      : "Babel is still loading its data, so the tour can't run its demo yet. Take the tour again in a moment.";
  } catch {
    return "The tour can't reach the Babel server. Check your connection, then take the tour again.";
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------- start, move, end
/** Start (or restart) the tour. Resolves once the server's readiness is known. */
export function startTour() {
  const opener = tour.active ? tour.opener : document.activeElement;
  if (tour.active) endTour({ restore: false });
  remember();
  $(".tour-invite")?.remove();
  closeAssistant();
  mount(opener);
  tour.steps = STEPS.filter((s) => !s.when || s.when());
  show(0, []);
  busy(true);
  const token = tour.token;
  return checkReady().then((problem) => {
    if (token !== tour.token) return;
    if (problem) fail(problem, null);
    else busy(false);
  });
}

/** End the tour; the app stays as it is (the demo plan stays open). */
export function endTour({ restore = true } = {}) {
  if (!tour.active) return;
  const step = tour.steps[tour.index];
  tour.active = false;
  tour.token += 1;
  cancelAnimationFrame(tour.raf);
  clearTimers();
  clearTimeout(tour.busyTimer);
  if (step?.leave) step.leave();
  if (tour.opened) closeWhy();  // the tour opened it while getting a step ready
  mark([]);
  tour.ui.layer.remove();
  document.documentElement.classList.remove("tour-on");
  document.removeEventListener("keydown", onKey);
  window.removeEventListener("resize", refresh);
  window.removeEventListener("scroll", refresh, { capture: true });
  if (restore) restoreFocus(tour.opener);
}

function move(dir) {
  if (!tour.active) return;
  if (tour.failed) {
    if (dir > 0) endTour();
    return;
  }
  if (tour.busy) return;
  const i = tour.index + dir;
  if (i < 0) return;
  if (i >= tour.steps.length) endTour();
  else go(i, dir);
}

/** Get step `start` ready and show it; a step that can't be shown is skipped in the direction of travel. */
async function go(start, dir) {
  const token = ++tour.token;
  const leaving = tour.steps[tour.index];
  clearTimers();
  busy(true);
  try {
    if (leaving?.leave) await leaving.leave();
    for (const dialog of $$("dialog.dialog[open]")) dialog.close();  // e.g. a Swap dialog left open
    closeAssistant();  // opened by the person during the tour
    for (let i = start; i >= 0 && i < tour.steps.length; i += dir) {
      const step = tour.steps[i];
      if (step.when && !step.when()) continue;
      let els = [];
      try {
        if (step.prepare) await step.prepare(context(i, token));
        check(token);
        if (step.target) els = (await waitFor(() => nonEmpty(resolve(step.target)), WAIT.target, token)) || [];
      } catch (err) {
        if (err instanceof Stale || err instanceof Stop) throw err;
        els = [];  // this step can't be shown here
      }
      check(token);
      if (step.target && !els.length) continue;
      show(i, els);
      return;
    }
    if (dir > 0) endTour();
    else show(0, []);
  } catch (err) {
    if (err instanceof Stale || token !== tour.token) return;
    fail(err instanceof Stop ? err.message : "Something went wrong while getting the next step ready.");
  }
}

function context(i, token) {
  return {
    wait: (fn, ms) => waitFor(fn, ms, token),
    busy: (title, body, target) => {
      check(token);
      interim(i, title, body, target);
    },
  };
}

function check(token) {
  if (token !== tour.token || !tour.active) throw new Stale();
}

async function waitFor(fn, ms, token) {
  const end = Date.now() + ms;
  for (;;) {
    check(token);
    const value = fn();
    if (value) return value;
    if (Date.now() >= end) return null;
    await new Promise((resolve) => { setTimeout(resolve, 80); });
  }
}

const nonEmpty = (list) => (list.length ? list : null);

// ---------------------------------------------------------------- the popover
function build() {
  const ui = {
    spot: h("div", { class: "tour-spot", "aria-hidden": "true" }),
    count: h("p", { id: "tour-count", class: "tour-count" }),
    title: h("h2", { id: "tour-title", class: "tour-title" }),
    body: h("p", { id: "tour-body", class: "tour-body" }),
    note: h("p", { id: "tour-note", class: "tour-note", hidden: true }),
    status: h("p", { class: "tour-status", hidden: true },
      h("span", { class: "spinner", "aria-hidden": "true" }), "Waiting for Babel…"),
    skip: h("button", { type: "button", class: "link-button tour-skip", onclick: () => endTour() }, "Skip tour"),
    back: h("button", { type: "button", class: "button button-secondary button-small tour-back",
      onclick: () => move(-1) }, "Back"),
    next: h("button", { type: "button", class: "button button-primary button-small tour-next",
      onclick: () => move(1) }, "Next"),
    live: h("p", { class: "visually-hidden", "aria-live": "polite" }),
  };
  ui.pop = h("div", { class: "tour-pop", role: "dialog", "aria-modal": "false", "aria-labelledby": "tour-title",
    "aria-describedby": "tour-body tour-note", tabindex: "-1" },
  ui.count, ui.title, ui.body, ui.note, ui.status,
  h("div", { class: "tour-actions" }, ui.skip, h("div", { class: "tour-nav" }, ui.back, ui.next)));
  ui.layer = h("div", { class: "tour-layer", "data-state": "ready" }, ui.spot, ui.pop, ui.live);
  return ui;
}

function mount(opener) {
  tour.ui ??= build();
  tour.token += 1;
  Object.assign(tour, { active: true, opener, index: -1, busy: false, failed: false, spec: null, targets: [],
    key: "", found: false, filled: false, ran: false, opened: false });
  ($("#tour-root") || document.body).append(tour.ui.layer);
  document.documentElement.classList.add("tour-on");
  document.addEventListener("keydown", onKey);
  window.addEventListener("resize", refresh);
  window.addEventListener("scroll", refresh, { capture: true, passive: true });
  tour.raf = requestAnimationFrame(frame);
}

const text = (x) => (typeof x === "function" ? x() : x) || "";

function show(i, els) {
  const { ui } = tour;
  const step = tour.steps[i];
  const first = tour.index === -1;
  tour.index = i;
  busy(false);
  setTargets(step.target || null, els);
  const last = i === tour.steps.length - 1;
  ui.layer.dataset.step = step.id;
  ui.count.textContent = `Step ${i + 1} of ${tour.steps.length}`;
  ui.title.textContent = text(step.title);
  ui.body.textContent = text(step.body);
  ui.note.textContent = text(step.note);
  ui.note.hidden = !ui.note.textContent;
  ui.back.hidden = i === 0;
  ui.skip.hidden = last;
  ui.next.textContent = last ? "Finish" : "Next";
  animate();
  reveal(els);
  sync();
  for (const ms of [450, 1100, 2000]) later(() => reveal(tour.targets), ms);  // after the app's own smooth scrolls
  if (!first) announce(`${ui.count.textContent}: ${ui.title.textContent}. ${ui.body.textContent}`);
  focusPop();
}

/** While a step gets ready (the demo's lookup and run): what is happening, and where. */
function interim(i, title, body, target) {
  const { ui } = tour;
  ui.count.textContent = `Step ${i + 1} of ${tour.steps.length}`;
  ui.title.textContent = title;
  ui.body.textContent = body;
  ui.note.textContent = "";
  ui.note.hidden = true;
  clearTimeout(tour.busyTimer);
  ui.status.hidden = false;
  setTargets(target, resolve(target));
  animate();
  sync();
  announce(`${title}. ${body}`);
  focusPop();
}

function fail(message, note = "Everything else in Babel still works, so you can carry on by yourself.") {
  const { ui } = tour;
  tour.token += 1;
  busy(false);
  tour.failed = true;
  setTargets(null, []);
  ui.layer.dataset.state = "error";
  ui.layer.dataset.step = "error";
  ui.count.textContent = "Tour stopped";
  ui.title.textContent = "The tour can't continue";
  ui.body.textContent = message;
  ui.note.textContent = note || "";
  ui.note.hidden = !note;
  ui.back.hidden = true;
  ui.skip.hidden = true;
  ui.next.textContent = "Close";
  animate();
  sync();
  announce(`The tour can't continue. ${message}`);
  focusPop();
}

function busy(on) {
  const { ui } = tour;
  tour.busy = on;
  ui.layer.dataset.state = on ? "busy" : tour.failed ? "error" : "ready";
  for (const button of [ui.back, ui.next]) {
    if (on) button.setAttribute("aria-disabled", "true");
    else button.removeAttribute("aria-disabled");
  }
  clearTimeout(tour.busyTimer);
  ui.status.hidden = true;
  if (on) {
    tour.busyTimer = setTimeout(() => {
      ui.status.hidden = !tour.busy;
      tour.key = "";
    }, 250);
  }
  tour.version += 1;
}

function animate() {
  const { ui } = tour;
  tour.version += 1;
  ui.pop.classList.remove("is-in");
  void ui.pop.offsetWidth;  // restart the entrance animation
  ui.pop.classList.add("is-in");
  ui.layer.classList.add("is-moving");
  later(() => ui.layer.classList.remove("is-moving"), 400);
}

function announce(message) {
  tour.ui.live.textContent = message;
}

/** Focus stays on a popover button the person is using; otherwise it moves to the main button. */
function focusPop() {
  const { ui } = tour;
  const active = document.activeElement;
  if (ui.pop.contains(active) && active !== ui.pop && !active.hidden) return;
  (ui.next.hidden ? ui.pop : ui.next).focus({ preventScroll: true });
}

function restoreFocus(opener) {
  const usable = (el) => el?.isConnected && el !== document.body && el.getClientRects().length > 0
    && !el.closest("[inert]") && !el.disabled;
  const launcher = $("#assistant-launcher");
  const fromAssistant = opener?.isConnected && opener.closest("#assistant-root") && usable(launcher);
  const el = usable(opener) ? opener : fromAssistant ? launcher : $('[data-action="tour"]');
  el?.focus({ preventScroll: true });
}

function onKey(e) {
  if (!tour.active) return;
  const el = e.target instanceof Element ? e.target : null;
  const inPop = Boolean(el && tour.ui.layer.contains(el));
  const loose = !el || el === document.body || el === document.documentElement;
  if (e.key === "Escape") {
    if (!inPop && !loose && (el.closest("dialog[open]") || el.matches("input, textarea, select, [contenteditable]"))) {
      return;  // Esc belongs to that dialog or field
    }
    e.preventDefault();
    endTour();
  } else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && (inPop || loose)
    && !e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
    e.preventDefault();
    move(e.key === "ArrowRight" ? 1 : -1);
  }
}

// ---------------------------------------------------------------- targets, spotlight and placement
function visible(el) {
  if (!el?.isConnected) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

function resolve(spec) {
  if (!spec) return [];
  const list = typeof spec === "function" ? spec() : [].concat(spec).flatMap((sel) => $$(sel));
  return list.filter(visible);
}

function setTargets(spec, els) {
  tour.spec = spec;
  tour.targets = els;
  mark(els);
  tour.key = "";
}

/** Mark the highlighted elements (class is-tour-target), for styling hooks and tests. */
function mark(els) {
  for (const el of $$(".is-tour-target")) if (!els.includes(el)) el.classList.remove("is-tour-target");
  for (const el of els) el.classList.add("is-tour-target");
}

function unionRect(els) {
  const rects = els.map((el) => el.getBoundingClientRect());
  const top = Math.min(...rects.map((r) => r.top));
  const left = Math.min(...rects.map((r) => r.left));
  const bottom = Math.max(...rects.map((r) => r.bottom));
  const right = Math.max(...rects.map((r) => r.right));
  return { top, left, bottom, right, width: right - left, height: bottom - top };
}

/** The part of a rectangle inside the viewport, or null. */
function onScreen(rect) {
  if (!rect) return null;
  const vw = document.documentElement.clientWidth;
  const vh = window.innerHeight;
  const top = Math.max(rect.top, 0);
  const left = Math.max(rect.left, 0);
  const bottom = Math.min(rect.bottom, vh);
  const right = Math.min(rect.right, vw);
  return bottom - top > 1 && right - left > 1 ? { top, left, bottom, right, width: right - left, height: bottom - top }
    : null;
}

const clamp = (value, lo, hi) => Math.min(Math.max(value, lo), Math.max(lo, hi));

function frame() {
  if (!tour.active) return;
  tour.raf = requestAnimationFrame(frame);
  sync();
}

function refresh() {
  tour.key = "";
  if (tour.active) sync();
}

/** Follow the targets (they move with scrolling, layout and re-renders) and keep the popover beside them. */
function sync() {
  const { ui } = tour;
  if (tour.spec && (!tour.targets.length || !tour.targets.every(visible))) {
    tour.targets = resolve(tour.spec);
    mark(tour.targets);
  }
  // a modal dialog makes the rest of the page inert: the tour lives inside the dialog while one is open
  const own = tour.targets.map((el) => el.closest("dialog")).find((d) => d?.open);
  const modal = own || $$("dialog[open]").reverse().find(isModal);
  const host = modal || $("#tour-root") || document.body;
  if (ui.layer.parentNode !== host) {
    const focused = ui.layer.contains(document.activeElement) ? document.activeElement : null;
    host.append(ui.layer);
    ui.layer.classList.toggle("is-in-dialog", Boolean(modal));
    if (focused) focused.focus({ preventScroll: true });
    else if (modal) focusPop();
    tour.key = "";
  }
  const rect = tour.targets.length ? onScreen(unionRect(tour.targets)) : null;
  const key = [rect ? [rect.top, rect.left, rect.width, rect.height].map(Math.round).join(",") : "-",
    window.innerWidth, window.innerHeight, tour.version].join("|");
  if (key === tour.key) return;
  tour.key = key;
  spotlight(rect);
  place(rect);
}

function isModal(dialog) {
  try {
    return dialog.matches(":modal");
  } catch {
    return true;
  }
}

function spotlight(rect) {
  const { spot } = tour.ui;
  spot.classList.toggle("is-none", !rect);
  if (!rect) {
    Object.assign(spot.style, { top: "50%", left: "50%", width: "0px", height: "0px" });
    return;
  }
  const vw = document.documentElement.clientWidth;
  const vh = window.innerHeight;
  const top = Math.max(rect.top - PAD, 3);
  const left = Math.max(rect.left - PAD, 3);
  const bottom = Math.min(rect.bottom + PAD, vh - 3);
  const right = Math.min(rect.right + PAD, vw - 3);
  Object.assign(spot.style, { top: `${top}px`, left: `${left}px`, width: `${Math.max(0, right - left)}px`,
    height: `${Math.max(0, bottom - top)}px`, borderRadius: radius() });
}

/** The spotlight follows a single target's corners (a round launcher gets a round light). */
function radius() {
  if (tour.targets.length !== 1) return "";
  const r = getComputedStyle(tour.targets[0]).borderTopLeftRadius;
  if (r.endsWith("%")) return "50%";
  const px = parseFloat(r) || 0;
  return px >= 8 ? `${px + PAD}px` : "";
}

/** Below the target, else above, else beside it, else docked at the bottom of the viewport. */
function place(rect) {
  const { pop } = tour.ui;
  const vw = document.documentElement.clientWidth;
  const vh = window.innerHeight;
  pop.style.width = "";
  let w = pop.offsetWidth;
  let ph = pop.offsetHeight;
  let x = (vw - w) / 2;
  let y = (vh - ph) / 2;
  let side = "center";
  if (rect) {
    const room = { bottom: vh - rect.bottom - GAP - EDGE, top: rect.top - GAP - EDGE,
      right: vw - rect.right - GAP - EDGE, left: rect.left - GAP - EDGE };
    const across = rect.left + rect.width / 2 - w / 2;
    const beside = room.right >= room.left ? "right" : "left";
    if (room.bottom >= ph) [side, x, y] = ["bottom", across, rect.bottom + GAP];
    else if (room.top >= ph) [side, x, y] = ["top", across, rect.top - GAP - ph];
    else if (room[beside] >= MIN_SIDE) {
      w = Math.min(w, room[beside]);
      pop.style.width = `${w}px`;
      ph = pop.offsetHeight;
      side = beside;
      x = beside === "right" ? rect.right + GAP : rect.left - GAP - w;
      y = rect.top + rect.height / 2 - ph / 2;
    } else {
      side = "dock";
      x = vw < 720 ? (vw - w) / 2 : EDGE;
      y = vh - ph - EDGE;
    }
  }
  pop.style.left = `${Math.round(clamp(x, EDGE, vw - w - EDGE))}px`;
  pop.style.top = `${Math.round(clamp(y, EDGE, vh - ph - EDGE))}px`;
  pop.dataset.side = side;
}

/** Scroll the page so the target (and, if both fit, the popover under it) is in view. */
function reveal(els) {
  if (!tour.active || !els.length || els.some((el) => !el.isConnected || el.closest("dialog"))) return;
  const r = unionRect(els);
  const vh = window.innerHeight;
  const m = 16;
  const { pop } = tour.ui;
  const width = pop.style.width;
  pop.style.width = "";
  const ph = pop.offsetHeight + GAP;
  pop.style.width = width;
  let top = null;  // where the target's top should be
  if (r.height + ph + 2 * m <= vh) {
    const fits = r.top >= m && (r.bottom + ph <= vh - m || (r.top - ph >= m && r.bottom <= vh - m));
    if (!fits) top = (vh - r.height - ph) / 2;
  } else if (r.height + 2 * m <= vh) {
    if (r.top < m || r.bottom > vh - m) top = (vh - r.height) / 2;
  } else {
    top = m;  // taller than the viewport: show as much of it as fits, from its top
  }
  if (top !== null && Math.abs(r.top - top) > 2) {
    window.scrollBy({ top: r.top - top, behavior: reducedMotion() ? "instant" : "smooth" });
  }
}

// ---------------------------------------------------------------- timers
function later(fn, ms) {
  tour.timers.push(setTimeout(fn, ms));
}

function clearTimers() {
  for (const id of tour.timers) clearTimeout(id);
  tour.timers = [];
}

// ---------------------------------------------------------------- the first-visit invitation
function seen() {
  try {
    return localStorage.getItem(STORE_KEY) === "seen";
  } catch {
    return false;
  }
}

function remember() {
  try {
    localStorage.setItem(STORE_KEY, "seen");
  } catch { /* storage blocked: the invitation simply shows again */ }
}

function invite() {
  const lede = $(".hero .lede");
  if (!lede || seen() || $(".tour-invite")) return;
  const box = h("p", { class: "tour-invite" },
    h("span", { text: "New here?" }),
    h("button", { type: "button", class: "link-button tour-invite-start", onclick: () => startTour() },
      "Take the 2-minute tour"),
    h("button", { type: "button", class: "tour-invite-close", "aria-label": "Dismiss the tour invitation",
      onclick: () => {
        remember();
        box.remove();
        $('[data-action="tour"]')?.focus();
      } }, h("span", { "aria-hidden": "true", text: "×" })));
  lede.after(box);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", invite);
else invite();
