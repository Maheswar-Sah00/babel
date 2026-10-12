"""A complete plan result made by the real engine from synthetic Qloo fan maps (no network, no cache): the same
shape babel.agent returns. Used by the map-data, API and browser tests."""
import pandas as pd

from babel import explain, explore, markets
from babel import plan as P

# Roughly the real typical mix (as in test_plan.py); Thai is under the 1% threshold
PRIOR = pd.Series({"russian": .217, "spanish": .123, "german": .110, "brazilian": .103, "schinese": .098,
                   "french": .085, "polish": .055, "koreana": .032, "turkish": .031, "japanese": .026,
                   "italian": .023, "tchinese": .012, "ukrainian": .012, "thai": .004})
BASE = pd.Series(0.5, index=P.LANGS)
# Per look-alike, per country: (Qloo affinity, mean cell popularity, cells), as babel.qloo.country_profile gives them
FAN_MAPS = {
    11: ("Alpha Farm", {"RU": (.80, .6, 40), "BY": (.70, .5, 9), "KZ": (.60, .5, 20), "ES": (.70, .6, 30),
                        "MX": (.75, .5, 25), "AR": (.60, .4, 15), "DE": (.55, .6, 22), "JP": (.40, .5, 30),
                        "CN": (.45, .6, 60), "BR": (.50, .5, 50), "US": (.60, .7, 300), "FR": (.50, .5, 30),
                        "PL": (.60, .5, 15), "CA": (.55, .5, 120), "UY": (.65, .4, 7), "CH": (.52, .5, 6),
                        "KR": (.30, .4, 12)}),
    12: ("Beta Town", {"RU": (.70, .5, 35), "BY": (.60, .4, 8), "ES": (.65, .5, 28), "MX": (.70, .5, 20),
                       "DE": (.50, .5, 20), "JP": (.35, .4, 25), "CN": (.40, .5, 55), "BR": (.55, .5, 45),
                       "US": (.62, .7, 280), "FR": (.48, .5, 28), "PL": (.58, .4, 12), "CA": (.50, .5, 110)}),
    13: ("Gamma Isle", {"RU": (.75, .5, 30), "ES": (.60, .5, 25), "MX": (.65, .4, 18), "DE": (.45, .5, 18),
                        "JP": (.50, .5, 28), "CN": (.42, .5, 50), "BR": (.60, .6, 48), "US": (.58, .7, 260),
                        "FR": (.52, .5, 26), "PL": (.55, .4, 10), "TR": (.40, .4, 14)}),
}
REJECTED = [{"appid": 31, "name": "Ghost Game", "qloo_id": "Q31", "status": "default map", "overlap": .2},
            {"appid": 32, "name": "Lost Game", "qloo_id": None, "status": "not in Qloo", "overlap": .1}]
# The per-country reference (mean affinity over the backtest's look-alikes); Uruguay has too few of them for a ratio
REFERENCE = {"lookalikes": 172, "countries": {
    **{cc: {"affinity": .5, "lookalikes": 120} for cc in ("RU", "BY", "KZ", "ES", "MX", "AR", "DE", "JP", "CN", "BR",
                                                          "US", "FR", "PL", "CA", "CH", "KR", "TR")},
    "UY": {"affinity": .5, "lookalikes": 12}}}
GAME = {"appid": 42, "name": "Test Game", "release_date": "2024-05-01", "supported": ["german"],
        "tags": {"Cozy": 10, "Farming Sim": 8}, "source": "steam"}


def profile(name, qloo_id=None):
    """babel.qloo.game_profile for a synthetic look-alike."""
    countries = next(c for n, c in FAN_MAPS.values() if n == name)
    return {"affinity": {cc: a for cc, (a, _, _) in countries.items()},
            "popularity": {cc: p for cc, (_, p, _) in countries.items()},
            "cells": {cc: n for cc, (_, _, n) in countries.items()},
            "mass": {cc: a * p * n for cc, (a, p, n) in countries.items()}}


