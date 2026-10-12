"""Browser tests: real Chromium (Playwright) against the real FastAPI app over HTTP.

Most tests swap in a fake agent and fake look-alike lookup (same signatures as babel.agent.run and babel.suggest) so
they are fast and can force failures; the fake agent's result is a real plan built by the engine from synthetic Qloo
fan maps (tests/synthetic.py). The budget slider calls the real POST /fit-budget. The last test runs the whole real
pipeline from the local cache. External requests from the browser (fonts, Steam images) are blocked: the tests run
offline. Needs: python -m playwright install chromium
"""
import base64
import json
import os
import re
import time

import pytest

import synthetic
from babel import api, net
from babel import plan as P
from babel.languages import COUNTRIES, LABEL, OFFICIAL_IN
from live_server import serve

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect
STEPS = ["game", "lookalikes", "fan_maps", "score", "optimize", "markets", "explain", "verify"]
HATCH = "url(#map-hatch)"
DIV_STRONG_BLUE, DIV_LIGHT_BLUE, SEQ_BIN3, PLAN_TRANSLATE = "#1c5cab", "#86b6ef", "#184f95", "#2a78d6"
# the dark theme's map palettes (web/static/mapdata.js, validated there against the dark map surface): monochrome
# greys, except the red "fewer" arm and the plan's store page (orange) and already supported (green)
DARK_SEQ = ["#484848", "#696969", "#8c8c8c", "#b4b4b4", "#e1e1e1"]
DARK_DIV = ["#ec9890", "#b3302c", "#3a3a3a", "#808080", "#e2e2e2"]
DARK_PLAN = {"translate_game": "#e8e8e8", "store_page_only": "#d95926", "skip": "#606060",
             "already_supported": "#199e70"}
DARK_NOT_COUNTED, DARK_HATCH = "#1b1b1b", ("#141414", "#404040")


def card(appid, name, status="valid", overlap=0.2, why="Shared tags: Cozy, Farming Sim"):
    return {"appid": appid, "name": name, "status": status, "usable": status == "valid",
            "qloo_id": f"Q{appid}" if status == "valid" else None, "overlap": overlap, "why": why, "year": 2020,
            "image": None}


class FakeLookup:
    """babel.suggest's three functions, with fixed games."""

    def __init__(self):
        self.calls = []

    def suggest(self, ctx, appid=None, name=None, description=None):
        self.calls.append({"appid": appid, "name": name, "description": description})
        if name == "Nope":
            raise P.PlanError("No Steam game found for 'Nope'.")
        return {"game": {"appid": None if description else (appid or 42),
                         "name": "Your game" if description else "Test Game", "release_date": "2024-05-01",
                         "supported_languages": ["german"], "top_tags": ["Cozy", "Farming Sim"], "image": None},
                "source": "description" if description else "steam_tags",
                "lookalikes": [card(11, "Alpha Farm", overlap=0.3), card(12, "Beta Town"),
                               card(13, "Gamma Isle", overlap=0.15)],
                "alternatives": [card(21, "Alt One", overlap=0.12), card(22, "Alt Two", overlap=0.1)],
                "rejected": [card(31, "Ghost Game", "default map")], "widened_search": False, "notes": [],
                "confidence": {"level": "medium", "reasons": ["The genre is mixed from this description."]}
                if description else None}

    def search(self, ctx, q):
        games = [card(41, "Starry Night", "unchecked", None, None), card(42, "Star Farmer", "valid", None, None)]
        return [g for g in games if q.lower() in g["name"].lower()]

    def check(self, ctx, appid):
        return card(appid, "Starry Night" if appid == 41 else "Star Farmer", "default map" if appid == 41 else "valid",
                    None, None)


class FakeAgent:
    """Has babel.agent.run's signature: emits a realistic sequence of events with a delay between them, and returns
    a real plan made by the engine from synthetic fan maps (no_data: no comparable game has a fan map)."""

    def __init__(self, delay=0.05, crash=False, partial=False, extra=0, no_data=False):
        self.delay, self.crash, self.partial, self.extra, self.no_data = delay, crash, partial, extra, no_data
        self.calls, self.emitted = [], 0

    def __call__(self, kwargs, ctx, sink):
        self.calls.append(kwargs)
        events = []

        def emit(type_, step, status, message, /, **data):
            events.append({"v": 1, "seq": len(events) + 1, "type": type_, "step": step, "status": status,
                           "message": message, "data": data})
            sink(events[-1])
            self.emitted = len(events)
            time.sleep(self.delay)
        emit("plan", "goal", "info", "Goal: a translation plan.", steps=STEPS)
        emit("act", "game", "started", "Looking up the game on Steam.")
        emit("act", "game", "ok", "Found Test Game (Steam 42).")
        for i in range(self.extra):
            emit("act", "lookalikes", "ok", f"Checking candidate {i + 1}.")
        emit("act", "lookalikes", "ok", "Look-alikes with real Qloo fan maps: Alpha Farm, Beta Town, Gamma Isle.")
        emit("reflect", "lookalikes", "warning", "Ghost Game: Qloo has only its default (no-data) map; not used.")
        if self.crash:
            raise ValueError("boom C:/babel/cache/secret")
        emit("act", "fan_maps", "ok", "Alpha Farm: Qloo world fan map read.")
        emit("act", "score", "ok", "Ranked the 14 languages.", detail="typical language mix × Qloo lift (alpha 1).")
        emit("act", "optimize", "ok", "Fitted the budget.")
        emit("act", "markets", "ok", "Russian -> Russia: films Film Alpha, Film Beta.")
        if self.partial:
            emit("error", "markets", "failed", "A request failed after 3 attempts; continuing without that data.")
        emit("explain", "explain", "ok", "Russian comes first.", kind="llm_text")
        emit("verify", "verify", "ok", "Budget respected.")
        status = "partial" if self.partial else "ok"
        result = synthetic.result(kwargs["word_count"], kwargs["budget"], valid=not self.no_data)
        emit("done", "result", "ok" if status == "ok" else "warning", "Plan ready.", status=status, result=result)
        return {"status": status, "result": result, "events": events}


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


