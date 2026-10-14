"""The dark theme is monochrome (the owner's choice): black, true greys (R = G = B) and white, plus red, amber, green
and orange where they carry a meaning; no blue, cyan, indigo, violet or purple anywhere. In a real browser (Playwright
+ Chromium) on the real app with test_web.py's fakes, every screen in the dark theme (each panel scrolled into view
first, so charts drawn on first view count too) is scanned: each visible element's computed colours (text,
backgrounds and gradients, borders, outlines, shadows, fill and stroke, ::before and ::after), the fill and stroke
attributes of every SVG element, and every colour token on :root. The light theme stays exactly as it was. Needs:
python -m playwright install chromium
"""
import re

import pytest

from test_assistant_web import Stub, ask, open_panel, reply
from test_tour import nav, walk
from test_web import Site, browser, choose_metric  # noqa: F401  (browser: the fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect

# Bluish, strictly: hue 170..300 degrees (cyan, blue, indigo, violet, purple) with a chroma (max - min of R, G, B) of
# 6 or more, at any opacity. Skipped: the report's paper (.report-sheet: the light printed page, on purpose) and the
# Start screen's hero map (its canvas, leader lines, pins, its own sea background and --hero-* tokens: the hero work).
SCAN = r"""() => {
  const bluish = (r, g, b) => {
    const max = Math.max(r, g, b), min = Math.min(r, g, b), c = max - min;
    if (c < 6) return false;
    let h;
    if (max === r) h = ((g - b) / c) % 6; else if (max === g) h = (b - r) / c + 2; else h = (r - g) / c + 4;
    h = (h * 60 + 360) % 360;
    return h >= 170 && h <= 300;
  };
  const colours = (text) => {
    const out = [];
    for (const m of String(text).matchAll(/rgba?\(([^)]+)\)/g)) {
      const [r, g, b, a = 1] = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
      if (a > 0 && bluish(r, g, b)) out.push(m[0]);
    }
    for (const m of String(text).matchAll(/#([0-9a-f]{6}|[0-9a-f]{3})\b/gi)) {
      const hex = m[1].length === 3 ? [...m[1]].map((x) => x + x).join("") : m[1];
      const n = parseInt(hex, 16);
      if (bluish(n >> 16, (n >> 8) & 255, n & 255)) out.push(m[0]);
    }
    return out;
  };
  const name = (el) => {
    const cls = typeof el.className === "string" ? el.className : el.getAttribute("class") || "";
    return el.tagName.toLowerCase() + (el.id ? `#${el.id}` : "") + (cls.trim() ? "." + cls.trim().split(/\s+/).slice(0, 3).join(".") : "");
  };
  const props = ["color", "backgroundColor", "backgroundImage", "borderTopColor", "borderRightColor",
    "borderBottomColor", "borderLeftColor", "outlineColor", "fill", "stroke", "boxShadow", "textShadow",
    "textDecorationColor", "accentColor"];
  const found = new Set();
  const check = (s, where) => {
    for (const p of props) {
      if (p === "outlineColor" && s.outlineStyle === "none") continue;
      for (const c of colours(s[p])) found.add(`${where} ${p} ${c}`);
    }
  };
  const skipped = (el) => el.closest(".report-sheet, .hero-map, .hero-leaders, .pins") || el.matches(".band");
  for (const el of document.querySelectorAll("body *")) {
    if (skipped(el)) continue;
    for (const attr of ["fill", "stroke", "stop-color"]) {
      for (const c of colours(el.getAttribute(attr) || "")) found.add(`${name(el)} @${attr} ${c}`);
    }
    const box = el.getBoundingClientRect(), s = getComputedStyle(el);
    if ((!box.width && !box.height) || s.visibility === "hidden" || s.display === "none") continue;
    check(s, name(el));
    for (const pseudo of ["::before", "::after"]) {
      const ps = getComputedStyle(el, pseudo);
      if (ps.content !== "none" && ps.content !== "normal") check(ps, name(el) + pseudo);
    }
  }
  const names = new Set();
  const walk = (rules) => { for (const r of rules) {
    if (r.style) for (const p of r.style) if (p.startsWith("--") && !p.startsWith("--hero-")) names.add(p);
    if (r.cssRules) walk(r.cssRules); } };
  for (const sheet of document.styleSheets) { try { walk(sheet.cssRules); } catch (e) { /* cross-origin */ } }
  const root = getComputedStyle(document.documentElement);
  for (const n of names) for (const c of colours(root.getPropertyValue(n))) found.add(`token ${n} ${c}`);
  return [...found].sort();
}"""
TOKENS = """(names) => Object.fromEntries(names.map((n) =>
  [n, getComputedStyle(document.documentElement).getPropertyValue(n).trim()]))"""