def lookalikes(valid=True):
    """Every look-alike examined, as the agent has them: valid ones carry their affinities."""
    good = [{"appid": appid, "name": name, "qloo_id": f"Q{appid}", "status": "valid", "overlap": .3 - .05 * i,
             "affinity": profile(name)["affinity"]} for i, (appid, (name, _)) in enumerate(FAN_MAPS.items())]
    return (good if valid else []) + [dict(r) for r in REJECTED]


def market_notes(p):
    """Market notes like babel.markets.market_notes: Russia has Qloo films (music unavailable) and a checked note."""
    row = next(x for x in p["languages"] if x["code"] == "russian")
    return {
        "audience": {"kind": "qloo_measured", "status": "ok", "reason": None,
                     "source": {"api": "Qloo /v2/insights filter.type=urn:demographics", "request": "demographics_x"},
                     "age": [{"band": "24 and younger", "skew": .31}, {"band": "25 to 29", "skew": .12},
                             {"band": "30 to 34", "skew": -.08}], "gender": {"female": -.05, "male": .05},
                     "meaning": "How fans of the look-alike games differ from the average Qloo audience."},
        "markets": [{
            "language": "russian", "language_name": "Russian", "group": row["group"], "in_plan": True,
            "country": "RU", "country_name": "Russia",
            "country_choice": {"kind": "qloo_measured", "reason": "Most Qloo fan mass for the look-alike games."},
            "estimated_share": {"kind": "estimate", "value": row["estimated_share"], "source": "Babel plan"},
            "steam_users": {"kind": "external", "value": .0905, "source": "Steam survey"},
            "also_loves": {
                "films": {"kind": "qloo_measured", "status": "ok", "reason": None, "local_pool_size": 30,
                          "ranked": 12, "requests": ["local_russia_movie_1", "fans_russia_movie_1"],
                          "items": [{"name": "Film Alpha", "qloo_id": "F1"}, {"name": "Film Beta", "qloo_id": "F2"}],
                          "meaning": "Films popular in Russia, ranked by fans of the look-alike games."},
                "music": {"kind": "qloo_measured", "status": "unavailable", "items": [], "requests": [],
                          "reason": "Qloo returned no music popular in Russia.", "meaning": ""}},
            "note": {"kind": "llm_text", "status": "ok", "reason": None, "source": "Claude",
                     "text": "Fans of similar games in Russia also love Film Alpha: a hook for the store page."}}],
        "lookalikes": [n for n, _ in FAN_MAPS.values()], "kinds": markets.KINDS, "caveats": markets.CAVEATS,
        "method": "Two Qloo steps per market and domain.",
    }


def result(word_count=30_000, budget=10_000, valid=True, with_markets=True):
    """The agent's result for Test Game: plan, market notes, explanation, evidence index and the Plan screen's data."""
    looks = lookalikes(valid)
    p = P.build_plan(dict(GAME), looks, word_count, budget, PRIOR, BASE, n_base=172)
    notes = market_notes(p) if with_markets and valid else None
    idx = explain.evidence_index(p, notes)
    top = p["languages"][0]
    cite = f"lang:{top['code']}"
    exp = {"kind": "llm_text", "status": "ok", "reason": None, "dropped": [], "source": "Claude",
           "summary": f"{top['language']} comes first: an estimated {idx[cite]['estimated share']} of non-English "
                      "demand.",
           "points": [{"text": f"{top['language']} has the highest estimated share.", "evidence": [cite]},
                      {"text": "Shares are estimates, not sales.", "evidence": ["caveat:1"]}]}
    return {"plan": p, "market_notes": notes, "explanation": exp, "evidence_index": idx,
            "explore": {"map": explore.map_data(looks, PRIOR, BASE, REFERENCE, P.ALPHA, profile=profile),
                        "versus_generic": explore.versus_generic(p, PRIOR), "costs": explore.cost_breakdown(p)}}
