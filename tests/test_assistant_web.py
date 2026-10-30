"""The AI assistant's panel in a real browser (Playwright + Chromium) against the real app with fakes (test_web.Site).

POST /assistant is stubbed with Playwright routing, so these tests do not depend on the backend: each stub records the
request bodies (checked against the contract: messages and context) and answers with canned replies, errors or a
broken connection. Actions run through the app's own actions.js, so they really change the screens. Needs:
python -m playwright install chromium
"""
import json
import re
import time

import pytest

import synthetic
from babel import plan as P
from babel.languages import LABEL
from test_track_web import LOW_CONTRAST, contrast, luminance
from test_web import FakeAgent, FakeLookup, Site, browser, group_names  # noqa: F401  (browser: the fixture)

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect
NO_OVERFLOW = "document.documentElement.scrollWidth <= window.innerWidth"
CHECKED = "Numbers checked against Babel's data"
FALLBACK = "Written by Babel's code"
REPLACED = "I couldn't answer that from this plan's evidence without quoting numbers I can't verify."
NO_PLAN = {"view": "start", "plan_id": None, "budget": None, "metric": None, "country": None, "language": None,
           "lookalike": None}


def reply(text="Russian comes first: it has the highest estimated share.", actions=(), dropped=(),
          sources=("lang:russian",), kind="llm_text", checked=True):
    return {"reply": text, "kind": kind, "checked": checked, "actions": list(actions),
            "dropped_actions": list(dropped), "sources": list(sources)}


class Stub:
    """Answers POST /assistant in the browser: replies in order (the last one repeats); records each request body.
    A reply is a dict (200), a (status, headers, body) tuple, or "abort" (a broken connection)."""

    def __init__(self, s, *replies):
        self.bodies, self.sizes, self.replies = [], [], list(replies)
        s.context.route("**/assistant", self.handle)

    def handle(self, route):
        self.bodies.append(route.request.post_data_json)
        self.sizes.append(len(route.request.post_data_buffer))  # what the server's 16,384-byte limit counts
        answer = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if answer == "abort":
            return route.abort()
        status, headers, body = answer if isinstance(answer, tuple) else (200, {}, answer)
        route.fulfill(status=status, headers=headers, content_type="application/json", body=json.dumps(body))


def launcher(page):
    return page.get_by_role("button", name="Ask Babel's assistant")


def panel(page):
    return page.get_by_role("dialog", name="Babel assistant")


def open_panel(page):
    launcher(page).click()
    expect(panel(page)).to_be_visible()
    expect(page.locator("#assistant-input")).to_be_focused()


def ask(page, text):
    page.locator("#assistant-input").fill(text)
    page.locator("#assistant-input").press("Enter")


def receipts(scope):
    return scope.locator(".asst-receipt")


def settled_box(locator):
    """The bounding box once the element's animations (the panel slides in) have finished."""
    locator.evaluate("el => Promise.all(el.getAnimations().map((a) => a.finished))")
    return locator.bounding_box()


def plan_id(page):
    return page.evaluate("async () => (await import('/static/plan.js')).currentPlan().res.plan_id")


