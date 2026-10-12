"""The Start screen's world map (web/static/hero.js) in a real browser: it draws every continent whole from the 1:50m
outlines, pins the languages (Hindi and seven African languages too) without covering the cards, each other or a
connecting line, fits phones, redraws in black and greys for the dark theme, and lights the countries of Babel's own
language mapping. Needs: python -m playwright install chromium
"""
import json
from pathlib import Path

import pytest

from babel import languages
from test_web import Site, browser  # noqa: F401  (the browser fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect

READY = '.band[data-map="ready"]'
# Every shown chip and marker against the band, the two cards and each other (boxes relative to the band).
LAYOUT = """() => {
  const band = document.querySelector('.band').getBoundingClientRect();
  const box = (el) => { const r = el.getBoundingClientRect();
    return [r.left - band.left, r.top - band.top, r.right - band.left, r.bottom - band.top]; };
  const chips = [...document.querySelectorAll('.pin:not([hidden])')].map((el) => ({text: el.textContent, box: box(el)}));
  const markers = [...document.querySelectorAll('.hero-marker')].map((c) => [+c.getAttribute('cx'), +c.getAttribute('cy')]);
  const lines = [...document.querySelectorAll('.hero-leaders line')].map((l) =>
    [[+l.getAttribute('x1'), +l.getAttribute('y1')], [+l.getAttribute('x2'), +l.getAttribute('y2')]]);
  const card = (sel) => { const el = document.querySelector(sel);
    return getComputedStyle(el).position === 'absolute' || sel === '.game-card' ? box(el) : null; };
  return {w: band.width, h: band.height, chips, markers, lines,
    cards: [card('.game-card'), card('.evidence-card')].filter(Boolean)};
}"""


