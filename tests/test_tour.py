"""The guided tour (web/static/tour.js) in a real browser, on the real app with test_web.py's fake look-up and fake
agent (whose result is a real plan from synthetic data). The tour walks every step over the real UI, runs the demo
once through the app's own buttons, keeps each step's target highlighted and in view, and ends cleanly from any step
(Esc, Skip tour, a server that is not ready, a demo that fails). Needs: python -m playwright install chromium
"""
import re
import time

import pytest

from test_track_web import LOW_CONTRAST, luminance
from test_web import FakeAgent, Site, browser  # noqa: F401  (the browser fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect
STEPS = ["welcome", "input", "demo", "comparables", "words", "run", "trace", "headline", "map", "country",
         "language", "plan", "why", "versus", "evidence", "report", "track", "assistant", "done"]
NO_OVERFLOW = "document.documentElement.scrollWidth <= window.innerWidth"
SETTLED = "() => { const l = document.querySelector('.tour-layer'); return !l || l.dataset.state !== 'busy'; }"
LAYOUT = """() => {
  const layer = document.querySelector('.tour-layer');
  if (!layer) return null;
  const box = (el) => { const r = el.getBoundingClientRect(); return {top: r.top, left: r.left, bottom: r.bottom,
    right: r.right}; };
  const rs = [...document.querySelectorAll('.is-tour-target')].map(box);
  const union = rs.length ? {top: Math.min(...rs.map((r) => r.top)), left: Math.min(...rs.map((r) => r.left)),
    bottom: Math.max(...rs.map((r) => r.bottom)), right: Math.max(...rs.map((r) => r.right))} : null;
  const pop = document.querySelector('.tour-pop');
  const text = (sel) => document.querySelector(sel).textContent;
  return {step: layer.dataset.step, state: layer.dataset.state, side: pop.dataset.side, count: text('.tour-count'),
    title: text('.tour-title'), copy: [text('.tour-title'), text('.tour-body'), text('.tour-note')].join(' '),
    union, spot: box(document.querySelector('.tour-spot')), pop: box(pop), vw: document.documentElement.clientWidth,
    vh: innerHeight, focused: pop.contains(document.activeElement), view: document.body.dataset.view};
}"""
# The highlighted elements are in view (all of them, or the top of a target taller than the viewport) and the
# spotlight covers them, with no more than its padding around them (it is kept inside the viewport).
IN_VIEW = """() => {
  const rs = [...document.querySelectorAll('.is-tour-target')].map((el) => el.getBoundingClientRect());
  if (!rs.length) return false;
  const top = Math.min(...rs.map((r) => r.top)), bottom = Math.max(...rs.map((r) => r.bottom));
  const left = Math.min(...rs.map((r) => r.left)), right = Math.max(...rs.map((r) => r.right));
  const vh = innerHeight, vw = document.documentElement.clientWidth;
  const shown = Math.min(bottom, vh) - Math.max(top, 0);
  const s = document.querySelector('.tour-spot').getBoundingClientRect();
  const covers = s.top <= Math.max(top, 3) + 1 && s.bottom >= Math.min(bottom, vh - 3) - 1
    && s.left <= Math.max(left, 3) + 1 && s.right >= Math.min(right, vw - 3) - 1;
  const snug = s.top >= top - 8 && s.bottom <= bottom + 8 && s.left >= left - 8 && s.right <= right + 8;
  return shown >= Math.min(bottom - top, vh - 32) - 2 && covers && snug;
}"""


def nav(page):
    """The nav's "Take the tour" button (the assistant has a suggestion chip with the same name)."""
    return page.locator('.nav button[data-action="tour"]')


def pop(page):
    return page.locator(".tour-pop")


def settle(page):
    """Wait until the current step is ready (not getting ready) and return its layout, or None after the end."""
    page.wait_for_function(SETTLED, timeout=20_000)
    return page.evaluate(LAYOUT)


def total(info):
    return int(re.fullmatch(r"Step \d+ of (\d+)", info["count"]).group(1))


def check_step(page, info):
    """The step's target is highlighted and in view; the popover is on screen, labelled, focused and free of
    numbers of its own (every number on screen comes from the server)."""
    if info["union"] is not None:
        try:
            page.wait_for_function(IN_VIEW, timeout=3_000)
        except playwright_api.TimeoutError:
            pytest.fail(f"{info['step']}: its target is not highlighted in view: {page.evaluate(LAYOUT)}")
        info = page.evaluate(LAYOUT)
        p, u = info["pop"], info["union"]
        vis = {"top": max(u["top"], 0), "bottom": min(u["bottom"], info["vh"]), "left": max(u["left"], 0),
               "right": min(u["right"], info["vw"])}
        if info["side"] in ("bottom", "top", "left", "right"):  # beside the target, not on it
            assert (p["right"] <= vis["left"] + 1 or p["left"] >= vis["right"] - 1 or p["bottom"] <= vis["top"] + 1
                    or p["top"] >= vis["bottom"] - 1), info
    p = info["pop"]
    assert p["left"] >= 0 and p["top"] >= 0 and p["right"] <= info["vw"] and p["bottom"] <= info["vh"], info
    assert info["focused"], info
    assert not re.search(r"\d", info["copy"]), info["copy"]
    expect(page.get_by_role("dialog", name=info["title"], exact=True)).to_be_visible()


