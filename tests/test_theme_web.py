"""Light and dark themes (web/static/theme.js and the nav switch) in a real browser: the system setting is the
default and is followed live, the switch overrides it and is remembered, the new theme spreads in a circle from the
click (at once under reduced motion), and printing always uses the light colours.
Needs: python -m playwright install chromium
"""
import re

import pytest

from test_web import Site, browser  # noqa: F401  (the browser fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect

LIGHT_BG, DARK_BG = "rgb(241, 246, 246)", "rgb(10, 10, 10)"
BG = "() => getComputedStyle(document.body).backgroundColor"


def theme(page):
    return page.evaluate("document.documentElement.dataset.theme")


def test_the_system_setting_is_the_default_and_is_followed_live(browser):
    with Site(browser) as s:
        page = s.page
        assert theme(page) == "light" and page.evaluate(BG) == LIGHT_BG
        page.emulate_media(color_scheme="dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert page.evaluate(BG) == DARK_BG
        expect(page.locator("#theme-toggle")).to_have_attribute("aria-pressed", "true")
        assert not s.errors


def test_the_switch_overrides_the_system_and_is_remembered(browser):
    with Site(browser) as s:
        page = s.page
        toggle = page.get_by_role("button", name="Dark mode")
        expect(toggle).to_have_attribute("aria-pressed", "false")
        toggle.click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        expect(toggle).to_have_attribute("aria-pressed", "true")
        assert page.evaluate(BG) == DARK_BG
        assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "dark"
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")  # the choice is kept
        page.emulate_media(color_scheme="light")
        page.wait_for_timeout(100)
        assert theme(page) == "dark"  # a saved choice wins over the system setting
        page.get_by_role("button", name="Dark mode").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.keyboard.press("Tab")  # the switch keeps working by keyboard
        page.get_by_role("button", name="Dark mode").focus()
        page.keyboard.press("Enter")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert not s.errors


def test_printing_uses_the_light_colours(browser):
    with Site(browser) as s:
        page = s.page
        page.evaluate("babelTheme.set('dark')")
        assert page.evaluate(BG) == DARK_BG
        page.emulate_media(media="print")
        assert page.evaluate(BG) == LIGHT_BG
        page.emulate_media(media="screen")
        assert page.evaluate(BG) == DARK_BG


# Records each view transition and the circle it animates: [{clip: [from, to], duration}].
RECORD = """() => { window.__reveals = [];
  const start = document.startViewTransition.bind(document);
  document.startViewTransition = (cb) => { window.__reveals.push({}); return start(cb); };
  const animate = Element.prototype.animate;
  Element.prototype.animate = function (k, o) {
    if (o && o.pseudoElement === '::view-transition-new(root)') Object.assign(window.__reveals.at(-1),
      {clip: k.clipPath, duration: o.duration});
    return animate.call(this, k, o); }; }"""


def circle(css):
    """'circle(12px at 30px 40px)' -> (12, 30, 40)."""
    return tuple(int(n) for n in re.findall(r"(\d+)px", css))


def test_the_new_theme_spreads_in_a_circle_from_the_click(browser):
    with Site(browser, viewport=(1280, 800)) as s:
        page = s.page
        page.evaluate(RECORD)
        box = page.locator("#theme-toggle").bounding_box()
        x, y = round(box["x"] + 8), round(box["y"] + 12)
        page.mouse.click(x, y)
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.wait_for_function("() => window.__reveals.length && window.__reveals[0].clip")
        reveal = page.evaluate("window.__reveals[0]")
        r0, x0, y0 = circle(reveal["clip"][0])
        r1, x1, y1 = circle(reveal["clip"][1])
        assert r0 == 0 and (x0, y0) == (x1, y1) and abs(x0 - x) <= 1 and abs(y0 - y) <= 1  # from the click
        assert r1 ** 2 >= max(x0, 1280 - x0) ** 2 + max(y0, 800 - y0) ** 2  # and grows over the whole window
        assert reveal["duration"] <= 600  # fast
        page.locator("#theme-toggle").focus()  # by keyboard: from the button's centre
        page.keyboard.press("Enter")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.wait_for_function("() => window.__reveals.length === 2 && window.__reveals[1].clip")
        _, kx, ky = circle(page.evaluate("window.__reveals[1].clip[0]"))
        assert abs(kx - (box["x"] + box["width"] / 2)) <= 1 and abs(ky - (box["y"] + box["height"] / 2)) <= 1
        assert not s.errors


def test_reduced_motion_switches_at_once(browser):
    with Site(browser) as s:
        page = s.page
        page.emulate_media(reduced_motion="reduce")
        page.evaluate(RECORD)
        page.get_by_role("button", name="Dark mode").click()
        assert theme(page) == "dark"  # synchronously, no transition
        assert page.evaluate("window.__reveals.length") == 0


@pytest.mark.parametrize("width", [320, 360, 390])
def test_the_switch_fits_the_nav_on_small_phones(browser, width):
    with Site(browser, viewport=(width, 800)) as s:
        page = s.page
        assert page.evaluate("document.documentElement.scrollWidth") == width  # no sideways scroll
        for name in ("Babel home", "Dark mode", "Plan a game"):
            box = page.get_by_role("link" if name != "Dark mode" else "button", name=name).first.bounding_box()
            assert box and box["width"] >= 24 and box["x"] + box["width"] <= width, name
        assert page.locator(".logo-mark").bounding_box()["width"] == 26


def test_storage_that_throws_still_gives_a_working_switch(browser):
    with Site(browser) as s:
        page = s.page
        page.context.add_init_script("Object.defineProperty(window, 'localStorage', "
                                     "{get() { throw new Error('blocked'); }});")
        page.reload()
        assert theme(page) == "light"
        page.get_by_role("button", name="Dark mode").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