class Site:
    """A live app (fakes inside), plus a browser page on it that blocks external requests and records errors."""

    def __init__(self, browser, agent=None, lookup=None, ready=True, viewport=(1280, 900), color_scheme="light",
                 **settings):
        self.agent, self.lookup = agent or FakeAgent(), lookup or FakeLookup()
        self.app = api.create_app(api.Settings(warmup=False, **settings), runner=self.agent, lookup=self.lookup)
        self.state = self.app.state.babel
        if ready:
            self.make_ready()
        self.browser, self.viewport, self.color_scheme = browser, viewport, color_scheme

    def make_ready(self):
        self.state.ctx = "CTX"
        self.state.ready.set()

    def __enter__(self):
        self._env = pytest.MonkeyPatch()  # readiness needs a Qloo key configured; the fakes never use it
        for name in ("QLOO_API_KEY", "ANTHROPIC_API_KEY"):
            if not os.environ.get(name):
                self._env.setenv(name, "placeholder-not-a-key")
        self._server = serve(self.app)
        self.url = self._server.__enter__()
        self.context = self.browser.new_context(viewport=dict(zip(("width", "height"), self.viewport)),
                                                color_scheme=self.color_scheme)
        self.context.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda route: route.abort())
        self.context.set_default_timeout(10_000)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
                     and self.errors.append(m.text))
        self.page.goto(self.url)
        return self

    def __exit__(self, *exc):
        self.context.close()
        self._server.__exit__(*exc)
        self._env.undo()

    def find(self, appid=3146520):
        page = self.page
        page.locator("#game-input").fill(f"https://store.steampowered.com/app/{appid}/")
        page.get_by_role("button", name="Find similar games").click()
        page.locator(".card").first.wait_for()

    def plan(self, map_ready=True):
        """Find the game, run the plan and wait for the Plan screen (and its map)."""
        self.find()
        self.page.get_by_role("button", name="Run the plan").click()
        expect(self.page.locator("#view-plan")).to_be_visible()
        if map_ready:
            expect(self.page.locator("#map-canvas")).to_have_attribute("data-state", "ready")
        return self.page


def expect_text(locator, text):
    expect(locator).to_contain_text(text)


def fill(page, cc):
    return page.locator(f'path.country[data-cc="{cc}"]').get_attribute("fill")


def click_country(page, cc):
    """A real mouse click on a point inside the country's shape (its bounding box centre can be sea or a neighbour)."""
    page.mouse.click(*point_in(page, cc))


def point_in(page, cc):
    """A visible screen point inside the country's shape."""
    page.locator("#map-canvas").scroll_into_view_if_needed()
    point = page.evaluate("""(cc) => {
      const p = document.querySelector(`path.country[data-cc="${cc}"]`);
      const box = p.getBBox(), ctm = p.getScreenCTM(), pt = p.ownerSVGElement.createSVGPoint();
      for (let i = 1; i < 24; i++) for (let j = 1; j < 24; j++) {
        pt.x = box.x + box.width * i / 24; pt.y = box.y + box.height * j / 24;
        if (!p.isPointInFill(pt)) continue;
        const s = pt.matrixTransform(ctm);
        if (document.elementFromPoint(s.x, s.y) === p) return [s.x, s.y];
      }
      return null;
    }""", cc)
    assert point, f"no visible point inside {cc}"
    return point


def zoom(page):
    return float(page.locator("#map-canvas").get_attribute("data-zoom") or 1)


def group_names(page, group):
    return page.locator(f"section[aria-labelledby='pg-{group}'] .lang-name").all_inner_texts()


def metric(page, key):
    return page.locator(f'input[name="metric"][value="{key}"]')


def choose_metric(page, key):
    page.locator(f'label.metric-option:has(input[value="{key}"])').click()


def wait_zoom(page, check):
    page.wait_for_function(f"() => {{ const k = Number(document.querySelector('#map-canvas').dataset.zoom || 1); "
                           f"return {check}; }}")


def rgb(hex_color):
    """'#3987e5' as getComputedStyle reports it."""
    return "rgb({}, {}, {})".format(*(int(hex_color[i:i + 2], 16) for i in (1, 3, 5)))


def legend_colors(page):
    """The legend's swatch colours, in order (None for the hatch swatch)."""
    return page.locator("#map-legend .swatch").evaluate_all(
        "els => els.map(e => e.classList.contains('swatch-hatch') ? null : getComputedStyle(e).backgroundColor)")


def hatch_ink(page, pattern="#map-hatch"):
    return (page.locator(f"pattern{pattern} rect").get_attribute("fill"),
            page.locator(f"pattern{pattern} line").get_attribute("stroke"))


# ---------------------------------------------------------------- Start and Working
def test_enter_a_game_swap_a_comparable_set_budget_and_watch_it_run(browser):
    with Site(browser, agent=FakeAgent(delay=0.12)) as s:
        page = s.page
        s.find()
        cards = page.locator(".card .card-title")
        assert cards.all_inner_texts() == ["Alpha Farm · 2020", "Beta Town · 2020", "Gamma Isle · 2020"]
        expect_text(page.locator("#game-summary"), "Test Game")
        expect_text(page.locator("#rejected-note"), "Also checked, not used: Qloo has no real fan data for Ghost Game.")
        page.get_by_role("button", name="Swap Beta Town").click()
        dialog = page.get_by_role("dialog")
        expect_text(dialog, "Alt One")
        dialog.get_by_role("button", name=re.compile("Alt One")).click()
        expect(dialog).to_be_hidden()
        assert cards.all_inner_texts()[1] == "Alt One · 2020"
        expect_text(page.locator(".card").nth(1), "Your pick")
        page.get_by_role("button", name="100k").click()
        page.get_by_label("Translation budget").fill("15000")
        page.get_by_role("button", name="Run the plan").click()

        expect_text(page.locator("#working-title"), "Planning Test Game")
        page.locator('.step[data-state="running"]').first.wait_for()  # progress arrives while the run is going
        expect(page.locator("#view-plan")).to_be_visible()  # then the Plan screen opens by itself
        expected = synthetic.result(100_000, 15_000)["plan"]
        first = LABEL[expected["groups"]["translate_game"][0]]
        expect_text(page.locator("#plan-title"), f"Translate {first}")
        assert group_names(page, "translate_game")[0] == first
        assert "Plan ready" in page.locator("#run-outcome").text_content()
        states = page.locator(".step").evaluate_all("els => els.map(e => [e.dataset.step, e.dataset.state])")
        assert states[0] == ["goal", "done"] and [s for s, _ in states[1:]] == STEPS
        assert dict(states)["lookalikes"] == "warning" and dict(states)["verify"] == "done"
        assert "null" not in page.locator("#view-plan").inner_text()
        assert page.locator("#raw-events li").count() >= 14
        # method notes stay out of the plain checklist, one click away in the detailed list
        expect_text(page.locator("#raw-events"), "Method: typical language mix × Qloo lift")
        assert "typical language mix" not in page.locator("#checklist").text_content()
        page.get_by_role("button", name="See every step").click()  # the trace is still there
        expect(page.locator("#view-working")).to_be_visible()
        page.get_by_role("button", name="Back to the plan").click()
        expect(page.locator("#plan-title")).to_be_focused()
        assert s.agent.calls == [{"appid": 3146520, "name": None, "description": None, "lookalikes": [11, 21, 13],
                                  "word_count": 100000, "budget": 15000.0, "with_markets": True,
                                  "with_explanation": True}]
        assert s.errors == []


