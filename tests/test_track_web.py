"""The Track record screen in a real browser (Playwright + Chromium) against the real app and the real backtest data.

The figures on screen are compared with backtest/final_report.md, parsed by tests/test_track_record.py's helpers
(never retyped). Per-game values are compared with what GET /track-record serves. Needs:
python -m playwright install chromium
"""
import json
import re
from decimal import ROUND_HALF_UP, Decimal

import pytest

from test_track_record import REPORT, primary_line, section, table
from test_web import Site, browser  # noqa: F401  (the browser fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect
TRUTHS = {"Wikipedia pageviews": "wikipedia_pageviews", "Steam reviews": "steam_reviews"}
LABEL = {"wikipedia_pageviews": "Wikipedia page views", "steam_reviews": "Steam reviews"}
BABEL, TYPICAL, GENERIC = "Babel: typical x S1 (primary)", "Typical mix (no Qloo)", "Generic tier list"
COVERAGE = "Top-3 coverage (primary)"
NO_OVERFLOW = "document.documentElement.scrollWidth <= window.innerWidth"
OPEN_ALL = "document.querySelectorAll('#view-track details').forEach((d) => { d.open = true; })"
# WCAG contrast in the browser. LOW_CONTRAST(root): every visible text under root below 4.5:1 (3:1 for large text)
# against what is behind it (the backgrounds of its ancestors, composited; opacity and images ignored). MARK_CONTRAST
# (selector): each matching element's background against what is behind its parent. Also used by test_tour.py and
# test_assistant_web.py.
CONTRAST_JS = """
  const rgba = (c) => { const m = /rgba?\\(([^)]+)\\)/.exec(c); if (!m) return null;
    const v = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const over = (top, under) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1);
  const lum = (c) => { const [r, g, b] = c.slice(0, 3).map((x) => { x /= 255;
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const behind = (el) => { const layers = [];
    for (let e = el; e; e = e.parentElement) { const c = rgba(getComputedStyle(e).backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] === 1) break; } }
    return layers.reverse().reduce((under, top) => over(top, under), [255, 255, 255, 1]); };
  const name = (el) => `${el.tagName.toLowerCase()}.${String(el.className).trim().replace(/\\s+/g, '.')}`;
"""
LOW_CONTRAST = """(root) => {""" + CONTRAST_JS + """
  const out = [];
  for (const el of document.querySelector(root).querySelectorAll('*')) {
    if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    if (!el.getClientRects().length || el.closest('.visually-hidden, svg, option')) continue;
    const s = getComputedStyle(el), fg = rgba(s.color);
    if (!fg || s.visibility !== 'visible' || Number(s.opacity) === 0) continue;
    const size = parseFloat(s.fontSize), large = size >= 24 || (Number(s.fontWeight) >= 700 && size >= 18.66);
    const bg = behind(el), r = ratio(over(fg, bg), bg);
    if (r < (large ? 3 : 4.5)) out.push(`${name(el)} "${el.textContent.trim().slice(0, 40)}" ${r.toFixed(2)}`);
  }
  return out;
}"""
MARK_CONTRAST = """(selector) => {""" + CONTRAST_JS + """
  return [...document.querySelectorAll(selector)].filter((el) => el.getClientRects().length).map((el) => {
    const mark = over(rgba(getComputedStyle(el).backgroundColor), behind(el.parentElement));
    return [name(el), ratio(mark, behind(el.parentElement)), getComputedStyle(el).backgroundColor];
  });
}"""
# Every text and every tooltip or accessible name on the Track record (inner_text misses attributes)
ALL_TEXT = """() => { const v = document.querySelector('#view-track');
  return [v.textContent, ...[...v.querySelectorAll('[title], [aria-label]')].map((e) =>
    `${e.getAttribute('title') || ''} ${e.getAttribute('aria-label') || ''}`)].join(' '); }"""


