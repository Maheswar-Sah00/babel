"""The top navigation in a real browser: exactly the logo, How it works, Take the tour, Ask AI agent, GitHub, the theme
switch and Plan a game; each one works from any screen; phones keep the essentials; the footer has no links.
Needs: python -m playwright install chromium
"""
import pytest

from test_web import Site, browser  # noqa: F401  (the browser fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect

VISIBLE = """() => [...document.querySelectorAll('.nav a, .nav button')].filter((e) => e.offsetParent)
  .map((e) => (e.getAttribute('aria-label') || e.textContent).trim())"""


def test_the_nav_has_exactly_the_chosen_items(browser):
    with Site(browser, viewport=(1440, 900)) as s:
        assert s.page.evaluate(VISIBLE) == ["Babel home", "How it works", "Take the tour", "Ask AI agent", "GitHub",
                                            "Dark mode", "Plan a game"]
        assert s.page.locator(".nav").get_by_text("Track record").count() == 0
        assert not s.errors


def test_ask_ai_agent_opens_the_assistant_and_points_at_its_launcher(browser):
    with Site(browser, viewport=(1440, 900)) as s:
        page = s.page
        launcher = page.locator("#assistant-launcher")
        page.get_by_role("button", name="Ask AI agent").hover()
        assert launcher.evaluate("el => getComputedStyle(el).outlineStyle") == "solid"  # the corner button lights up
        page.get_by_role("button", name="Ask AI agent").click()
        expect(page.locator("#assistant-input")).to_be_focused()
        expect(launcher).to_be_hidden()
        assert not s.errors


def test_how_it_works_works_from_the_plan_and_the_footer_has_no_links(browser):
    with Site(browser, viewport=(1280, 900)) as s:
        page = s.plan()
        page.get_by_role("link", name="How it works").click()
        expect(page.locator("body")).to_have_attribute("data-view", "start")
        expect(page.locator("#how")).to_be_in_viewport()
        expect(page.locator("footer a")).to_have_count(0)
        assert not s.errors


@pytest.mark.parametrize("width", [820, 390])
def test_smaller_screens_keep_the_essentials(browser, width):
    with Site(browser, viewport=(width, 800)) as s:
        seen = s.page.evaluate(VISIBLE)
        assert {"Babel home", "Take the tour", "Dark mode", "Plan a game"} <= set(seen)
        if width < 600:
            assert "Ask AI agent" not in seen and "GitHub" not in seen  # the launcher stays in the corner
        assert s.page.evaluate("document.documentElement.scrollWidth") == width
