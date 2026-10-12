"""The whole user journey in a real browser against the real app and data (precomputed runtime data or the API cache),
with every network request from the server refused: game -> comparable games -> live trace -> plan -> map -> country
-> language -> budget -> evidence -> report export -> track record. Skipped without the local cache."""
import re

import pytest

from babel import api, net
from babel import plan as P
from live_server import serve

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect
SLOW = 30_000  # ms: steps that wait on the server, generous so a loaded machine does not flake
pytestmark = pytest.mark.skipif(not any((P.ROOT / "cache" / "qloo").glob("heatmap_*")),
                                reason="needs the local API cache")


@pytest.fixture(scope="module")
def site():
    """The real app on a live port, warmed up, with the server's network and Claude refused."""
    import anthropic
    monkey = pytest.MonkeyPatch()

    def refuse(*args, **kwargs):
        raise AssertionError("network call during an offline test")
    monkey.setattr(net, "request", refuse)
    monkey.setattr(anthropic, "Anthropic", refuse)
    app = api.create_app(api.Settings(warmup=True))
    with serve(app) as url, playwright_api.sync_playwright() as p:
        assert app.state.babel.ready.wait(180), app.state.babel.data_status
        browser = p.chromium.launch()
        yield url, browser
        browser.close()
    monkey.undo()


def new_page(site, width=1280):
    url, browser = site
    context = browser.new_context(viewport={"width": width, "height": 900})
    context.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda route: route.abort())
    context.set_default_timeout(SLOW)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
            and errors.append(m.text))
    page.goto(url)
    return page, errors


def run_demo(page, demo):
    page.get_by_role("button", name=demo).click()
    page.locator(".card").first.wait_for(timeout=30_000)
    page.get_by_role("button", name="Run the plan").click()
    page.locator('.step[data-state="done"]').first.wait_for(timeout=30_000)  # the live trace
    expect(page.locator("#view-plan")).to_be_visible(timeout=90_000)
    expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready", timeout=30_000)


def test_the_full_journey_for_webfishing(site):
    page, errors = new_page(site)
    run_demo(page, "WEBFISHING")
    expect(page.locator("#plan-title")).to_have_text("Translate Russian and Spanish.", timeout=SLOW)
    # map: a country, then a language
    page.locator("#country-search").fill("Japan")
    page.locator("#country-search").press("Enter")
    expect(page.locator("#panel-title")).to_have_text("Japan", timeout=SLOW)
    expect(page.locator("#map-panel")).to_contain_text("A Hat in Time", timeout=SLOW)
    page.get_by_role("button", name="← All countries").click()
    page.get_by_role("button", name="Spanish: show its countries").click()
    assert page.locator("path.outline-highlight").count() == 6
    # budget
    page.locator("#plan-budget").fill("4000")
    expect(page.locator("#plan-title")).to_have_text("Translate Russian.", timeout=SLOW)
    page.get_by_role("button", name="Back to $10,000").click()
    expect(page.locator("#plan-title")).to_have_text("Translate Russian and Spanish.", timeout=SLOW)
    # evidence
    page.get_by_role("button", name="Why this recommendation for Russian?").click()
    expect(page.locator("#why-dialog")).to_contain_text("Mean S1", timeout=SLOW)
    page.keyboard.press("Escape")
    expect(page.locator("#evidence-grid")).to_contain_text("Not used: Qloo has no real data", timeout=SLOW)
    # report export
    page.get_by_role("button", name="Export report").click()
    report = page.locator("#view-report")
    expect(report).to_be_visible(timeout=SLOW)
    expect(report).to_contain_text("WEBFISHING", timeout=SLOW)
    expect(report).to_contain_text("Russian", timeout=SLOW)
    assert report.locator("svg path[fill]").count() > 100
    page.get_by_role("button", name="Back to the plan").click()
    expect(page.locator("#view-plan")).to_be_visible(timeout=SLOW)
    # track record
    page.get_by_role("link", name="Track record").first.click()
    expect(page.locator("#view-track")).to_be_visible(timeout=SLOW)
    expect(page.locator("#track-title")).to_be_focused(timeout=SLOW)
    assert errors == []


@pytest.mark.parametrize("demo, first", [("Dawnsbury Days", "Russian"), ("Never Second in Rome", "Russian")])
def test_the_other_demo_games(site, demo, first):
    page, errors = new_page(site)
    run_demo(page, demo)
    expect(page.locator("#plan-title")).to_contain_text(f"Translate {first}", timeout=SLOW)
    assert page.locator("path.country").evaluate_all(
        "els => els.filter(e => e.getAttribute('fill') !== 'url(#map-hatch)').length") > 60
    assert errors == []


def test_the_description_demo(site):
    page, errors = new_page(site)
    page.get_by_role("button", name="A cozy farming idea").click()
    page.locator(".card").first.wait_for(timeout=30_000)
    expect(page.locator("#game-summary")).to_contain_text("Your game", timeout=SLOW)
    page.get_by_role("button", name="Run the plan").click()
    expect(page.locator("#view-plan")).to_be_visible(timeout=90_000)
    expect(page.locator("#plan-title")).to_contain_text("Translate", timeout=SLOW)
    assert errors == []
