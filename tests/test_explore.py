"""The Plan screen's data (babel/explore.py) and budget re-fitting (plan.fit_budget): synthetic data, no network."""
import json

import pytest

from babel import explore, qloo
from babel import plan as P
from babel.languages import COUNTRIES, GENERIC, OFFICIAL_IN
from synthetic import BASE, FAN_MAPS, GAME, PRIOR, lookalikes, profile, result


def cell(lat, lon, affinity, popularity, i):
    return {"location": {"latitude": lat, "longitude": lon, "geohash": f"c{i}"},
            "query": {"affinity": affinity, "popularity": popularity}}


# ---------------------------------------------------------------- country aggregation (babel.qloo)
def test_countries_are_popularity_weighted_and_need_five_cells():
    japan = [(35.68, 139.69, .9, .8), (34.69, 135.50, .5, .2), (35.18, 136.90, .7, .5), (43.06, 141.35, .2, .1),
             (33.59, 130.40, .6, .4), (38.27, 140.87, .8, .6)]
    brazil = [(-23.55, -46.63, .9, .9), (-22.91, -43.17, .9, .9), (-15.79, -47.88, .9, .9), (-12.97, -38.50, .9, .9)]
    prof = qloo.country_profile([cell(*c, i) for i, c in enumerate(japan + brazil)])
    weighted = sum(a * p for _, _, a, p in japan) / sum(p for _, _, _, p in japan)
    assert prof["affinity"]["JP"] == pytest.approx(weighted)
    assert prof["affinity"]["JP"] != pytest.approx(sum(a for _, _, a, _ in japan) / len(japan))  # not a plain mean
    assert prof["cells"]["JP"] == 6 and prof["popularity"]["JP"] == pytest.approx(2.6 / 6)
    assert "BR" not in prof["affinity"] and "BR" not in prof["cells"]  # 4 cells: no score


# ---------------------------------------------------------------- the map's countries
def test_a_country_is_the_mean_over_lookalikes_with_a_score_there():
    m = result()["explore"]["map"]
    ru, by = m["countries"]["RU"], m["countries"]["BY"]
    assert ru["affinity"] == pytest.approx((.80 + .70 + .75) / 3) and ru["lookalikes_with_score"] == 3
    assert by["affinity"] == pytest.approx((.70 + .60) / 2) and by["lookalikes_with_score"] == 2
    assert set(by["by_lookalike"]) == {"11", "12"}
    assert ru["relative"] == pytest.approx(ru["affinity"] / .5, abs=1e-3)
    assert ru["by_lookalike"]["11"] == {"affinity": .8, "popularity": .6, "cells": 40, "relative": 1.6}


def test_relative_needs_enough_reference_games():
    uy = result()["explore"]["map"]["countries"]["UY"]
    assert uy["affinity"] == .65 and uy["relative"] is None and uy["reference"]["usable"] is False
    no_ref = explore.map_data(lookalikes(), PRIOR, BASE, None, profile=profile)
    assert no_ref["reference"]["available"] is False
    assert all(r["relative"] is None for r in no_ref["countries"].values())


def test_countries_without_a_score_are_not_given_one():
    m = result()["explore"]["map"]
    assert m["countries"]["UA"]["affinity"] is None and m["countries"]["UA"]["by_lookalike"] == {}
    assert m["countries_with_score"] == len({cc for _, c in FAN_MAPS.values() for cc in c})


# ---------------------------------------------------------------- languages and countries are not one-to-one
def test_language_and_country_relationships_are_explicit():
    m = result()["explore"]["map"]
    c = m["countries"]
    assert c["CH"]["model_language"] == "german" and set(c["CH"]["official_languages"]) == {"german", "french",
                                                                                          "italian"}
    assert c["CA"]["model_language"] is None and c["CA"]["official_languages"] == ["french"]
    assert c["UY"]["model_language"] is None and c["UY"]["official_languages"] == ["spanish"]
    assert c["MX"]["model_language"] == "spanish" and c["MX"]["population_m"] == 129
    for lang, countries in COUNTRIES.items():
        assert m["languages"][lang]["countries"] == countries and all(c[cc]["model_language"] == lang
                                                                      for cc in countries)
        assert set(countries) <= set(OFFICIAL_IN[lang])  # Babel only counts countries where the language is official


# ---------------------------------------------------------------- every language's calculation equals the plan
def test_language_calculations_recompute_the_plan_exactly():
    r = result()
    m, rows = r["explore"]["map"], {x["code"]: x for x in r["plan"]["languages"]}
    for lang in P.LANGS:
        x = m["languages"][lang]
        assert x["lift"] == rows[lang]["qloo_lift"] and x["estimated_share"] == rows[lang]["estimated_share"]
        assert x["baseline_x_lift"] / m["baseline_x_lift_sum"] == pytest.approx(x["estimated_share"], abs=1e-4)
        for appid, (name, _) in FAN_MAPS.items():
            s1 = P.comp_signal(profile(name)["affinity"])[lang]
            assert x["s1"][str(appid)] == (None if s1 != s1 else round(s1, 4))
    ru = m["languages"]["russian"]
    assert ru["mean_s1"] / ru["reference_s1"] == pytest.approx(ru["lift"], abs=1e-3)