def test_unchanged_comparables_are_left_to_the_engine(browser):
    with Site(browser) as s:
        s.plan(map_ready=False)
        assert s.agent.calls[0]["lookalikes"] is None  # the engine picks the same three itself


def test_a_description_with_keyboard_tabs(browser):
    with Site(browser) as s:
        page = s.page
        page.get_by_role("tab", name="Steam link").focus()
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        expect(page.get_by_role("tab", name="Describe it")).to_have_attribute("aria-selected", "true")
        page.locator("#game-description").fill("short")
        page.get_by_role("button", name="Find similar games").click()
        expect_text(page.locator("#game-error"), "at least 10 characters")
        assert s.lookup.calls == []
        page.locator("#game-description").fill("A cozy farming game on a small island with fishing.")
        page.get_by_role("button", name="Find similar games").click()
        notes = page.locator("#setup-notes")
        expect_text(notes, "Babel is fairly sure, but not certain")  # the plain message first
        reason = notes.get_by_text("The genre is mixed from this description.")
        expect(reason).to_be_hidden()  # the server's reasons, one click away
        notes.get_by_text("Why only fairly sure").click()
        expect(reason).to_be_visible()
        page.get_by_role("button", name="Run the plan").click()
        expect(page.locator("#view-plan")).to_be_visible()
        assert s.agent.calls[0]["description"].startswith("A cozy farming") and s.agent.calls[0]["appid"] is None


def test_search_and_check_a_game_to_swap_in(browser):
    with Site(browser) as s:
        page = s.page
        s.find()
        page.get_by_role("button", name="Swap Gamma Isle").click()
        page.get_by_label("Search").fill("sta")
        expect_text(page.locator("#swap-status"), "2 well-known games found")
        page.get_by_role("button", name=re.compile("Starry Night")).click()
        expect_text(page.locator(".card").nth(2), "Won't be used: Qloo has no real fan data")


def test_invalid_inputs_are_caught_before_any_request(browser):
    with Site(browser) as s:
        page = s.page
        page.get_by_role("button", name="Find similar games").click()
        expect_text(page.locator("#game-error"), "Paste a Steam store link")
        page.locator("#game-input").fill("https://example.com/app/1/")
        page.get_by_role("button", name="Find similar games").click()
        expect_text(page.locator("#game-error"), "Paste a Steam store link")
        expect(page.locator("#game-input")).to_have_attribute("aria-invalid", "true")
        assert s.lookup.calls == []
        s.find()
        page.get_by_label("Words to translate").fill("0")
        page.get_by_label("Translation budget").fill("-5")
        page.get_by_role("button", name="Run the plan").click()
        expect_text(page.locator("#words-error"), "whole number of words")
        expect_text(page.locator("#budget-error"), "budget from $0")
        assert s.agent.calls == []


def test_a_game_the_server_cannot_find(browser):
    with Site(browser) as s:
        page = s.page
        page.get_by_role("tab", name="Game name").click()
        page.locator("#game-input").fill("Nope")
        page.get_by_role("button", name="Find similar games").click()
        expect_text(page.locator("#game-error"), "No Steam game found for 'Nope'.")
        assert page.locator("#setup").is_hidden()


def test_a_loading_server_shows_a_banner_until_ready(browser):
    with Site(browser, ready=False) as s:
        page = s.page
        expect_text(page.locator("#ready-banner"), "loading its data")
        expect(page.get_by_role("button", name="Find similar games")).to_be_disabled()
        s.make_ready()
        expect(page.locator("#ready-banner")).to_be_hidden()
        expect(page.get_by_role("button", name="Find similar games")).to_be_enabled()


def test_a_failed_run_shows_the_error_and_can_retry(browser):
    with Site(browser, agent=FakeAgent(crash=True)) as s:
        page = s.page
        s.find()
        page.get_by_role("button", name="Run the plan").click()
        outcome = page.locator("#run-outcome")
        expect_text(outcome, "The plan stopped")
        expect_text(outcome, "Request ID")
        assert "secret" not in outcome.inner_text() and "null" not in outcome.inner_text()
        expect(page.locator(".step").filter(has_text="Find games like yours")).to_have_attribute("data-state", "failed")
        page.get_by_role("button", name="Try again").click()
        expect_text(outcome, "The plan stopped")
        assert len(s.agent.calls) == 2
        page.get_by_role("button", name="Back to setup").click()
        expect(page.locator("#setup")).to_be_visible()


def test_cancel_stops_the_run_on_the_server(browser):
    agent = FakeAgent(delay=0.2, extra=40)
    with Site(browser, agent=agent) as s:
        page = s.page
        s.find()
        page.get_by_role("button", name="Run the plan").click()
        expect_text(page.locator("#checklist"), "Checking candidate 2")
        page.get_by_role("button", name="Cancel").click()
        expect_text(page.locator("#run-outcome"), "Cancelled")
        time.sleep(1.5)
        stopped_at = agent.emitted
        time.sleep(1.0)
        assert agent.emitted == stopped_at < 30  # the server-side agent stopped too
        assert s.state.active == 0


def test_a_partial_result_opens_the_plan_with_its_warning(browser):
    with Site(browser, agent=FakeAgent(partial=True)) as s:
        page = s.plan(map_ready=False)
        expect_text(page.locator("#plan-alerts"), "Some data could not be read")
        expect_text(page.locator("#plan-alerts"), "A request failed after 3 attempts")
        assert "with warnings" in page.locator("#run-outcome").text_content()


