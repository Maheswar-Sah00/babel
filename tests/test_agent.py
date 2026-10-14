"""The agent: event schema, success, retries, failures, recovery and grounded explanations.

Synthetic pool and fake APIs (Qloo over a fake HTTP layer, Claude as a function): no network, temporary cache."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from babel import agent, comps, describe, explain, explore, llm, markets, net, qloo
from babel import plan as P
from babel.languages import COUNTRY_NAME, GENERIC

PRIOR = pd.Series({l: 14 - i for i, l in enumerate(GENERIC)}, dtype=float)
BASE = pd.Series(0.5, index=GENERIC)
AFFINITY = {"RU": 0.4, "BR": 0.9, "DE": 0.5, "CN": 0.6, "JP": 0.7}
# Games 1-8 share 'Alpha' with overlap falling as i grows; only 1, 7 and 8 have real Qloo maps (the widening case).
# Games 11-13 share 'Cozy' and all have real maps (the normal case). Game 14 has only a default map.
POOL = {**{i: (f"Alpha {i}", {"Alpha": 100, f"Pad{i}": 10 * i}) for i in range(1, 9)},
        11: ("Cozy One", {"Cozy": 100, "Farming Sim": 80}), 12: ("Cozy Two", {"Cozy": 90, "Life Sim": 60}),
        13: ("Cozy Three", {"Cozy": 80, "Relaxing": 50}), 14: ("Gloomy", {"Horror": 100, "Space": 40}),
        15: ("Racer", {"Racing": 100})}
INVALID = {2: "default map", 3: "default map", 4: "not in Qloo", 5: "default map", 6: "default map",
           14: "default map"}
COZY = ["Cozy", "Farming Sim", "Life Sim"]


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.headers, self.text = status, body, {}, json.dumps(body)

    def json(self):
        return self._body


class FakeQlooHTTP:
    """Answers Qloo /v2/insights over the fake HTTP layer used by babel.net; `fail(params, n)` forces a 503."""

    def __init__(self, fail=lambda params, n: False, empty=()):
        self.fail, self.empty, self.calls = fail, set(empty), 0

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        if self.fail(params, self.calls):
            return Resp(503, {"error": "busy"})
        if params["filter.type"] == "urn:demographics":
            return Resp(200, {"results": {"demographics": [{"query": {"age": {"25_to_29": 0.7}, "gender": {}}}]}})
        country, kind = params.get("signal.location.query"), params["filter.type"].split(":")[-1]
        if "filter.results.entities" not in params:
            n = 0 if country in self.empty else 4
            return Resp(200, {"results": {"entities": [
                {"entity_id": f"{country}-{kind}-{i}", "name": f"{country} {kind} {i}"} for i in range(n)]}})
        pool = params["filter.results.entities"].split(",")
        return Resp(200, {"results": {"entities": [
            {"entity_id": e, "name": e, "query": {"affinity": 0.8}} for e in pool]}})


def fake_claude(prompt, schema):
    """A well-behaved Claude: explanations that quote the evidence exactly; description tags from the pool."""
    if schema is explain.SCHEMA:
        idx = json.loads(prompt.split("Evidence: ", 1)[1])
        return {"summary": f"The plan spends {idx['costs']['total']} of {idx['plan']['budget']}.",
                "points": [{"text": f"Total cost {idx['costs']['total']}, an estimate.", "evidence": ["costs"]},
                           {"text": "Shares are estimates, not sales.", "evidence": ["caveat:1"]}]}
    if schema is describe.SCHEMA:
        return {"tags": COZY, "lookalikes": [{"name": "Cozy One", "reason": "Cozy."}], "genre_clarity": "clear",
                "genres": ["Cozy"]}
    pytest.fail(f"unexpected Claude call with schema {schema}")


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A synthetic context; Qloo answered by FakeQlooHTTP through the real babel.net retry loop; no sleeping."""
    status = {a: (INVALID.get(a, "valid"), None if INVALID.get(a) == "not in Qloo" else f"Q{a}") for a in POOL}
    picker = comps.CompPicker.from_tags({a: n for a, (n, _) in POOL.items()}, {a: t for a, (_, t) in POOL.items()},
                                        "DEFAULT", status)
    http = FakeQlooHTTP()
    monkeypatch.setenv("QLOO_API_KEY", "test-key")
    monkeypatch.setattr(qloo, "CACHE", tmp_path)
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: http(*a, **k))
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    monkeypatch.setattr(P, "comp_affinity", lambda name, qloo_id: AFFINITY)
    monkeypatch.setattr(qloo, "game_profile", lambda name, qloo_id: {"affinity": AFFINITY, "mass": {"ES": 2, "MX": 1}})
    monkeypatch.setattr(llm, "ask_claude_json", fake_claude)
    return SimpleNamespace(ctx=SimpleNamespace(picker=picker, prior=PRIOR, base=(BASE, 3), default_map="DEFAULT"),
                           http=http, picker=picker)


