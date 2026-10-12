"""Data for the Plan screen: where fans of the look-alikes are (the world map), and Babel vs the generic list.

Computed by code from the fan maps the plan already read (no new requests):
  - countries: each valid look-alike's Qloo world fan map aggregated per country by babel.qloo.country_profile
    (popularity-weighted mean cell affinity; countries with fewer than qloo.MIN_CELLS cells get no score), then the
    mean over the look-alikes with a score there, as the engine's lift does. 'relative' divides by the same country's
    mean over the Steam backtest's look-alikes (the lift reference, one country at a time), shown only where at least
    REFERENCE_MIN of them have a score. Display only: the language scores come from babel.plan;
  - languages: the whole calculation behind each estimated share (S1 per look-alike from its countries' affinities
    and population weights, the reference S1, the lift, baseline x lift, the sum, the share), recomputed with
    babel.plan's own functions; the agent verifies it equals the plan;
  - official languages (reference data, display only), so the map can say that a language spans several countries
    and a country can speak several languages, instead of pretending the mapping is one-to-one;
  - versus_generic: Babel's ranking against the copy-pasted tier list, split into the baseline's effect and Qloo's.
Qloo describes the aggregate taste of fans of similar games: none of this is a player count or a sales forecast.
"""
import numpy as np

from . import plan as P
from . import qloo
from .languages import COUNTRIES, GENERIC, LABEL, OFFICIAL_IN, POP, STEAM_SHARE

VERSION = 1
REFERENCE_MIN = 20  # backtest look-alikes with a score in a country before 'vs typical games' is shown there
NEAR = 0.05  # a lift within 1 +- NEAR counts as "about average" in the comparison text
REJECTED = {"default map": "Qloo returned its default (no-data) map for this game, so Babel does not use it.",
            "not in Qloo": "Qloo has no entry for this game.",
            "no heatmap": "Qloo returned no fan map for this game."}
SOURCES = {
    "affinity": "Qloo world heatmaps (urn:heatmap, geohash-3 cells of about 156 km) of the look-alike games, "
                "aggregated per country by Babel",
    "reference": "The same Qloo heatmaps for the Steam backtest's look-alike games (backtest/data/comps.csv)",
    "official_languages": "Public reference data on official languages; display only, never in a score",
    "population": "Population weights (millions) in babel/languages.py, as in the backtest",
}
METHOD = {
    "affinity": f"Per look-alike: the mean of its Qloo cells' affinity in the country, weighted by each cell's Qloo "
                f"popularity; countries with fewer than {qloo.MIN_CELLS} cells get no score. Then the mean over the "
                f"look-alikes with a score there.",
    "relative": f"The country's fan affinity divided by the mean affinity there over the Steam backtest's look-alikes "
                f"(shown where at least {REFERENCE_MIN} of them have a score). Above 1: fans of games like yours are "
                f"more over-represented there than fans of typical games.",
    "popularity": "Qloo popularity (0 to 1) says how much activity a game has in a cell, relative to other cells. It "
                  "is the weight in the affinity average, not a player count.",
    "demand": "Babel's estimated share of non-English demand for a language (typical language mix x Qloo lift). It "
              "belongs to the language, and is drawn on every country Babel counts for it.",
}