def test_rate_limits_are_explained(browser):
    with Site(browser, plan_rate=(1, 60)) as s:
        page = s.plan(map_ready=False)
        page.get_by_role("button", name="Change the inputs").click()
        expect(page.locator("#setup")).to_be_visible()
        page.get_by_label("Translation budget").fill("9000")
        page.get_by_role("button", name="Run the plan").click()
        expect_text(page.locator("#run-outcome"), "going a little fast")
        page.get_by_role("button", name="Back to setup").click()
        expect(page.get_by_role("button", name="Run the plan")).to_be_disabled()


def test_the_swap_dialog_works_by_keyboard(browser):
    with Site(browser) as s:
        page = s.page
        s.find()
        swap = page.get_by_role("button", name="Swap Alpha Farm")
        swap.focus()
        page.keyboard.press("Enter")
        expect(page.get_by_role("dialog")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.get_by_role("dialog")).to_be_hidden()
        expect(swap).to_be_focused()


# ---------------------------------------------------------------- the Plan screen: map
def test_the_map_draws_real_country_scores_and_a_country_opens_its_evidence(browser):
    with Site(browser) as s:
        page = s.plan()
        assert page.locator("path.country").count() >= 170
        # default view: fans vs typical games (Qloo); colours come from the server's numbers, binned
        expect(metric(page, "relative")).to_be_checked()
        assert fill(page, "RU") == DIV_STRONG_BLUE  # 0.75 / 0.50 = x1.5
        assert fill(page, "BR") == DIV_LIGHT_BLUE  # 0.55 / 0.50 = x1.1
        assert fill(page, "UY") == HATCH  # a score, but too few reference games for a ratio
        assert fill(page, "AU") == HATCH  # no Qloo score at all
        page.locator('path.country[data-cc="BR"]').hover()
        expect_text(page.locator("#map-tooltip"), "Brazil")
        expect_text(page.locator("#map-tooltip"), "10% more fans than usual")  # x1.10, in words
        click_country(page, "BR")
        panel = page.locator("#map-panel")
        expect(page.locator("#panel-title")).to_have_text("Brazil")
        expect_text(panel, "10% more fans than usual (from 3 of 3 games like yours)")
        expect_text(panel, "Fan interest 0.55 on Qloo's 0–1 scale; the usual here is 0.50")  # the exact values
        for name in ("Alpha Farm", "Beta Town", "Gamma Isle"):
            expect_text(panel.locator("tbody"), name)
        expect_text(panel, "Babel counts Brazil for Portuguese-BR")
        assert page.locator("path.outline-selected").count() == 1
        page.get_by_role("button", name="← All countries").click()
        expect(page.locator("#country-search")).to_be_focused()
        assert page.locator("path.outline-selected").count() == 0
        click_country(page, "CA")  # French is official there, but not in Babel's score
        expect_text(panel, "French is official here, but Babel's score for it uses other countries")
        click_country(page, "RU")
        expect_text(panel, "What these fans also like here")
        expect_text(panel, "Film Alpha")
        assert s.errors == []


def test_selecting_a_language_highlights_its_markets(browser):
    with Site(browser) as s:
        page = s.plan()
        drawn = set(page.locator("path.country").evaluate_all("els => els.map(e => e.dataset.cc).filter(Boolean)"))
        page.get_by_role("button", name="Spanish: show its countries").click()
        expect(page.locator("#panel-title")).to_have_text("Spanish")
        expect_text(page.locator("#map-panel"), "Babel's Spanish score uses 6 countries")
        official_only = [cc for cc in OFFICIAL_IN["spanish"] if cc not in COUNTRIES["spanish"] and cc in drawn]
        assert page.locator("path.outline-highlight").count() == len(COUNTRIES["spanish"])
        assert page.locator("path.outline-alt").count() == len(official_only) > 10
        assert page.locator("path.country.is-dim").count() > 100
        page.get_by_role("button", name=re.compile("^Mexico")).click()  # from the language to one of its countries
        expect(page.locator("#panel-title")).to_have_text("Mexico")
        assert page.locator("path.country.is-dim").count() == 0
        # the same from the plan's language cards
        page.get_by_role("button", name="Show Russian on the map").click()
        expect(page.locator("#panel-title")).to_have_text("Russian")
        assert page.locator("path.outline-highlight").count() == 3


def test_search_zoom_pan_and_reset(browser):
    with Site(browser) as s:
        page = s.plan()
        page.locator("#country-search").fill("jap")
        assert page.locator(".country-row").all_inner_texts()[0].startswith("Japan")
        page.locator("#country-search").press("Enter")
        expect(page.locator("#panel-title")).to_have_text("Japan")
        wait_zoom(page, "k > 2")
        page.get_by_role("button", name="World").click()
        wait_zoom(page, "k === 1")
        page.get_by_role("button", name="Zoom in").click()
        wait_zoom(page, "Math.abs(k - 1.6) < 0.01")
        page.get_by_role("button", name="Zoom out").click()
        wait_zoom(page, "k === 1")
        canvas = page.locator("#map-canvas")
        canvas.focus()
        page.keyboard.press("+")
        wait_zoom(page, "k > 1.5")
        before = page.locator(".map-zoom").get_attribute("transform")
        page.keyboard.press("ArrowLeft")  # pan
        page.wait_for_function("(t) => document.querySelector('.map-zoom').getAttribute('transform') !== t", arg=before)
        page.keyboard.press("0")
        wait_zoom(page, "k === 1")
        # the country list is a keyboard path to every value
        page.get_by_role("button", name="← All countries").click()
        page.locator("#country-search").fill("")
        page.locator("#country-search").press("ArrowDown")
        expect(page.locator(".country-row").first).to_be_focused()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        expect(page.locator("#panel-title")).to_be_focused()


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
OSM = re.compile(r"^https://tile\.openstreetmap\.org/(\d+)/\d+/\d+\.png$")


