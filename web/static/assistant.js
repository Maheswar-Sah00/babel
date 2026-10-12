// The AI assistant: a Babel logo button at the side of the screen opens a chat panel (static/assistant.css). It asks
// POST /assistant about the open plan and performs the actions in the reply through actions.js, the same functions a
// person's clicks use, with a receipt for each. Text from the server or the user is inserted as text, never as HTML,
// and every reply says who wrote it. Wide screens dock the panel beside the page (the page shifts left, so whatever an
// action changes stays in view); narrower screens get a sheet that steps aside into a small card while the actions
// run. The conversation lives in memory and in sessionStorage (this tab only).

import { $, $$, api, countryName, errorText, fmtInt, fmtUsd, h, LANG, reducedMotion } from "./ui.js";
import { perform } from "./actions.js";
import { currentPlan } from "./plan.js";
import { METRICS } from "./mapdata.js";

const MAX_CHARS = 2000;  // per message (the API's limit)
const MAX_MESSAGES = 12;  // sent per request: the newest ones, ending with the user's
const MAX_BYTES = 15000;  // per request body (the server refuses more than 16,384 bytes with 413)
const KEPT_TURNS = 60;  // kept in sessionStorage
const TIMEOUT_MS = 60000;
const STORE = "babel.assistant.v1";
const DOCK = window.matchMedia("(min-width: 1200px)");  // room to dock beside the page
const PAGE = [".skip-link", "#ready-banner", ".frame-top", "main", ".footer"];  // inert behind the sheet
const GUARDED = ".map-controls button, .plan-actions .button";  // the launcher never sits on these
const KEYS = "Enter to send · Shift+Enter for a new line";
const VIEWS = ["start", "working", "plan", "track", "report"];
const LABELS = {  // kind "fallback": Babel's code wrote it; checked false: Claude's answer failed the number check
  checked: ["is-checked", "Written by Claude · numbers checked against Babel's data"],
  unchecked: ["is-unchecked", "Written by Claude · numbers not checked against Babel's data"],
  fallback: ["is-fallback", "Written by Babel's code, not by Claude"],
  replaced: ["is-fallback", "Written by Babel's code, not by Claude · Claude's numbers couldn't be verified"],
};
const ICON = { pending: "…", ok: "✓", failed: "✗", skipped: "–", dropped: "!", info: "→" };
const SPOKEN = { pending: "Doing", ok: "Done", failed: "Failed", skipped: "Skipped", dropped: "Not done",
  info: "Note" };
const DEFAULT_LABEL = {
  run_plan: (a) => `Plan ${a.game?.name || (a.game?.appid ? `Steam app ${a.game.appid}` : "the game")}`,
  set_budget: (a) => `Set the budget to ${Number.isFinite(a.budget) ? fmtUsd.format(a.budget) : a.budget}`,
  show_country: (a) => `Show ${countryName(String(a.country || "?"))} on the map`,
  show_language: (a) => `Show ${LANG[a.language] || a.language} on the map`,
  set_metric: (a) => `Colour the map by ${(METRICS[a.metric]?.label || String(a.metric)).toLowerCase()}`,
  open_why: (a) => `Explain why ${LANG[a.language] || a.language}`,
  open_report: () => "Open the report",
  open_track_record: () => "Open the track record",
  start_tour: () => "Start the tour",
  reset_map: () => "Show all countries again",
  go_start: () => "Go back to the start",
};

const s = { turns: [], pending: null, acting: false, retryUntil: 0, tick: 0, failure: null, peekTurn: null };
const nodes = new WeakMap();  // turn -> {receipts: <ul>}
let ui = null;
let dodgeFrame = 0;

// ---------------------------------------------------------------- small helpers
const isOpen = () => Boolean(ui && !ui.panel.hidden);
const busy = () => Boolean(s.pending) || s.acting || Date.now() < s.retryUntil;
const lowerFirst = (t) => t.charAt(0).toLowerCase() + t.slice(1);
const labelOf = (a) => (typeof a.label === "string" && a.label.trim()) || DEFAULT_LABEL[a.type]?.(a) || String(a.type);