# ---------------------------------------------------------------- the launcher and the panel
def test_the_launcher_opens_and_closes_with_escape_and_focus_returns(browser):
    with Site(browser) as s:
        page = s.page
        button = launcher(page)
        expect(button).to_have_attribute("aria-expanded", "false")
        expect(button.locator(".asst-ai")).to_have_text("AI")
        button.hover()
        expect(page.locator(".asst-tip")).to_have_css("opacity", "1")
        expect(page.locator(".asst-tip")).to_have_text("Ask Babel's assistant")

        open_panel(page)
        dialog = panel(page)
        expect(dialog).to_contain_text("Answers from Babel's data · can use the app for you")
        expect(dialog).to_have_attribute("aria-modal", "false")  # docked beside the page at 1280 px
        expect(page.locator("body")).to_have_attribute("data-assistant", "docked")
        expect(button).to_be_hidden()
        assert page.locator(".asst-chip").all_inner_texts() == ["Plan WEBFISHING", "What does Babel do?",
                                                                 "Take the tour"]
        assert page.locator("#assistant-input").get_attribute("maxlength") == "2000"
        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        expect(button).to_be_focused()
        expect(button).to_have_attribute("aria-expanded", "false")
        assert page.locator("body").get_attribute("data-assistant") is None

        open_panel(page)
        page.get_by_role("button", name="Close the assistant").click()
        expect(dialog).to_be_hidden()
        expect(button).to_be_focused()

        # the suggestions follow the screen, also while the panel is open
        page.get_by_role("link", name="The full track record").click()
        expect(page.locator("#view-track")).to_be_visible()
        open_panel(page)
        expect(page.locator(".asst-chip").first).to_have_text("How much better is Babel than the usual list?")
        page.locator("#track-back").click()
        expect(page.locator(".asst-chip").first).to_have_text("Plan WEBFISHING")
        assert s.errors == []


def test_a_reply_is_rendered_as_text_with_its_label_and_the_request_follows_the_contract(browser):
    with Site(browser) as s:
        page = s.page
        stub = Stub(s, reply("Babel turns Qloo fan maps of look-alike games into a costed translation plan."),
                    reply('<img src=x onerror="window.pwned = 1">Not <b>bold</b>.', sources=()))
        open_panel(page)
        page.get_by_role("button", name="What does Babel do?").click()
        message = page.locator(".asst-msg.is-assistant").first
        expect(message.locator(".asst-text")).to_have_text(
            "Babel turns Qloo fan maps of look-alike games into a costed translation plan.")
        expect(message.locator(".asst-label")).to_contain_text(CHECKED)
        expect(page.locator("#assistant-root [aria-live='polite']")).to_contain_text("costed translation plan")
        assert stub.bodies == [{"messages": [{"role": "user", "text": "What does Babel do?"}], "context": NO_PLAN}]
        expect(page.locator("#assistant-input")).to_be_focused()
        sources = message.locator(".asst-sources")  # evidence ids: one click away
        expect(sources.locator("summary")).to_have_text("Sources it cites (1)")
        expect(sources.locator(".asst-source")).to_be_hidden()
        sources.locator("summary").click()
        expect(sources.locator(".asst-source")).to_have_text(["lang:russian"])
        expect(sources.locator(".asst-source")).to_be_visible()

        ask(page, "And the evidence?")  # the history goes along; replies are text, never HTML
        expect(page.locator(".asst-text").nth(1)).to_have_text('<img src=x onerror="window.pwned = 1">Not <b>bold</b>.')
        assert page.locator("#assistant-panel img:not(.asst-mark), #assistant-panel b").count() == 0
        assert page.evaluate("window.pwned") is None
        first = "Babel turns Qloo fan maps of look-alike games into a costed translation plan."
        assert stub.bodies[1]["messages"] == [{"role": "user", "text": "What does Babel do?"},
                                              {"role": "assistant", "text": first},
                                              {"role": "user", "text": "And the evidence?"}]

        page.reload()  # the conversation survives a reload in this tab (sessionStorage)
        open_panel(page)
        expect(page.locator(".asst-msg.is-user")).to_have_count(2)
        expect(page.locator(".asst-welcome")).to_be_hidden()
        page.get_by_role("button", name="New conversation").click()
        expect(page.locator(".asst-msg")).to_have_count(0)
        expect(page.locator(".asst-welcome")).to_be_visible()
        expect(page.locator("#assistant-input")).to_be_focused()
        assert page.evaluate("sessionStorage.getItem('babel.assistant.v1')") is None
        assert s.errors == []


