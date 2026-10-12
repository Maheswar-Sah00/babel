"""Unit tests for the planning engine: synthetic data only (no network, no cache)."""
import ast
import itertools
import json
import math
import random
from pathlib import Path

import pandas as pd
import pytest

from babel import languages
from babel import plan as P

ROOT = Path(__file__).resolve().parents[1]
LANGS = list(languages.TARGETS)
# Roughly the real typical mix (backtest/step2_report.md); Thai is under the 1% threshold
PRIOR = pd.Series({"russian": .217, "spanish": .123, "german": .110, "brazilian": .103, "schinese": .098,
                   "french": .085, "polish": .055, "koreana": .032, "turkish": .031, "japanese": .026,
                   "italian": .023, "tchinese": .012, "ukrainian": .012, "thai": .004})
BASE = pd.Series(0.5, index=LANGS)
SHARES = PRIOR / PRIOR.sum()
COST_FULL = {l: P.full_cost(l, 30_000, P.Rates()) for l in LANGS}
COST_STORE = {l: P.store_cost(l, P.Rates()) for l in LANGS}


def game(**kw):
    return {"appid": 1, "name": "Test game", "release_date": None, "supported": [], "tags": {"Cozy": 10},
            "source": "test", **kw}


def look(affinity=None, status="valid", name="Look-alike"):
    return {"appid": 2, "name": name, "qloo_id": "Q", "status": status, "overlap": 0.3, "affinity": affinity or {}}


def plan_of(budget=10_000, words=30_000, looks=(), game_kw=None, **kw):
    return P.build_plan(game(**(game_kw or {})), list(looks), words, budget, PRIOR, BASE, **kw)


def allocate(budget, **kw):
    return P.allocate(SHARES, COST_FULL, COST_STORE, budget, **kw)


def spent(groups):
    return sum(COST_FULL[l] for l in groups["translate_game"]) + sum(COST_STORE[l] for l in groups["store_page_only"])


def brute_force(values, costs, budget):
    return max(sum(values[k] for k in combo) for r in range(len(values) + 1)
               for combo in itertools.combinations(values, r) if sum(costs[k] for k in combo) <= budget + 1e-9)