function mark() {
  const svg = $(".logo .logo-mark")?.cloneNode(true) || h("span");
  svg.setAttribute("class", "asst-mark");
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

function sendIcon() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const path = document.createElementNS(ns, "path");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("class", "asst-icon");
  svg.setAttribute("aria-hidden", "true");
  path.setAttribute("d", "M10 16.5V4M4.5 9.5 10 4l5.5 5.5");
  svg.append(path);
  return svg;
}

/** Polite announcements, appended (a reply and its receipts can follow each other within milliseconds). */
function announce(text) {
  ui.live.append(h("p", { text }));
  while (ui.live.childElementCount > 3) ui.live.firstElementChild.remove();
}

function scrollToEnd() {
  ui.scroll.scrollTo({ top: ui.scroll.scrollHeight, behavior: reducedMotion() ? "auto" : "smooth" });
}

// ---------------------------------------------------------------- what the server is told
const keep = (value, ok) => (ok(value) ? value : null);

/**
 * The context the API accepts, from the screen's view and a plan.js currentPlan() snapshot: each value in the form
 * the server validates, or null when it is unknown (never an empty string). Pure, so the tests can call it.
 */
export function assistantContext(view, p) {
  const open = Boolean(p?.res && p.fit);
  const lookalike = open && p.lookalike != null ? String(p.lookalike) : null;
  return {
    view: VIEWS.includes(view) ? view : "start",
    plan_id: open ? keep(p.res.plan_id, (x) => typeof x === "string" && /^[0-9a-f]{16}$/.test(x)) : null,
    budget: open ? keep(p.fit.costs?.budget, (x) => Number.isFinite(x) && x >= 0 && x <= 10000000) : null,
    metric: open ? keep(p.metric, (x) => typeof x === "string" && Object.hasOwn(METRICS, x)) : null,
    country: open ? keep(p.country, (x) => typeof x === "string" && /^[A-Z]{2}$/.test(x)) : null,
    language: open ? keep(p.language, (x) => typeof x === "string" && Object.hasOwn(LANG, x)) : null,
    lookalike: keep(lookalike, (x) => x === "all" || /^\d{1,10}$/.test(x)),
  };
}

const context = () => assistantContext(document.body.dataset.view, currentPlan());
const bytes = (value) => new TextEncoder().encode(JSON.stringify(value)).length;

/** The newest messages (at most 12, each at most 2,000 characters), ending with the user's. */
function history() {
  return s.turns.filter((t) => !t.failed && t.text).slice(-MAX_MESSAGES)
    .map((t) => ({ role: t.role, text: t.text.slice(0, MAX_CHARS) }));
}

/** The request body, under MAX_BYTES: the oldest messages go first; the user's latest message always stays. */
function requestBody() {
  const body = { messages: history(), context: context() };
  while (body.messages.length > 1 && bytes(body) > MAX_BYTES) body.messages.shift();
  return body;
}

function chipsFor(view) {
  const p = currentPlan();
  if (view === "plan" && p.res && p.fit) {
    const top = p.fit.groups.translate_game[0] || p.fit.groups.store_page_only[0];
    const other = p.fit.costs.budget === 5000 ? 20000 : 5000;
    return [top ? `Why ${LANG[top]}?` : null, `What if my budget is ${fmtUsd.format(other)}?`, "Show Japan on the map",
      "Which countries love games like mine?", "Export the report"].filter(Boolean);
  }
  if (view === "track") return ["How much better is Babel than the usual list?", "What does Qloo add?",
    "How was the test fixed in advance?"];
  if (view === "working") return ["What is Babel doing now?", "Why does Babel look at games like mine?"];
  if (view === "report") return ["What's in this report?", "How do I save it as a PDF?"];
  return ["Plan WEBFISHING", "What does Babel do?", "Take the tour"];
}

// ---------------------------------------------------------------- the conversation (memory + sessionStorage)
function save() {
  try {
    const kept = s.turns.filter((t) => !t.failed).slice(-KEPT_TURNS)
      .map(({ role, text, kind, checked, sources, receipts }) => ({ role, text, kind, checked, sources, receipts }));
    sessionStorage.setItem(STORE, JSON.stringify(kept));
  } catch { /* storage blocked or full: the conversation stays in memory */ }
}

