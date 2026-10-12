"""The engine against the real backtest, offline. Needs the local API cache (cache/, git-ignored): skipped without it,
and any network call fails the test."""
import asyncio
import json

import anthropic
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from babel import agent, api, describe, markets, net, qloo
from babel import plan as P

DATA = P.BACKTEST_DATA
pytestmark = pytest.mark.skipif(not any((P.ROOT / "cache" / "qloo").glob("heatmap_*")),
                                reason="needs the local API cache in cache/ (not in the repo)")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network call during an offline test")
    monkeypatch.setattr(net, "request", refuse)
    monkeypatch.setattr(anthropic, "Anthropic", refuse)  # Claude answers must come from the cache


@pytest.fixture(scope="module")
def ctx():
    return P.Context()


def test_engine_reproduces_the_backtest_rankings(ctx):
    """For all 71 Steam test games, the engine's ranking equals the pre-registered Babel ranking."""
    preds = pd.read_csv(DATA / "final_predictions_steam.csv")
    expected = preds[preds.competitor == "Babel: typical x S1 (primary)"].set_index("appid").ranking
    dev = set(pd.read_csv(DATA / "dev_test_games_43.csv").appid) & set(pd.read_csv(DATA / "truth_reviews.csv").appid)
    prior = P.typical_mix(dev)  # the backtest used the dev games' mix for test games
    comps = pd.read_csv(DATA / "comps.csv")
    base, _ = ctx.base
    for appid, ranking in expected.items():
        signals = [P.comp_signal(P.comp_affinity(r.comp_name, r.qloo_id))
                   for r in comps[comps.test_appid == appid].itertuples()]
        assert "|".join(P.rank(P.demand_shares(prior, P.qloo_lift(signals, base)))) == ranking, appid
    assert len(expected) == 71


@pytest.mark.parametrize("appid, words, budget", P.EXAMPLES)
def test_example_plans(ctx, appid, words, budget):
    p = P.plan(words, budget, appid=appid, ctx=ctx)
    assert p["status"] == "ok"
    assert all(p["groups"][g] for g in ("translate_game", "store_page_only", "skip"))
    assert p["costs"]["total"] <= budget
    backtest = pd.read_csv(DATA / "comps.csv")  # same look-alikes as the backtest picked
    assert [x["name"] for x in p["lookalikes"]["used"]] == list(backtest[backtest.test_appid == appid].comp_name)


@pytest.mark.parametrize("appid, words, budget", P.EXAMPLES)
def test_market_notes_for_the_demo_games(ctx, appid, words, budget):
    """Every demo market has Qloo insights or an explicit unavailable message, and every item is labelled."""
    notes = markets.market_notes(P.plan(words, budget, appid=appid, ctx=ctx))
    assert notes["audience"]["status"] == "ok" and len(notes["markets"]) == markets.MAX_MARKETS
    for m in notes["markets"]:
        for res in [*m["also_loves"].values(), m["note"]]:
            assert (res["status"] == "ok") != bool(res["reason"])  # either a result or the reason it is missing
        assert all(i["qloo_id"] for res in m["also_loves"].values() for i in res["items"])
    json.dumps(notes, allow_nan=False)


@pytest.mark.parametrize("appid, words, budget", P.EXAMPLES)
def test_agent_on_the_demo_games(ctx, appid, words, budget):
    """Complete trace, plan identical to the engine's, grounded explanation, identical on a repeated run."""
    first, second = (agent.run(words, budget, appid=appid, ctx=ctx) for _ in range(2))
    assert first["status"] == "ok" and first == second
    assert first["result"]["plan"] == P.plan(words, budget, appid=appid, ctx=ctx)
    assert first["result"]["explanation"]["kind"] == "llm_text"
    types = [e["type"] for e in first["events"]]
    assert types[-1] == "done" and "error" not in types


@pytest.mark.parametrize("appid, words, budget", P.EXAMPLES)
def test_world_map_evidence_for_the_demo_games(ctx, appid, words, budget):
    """Real Qloo evidence on the map: each country's score is the mean of the look-alikes' popularity-weighted country
    scores, the lifts equal the plan's, every fan map traces to its cached response, rejected games are never drawn."""
    out = agent.run(words, budget, appid=appid, ctx=ctx, with_markets=False, with_explanation=False)
    m, p = out["result"]["explore"]["map"], out["result"]["plan"]
    assert out["status"] == "ok" and m["status"] == "ok" and m["countries_with_score"] >= 60
    used = [x for x in m["lookalikes"] if x["usable"]]
    assert [x["name"] for x in used] == [x["name"] for x in p["lookalikes"]["used"]] and len(used) == 3
    assert all((P.ROOT / "cache" / "qloo" / f"{x['request']}.json").exists() for x in m["lookalikes"] if x["request"])
    profiles = {str(x["appid"]): qloo.game_profile(x["name"], x["qloo_id"])["affinity"] for x in used}
    for cc, row in m["countries"].items():
        have = [prof[cc] for prof in profiles.values() if cc in prof]
        assert row["lookalikes_with_score"] == len(have) and set(row["by_lookalike"]) <= set(profiles)
        assert row["affinity"] == (round(sum(have) / len(have), 4) if have else None)
    rows = {x["code"]: x for x in p["languages"]}
    assert all(m["languages"][l]["lift"] == rows[l]["qloo_lift"] for l in P.LANGS)
    assert sum(r["relative"] is not None for r in m["countries"].values()) >= 50
    assert out["result"]["explore"]["versus_generic"]["babel_top3"] == [x["code"] for x in p["languages"][:3]]