def run(env, **kw):
    return agent.run(kw.pop("word_count", 30_000), kw.pop("budget", 10_000), ctx=env.ctx, **kw)


def events(out, type_=None, step=None, status=None):
    return [e for e in out["events"] if (type_ is None or e["type"] == type_) and (step is None or e["step"] == step)
            and (status is None or e["status"] == status)]


# ---------------------------------------------------------------- success and the event schema
def test_a_complete_trace_with_a_stable_schema(env):
    out = run(env, tags=COZY)
    assert out["status"] == "ok"
    for i, e in enumerate(out["events"], 1):
        assert set(e) == {"v", "seq", "type", "step", "status", "message", "data"} and e["seq"] == i
        assert e["type"] in agent.EVENT_TYPES and e["step"] in agent.STEPS and e["status"] in agent.STATUSES
    json.dumps(out["events"], allow_nan=False)
    assert out["events"][0]["type"] == "plan" and out["events"][-1]["type"] == "done"
    steps = list(dict.fromkeys(e["step"] for e in out["events"]))
    assert steps == ["goal", "game", "tags", "lookalikes", "fan_maps", "score", "optimize", "markets", "explain",
                     "verify", "result"]
    assert all(e["status"] == "ok" for e in events(out, "verify", "verify"))
    assert out["result"]["explanation"]["kind"] == "llm_text"


def test_the_result_carries_the_plan_screens_data_and_verifies_it(env):
    out = run(env, tags=COZY)
    screen, p = out["result"]["explore"], out["result"]["plan"]
    assert screen["map"]["status"] == "ok" and [x["appid"] for x in screen["map"]["lookalikes"] if x["usable"]] == [
        x["appid"] for x in p["lookalikes"]["used"]]
    assert screen["map"]["countries"]["BR"]["affinity"] == AFFINITY["BR"]
    assert len(screen["versus_generic"]["rows"]) == 14 and set(screen["costs"]) == set(P.LANGS)
    world = events(out, "act", "fan_maps")[-1]
    assert world["message"] == "World map: Qloo has fan data for 5 countries, from 3 games like yours."
    assert "popularity-weighted mean affinity" in world["data"]["detail"]  # the method, one click away
    check = [e for e in events(out, "verify", "verify") if e["message"].startswith("World map:")]
    assert len(check) == 1 and check[0]["status"] == "ok"