# The dark theme's greys: exactly neutral (R = G = B), not tinted.
GREYS = ["--bg", "--surface", "--surface-2", "--ink", "--ink-2", "--ink-3", "--line", "--line-2", "--accent",
         "--accent-hover", "--on-accent", "--on-ink", "--blue", "--blue-hover", "--blue-soft", "--blue-ink",
         "--blue-line", "--blue-solid", "--on-warn-solid", "--placeholder", "--img-bg", "--map-surface",
         "--map-hatch-bg", "--map-hatch-ink", "--tip-bg", "--tip-ink", "--tip-muted", "--tip-hint", "--plan-translate",
         "--plan-skip", "--plan-translate-bg", "--plan-translate-line", "--skew-pos", "--src-qloo-bg",
         "--src-qloo-ink", "--src-qloo-line", "--src-llm-bg", "--src-llm-ink", "--src-llm-line", "--llm-bg",
         "--llm-line", "--tr-babel-row", "--tr-tie", "--tr-bar", "--tr-share", "--asst-mark-accent"]
# The light theme, unchanged (a sample of every stylesheet's tokens)
LIGHT = {"--bg": "#f1f6f6", "--surface": "#ffffff", "--ink": "#12181c", "--ink-2": "#48535a", "--line": "#e1e8e9",
         "--accent": "#2d6cf3", "--on-accent": "#ffffff", "--blue": "#2d6cf3", "--blue-soft": "#e8effe",
         "--blue-ink": "#1d4fbf", "--plan-translate": "#2a78d6", "--plan-skip": "#b5bcb9", "--map-surface": "#fbfcfc",
         "--src-qloo-bg": "#eaf1fe", "--src-llm-ink": "#5636a3", "--llm-line": "#8b6ad8", "--tr-babel-row": "#f3f7fe",
         "--tr-bar": "#b5bcb9", "--tr-share": "#7d9aa8", "--asst-mark-accent": "#8fb1ff",
         "--tour-halo": "rgba(255, 255, 255, .7)", "--r-toolbar": "rgba(255, 255, 255, .92)"}


class Scanner:
    """Scans a page on each screen and remembers where every bluish colour was seen."""

    def __init__(self, page):
        self.page, self.found = page, {}

    def __call__(self, screen):
        for item in self.page.evaluate(SCAN):
            self.found.setdefault(item, []).append(screen)

    def report(self):
        return [f"{item}  [{', '.join(screens)}]" for item, screens in sorted(self.found.items())]


def reveal(page, root):
    """Scroll each section of a screen into view, so anything drawn on first view (charts, say) is there to scan."""
    for section in page.locator(f"{root} section").all():
        section.scroll_into_view_if_needed()
        page.wait_for_timeout(150)
    page.evaluate("window.scrollTo(0, 0)")


def grey(css):
    """'#1a1a1a' or 'rgb(26, 26, 26)' -> True when R = G = B."""
    if css.startswith("#"):
        r, g, b = (css[i:i + 2] for i in (1, 3, 5))
    else:
        r, g, b = re.findall(r"[\d.]+", css)[:3]
    return r == g == b


def test_every_dark_screen_is_monochrome(browser):
    with Site(browser, color_scheme="dark") as s:
        page = s.page
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        scan = Scanner(page)
        scan("start")
        s.find()
        scan("setup")
        page.get_by_role("button", name="Swap Beta Town").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        scan("swap")
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Run the plan").click()
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready")
        reveal(page, "#view-plan")  # every panel of the Plan screen, charts included
        for metric in ("relative", "affinity", "demand", "plan"):
            choose_metric(page, metric)
            scan(f"plan:{metric}")
        page.evaluate("document.querySelectorAll('#view-plan details').forEach((d) => { d.open = true; })")
        page.locator(".country-row").first.click()
        expect(page.locator(".map-canvas .outline-selected")).to_have_count(1)
        scan("country")
        page.locator('.lang-row button:has-text("Why")').first.click()
        expect(page.locator("#why-dialog")).to_be_visible()
        page.evaluate("document.querySelectorAll('#why-dialog details').forEach((d) => { d.open = true; })")
        scan("why")
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Export report").click()
        expect(page.locator(".report-sheet")).to_be_visible()
        scan("report")
        page.get_by_role("button", name="Back to the plan").click()
        page.get_by_role("button", name="See every step").click()
        expect(page.locator("#view-working")).to_be_visible()
        scan("working")
        page.evaluate("document.querySelector('[data-action=\"track\"]').click()")  # as the assistant opens it
        page.locator(".tr-verdict").first.wait_for()
        page.locator(".tr-example").last.click()
        page.evaluate("document.querySelectorAll('#view-track details').forEach((d) => { d.open = true; })")
        reveal(page, "#view-track")
        scan("track")
        assert scan.report() == []
        assert s.errors == []