def test_default_maps_and_missing_games_are_listed_but_never_used():
    m = result()["explore"]["map"]
    entries = {x["appid"]: x for x in m["lookalikes"]}
    assert [x["appid"] for x in m["lookalikes"] if x["usable"]] == list(FAN_MAPS)
    ghost, lost = entries[31], entries[32]
    assert not ghost["usable"] and "default (no-data) map" in ghost["reason"]
    assert ghost["request"] == qloo.heatmap_id("Ghost Game", "Q31")  # traceable, but not drawn
    assert not lost["usable"] and lost["request"] is None and "no entry" in lost["reason"]
    assert all("31" not in r["by_lookalike"] and "32" not in r["by_lookalike"] for r in m["countries"].values())


def test_no_fan_map_gives_a_no_data_map_with_languages_only():
    r = result(valid=False)
    m = r["explore"]["map"]
    assert m["status"] == "no_data" and m["countries_with_score"] == 0
    assert all(x["lift"] == 1.0 for x in m["languages"].values())
    assert m["countries"]["RU"]["model_language"] == "russian" and m["countries"]["RU"]["affinity"] is None
    assert not any(x["usable"] for x in m["lookalikes"])


def test_map_data_is_json_ready():
    json.dumps(result(), allow_nan=False)


# ---------------------------------------------------------------- Babel vs the generic list, and costs
def test_versus_generic_explains_every_difference():
    r = result()
    vs, rows = r["explore"]["versus_generic"], {x["code"]: x for x in r["plan"]["languages"]}
    assert [x["babel_rank"] for x in vs["rows"]] == list(range(1, 15))
    assert vs["generic_top3"] == GENERIC[:3] and vs["babel_top3"] == [x["code"] for x in r["plan"]["languages"][:3]]
    for x in vs["rows"]:
        assert x["generic_rank"] == GENERIC.index(x["code"]) + 1 and x["places"] == x["generic_rank"] - x["babel_rank"]
        assert x["babel_rank"] == rows[x["code"]]["rank"] and x["qloo_lift"] == rows[x["code"]]["qloo_lift"]
        assert x["why"].startswith("Typical mix:") and f"{x['qloo_lift']:.2f}" in x["why"]
    ru = next(x for x in vs["rows"] if x["code"] == "russian")
    assert "1st" in ru["why"] and "(generic list: 5th)" in ru["why"] and "more over-represented" in ru["why"]


@pytest.mark.parametrize("words", [30_000, 10])
def test_cost_breakdown_reproduces_the_plans_costs(words):
    p = result(word_count=words)["plan"]
    costs, rates = explore.cost_breakdown(p), p["rates"]
    for x in p["languages"]:
        c = costs[x["code"]]
        charged = max(rates["min_fee"], c["full_before_qa"])
        assert round(charged * (1 + rates["qa_overhead"]), 2) == pytest.approx(x["cost_full"], abs=.01)
        assert c["min_fee_applies"] == ((words + 500) * rates["per_word"][x["code"]] < rates["min_fee"])
        assert c["cost_store_page"] == x["cost_store_page"] == max(rates["min_fee"], c["store_page_before_min"])
    assert any(c["min_fee_applies"] for c in costs.values()) == (words == 10)  # Ukrainian: 510 x $0.09 < $50


# ---------------------------------------------------------------- the budget slider = the engine's own optimizer
@pytest.mark.parametrize("budget", [0, 49, 50, 499, 3507.5, 3508, 5000, 7365, 7366, 10_000, 25_000, 60_000, 1e6])
def test_refitting_the_budget_gives_exactly_a_fresh_plan(budget):
    first = result(budget=10_000)["plan"]
    allocation = json.loads(json.dumps(first["allocation"]))  # as the browser sends it back
    fit = P.fit_budget(allocation["shares"], allocation["cost_full"], allocation["cost_store_page"], budget,
                       allocation["min_share"], allocation["supported"])
    fresh = P.build_plan(dict(GAME), lookalikes(), 30_000, budget, PRIOR, BASE, n_base=172)
    assert fit["groups"] == fresh["groups"] and fit["costs"] == fresh["costs"]
    assert fit["estimated_coverage"] == fresh["estimated_coverage"] and fit["status"] == fresh["status"]
    assert fit["reasons"] == {x["code"]: x["reason"] for x in fresh["languages"]}
    assert fit["message"] == (None if fresh["status"] == "ok" else fresh["messages"][-1])
    assert fit["costs"]["total"] <= budget + 1e-6


def test_the_allocation_round_trips_exactly():
    p = result()["plan"]
    shares = json.loads(json.dumps(p["allocation"]))["shares"]
    assert shares == p["allocation"]["shares"] and abs(sum(shares.values()) - 1) < 1e-12
    assert {l: round(s, 4) for l, s in shares.items()} == {x["code"]: x["estimated_share"] for x in p["languages"]}
