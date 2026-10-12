"""Browser tests of the one-page report (web/static/report.js): real Chromium against the real app.

The plan comes from the fake agent of test_web.py: a real plan built by the engine from synthetic Qloo fan maps
(tests/synthetic.py). The report is opened from the Plan screen ("Export report"); printing is checked with print
media emulation and a real A4 PDF from Chromium. The last test runs the WEBFISHING demo through the real backend
from the local cache, with the network refused. Needs: python -m playwright install chromium
"""
import re
from decimal import ROUND_HALF_UP, Decimal

import pytest

import synthetic
from babel import api, net
from babel import plan as P
from babel.languages import LABEL
from live_server import serve
from test_track_web import LOW_CONTRAST, luminance
from test_web import FakeAgent, Site, browser, expect, expect_text, wait_zoom  # noqa: F401

GROUPS = ["translate_game", "store_page_only", "skip"]
QLOO_NOTE = "Qloo describes the combined taste of many fans, never individual players, and it doesn't guarantee sales."
ESTIMATE_NOTE = "Costs and shares are estimates, not quotes or sales."
# babel/plan.py CAVEATS the report words plainly (the small-indie result is said by its track record line)
PLAIN_CAVEATS = {"Shares are estimates": "not sales, wishlists or player counts",
                 "The baseline comes from": "miss players who only buy translated games",
                 "Costs are estimates": "Costs are estimates from per-word rates you can edit, not quotes."}
MAPDATA = "async ([name, ...args]) => { const m = await import('/static/mapdata.js'); return m[name](...args); }"
HATCH, DIV_STRONG_BLUE, NOT_COUNTED = "url(#report-map-hatch)", "#1c5cab", "#eceeed"
NO_OVERFLOW = "document.documentElement.scrollWidth <= window.innerWidth"


def usd(x):
    """As the browser formats it (Intl, whole dollars, half away from zero)."""
    return f"${Decimal(str(x)).quantize(Decimal(1), ROUND_HALF_UP):,}"


def pct(x):
    return f"{x * 100:.1f}%"


def pdf_pages(pdf):
    """Page objects in a PDF (not the /Pages tree nodes)."""
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf))


def open_report(page):
    page.get_by_role("button", name="Export report").click()
    expect(page.locator("#view-report")).to_be_visible()
    return page.locator("#view-report")


def group_names(report, group):
    return report.locator(f'tbody[data-group="{group}"] th.r-lang').all_inner_texts()