def test_precomputed_runtime_data_gives_identical_plans(ctx, monkeypatch, tmp_path):
    """Task 2: the files tools/build_runtime.py writes, built from the cache with no network, give the same baseline,
    pool, fan maps, plans and map data as the cache-built context."""
    from babel import runtime

    def offline(*args, **kwargs):
        raise net.Offline("not cached")
    monkeypatch.setattr(net, "request", offline)
    runtime.save(runtime.build(ctx), tmp_path)
    try:
        pre = runtime.load(tmp_path)
        assert pre.prior.equals(ctx.prior) and pre.base[0].equals(ctx.base[0]) and pre.base[1] == ctx.base[1]
        assert pre.country_reference == ctx.country_reference and pre.default_map == ctx.default_map
        assert pre.picker.names == ctx.picker.names and pre.picker.weights_of == ctx.picker.weights_of
        assert all(pre.picker.status[a] == s for a, s in ctx.picker.status.items())
        for appid, words, budget in P.EXAMPLES:
            assert P.plan(words, budget, appid=appid, ctx=pre) == P.plan(words, budget, appid=appid, ctx=ctx)
            fresh, cached = (agent.run(words, budget, appid=appid, ctx=c, with_markets=False, with_explanation=False)
                             for c in (pre, ctx))
            assert fresh["result"] == cached["result"]
    finally:
        qloo._PRECOMPUTED.clear()
        qloo.game_sums.cache_clear()


def test_mcp_api_and_cli_give_the_same_plan(ctx):
    """For identical inputs, the MCP tool, POST /plan, the agent CLI path and the engine return the identical plan."""
    appid, words, budget = P.EXAMPLES[0]
    args = {"appid": appid, "word_count": words, "budget": budget}

    def fresh_app():  # separate apps, so no answer comes from another's plan cache
        app = api.create_app(api.Settings(warmup=False), loader=lambda: ctx)
        app.state.babel.ctx = ctx
        app.state.babel.ready.set()
        return app

    async def mcp_call(app):
        async with create_connected_server_and_client_session(app.state.mcp) as session:
            return await session.call_tool("babel_language_plan", args)
    via_api = TestClient(fresh_app()).post("/plan?stream=false", json=args).json()["result"]["plan"]
    via_mcp = asyncio.run(mcp_call(fresh_app())).structuredContent["plan"]
    via_cli = json.loads(json.dumps(agent.run(words, budget, appid=appid, ctx=ctx)["result"]["plan"]))
    via_engine = json.loads(json.dumps(P.plan(words, budget, appid=appid, ctx=ctx)))
    assert via_mcp == via_api == via_cli == via_engine


def test_name_lookup(ctx):
    assert P.plan(30_000, 10_000, name="WEBFISHING", ctx=ctx)["game"]["appid"] == 3146520


def test_description_examples(ctx):
    """The three example descriptions, from cached Claude answers: verified look-alikes and honest confidence."""
    cozy, tactics, vague = [P.plan(40_000, 12_000, description=t, ctx=ctx) for t in describe.EXAMPLES]
    assert [x["name"] for x in cozy["lookalikes"]["used"]] == ["Stardew Valley", "My Time at Portia", "Unpacking"]
    assert cozy["discovery"]["confidence"]["level"] == "high"
    assert tactics["lookalikes"]["used"][0]["name"].startswith("Darkest Dungeon")  # named by Claude + tag match
    assert vague["discovery"]["needs_user_choice"]
    assert any("choose comparable games yourself" in m for m in vague["messages"])
    assert all(p["status"] == "ok" and p["costs"]["total"] <= 12_000 for p in (cozy, tactics, vague))


def test_user_lookalikes_for_a_game_without_a_store_page(ctx):
    p = P.plan(30_000, 8_000, lookalikes=[413150, 1135690], ctx=ctx)
    assert p["game"]["appid"] is None
    assert [x["name"] for x in p["lookalikes"]["used"]] == ["Stardew Valley", "Unpacking"]
    assert p["lookalikes"]["evidence_level"] == "low"
