"""Market notes: caching, missing data and provenance, against a fake Qloo API (no network; temporary cache)."""
import json

import pytest

from babel import llm, markets, net, qloo

POOL_SIZE = 5


class FakeQloo:
    """Answers /v2/insights like Qloo, records every request; special ids and countries trigger failures."""

    def __init__(self):
        self.requests = []

    def __call__(self, url, params=None, headers=None, json_body=None):
        self.requests.append(dict(params))
        if params["filter.type"] == "urn:demographics":
            if "Q-NODEMO" in params["signal.interests.entities"]:
                return 200, {"results": {"demographics": [{"query": None}]}}
            return 200, {"results": {"demographics": [{"query": {
                "age": {"25_to_29": 0.7, "55_and_older": -0.5}, "gender": {"male": -0.1, "female": 0.1}}}]}}
        country, kind = params.get("signal.location.query"), params["filter.type"].split(":")[-1]
        if "filter.results.entities" not in params:  # step 1: the country's pool
            if country == "Errorland":
                return 500, {"error": "boom"}
            n = 0 if country == "Nowhere" else POOL_SIZE
            return 200, {"results": {"entities": [
                {"entity_id": f"{country}-{kind}-{i}", "name": f"{country} {kind} {i}"} for i in range(n)]}}
        pool = params["filter.results.entities"].split(",")
        foreign = [{"entity_id": "FOREIGN-1", "name": "Somewhere else", "query": {"affinity": 0.99}}]
        if "Q-OUTSIDE" in params["signal.interests.entities"]:
            return 200, {"results": {"entities": foreign}}
        ranked = [{"entity_id": e, "name": e, "query": {"affinity": 0.9 - i / 100}}
                  for i, e in enumerate(reversed(pool))]
        return 200, {"results": {"entities": foreign + ranked[:-1]}}  # one outside the pool, one pool entity dropped


@pytest.fixture
def api(monkeypatch, tmp_path):
    fake = FakeQloo()
    monkeypatch.setenv("QLOO_API_KEY", "test-key")  # a fresh clone has no .env; the fake API ignores the key
    monkeypatch.setattr(qloo, "CACHE", tmp_path)
    monkeypatch.setattr(net, "request", fake)
    monkeypatch.setattr(qloo, "game_profile", lambda name, qloo_id: {"affinity": {}, "mass": {"ES": 9.0, "MX": 5.0}})
    monkeypatch.setattr(llm, "ask_claude_json", lambda prompt, schema: pytest.fail("unexpected Claude call"))
    return fake


def plan_stub(used=({"name": "Look-alike", "qloo_id": "Q1"},), full=("russian", "spanish"), store=("german",)):
    groups = {"translate_game": list(full), "store_page_only": list(store), "skip": ["thai"], "already_supported": []}
    langs = [{"code": l, "group": g, "estimated_share": 0.1} for g, ls in groups.items() for l in ls]
    return {"lookalikes": {"used": list(used)}, "groups": groups, "languages": langs}


def kinds_in(obj):
    """Every 'kind' value anywhere in a nested structure."""
    if isinstance(obj, dict):
        return ([obj["kind"]] if "kind" in obj else []) + [k for v in obj.values() for k in kinds_in(v)]
    return [k for v in obj for k in kinds_in(v)] if isinstance(obj, list) else []


# ---------------------------------------------------------------- the two-step query
def test_two_steps_keep_results_in_the_country_pool(api):
    res = markets.also_loved("Spain", "films", ["Q1"])
    assert res["status"] == "ok"
    assert all(i["qloo_id"].startswith("Spain-movie-") for i in res["items"])  # 'Somewhere else' was dropped
    assert res["ranked"] == POOL_SIZE - 1 and res["local_pool_size"] == POOL_SIZE
    step1, step2 = api.requests
    assert step1["signal.location.query"] == "Spain" and "signal.interests.entities" not in step1
    assert "signal.location.query" not in step2  # interests never combined with a location signal
    assert step2["signal.interests.entities"] == "Q1"


def test_lookalike_ids_are_combined_into_one_fans_signal(api):
    markets.also_loved("Spain", "music", ["Q2", "Q1"])
    assert api.requests[1]["signal.interests.entities"] == "Q1,Q2"


# ---------------------------------------------------------------- caching
def test_repeated_queries_come_from_the_cache(api):
    first = markets.also_loved("Spain", "films", ["Q1"])
    hits = net.cache_hits[qloo.HOST]
    second = markets.also_loved("Spain", "films", ["Q1"])
    assert first == second and len(api.requests) == 2  # one pool + one re-rank, never repeated
    assert net.cache_hits[qloo.HOST] == hits + 2


def test_the_country_pool_is_shared_across_games(api):
    markets.also_loved("Spain", "films", ["Q1"])
    markets.also_loved("Spain", "films", ["Q9"])
    assert len(api.requests) == 3  # the Spain pool is fetched once


def test_request_ids_point_to_the_cached_raw_responses(api):
    res = markets.also_loved("Spain", "films", ["Q1"])
    for request in res["requests"]:
        assert json.loads((qloo.CACHE / f"{request}.json").read_text(encoding="utf-8"))["status"] == 200