function restore() {
  let saved = [];
  try { saved = JSON.parse(sessionStorage.getItem(STORE) || "[]"); } catch { /* blocked or corrupt */ }
  if (!Array.isArray(saved)) return;
  s.turns = saved.filter((t) => t && (t.role === "user" || t.role === "assistant") && typeof t.text === "string")
    .map((t) => (t.role === "user" ? { role: "user", text: t.text } : {
      role: "assistant", text: t.text, kind: t.kind, checked: t.checked === true,
      sources: (Array.isArray(t.sources) ? t.sources : []).filter((x) => typeof x === "string"),
      receipts: (Array.isArray(t.receipts) ? t.receipts : [])
        .filter((r) => r && ICON[r.state] && typeof r.text === "string")
        .map((r) => (r.state === "pending" ? { state: "skipped", text: `Not finished: ${r.text}` } : r)),
    }));
}

function labelFor(turn) {
  if (turn.kind === "llm_text") return LABELS[turn.checked ? "checked" : "unchecked"];
  return LABELS[turn.checked ? "fallback" : "replaced"];
}

/** "✓ Set the budget to $5,000" (screen readers say "check mark"); failures and skips say so in words. */
function receiptNode(r) {
  return h("li", { class: `asst-receipt is-${r.state}` },
    h("span", { class: "asst-receipt-icon", text: ICON[r.state] }), " ", h("span", { text: r.text }));
}

function renderReceipts(turn) {
  const lists = [nodes.get(turn)?.receipts, s.peekTurn === turn ? ui.peekReceipts : null].filter(Boolean);
  for (const list of lists) {
    list.replaceChildren(...turn.receipts.map(receiptNode));
    list.hidden = !turn.receipts.length;
  }
}

function turnNode(turn) {
  if (turn.role === "user") {
    return h("li", { class: "asst-msg is-user" }, h("span", { class: "visually-hidden", text: "You: " }),
      h("p", { class: "asst-bubble", text: turn.text }));
  }
  const [cls, label] = labelFor(turn);
  const receipts = h("ul", { class: "asst-receipts", "aria-label": "What Babel did" });
  nodes.set(turn, { receipts });
  const li = h("li", { class: `asst-msg is-assistant ${cls}` },
    h("p", { class: "asst-label" }, h("span", { class: "asst-label-dot", "aria-hidden": "true" }),
      h("span", { class: "visually-hidden", text: "Babel assistant. " }),
      h("span", { class: "asst-label-text", text: label })),
    h("p", { class: "asst-text", text: turn.text }),
    turn.sources?.length ? h("details", { class: "asst-sources" },  // evidence ids: one click away
      h("summary", { class: "asst-sources-label", text: `Sources it cites (${turn.sources.length})` }),
      h("ul", { "aria-label": "Evidence the answer cites" },
        turn.sources.map((id) => h("li", {}, h("code", { class: "asst-source", text: id }))))) : null,
    receipts);
  renderReceipts(turn);
  return li;
}

function push(turn) {
  s.turns.push(turn);
  ui.log.append(turnNode(turn));
  ui.typing.remove();
  if (s.pending) ui.log.append(ui.typing);
  save();
  renderChrome();
  scrollToEnd();
}

function renderAll() {
  ui.log.replaceChildren(...s.turns.map(turnNode));
  renderChrome();
}

/** Parts that follow the conversation: the welcome, "New conversation", the suggestion chips. */
function renderChrome() {
  const empty = !s.turns.length;
  ui.welcome.hidden = !empty;
  ui.newButton.hidden = empty;
  ui.chips.classList.toggle("is-compact", !empty);
  ui.chips.replaceChildren(...chipsFor(document.body.dataset.view || "start").map((text) =>
    h("button", { type: "button", class: "asst-chip", onclick: () => submit(text) }, text)));
  refresh();
}

