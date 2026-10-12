"""The web API: every endpoint, invalid requests, upstream failures, rate limits, streaming and disconnects.

Fake agents (functions with the agent's signature) keep these fast; one test runs the real agent through the API."""
import asyncio
import json
import time
import typing

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from babel import agent, api, net, qloo
from babel import plan as P
from babel.languages import GENERIC

# Fake keys, built at run time so the source holds nothing shaped like a credential (tools/check_secrets.py)
SECRETS = {"QLOO_API_KEY": "hack_" + "fake" * 8, "ANTHROPIC_API_KEY": "-".join(["sk", "ant", "fake", "testvalue"])}
GAME = {"appid": 3146520, "word_count": 30_000, "budget": 10_000}


def event(seq, type_, step, status="ok", message=None, /, **data):
    return {"v": 1, "seq": seq, "type": type_, "step": step, "status": status, "message": message or f"{type_}:{step}",
            "data": data}


class FakeAgent:
    """Emits a few events through the sink and returns a result like babel.agent.run."""

    def __init__(self, status="ok", delay=0.0, crash=None, steps=3):
        self.status, self.delay, self.crash, self.steps, self.calls, self.emitted = status, delay, crash, steps, [], 0

    def __call__(self, kwargs, ctx, sink):
        self.calls.append(kwargs)
        events = [event(1, "plan", "goal", "info")]
        sink(events[-1])
        for i in range(2, self.steps):
            time.sleep(self.delay)
            events.append(event(i, "act", "score", message=f"step {i}"))
            sink(events[-1])
            self.emitted = i
        if self.crash:
            raise self.crash
        if self.status == "partial":
            events.append(event(len(events) + 1, "error", "markets", "failed", "A request failed after 3 attempts."))
            sink(events[-1])
        result = {"plan": {"budget": kwargs["budget"], "appid": kwargs["appid"]}, "policy": dict(net.policy.get())}
        events.append(event(len(events) + 1, "done", "result", "ok" if self.status == "ok" else "warning",
                            status=self.status, result=result))
        sink(events[-1])
        return {"status": self.status, "result": result, "events": events}


def make(fake=None, warmup=True, loader=lambda: "CTX", **settings):
    app = api.create_app(api.Settings(warmup=warmup, **settings), runner=fake or FakeAgent(), loader=loader)
    return app, app.state.babel


@pytest.fixture
def secrets(monkeypatch):
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)


def client(app):
    c = TestClient(app, raise_server_exceptions=False)
    c.__enter__()
    app.state.babel.ready.wait(2)
    return c


def sse(text):
    """[(event name, payload)] from an SSE body (comments skipped)."""
    out = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if fields:
            out.append((fields["event"], json.loads(fields["data"])))
    return out