def test_zooming_onto_a_country_opens_its_street_map(browser):
    with Site(browser) as s:
        page = s.plan()
        page.emulate_media(reduced_motion="reduce")  # zoom steps land at once
        canvas, streets, search = page.locator("#map-canvas"), page.locator(".map-streets"), page.locator("#country-search")
        # tiles blocked (offline): the outline and a note still show
        search.fill("bra")
        search.press("Enter")
        expect(canvas).to_have_attribute("data-streets", "BR")
        expect(streets).to_have_attribute("data-tiles", "failed")
        expect_text(streets, "The street map could not load")
        assert page.locator(".streets-tiles img").evaluate_all(
            "els => els.length > 0 && els.every(i => getComputedStyle(i).visibility === 'hidden')")  # no broken icons
        assert page.locator(".streets-outline").get_attribute("d").startswith("M")
        page.get_by_role("button", name="World").click()
        expect(streets).to_be_hidden()
        assert canvas.get_attribute("data-streets") is None
        # tiles served: OpenStreetMap's street map of the country, credited; the requests carry the site's origin
        tiles, referers = [], set()
        s.context.route(OSM, lambda r: (tiles.append(int(OSM.match(r.request.url).group(1))),
                                        referers.add(r.request.headers.get("referer")),
                                        r.fulfill(body=PNG, content_type="image/png")))
        page.get_by_role("button", name="← All countries").click()
        search.fill("jap")
        search.press("Enter")
        expect(canvas).to_have_attribute("data-streets", "JP")
        expect(streets).to_have_attribute("data-tiles", "ok")
        expect_text(streets, "Street map for context: Babel's figures are for the whole country.")
        expect_text(streets.locator(".streets-credit"), "© OpenStreetMap contributors")
        assert referers == {s.url.rstrip("/") + "/"}
        fit_z = max(tiles)
        for _ in range(4):  # zoom in toward street level
            page.get_by_role("button", name="Zoom in").click()
        page.wait_for_function(f"() => [...document.querySelectorAll('.streets-tiles img')].some(i => i.src.includes('/{fit_z + 3}/'))")
        expect(streets).to_have_class(re.compile(r"(^| )is-close( |$)"))  # the coarse outline gives way to the tiles' borders
        page.locator("#theme-toggle").click()  # the dark theme shows the tiles grey and inverted
        page.wait_for_function("() => getComputedStyle(document.querySelector('.streets-tiles img')).filter.includes('invert(1)')")
        page.locator("#theme-toggle").click()
        # zooming out past the country's whole view goes back to the world map, still on Japan
        for _ in range(12):
            if not streets.is_visible():
                break
            page.get_by_role("button", name="Zoom out").click()
        expect(streets).to_be_hidden()
        expect(page.locator("#panel-title")).to_have_text("Japan")
        assert page.locator("path.outline-selected").count() == 1 and zoom(page) > 1
        # zooming in past the world map's limit opens the street map again
        for _ in range(12):
            if streets.is_visible():
                break
            page.get_by_role("button", name="Zoom in").click()
        expect(canvas).to_have_attribute("data-streets", "JP")
        page.get_by_role("button", name="World").click()
        expect(streets).to_be_hidden()
        wait_zoom(page, "k === 1")
        assert s.errors == []


def test_wheel_zooming_onto_a_clicked_country_opens_its_street_map(browser):
    """A country clicked on the map, then one continuous scroll over it: once it fills the view, its street map opens."""
    with Site(browser) as s:
        page = s.plan()
        click_country(page, "RU")
        expect(page.locator("#panel-title")).to_have_text("Russia")
        page.mouse.move(*point_in(page, "RU"))
        for _ in range(3):  # no pause between notches: one gesture
            page.mouse.wheel(0, -120)
            page.wait_for_timeout(40)
            if page.locator("#map-canvas").get_attribute("data-streets"):
                break
        expect(page.locator("#map-canvas")).to_have_attribute("data-streets", "RU")
        assert s.errors == []


def test_metrics_legend_and_lookalike_views(browser):
    with Site(browser) as s:
        page = s.plan()
        choose_metric(page, "affinity")
        expect_text(page.locator(".legend-title"), "Fan interest")
        assert fill(page, "UY") == SEQ_BIN3  # 0.65: raw affinity exists even without a reference
        page.locator(".legend-item").nth(3).click()  # 0.6 to 0.8: picks out its countries
        expect(page.locator(".legend-item").nth(3)).to_have_attribute("aria-pressed", "true")
        assert page.locator("path.outline-highlight").count() >= 3 and page.locator("path.is-dim").count() > 100
        page.locator("#lookalike-select").select_option(label="Beta Town")
        assert fill(page, "KZ") == HATCH and fill(page, "BY") == SEQ_BIN3  # Beta Town: KZ none, BY 0.6
        choose_metric(page, "plan")
        expect(page.locator("#lookalike-select")).to_be_disabled()  # languages, not one game
        assert fill(page, "RU") == PLAN_TRANSLATE and fill(page, "US") == "#eceeed"  # US: no target language
        expect_text(page.locator("#map-legend"), "Translate the game")
        choose_metric(page, "demand")
        expect_text(page.locator(".legend-title"), "Babel estimate")
        assert fill(page, "MX") == fill(page, "ES")  # one value per language, drawn on all its countries


def test_default_maps_are_shown_as_not_used(browser):
    with Site(browser) as s:
        page = s.plan()
        page.locator("#lookalike-select").select_option(label="Ghost Game (no real Qloo data)")
        expect_text(page.locator("#map-overlay"), "no real fan data for this game (it returned its default map)")
        assert fill(page, "RU") == HATCH and fill(page, "US") == HATCH
        evidence = page.locator("#evidence-grid")
        expect_text(evidence, "Not used: Qloo has no real data")
        expect_text(evidence, "Not used: Qloo doesn't know it")


def test_no_fan_maps_show_a_no_data_state(browser):
    with Site(browser, agent=FakeAgent(no_data=True)) as s:
        page = s.plan()
        expect(metric(page, "plan")).to_be_checked()  # the language views still work
        assert page.locator("#map-overlay").is_hidden()
        expect_text(page.locator("#plan-chips"), "Qloo has no real fan data")
        choose_metric(page, "affinity")
        expect_text(page.locator("#map-overlay"), "no real fan data for any of the games like yours")
        expect_text(page.locator("#map-panel"), "no score")


def test_a_map_that_fails_to_load_keeps_the_list_and_retries(browser):
    with Site(browser) as s:
        s.context.route("**/static/world.json", lambda route: route.abort())
        page = s.plan(map_ready=False)
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "failed")
        expect_text(page.locator("#map-overlay"), "The map could not load")
        assert page.locator(".country-row").count() == 15 and "Russia" in page.locator("#map-panel").inner_text()
        page.get_by_role("button", name=re.compile("Show all")).click()
        assert page.locator(".country-row").count() > 15
        s.context.unroute("**/static/world.json")
        page.get_by_role("button", name="Try again").click()
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready")