def overlaps(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def through(line, box):
    """Whether a connecting line passes through the inside of a chip (sampled every pixel or so)."""
    (x0, y0), (x1, y1) = line
    steps = max(2, int(max(abs(x1 - x0), abs(y1 - y0))))
    return any(box[0] + 3 < x0 + (x1 - x0) * t / steps < box[2] - 3 and box[1] + 3 < y0 + (y1 - y0) * t / steps < box[3] - 3
               for t in range(steps + 1))


def check_layout(page):
    page.wait_for_function("() => !document.querySelector('.pin.is-new')")  # the chips' entrance has finished
    layout = page.evaluate(LAYOUT)
    chips, cards = layout["chips"], layout["cards"]
    assert len(layout["markers"]) == len(chips)
    for i, chip in enumerate(chips):
        x0, y0, x1, y1 = chip["box"]
        assert 0 <= x0 and 0 <= y0 and x1 <= layout["w"] and y1 <= layout["h"], chip
        assert not any(overlaps(chip["box"], card) for card in cards), chip
        assert not any(overlaps(chip["box"], other["box"]) for other in chips[i + 1:]), chip
    for x, y in layout["markers"]:
        assert not any(c[0] <= x <= c[2] and c[1] <= y <= c[3] for c in cards), (x, y)
    for line in layout["lines"]:  # a line may end on its own chip's edge, never cross another chip
        assert not any(through(line, chip["box"]) for chip in chips), line
    return [c["text"] for c in chips]


def canvas_ink(page):
    """How many canvas pixels are drawn, and their mean colour (the map's dots, glow and grid)."""
    return page.evaluate("""() => {
      const c = document.querySelector('.hero-map');
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      let n = 0, r = 0, g = 0, b = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) { n++; r += d[i]; g += d[i + 1]; b += d[i + 2]; }
      return {n, mean: n ? [r / n, g / n, b / n].map(Math.round) : null};
    }""")


AFRICAN = ["العربية", "Hausa", "አማርኛ", "Kiswahili", "Lingála", "Soomaali", "isiZulu"]


def test_the_world_map_pins_every_language_hindi_and_african_ones_clear_of_the_cards(browser):
    with Site(browser, viewport=(1440, 900)) as s:
        page = s.page
        page.wait_for_selector(READY)
        names = check_layout(page)
        assert "हिन्दी" in names and "简体中文" in names and "Español" in names
        assert all(name in names for name in AFRICAN)
        assert len(names) == 22
        assert page.locator('.pin[lang="hi"]').is_visible() and page.locator('.pin[lang="am"]').is_visible()
        assert canvas_ink(page)["n"] > 5000
        # every continent whole: land dots reach the band's lowest tenth (South America's tip, Australia, South Africa)
        assert page.evaluate("""() => { const c = document.querySelector('.hero-map'), ctx = c.getContext('2d');
          const d = ctx.getImageData(0, Math.floor(c.height * 0.86), c.width, Math.floor(c.height * 0.1)).data;
          let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 200) n++; return n; }""") > 50
        for layer in (".hero-map", ".hero-leaders", ".pins"):  # decorative only: screen readers skip it
            assert page.locator(f".band > {layer}").get_attribute("aria-hidden") == "true"
        assert not s.errors


@pytest.mark.parametrize("viewport", [(1100, 800), (820, 1000), (390, 844)])
def test_the_map_fits_smaller_screens(browser, viewport):
    with Site(browser, viewport=viewport) as s:
        page = s.page
        page.wait_for_selector(READY)
        names = check_layout(page)
        assert len(names) >= 8 and "हिन्दी" in names
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if viewport[0] < 600:
            assert len(names) == 8  # a phone shows the most-spoken languages only
        assert not s.errors


def test_the_map_redraws_for_the_dark_theme_and_on_resize(browser):
    with Site(browser, viewport=(1280, 900)) as s:
        page = s.page
        page.wait_for_selector(READY)
        light = canvas_ink(page)
        page.locator("#theme-toggle").click()
        page.wait_for_function(f"(m) => {{ const c = document.querySelector('.hero-map'); "
                               f"const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; "
                               f"let r = 0, n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) {{ n++; r += d[i]; }} "
                               f"return n && Math.round(r / n) !== m; }}", arg=light["mean"][0])
        dark = canvas_ink(page)
        assert dark["mean"] != light["mean"] and max(dark["mean"]) - min(dark["mean"]) <= 3  # black, greys, white
        page.set_viewport_size({"width": 900, "height": 900})
        page.wait_for_function("() => document.querySelector('.hero-map').width <= 900 * devicePixelRatio")
        check_layout(page)
        assert not s.errors


def test_the_lit_countries_are_babels_own_language_mapping(browser):
    with Site(browser) as s:
        hero = s.page.evaluate("async () => { const m = await import('/static/hero.js'); "
                               "return {spoken: m.SPOKEN, also: m.ALSO, pins: m.PINS.map((p) => p.lang)}; }")
        expected = {lang: sorted(codes) for lang, codes in languages.COUNTRIES.items()}
        assert {lang: sorted(codes) for lang, codes in hero["spoken"].items()} == expected
        assert not set(hero["also"]) & set(languages.COUNTRIES)  # the extra languages are not ones Babel plans for
        assert set(hero["pins"]) == set(hero["spoken"]) | set(hero["also"])  # one chip per language, each lit


def test_the_finer_outlines_keep_small_islands_and_stay_light():
    """web/static/world-hero.json (tools/build_world.py --hero): 1:50m outlines, ids only, small islands as points."""
    path = Path(__file__).resolve().parent.parent / "web" / "static" / "world-hero.json"
    world = json.loads(path.read_text(encoding="utf-8"))
    assert "1:50m" in world["source"] and path.stat().st_size < 450_000
    ids = {f["id"] for f in world["features"]}
    assert {"CN", "BR", "NG", "ET", "ZA", "IN", "JP"} <= ids and "AQ" not in ids
    assert len(world["islands"]) > 500 and all(len(i) == 3 for i in world["islands"])
    assert any(i[2] in ("HK", "MO") for i in world["islands"]) or ids & {"HK", "MO"}  # tiny places still count