def next_button(page):
    return pop(page).locator(".tour-next")


def advance_to(page, step):
    """Press Next until the tour shows `step`; returns its layout."""
    for _ in range(len(STEPS)):
        info = settle(page)
        assert info and info["state"] != "error", info
        if info["step"] == step:
            return info
        next_button(page).click()
    pytest.fail(f"the tour never reached {step}")


def walk(page, on_step=None, start=1):
    """Press Next through the rest of the tour (from step number `start`), checking every step; returns the step ids
    seen."""
    seen, n = [], None
    while True:
        info = settle(page)
        if info is None:
            return seen
        assert info["state"] != "error", info["copy"]
        seen.append(info["step"])
        n = n or total(info)
        assert info["count"] == f"Step {start + len(seen) - 1} of {n}", info
        assert (info["union"] is None) == (info["step"] in ("welcome", "done")), info  # every other step lights one
        check_step(page, info)
        if on_step:
            on_step(info)
        assert len(seen) <= len(STEPS)
        next_button(page).click()


# ---------------------------------------------------------------- the whole tour
def test_the_tour_walks_the_whole_product_over_the_real_ui(browser):
    with Site(browser, viewport=(1440, 900)) as s:
        page = s.page
        page.emulate_media(reduced_motion="reduce")
        nav(page).click()

        def on_step(info):
            step = info["step"]
            if step == "comparables":  # the tour clicked the real demo button: one look-up, for WEBFISHING
                assert s.lookup.calls == [{"appid": 3146520, "name": None, "description": None}]
                expect(page.locator("#cards .card")).to_have_count(3)
            elif step == "words":
                expect(page.locator("#words")).to_have_value("30000")
                expect(page.locator("#budget")).to_have_value("10000")
            elif step == "trace":  # the real run's events, as the server sent them
                assert len(s.agent.calls) == 1 and info["view"] == "working"
                states = page.locator("#checklist .step").evaluate_all("els => els.map((e) => e.dataset.state)")
                assert states.count("done") >= 7 and not {"running", "pending", "failed"} & set(states)
            elif step == "headline":
                expect(page.locator("#plan-title")).to_have_text(re.compile(r"^Translate "))
            elif step == "country":
                expect(page.locator("#panel-title")).to_have_text("Japan")
            elif step == "language":
                expect(page.locator("#panel-title")).to_have_text("Spanish")
            elif step == "why":
                expect(page.locator("#why-dialog")).to_be_visible()
            elif step == "versus":  # the tour closed the dialog it opened
                expect(page.locator("#why-dialog")).to_be_hidden()
            elif step == "report":
                expect(page.locator("#view-report .report-sheet")).to_be_visible()
            elif step == "track":
                expect(page.locator(".tr-verdict")).to_have_count(2)
                expect(page.locator("#view-track .tr-summary .tr-verdict-title")).to_have_text(
                    re.compile(r"^About [\d to]+× the reach of the usual list$"))
                expect(page.locator(".tr-qloo .tr-facts")).to_contain_text("Very unlikely to be luck")
            elif step == "assistant":
                expect(page.locator("#assistant-launcher")).to_have_class(re.compile(r"\bis-tour-target\b"))
                expect(page.locator(".is-tour-target")).to_have_count(1)
            elif step == "done":
                assert info["view"] == "plan" and info["side"] == "center"
                expect(next_button(page)).to_have_text("Finish")

        seen = walk(page, on_step)
        assert seen in (STEPS, [x for x in STEPS if x != "assistant"])
        expect(page.locator(".tour-layer")).to_have_count(0)
        expect(page.locator(".is-tour-target")).to_have_count(0)
        expect(nav(page)).to_be_focused()  # focus is back where the tour started
        expect(page.locator("#view-plan")).to_be_visible()  # and the demo plan stays open
        call = s.agent.calls[0]
        assert len(s.agent.calls) == 1 and call["appid"] == 3146520 and call["word_count"] == 30000
        assert call["budget"] == 10000 and call["with_markets"] and call["with_explanation"]
        assert s.errors == []