def test_the_assistant_and_its_messages_are_monochrome(browser):
    """Every kind of answer (checked, not checked, fallback, error) and receipt (done, dropped, the Why note)."""
    with Site(browser, color_scheme="dark") as s:
        page = s.plan()
        why = {"type": "open_why", "language": "russian", "label": "Why Russian? Open the calculation"}
        Stub(s, reply("I'll change the budget, then show Japan.", actions=[
            {"type": "set_budget", "budget": 5000, "label": "Set the budget to $5,000"},
            {"type": "show_country", "country": "JP", "label": "Show Japan on the map"}],
            dropped=[{"type": "open_track_record", "reason": "Not now."}]),
            reply("Not checked.", checked=False, sources=()),
            reply("Written by Babel's code.", kind="fallback", checked=False, sources=("product:limits",)),
            "abort", reply(actions=[why]))
        scan = Scanner(page)
        open_panel(page)
        scan("assistant:welcome")
        for question in ("Set the budget and show Japan", "Anything", "Japan's revenue?", "Hi"):
            ask(page, question)
            expect(page.locator(".asst-send")).to_be_enabled()
        ask(page, "Why Russian?")
        expect(page.locator("#assistant-root .asst-receipt.is-info")).to_be_visible()
        for cls in ("is-checked", "is-unchecked", "is-fallback", "is-error"):
            expect(page.locator(f".asst-msg.{cls}").first).to_be_attached()
        scan("assistant:messages")
        assert scan.report() == []
        assert s.errors == []


def test_the_tour_is_monochrome(browser):
    with Site(browser, color_scheme="dark") as s:
        page = s.page
        page.emulate_media(reduced_motion="reduce")
        scan = Scanner(page)
        nav(page).click()
        seen = walk(page, lambda info: scan(f"tour:{info['step']}"))
        assert seen[0] == "welcome" and seen[-1] == "done"
        assert scan.report() == []
        assert s.errors == []


def test_dark_greys_are_true_greys_and_cues_replace_hue(browser):
    """The greys are exactly neutral; links stay distinguishable without colour (underlined), filled buttons are
    near-white with black text, focus rings are light, Claude's chips have a dashed edge."""
    with Site(browser, color_scheme="dark") as s:
        page = s.page
        tokens = page.evaluate(TOKENS, GREYS)
        assert [n for n, v in tokens.items() if not v or not grey(v)] == []
        css = lambda sel, prop: page.locator(sel).first.evaluate(f"(e) => getComputedStyle(e).{prop}")  # noqa: E731
        assert css(".nav .button-primary", "backgroundColor") == "rgb(237, 237, 237)"
        assert css(".nav .button-primary", "color") == "rgb(10, 10, 10)"
        assert "underline" in css(".evidence-card .link", "textDecorationLine")
        page.locator("#theme-toggle").focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")  # a keyboard focus: :focus-visible
        assert css("#theme-toggle", "outlineColor") == "rgb(245, 245, 245)"
        page.locator("#theme-toggle").blur()
        s.plan()
        assert css(".src-qloo", "borderTopStyle") == "solid"
        page.get_by_role("button", name="Export report").click()
        assert s.errors == []


def test_the_light_theme_is_unchanged(browser):
    with Site(browser) as s:
        page = s.page
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        assert page.evaluate(TOKENS, list(LIGHT)) == LIGHT
        css = lambda sel, prop: page.locator(sel).first.evaluate(f"(e) => getComputedStyle(e).{prop}")  # noqa: E731
        assert css(".nav .button-primary", "backgroundColor") == "rgb(45, 108, 243)"
        assert css(".nav .button-primary", "color") == "rgb(255, 255, 255)"
        assert "rgba(45, 108, 243, 0.35)" in css(".nav .button-primary", "boxShadow")
        assert css(".evidence-card .link", "textDecorationLine") == "none"
        assert css(".logo-mark path", "fill") == "rgb(45, 108, 243)"
        page = s.plan()
        assert css(".src-qloo", "borderTopStyle") == "solid"
        assert css(".src-qloo", "backgroundColor") == "rgb(234, 241, 254)"
        assert s.errors == []