def test_the_history_sent_is_trimmed_to_twelve_messages_of_2000_characters(browser):
    with Site(browser) as s:
        page = s.page
        stub = Stub(s, reply("x" * 2500, sources=()))
        open_panel(page)
        for i in range(7):
            ask(page, f"Question {i}")
            expect(page.locator(".asst-msg.is-assistant")).to_have_count(i + 1)
        messages = stub.bodies[-1]["messages"]
        assert len(messages) == 12 and messages[-1] == {"role": "user", "text": "Question 6"}
        assert messages[0]["role"] == "assistant" and all(len(m["text"]) <= 2000 for m in messages)
        page.locator("#assistant-input").fill("y" * 2100)  # the field stops at the limit and counts near it
        assert len(page.locator("#assistant-input").input_value()) == 2000
        expect(page.locator(".asst-count")).to_have_text("2,000 / 2,000")
        assert s.errors == []


def test_long_histories_are_trimmed_under_the_body_limit(browser):
    with Site(browser) as s:
        page = s.page
        stub = Stub(s, reply("ü" * 2000, sources=()))  # 4,000 bytes of UTF-8 per answer
        open_panel(page)
        for i in range(5):
            ask(page, f"Question {i} " + "é" * 1400)  # about 2,800 bytes per question
            expect(page.locator(".asst-msg.is-assistant")).to_have_count(i + 1)
        assert max(stub.sizes) <= 15000 and stub.sizes[0] < stub.sizes[-1]
        talk = []
        for i in range(5):
            talk += [{"role": "user", "text": f"Question {i} " + "é" * 1400},
                     {"role": "assistant", "text": "ü" * 2000}]
        sent = stub.bodies[-1]
        n = len(sent["messages"])
        assert 1 < n < 9 and sent["messages"] == talk[:-1][-n:]  # the newest, ending with the latest question

        def size(messages):
            return len(json.dumps({"messages": messages, "context": sent["context"]}, ensure_ascii=False,
                                  separators=(",", ":")).encode())
        assert size(talk[:-1][-n:]) == stub.sizes[-1] and size(talk[:-1][-n - 1:]) > 15000  # only the oldest went
        assert s.errors == []


def test_the_context_sent_is_valid_or_null(browser):
    with Site(browser) as s:
        out = s.page.evaluate("""async () => {
          const { assistantContext } = await import('/static/assistant.js');
          const plan = (over) => ({ res: { plan_id: 'abcdef0123456789' }, fit: { costs: { budget: 5000 } },
            metric: 'plan', country: 'JP', language: 'russian', lookalike: '3146520', ...over });
          return [assistantContext('plan', plan({})),
            assistantContext('', plan({ res: { plan_id: 'ABCDEF0123456789' }, fit: { costs: { budget: -1 } },
              metric: '', country: 'jp', language: 'klingon', lookalike: '' })),
            assistantContext('plan', plan({ fit: { costs: { budget: 2e7 } }, country: '-99', lookalike: 'all' })),
            assistantContext(undefined, { res: undefined, metric: 'affinity', lookalike: 'all' })];
        }""")
        assert out[0] == {"view": "plan", "plan_id": "abcdef0123456789", "budget": 5000, "metric": "plan",
                          "country": "JP", "language": "russian", "lookalike": "3146520"}
        assert out[1] == NO_PLAN  # invalid values become null, never empty strings
        assert out[2] == {**out[0], "budget": None, "country": None, "lookalike": "all"}
        assert out[3] == NO_PLAN
        assert s.errors == []