def test_keyboard_back_and_escape(browser):
    with Site(browser) as s:
        page = s.page
        nav(page).focus()
        page.keyboard.press("Enter")
        info = settle(page)
        expect(page.get_by_role("dialog", name="Welcome to Babel", exact=True)).to_be_visible()
        expect(next_button(page)).to_be_focused()
        expect(pop(page).get_by_role("button", name="Back")).to_be_hidden()  # nothing before the first step
        assert info["count"] == f"Step 1 of {total(info)}"
        for _ in range(3):
            page.keyboard.press("ArrowRight")
        assert settle(page)["step"] == "comparables" and len(s.lookup.calls) == 1
        page.keyboard.press("ArrowLeft")
        info = settle(page)
        assert info["step"] == "demo" and "already loaded" in info["copy"]
        expect(page.locator(".tour-layer [aria-live]")).to_have_text(re.compile(r"^Step 3 of \d+: Try a demo\. "))
        back = pop(page).get_by_role("button", name="Back")
        back.click()
        assert settle(page)["step"] == "input"
        expect(back).to_be_focused()  # focus stays on the button in use
        page.keyboard.press("Tab")
        expect(next_button(page)).to_be_focused()
        page.keyboard.press("Enter")
        assert settle(page)["step"] == "demo"
        page.keyboard.press("ArrowRight")
        assert settle(page)["step"] == "comparables"
        assert len(s.lookup.calls) == 1  # Back and Next again do not repeat the demo's request
        page.keyboard.press("Escape")
        expect(page.locator(".tour-layer")).to_have_count(0)
        expect(nav(page)).to_be_focused()
        expect(page.locator("#setup")).to_be_visible()  # the app is left as the tour made it
        assert s.errors == []


def test_ending_mid_tour_keeps_the_plan_and_closes_what_the_tour_opened(browser):
    with Site(browser) as s:
        page = s.page
        page.emulate_media(reduced_motion="reduce")
        nav(page).click()
        advance_to(page, "why")
        expect(page.locator("#why-dialog")).to_be_visible()
        expect(next_button(page)).to_be_focused()  # the popover lives in the open dialog, so it stays usable
        page.keyboard.press("Escape")
        expect(page.locator(".tour-layer")).to_have_count(0)
        expect(page.locator("#why-dialog")).to_be_hidden()
        expect(nav(page)).to_be_focused()
        expect(page.locator("#plan-title")).to_have_text(re.compile(r"^Translate "))
        page.get_by_role("button", name="See every step").click()  # the app is usable as before
        expect(page.locator("#view-working")).to_be_visible()
        assert len(s.agent.calls) == 1 and s.errors == []


def test_a_missing_target_is_skipped_without_hanging(browser):
    with Site(browser) as s:
        page = s.page
        page.emulate_media(reduced_motion="reduce")
        page.evaluate("document.querySelector('#assistant-root')?.remove()")  # no assistant on this page
        nav(page).click()
        info = settle(page)
        n = total(info)
        assert n == len(STEPS) - 1  # the assistant's step is left out
        advance_to(page, "why")
        page.evaluate("document.querySelector('.versus').hidden = true")  # the next step's target is gone
        started = time.monotonic()
        next_button(page).click()
        info = settle(page)
        assert info["step"] == "evidence" and time.monotonic() - started < 8
        assert info["count"] == f"Step {STEPS.index('evidence') + 1} of {n}"  # the count skips the missing step
        seen = walk(page, start=STEPS.index("evidence") + 1)
        assert seen == ["evidence", "report", "track", "done"]
        expect(nav(page)).to_be_focused()


def test_skip_tour_ends_it_at_once(browser):
    with Site(browser) as s:
        page = s.page
        nav(page).click()
        advance_to(page, "input")
        pop(page).get_by_role("button", name="Skip tour").click()
        expect(page.locator(".tour-layer")).to_have_count(0)
        expect(nav(page)).to_be_focused()
        assert s.lookup.calls == [] and s.agent.calls == []


def test_the_assistant_panel_never_hides_the_tour(browser):
    with Site(browser, viewport=(1440, 900)) as s:  # wide: the panel docks beside the page
        page = s.page
        if not page.locator("#assistant-launcher").count():
            pytest.skip("this page has no assistant")
        page.locator("#assistant-launcher").click()
        expect(page.locator("#assistant-panel")).to_be_visible()
        nav(page).click()
        expect(page.locator("#assistant-panel")).to_be_hidden()  # the tour closed it with its own button
        expect(page.locator("#assistant-launcher")).to_be_visible()
        assert settle(page)["step"] == "welcome"
        expect(next_button(page)).to_be_focused()
        page.keyboard.press("Escape")
    with Site(browser, viewport=(1100, 900)) as s:  # narrower: a modal sheet, the page behind it inert
        page = s.page
        nav(page).click()
        advance_to(page, "input")
        page.locator("#assistant-launcher").click()  # the person opens it mid-tour
        expect(page.locator("#assistant-panel")).to_be_visible()
        next_button(page).click()  # the popover stays usable above the sheet
        info = settle(page)
        assert info["step"] == "demo" and info["focused"]
        expect(page.locator("#assistant-panel")).to_be_hidden()
        check_step(page, info)
        page.keyboard.press("Escape")
        expect(page.locator(".tour-layer")).to_have_count(0)
        assert s.errors == []


