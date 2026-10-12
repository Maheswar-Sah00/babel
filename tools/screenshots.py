"""Screenshots of the browser app against a running server (real backend), for the README and Devpost.

  uvicorn babel.api:app --port 8765          (in another terminal; wait for /health/ready)
  python tools/screenshots.py --base http://127.0.0.1:8765 --out docs/screenshots
The working-screen shot is taken while the agent is really running (a swapped comparable game and a new budget force
a fresh plan, so it calls Claude and may call Qloo). The Plan screen shots use the WEBFISHING demo plan; its one-page
report is also saved as docs/samples/report-webfishing.pdf.
"""
import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


NO_INVITE = "try { localStorage.setItem('babel.tour', 'seen'); } catch (e) {}"  # no first-visit tour invitation


def plan_for(page, demo, words="30000", budget="10000"):
    """Run a demo game with these words and budget, and wait for the Plan screen's map."""
    page.get_by_role("link", name="Plan a game").click()
    page.get_by_role("button", name=demo).click()
    page.locator(".card img").first.wait_for(timeout=60_000)
    page.get_by_label("Words to translate").fill(words)
    page.get_by_label("Translation budget").fill(budget)
    page.get_by_role("button", name="Run the plan").click()
    expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready", timeout=180_000)
    page.wait_for_timeout(1200)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--out", default="docs/screenshots")
    ap.add_argument("--budget", default="49000", help="budget for the live run (a new value forces a fresh plan)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1024}, device_scale_factor=1)
        page.add_init_script(NO_INVITE)
        page.goto(a.base)
        expect(page.get_by_role("button", name="Find similar games")).to_be_enabled(timeout=120_000)
        page.wait_for_timeout(1500)  # fonts
        page.screenshot(path=out / "01-start.png")
        page.evaluate("babelTheme.set('dark')")  # the same screen in the dark theme
        page.wait_for_timeout(800)
        page.screenshot(path=out / "19-start-dark.png")
        page.evaluate("babelTheme.set('light')")

        page.locator("#game-input").fill("store.steampowered.com/app/nope")
        page.get_by_role("button", name="Find similar games").click()
        page.screenshot(path=out / "02-validation.png", clip={"x": 0, "y": 380, "width": 1440, "height": 640})

        page.get_by_role("button", name="Dawnsbury Days").click()
        page.locator(".card img").first.wait_for(timeout=60_000)
        page.wait_for_timeout(1500)  # Steam artwork
        page.locator("#setup").screenshot(path=out / "03-comparables.png")

        page.get_by_role("button", name=r"Swap Marvel's Midnight Suns").click()
        page.wait_for_timeout(1200)
        page.screenshot(path=out / "04-swap.png")
        page.get_by_role("dialog").get_by_role("button", name="Baldur's Gate").first.click()
        page.get_by_label("Words to translate").fill("200000")
        page.get_by_label("Translation budget").fill(a.budget)
        page.get_by_role("button", name="Run the plan").click()
        running = '.step[data-step="{}"][data-state="running"]'
        page.locator(f"{running.format('markets')}, {running.format('explain')}").first.wait_for(timeout=120_000)
        page.wait_for_timeout(600)
        page.screenshot(path=out / "05-working-live.png", full_page=True)
        expect(page.locator("#view-plan")).to_be_visible(timeout=180_000)

        plan_for(page, "WEBFISHING")  # the Plan screen: global view, a country, a language, the plan, the why
        page.mouse.move(0, 0)
        page.locator(".explore").screenshot(path=out / "06-plan-map.png")
        page.locator("#country-search").fill("Japan")
        page.locator("#country-search").press("Enter")
        page.wait_for_timeout(900)
        page.locator(".explore").screenshot(path=out / "07-plan-country.png")
        page.get_by_role("button", name="← All countries").click()
        page.get_by_role("button", name="Spanish: show its countries").click()
        page.wait_for_timeout(900)
        page.locator(".explore").screenshot(path=out / "08-plan-language.png")
        page.locator(".localize").screenshot(path=out / "09-plan-localization.png")
        page.get_by_role("button", name="Why this recommendation for Russian?").click()
        page.wait_for_timeout(500)
        page.locator("#why-dialog").screenshot(path=out / "10-plan-why.png")
        page.keyboard.press("Escape")
        page.locator(".versus").screenshot(path=out / "11-plan-vs-generic.png")
        page.evaluate("babelTheme.set('dark')")
        page.wait_for_timeout(800)
        page.locator(".explore").screenshot(path=out / "20-plan-dark.png")
        page.evaluate("babelTheme.set('light')")

        page.get_by_role("button", name="Export report").click()  # the one-page report, on screen and as a PDF
        page.locator(".report-sheet").wait_for()
        page.wait_for_timeout(800)
        page.locator(".report-sheet").screenshot(path=out / "12-report.png")
        samples = out.parent / "samples"
        samples.mkdir(exist_ok=True)
        page.emulate_media(media="print")
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        page.pdf(path=samples / "report-webfishing.pdf", format="A4", print_background=True)
        page.emulate_media(media="screen")
        page.get_by_role("button", name="Back to the plan").click()

        page.get_by_role("link", name="Track record").first.click()  # the backtest results
        page.locator("#track-title").wait_for()
        page.wait_for_timeout(1200)
        page.screenshot(path=out / "13-track-record.png")

        tour = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)  # the guided tour
        tour.add_init_script(NO_INVITE)
        tour.goto(a.base)
        expect(tour.get_by_role("button", name="Find similar games")).to_be_enabled(timeout=120_000)
        tour.get_by_role("button", name="Take the tour").click()
        popover = tour.get_by_role("dialog").filter(has_text="Step")
        for _ in range(30):
            if "Step 9 of" in popover.inner_text():
                break
            tour.get_by_role("button", name="Next").click()
            tour.wait_for_timeout(900)
        tour.wait_for_timeout(1200)
        tour.screenshot(path=out / "17-tour.png")
        tour.close()

        plan_for(page, "WEBFISHING")  # the assistant, on a fresh demo plan (a cached answer: no new Claude call)
        page.locator("#assistant-launcher").click()
        page.locator("#assistant-input").fill("Why is Russian the first language?")
        page.locator("#assistant-input").press("Enter")
        page.locator("#assistant-root .asst-receipt").first.wait_for(timeout=120_000)
        page.wait_for_timeout(1500)
        page.keyboard.press("Escape")  # close the "Why?" calculation it opened, so the chat shows
        page.wait_for_timeout(600)
        page.screenshot(path=out / "18-assistant.png")

        phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        phone.add_init_script(NO_INVITE)
        phone.goto(a.base)
        expect(phone.get_by_role("button", name="Find similar games")).to_be_enabled(timeout=120_000)
        phone.wait_for_timeout(1500)
        phone.screenshot(path=out / "14-phone-start.png")
        phone.get_by_role("button", name="WEBFISHING").click()
        phone.locator(".card img").first.wait_for(timeout=60_000)
        phone.wait_for_timeout(1200)
        phone.locator("#cards").screenshot(path=out / "15-phone-comparables.png")
        phone.get_by_role("button", name="Run the plan").click()
        expect(phone.locator("#map-canvas")).to_have_attribute("data-state", "ready", timeout=180_000)
        phone.mouse.move(0, 0)  # a phone has no hover outline
        phone.wait_for_timeout(1000)
        phone.locator(".explore").screenshot(path=out / "16-phone-plan.png")
        browser.close()
    print("\n".join(str(f) for f in sorted(out.glob("*.png"))))


if __name__ == "__main__":
    main()