# ---------------------------------------------------------------- the Plan screen: plan, budget, why
def test_changing_the_budget_refits_the_plan_on_the_server(browser):
    with Site(browser) as s:
        page = s.plan()
        first = synthetic.result()["plan"]
        a = first["allocation"]
        expected = P.fit_budget(a["shares"], a["cost_full"], a["cost_store_page"], 3600, a["min_share"],
                                a["supported"])
        page.locator("#plan-budget").fill("3600")
        expect(page.locator("#plan-title")).to_have_text(f"Translate {LABEL[expected['groups']['translate_game'][0]]}.")
        groups = {g: group_names(page, g) for g in ("translate_game", "store_page_only", "skip")}
        assert groups == {g: [LABEL[c] for c in expected["groups"][g]] for g in groups}
        expect_text(page.locator("#plan-chips"), "Budget changed from $10,000")
        expect_text(page.locator("#evidence-grid"), "Written for the $10,000 plan")
        choose_metric(page, "plan")  # the map follows the new plan
        assert fill(page, "ES") == "#eb6834"  # Spanish: now a store page
        page.locator("#plan-budget-range").focus()
        page.keyboard.press("End")  # the slider's maximum: every full translation over the threshold fits
        expect(page.locator("section[aria-labelledby='pg-skip'] .lang-name")).to_have_text([LABEL["thai"]])
        page.get_by_role("button", name="Back to $10,000").click()
        expect_text(page.locator("#plan-sub"), "of your $10,000 budget")
        assert group_names(page, "translate_game") == [LABEL[c] for c in first["groups"]["translate_game"]]
        assert s.errors == []


def test_why_this_recommendation_shows_every_value_and_step(browser):
    with Site(browser) as s:
        page = s.plan()
        r = synthetic.result()
        ru = r["explore"]["map"]["languages"]["russian"]
        why = page.get_by_role("button", name="Why this recommendation for Russian?")
        why.click()
        dialog = page.locator("#why-dialog")
        expect_text(dialog, f"The usual share: {ru['baseline_share'] * 100:.1f}%")
        expect_text(dialog, "Qloo adjustment: ")
        expect_text(dialog, f"= ×{ru['lift']:.3f}")  # the exact lift, one click away
        expect_text(dialog, f"Mean S1 {ru['mean_s1']:.3f} ÷ reference {ru['reference_s1']:.3f}")
        expect_text(dialog.locator("tbody"), "0.800")  # Alpha Farm's affinity in Russia, from the map data
        expect_text(dialog, f"= {ru['baseline_x_lift']:.5f}; ÷ {r['explore']['map']['baseline_x_lift_sum']:.5f}")
        expect_text(dialog, "(30,000 game words + 500 store-page words) × $0.10 per word = $3,050.00")
        expect_text(dialog, "= $3,507.50")
        expect_text(dialog, "Budget decision: Translate the game")
        expect_text(dialog, r["explore"]["map"]["lookalikes"][0]["request"])  # the cached Qloo response behind it
        expect_text(dialog, "Russian has the highest estimated share")  # Claude's point citing lang:russian
        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        expect(why).to_be_focused()
        page.locator('.evidence-id[data-id="lang:russian"]', has_text="Russian").click()
        expect_text(dialog, "estimated share")
        expect_text(dialog.locator("#why-title"), "Evidence: Russian")
        expect_text(dialog, "(ID lang:russian)")


def test_babel_vs_the_generic_list(browser):
    with Site(browser) as s:
        page = s.plan()
        rows = page.locator("#versus-table tbody tr")
        expect(rows).to_have_count(14)
        expect_text(rows.first, "Russian")
        expect_text(rows.first, "▲ 4")
        expect_text(rows.first, "(5th on the usual list)")
        expect_text(page.locator("#versus-about"),
                    "The usual list starts with Simplified Chinese, Japanese and Korean")


def test_map_data_transforms_in_the_browser(browser):
    """mapdata.js: pure functions over the server's map data (selection, bins, statuses, legends, lists, labels)."""
    with Site(browser) as s:
        r = synthetic.result()
        out = s.page.evaluate("""async (r) => {
          const m = await import('/static/mapdata.js');
          const model = m.model(r.explore.map, r.plan, r.plan.groups);
          return {
            bins: [m.binIndex(0.1, [0.2, 0.4]), m.binIndex(0.2, [0.2, 0.4]), m.binIndex(0.9, [0.2, 0.4])],
            ru: m.countryValue(model, 'relative', 'RU'), uy: m.countryValue(model, 'relative', 'UY'),
            au: m.countryValue(model, 'affinity', 'AU'), us: m.countryValue(model, 'plan', 'US'),
            ghost: m.countryValue(model, 'affinity', 'RU', '31'), beta: m.countryValue(model, 'affinity', 'BY', '12'),
            mx: m.countryValue(model, 'demand', 'MX'), ruFill: m.fillFor(model, 'plan', 'RU'),
            legend: m.legendItems('relative').map((i) => i.key), planLegend: m.legendItems('plan').map((i) => i.label),
            list: m.countryList(model, 'affinity', 'all', (cc) => cc).map((x) => [x.cc, x.status]),
            conf: m.confidence(r.plan.languages[0], 3), mixed: m.confidence({lookalikes_with_data: 2,
              lift_range: [0.8, 1.2]}, 3), none: m.confidence({lookalikes_with_data: 0, lift_range: null}, 3),
            head: m.headline(r.plan.status, r.plan.groups, r.plan.costs),
            nothing: m.headline('nothing_affordable', {translate_game: [], store_page_only: []}, {total: 0, budget: 0}),
            spanish: m.languageCountries(model, 'spanish'),
            // plain words, computed from the server's ratios (x1.16 -> "16% more")
            words: [m.relativeText(1.16), m.relativeText(0.7), m.relativeText(0.95), m.relativeShort(7.77),
              m.formatValue('relative', 1.16), m.signedPct(0.7)],
            adj: [m.qlooAdjustment(1.159).short, m.qlooAdjustment(0.993).short, m.qlooAdjustment(0.91).short,
              m.qlooAdjustment(1, false).short, m.qlooAdjustment(1.159).exact],
            relLegend: m.legendItems('relative').map((i) => [i.label, i.detail ?? null]),
          };
        }""", json.loads(json.dumps(r)))
        assert out["bins"] == [0, 1, 2]
        assert out["ru"] == {"status": "value", "value": 1.5, "bin": 4, "n": 3, "affinity": .75}
        assert out["uy"]["status"] == "no_reference" and out["uy"]["affinity"] == .65
        assert out["au"]["status"] == "no_score" and out["us"]["status"] == "not_counted"
        assert out["ghost"]["status"] == "unused_map" and "no real fan data" in out["ghost"]["reason"]
        assert out["beta"] == {"status": "value", "value": .6, "bin": 3, "n": 1, "affinity": .6}
        assert out["mx"]["value"] == r["explore"]["map"]["languages"]["spanish"]["estimated_share"]
        assert out["ruFill"] == {"fill": PLAN_TRANSLATE, "key": "b0"}
        assert out["legend"] == ["b0", "b1", "b2", "b3", "b4", "none"]
        assert out["planLegend"] == ["Translate the game", "Translate the store page only", "Skip for now",
                                     "Already in your game", "Not counted for any of the 14 languages"]
        values = [cc for cc, st in out["list"] if st == "value"]
        assert values[:2] == ["RU", "MX"] and out["list"][-1][1] in ("no_score", "not_counted")
        assert len(values) == r["explore"]["map"]["countries_with_score"]
        assert out["conf"]["level"] == "agree" and out["mixed"]["level"] == "mixed" and out["none"]["level"] == "none"
        assert out["head"]["title"] == "Translate Russian and Spanish." and "store pages" in out["head"]["sub"]
        assert out["nothing"]["title"] == "Nothing fits this budget yet."
        assert out["spanish"]["model"] == COUNTRIES["spanish"] and "UY" in out["spanish"]["officialOnly"]
        assert out["words"] == ["16% more fans than usual", "30% fewer fans than usual", "about the same as usual (−5%)",
                                "7.8× usual", "+16%", "−30%"]
        assert out["adj"] == ["+16%", "about average", "−9%", "no data", "×1.16"]
        assert out["relLegend"][0] == ["Far fewer (over 33% fewer)", "Under ×0.67"]  # plain label, exact range as detail
        assert out["relLegend"][4] == ["Far more (over 50% more)", "×1.5 and up"] and out["relLegend"][2][0] == "About the same"
        assert out["mixed"]["text"] == "Games like yours disagree (20% fewer to 20% more fans)"
        assert out["mixed"]["range"] == "×0.80 to ×1.20"