def test_a_failed_map_is_reported_and_the_plan_still_stands(env, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("boom")
    monkeypatch.setattr(explore, "map_data", broken)
    out = run(env, tags=COZY)
    assert out["status"] == "partial" and out["result"]["explore"]["map"] is None
    failed = events(out, "error", "fan_maps", "failed")
    assert len(failed) == 1 and "the plan itself is unaffected" in failed[0]["message"]
    assert out["result"]["plan"] == P.plan(30_000, 10_000, tags=COZY, ctx=env.ctx)


def test_the_agent_never_changes_the_engines_numbers(env):
    out = run(env, tags=COZY)
    assert out["result"]["plan"] == P.plan(30_000, 10_000, tags=COZY, ctx=env.ctx)


def test_repeated_runs_are_identical(env):
    first, second = run(env, tags=COZY), run(env, tags=COZY)
    assert first["result"] == second["result"] and first["events"] == second["events"]


def test_events_stream_to_the_sink_as_they_happen(env):
    seen = []
    out = run(env, tags=COZY, sink=seen.append)
    assert seen == out["events"]


# ---------------------------------------------------------------- retries and failed requests
def test_a_retried_request_is_traced_and_recovers(env):
    env.http.fail = lambda params, n: params["filter.type"] == "urn:demographics" and n == 1
    out = run(env, tags=COZY)
    retries = [e for e in events(out, "reflect", "markets") if "HTTP 503" in e["message"]]
    assert len(retries) == 1 and "retrying" in retries[0]["message"]
    assert out["status"] == "ok" and out["result"]["market_notes"]["audience"]["status"] == "ok"


def test_a_request_that_keeps_failing_is_reported_never_hidden(env):
    env.http.fail = lambda params, n: True
    out = run(env, tags=COZY)
    assert out["status"] == "partial"
    retries = [e for e in out["events"] if "HTTP 503" in e["message"]]
    assert len(retries) == net.ATTEMPTS and "giving up" in retries[-1]["message"]
    (error,) = events(out, "error")
    assert error["step"] == "markets" and f"failed after {net.ATTEMPTS} attempts" in error["message"]
    assert out["result"]["market_notes"] is None and out["result"]["plan"]["status"] == "ok"
    assert any("1 failed request" in e["message"] for e in events(out, "verify"))


def test_qloo_failing_during_the_lookalike_check_falls_back_with_disclosure(env, monkeypatch):
    for appid in (11, 12, 13):
        del env.picker.status[appid]  # not checked yet: the agent must ask Qloo
    env.http.fail = lambda params, n: True
    monkeypatch.setattr(qloo, "find_game", lambda name: qloo.fetch(f"search_{qloo.slug(name)}", "/search",
                                                                   {"query": name}) and (None, 200))
    out = run(env, tags=COZY)
    assert out["status"] == "partial" and events(out, "error", "lookalikes")
    p = out["result"]["plan"]
    assert p["lookalikes"]["evidence_level"] == "none" and all(x["qloo_lift"] == 1 for x in p["languages"])
    assert any("request failed after retries" in m for m in p["messages"])
    assert any("skipped" in e["message"] for e in events(out, "reflect", "markets"))


# ---------------------------------------------------------------- reflection and recovery
def test_too_few_lookalikes_widens_the_search(env):
    out = run(env, tags=["Alpha"])
    widened = [e for e in events(out, "reflect", "lookalikes") if "wider search" in e["message"]]
    assert len(widened) == 1 and "track record doesn't cover" in widened[0]["message"]  # disclosed, not hidden
    assert "backtest did not cover" in widened[0]["data"]["detail"]
    p = out["result"]["plan"]
    assert p["lookalikes"]["widened_search"] and len(p["lookalikes"]["used"]) == 3
    assert any("Qloo has no real fan data for it, so it isn't used" in e["message"] and e["data"]["status"] ==
               "default map" for e in events(out, "reflect", "lookalikes"))


def test_no_usable_lookalikes_falls_back_to_the_typical_mix_and_asks_the_user(env):
    out = run(env, tags=["Horror", "Space"])
    assert events(out, "reflect", "lookalikes", "needs_input")
    p = out["result"]["plan"]
    assert p["lookalikes"]["evidence_level"] == "none" and all(x["qloo_lift"] == 1 for x in p["languages"])
    assert any("typical language mix" in m for m in p["messages"])
    assert "unavailable" in out["result"]["evidence_index"]["audience"]


def test_sparse_tags_are_recovered_from_the_store_description(env, monkeypatch):
    monkeypatch.setattr(P, "game_info", lambda appid: {
        "appid": appid, "name": "Sparse Game", "release_date": None, "supported": ["german"], "tags": {"Indie": 5},
        "source": "steam", "description": "A cozy farming life sim about a small village and its seasons."})
    out = run(env, appid=999)
    assert any("only 1 tag" in e["message"] for e in events(out, "reflect", "tags"))
    p = out["result"]["plan"]
    assert p["discovery"]["inferred_tags"] == COZY and p["game"]["supported_languages"] == ["german"]
    assert any("inferred from the store description" in m for m in p["messages"])


def test_a_market_without_qloo_data_is_replaced_by_the_next_one(env):
    first = markets.candidates(P.plan(30_000, 10_000, tags=COZY, ctx=env.ctx))[0]
    country = COUNTRY_NAME[markets.market_country(first, [{"ES": 2, "MX": 1}])[0]]
    env.http.empty = {country}
    out = run(env, tags=COZY)
    assert any(f"No Qloo market data for {country}" in e["message"] for e in events(out, "reflect", "markets"))
    shown = [m["language"] for m in out["result"]["market_notes"]["markets"]]
    assert first not in shown and len(shown) == 3


# ---------------------------------------------------------------- grounded explanations
def test_unsupported_numbers_and_unknown_ids_are_dropped(env, monkeypatch):
    def claude(prompt, schema):
        idx = json.loads(prompt.split("Evidence: ", 1)[1])
        return {"summary": "A plan within the budget.", "points": [
            {"text": f"Total {idx['costs']['total']}.", "evidence": ["costs"]},
            {"text": "Russian has 50.0% of demand.", "evidence": ["lang:russian"]},  # invented number
            {"text": "Trust this.", "evidence": ["made-up-id"]},
            {"text": "No evidence cited."},
            {"text": "Shares are estimates.", "evidence": ["caveat:1"]}]}
    monkeypatch.setattr(llm, "ask_claude_json", claude)
    out = run(env, tags=COZY)
    exp = out["result"]["explanation"]
    assert exp["kind"] == "llm_text" and len(exp["points"]) == 2
    reasons = " ".join(d["reason"] for d in exp["dropped"])
    assert "50.0%" in reasons and "made-up-id" in reasons and "cites no evidence" in reasons
    assert len([e for e in events(out, "verify", "explain") if "Left out of the explanation" in e["message"]]) == 3


def test_a_failed_or_unavailable_claude_falls_back_to_the_template(env, monkeypatch):
    def broken(prompt, schema):
        raise ConnectionError("no network")
    monkeypatch.setattr(llm, "ask_claude_json", broken)
    out = run(env, tags=COZY)
    exp = out["result"]["explanation"]
    assert exp["kind"] == "template" and "LLM unavailable" in exp["reason"]
    assert events(out, "error", "explain") and out["status"] == "partial"
    idx = out["result"]["evidence_index"]
    assert all(not explain.unsupported(pt["text"], [idx[e] for e in pt["evidence"]]) for pt in exp["points"])


def test_money_and_percentages_are_never_waved_through():
    assert explain.unsupported("only $4 left, 3 games, rank 5", [{"x": "nothing"}]) == ["4"]
    assert explain.unsupported("7% of demand", [{}]) == ["7%"]
    assert explain.unsupported("costs $3,508 (20.2%)", [{"cost": "$3,508", "share": "20.2%"}]) == []


# ---------------------------------------------------------------- invalid input
def test_invalid_input_becomes_an_error_event(env):
    out = run(env, budget=-5, tags=COZY)
    assert out["status"] == "failed" and out["result"] is None
    assert [e["type"] for e in out["events"]] == ["error", "done"] and "negative" in out["events"][0]["message"]