def test_the_report_has_the_inputs_the_plan_the_evidence_and_the_limits(browser):
    with Site(browser) as s:
        page = s.plan()
        plan_id = re.search(r"babel-plan-(\w+)\.json", page.locator("#plan-download").get_attribute("download"))[1]
        report = open_report(page)
        expect(page.locator("#report-title")).to_be_focused()
        expect(page.locator("#report-title")).to_have_text("Test Game")
        r = synthetic.result()
        p = r["plan"]
        expect(report.locator(".r-headline")).to_have_text("Translate Russian and Spanish.")
        meta = report.locator(".r-meta")
        for text in (plan_id, "42", "3 games like yours with Qloo fan data"):
            expect_text(meta, text)
        inputs = report.locator(".r-inputs")
        for text in ("30,000", usd(10_000), usd(p["costs"]["total"]), usd(p["costs"]["unspent"]),
                     pct(p["estimated_coverage"]["translate_game"]), pct(p["estimated_coverage"]["store_page_only"])):
            expect_text(inputs, text)
        assert report.locator(".r-inputs .is-changed").count() == 0

        # the three groups, with each language's estimated share, Qloo lift and cost, and the group totals
        for group in GROUPS:
            assert group_names(report, group) == [LABEL[c] for c in p["groups"][group]]
        for group in ("translate_game", "store_page_only"):
            expect_text(report.locator(f'tbody[data-group="{group}"] .r-group-sum'), usd(p["costs"][group]))
        for x in p["languages"]:
            if x["group"] == "already_supported":
                assert report.locator(f'tr[data-lang="{x["code"]}"]').count() == 0
                continue
            row = report.locator(f'tr[data-lang="{x["code"]}"]')
            expect_text(row, pct(x["estimated_share"]))
            # the Qloo adjustment in the Plan screen's own words ("+16%"), the exact multiplier for screen readers
            adj = page.evaluate(MAPDATA, ["qlooAdjustment", x["qloo_lift"], x["lookalikes_with_data"] > 0])
            expect(row.locator(".r-lift strong")).to_have_text(adj["short"])
            expect_text(row.locator(".r-lift"), f"Exact: ×{x['qloo_lift']:.2f}")
            cost = x["cost_store_page"] if x["group"] == "store_page_only" else x["cost_full"]
            expect_text(row.locator(".r-cost"), usd(cost))
        expect_text(report.locator(".r-versus"), "Already in your game: German.")
        # why, in plain words from the plan's numbers; the server's own wording is the tooltip
        versus = {v["code"]: v for v in r["explore"]["versus_generic"]["rows"]}
        ru = versus["russian"]
        russian = report.locator('tr[data-lang="russian"] .r-why')
        expect_text(russian, f"The usual share: {pct(ru['baseline_share'])}, 1st (5th on the usual list).")
        assert (ru["baseline_rank"], ru["generic_rank"], ru["babel_rank"]) == (1, 5, 1)
        expect_text(russian, "so it stays 1st.")
        expect(russian).to_have_attribute("title", ru["why"])
        expect_text(report.locator('tr[data-lang="french"] .r-why'), "didn't fit; the store page tests this market")
        thai = report.locator('tr[data-lang="thai"] .r-why')
        assert p["languages"][-1]["estimated_share"] < p["allocation"]["min_share"]
        expect(thai).to_have_text(f"Too few likely players: under {pct(p['allocation']['min_share'])}.")
        expect(thai).to_have_attribute("title", p["languages"][-1]["reason"])

        # evidence: comparable games with their Qloo status, the explanation (labelled), market notes
        looks = report.locator(".r-looks")
        expect(looks.locator(".badge", has_text="Used: real Qloo fan data")).to_have_count(3)
        expect_text(looks.locator("li", has_text="Ghost Game"), "Not used: Qloo has no real data")
        expect_text(looks.locator("li", has_text="Lost Game"), "Not used: Qloo doesn't know it")
        explain = report.locator(".r-explain")
        expect_text(explain.locator(".src"), "Claude")
        expect_text(explain, r["explanation"]["summary"])
        markets = report.locator(".r-markets")
        expect_text(markets, "Russian → Russia")
        expect_text(markets, "Film Alpha · Film Beta")
        expect_text(markets.locator(".r-llm"), r["market_notes"]["markets"][0]["note"]["text"])
        expect_text(markets.locator(".r-audience"), "24 and younger +0.31")

        # limits, the permanent Qloo note, provenance
        limits = report.locator(".r-limits")
        for caveat in p["uncertainty"]["caveats"]:  # each one, in plain words or (if unknown) as the server sent it
            if caveat.startswith("On small English-only indie games"):
                continue  # a note about the test, not this plan: the Track record has it
            plain = next((v for k, v in PLAIN_CAVEATS.items() if caveat.startswith(k)), caveat)
            expect_text(limits, plain)
        expect(limits).not_to_contain_text("rule out luck")
        steam = p["track_record"]["steam_reviews"]
        wiki = p["track_record"]["wikipedia_pageviews"]
        expect_text(limits, f"on {wiki['test_games']} well-known games, Babel's top 3 languages reached "
                            f"{pct(wiki['babel_top3_coverage'])} of the real non-English audience")
        expect_text(limits, f"On {steam['test_games']} small indie games, they reached "
                            f"{pct(steam['babel_top3_coverage'])} of non-English reviews")
        expect_text(limits, QLOO_NOTE)
        expect_text(limits, ESTIMATE_NOTE)
        expect_text(report.locator(".r-foot"), f"plan {plan_id}")
        expect_text(report.locator(".r-foot"), "Qloo world heatmaps (urn:heatmap) of the look-alike games")
        text = report.inner_text()
        assert not any(bad in text for bad in ("null", "undefined", "NaN"))
        assert s.errors == []