# ---------------------------------------------------------------- actions
def test_an_action_chain_changes_the_plan_screen_beside_the_docked_panel(browser):
    with Site(browser, viewport=(1440, 900)) as s:
        page = s.plan()
        first = synthetic.result()["plan"]
        stub = Stub(s, reply("At $5,000 Russian still fits in full. Japan is over-represented.", actions=[
            {"type": "set_budget", "budget": 5000, "label": "Set the budget to $5,000"},
            {"type": "show_country", "country": "JP", "label": "Show Japan on the map"}],
            sources=["lang:russian", "country:JP"]), reply("Noted.", sources=()))
        open_panel(page)
        top = LABEL[first["groups"]["translate_game"][0]]
        assert page.locator(".asst-chip").all_inner_texts()[:3] == [f"Why {top}?", "What if my budget is $5,000?",
                                                                      "Show Japan on the map"]
        ask(page, "What if my budget is $5,000? Show me Japan.")
        rows = receipts(page.locator("#assistant-panel"))
        expect(rows).to_have_text(["✓ Set the budget to $5,000", "✓ Show Japan on the map"])
        live = page.locator("#assistant-root [aria-live='polite']")  # the reply and then what was done
        expect(live).to_contain_text("Babel assistant: At $5,000 Russian still fits in full.")
        expect(live).to_contain_text("Done: Set the budget to $5,000. Done: Show Japan on the map.")
        assert stub.bodies[0]["context"] == {"view": "plan", "plan_id": plan_id(page), "budget": 10000,
                                             "metric": "relative", "country": None, "language": None,
                                             "lookalike": "all"}
        assert re.fullmatch(r"[0-9a-f]{16}", stub.bodies[0]["context"]["plan_id"])

        # the Plan screen really changed: the server re-fitted the budget, and the map panel shows Japan
        a = first["allocation"]
        expected = P.fit_budget(a["shares"], a["cost_full"], a["cost_store_page"], 5000, a["min_share"],
                                a["supported"])
        expect(page.locator("#plan-budget")).to_have_value("5000")
        lead = LABEL[expected["groups"]["translate_game"][0]]
        expect(page.locator("#plan-title")).to_contain_text(f"Translate {lead}")
        assert group_names(page, "translate_game") == [LABEL[c] for c in expected["groups"]["translate_game"]]
        expect(page.locator("#panel-title")).to_have_text("Japan")
        expect(page.locator("#plan-chips")).to_contain_text("Budget changed from $10,000")

        # docked: the page shifted left, so nothing the actions changed is under the panel
        box = settled_box(panel(page))
        assert box["x"] >= 1440 - 400 - 1 and box["width"] <= 401
        for selector in ("#map-panel", "#map-canvas", ".plan-page"):
            other = page.locator(selector).bounding_box()
            assert other["x"] + other["width"] <= box["x"], selector
        expect(page.locator("#panel-title")).to_be_in_viewport()
        expect(page.locator("#assistant-input")).to_be_focused()  # the chat keeps the keyboard
        assert page.evaluate(NO_OVERFLOW)

        expect(page.locator(".asst-chip").nth(1)).to_have_text("What if my budget is $20,000?")
        ask(page, "Thanks")  # the next request sees the new state
        expect(page.locator(".asst-text")).to_have_count(2)
        context = stub.bodies[1]["context"]
        assert context["budget"] == 5000 and context["country"] == "JP" and context["view"] == "plan"
        assert s.errors == []


def test_failed_and_dropped_actions_get_receipts_and_stop_the_chain(browser):
    with Site(browser) as s:
        page = s.page
        Stub(s, reply("I'll change the budget, then show Japan.", actions=[
            {"type": "set_budget", "budget": 5000, "label": "Set the budget to $5,000"},
            {"type": "show_country", "country": "JP", "label": "Show Japan on the map"}],
            dropped=[{"type": "open_why", "reason": "No plan is open yet."},
                     {"type": "set_metric", "reason": "The open plan is no longer on this server: run it again."}]),
            reply("Trying.", actions=[{"type": "fly", "label": "Fly to the moon"}], sources=()))
        open_panel(page)
        ask(page, "Set the budget to $5,000 and show Japan")
        rows = receipts(page.locator(".asst-msg.is-assistant").first)
        expect(rows).to_have_text([
            "✗ Couldn't set the budget to $5,000: There is no plan open yet: run one first.",
            "– Skipped: Show Japan on the map (the step before it failed)",
            "! Not done: No plan is open yet.",
            "! Not done: The open plan is no longer on this server: run it again."])
        expect(rows.nth(0)).to_have_class(re.compile("is-failed"))
        expect(page.locator("#view-start")).to_be_visible()  # nothing moved
        expect(page.locator("#assistant-root [aria-live='polite']")).to_contain_text("Failed: Couldn't set the budget")
        ask(page, "Fly")
        expect(receipts(page.locator(".asst-msg.is-assistant").nth(1))).to_have_text(
            ["✗ Couldn't fly to the moon: Babel can't do \"fly\" here."])
        expect(page.locator(".asst-send")).to_be_enabled()
        assert s.errors == []


