// Shared helpers: DOM building (text only, never HTML), formatting, and the same-origin API.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const fmtInt = new Intl.NumberFormat("en-US");
export const fmtUsd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const fmtUsd2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2,
  maximumFractionDigits: 2 });
export const pct = (x, digits = 1) => `${(x * 100).toFixed(digits)}%`;
export const LANG = {
  schinese: "Simplified Chinese", tchinese: "Traditional Chinese", japanese: "Japanese", koreana: "Korean",
  brazilian: "Portuguese-BR", russian: "Russian", spanish: "Spanish", turkish: "Turkish", german: "German",
  french: "French", polish: "Polish", italian: "Italian", ukrainian: "Ukrainian", thai: "Thai",
};
export const GROUP_LABEL = { translate_game: "Translate the game", store_page_only: "Translate the store page only",
  skip: "Skip for now", already_supported: "Already in your game" };

const regionNames = typeof Intl.DisplayNames === "function" ? new Intl.DisplayNames(["en"], { type: "region" }) : null;
/** An English country name for an ISO 3166-1 alpha-2 code (the browser's own list), else the fallback or the code. */
export function countryName(cc, fallback) {
  try {
    const name = regionNames?.of(cc);
    if (name && name !== cc) return name;
  } catch { /* not a region code */ }
  return fallback || cc;
}

/** "A", "A and B", "A, B and C". */
export function listText(items) {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : String(c));
  }
  return el;
}

export function showError(id, message, inputs = []) {
  const el = $(id);
  el.textContent = message || "";
  el.hidden = !message;
  for (const input of inputs) input.setAttribute("aria-invalid", message ? "true" : "false");
}

export function short(name, max = 28) {
  return name.length > max ? `${name.slice(0, max - 1).trimEnd()}…` : name;
}

export function initials(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

export function picture(card, cls = "") {
  const fallback = () => h("div", { class: `thumb-fallback ${cls}`, "aria-hidden": "true", text: initials(card.name) });
  if (!card.image) return fallback();
  const img = h("img", { src: card.image, alt: "", referrerpolicy: "no-referrer", class: cls });
  img.addEventListener("error", () => img.replaceWith(fallback()), { once: true });
  return img;
}

/** Same-origin JSON request: {ok, status, data} or {ok: false, status, retryAfter, error}. Abort errors propagate. */
export async function api(method, url, body, signal) {
  let res;
  try {
    res = await fetch(url, { method, signal, headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    return { ok: false, status: 0, error: { error: "network",
      message: "Can't reach the Babel server. Check your connection and try again." } };
  }
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (res.ok) return { ok: true, status: res.status, data };
  return { ok: false, status: res.status, retryAfter: Number(res.headers.get("Retry-After")) || 0,
    error: data && data.error ? data : { error: "http_error", message: `The server answered ${res.status}.` } };
}

export function errorText(r) {
  const e = r.error || {};
  if (e.error === "rate_limited") return `You're going a little fast. Try again in ${r.retryAfter || "a few"} seconds.`;
  if (e.error === "not_ready") return "Babel is still loading its data. Try again in a few seconds.";
  if (e.error === "busy") return "Babel is busy with other plans. Try again in a few seconds.";
  return e.message || "Something went wrong.";
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
