// Babel in the browser: Start (game, comparable games, words and budget), Working (the agent's live events) and the
// Plan screen (plan.js). No framework and no keys: it talks only to this server's API (same origin). Text from the
// server or the user is always inserted as text, never as HTML. Progress comes only from the server's events.

import { $, $$, api, errorText, fmtInt, fmtUsd, GROUP_LABEL, h, LANG, listText, picture, reducedMotion, short,
  showError } from "./ui.js";
import { register } from "./actions.js";
import { initAssistant, openAssistant } from "./assistant.js";
import { initHero } from "./hero.js";
import { currentPlan, openPlan, planActions, wirePlanScreen } from "./plan.js";
import { startTour } from "./tour.js";
import { openReport } from "./report.js";
import { openTrackRecord } from "./track.js";

const STEAM_URL = /^(?:https?:\/\/)?store\.steampowered\.com\/app\/(\d+)(?:[/?#].*)?$/i;
const STEP_ORDER = ["connect", "goal", "game", "tags", "lookalikes", "fan_maps", "score", "optimize", "markets",
  "explain", "verify", "result"];
const STEP_LABEL = {
  connect: "Connect to Babel", goal: "Plan the work", game: "Find your game on Steam", tags: "Work out your game's tags",
  lookalikes: "Find games like yours", fan_maps: "See where their fans are", score: "Rank the 14 languages",
  optimize: "Fit your budget", markets: "Notes on your top markets", explain: "Explain the plan",
  verify: "Double-check the plan", result: "Finish",
};
const STATE_TEXT = { pending: "", running: "working…", done: "done", warning: "see note", input: "needs you",
  failed: "failed", skipped: "skipped" };
// Qloo status of a similar game (server codes: valid, default map, not in Qloo, no heatmap, unchecked)
const STATUS_TEXT = {
  valid: "Has Qloo fan data", "default map": "Qloo has no real fan data", "not in Qloo": "Qloo doesn't know this game",
  "no heatmap": "Qloo has no fan map for it", unchecked: "Not checked with Qloo yet",
};
const statusText = (status) => STATUS_TEXT[status] || status;
const MODES = {
  steam: { label: "Steam store link", help: "Paste your game's Steam store link.",
    placeholder: "https://store.steampowered.com/app/…" },
  name: { label: "Game name", help: "Type the game's name as it appears on Steam.", placeholder: "e.g. WEBFISHING" },
  description: { label: "Describe your game", placeholder: "",
    help: "No store page yet? Describe the game in a few sentences (10 to 4,000 characters)." },
};

const state = { ready: false, mode: "steam", request: null, suggestions: null, chosen: [], picked: [],
  swapIndex: 0, swapOpener: null, run: null, retryUntil: 0 };

// ---------------------------------------------------------------- small helpers
function setLoading(button, loading, text) {
  if (loading) {
    button.dataset.label = button.textContent;
    button.textContent = text;
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
  } else if (button.dataset.label) {
    button.textContent = button.dataset.label;
    button.removeAttribute("aria-busy");
    button.disabled = !state.ready || Date.now() < state.retryUntil;
  }
}

// ---------------------------------------------------------------- the API (same origin; keys stay on the server)
function holdOff(r) {
  if (r.status !== 429 || !r.retryAfter) return;
  state.retryUntil = Date.now() + r.retryAfter * 1000;
  const tick = () => {
    const left = Math.ceil((state.retryUntil - Date.now()) / 1000);
    for (const b of [$("#find-button"), $("#run-button")]) {
      if (b.getAttribute("aria-busy")) continue;
      b.disabled = left > 0 || !state.ready;
    }
    if (left > 0) setTimeout(tick, 500);
  };
  tick();
}

/** POST /plan and read its Server-Sent Events: calls onEvent(name, data) for each. */
async function streamPlan(body, { signal, onEvent }) {
  let res;
  try {
    res = await fetch("/plan", { method: "POST", signal, body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" } });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    return { ok: false, status: 0, error: { error: "network",
      message: "Can't reach the Babel server. Check your connection and try again." } };
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { /* not JSON */ }
    return { ok: false, status: res.status, retryAfter: Number(res.headers.get("Retry-After")) || 0,
      error: data && data.error ? data : { error: "http_error",
        message: `Babel's server had a problem (error ${res.status}). Try again in a minute.` } };
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const fields = {};
      for (const line of block.split("\n")) {
        if (!line || line.startsWith(":")) continue;  // ": keep-alive" comments
        const colon = line.indexOf(":");
        const key = line.slice(0, colon);
        const val = line.slice(colon + 1).replace(/^ /, "");
        fields[key] = key in fields ? `${fields[key]}\n${val}` : val;
      }
      if (fields.event && fields.data) onEvent(fields.event, JSON.parse(fields.data));
    }
  }
  return { ok: true };
}

// ---------------------------------------------------------------- readiness
async function watchReadiness() {
  const banner = $("#ready-banner");
  for (;;) {
    let ready = false;
    let checks = {};
    try {
      const res = await fetch("/health/ready");
      const data = await res.json();
      ready = res.ok && data.ready;
      checks = data.checks || {};
    } catch { /* server not reachable yet */ }
    state.ready = ready;
    for (const b of [$("#find-button"), $("#run-button")]) {
      if (!b.getAttribute("aria-busy")) b.disabled = !ready || Date.now() < state.retryUntil;
    }
    if (ready) { banner.hidden = true; return; }
    banner.replaceChildren();
    const failed = String(checks.runtime_data || "").startsWith("failed") || checks.qloo_key_configured === false;
    banner.classList.toggle("is-bad", failed);
    banner.append(...(failed
      ? ["Babel couldn't load its data, so it can't plan right now. Please try again later."]
      : [h("span", { class: "spinner", "aria-hidden": "true" }), "Babel is loading its data. This takes about 20 seconds."]));
    banner.hidden = false;
    await new Promise((resolve) => setTimeout(resolve, failed ? 10000 : 2000));
  }
}

// ---------------------------------------------------------------- Start: the game
function setMode(mode, { focus = false } = {}) {
  state.mode = mode;
  for (const tab of $$('[role="tab"]')) {
    const on = tab.dataset.mode === mode;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    if (on && focus) tab.focus();
  }
  const input = $("#game-input");
  const area = $("#game-description");
  const isText = mode === "description";
  input.hidden = isText;
  area.hidden = !isText;
  $("#game-input-wrap").setAttribute("aria-labelledby", `mode-${mode}`);
  $("#game-input-label").textContent = MODES[mode].label;
  area.setAttribute("aria-label", MODES[mode].label);
  input.placeholder = MODES[mode].placeholder;
  $("#game-help").textContent = MODES[mode].help;
  showError("#game-error", "", [input, area]);
}

function gameField() {
  return state.mode === "description" ? $("#game-description") : $("#game-input");
}

/** The game request from the form, or null after showing what is wrong. */
function readGame() {
  const raw = gameField().value.trim();
  const fail = (msg) => { showError("#game-error", msg, [gameField()]); gameField().focus(); return null; };
  if (state.mode === "steam") {
    if (/^\d{1,10}$/.test(raw)) return { body: { appid: Number(raw) }, raw };
    const match = raw.match(STEAM_URL);
    if (!match) return fail("Paste a Steam store link like https://store.steampowered.com/app/3146520/, or its app ID.");
    return { body: { appid: Number(match[1]) }, raw };
  }
  if (state.mode === "name") {
    if (!raw) return fail("Type the game's name.");
    if (raw.length > 200) return fail("Keep the name under 200 characters.");
    return { body: { name: raw }, raw };
  }
  if (raw.length < 10) return fail("Describe the game in at least 10 characters.");
  if (raw.length > 4000) return fail("Keep the description under 4,000 characters.");
  return { body: { description: raw }, raw };
}

async function findLookalikes(event) {
  event?.preventDefault();
  if (!state.ready) {
    showError("#game-error", "Babel is still loading its data. Try again in a few seconds.");
    return;
  }
  const request = readGame();
  if (!request) return;
  showError("#game-error", "", [gameField()]);
  const button = $("#find-button");
  setLoading(button, true, "Finding similar games…");
  const r = await api("POST", "/lookalikes", request.body);
  setLoading(button, false);
  if (!r.ok) {
    holdOff(r);
    const details = (r.error.details || []).map((d) => d.message).join(" ");
    showError("#game-error", r.status === 422 && details ? details : errorText(r), [gameField()]);
    return;
  }
  state.request = request;
  state.suggestions = r.data;
  state.chosen = r.data.lookalikes.slice();
  state.picked = state.chosen.map((c) => c.appid);
  renderSetup();
  $("#setup").hidden = false;
  $("#setup").scrollIntoView({ block: "start" });
  $("#setup-title").focus({ preventScroll: true });
}

// ---------------------------------------------------------------- Start: comparable games
function chosenChanged() {
  const now = state.chosen.map((c) => c.appid);
  return now.length !== state.picked.length || now.some((a, i) => a !== state.picked[i]);
}

function renderSetup() {
  const s = state.suggestions;
  const g = s.game;
  const source = { steam_tags: "Games like it were matched on Steam tags; rare tags count more.",
    store_description: "An LLM suggested tags from its store description; Babel checked them on Steam and Qloo.",
    description: "An LLM read your description and suggested tags and similar games; Babel checked each one on Steam and Qloo.",
  }[s.source];
  const langs = (g.supported_languages || []).map((l) => LANG[l] || l);
  $("#game-summary").replaceChildren(
    picture(g),
    h("div", {},
      h("h3", { text: g.name }),
      h("p", { text: [g.release_date ? `Released ${g.release_date.slice(0, 4)}` : null, source].filter(Boolean).join(" · ") }),
      h("p", { text: langs.length ? `Already in your game: ${langs.join(", ")}.`
        : "Not translated into any of the 14 languages Babel plans for yet." }),
      h("div", { class: "tags", "aria-label": "Steam tags" }, (g.top_tags || []).slice(0, 8).map((t) => h("span", { class: "tag", text: t })))));

  const notes = s.notes.map((n) => h("p", { class: "note", text: n }));
  if (s.confidence && s.confidence.level !== "high") {
    // the server's reasons (the same ones the plan's evidence keeps) one click away
    const low = s.confidence.level === "low";
    notes.push(h("div", { class: low ? "note" : "note is-info" },
      h("p", { class: "note-lead", text: low
        ? "Babel isn't sure these games are like yours. Check them, and swap any that don't fit."
        : "Check these games: Babel is fairly sure, but not certain, that they are like yours." }),
      s.confidence.reasons.length ? h("details", { class: "note-details" },
        h("summary", { text: low ? "Why Babel isn't sure" : "Why only fairly sure" }),
        h("ul", {}, s.confidence.reasons.map((r) => h("li", { text: r })))) : null));
  }
  if (s.widened_search) notes.push(h("p", { class: "note is-info", text: "Few of the closest matches had Qloo fan data, so Babel also looked at less similar games." }));
  $("#setup-notes").replaceChildren(...notes);

  const cards = state.chosen.map((c, i) => renderCard(c, i));
  if (state.chosen.length < 3) {
    cards.push(h("div", { class: "cards-empty" },
      h("p", { text: state.chosen.length ? "You can add up to three games like yours." : "No similar game with Qloo fan data yet." }),
      h("button", { type: "button", class: "button button-secondary", onclick: (e) => openSwap(state.chosen.length, e.currentTarget) },
        "Add a similar game")));
  }
  $("#cards").replaceChildren(...cards);
  $("#reset-cards").hidden = !chosenChanged();
  $("#rejected-note").textContent = rejectedText(s.rejected.slice(0, 4));
  showError("#cards-error", "");
}

/** "Also checked, not used: Qloo doesn't know A and B; Qloo has no real fan data for C." (grouped by reason) */
function rejectedText(cards) {
  const lead = { "default map": "Qloo has no real fan data for", "not in Qloo": "Qloo doesn't know",
    "no heatmap": "Qloo has no fan map for" };
  const groups = new Map();
  for (const c of cards) groups.set(c.status, [...(groups.get(c.status) || []), c.name]);
  const parts = [...groups].map(([status, names]) => (lead[status] ? `${lead[status]} ${listText(names)}`
    : names.map((n) => `${n} (${status})`).join(", ")));
  return parts.length ? `Also checked, not used: ${parts.join("; ")}.` : "";
}

function renderCard(c, i) {
  const titleId = `card-title-${i}`;
  const swapped = !state.picked.includes(c.appid);
  const badges = [h("span", { class: c.usable ? "badge badge-ok" : "badge badge-warn",
    text: c.usable ? statusText("valid") : `Won't be used: ${statusText(c.status)}` })];
  if (swapped) badges.push(h("span", { class: "badge badge-swapped", text: "Your pick" }));
  let meter = null;
  if (c.overlap != null) {
    // the bar shows how closely the tags match; the exact score (weighted tag overlap, 0 to 1) is in the tooltip
    const fill = h("span", { class: "meter-fill" });
    fill.style.width = `${Math.min(100, c.overlap * 200)}%`;  // CSSOM, allowed by the page's CSP
    const exact = `Tag match score ${c.overlap.toFixed(2)} on a 0 to 1 scale: the share of Steam tags in common, rare tags counting more`;
    meter = h("div", { class: "meter", title: exact }, h("span", { text: "How closely the tags match" }),
      h("span", { class: "meter-bar", role: "img", "aria-label": exact }, fill));
  }
  return h("article", { class: "card", "aria-labelledby": titleId },
    picture(c),
    h("div", { class: "card-body" },
      h("h4", { class: "card-title", id: titleId }, c.name, c.year ? h("span", { class: "muted", text: ` · ${c.year}` }) : null),
      c.why ? h("p", { class: "card-why", text: c.why }) : null,
      meter,
      h("div", { class: "card-foot" },
        h("div", { class: "tags" }, badges),
        h("button", { type: "button", class: "button button-secondary", "data-swap": String(i),
          "aria-label": `Swap ${c.name}`, onclick: (e) => openSwap(i, e.currentTarget) }, "Swap"))));
}

// ---------------------------------------------------------------- swap dialog
let searchTimer = 0;
let searchController = null;

function swapOption(card) {
  return h("li", {}, h("button", { type: "button", class: "swap-option", onclick: () => choose(card) },
    picture(card),
    h("span", {}, h("span", { class: "swap-name", text: card.year ? `${card.name} · ${card.year}` : card.name }),
      card.why ? h("span", { class: "swap-why", text: card.why }) : null),
    h("span", { class: card.usable ? "badge badge-ok" : card.status === "unchecked" ? "badge" : "badge badge-warn",
      text: statusText(card.status) })));
}

function openSwap(index, opener) {
  state.swapIndex = index;
  state.swapOpener = opener || null;
  const current = state.chosen[index];
  $("#swap-title").textContent = current ? `Swap ${current.name}` : "Add a similar game";
  const taken = new Set(state.chosen.map((c) => c.appid));
  const alternatives = state.suggestions.alternatives.filter((c) => !taken.has(c.appid));
  $("#swap-alternatives").replaceChildren(...(alternatives.length ? alternatives.map(swapOption)
    : [h("li", { class: "swap-empty", text: "No more suggestions with Qloo fan data. Search below." })]));
  $("#swap-search").value = "";
  $("#swap-results").replaceChildren();
  $("#swap-status").textContent = "";
  $("#swap-dialog").showModal();
  ($(".swap-option", $("#swap-alternatives")) || $("#swap-search")).focus();
}

async function choose(card) {
  let chosen = card;
  if (card.status === "unchecked") {
    $("#swap-status").textContent = `Checking whether Qloo has fan data for ${card.name}…`;
    const r = await api("GET", `/games/${card.appid}`);
    if (!r.ok) {
      holdOff(r);
      $("#swap-status").textContent = errorText(r);
      return;
    }
    chosen = r.data;
  }
  state.chosen[state.swapIndex] = chosen;
  $("#swap-dialog").close();
  renderSetup();
  const button = $(`[data-swap="${state.swapIndex}"]`);
  (button || $("#run-button")).focus();
}

function searchGames() {
  clearTimeout(searchTimer);
  const q = $("#swap-search").value.trim();
  if (q.length < 2) {
    $("#swap-results").replaceChildren();
    $("#swap-status").textContent = q ? "Type at least 2 letters." : "";
    return;
  }
  searchTimer = setTimeout(async () => {
    searchController?.abort();
    searchController = new AbortController();
    let r;
    try { r = await api("GET", `/games/search?q=${encodeURIComponent(q)}`, null, searchController.signal); }
    catch { return; }  // a newer search replaced this one
    if (!r.ok) { $("#swap-status").textContent = errorText(r); return; }
    const taken = new Set(state.chosen.map((c) => c.appid));
    const results = r.data.results.filter((c) => !taken.has(c.appid));
    $("#swap-results").replaceChildren(...results.map(swapOption));
    $("#swap-status").textContent = results.length ? `${results.length} well-known game${results.length > 1 ? "s" : ""} found.`
      : "No well-known game matches. Babel compares only with games that have many Steam reviews.";
  }, 250);
}

// ---------------------------------------------------------------- Start: words and budget
function readControls() {
  const wordsEl = $("#words");
  const budgetEl = $("#budget");
  const words = Number(wordsEl.value);
  const budget = Number(budgetEl.value);
  let ok = true;
  if (!Number.isInteger(words) || words < 1 || words > 5000000) {
    showError("#words-error", "Enter a whole number of words from 1 to 5,000,000.", [wordsEl]);
    ok = false;
  } else showError("#words-error", "", [wordsEl]);
  if (budgetEl.value === "" || !Number.isFinite(budget) || budget < 0 || budget > 10000000) {
    showError("#budget-error", "Enter a budget from $0 to $10,000,000.", [budgetEl]);
    ok = false;
  } else showError("#budget-error", "", [budgetEl]);
  if (!ok) ($('[aria-invalid="true"]', $("#plan-form")) || wordsEl).focus();
  return ok ? { words, budget } : null;
}

function syncChips() {
  for (const chip of $$(".chip")) chip.setAttribute("aria-pressed", String(chip.dataset.words === $("#words").value));
}

function planBody() {
  const controls = readControls();
  if (!controls) return null;
  const s = state.suggestions;
  const body = s.game.appid ? { appid: s.game.appid } : { description: state.request.body.description };
  Object.assign(body, { word_count: controls.words, budget: controls.budget,
    markets: $("#opt-markets").checked, explain: $("#opt-explain").checked });
  if (chosenChanged()) body.lookalikes = state.chosen.map((c) => c.appid).filter(Boolean);
  return body;
}

// ---------------------------------------------------------------- Working
const VIEWS = ["start", "working", "plan", "track", "report"];

function showView(view) {
  if (document.body.dataset.view !== view) state.lastView = document.body.dataset.view;
  document.body.dataset.view = view;
  for (const v of VIEWS) $(`#view-${v}`).hidden = v !== view;
  window.scrollTo({ top: 0 });
}

function rowFor(step) {
  const run = state.run;
  if (!run.rows.has(step)) {
    const rank = (s) => (STEP_ORDER.includes(s) ? STEP_ORDER.indexOf(s) : STEP_ORDER.length);
    const before = run.order.findIndex((s) => rank(s) > rank(step));
    if (before >= 0) run.order.splice(before, 0, step); else run.order.push(step);
    run.rows.set(step, { step, touched: false, flag: null, messages: [] });
  }
  return run.rows.get(step);
}

function rowState(row) {
  if (row.flag === "failed") return "failed";
  if (state.run.active === row.step && !state.run.finished) return "running";
  if (row.flag === "input") return "input";
  if (row.flag === "warning") return "warning";
  if (row.touched) return "done";
  return state.run.finished ? "skipped" : "pending";
}

function renderChecklist() {
  const run = state.run;
  $("#checklist").replaceChildren(...run.order.map((step) => {
    const row = run.rows.get(step);
    const st = rowState(row);
    return h("li", { class: "step", "data-state": st, "data-step": step },
      h("span", { class: "step-icon", "aria-hidden": "true" }),
      h("span", { class: "step-name", text: STEP_LABEL[step] || step }),
      h("span", { class: "step-state", text: STATE_TEXT[st] }),
      row.messages.length ? h("ul", { class: "step-messages" }, row.messages.map((m) =>
        h("li", { class: m.cls, text: m.text }))) : null);
  }));
}

function onEvent(name, data) {
  const run = state.run;
  if (!run || run.closed) return;
  if (name === "meta") { run.planId = data.plan_id; run.cache = data.cache; return; }
  if (name === "result") { run.result = data; return; }
  if (data.type === "error") run.errors.push(data);
  if (data.type === "plan") {
    run.rows.clear();
    run.order = [];
    const goal = rowFor("goal");
    goal.touched = true;
    goal.messages.push({ cls: "", text: data.message });
    for (const step of data.data.steps || []) rowFor(step);
    run.active = null;
  } else if (data.type === "done") {
    run.finished = true;
    run.active = null;
  } else {
    // an error from the server itself (time out, internal) belongs to whatever step was running
    const step = data.step === "result" ? (run.rows.has(run.active) ? run.active : "result") : data.step;
    const row = rowFor(step);
    if (run.active !== row.step) {
      run.active = row.step;
      $("#run-live").textContent = `${STEP_LABEL[row.step] || row.step}…`;
    }
    row.touched = true;
    if (data.status === "failed" || data.type === "error") row.flag = "failed";
    else if (data.status === "needs_input" && row.flag !== "failed") row.flag = "input";
    else if (data.status === "warning" && !row.flag) row.flag = "warning";
    if (data.status !== "started" || !row.messages.length) {
      const cls = data.type === "error" ? "is-error" : data.type === "explain" ? "is-explain"
        : data.status === "needs_input" ? "is-input" : data.status === "warning" ? "is-warning" : "";
      row.messages.push({ cls, text: data.message });
    }
  }
  renderChecklist();
}

async function startRun(body) {
  state.run?.controller.abort();
  const controller = new AbortController();
  state.run = { body, controller, rows: new Map(), order: [], active: "connect", finished: false, closed: false,
    errors: [], result: null, planId: null };
  const s = state.suggestions;
  const gameName = s.game.appid ? s.game.name : "your game";
  $("#working-title").textContent = `Planning ${gameName}`;
  $("#working-meta").textContent = [`${fmtInt.format(body.word_count)} words`, `${fmtUsd.format(body.budget)} budget`,
    state.chosen.length ? `compared with ${state.chosen.map((c) => short(c.name)).join(", ")}` : "no similar games"].join(" · ");
  $("#run-outcome").hidden = true;
  $("#cancel-button").hidden = false;
  $("#cancel-button").disabled = false;
  rowFor("connect").messages.push({ cls: "", text: "Sending your game to Babel." });
  renderChecklist();
  showView("working");
  $("#working-title").focus();

  let outcome;
  try {
    outcome = await streamPlan(body, { signal: controller.signal, onEvent });
  } catch (err) {
    if (state.run.controller !== controller) return;  // a newer run replaced this one
    if (err.name === "AbortError") return finish("cancelled");
    outcome = { ok: false, status: 0, error: { error: "network", message: "The connection to Babel was lost. Try again." } };
  }
  if (state.run.controller !== controller) return;
  if (!outcome.ok) {
    holdOff(outcome);
    return finish("failed", { message: errorText(outcome), requestId: outcome.error.request_id });
  }
  const run = state.run;
  if (run.result) return finish(run.result.status === "ok" ? "ok" : "partial");
  const last = run.errors[run.errors.length - 1];
  return finish("failed", { message: last ? last.message : "The connection closed before the plan finished.",
    requestId: last?.data?.request_id });
}

function finish(kind, { message, requestId } = {}) {
  const run = state.run;
  run.closed = true;
  if (kind !== "ok" && kind !== "partial" && run.active && run.rows.has(run.active)) {
    run.rows.get(run.active).flag = kind === "cancelled" ? "warning" : "failed";
  }
  run.finished = true;
  renderChecklist();
  $("#cancel-button").hidden = true;
  const box = $("#run-outcome");
  box.className = "outcome";
  const back = h("button", { type: "button", class: "button button-secondary", onclick: backToSetup }, "Back to setup");
  if (kind === "cancelled") {
    box.replaceChildren(h("h2", { text: "Cancelled" }),
      h("p", { text: "Babel stopped working on this plan. Nothing was saved." }), h("div", { class: "outcome-actions" }, back));
  } else if (kind === "failed") {
    box.classList.add("is-bad");
    box.replaceChildren(...[h("h2", { text: "The plan stopped" }), h("p", { text: message }),
      requestId ? h("p", { class: "muted", text: `Request ID ${requestId} (quote it if you report this)` }) : null,
      h("div", { class: "outcome-actions" },
        h("button", { type: "button", class: "button button-primary", onclick: () => startRun(run.body) }, "Try again"), back),
    ].filter(Boolean));  // replaceChildren would print null as text
  } else {
    box.replaceChildren(...resultView(run.result, kind, back).filter(Boolean));
  }
  box.hidden = false;
  $("#run-live").textContent = { ok: "Plan ready.", partial: "Plan ready, with warnings.", cancelled: "Cancelled.",
    failed: "The plan stopped." }[kind];
  if (kind === "ok" || kind === "partial") {
    openPlan(run.result, { errors: run.errors.map((e) => e.message) });
    showView("plan");
    $("#plan-title").focus();
    return;
  }
  box.focus();
}

function resultView(res, kind, back) {
  const p = res.result.plan;
  const errors = state.run.errors.map((e) => e.message);
  const names = (codes) => listText(codes.map((c) => LANG[c] || c)) || "none";
  return [
    h("h2", { text: kind === "ok" ? "Plan ready" : "Plan ready, with warnings" }),
    h("p", { text: `${GROUP_LABEL.translate_game}: ${names(p.groups.translate_game)}. `
      + `${GROUP_LABEL.store_page_only}: ${names(p.groups.store_page_only)}. `
      + `Estimated cost: ${fmtUsd.format(p.costs.total)} of your ${fmtUsd.format(p.costs.budget)} budget.` }),
    kind === "partial" ? h("p", { class: "note", text: `Some data could not be read: ${errors.join(" ")}` }) : null,
    h("div", { class: "outcome-actions" },
      h("button", { type: "button", class: "button button-primary", onclick: () => { showView("plan"); $("#plan-title").focus(); } },
        "Back to the plan"), back),
  ];
}

/** run_plan for the assistant: the same path as a person typing the game and pressing the buttons. */
async function runFromAction({ game = {}, word_count: words, budget }) {
  showView("start");
  const mode = game.description ? "description" : game.name ? "name" : "steam";
  setMode(mode);
  gameField().value = game.description || game.name || game.steam_url
    || (game.appid ? `https://store.steampowered.com/app/${game.appid}/` : "");
  await findLookalikes();
  if ($("#setup").hidden) throw new Error($("#game-error").textContent || "Babel could not find that game.");
  if (words) { $("#words").value = String(words); syncChips(); }
  if (budget !== undefined && budget !== null) {
    $("#budget").value = String(budget);
    $("#budget-range").value = String(Math.min(100000, budget));
  }
  const body = planBody();
  if (!body) throw new Error("Check the words and the budget.");
  startRun(body);  // the live trace takes over; the assistant does not wait for the whole run
}

function registerActions() {
  register("run_plan", runFromAction);
  register("open_track_record", () => $('[data-action="track"]').click());
  register("open_report", () => { requirePlan(); showView("plan"); $("#plan-export").click(); });
  register("start_tour", () => startTour());
  register("go_start", () => { showView("start"); gameField().focus(); });
  for (const [name, fn] of Object.entries(planActions)) {
    register(name, (action) => {
      requirePlan();
      if (document.body.dataset.view !== "plan") showView("plan");
      return fn(action);
    });
  }
}

function requirePlan() {
  if (!currentPlan().res) throw new Error("There is no plan open yet: run one first.");
}

function backToSetup() {
  showView("start");
  $("#setup").hidden = !state.suggestions;
  ($("#setup").hidden ? gameField() : $("#run-button")).focus();
}

// ---------------------------------------------------------------- wiring
/** The nav's light/dark switch (static/theme.js holds the theme; this keeps the button in step with it). */
function initThemeToggle() {
  const button = $("#theme-toggle");
  const theme = window.babelTheme;
  if (!button || !theme) return;
  const sync = () => {
    const dark = theme.get() === "dark";
    button.setAttribute("aria-pressed", String(dark));
    button.title = dark ? "Switch to light mode" : "Switch to dark mode";
  };
  button.addEventListener("click", (e) => {
    // The new theme spreads from the pointer; a keyboard press has no pointer (detail 0), so from the button's centre.
    const r = button.getBoundingClientRect();
    const pointer = e.detail > 0;
    theme.toggle(pointer ? e.clientX : r.left + r.width / 2, pointer ? e.clientY : r.top + r.height / 2);
  });
  document.addEventListener("babel:theme", sync);
  sync();
}

function init() {
  setMode("steam");
  watchReadiness();
  wirePlanScreen({ onBack: backToSetup, onTrace: () => { showView("working"); $("#run-outcome").focus(); } });
  registerActions();
  $('[data-action="tour"]').addEventListener("click", () => startTour());
  initAssistant();
  initThemeToggle();
  initHero();
  for (const link of $$('[data-action="track"]')) {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const back = document.body.dataset.view === "track" ? state.lastView : document.body.dataset.view;
      showView("track");
      openTrackRecord({ onBack: () => showView(back || "start") });
    });
  }
  $("#plan-export").addEventListener("click", () => {
    showView("report");
    openReport(currentPlan(), { onBack: () => { showView("plan"); $("#plan-export").focus(); } });
  });

  const tabs = $$('[role="tab"]');
  for (const tab of tabs) tab.addEventListener("click", () => { setMode(tab.dataset.mode); gameField().focus(); });
  $(".segmented").addEventListener("keydown", (e) => {
    const i = tabs.findIndex((t) => t.dataset.mode === state.mode);
    const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    setMode(tabs[(next + tabs.length) % tabs.length].dataset.mode, { focus: true });
  });
  $("#game-form").addEventListener("submit", findLookalikes);
  for (const field of [$("#game-input"), $("#game-description")]) {
    field.addEventListener("input", () => {
      showError("#game-error", "", [field]);
      if (state.suggestions && field.value.trim() !== state.request?.raw) $("#setup").hidden = true;
      for (const t of $$(".strip-tab")) t.setAttribute("aria-pressed", "false");
    });
  }
  $("#game-description").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) findLookalikes(e);
  });
  for (const tab of $$(".strip-tab")) {
    tab.setAttribute("aria-pressed", "false");
    tab.addEventListener("click", () => {
      for (const t of $$(".strip-tab")) t.setAttribute("aria-pressed", String(t === tab));
      if (tab.dataset.demoDescription) {
        setMode("description");
        $("#game-description").value = tab.dataset.demoDescription;
      } else {
        setMode("steam");
        $("#game-input").value = `https://store.steampowered.com/app/${tab.dataset.demoAppid}/`;
      }
      findLookalikes();
    });
  }
  $('[data-action="ask"]').addEventListener("click", () => openAssistant());
  $('[data-action="how"]').addEventListener("click", (e) => {  // from any screen: back to Start, at How it works
    e.preventDefault();
    if (document.body.dataset.view !== "start") showView("start");
    $("#how").scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth" });
  });
  $('[data-action="focus-start"]').addEventListener("click", (e) => {
    e.preventDefault();
    if (document.body.dataset.view !== "start") showView("start");
    $("#game-form").scrollIntoView({ block: "center" });
    gameField().focus({ preventScroll: true });
  });

  $("#reset-cards").addEventListener("click", () => {
    state.chosen = state.suggestions.lookalikes.slice();
    renderSetup();
    $("#cards .button")?.focus();
  });
  $("#swap-search").addEventListener("input", searchGames);
  $("#swap-dialog").addEventListener("close", () => {
    clearTimeout(searchTimer);
    if (state.swapOpener?.isConnected && document.activeElement === document.body) state.swapOpener.focus();
  });

  $("#words").addEventListener("input", () => { syncChips(); showError("#words-error", "", [$("#words")]); });
  for (const chip of $$(".chip")) chip.addEventListener("click", () => { $("#words").value = chip.dataset.words; syncChips(); });
  syncChips();
  $("#budget").addEventListener("input", () => {
    showError("#budget-error", "", [$("#budget")]);
    if ($("#budget").value !== "") $("#budget-range").value = Math.min(100000, Number($("#budget").value));
  });
  $("#budget-range").addEventListener("input", () => { $("#budget").value = $("#budget-range").value; });

  $("#plan-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (!state.ready || !state.suggestions) return;
    const body = planBody();
    if (body) startRun(body);
  });
  $("#cancel-button").addEventListener("click", () => {
    $("#cancel-button").disabled = true;
    state.run?.controller.abort();
  });
}

init();