@pytest.mark.parametrize("viewport", [(1440, 900), (390, 844)], ids=["docked", "phone"])
def test_run_plan_from_the_start_screen_starts_a_live_run(browser, viewport):
    with Site(browser, agent=FakeAgent(delay=0.15), viewport=viewport) as s:
        page = s.page
        Stub(s, reply("Planning WEBFISHING: 30,000 words, a $10,000 budget.", sources=(), actions=[
            {"type": "run_plan", "label": "Plan WEBFISHING", "game": {"appid": 3146520}, "word_count": 30000,
             "budget": 10000}]))
        open_panel(page)
        page.get_by_role("button", name="Plan WEBFISHING").click()
        expect(page.locator("#view-working")).to_be_visible()  # the live trace, while the run is going
        expect(page.locator(".step").first).to_be_visible()
        docked = viewport[0] >= 1200
        if docked:  # the panel stays usable beside the run
            expect(panel(page)).to_be_visible()
            expect(receipts(panel(page))).to_have_text(["✓ Plan WEBFISHING"])
            expect(page.locator(".asst-send")).to_be_enabled()
        else:  # the sheet steps aside so the run is seen; a card keeps the answer
            expect(panel(page)).to_be_hidden()
            peek = page.locator(".asst-peek")
            expect(peek).to_contain_text("Planning WEBFISHING")
            expect(receipts(peek)).to_have_text(["✓ Plan WEBFISHING"])
            assert page.evaluate(NO_OVERFLOW)
        expect(page.locator("#view-plan")).to_be_visible()
        assert s.lookup.calls[0]["appid"] == 3146520
        call = s.agent.calls[0]
        assert (call["appid"], call["word_count"], call["budget"]) == (3146520, 30000, 10000)
        if not docked:
            page.get_by_role("button", name="Open the chat").click()
            expect(panel(page)).to_be_visible()
            expect(receipts(panel(page))).to_have_text(["✓ Plan WEBFISHING"])
            expect(page.locator(".asst-peek")).to_be_hidden()
        assert s.errors == []


# ---------------------------------------------------------------- labels and failures
def test_code_written_replies_are_labelled_as_such_in_the_tablet_drawer(browser):
    with Site(browser, viewport=(1024, 800)) as s:
        page = s.page
        unavailable = ("The assistant needs the LLM, which isn't available right now. Every button and screen in Babel "
                       "still works.")
        Stub(s, reply(unavailable, kind="fallback", checked=True, sources=()),
             reply(REPLACED, kind="fallback", checked=False, sources=("product:limits",),  # actions may still come
                   actions=[{"type": "open_track_record", "label": "Open the track record"}]))
        open_panel(page)
        expect(page.locator("body")).to_have_attribute("data-assistant", "sheet")  # a modal drawer here
        expect(panel(page)).to_have_attribute("aria-modal", "true")
        assert page.locator("main").evaluate("el => el.inert") is True
        ask(page, "What does Babel do?")
        first = page.locator(".asst-msg.is-assistant").first
        expect(first.locator(".asst-label-text")).to_have_text(FALLBACK)
        expect(first).to_have_class(re.compile("is-fallback"))
        assert "Claude ·" not in first.inner_text()

        ask(page, "How much will Japan earn me?")  # Claude's answer failed the number check: code replaced it
        expect(page.locator(".asst-peek")).to_contain_text(REPLACED)
        expect(page.locator("#view-track")).to_be_visible()
        page.get_by_role("button", name="Open the chat").click()
        second = page.locator(".asst-msg.is-assistant").nth(1)
        expect(second.locator(".asst-label-text")).to_have_text(
            f"{FALLBACK} · the first answer's numbers couldn't be verified")
        expect(second.locator(".asst-source")).to_have_text(["product:limits"])
        expect(receipts(second)).to_have_text(["✓ Open the track record"])
        assert page.locator("#assistant-panel a").count() == 0  # evidence chips are not links
        page.mouse.click(100, 400)  # the backdrop closes the drawer
        expect(panel(page)).to_be_hidden()
        expect(launcher(page)).to_be_focused()
        assert page.locator("main").evaluate("el => el.inert") is False
        assert s.errors == []