def test_no_country_shape_is_drawn_inside_out(browser):
    with Site(browser) as s:
        s.plan()
        inside_out = s.page.evaluate("""async () => {
          const world = await (await fetch('/static/world.json')).json();
          return world.features.filter((f) => d3.geoArea(f) > 1).map((f) => f.id);
        }""")
        assert inside_out == []  # every country is smaller than a steradian; a reversed ring would be the whole globe


def test_phone_layout_has_no_sideways_scrolling(browser):
    with Site(browser, viewport=(390, 844)) as s:
        page = s.page
        no_overflow = "document.documentElement.scrollWidth <= window.innerWidth"
        assert page.evaluate(no_overflow)
        s.find()
        assert page.evaluate(no_overflow)
        s.page.get_by_role("button", name="Run the plan").click()
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready")
        assert page.evaluate(no_overflow) and s.errors == []
        svg, controls = page.locator(".map-svg").bounding_box(), page.locator(".map-controls").bounding_box()
        assert controls["y"] >= svg["y"] + svg["height"] - 1  # zoom buttons sit under the map, not on it
        click_country(page, "BR")
        expect(page.locator("#panel-title")).to_have_text("Brazil")
        assert page.evaluate(no_overflow)


# ---------------------------------------------------------------- the Plan screen: dark theme
LIGHT_SEQ = ["#86b6ef", "#5598e7", "#2a78d6", "#184f95", "#0d366b"]
LIGHT_DIV = ["#b3302c", "#ec9890", "#dcdfdd", "#86b6ef", "#1c5cab"]
LIGHT_HATCH = ("#f4f6f6", "#aab4b8")
PLAN_ORDER = ["translate_game", "store_page_only", "skip", "already_supported"]


def test_map_palettes_per_theme(browser):
    """mapdata.js: light is the default (the report's palette); dark has its own steps; legend keys do not change."""
    with Site(browser) as s:
        r = synthetic.result()
        out = s.page.evaluate("""async (r) => {
          const m = await import('/static/mapdata.js');
          const model = m.model(r.explore.map, r.plan, r.plan.groups);
          const colors = (metric, theme) => m.legendItems(metric, theme).map((i) => i.color ?? null);
          const keys = (metric, theme) => m.legendItems(metric, theme).map((i) => i.key);
          return {
            light: ['relative', 'affinity', 'plan'].map((k) => colors(k)),
            dark: ['relative', 'affinity', 'plan'].map((k) => colors(k, 'dark')),
            sameKeys: ['relative', 'demand', 'plan'].every((k) => keys(k).join() === keys(k, 'dark').join()),
            ru: m.fillFor(model, 'plan', 'RU'), ruDark: m.fillFor(model, 'plan', 'RU', 'all', 'dark'),
            usDark: m.fillFor(model, 'plan', 'US', 'all', 'dark'), auDark: m.fillFor(model, 'affinity', 'AU', 'all', 'dark'),
            fallback: m.palette('sepia') === m.palette('light') && m.palette() === m.palette('light'),
          };
        }""", json.loads(json.dumps(r)))
        assert out["light"] == [LIGHT_DIV + [None], LIGHT_SEQ + [None],
                                [PLAN_TRANSLATE, "#eb6834", "#cfd4d2", "#1baf7a", "#eceeed"]]
        assert out["dark"] == [DARK_DIV + [None], DARK_SEQ + [None], [DARK_PLAN[g] for g in PLAN_ORDER] + [DARK_NOT_COUNTED]]
        assert out["sameKeys"] and out["fallback"]
        assert out["ru"] == {"fill": PLAN_TRANSLATE, "key": "b0"}
        assert out["ruDark"] == {"fill": DARK_PLAN["translate_game"], "key": "b0"}
        assert out["usDark"] == {"fill": DARK_NOT_COUNTED, "key": "other"}
        assert out["auDark"] == {"fill": HATCH, "key": "none"}