# ---------------------------------------------------------------- missing data
def test_no_lookalikes_means_explicit_unavailable_messages_and_no_calls(api):
    notes = markets.market_notes(plan_stub(used=()), explain=True)
    assert notes["audience"]["status"] == "unavailable" and "No look-alike" in notes["audience"]["reason"]
    for m in notes["markets"]:
        assert all(r["status"] == "unavailable" and r["reason"] for r in m["also_loves"].values())
        assert m["note"]["status"] == "unavailable" and "No Qloo evidence" in m["note"]["reason"]
    assert api.requests == []


@pytest.mark.parametrize("country, reason", [("Nowhere", "no films popular in Nowhere"), ("Errorland", "HTTP 500")])
def test_an_empty_or_failed_pool_is_reported(api, country, reason):
    res = markets.also_loved(country, "films", ["Q1"])
    assert res["status"] == "unavailable" and reason in res["reason"] and res["items"] == []


def test_results_outside_the_pool_are_never_shown(api):
    res = markets.also_loved("Spain", "films", ["Q-OUTSIDE"])
    assert res["status"] == "unavailable" and "ranked none" in res["reason"]


def test_missing_audience_data_is_reported(api):
    a = markets.audience(["Q-NODEMO"])
    assert a["status"] == "unavailable" and "no audience data" in a["reason"]


# ---------------------------------------------------------------- provenance
def test_every_item_says_what_kind_of_evidence_it_is(api):
    notes = markets.market_notes(plan_stub(), explain=False)
    json.dumps(notes, allow_nan=False)
    assert set(kinds_in(notes)) <= set(markets.KINDS)
    m = notes["markets"][0]
    assert m["estimated_share"]["kind"] == "estimate" and m["steam_users"]["kind"] == "external"
    assert m["also_loves"]["films"]["kind"] == "qloo_measured" and m["note"]["kind"] == "llm_text"
    a = notes["audience"]
    assert a["kind"] == "qloo_measured" and (qloo.CACHE / f"{a['source']['request']}.json").exists()
    assert any("never an individual" in c for c in notes["caveats"])


def test_markets_follow_the_plan(api):
    notes = markets.market_notes(plan_stub(), explain=False)
    assert [m["language"] for m in notes["markets"]] == ["russian", "spanish", "german"]
    assert notes["markets"][1]["country_name"] == "Spain"  # more Qloo fan mass than Mexico
    empty = markets.market_notes(plan_stub(full=(), store=()), explain=False)
    assert [m["language"] for m in empty["markets"]] == ["thai"] and not empty["markets"][0]["in_plan"]


def test_country_choice_uses_fan_mass_then_population():
    assert markets.market_country("spanish", [{"ES": 9.0, "MX": 5.0}]) == (
        "ES", {"kind": "qloo_measured", "reason": "Most Qloo fan mass for the look-alike games in this language area."})
    country, choice = markets.market_country("spanish", [])
    assert country == "MX" and choice["kind"] == "external"  # the most populous, without fan data
    assert markets.market_country("japanese", [])[1]["kind"] == "external"


# ---------------------------------------------------------------- notes written by Claude, checked by code
def test_claude_notes_are_labelled_and_checked():
    raw = {"notes": [
        {"country": "Spain", "note": "Fans of similar games in Spain love Spain film 1."},
        {"country": "Germany", "note": "Fans of similar games in Germany like 25 km/h and Little Women."},
        {"country": "Russia", "note": "Over 40% of fans love this."},
        {"country": "Brazil", "note": "Mostly female fans of similar games in Brazil."},
        {"country": "Atlantis", "note": "Not a market in the plan."}]}
    evidence = {"Spain": ["Spain film 1"], "Germany": ["25 km/h", "Little Women"], "Russia": ["X"], "Brazil": ["Y"]}
    out = dict(zip(["Spain", "Germany", "Russia", "Brazil", "Japan"],
                   markets.check_notes(raw, ["Spain", "Germany", "Russia", "Brazil", "Japan"], evidence)))
    assert out["Spain"]["status"] == "ok" and out["Spain"]["kind"] == "llm_text"
    assert "check before use" in out["Spain"]["source"]
    assert out["Germany"]["status"] == "ok"  # numbers and words inside evidence titles are fine
    assert "numbers" in out["Russia"]["reason"] and "personal trait" in out["Brazil"]["reason"]
    assert "No Qloo evidence" in out["Japan"]["reason"]


@pytest.mark.parametrize("raw", [{}, None, {"notes": "text"}, {"notes": [{"country": "Spain"}]}])
def test_malformed_claude_notes_are_reported(raw):
    (note,) = markets.check_notes(raw, ["Spain"], {"Spain": ["a"]})
    assert note["status"] == "unavailable" and "wrote no note" in note["reason"]


def test_notes_are_written_from_the_evidence_only(api, monkeypatch):
    seen = {}

    def fake_claude(prompt, schema):
        seen["prompt"] = prompt
        return {"notes": [{"country": "Russia", "note": "Fans of similar games in Russia enjoy Russia movie 4."}]}
    monkeypatch.setattr(llm, "ask_claude_json", fake_claude)
    notes = markets.market_notes(plan_stub(full=("russian",), store=()), explain=True)
    assert notes["markets"][0]["note"]["status"] == "ok"
    assert "Russia movie 4" in seen["prompt"] and "no other numbers" in seen["prompt"]