def test_a_rate_limit_counts_down_before_sending_again(browser):
    with Site(browser) as s:
        page = s.page
        stub = Stub(s, (429, {"Retry-After": "3"}, {"error": "rate_limited", "message": "Too many requests.",
                                                    "request_id": "req-429"}),
                    reply("Hello again.", sources=()))
        open_panel(page)
        started = time.monotonic()
        ask(page, "Hello")
        error = page.locator(".asst-msg.is-error")
        expect(error).to_contain_text("You're going a little fast. Try again in 3 seconds.")
        expect(error).to_contain_text("Request ID req-429")
        expect(page.locator(".asst-keys")).to_have_text(re.compile(r"You can send again in [1-3] s"))
        expect(page.locator(".asst-send")).to_be_disabled()
        retry = error.get_by_role("button", name=re.compile("Try again"))
        expect(retry).to_have_text(re.compile(r"Try again in [1-3] s"))
        expect(retry).to_be_disabled()
        ask(page, "Hello?")  # Enter does nothing while waiting
        assert len(stub.bodies) == 1
        expect(retry).to_have_text("Try again", timeout=6000)
        assert time.monotonic() - started >= 2.4
        expect(page.locator(".asst-send")).to_be_enabled()
        expect(page.locator(".asst-keys")).to_have_text("Enter to send · Shift+Enter for a new line")
        page.locator("#assistant-input").fill("")
        retry.click()
        expect(page.locator(".asst-text")).to_have_text("Hello again.")
        expect(error).to_have_count(0)
        assert len(stub.bodies) == 2 and stub.bodies[1]["messages"] == [{"role": "user", "text": "Hello"}]
        assert s.errors == []


def test_network_and_server_errors_offer_try_again(browser):
    with Site(browser) as s:
        page = s.page
        stub = Stub(s, "abort", (503, {}, {"error": "busy", "message": "Busy.", "request_id": "req-503"}),
                    reply("Here you are.", sources=()))
        open_panel(page)
        ask(page, "Why Russian?")
        error = page.locator(".asst-msg.is-error")
        expect(error).to_contain_text("Can't reach the Babel server. Check your connection and try again.")
        expect(page.locator(".asst-typing-row")).to_have_count(0)
        expect(page.locator(".asst-send")).to_be_enabled()
        error.get_by_role("button", name="Try again").click()
        expect(error).to_contain_text("Babel is busy with other plans. Try again in a few seconds.")
        expect(error).to_contain_text("Request ID req-503")
        error.get_by_role("button", name="Try again").click()
        expect(page.locator(".asst-text")).to_have_text("Here you are.")
        expect(page.locator(".asst-msg.is-user")).to_have_count(1)  # the question is not repeated
        assert len(stub.bodies) == 3 and all(b["messages"] == [{"role": "user", "text": "Why Russian?"}]
                                             for b in stub.bodies)
        assert s.errors == []


def test_a_failed_message_is_left_out_when_a_new_one_is_sent(browser):
    with Site(browser) as s:
        page = s.page
        stub = Stub(s, (500, {}, {"error": "internal", "message": "Something broke.", "request_id": "req-500"}),
                    reply("Fine.", sources=()))
        open_panel(page)
        ask(page, "First try")
        expect(page.locator(".asst-msg.is-error")).to_contain_text("Something broke.")
        ask(page, "Second try")
        expect(page.locator(".asst-text")).to_have_text("Fine.")
        expect(page.locator(".asst-msg.is-error")).to_contain_text("Not sent.")
        expect(page.locator(".asst-retry")).to_have_count(0)
        assert stub.bodies[1]["messages"] == [{"role": "user", "text": "Second try"}]
        assert s.errors == []