/** Buttons follow the state: nothing is sent while a request, its actions or a rate-limit wait is running. */
function refresh() {
  const wait = busy();
  ui.send.disabled = wait;
  ui.send.setAttribute("aria-busy", String(Boolean(s.pending)));
  for (const chip of $$(".asst-chip", ui.chips)) chip.setAttribute("aria-disabled", String(wait));
  for (const b of $$(".asst-retry", ui.log)) b.disabled = wait;
  ui.scroll.setAttribute("aria-busy", String(Boolean(s.pending)));
}

// ---------------------------------------------------------------- sending
function submit(raw) {
  const text = String(raw ?? "").trim().slice(0, MAX_CHARS);
  if (!text || busy()) return;
  if (s.failure) retire();
  const turn = { role: "user", text };
  if (isOpen()) ui.input.focus({ preventScroll: true });
  ui.input.value = "";
  resize();
  push(turn);
  request(turn);
}

async function request(turn) {
  const body = requestBody();
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, TIMEOUT_MS);
  s.pending = controller;
  ui.log.append(ui.typing);
  refresh();
  scrollToEnd();
  let r = null;
  try {
    r = await api("POST", "/assistant", body, controller.signal);
  } catch {
    if (timedOut) {
      r = { ok: false, status: 0, error: { error: "timeout", message: "The assistant took too long to answer." } };
    }
  } finally {
    clearTimeout(timer);
  }
  if (s.pending !== controller) return;  // a new conversation replaced this request
  s.pending = null;
  ui.typing.remove();
  refresh();
  if (!r) return;
  if (r.ok && (!r.data || typeof r.data.reply !== "string")) {
    r = { ok: false, status: 502, error: { error: "bad_reply", message: "The assistant's answer could not be read." } };
  }
  if (!r.ok) return fail(turn, r);
  await answer(r.data);
}

async function answer(data) {
  const actions = (Array.isArray(data.actions) ? data.actions : []).filter((a) => a && typeof a.type === "string");
  const dropped = (Array.isArray(data.dropped_actions) ? data.dropped_actions : []).filter(Boolean);
  const turn = { role: "assistant", text: data.reply, kind: data.kind, checked: data.checked === true,
    sources: (Array.isArray(data.sources) ? data.sources : []).filter((x) => typeof x === "string").slice(0, 12),
    receipts: [...actions.map((a) => ({ state: "pending", text: labelOf(a) })),
      ...dropped.map((d) => ({ state: "dropped", text: `Not done: ${d.reason || "Babel can't do that here."}` }))] };
  push(turn);
  announce(`Babel assistant: ${turn.text}`);
  if (!isOpen()) showPeek(turn, { focus: false });  // closed while it was thinking: show the answer beside the launcher
  if (actions.length) await act(turn, actions);
}

/** Perform the reply's actions in order; the first failure stops the chain (later steps may depend on it). */
async function act(turn, actions) {
  s.acting = true;
  refresh();
  const docked = isOpen() && DOCK.matches;
  const keepFocus = docked && ui.panel.contains(document.activeElement);
  if (actions.some((a) => a.type === "start_tour")) closePanel({ focus: false });  // the tour needs the whole screen
  else if (isOpen() && !docked) {  // the sheet covers the page: step aside so the change is seen
    hidePanel();
    showPeek(turn, { focus: true });
  }
  for (let i = 0; i < actions.length; i++) {
    const label = labelOf(actions[i]);
    try {
      await perform(actions[i]);
      turn.receipts[i] = { state: "ok", text: label };
    } catch (err) {
      const reason = (err instanceof Error ? err.message : String(err || "")).trim() || "it didn't work.";
      turn.receipts[i] = { state: "failed", text: `Couldn't ${lowerFirst(label)}: ${reason}` };
      for (let j = i + 1; j < actions.length; j++) {
        turn.receipts[j] = { state: "skipped", text: `Skipped: ${labelOf(actions[j])} (the step before it failed)` };
      }
      renderReceipts(turn);
      break;
    }
    renderReceipts(turn);
  }
  s.acting = false;
  save();
  renderChrome();  // suggestions follow the new state (a new budget, another screen)
  const modal = document.querySelector("dialog[open]");
  if (modal && isOpen()) {  // a modal dialog (the "Why?" calculation) blocks the page and this panel until it closes
    turn.receipts.push({ state: "info", text: "The calculation is open over the page: close it (Esc) to keep chatting." });
    renderReceipts(turn);
    modal.addEventListener("close", () => {
      turn.receipts = turn.receipts.filter((r) => r.state !== "info");  // the note served its purpose
      renderReceipts(turn);
      save();
      if (isOpen()) ui.input.focus({ preventScroll: true });
    }, { once: true });
  }
  announce(turn.receipts.map((r) => `${SPOKEN[r.state]}: ${r.text.replace(/\.$/, "")}.`).join(" "));
  if (keepFocus && isOpen() && !modal) ui.input.focus({ preventScroll: true });
  queueDodge();
}