def luminance(css):
    """Relative luminance of a computed 'rgb(r, g, b)' colour (0 black, 1 white)."""
    r, g, b = (int(x) / 255 for x in re.findall(r"\d+", css)[:3])
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    """WCAG contrast ratio of two computed colours."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def fixed(x, digits):
    """JavaScript's toFixed: round half up on the double's exact value (Python's format rounds half to even)."""
    return str(Decimal(x).quantize(Decimal(1).scaleb(-digits), ROUND_HALF_UP))


def pts(report_pct):
    """'+1.18%' -> '+1.2' as the screen writes points (with a real minus sign)."""
    x = float(report_pct.rstrip("%"))
    return f"{'+' if x > 0 else ''}{fixed(x, 1)}".replace("-", "−")


def p_text(p):
    p = float(p)
    return "< 0.001" if p < 0.001 else f"= {p:.2f}"


def between(lo, hi):
    """The likely range in words, as the screen writes it: '-2.46%', '+5.00%' -> 'between 2.5 points worse and 5.0
    points better'."""
    a, b = (float(x.rstrip("%")) for x in (lo, hi))
    f = lambda x: fixed(abs(x), 1)  # noqa: E731
    if a >= 0:
        return f"between {f(a)} and {f(b)} points better"
    if b <= 0:
        return f"between {f(b)} and {f(a)} points worse"
    return f"between {f(a)} points worse and {f(b)} points better"


def coverage(name):
    """{report row name: top-3 coverage text} for one truth's section."""
    return {r["Competitor"]: r[COVERAGE] for r in table(section(name), "Competitor")}


def open_track(s):
    page = s.page
    page.get_by_role("link", name="The full track record").click()
    expect(page.locator("#view-track")).to_be_visible()
    page.locator(".tr-verdict").first.wait_for()
    return page


def choose_truth(page, key):
    page.locator("label.metric-option", has_text=LABEL[key]).click()


def served(page):
    return page.evaluate("async () => (await fetch('/track-record')).json()")


def reach(tr):
    """(Babel's top-3 coverage, the usual list's) from the served competitors."""
    cov = {c["key"]: c["top3_coverage"] for c in tr["competitors"]}
    return cov["babel"], cov["generic"]


# ---------------------------------------------------------------- the published figures
def test_babel_against_the_usual_list_equals_the_report(browser):
    with Site(browser) as s:
        page = open_track(s)
        expect(page.locator("#track-title")).to_be_focused()
        data = served(page)
        games = 0
        for name, key in TRUTHS.items():
            rows = coverage(name)
            games += int(re.search(r"Dev \d+ games, test (\d+) games", section(name))[1])
            card = page.locator(f'.tr-verdict[data-truth="{key}"]')
            expect(card.locator(".tr-card-measure")).to_have_text(LABEL[key])
            expect(card.locator(".tr-hero-value")).to_have_text(rows[BABEL])
            expect(card.locator('.tr-compare-row[data-key="babel"] .tr-compare-value')).to_have_text(rows[BABEL])
            expect(card.locator('.tr-compare-row[data-key="generic"] .tr-compare-value')).to_have_text(rows[GENERIC])
            babel, usual = reach(data["truths"][key])
            assert (f"{babel:.1%}", f"{usual:.1%}") == (rows[BABEL], rows[GENERIC])
            expect(card.locator(".tr-ratio")).to_have_text(f"{fixed(babel / usual, 1)}× the usual list")
            widths = card.locator(".tr-compare-fill").evaluate_all(
                "els => els.map((e) => e.getBoundingClientRect().width / e.parentElement.getBoundingClientRect().width)")
            assert widths == pytest.approx([babel, usual], abs=0.01)  # one honest scale, 0 to 100%
        times = sorted({round(a / b) for a, b in (reach(data["truths"][k]) for k in TRUTHS.values())})
        assert times == [3]  # Wikipedia 2.8x, Steam 3.1x: "about 3x" (the tour's wording relies on it)
        title = page.locator("#view-track .tr-summary .tr-verdict-title")  # the tour's targets
        expect(title).to_have_text("About 3× the reach of the usual list")
        expect(page.locator(".tr-summary .tr-about")).to_contain_text("Chinese, Japanese and Korean first")
        expect(page.locator("#track-sub")).to_contain_text(f"We tested Babel on {games} real games released since 2023")
        assert s.errors == []


def test_what_qloo_adds_equals_the_wikipedia_test(browser):
    with Site(browser) as s:
        page = open_track(s)
        text = section("Wikipedia pageviews")
        better, tie, worse, p, mean, *_ = primary_line(text)
        rows = coverage("Wikipedia pageviews")
        card = page.locator(".tr-qloo")
        expect(card).to_have_attribute("data-truth", "wikipedia_pageviews")
        expect(card.locator(".tr-counts li")).to_have_count(3)
        for k, n in (("better", better), ("tie", tie), ("worse", worse)):
            expect(card.locator(f'.tr-counts li[data-count="{k}"] .tr-count-value')).to_have_text(n)
        expect(card.locator(".tr-counts")).to_have_text(
            re.compile(rf"▲\s*Better\s*{better}\s*games\s*=\s*The same\s*{tie}\s*games\s*▼\s*Worse\s*{worse}\s*games"))
        expect(card.locator("#tr-qloo-title")).to_have_text(
            f"Qloo's fan maps improved Babel's picks {fixed(int(better) / int(worse), 1)} times as often as they hurt them")
        expect(card).not_to_contain_text(rows[TYPICAL])  # no "without Qloo" figure on the page's cards
        expect(card.locator(".tr-step")).to_have_count(0)
        assert p_text(p) == "< 0.001"
        expect(card.locator(".tr-facts")).to_contain_text("Very unlikely to be luck (p < 0.001)")
        verdict = re.search(r"\*\*Pre-registered verdict \(Wikipedia pageviews\): (.+?)\.\*\*", REPORT)[1]
        expect(card.locator(".tr-facts")).to_contain_text(f"Verdict under the rules fixed in advance: {verdict}")
        segs = card.locator(".tr-btw-seg").evaluate_all("els => els.map((e) => getComputedStyle(e).flexGrow)")
        assert segs == [better, tie, worse]
        # only the significant test gets a card: the Steam one is described once, in "How the test worked"
        expect(page.locator(".tr-qloo")).to_have_count(1)
        assert s.errors == []


def test_how_the_test_worked_is_collapsed_and_says_the_limits_once(browser):
    with Site(browser) as s:
        page = open_track(s)
        how = page.locator("details.tr-how")
        expect(how).not_to_have_attribute("open", "")
        expect(how.locator("[data-note]").first).to_be_hidden()
        how.locator("summary").click()
        expect(how).to_have_attribute("open", "")
        _, _, _, sp, smean, *_ = primary_line(section("Steam reviews"))
        steam_games = int(re.search(r"Dev \d+ games, test (\d+) games", section("Steam reviews"))[1])
        expect(how.locator('[data-note="small-indie"]')).to_have_text(
            f"On the {steam_games} small indie games (the Steam reviews test), Qloo's own addition was small "
            f"({pts(smean)} points vs the starting point) and not statistically significant (p {p_text(sp)}).")
        assert p_text(sp) == "= 0.50"
        expect(how.locator('[data-note="not-sales"]')).to_have_text("Both measures are signs of demand, not sales.")
        _, _, _, wp, wmean, lo, hi = primary_line(section("Wikipedia pageviews"))
        expect(how).to_contain_text("PREREGISTRATION.md")
        expect(how).to_contain_text(f"Wikipedia page views: p {p_text(wp)}, very unlikely to be luck")
        expect(how).to_contain_text(f"{pts(wmean)} points on average, likely {between(lo, hi)} (95% interval)")
        # said exactly once on the page, and only inside the collapsed section
        page.evaluate(OPEN_ALL)
        body = page.locator("#view-track").inner_text()
        inside = how.inner_text()
        for phrase in ("not statistically significant", "not sales", "small indie games (the Steam reviews test)"):
            assert body.count(phrase) == 1 and inside.count(phrase) == 1, phrase
        # in normal small text: the colour of the definitions, not a warning colour
        note = how.locator('[data-note="small-indie"]')
        color = lambda loc: loc.evaluate("e => getComputedStyle(e).color")  # noqa: E731
        assert color(note) == color(how.locator(".tr-defs dd").first)
        assert note.evaluate("e => getComputedStyle(e).backgroundColor") == "rgba(0, 0, 0, 0)"
        assert s.errors == []


def test_no_comparison_with_ai_tools_on_the_page(browser):
    with Site(browser) as s:
        page = open_track(s)
        page.evaluate(OPEN_ALL)
        for key in TRUTHS.values():  # every view of the explorer, every example
            choose_truth(page, key)
            for i in range(page.locator(".tr-example").count()):
                page.locator(".tr-example").nth(i).click()
                text = page.evaluate(ALL_TEXT)
                for word in ("Claude", "Groq", "AI alone", "AI on its own", "gpt-oss", "Opus 5", "Spearman",
                             "Exploratory", "blind spot", "rule out luck"):
                    assert word.lower() not in text.lower(), (word, key, i)
                assert not re.search(r"\bAI\b|\bnull\b|\bundefined\b|\bNaN\b", text), (key, i)  # game names: "Remnant"
        expect(page.locator('#tr-game [data-key="claude"]')).to_have_count(0)
        assert s.errors == []


# ---------------------------------------------------------------- predicted vs observed, game by game
def expect_game(page, tr, game):
    """The detail panel shows this game's served values: observed shares, each ranking, coverage."""
    expect(page.locator("#tr-game-title")).to_have_text(game["name"])
    label = {l["code"]: l["label"] for l in tr["languages"]}
    rankings = {"babel": game["rankings"]["babel"], "generic": tr["generic_ranking"]}
    rows = page.locator("#tr-game tbody tr")
    expect(rows).to_have_count(len(label))
    expect(page.locator("#tr-game thead th")).to_have_text(["Language", "Real share", "Babel", "Usual list"])
    expect(page.locator('#tr-game [data-key="typical_mix"]')).to_have_count(0)
    for code, share in game["observed_share"].items():
        row = page.locator(f'#tr-game tr[data-lang="{code}"]')
        expect(row.locator("th")).to_contain_text(label[code])
        expect(row.locator(".tr-share-value")).to_have_text(f"{fixed(share * 100, 1)}%")
        for key, ranking in rankings.items():
            expect(row.locator(f'td[data-key="{key}"] .tr-rank')).to_have_text(f"#{ranking.index(code) + 1}")
    for key in rankings:
        expect(page.locator(f'#tr-game dd[data-key="{key}"]')).to_have_text(
            f"{fixed(game['scores'][key]['coverage'] * 100, 1)}%")
    first = rows.first.locator("th")
    top = max(game["observed_share"], key=game["observed_share"].get)
    expect(first).to_contain_text(label[top])
    expect(page.locator("#tr-game .tr-match")).to_contain_text(game["real_top3"][0])


def test_a_representative_game_shows_predicted_vs_observed(browser):
    with Site(browser) as s:
        page = open_track(s)
        data = served(page)
        wiki = data["truths"]["wikipedia_pageviews"]
        expect(page.locator('input[name="tr-truth"][value="wikipedia_pageviews"]')).to_be_checked()
        # the default game is the rule-picked median game for Babel, as its example button says
        median = page.locator(".tr-example").first
        expect(median).to_contain_text("Typical result for Babel")
        name = median.locator(".tr-example-name").inner_text()
        game = next(g for g in wiki["games"] if g["name"] == name)
        ordered = sorted((g["scores"]["babel"]["coverage"] for g in wiki["games"]), reverse=True)
        assert game["scores"]["babel"]["coverage"] == ordered[(len(ordered) - 1) // 2]  # the upper median of 186
        expect_game(page, wiki, game)
        expect(page.locator(".tr-example")).to_have_count(2)
        page.locator(".tr-example", has_text="Biggest lead over the usual list").click()
        lead = lambda g: g["scores"]["babel"]["coverage"] - g["scores"]["generic"]["coverage"]  # noqa: E731
        best = max(lead(g) for g in wiki["games"])
        shown = page.locator(".tr-example", has_text="Biggest lead").locator(".tr-example-name").inner_text()
        game = next(g for g in wiki["games"] if g["name"] == shown)
        assert abs(lead(game) - best) < 1e-12
        expect_game(page, wiki, game)
        expect(page.locator("#tr-game-title")).to_be_focused()
        # a small indie game on the other measure, found by search
        choose_truth(page, "steam_reviews")
        steam = data["truths"]["steam_reviews"]
        target = sorted(steam["games"], key=lambda g: g["name"])[0]
        page.get_by_label("Find a test game").fill(target["name"])
        page.locator(f'.tr-game-row[data-appid="{target["appid"]}"]').click()
        expect_game(page, steam, target)
        assert s.errors == []


def test_the_game_picker_works_by_keyboard(browser):
    with Site(browser) as s:
        page = open_track(s)
        wiki = served(page)["truths"]["wikipedia_pageviews"]
        search = page.get_by_label("Find a test game")
        search.focus()
        page.keyboard.type("a")
        names = page.evaluate("(n) => n.sort((a, b) => a.localeCompare(b))",
                              [g["name"] for g in wiki["games"] if "a" in g["name"].lower()])
        expect(page.locator(".tr-game-row .tr-game-name")).to_have_text(names)
        page.keyboard.press("ArrowDown")
        expect(page.locator(".tr-game-row").first).to_be_focused()
        page.keyboard.press("ArrowDown")
        second = page.locator(".tr-game-row").nth(1)
        expect(second).to_be_focused()
        assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"  # visible focus
        page.keyboard.press("Enter")
        expect(second).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#tr-game-title")).to_have_text(names[1])
        page.keyboard.press("End")
        expect(page.locator(".tr-game-row").last).to_be_focused()
        page.keyboard.press("Home")
        page.keyboard.press("ArrowUp")
        expect(search).to_be_focused()
        # each row compares Babel with the usual list; the measure switch is a native control
        expect(page.locator("#tr-filter")).to_have_count(0)
        expect(page.locator(".tr-game-meta").first).to_contain_text("usual list")
        page.locator('input[name="tr-truth"]:checked').focus()
        page.keyboard.press("ArrowRight")
        expect(page.locator('input[name="tr-truth"][value="steam_reviews"]')).to_be_checked()
        # an example by keyboard moves focus to the game it shows
        example = page.locator(".tr-example").nth(1)
        example.focus()
        page.keyboard.press("Enter")
        expect(page.locator("#tr-game-title")).to_be_focused()
        expect(page.locator("#tr-game-title")).to_have_text(example.locator(".tr-example-name").inner_text())
        page.locator("#track-back").focus()
        page.keyboard.press("Enter")
        expect(page.locator("#view-start")).to_be_visible()
        assert s.errors == []


def test_phone_width_has_no_sideways_scroll(browser):
    with Site(browser, viewport=(390, 844)) as s:
        page = open_track(s)
        page.evaluate(OPEN_ALL)
        assert page.evaluate(NO_OVERFLOW)
        wide = page.evaluate("""() => [...document.querySelectorAll('#view-track *')]
          .filter((e) => e.getClientRects().length && e.getBoundingClientRect().right > window.innerWidth + 0.5)
          .map((e) => e.tagName + '.' + e.className)""")
        assert wide == []  # nothing is cut off inside a scrolling box either
        cards = page.locator(".tr-verdict").evaluate_all("els => els.map((e) => e.getBoundingClientRect().width)")
        assert len(cards) == 2 and all(w > 330 for w in cards)  # stacked, full width
        choose_truth(page, "steam_reviews")
        page.locator(".tr-example").nth(1).click()
        assert page.evaluate(NO_OVERFLOW) and s.errors == []
        table_box = page.locator("#tr-game table").bounding_box()
        assert table_box["x"] >= 0 and table_box["x"] + table_box["width"] <= 390


# ---------------------------------------------------------------- loading, failure, readiness
def test_loading_then_a_failed_load_then_retry(browser):
    with Site(browser) as s:
        page = s.page
        held = []
        s.context.route("**/track-record", lambda route: held.append(route))
        page.get_by_role("link", name="The full track record").click()
        expect(page.locator("#track-body [role=status]")).to_contain_text("Loading the track record")
        expect(page.locator("#track-title")).to_be_focused()
        for _ in range(100):  # the route holds the request until the test answers it
            if held:
                break
            page.wait_for_timeout(50)
        held[0].fulfill(status=500, content_type="application/json",
                        body=json.dumps({"error": "internal_error", "message": "Something went wrong."}))
        failed = page.locator("#track-body [role=alert]")
        expect(failed).to_contain_text("The track record could not load.")
        expect(failed).to_contain_text("Something went wrong.")
        s.context.unroute("**/track-record")
        page.get_by_role("button", name="Try again").click()
        expect(page.locator(".tr-verdict")).to_have_count(2)
        expect(page.locator("#track-title")).to_be_focused()


def test_the_dark_theme_keeps_every_figure_readable(browser):
    """The system's dark setting: dark cards, every text at WCAG AA, chart marks at 3:1 on their background with the
    series still told apart; printing keeps the light colours."""
    with Site(browser, color_scheme="dark") as s:
        page = open_track(s)
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.locator(".tr-example").last.click()  # a game with filled ranks and observed-top-3 tags
        page.evaluate(OPEN_ALL)
        cards = page.locator("#view-track .panel-card").evaluate_all(
            "els => els.map((e) => getComputedStyle(e).backgroundColor)")
        assert len(cards) >= 6 and all(luminance(c) < 0.02 for c in cards)
        assert page.evaluate(LOW_CONTRAST, "#view-track") == []
        marks = page.evaluate(MARK_CONTRAST, ".tr-compare-fill, .tr-btw-seg, .tr-share-fill")
        assert len(marks) >= 20 and [m for m in marks if m[1] < 3] == []
        color = lambda sel: page.locator(sel).first.evaluate("e => getComputedStyle(e).backgroundColor")  # noqa: E731
        series = [color(f".tr-btw-seg.is-{k}") for k in ("better", "tie", "worse")]
        assert len(set(series)) == 3
        assert color('.tr-compare-row[data-key="babel"] .tr-compare-fill') \
            != color('.tr-compare-row[data-key="generic"] .tr-compare-fill')
        page.emulate_media(media="print")  # the dark colours are screen-only
        assert color('.tr-compare-row[data-key="babel"] .tr-compare-fill') == "rgb(45, 108, 243)"
        assert color('#tr-game td[data-key="babel"]') == "rgb(243, 247, 254)"
        assert s.errors == []


def test_the_track_record_does_not_wait_for_the_runtime_data(browser):
    with Site(browser, ready=False) as s:
        page = open_track(s)
        expect(page.locator(".tr-verdict")).to_have_count(2)
        page.get_by_role("button", name="Back", exact=True).click()
        expect(page.locator("#view-start")).to_be_visible()
        page.locator('a[data-action="track"]').last.click()  # opening it again keeps the loaded screen
        expect(page.locator("#track-title")).to_be_focused()
        expect(page.locator(".tr-verdict")).to_have_count(2)