def test_the_map_is_a_static_copy_of_the_live_map(browser):
    with Site(browser) as s:
        page = s.plan()
        page.get_by_role("button", name="Spanish: show its countries").click()  # dims the rest, outlines Spanish
        page.get_by_role("button", name="Zoom in").click()
        wait_zoom(page, "Math.abs(k - 1.6) < 0.01")
        assert page.locator("#map-svg-host path.country.is-dim").count() > 100
        report = open_report(page)
        svg = report.locator("svg.r-map-svg")
        expect(svg).to_have_count(1)
        countries = svg.locator("path.country")
        assert countries.count() >= 170
        fills = countries.evaluate_all("els => els.map((e) => [e.dataset.cc, e.getAttribute('fill')])")
        painted = [cc for cc, f in fills if f not in (HATCH, NOT_COUNTED)]
        assert len(painted) >= 15 and dict(fills)["RU"] == DIV_STRONG_BLUE and dict(fills)["AU"] == HATCH
        assert svg.locator(".map-zoom").get_attribute("transform") is None  # zoom reset
        assert svg.locator(".is-dim").count() == 0 and svg.locator(".map-outlines > *").count() == 0
        assert svg.locator("pattern#report-map-hatch").count() == 1 and page.locator("#map-hatch").count() == 1
        assert svg.locator('[fill="url(#map-hatch)"]').count() == 0
        legend = report.locator(".r-legend li")
        expect(legend).to_have_count(6)
        expect_text(report.locator(".r-legend"), "Far more (over 50% more)")  # mapdata.js labels (x1.5 and up)
        expect_text(report.locator(".r-map-view"), "Fans compared with usual")
        expect_text(report.locator(".r-map"), "Highest: Russia +50%")  # x1.50, as mapdata.formatValue words it
        # the live map is untouched
        assert page.locator("#map-svg-host .map-zoom").get_attribute("transform")
        assert page.locator("#map-svg-host path.country.is-dim").count() > 100
        assert s.errors == []


def test_a_budget_moved_on_the_plan_screen_is_the_budget_of_the_report(browser):
    with Site(browser) as s:
        page = s.plan()
        a = synthetic.result()["plan"]["allocation"]
        expected = P.fit_budget(a["shares"], a["cost_full"], a["cost_store_page"], 3600, a["min_share"],
                                a["supported"])
        page.locator("#plan-budget").fill("3600")
        expect(page.locator("#plan-title")).to_have_text(f"Translate {LABEL[expected['groups']['translate_game'][0]]}.")
        report = open_report(page)
        expect(report.locator(".r-headline")).to_have_text(page.locator("#plan-title").inner_text())
        changed = report.locator(".r-inputs .is-changed")
        expect_text(changed, "Current budget")
        expect_text(changed, "$3,600")
        expect_text(report.locator(".r-inputs"), "$10,000")
        for text in (usd(expected["costs"]["total"]), usd(expected["costs"]["unspent"]),
                     pct(expected["estimated_coverage"]["translate_game"])):
            expect_text(report.locator(".r-inputs"), text)
        for group in GROUPS:
            assert group_names(report, group) == [LABEL[c] for c in expected["groups"][group]]
        expect_text(report.locator(".r-alerts"), "current budget, $3,600")
        expect_text(report.locator(".r-explain"), "Written for the $10,000 plan.")
        expect_text(report.locator(".r-markets"), "Markets were chosen for the $10,000 plan.")
        assert s.errors == []


def test_print_shows_only_the_report_on_one_a4_page(browser):
    with Site(browser) as s:
        page = s.plan()
        open_report(page)
        expect(page.locator("header.nav")).to_be_visible()
        expect(page.locator(".report-toolbar")).to_be_visible()
        page.emulate_media(media="print")
        for hidden in ("header.nav", ".footer", ".report-toolbar", "#view-plan", "#view-start", "#view-working"):
            expect(page.locator(hidden)).to_be_hidden()
        expect(page.locator(".report-sheet")).to_be_visible()
        expect(page.locator("svg.r-map-svg")).to_be_visible()
        adjust = page.locator(".r-group-row th").first.evaluate(
            "e => getComputedStyle(e).printColorAdjust || getComputedStyle(e).webkitPrintColorAdjust")
        assert adjust == "exact"  # colour chips and backgrounds print
        assert float(page.locator(".report-sheet").get_attribute("data-fit")) >= 0.9  # no visible shrinking
        assert pdf_pages(page.pdf(format="A4")) == 1
        page.emulate_media(media="screen")
        expect(page.locator(".report-toolbar")).to_be_visible()
        assert s.errors == []


# Every element of the sheet with its computed colours: the paper must look the same in both themes and in print.
PAPER = """() => [...document.querySelectorAll('.report-sheet, .report-sheet *')].map((e) => {
  const s = getComputedStyle(e);
  return [e.tagName, s.color, s.backgroundColor, s.backgroundImage, s.borderTopColor, s.borderRightColor,
    s.borderBottomColor, s.borderLeftColor, s.fill, s.stroke].join(' | ');
})"""