// ---------------------------------------------------------------- errors, the rate limit, retry
function fail(turn, r) {
  turn.failed = true;
  const missing = r.status === 404 || r.status === 405;
  const message = missing ? "The assistant isn't available on this server yet." : errorText(r);
  const details = r.status === 422 ? (r.error?.details || []).map((d) => d?.message).filter(Boolean) : [];
  const canRetry = ![404, 405, 413, 422].includes(r.status);  // the same request would fail the same way
  const node = h("li", { class: "asst-msg is-error" },
    h("p", { class: "asst-error-text", text: message }),
    details.length ? h("p", { class: "asst-error-more", text: details.join(" ") }) : null,
    r.error?.request_id ? h("details", { class: "asst-error-more asst-error-id" }, h("summary", { text: "Details" }),
      h("p", { text: `Request ID ${r.error.request_id}` })) : null,
    canRetry ? h("button", { type: "button", class: "button button-secondary button-small asst-retry",
      onclick: () => retry(turn, node) }, "Try again") : null);
  s.failure = { turn, node };
  ui.log.append(node);
  refresh();
  if (r.status === 429) holdOff(r.retryAfter || 10);  // after the node exists, so its Try again counts down too
  scrollToEnd();
  announce(message);
}

function retry(turn, node) {
  if (busy()) return;
  node.remove();
  s.failure = null;
  turn.failed = false;
  ui.input.focus({ preventScroll: true });
  request(turn);
}

/** A new message replaces a failed one: its Try again goes (the failed message is left out of the history). */
function retire() {
  s.failure.node.querySelector(".asst-retry")?.remove();
  s.failure.node.append(h("p", { class: "asst-error-more", text: "Not sent." }));
  s.failure = null;
}

/** After a 429: no sending until Retry-After has passed, with a countdown on the buttons (as app.js holdOff). */
function holdOff(seconds) {
  s.retryUntil = Date.now() + seconds * 1000;
  clearTimeout(s.tick);
  const tick = () => {
    const left = Math.ceil((s.retryUntil - Date.now()) / 1000);
    ui.keys.textContent = left > 0 ? `You can send again in ${left} s` : KEYS;
    ui.keys.classList.toggle("is-wait", left > 0);
    for (const b of $$(".asst-retry", ui.log)) b.textContent = left > 0 ? `Try again in ${left} s` : "Try again";
    refresh();
    if (left > 0) s.tick = setTimeout(tick, 250);
  };
  tick();
}

function newConversation() {
  s.pending?.abort();
  s.pending = null;
  s.turns = [];
  s.failure = null;
  hidePeek();
  try { sessionStorage.removeItem(STORE); } catch { /* blocked */ }
  ui.typing.remove();
  renderAll();
  announce("New conversation.");
  ui.input.focus();
}

// ---------------------------------------------------------------- open, close, the sheet, the peek card
function openPanel() {
  hidePeek();
  ui.panel.hidden = false;
  ui.launcher.hidden = true;
  ui.launcher.setAttribute("aria-expanded", "true");
  applyMode();
  renderChrome();
  ui.scroll.scrollTop = ui.scroll.scrollHeight;
  ui.input.focus();
}

function hidePanel() {
  ui.panel.hidden = true;
  ui.launcher.hidden = false;
  ui.launcher.setAttribute("aria-expanded", "false");
  applyMode();
}