# ---------------------------------------------------------------- phones and the keyboard
def test_the_phone_sheet_fits_without_sideways_scroll_and_steps_aside_for_actions(browser):
    with Site(browser, viewport=(390, 844)) as s:
        page = s.page
        long = "https://store.steampowered.com/app/3146520/WEBFISHING/" * 4
        Stub(s, reply(f"A long answer: {long}", sources=[f"lookalike:{'9' * 60}", "lang:russian"]),
             reply("Japan is on the map.", sources=(), actions=[
                 {"type": "show_country", "country": "JP", "label": "Show Japan on the map"}]))
        assert page.evaluate(NO_OVERFLOW)
        open_panel(page)
        assert settled_box(panel(page)) == {"x": 0, "y": 0, "width": 390, "height": 844}  # a full-screen sheet
        assert page.locator("main").evaluate("el => el.inert") is True
        ask(page, "Tell me everything")
        expect(page.locator(".asst-text")).to_contain_text("A long answer")
        assert page.evaluate(NO_OVERFLOW)
        assert page.locator(".asst-scroll").evaluate("el => el.scrollWidth <= el.clientWidth")
        page.keyboard.press("Escape")
        expect(panel(page)).to_be_hidden()
        assert page.locator("main").evaluate("el => el.inert") is False

        s.find()  # plan a game on the phone, then act on it
        page.get_by_role("button", name="Run the plan").click()
        expect(page.locator("#map-canvas")).to_have_attribute("data-state", "ready")
        open_panel(page)
        ask(page, "Show Japan on the map")
        expect(panel(page)).to_be_hidden()  # the sheet stepped aside: the change is in view
        peek = page.locator(".asst-peek")
        expect(receipts(peek)).to_have_text(["✓ Show Japan on the map"])
        expect(page.locator("#panel-title")).to_have_text("Japan")
        expect(page.get_by_role("button", name="Open the chat")).to_be_focused()
        assert page.evaluate(NO_OVERFLOW)
        page.get_by_role("button", name="Dismiss").click()
        expect(peek).to_be_hidden()
        expect(launcher(page)).to_be_focused()

        # the launcher never sits on the map's zoom buttons: scrolled over them, it fades out of the way
        page.evaluate("""() => {
          const b = document.querySelector('#map-reset').getBoundingClientRect();
          const l = document.querySelector('#assistant-launcher').getBoundingClientRect();
          window.scrollBy(0, b.top - l.top);
        }""")
        expect(page.locator("#assistant-launcher")).to_have_class(re.compile("is-dodging"))
        page.evaluate("document.activeElement.blur()")
        expect(page.locator("#assistant-launcher")).to_have_css("opacity", "0")
        page.evaluate("window.scrollTo(0, 0)")
        expect(page.locator("#assistant-launcher")).not_to_have_class(re.compile("is-dodging"))
        assert s.errors == []