def test_the_dark_theme_darkens_the_surroundings_and_keeps_the_paper_light(browser):
    """The sheet is the printed page: made in either theme (in the dark one with a light copy of the map), every
    element has exactly the light colours; only the page and the toolbar around it go dark. Print stays light."""
    with Site(browser) as s:
        page = s.plan()
        open_report(page)
        light = page.evaluate(PAPER)
        assert luminance(page.locator(".report-toolbar").evaluate("e => getComputedStyle(e).backgroundColor")) > 0.9
        page.emulate_media(media="print")  # print has its own rules (no border, for one): compare like with like
        printed = page.evaluate(PAPER)
        page.emulate_media(media="screen")
        page.get_by_role("button", name="Back to the plan").click()
        page.locator("#theme-toggle").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        open_report(page)
        assert page.evaluate(PAPER) == light
        expect(page.locator("svg.r-map-svg")).to_have_count(1)
        toolbar = page.locator(".report-toolbar").evaluate("e => getComputedStyle(e).backgroundColor")
        body = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert luminance(toolbar) < 0.02 and luminance(body) < 0.02
        assert page.evaluate(LOW_CONTRAST, ".report-toolbar") == []
        page.emulate_media(media="print")
        assert page.evaluate(PAPER) == printed
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"
        assert pdf_pages(page.pdf(format="A4")) == 1
        assert s.errors == []


def test_print_button_title_and_back_to_the_plan(browser):
    with Site(browser) as s:
        page = s.plan(map_ready=False)
        open_report(page)
        page.evaluate("() => { window.print = () => { window.printed = (window.printed || 0) + 1; }; }")
        page.get_by_role("button", name="Print or save as PDF").click()
        assert page.evaluate("window.printed") == 1
        title = page.title()
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        assert page.title().startswith("Babel report - Test Game - ")  # the default "Save as PDF" file name
        page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        assert page.title() == title
        page.get_by_role("button", name="Back to the plan").click()
        expect(page.locator("#view-plan")).to_be_visible()
        expect(page.locator("#view-report")).to_be_hidden()
        expect(page.locator("#plan-export")).to_be_focused()
        assert s.errors == []


def test_a_map_that_is_not_ready_is_named_not_drawn(browser):
    with Site(browser) as s:
        s.context.route("**/static/world.json", lambda route: route.abort())
        page = s.plan(map_ready=False)
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "failed")
        report = open_report(page)
        expect_text(report.locator(".r-map"), "The world map was not ready when this report was made")
        assert report.locator("svg.r-map-svg").count() == 0
        expect(report.locator(".r-legend li")).to_have_count(6)


def test_a_plan_without_qloo_fan_maps(browser):
    with Site(browser, agent=FakeAgent(no_data=True)) as s:
        page = s.plan()
        report = open_report(page)
        expect_text(report.locator(".r-meta"), "Qloo has no real fan data for games like this: the usual share only")
        expect_text(report.locator(".r-map"), "The plan on the world map")
        expect_text(report.locator(".r-legend"), "Translate the game")
        expect_text(report.locator(".r-looks"), "Not used: Qloo has no real data")
        expect_text(report.locator(".r-limits"), "No Qloo fan data for games like this")
        expect_text(report.locator(".r-markets"), "Market notes were not requested for this plan.")
        assert s.errors == []


def test_phone_width_has_no_sideways_scrolling(browser):
    with Site(browser, viewport=(390, 844)) as s:
        page = s.plan()
        open_report(page)
        expect(page.locator("svg.r-map-svg")).to_be_visible()
        assert page.evaluate(NO_OVERFLOW)
        page.locator(".r-foot").scroll_into_view_if_needed()
        assert page.evaluate(NO_OVERFLOW)
        assert pdf_pages(page.pdf(format="A4")) == 1  # the printed page keeps the A4 layout
        assert s.errors == []


# ---------------------------------------------------------------- the real pipeline, browser to backend
@pytest.mark.skipif(not any((P.ROOT / "cache" / "qloo").glob("heatmap_*")), reason="needs the local API cache")
def test_the_webfishing_report_fits_one_page(browser, monkeypatch):
    """WEBFISHING (11 store-page languages) through the real app from the cache; any network call fails it."""
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
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.get_by_role("button", name="WEBFISHING").click()
        page.locator(".card").first.wait_for(timeout=30_000)
        page.get_by_role("button", name="Run the plan").click()
        expect(page.locator("#view-plan")).to_be_visible(timeout=60_000)
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready")
        report = open_report(page)
        expect(page.locator("#report-title")).to_have_text("WEBFISHING")
        expect(report.locator('tbody[data-group="store_page_only"] tr[data-lang]')).to_have_count(11)
        expect_text(report.locator(".r-inputs"), "$7,996")
        expect(report.locator(".r-looks li")).to_have_count(6)
        assert pdf_pages(page.pdf(format="A4")) == 1
        assert float(report.locator(".report-sheet").get_attribute("data-fit")) >= 0.9
        assert errors == []
        context.close()