# ---------------------------------------------------------------- the engine uses the backtest's method
def backtest_literal(name):
    tree = ast.parse((ROOT / "backtest" / "evaluate.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets))


def test_language_tables_match_the_backtest():
    assert languages.TARGETS == backtest_literal("TARGETS")
    assert languages.GENERIC == backtest_literal("GENERIC")
    assert languages.POP == backtest_literal("POP")
    assert languages.COUNTRIES == {l: backtest_literal("COUNTRIES")[l] for l in LANGS}
    assert languages.LABEL == {l: backtest_literal("LABEL")[l] for l in LANGS}
    assert languages.COUNTRY_NAME == backtest_literal("COUNTRY_NAME")
    assert languages.STEAM_SHARE == backtest_literal("STEAM_SHARE")


def test_track_record_matches_the_final_report():
    report = (ROOT / "backtest" / "final_report.md").read_text(encoding="utf-8")
    for truth in ("steam_reviews", "wikipedia_pageviews"):
        r = P.TRACK_RECORD[truth]
        assert f"{r['babel_top3_coverage']:.1%}" in report and f"{r['typical_mix_top3_coverage']:.1%}" in report
    assert "p = 0.500" in report


# ---------------------------------------------------------------- costs
def test_full_cost_formula():
    rates = P.Rates(per_word={l: 0.10 for l in LANGS}, store_page_words=500, qa_overhead=0.15, min_fee=50)
    assert P.full_cost("german", 10_000, rates) == pytest.approx((10_000 + 500) * 0.10 * 1.15)


def test_store_cost_formula():
    assert P.store_cost("german", P.Rates()) == pytest.approx(500 * 0.12)


def test_minimum_fee_applies_to_small_jobs():
    rates = P.Rates(per_word={l: 0.10 for l in LANGS}, store_page_words=100, qa_overhead=0, min_fee=100)
    assert P.store_cost("german", rates) == 100  # 100 words x $0.10 = $10, under the minimum
    assert P.full_cost("german", 1, rates) == 100


@pytest.mark.parametrize("rates", [
    P.Rates(per_word={"german": 0.1}),  # rates missing for 13 languages
    P.Rates(per_word={**P.DEFAULT_PER_WORD, "thai": -0.1}),
    P.Rates(store_page_words=0),
    P.Rates(qa_overhead=-0.1),
    P.Rates(min_fee=float("nan")),
])
def test_invalid_rates_are_rejected(rates):
    with pytest.raises(P.PlanError):
        rates.check()


# ---------------------------------------------------------------- optimizer
def test_optimizer_beats_greedy():
    # greedy by value takes only "a" (0.5); the best set is b + c (0.6)
    assert P.best_subset({"a": 0.5, "b": 0.3, "c": 0.3}, {"a": 6, "b": 5, "c": 5}, 10) == ["b", "c"]


def test_optimizer_matches_brute_force():
    rng = random.Random(7)
    for _ in range(300):
        values = {f"k{i}": rng.random() for i in range(rng.randint(1, 8))}
        costs = {k: rng.randint(1, 20) for k in values}
        budget = rng.uniform(0, 60)
        chosen = P.best_subset(values, costs, budget)
        assert sum(costs[k] for k in chosen) <= budget + 1e-9
        assert sum(values[k] for k in chosen) == pytest.approx(brute_force(values, costs, budget))


@pytest.mark.parametrize("budget, expected", [(-5, []), (0, []), (4.99, []), (5, ["b"]), (9.99, ["b"]),
                                              (10, ["a"]), (14.99, ["a"]), (15, ["a", "b"])])
def test_optimizer_budget_boundaries(budget, expected):
    assert P.best_subset({"a": 0.6, "b": 0.4}, {"a": 10, "b": 5}, budget) == expected


def test_optimizer_prefers_the_cheaper_of_equal_sets():
    assert P.best_subset({"a": 0.5, "b": 0.5}, {"a": 10, "b": 5}, 10) == ["b"]


def test_optimizer_refuses_too_many_items():
    with pytest.raises(ValueError):
        P.best_subset({i: 1 for i in range(21)}, {i: 1 for i in range(21)}, 5)


# ---------------------------------------------------------------- demand scores
def test_comp_signal_is_population_weighted():
    s = P.comp_signal({"RU": 1.0, "BY": 0.0, "KZ": 0.5, "DE": 0.8})
    assert s["russian"] == pytest.approx((144 * 1.0 + 9 * 0.0 + 20 * 0.5) / (144 + 9 + 20))
    assert s["german"] == pytest.approx(0.8)  # Austria and Switzerland missing: Germany alone
    assert math.isnan(s["japanese"])


def test_lift_is_one_where_there_is_no_data():
    assert (P.qloo_lift([], BASE) == 1).all()
    lift = P.qloo_lift([P.comp_signal({"JP": 1.0}), P.comp_signal({"JP": 0.5, "KR": 0.2})], BASE)
    assert lift["japanese"] == pytest.approx(0.75 / 0.5)
    assert lift["koreana"] == pytest.approx(0.2 / 0.5)
    assert lift["german"] == 1.0


def test_demand_shares_sum_to_one_and_alpha_zero_is_the_baseline():
    lift = pd.Series(1.0, index=LANGS).mask(lambda s: s.index == "japanese", 3.0)
    shares = P.demand_shares(PRIOR, lift)
    assert shares.sum() == pytest.approx(1)
    assert shares["japanese"] > SHARES["japanese"]
    assert P.demand_shares(PRIOR, lift, alpha=0).values == pytest.approx(SHARES[LANGS].values)


def test_demand_shares_reject_a_bad_baseline():
    with pytest.raises(ValueError):
        P.demand_shares(-PRIOR, pd.Series(1.0, index=LANGS))


def test_rank_breaks_ties_in_generic_order():
    assert P.rank(pd.Series(1.0, index=LANGS)) == languages.GENERIC


# ---------------------------------------------------------------- the three groups
def test_a_mid_budget_gives_all_three_groups():
    groups, reasons = allocate(10_000)
    assert groups["translate_game"] and groups["store_page_only"] and groups["skip"]
    assert "thai" in groups["skip"] and "threshold" in reasons["thai"]
    assert set(reasons) == set(LANGS)


def test_every_language_lands_in_exactly_one_group():
    for budget in (0, 120, 5_000, 10_000, 1e6):
        groups, _ = allocate(budget, supported=["german"])
        assert sorted(l for ls in groups.values() for l in ls) == sorted(LANGS)


def test_the_budget_is_never_exceeded():
    rng = random.Random(3)
    for budget in [0, 49.99, 50, 700, 3_157, 7_000, 20_000, 1e6] + [rng.uniform(0, 60_000) for _ in range(50)]:
        assert spent(allocate(budget)[0]) <= budget + 1e-6


def test_full_translations_are_the_best_set_not_the_top_ranks():
    eligible = [l for l in LANGS if SHARES[l] >= P.MIN_SHARE]
    rng = random.Random(5)
    for budget in [rng.uniform(3_000, 40_000) for _ in range(20)]:
        full = allocate(budget)[0]["translate_game"]
        best = brute_force({l: SHARES[l] for l in eligible}, {l: COST_FULL[l] for l in eligible}, budget)
        assert sum(SHARES[l] for l in full) == pytest.approx(best)


def test_zero_budget_skips_everything():
    groups, reasons = allocate(0)
    assert not groups["translate_game"] and not groups["store_page_only"]
    assert len(groups["skip"]) == len(LANGS)
    assert "Not enough budget" in reasons["russian"]


def test_a_huge_budget_translates_everything_over_the_threshold():
    groups, _ = allocate(1e7)
    assert groups["skip"] == ["thai"]
    assert len(groups["translate_game"]) == len(LANGS) - 1


def test_store_pages_only_when_no_full_translation_fits():
    groups, reasons = allocate(min(COST_FULL.values()) - 1)
    assert not groups["translate_game"] and groups["store_page_only"]
    assert "store page" in reasons[groups["store_page_only"][0]]


def test_supported_languages_are_left_out():
    groups, reasons = allocate(10_000, supported=["german", "russian"])
    assert groups["already_supported"] == ["russian", "german"]  # in rank order
    assert "russian" not in groups["translate_game"] and "already supports" in reasons["russian"]


# ---------------------------------------------------------------- missing data and the evidence object
def test_no_qloo_data_falls_back_to_the_baseline():
    p = plan_of(looks=[])
    assert p["lookalikes"]["evidence_level"] == "none"
    assert all(x["qloo_lift"] == 1 for x in p["languages"])
    assert [x["estimated_share"] for x in p["languages"]] == [x["baseline_share"] for x in p["languages"]]
    assert any("typical language mix" in m for m in p["messages"])


def test_default_map_lookalikes_are_not_used():
    p = plan_of(looks=[look(status="default map", name="Lethal Company"), look(status="not in Qloo", name="X")])
    assert p["lookalikes"]["evidence_level"] == "none" and not p["lookalikes"]["used"]
    assert [x["name"] for x in p["lookalikes"]["rejected"]] == ["Lethal Company", "X"]
    assert all(x["qloo_lift"] == 1 for x in p["languages"])


def test_one_lookalike_is_low_evidence_and_moves_the_estimate():
    p = plan_of(looks=[look({"JP": 2.0})])  # lift = 2.0 / 0.5 = 4
    jp = next(x for x in p["languages"] if x["code"] == "japanese")
    assert p["lookalikes"]["evidence_level"] == "low"
    assert jp["qloo_lift"] == 4.0 and jp["estimated_share"] > jp["baseline_share"]


def test_disagreeing_lookalikes_are_flagged():
    p = plan_of(looks=[look({"JP": 1.0}), look({"JP": 0.1}), look({"JP": 0.5})])
    assert p["lookalikes"]["evidence_level"] == "normal"
    assert "japanese" in p["uncertainty"]["lookalikes_disagree_on"]


def test_evidence_object_is_complete_and_json_ready():
    p = plan_of(looks=[look({"RU": 0.6, "DE": 0.4, "JP": 0.9}) for _ in range(3)])
    json.dumps(p, allow_nan=False)  # plain types only, no NaN
    assert {"status", "messages", "game", "inputs", "lookalikes", "groups", "languages", "costs",
            "estimated_coverage", "rates", "formulas", "sources", "uncertainty", "track_record"} <= set(p)
    assert "affinity" not in p["lookalikes"]["used"][0]
    assert p["costs"]["total"] <= p["costs"]["budget"]
    assert p["costs"]["total"] + p["costs"]["unspent"] == pytest.approx(p["costs"]["budget"])
    assert sum(x["estimated_share"] for x in p["languages"]) == pytest.approx(1, abs=1e-3)
    assert any("not sales" in c for c in p["uncertainty"]["caveats"])


@pytest.mark.parametrize("budget, status", [(0, "nothing_affordable"), (40, "nothing_affordable"),
                                            (1_000, "store_pages_only"), (10_000, "ok")])
def test_status_follows_the_budget(budget, status):
    p = plan_of(budget=budget)
    assert p["status"] == status
    assert p["costs"]["total"] <= budget


def test_a_fully_translated_game_has_nothing_to_translate():
    p = plan_of(game_kw={"supported": LANGS})
    assert p["status"] == "nothing_to_translate" and p["costs"]["total"] == 0


# ---------------------------------------------------------------- input validation (before any data is loaded)
@pytest.mark.parametrize("words, budget", [(30_000, -1), (30_000, float("nan")), (30_000, float("inf")),
                                           (30_000, "100"), (0, 100), (-5, 100), (1.5, 100), (True, 100),
                                           (None, 100), ("abc", 100), (P.MAX_WORDS + 1, 100)])
def test_invalid_inputs_raise_plan_error(words, budget):
    with pytest.raises(P.PlanError):
        P.plan(words, budget, appid=1, ctx="never loaded")


def test_a_game_source_is_required():
    with pytest.raises(P.PlanError, match="Steam app ID"):
        P.plan(30_000, 1_000, ctx="never loaded")