function closePanel({ focus = true } = {}) {
  hidePanel();
  if (focus) ui.launcher.focus();
}

/** Docked beside the page on wide screens (non-modal); a modal sheet elsewhere, with the page behind it inert. */
function applyMode() {
  const open = isOpen();
  const docked = open && DOCK.matches;
  if (open) document.body.dataset.assistant = docked ? "docked" : "sheet";
  else delete document.body.dataset.assistant;
  ui.panel.setAttribute("aria-modal", String(open && !docked));
  ui.backdrop.hidden = !open || docked;
  for (const el of PAGE.flatMap((sel) => $$(sel))) {
    if (open && !docked && !el.inert) { el.inert = true; el.dataset.asstInert = ""; }
    if ((!open || docked) && "asstInert" in el.dataset) { el.inert = false; delete el.dataset.asstInert; }
  }
  queueDodge();
}

function showPeek(turn, { focus }) {
  s.peekTurn = turn;
  ui.peekText.textContent = turn.text;
  renderReceipts(turn);
  ui.peek.hidden = false;
  if (focus) ui.peekOpen.focus({ preventScroll: true });
}

function hidePeek() {
  ui.peek.hidden = true;
  s.peekTurn = null;
}

/** The launcher fades out while it would sit on the map's zoom buttons or the plan actions (only while scrolling
 * past them on narrow screens; on wide ones they never meet). It stays visible while it has keyboard focus. */
function queueDodge() {
  if (!dodgeFrame) dodgeFrame = requestAnimationFrame(dodge);
}

function dodge() {
  dodgeFrame = 0;
  if (!ui || ui.launcher.hidden) return;
  const r = ui.launcher.getBoundingClientRect();
  const hit = $$(GUARDED).some((el) => {
    const b = el.getBoundingClientRect();
    return b.width > 0 && b.left < r.right && b.right > r.left && b.top < r.bottom && b.bottom > r.top;
  });
  ui.launcher.classList.toggle("is-dodging", hit);
}

function resize() {
  const input = ui.input;
  input.style.height = "auto";  // CSSOM: allowed by the page's CSP
  input.style.height = `${Math.min(input.scrollHeight, 168)}px`;
  const n = input.value.length;
  ui.count.textContent = n >= MAX_CHARS * 0.8 ? `${fmtInt.format(n)} / ${fmtInt.format(MAX_CHARS)}` : "";
}