def test_keyboard_only_open_type_send_and_close(browser):
    with Site(browser) as s:
        page = s.page
        stub = Stub(s, reply("Hi! Ask me about your plan.", sources=()))
        launcher(page).focus()
        page.keyboard.press("Enter")
        expect(page.locator("#assistant-input")).to_be_focused()
        outline = page.locator(".asst-compose").evaluate("el => getComputedStyle(el).outlineStyle")
        assert outline == "solid"  # focus is visible on the composer
        page.keyboard.type("Hello")
        page.keyboard.press("Shift+Enter")
        page.keyboard.type("there")
        expect(page.locator("#assistant-input")).to_have_value("Hello\nthere")
        page.keyboard.press("Enter")
        expect(page.locator(".asst-text")).to_have_text("Hi! Ask me about your plan.")
        assert stub.bodies[0]["messages"] == [{"role": "user", "text": "Hello\nthere"}]
        expect(page.locator("#assistant-input")).to_have_value("")
        expect(page.locator("#assistant-input")).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.get_by_role("button", name="Send")).to_be_focused()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Shift+Tab")  # the suggestions sit just before the field
        expect(page.locator(".asst-chip").last).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator(".asst-text")).to_have_count(2)
        assert stub.bodies[1]["messages"][-1] == {"role": "user", "text": "Take the tour"}
        page.keyboard.press("Escape")
        expect(panel(page)).to_be_hidden()
        expect(launcher(page)).to_be_focused()
        assert s.errors == []


def test_the_dark_theme_keeps_the_launcher_and_every_message_readable(browser):
    """The system's dark setting: the launcher turns light (it stays the ink colour) with its mark readable on it;
    the panel is dark and every label, answer, receipt and error in it has WCAG AA text."""
    with Site(browser, color_scheme="dark") as s:
        page = s.page
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        css = lambda sel, prop: page.locator(sel).first.evaluate(f"e => getComputedStyle(e).{prop}")  # noqa: E731
        disc = css("#assistant-launcher", "backgroundColor")
        assert luminance(disc) > 0.7
        assert page.locator("#assistant-launcher .asst-mark").evaluate("e => e.naturalWidth") > 0  # the logo image
        assert contrast(css(".asst-ai", "color"), css(".asst-ai", "backgroundColor")) >= 4.5
        Stub(s, reply("I'll change the budget, then show Japan.", actions=[
            {"type": "set_budget", "budget": 5000, "label": "Set the budget to $5,000"},
            {"type": "show_country", "country": "JP", "label": "Show Japan on the map"}],
            dropped=[{"type": "open_why", "reason": "No plan is open yet."}]),
            reply("Here is the track record.", checked=False, sources=(),
                  actions=[{"type": "open_track_record", "label": "Open the track record"}]),
            reply(REPLACED, kind="fallback", checked=False, sources=("product:limits",)), "abort")
        open_panel(page)
        assert luminance(css("#assistant-panel", "backgroundColor")) < 0.02
        for question in ("Set the budget to $5,000 and show Japan", "Open the track record", "Japan's revenue?", "Hi"):
            ask(page, question)
            expect(page.locator(".asst-send")).to_be_enabled()
        for cls in ("is-failed", "is-skipped", "is-dropped", "is-ok"):
            expect(page.locator(f".asst-receipt.{cls}").first).to_be_visible()
        for cls in ("is-checked", "is-unchecked", "is-fallback", "is-error"):
            expect(page.locator(f".asst-msg.{cls}").first).to_be_attached()
        assert css(".asst-bubble", "backgroundColor") == "rgb(237, 237, 237)"  # the accent: near-white, black text
        assert css(".asst-bubble", "color") == "rgb(10, 10, 10)"
        assert page.evaluate(LOW_CONTRAST, "#assistant-panel") == []
        assert s.errors == []


def test_the_why_calculation_says_how_to_get_back_to_the_chat(browser):
    """open_why opens a modal dialog, which blocks the page and the docked panel: the chat says so until it closes."""
    with Site(browser) as s:
        page = s.plan()
        why = {"type": "open_why", "language": "russian", "label": "Why Russian? Open the calculation"}
        Stub(s, reply(actions=[why]))
        open_panel(page)
        ask(page, "Why Russian?")
        expect(page.locator("#why-dialog")).to_be_visible()
        note = page.locator("#assistant-root .asst-receipt.is-info")
        expect(note).to_contain_text("close it (Esc) to keep chatting")
        page.keyboard.press("Escape")
        expect(page.locator("#why-dialog")).to_be_hidden()
        expect(note).to_have_count(0)
        expect(page.locator("#assistant-input")).to_be_focused()
        assert s.errors == []