def test_the_dark_theme_paints_the_map_legend_and_lists_with_the_dark_palettes(browser):
    with Site(browser, color_scheme="dark") as s:
        page = s.plan()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert fill(page, "RU") == DARK_DIV[4] and fill(page, "BR") == DARK_DIV[3]  # x1.5 and x1.1, as in light
        assert fill(page, "UY") == HATCH and hatch_ink(page) == DARK_HATCH
        assert legend_colors(page) == [rgb(c) for c in DARK_DIV] + [None]
        hatch = page.locator("#map-legend .swatch-hatch").evaluate("e => getComputedStyle(e).backgroundImage")
        assert all(rgb(c) in hatch for c in DARK_HATCH)  # the legend's hatch is the map's
        row = page.locator('.country-row[data-cc="RU"] .swatch')
        assert row.evaluate("e => getComputedStyle(e).backgroundColor") == rgb(DARK_DIV[4])
        choose_metric(page, "plan")
        assert fill(page, "RU") == DARK_PLAN["translate_game"] and fill(page, "US") == DARK_NOT_COUNTED
        assert legend_colors(page) == [rgb(DARK_PLAN[g]) for g in PLAN_ORDER] + [rgb(DARK_NOT_COUNTED)]
        dots = page.locator(".lang-chip, .plan-group-head h3").evaluate_all(
            "els => els.map(e => [(e.closest('.plan-group') || e).className, getComputedStyle(e, '::before').backgroundColor])")
        assert len(dots) > 6
        for cls, color in dots:  # the plan's group dots are the map's plan colours
            assert color == rgb(DARK_PLAN[re.search(r"group-(\w+)", cls)[1]])
        choose_metric(page, "affinity")
        assert fill(page, "UY") == DARK_SEQ[3]
        page.evaluate("dispatchEvent(new Event('beforeprint'))")  # a printed page is light
        assert fill(page, "UY") == SEQ_BIN3 and hatch_ink(page) == LIGHT_HATCH
        page.evaluate("dispatchEvent(new Event('afterprint'))")
        assert fill(page, "UY") == DARK_SEQ[3] and hatch_ink(page) == DARK_HATCH
        assert s.errors == []


def test_switching_the_theme_repaints_the_open_plan_and_keeps_the_view(browser):
    with Site(browser) as s:
        page = s.plan()
        choose_metric(page, "affinity")
        assert fill(page, "UY") == SEQ_BIN3
        click_country(page, "BR")
        expect(page.locator("#panel-title")).to_have_text("Brazil")
        page.get_by_role("button", name="Zoom in").click()
        wait_zoom(page, "Math.abs(k - 1.6) < 0.01")
        page.evaluate("window.notReloaded = true")
        page.locator("#theme-toggle").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert fill(page, "UY") == DARK_SEQ[3] and hatch_ink(page) == DARK_HATCH
        assert legend_colors(page) == [rgb(c) for c in DARK_SEQ] + [None]
        expect(metric(page, "affinity")).to_be_checked()  # same view, selection and zoom; no reload
        expect(page.locator("#panel-title")).to_have_text("Brazil")
        assert page.locator("path.outline-selected").count() == 1 and abs(zoom(page) - 1.6) < 0.01
        assert page.evaluate("window.notReloaded") is True
        page.locator("#theme-toggle").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        assert fill(page, "UY") == SEQ_BIN3 and hatch_ink(page) == LIGHT_HATCH
        assert legend_colors(page) == [rgb(c) for c in LIGHT_SEQ] + [None]
        assert s.errors == []


def test_the_report_keeps_a_light_map_in_the_dark_theme(browser):
    with Site(browser, color_scheme="dark") as s:
        page = s.plan()
        page.get_by_role("button", name="Export report").click()
        expect(page.locator("#view-report")).to_be_visible()
        report = page.locator("#view-report")
        assert report.locator('path.country[data-cc="RU"]').get_attribute("fill") == DIV_STRONG_BLUE
        assert report.locator('path.country[data-cc="UY"]').get_attribute("fill") == "url(#report-map-hatch)"
        assert hatch_ink(page, "#report-map-hatch") == LIGHT_HATCH
        live = page.locator('#map-svg-host path.country[data-cc="RU"]')
        assert live.get_attribute("fill") == DARK_DIV[4] and hatch_ink(page) == DARK_HATCH  # the live map is untouched
        assert s.errors == []


# ---------------------------------------------------------------- the real pipeline, browser to backend
@pytest.mark.skipif(not any((P.ROOT / "cache" / "qloo").glob("heatmap_*")), reason="needs the local API cache")
def test_browser_to_the_real_backend(browser, monkeypatch):
    """The real app (real look-alike lookup, real agent, real cache); any network call from the server fails it."""
    import anthropic

    def refuse(*args, **kwargs):
        raise AssertionError("network call during an offline test")
    monkeypatch.setattr(net, "request", refuse)
    monkeypatch.setattr(anthropic, "Anthropic", refuse)
    app = api.create_app(api.Settings(warmup=True))
    with serve(app) as url:
        assert app.state.babel.ready.wait(180), app.state.babel.data_status
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        context.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda route: route.abort())
        page = context.new_page()
        page.goto(url)
        page.get_by_role("button", name="WEBFISHING").click()
        page.locator(".card").first.wait_for(timeout=30_000)
        assert page.locator(".card .card-title").all_inner_texts() == [
            "Temtem · 2022", "A Hat in Time · 2017", "Unpacking · 2021"]
        page.get_by_role("button", name="Run the plan").click()
        expect(page.locator("#view-plan")).to_be_visible(timeout=60_000)
        expect(page.locator("#plan-title")).to_have_text("Translate Russian and Spanish.")
        expect_text(page.locator("#plan-sub"), "$7,996")
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready")
        assert fill(page, "JP") == DIV_STRONG_BLUE  # fans of these games: Japan far above typical games
        assert page.locator("path.country").evaluate_all(
            "els => els.filter(e => e.getAttribute('fill') !== 'url(#map-hatch)').length") > 80
        page.locator("#country-search").fill("Japan")
        page.locator("#country-search").press("Enter")
        expect_text(page.locator("#map-panel"), "A Hat in Time")
        page.get_by_role("button", name="Why this recommendation for Russian?").click()
        expect_text(page.locator("#why-dialog"), "Kazakhstan")
        page.keyboard.press("Escape")
        page.locator("#plan-budget").fill("20000")
        expect(page.locator("#plan-chips")).to_contain_text("Budget changed")
        states = dict(page.locator(".step").evaluate_all("els => els.map(e => [e.dataset.step, e.dataset.state])"))
        assert states["verify"] == "done" and states["explain"] == "done"
        context.close()