// ---------------------------------------------------------------- building
function build() {
  const launcher = h("button", { type: "button", id: "assistant-launcher", class: "asst-launcher",
    "aria-label": "Ask Babel's assistant", "aria-expanded": "false", "aria-controls": "assistant-panel",
    onclick: () => openPanel() },
  mark(), h("span", { class: "asst-ai", "aria-hidden": "true", text: "AI" }),
  h("span", { class: "asst-tip", "aria-hidden": "true", text: "Ask Babel's assistant" }));

  const newButton = h("button", { type: "button", class: "asst-new", onclick: newConversation }, "New conversation");
  const head = h("header", { class: "asst-head" },
    h("div", { class: "asst-head-row" },
      h("span", { class: "asst-head-mark", "aria-hidden": "true" }, mark()),
      h("h2", { id: "assistant-title", class: "asst-title", text: "Babel assistant" }),
      newButton,
      h("button", { type: "button", class: "icon-button asst-close", "aria-label": "Close the assistant",
        onclick: () => closePanel() }, "×")),
    h("p", { id: "assistant-sub", class: "asst-sub", text: "Answers from Babel's data · can use the app "
      + "for you" }));

  const welcome = h("div", { class: "asst-welcome" },
    h("p", { class: "asst-welcome-lead", text: "Ask about your plan, why Babel chose it, or how well Babel did in "
      + "testing." }),
    h("p", { text: "I can also use the app for you: plan a game, change the budget, show a country or language on the "
      + "map, open the report." }),
    h("p", { class: "asst-welcome-note", text: "Numbers come from Babel's code and Qloo data, not from the AI. Each "
      + "answer says whether Claude wrote it and whether its numbers were checked." }));
  const log = h("ol", { class: "asst-log" });
  const scroll = h("div", { class: "asst-scroll", role: "region", tabindex: "0", "aria-label": "Conversation" },
    welcome, log);
  const typing = h("li", { class: "asst-msg is-assistant asst-typing-row" },
    h("span", { class: "asst-typing" },
      h("span", { class: "asst-dots", "aria-hidden": "true" }, h("span"), h("span"), h("span")),
      "Babel is thinking…"));
  const chips = h("div", { class: "asst-chips", role: "group", "aria-label": "Suggestions" });

  const input = h("textarea", { id: "assistant-input", class: "asst-input", rows: "1", maxlength: String(MAX_CHARS),
    placeholder: "Ask about your plan, or how Babel works", "aria-describedby": "assistant-hint",
    enterkeyhint: "send" });
  const send = h("button", { type: "submit", class: "asst-send", "aria-label": "Send" }, sendIcon());
  const keys = h("span", { class: "asst-keys", text: KEYS });
  const count = h("span", { class: "asst-count" });
  const form = h("form", { class: "asst-form", novalidate: true },
    h("label", { class: "visually-hidden", for: "assistant-input", text: "Message to Babel's assistant" }),
    h("div", { class: "asst-compose" }, input, send),
    h("p", { id: "assistant-hint", class: "asst-hint" }, keys, count));
  const panel = h("section", { id: "assistant-panel", class: "asst-panel", role: "dialog", "aria-modal": "false",
    "aria-labelledby": "assistant-title", "aria-describedby": "assistant-sub", hidden: true },
  head, scroll, chips, form);

  const peekText = h("p", { class: "asst-peek-text" });
  const peekReceipts = h("ul", { class: "asst-receipts", "aria-label": "What Babel did" });
  const peekOpen = h("button", { type: "button", class: "button button-secondary button-small",
    onclick: () => openPanel() }, "Open the chat");
  const peek = h("section", { class: "asst-peek", "aria-label": "Babel assistant: latest answer", hidden: true },
    h("div", { class: "asst-peek-head" }, h("span", { class: "asst-head-mark", "aria-hidden": "true" }, mark()),
      h("strong", { text: "Babel assistant" }),
      h("button", { type: "button", class: "icon-button asst-peek-close", "aria-label": "Dismiss",
        onclick: () => { hidePeek(); ui.launcher.focus(); } }, "×")),
    peekText, peekReceipts, h("div", { class: "asst-peek-actions" }, peekOpen));
  const backdrop = h("div", { class: "asst-backdrop", hidden: true, onclick: () => closePanel() });
  const live = h("div", { class: "visually-hidden", "aria-live": "polite", "aria-relevant": "additions" });

  ui = { launcher, panel, head, newButton, welcome, log, scroll, typing, chips, input, send, keys, count, form, peek,
    peekText, peekReceipts, peekOpen, backdrop, live };
  const root = $("#assistant-root") || document.body.appendChild(h("div", { id: "assistant-root" }));
  root.replaceChildren(backdrop, panel, peek, launcher, live);
}

function wire() {
  ui.form.addEventListener("submit", (e) => { e.preventDefault(); submit(ui.input.value); });
  ui.input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    submit(ui.input.value);
  });
  ui.input.addEventListener("input", resize);
  ui.panel.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || e.isComposing) return;
    e.preventDefault();
    closePanel();
  });
  ui.peek.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    hidePeek();
    ui.launcher.focus();
  });
  DOCK.addEventListener("change", applyMode);
  window.addEventListener("scroll", queueDodge, { passive: true });
  window.addEventListener("resize", queueDodge);
  new MutationObserver(() => {  // a new screen: suggestions that fit it, and a fresh launcher check
    if (isOpen()) renderChrome();
    queueDodge();
  }).observe(document.body, { attributes: true, attributeFilter: ["data-view"] });
}

/** Open the panel, as the launcher does (the nav's "Ask AI agent"). */
export function openAssistant() {
  if (ui) openPanel();
}

/** Put the launcher on the page (called once by app.js). */
export function initAssistant() {
  if (ui) return;
  build();
  wire();
  restore();
  renderAll();
  queueDodge();
}
