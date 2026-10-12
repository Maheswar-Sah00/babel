"""The Plan screen's "plan at a glance" charts (static/charts.js), in a real browser (Playwright + Chromium) on the
real app with test_web.py's fakes: every number in a chart is the plan's own number, the charts follow the budget,
and a language opens on the map. Needs: python -m playwright install chromium
"""
import re

import pytest

from test_web import Site, browser, expect_text  # noqa: F401  (browser: the fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect


def money(text):
    return int(re.sub(r"[^\d]", "", text))


def test_the_charts_show_the_plans_own_numbers(browser):
    with Site(browser) as s:
        page = s.plan()
        page.locator("section.glance").scroll_into_view_if_needed()
        assert page.locator("#plan-charts svg").count() == 4
        # share chart: every language (those already in the game too), high to low, each value the same as on the
        # plan's language cards
        rows = page.locator("#chart-share-plot g.row")
        cards = page.locator("#plan-groups li.lang-row")
        assert rows.count() == page.locator("#chart-lift-plot g.row").count() >= cards.count() > 0
        shown = dict(zip(rows.evaluate_all("els => els.map(e => e.dataset.lang)"),
                         rows.locator("text.value").evaluate_all("els => els.map(e => e.textContent)")))  # SVG text: no innerText
        for code, share in zip(cards.evaluate_all("els => els.map(e => e.dataset.lang)"),
                               cards.locator(".lang-share").all_inner_texts()):
            assert shown[code] == share
        values = [float(t.rstrip("%")) for t in shown.values()]
        assert values == sorted(values, reverse=True)
        # the slope chart has every language of the "Babel vs the usual list" table
        assert page.locator("#chart-slope-plot g.row").count() == page.locator("#versus-table tbody tr").count()
        # budget: the breakdown adds up to the budget, and the planned part to the estimated cost
        amounts = [money(t) for t in page.locator(".chart-breakdown dd").all_inner_texts()]
        labels = page.locator(".chart-breakdown dt").all_inner_texts()
        budget = money(page.locator("#plan-budget").input_value())
        assert sum(amounts) == pytest.approx(budget, abs=len(amounts))
        planned = sum(a for a, label in zip(amounts, labels) if label != "Left over")
        cost = money(page.locator("#budget-stats dd").first.inner_text())
        assert planned == pytest.approx(cost, abs=len(amounts))
        # hover gives the numbers; a click shows the language on the map
        rows.first.hover()
        expect(page.locator("#chart-share-plot").locator("xpath=..").locator(".chart-tooltip")).to_be_visible()
        first = rows.first.get_attribute("data-lang")
        name = page.locator(f'#plan-groups li.lang-row[data-lang="{first}"] .lang-name').inner_text()
        rows.first.click()
        expect(page.locator("#panel-title")).to_have_text(name)
        assert s.errors == []


def test_the_charts_follow_the_budget(browser):
    with Site(browser) as s:
        page = s.plan()
        before = page.locator(".chart-breakdown").inner_text()
        page.locator("#plan-budget").fill("0")
        expect(page.locator(".chart-breakdown")).not_to_have_text(before)
        expect_text(page.locator(".chart-breakdown"), "Left over")
        assert s.errors == []