# ---------------------------------------------------------------- health and readiness
def test_health_answers_without_loading_any_data():
    app, state = make(warmup=False)
    c = client(app)
    assert c.get("/health").json()["status"] == "ok"
    r = c.get("/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["runtime_data"] == "not loaded"


def test_ready_after_warm_up_and_no_secrets_anywhere(secrets):
    app, _ = make()
    c = client(app)
    r = c.get("/health/ready")
    assert r.status_code == 200 and r.json()["ready"]
    assert r.json()["checks"]["qloo_key_configured"] is True
    bodies = [r.text, c.get("/health").text, c.post("/plan", json=GAME).text, c.get("/openapi.json").text,
              c.post("/plan", json={"word_count": 1}).text]
    assert not any(secret in body for body in bodies for secret in SECRETS.values())


def test_a_failed_warm_up_is_reported_without_details():
    def broken():
        raise ValueError("C:/secret/path is missing")
    app, _ = make(loader=broken)
    c = client(app)
    time.sleep(0.2)
    r = c.get("/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["runtime_data"] == "failed (ValueError)"
    assert "secret" not in r.text


# ---------------------------------------------------------------- streaming a plan
def test_a_plan_streams_events_then_the_result():
    app, _ = make()
    r = client(app).post("/plan", json=GAME)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-babel-cache"] == "miss" and r.headers["x-request-id"]
    events = sse(r.text)
    assert [name for name, _ in events] == ["meta", "plan", "act", "done", "result"]
    assert all(api.Event.model_validate(e) for name, e in events if name not in ("meta", "result"))
    assert "result" not in events[3][1]["data"]  # the full result comes once, in the result event
    assert events[-1][1]["result"]["plan"] == {"budget": 10000.0, "appid": 3146520}


def test_identical_requests_come_from_the_plan_cache():
    fake = FakeAgent()
    app, _ = make(fake)
    c = client(app)
    first, second = c.post("/plan", json=GAME), c.post("/plan", json=GAME)
    assert second.headers["x-babel-cache"] == "hit" and len(fake.calls) == 1
    assert sse(first.text)[-1][1]["result"] == sse(second.text)[-1][1]["result"]
    plan_id = sse(first.text)[0][1]["plan_id"]
    saved = c.get(f"/plans/{plan_id}")
    assert saved.status_code == 200 and saved.json()["cached"] and saved.json()["status"] == "ok"
    assert c.post("/plan", json={**GAME, "budget": 9_999}).headers["x-babel-cache"] == "miss"


def test_json_mode_returns_one_validated_object():
    app, _ = make()
    r = client(app).post("/plan?stream=false", json=GAME)
    body = api.PlanResponse.model_validate(r.json())
    assert r.status_code == 200 and body.status == "ok" and [e.type for e in body.events] == ["plan", "act", "done"]


def test_a_steam_url_becomes_an_app_id():
    fake = FakeAgent()
    app, _ = make(fake)
    client(app).post("/plan", json={"steam_url": "https://store.steampowered.com/app/3146520/WEBFISHING/",
                                    "word_count": 30_000, "budget": 10_000})
    assert fake.calls[0]["appid"] == 3146520


def test_the_short_upstream_retry_policy_applies_inside_the_plan():
    app, _ = make(upstream_attempts=2, upstream_max_wait=1.5, upstream_timeout=9)
    r = client(app).post("/plan?stream=false", json=GAME)
    assert r.json()["result"]["policy"] == {"attempts": 2, "max_wait": 1.5, "timeout": 9}
    assert net.policy.get()["attempts"] == net.ATTEMPTS  # scripts keep the patient default


# ---------------------------------------------------------------- invalid requests
@pytest.mark.parametrize("body, field", [
    ({"appid": 1, "budget": 10}, "word_count"),
    ({**GAME, "budget": -1}, "budget"),
    ({**GAME, "budget": True}, "budget"),
    ({**GAME, "word_count": 1.5}, "word_count"),
    ({**GAME, "word_count": "30000"}, "word_count"),
    ({"word_count": 10, "budget": 10}, "body"),
    ({**GAME, "steam_url": "https://store.steampowered.com/app/999/"}, "body"),
    ({"steam_url": "https://evil.example/app/1/", "word_count": 10, "budget": 10}, "body"),
    ({**GAME, "name": "WEBFISHING"}, "body"),
    ({**GAME, "surprise": 1}, "surprise"),
    ({"description": "short", "word_count": 10, "budget": 10}, "body"),
    ({**GAME, "lookalikes": list(range(1, 12))}, "lookalikes"),
    ({**GAME, "lookalikes": [-3]}, "body"),
])
def test_invalid_requests_are_rejected_cleanly(body, field):
    fake = FakeAgent()
    app, _ = make(fake)
    r = client(app).post("/plan", json=body)
    assert r.status_code == 422 and r.json()["error"] == "invalid_request" and r.json()["request_id"]
    assert field in [d["field"] for d in r.json()["details"]]
    assert "Traceback" not in r.text and fake.calls == []


def test_a_malformed_json_body_is_rejected():
    app, _ = make()
    r = client(app).post("/plan", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"


def test_request_bodies_are_size_limited():
    app, _ = make(max_body_bytes=500)
    c = client(app)
    big = {**GAME, "appid": None, "description": "x" * 1000}
    assert c.post("/plan", json=big).status_code == 413
    chunked = c.post("/plan", content=(b"x" * 100 for _ in range(10)), headers={"Content-Type": "application/json"})
    assert chunked.status_code == 413 and chunked.json()["error"] == "too_large"


# ---------------------------------------------------------------- limits and readiness
def test_rate_limits_answer_429_with_retry_after():
    app, _ = make(plan_rate=(2, 60), read_rate=(3, 60))
    c = client(app)
    codes = [c.post("/plan", json={**GAME, "budget": b}).status_code for b in (1, 2, 3)]
    assert codes == [200, 200, 429]
    limited = c.post("/plan", json=GAME)
    assert limited.json()["error"] == "rate_limited" and int(limited.headers["retry-after"]) >= 1
    assert [c.get("/track-record?games=false").status_code for _ in range(4)] == [200, 200, 200, 429]
    assert all(c.get("/health").status_code == 200 for _ in range(10))  # health is never limited


def test_plans_wait_for_readiness():
    app, _ = make(warmup=False)
    r = client(app).post("/plan", json=GAME)
    assert r.status_code == 503 and r.json()["error"] == "not_ready" and r.headers["retry-after"]


def test_too_many_running_plans_answers_busy():
    app, _ = make(max_concurrent=0)
    r = client(app).post("/plan", json=GAME)
    assert r.status_code == 503 and r.json()["error"] == "busy"


def test_cors_follows_the_configured_origins():
    app, _ = make(cors_origins=("https://babel.example",))
    c = client(app)
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    ok = c.options("/plan", headers={"Origin": "https://babel.example", **preflight})
    bad = c.options("/plan", headers={"Origin": "https://evil.example", **preflight})
    assert ok.headers.get("access-control-allow-origin") == "https://babel.example"
    assert "access-control-allow-origin" not in bad.headers
    default = client(make()[0]).get("/health", headers={"Origin": "https://babel.example"})
    assert "access-control-allow-origin" not in default.headers


# ---------------------------------------------------------------- upstream failures, crashes, timeouts
def test_upstream_failures_are_streamed_and_not_cached():
    fake = FakeAgent(status="partial")
    app, _ = make(fake)
    c = client(app)
    events = sse(c.post("/plan", json=GAME).text)
    assert any(name == "error" and "failed after 3 attempts" in e["message"] for name, e in events)
    assert events[-1][1]["status"] == "partial"
    assert c.post("/plan", json=GAME).headers["x-babel-cache"] == "miss" and len(fake.calls) == 2


def test_an_agent_crash_gives_a_generic_error_without_internals():
    app, _ = make(FakeAgent(crash=ValueError("secret detail C:/babel/cache/qloo")))
    c = client(app)
    streamed = c.post("/plan", json=GAME)
    name, err = sse(streamed.text)[-1]
    assert name == "error" and err["data"]["request_id"] and "could not be finished" in err["message"]
    as_json = c.post("/plan?stream=false", json={**GAME, "budget": 1})
    assert as_json.status_code == 500 and as_json.json()["error"] == "internal_error"
    assert not any(s in r.text for r in (streamed, as_json) for s in ("secret detail", "Traceback", "cache/qloo"))


def test_a_slow_plan_times_out():
    app, _ = make(FakeAgent(delay=0.5, steps=6), plan_timeout=0.3)
    c = client(app)
    name, err = sse(c.post("/plan", json=GAME).text)[-1]
    assert name == "error" and "took longer than" in err["message"]
    assert c.post("/plan?stream=false", json={**GAME, "budget": 1}).status_code == 504


def test_a_client_disconnect_stops_the_agent():
    fake = FakeAgent(delay=0.05, steps=60)
    app, state = make(fake, warmup=False)
    state.ctx = "CTX"
    state.ready.set()
    body = json.dumps(GAME).encode()
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/plan", "raw_path": b"/plan", "query_string": b"", "root_path": "", "server": ("test", 80),
             "client": ("127.0.0.1", 1234), "headers": [(b"content-type", b"application/json"),
                                                        (b"content-length", str(len(body)).encode())]}

    async def scenario():
        chunks, gone = [], asyncio.Event()
        sent = iter([{"type": "http.request", "body": body, "more_body": False}])

        async def receive():
            msg = next(sent, None)
            if msg:
                return msg
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                chunks.append(message["body"])
                if len(chunks) == 3:
                    gone.set()  # the browser tab closes after a few events
        await asyncio.wait_for(app(scope, receive, send), 5)
        return chunks
    asyncio.run(scenario())
    time.sleep(0.3)
    assert fake.emitted < 20 and state.active == 0  # stopped early and released its slot


# ---------------------------------------------------------------- other endpoints and errors
def test_track_record_serves_the_published_numbers():
    c = client(make()[0])
    r = c.get("/track-record").json()
    steam, wiki = r["truths"]["steam_reviews"], r["truths"]["wikipedia_pageviews"]
    assert f"{steam['babel_vs_typical_mix']['babel_top3_coverage']:.1%}" == "48.9%"
    assert (wiki["babel_vs_typical_mix"]["better"], wiki["babel_vs_typical_mix"]["worse"]) == (87, 33)
    assert len(steam["games"]) == 71 and len(wiki["games"]) == 186 and len(steam["source"]["sha256"]) == 64
    assert "Exploratory" in r["exploratory"]["label"]
    assert "games" not in c.get("/track-record?games=false").json()["truths"]["steam_reviews"]


# ---------------------------------------------------------------- the Plan screen's budget slider
def fit_body(budget=20_000):
    from synthetic import result
    return {"budget": budget, "allocation": result()["plan"]["allocation"]}


def test_fit_budget_reruns_the_engines_optimizer_without_waiting_for_data():
    app, _ = make(warmup=False)  # pure computation: no runtime data needed
    body = fit_body()
    r = client(app).post("/fit-budget", json=body)
    a = body["allocation"]
    assert r.status_code == 200
    assert r.json() == P.fit_budget(a["shares"], a["cost_full"], a["cost_store_page"], 20_000, a["min_share"],
                                    a["supported"])
    assert r.json()["costs"]["total"] <= 20_000


@pytest.mark.parametrize("change, field", [
    (lambda b: b["allocation"]["shares"].pop("thai"), "shares must give exactly the 14 target languages"),
    (lambda b: b["allocation"]["cost_full"].update(russian=0), "allocation.cost_full.russian"),
    (lambda b: b.update(budget=-1), "budget"), (lambda b: b.update(budget="10000"), "budget"),
    (lambda b: b.update(extra=1), "extra"), (lambda b: b["allocation"].update(supported=["klingon"]), "supported"),
])
def test_fit_budget_rejects_a_bad_allocation(change, field):
    app, _ = make()
    body = fit_body()
    change(body)
    r = client(app).post("/fit-budget", json=body)
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"
    assert field in json.dumps(r.json()["details"])


def test_fit_budget_has_its_own_rate_limit():
    app, _ = make(compute_rate=(2, 60), read_rate=(5, 60))
    c = client(app)
    assert [c.post("/fit-budget", json=fit_body(b)).status_code for b in (1, 2, 3)] == [200, 200, 429]
    assert c.get("/track-record?games=false").status_code == 200


def test_unknown_routes_plans_and_methods_answer_json_errors():
    c = client(make()[0])
    assert c.get("/nope").json()["error"] == "not_found"
    assert c.get("/plans/0123456789abcdef").status_code == 404 and c.get("/plans/..%2Fsecret").status_code == 404
    assert c.get("/plan").json()["error"] == "method_not_allowed"


def test_settings_come_from_the_environment():
    s = api.Settings.from_env({"BABEL_CORS_ORIGINS": "https://a.example, https://b.example", "BABEL_PLAN_RATE": "5/30",
                               "BABEL_PLAN_TIMEOUT": "45", "BABEL_TRUST_PROXY": "1", "BABEL_WARMUP": "0"})
    assert s.cors_origins == ("https://a.example", "https://b.example") and s.plan_rate == (5, 30.0)
    assert s.plan_timeout == 45.0 and s.trust_proxy and not s.warmup
    assert api.Settings.from_env({}) == api.Settings()


def test_the_event_schema_matches_the_agent():
    fields = api.Event.model_fields
    assert typing.get_args(fields["type"].annotation) == agent.EVENT_TYPES
    assert typing.get_args(fields["step"].annotation) == agent.STEPS
    assert typing.get_args(fields["status"].annotation) == agent.STATUSES


# ---------------------------------------------------------------- the real agent through the API
def test_the_real_agent_streams_through_the_api(monkeypatch):
    prior = pd.Series({l: 14 - i for i, l in enumerate(GENERIC)}, dtype=float)
    ctx = type("Ctx", (), {"prior": prior, "base": (pd.Series(0.5, index=GENERIC), 3), "default_map": "D",
                           "picker": None})()
    monkeypatch.setattr(P, "user_lookalike", lambda appid, default_map: {
        "appid": appid, "name": f"Game {appid}", "qloo_id": f"Q{appid}", "status": "valid", "overlap": None})
    monkeypatch.setattr(P, "comp_affinity", lambda name, qloo_id: {"RU": 0.4, "BR": 0.9, "JP": 0.7})
    monkeypatch.setattr(qloo, "game_profile", lambda name, qloo_id: {"affinity": {"RU": 0.4, "BR": 0.9, "JP": 0.7}})
    app = api.create_app(api.Settings(warmup=True), loader=lambda: ctx)
    events = sse(client(app).post("/plan", json={"lookalikes": [11, 12, 13], "word_count": 30_000, "budget": 10_000,
                                                 "markets": False, "explain": False}).text)
    for name, e in events[1:-1]:
        api.Event.model_validate(e)
    done = [e for name, e in events if name == "done"][0]
    assert done["data"]["status"] == "ok" and events[-1][0] == "result"
    plan = events[-1][1]["result"]["plan"]
    assert plan["status"] == "ok" and len(plan["lookalikes"]["used"]) == 3 and plan["costs"]["total"] <= 10_000