def _r(x, n=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def _official():
    out = {}
    for lang, countries in OFFICIAL_IN.items():
        for cc in countries:
            out.setdefault(cc, []).append(lang)
    return out


def lookalike_entries(lookalikes, profiles):
    """Every look-alike examined, with whether its Qloo fan map is used, why not, and its request id (provenance)."""
    out = []
    for x in lookalikes:
        valid = x.get("status") == "valid"
        has_map = bool(x.get("qloo_id")) and (valid or x.get("status") == "default map")
        prof = profiles.get(str(x.get("appid"))) if valid else None
        out.append({"appid": x.get("appid"), "name": x.get("name"), "qloo_id": x.get("qloo_id"),
                    "status": x.get("status"), "usable": valid,
                    "reason": None if valid else REJECTED.get(x.get("status"), f"Not used: {x.get('status')}."),
                    "request": qloo.heatmap_id(x["name"], x["qloo_id"]) if has_map else None,
                    "countries_with_score": len(prof["affinity"]) if prof else 0,
                    "cells": sum(prof.get("cells", {}).values()) if prof else None})
    return out


def country_rows(profiles, reference):
    """{country: row} for every country with a Qloo score, a model language or an official target language."""
    lang_of = {cc: lang for lang, ccs in COUNTRIES.items() for cc in ccs}
    official, ref = _official(), (reference or {}).get("countries", {})
    scores = {}
    for key, prof in profiles.items():
        for cc, aff in prof["affinity"].items():
            scores.setdefault(cc, {})[key] = {"affinity": aff, "popularity": prof.get("popularity", {}).get(cc),
                                              "cells": prof.get("cells", {}).get(cc)}
    rows = {}
    for cc in sorted(set(scores) | set(lang_of) | set(official)):
        per, r = scores.get(cc, {}), ref.get(cc)
        usable_ref = bool(r) and r["lookalikes"] >= REFERENCE_MIN and r["affinity"] > 0
        mean = float(np.mean([v["affinity"] for v in per.values()])) if per else None
        lang = lang_of.get(cc)
        rows[cc] = {
            "model_language": lang,
            "population_m": POP[cc] if lang else None,
            "official_languages": official.get(cc, []),
            "affinity": _r(mean),
            "relative": _r(mean / r["affinity"], 3) if per and usable_ref else None,
            "lookalikes_with_score": len(per),
            "reference": {"affinity": _r(r["affinity"]), "lookalikes": r["lookalikes"], "usable": usable_ref}
            if r else None,
            "by_lookalike": {key: {"affinity": _r(v["affinity"]), "popularity": _r(v["popularity"]),
                                   "cells": v["cells"],
                                   "relative": _r(v["affinity"] / r["affinity"], 3) if usable_ref else None}
                             for key, v in per.items()},
        }
    return rows


def language_rows(profiles, prior, base, alpha=P.ALPHA):
    """{language: the calculation behind its estimated share}, with babel.plan's functions (so it equals the plan)."""
    signals = {key: P.comp_signal(prof["affinity"]) for key, prof in profiles.items()}
    lift = P.qloo_lift(list(signals.values()), base)
    shares = P.demand_shares(prior, lift, alpha)
    baseline = prior.reindex(P.LANGS) / prior.sum()
    product = baseline * lift.reindex(P.LANGS) ** alpha
    rows = {}
    for lang in P.LANGS:
        have = [float(s[lang]) for s in signals.values() if not np.isnan(s[lang])]
        rows[lang] = {
            "language": LABEL[lang], "countries": COUNTRIES[lang],
            "population_m": {cc: POP[cc] for cc in COUNTRIES[lang]},
            "official_in": OFFICIAL_IN[lang],
            "s1": {key: _r(s[lang]) for key, s in signals.items()},
            "mean_s1": _r(np.mean(have)) if have else None, "reference_s1": _r(base[lang]),
            "lift": round(float(lift[lang]), 3), "baseline_share": round(float(baseline[lang]), 4),
            "baseline_x_lift": round(float(product[lang]), 5), "estimated_share": round(float(shares[lang]), 4),
        }
    return rows, round(float(product.sum()), 5)


def map_data(lookalikes, prior, base, reference=None, alpha=P.ALPHA, profile=None):
    """The Plan screen's map: every look-alike examined (valid or not), per-country Qloo evidence, per-language
    calculations, and how they were made. `lookalikes` as in the plan; only valid ones' fan maps are read (cached)."""
    profile = profile or qloo.game_profile
    valid = [x for x in lookalikes if x.get("status") == "valid"]
    profiles = {}
    for x in valid:  # the affinities the plan used, plus each fan map's cell counts and popularity
        prof = profile(x["name"], x["qloo_id"])
        profiles[str(x["appid"])] = {**prof, "affinity": x.get("affinity", prof["affinity"])}
    languages, total = language_rows(profiles, prior, base, alpha)
    countries = country_rows(profiles, reference)
    return {
        "v": VERSION, "status": "ok" if profiles else "no_data",
        "lookalikes": lookalike_entries(lookalikes, profiles),
        "countries": countries, "countries_with_score": sum(r["affinity"] is not None for r in countries.values()),
        "languages": languages, "baseline_x_lift_sum": total, "alpha": alpha,
        "min_cells": qloo.MIN_CELLS, "reference": {"lookalikes": (reference or {}).get("lookalikes"),
                                                   "min_lookalikes": REFERENCE_MIN, "available": bool(reference)},
        "method": METHOD, "sources": SOURCES,
    }


def cost_breakdown(p):
    """{language: each step of its two cost estimates}, from the plan's own rates and word count (babel.plan's
    full_cost and store_cost), so the Plan screen shows the calculation without redoing it."""
    r, words = p["rates"], p["inputs"]["word_count"]
    out = {}
    for x in p["languages"]:
        lang, rate = x["code"], r["per_word"][x["code"]]
        full_words = words + r["store_page_words"]
        out[lang] = {
            "rate_per_word": rate, "game_words": words, "store_page_words": r["store_page_words"],
            "full_words": full_words, "full_before_qa": round(full_words * rate, 2),
            "min_fee": r["min_fee"], "min_fee_applies": full_words * rate < r["min_fee"],
            "qa_overhead": r["qa_overhead"], "cost_full": x["cost_full"],
            "store_page_before_min": round(r["store_page_words"] * rate, 2),
            "store_min_fee_applies": r["store_page_words"] * rate < r["min_fee"],
            "cost_store_page": x["cost_store_page"],
        }
    return out


# ---------------------------------------------------------------- Babel vs the generic list
def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def versus_generic(p, prior):
    """Babel's ranking against the copy-pasted tier list (languages.GENERIC), language by language: where the
    typical mix alone would put it (the baseline), and how Qloo's lift moved it. Pure and budget-independent."""
    rows = {x["code"]: x for x in p["languages"]}
    baseline_rank = {lang: i + 1 for i, lang in enumerate(P.rank(prior.reindex(P.LANGS) / prior.sum()))}
    out = []
    for lang in P.LANGS:
        x, g, b0 = rows[lang], GENERIC.index(lang) + 1, baseline_rank[lang]
        b, lift, name = x["rank"], x["qloo_lift"], LABEL[lang]
        strong = bool(x["lookalikes_with_data"]) and abs(lift - 1) >= NEAR
        why = [f"Typical mix: {x['baseline_share']:.1%} of non-English reviews, {_ordinal(b0)}" + (
            f" (generic list: {_ordinal(g)})." if b0 != g else " (the same place as on the generic list).")]
        qloo_part = ("No Qloo data for its countries (lift ×1.00)" if not x["lookalikes_with_data"] else
                     f"Qloo lift ×{lift:.2f}" + (f": fans of the look-alikes are {'more' if lift > 1 else 'less'} "
                                                 "over-represented there than fans of typical games" if strong else
                                                 " (about average)"))
        if b == b0:
            why.append(f"{qloo_part}; it stays {_ordinal(b)}.")
        elif strong and (lift > 1) == (b < b0):
            why.append(f"{qloo_part}, moving it {'up' if b < b0 else 'down'} to {_ordinal(b)}.")
        else:
            why.append(f"{qloo_part}; other languages' lifts move it {'up' if b < b0 else 'down'} to {_ordinal(b)}.")
        out.append({"code": lang, "language": name, "generic_rank": g, "baseline_rank": b0, "babel_rank": b,
                    "places": g - b, "baseline_share": x["baseline_share"], "estimated_share": x["estimated_share"],
                    "qloo_lift": lift, "steam_users": round(STEAM_SHARE[lang] / 100, 4), "group": x["group"],
                    "why": " ".join(why)})
    out.sort(key=lambda r: r["babel_rank"])
    babel_top, generic_top = [r["code"] for r in out[:3]], GENERIC[:3]
    return {
        "rows": out, "babel_top3": babel_top, "generic_top3": generic_top,
        "same_top3": set(babel_top) == set(generic_top),
        "about": "The generic list is the tier list many developers copy (Chinese, Japanese and Korean first): the "
                 "same for every game. Babel starts from the typical mix (the share of non-English Steam reviews that "
                 "English-only indie games actually receive) and adjusts it with Qloo fan maps of games like yours.",
        "caveat": "The typical mix comes from reviews of English-only games, so it under-counts players who only buy "
                  "translated games (especially Chinese, Japanese and Korean); Steam's user share is shown for that "
                  "context.",
    }