# ---------------------------------------------------------------- when the demo cannot run
def test_a_server_that_is_not_ready_ends_the_tour_cleanly(browser):
    with Site(browser, ready=False) as s:
        page = s.page
        nav(page).click()
        expect(pop(page)).to_contain_text("still loading its data")
        close = pop(page).get_by_role("button", name="Close")
        expect(close).to_be_focused()
        expect(pop(page).get_by_role("button", name="Back")).to_be_hidden()
        page.keyboard.press("Enter")
        expect(page.locator(".tour-layer")).to_have_count(0)
        expect(nav(page)).to_be_focused()
        assert s.lookup.calls == [] and s.agent.calls == []


def test_a_demo_that_fails_says_so_and_ends_cleanly(browser):
    with Site(browser, agent=FakeAgent(crash=True)) as s:
        page = s.page
        nav(page).click()
        advance_to(page, "run")
        next_button(page).click()
        expect(pop(page)).to_contain_text("The demo plan didn't finish", timeout=15_000)
        assert page.locator(".tour-layer").get_attribute("data-step") == "error"
        expect(pop(page)).to_contain_text("Everything else in Babel still works")
        pop(page).get_by_role("button", name="Close").click()
        expect(page.locator(".tour-layer")).to_have_count(0)
        expect(page.locator("#run-outcome")).to_contain_text("The plan stopped")  # the app's own error, as before
        expect(page.get_by_role("button", name="Try again")).to_be_enabled()
        assert len(s.agent.calls) == 1


# ---------------------------------------------------------------- phones, the nav button, the invitation
def test_the_tour_on_a_phone(browser):
    with Site(browser, viewport=(390, 844)) as s:
        page = s.page
        page.emulate_media(reduced_motion="reduce")
        button, logo = nav(page).bounding_box(), page.locator(".logo").bounding_box()
        assert button["x"] >= logo["x"] + logo["width"] and button["x"] + button["width"] <= 390  # visible, no overlap

        def on_step(info):
            assert page.evaluate(NO_OVERFLOW), info["step"]
        nav(page).click()
        seen = walk(page, on_step)
        assert seen[0] == "welcome" and seen[-1] == "done" and len(seen) >= len(STEPS) - 1
        assert page.evaluate(NO_OVERFLOW) and s.errors == []


def test_the_tour_in_the_dark_theme(browser):
    """The system's dark setting: the invitation and every step's popover are dark with WCAG AA text, and the page
    around the spotlight is dimmed more than in the light theme."""
    with Site(browser, color_scheme="dark") as s:
        page = s.page
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        expect(page.locator(".tour-invite")).to_be_visible()
        assert page.evaluate(LOW_CONTRAST, ".tour-invite") == []

        def on_step(info):
            assert luminance(pop(page).evaluate("e => getComputedStyle(e).backgroundColor")) < 0.02, info["step"]
            assert page.evaluate(LOW_CONTRAST, ".tour-pop") == [], info["step"]
            spot = page.locator(".tour-spot").evaluate("e => getComputedStyle(e).boxShadow")
            assert ("rgba(0, 0, 0, 0.3)" if page.locator(".tour-layer.is-in-dialog").count()
                    else "rgba(0, 0, 0, 0.6)") in spot, info["step"]
        nav(page).click()
        seen = walk(page, on_step)
        assert seen[0] == "welcome" and seen[-1] == "done" and "why" in seen
        assert s.errors == []


def test_the_first_visit_invitation(browser):
    with Site(browser) as s:
        page = s.page
        invite = page.locator(".tour-invite")
        expect(invite).to_contain_text("New here?")
        page.get_by_role("button", name="Dismiss the tour invitation").click()
        expect(invite).to_have_count(0)
        expect(nav(page)).to_be_focused()
        page.reload()
        expect(page.locator("#hero-title")).to_be_visible()
        expect(invite).to_have_count(0)  # dismissed for good
        page.evaluate("localStorage.clear()")
        page.reload()
        page.get_by_role("button", name="Take the 2-minute tour").click()
        expect(page.get_by_role("dialog", name="Welcome to Babel", exact=True)).to_be_visible()
        expect(invite).to_have_count(0)
        nav(page).click()  # restarts the tour: still one layer, back at the first step
        assert settle(page)["count"].startswith("Step 1 of ")
        expect(page.locator(".tour-layer")).to_have_count(1)
        page.keyboard.press("Escape")
        expect(nav(page)).to_be_focused()  # the invitation is gone, so focus goes to the nav button
        assert s.errors == []
