"""Babel's planning engine: game -> look-alikes -> per-language demand -> costs -> budget plan + evidence object.

Deterministic; every number comes from code, never from an LLM. The demand model is the one the pre-registered
backtest validated (backtest/PREREGISTRATION.md, backtest/final_report.md): the typical language mix of English-only
indie games x (Qloo S1 lift of the game's look-alikes)^alpha, with alpha = 1. Costs come from editable per-word rates
(estimates, not quotes). Scoring, costs and the optimizer are pure functions; only plan() and its helpers do I/O.

  python -m babel.plan --appid 3146520 --words 30000 --budget 10000
  python -m babel.plan --name "Dawnsbury Days" --words 200000 --budget 40000
  python -m babel.plan --lookalikes 413150,1135690 --words 30000 --budget 8000   # a game without a store page
  python -m babel.plan --description "A cozy farming game..." --words 30000 --budget 8000   # text only
  python -m babel.plan --examples                                                # three example games
  python -m babel.plan --description-examples                                    # three example descriptions
Add --markets for market notes (babel/markets.py) and --json to print the full evidence object.
"""
import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from . import comps, describe, markets, qloo, steam
from .languages import COUNTRIES, GENERIC, LABEL, POP, STORE_NAME, TARGETS

ROOT = Path(__file__).resolve().parent.parent
BACKTEST_DATA = ROOT / "backtest" / "data"
LANGS = list(TARGETS)
ALPHA = 1  # S1 with alpha = 1, chosen on the dev games of both truths (backtest/final_report.md)
SIGNAL = "S1: look-alike fan maps (affinity)"
MIN_SHARE = 0.01  # product default, editable: languages under 1% of estimated non-English demand are skipped
MAX_WORDS = 5_000_000
EPS = 1e-9
DEFAULT_PER_WORD = {"schinese": 0.12, "tchinese": 0.12, "japanese": 0.14, "koreana": 0.13, "brazilian": 0.10,
                    "russian": 0.10, "spanish": 0.11, "turkish": 0.10, "german": 0.12, "french": 0.12,
                    "polish": 0.10, "italian": 0.11, "ukrainian": 0.09, "thai": 0.11}  # USD per word, illustrative
GROUPS = {"translate_game": "Translate the game", "store_page_only": "Store page only", "skip": "Skip for now",
          "already_supported": "Already supported"}
TRACK_RECORD = {
    "source": "backtest/final_report.md",
    "steam_reviews": {"test_games": 71, "babel_top3_coverage": 0.489, "typical_mix_top3_coverage": 0.477,
                      "sign_test_p": "0.500", "verdict": "Qloo adds a weak signal only"},
    "wikipedia_pageviews": {"test_games": 186, "babel_top3_coverage": 0.601, "typical_mix_top3_coverage": 0.574,
                            "sign_test_p": "< 0.001", "verdict": "Qloo adds value"},
}
CAVEATS = [
    "Shares are estimates of where non-English demand is, not sales, wishlists or player counts.",
    "The baseline comes from Steam reviews of English-only games, which under-count players who need a translation "
    "(especially Chinese, Japanese and Korean).",
    "On small English-only indie games, Qloo's improvement over the baseline was small and not significant "
    "(backtest: +1.2 points of top-3 coverage, p = 0.50).",
    "Costs are estimates from editable per-word rates, not quotes.",
]
EXAMPLES = [(3146520, 30_000, 10_000), (2693730, 200_000, 40_000), (3169580, 60_000, 15_000)]


class PlanError(ValueError):
    """Invalid input; the message is safe to show to the user."""


def _number(x):
    return isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool) and math.isfinite(x)


# ---------------------------------------------------------------- inputs and costs
def check_inputs(word_count, budget, min_share=MIN_SHARE, alpha=ALPHA):
    """Raise PlanError unless the word count is a whole number in range and the budget is a number >= 0."""
    if not _number(word_count) or word_count != int(word_count) or not 1 <= word_count <= MAX_WORDS:
        raise PlanError(f"Word count must be a whole number from 1 to {MAX_WORDS:,}.")
    if not _number(budget):
        raise PlanError("Budget must be a number (USD).")
    if budget < 0:
        raise PlanError("Budget cannot be negative.")
    if not _number(min_share) or not 0 <= min_share < 1:
        raise PlanError("The demand threshold must be from 0 to 1.")
    if not _number(alpha) or alpha < 0:
        raise PlanError("alpha must be zero or more.")


@dataclass(frozen=True)
class Rates:
    """Editable cost assumptions in USD. Illustrative defaults, not quotes: use your vendor's rates."""
    per_word: dict = field(default_factory=lambda: dict(DEFAULT_PER_WORD))
    store_page_words: int = 500  # store page text (short + long description), translated with every language
    qa_overhead: float = 0.15  # review and in-game linguistic QA, as a share of a full translation
    min_fee: float = 50.0  # minimum charge per language and job

    def check(self):
        bad = [LABEL[l] for l in LANGS if not (_number(self.per_word.get(l)) and self.per_word[l] > 0)]
        if bad:
            raise PlanError(f"Missing or invalid per-word rate for: {', '.join(bad)}.")
        if not (isinstance(self.store_page_words, int) and self.store_page_words > 0):
            raise PlanError("Store page word count must be a whole number above 0.")
        if not (_number(self.qa_overhead) and self.qa_overhead >= 0 and _number(self.min_fee) and self.min_fee >= 0):
            raise PlanError("QA overhead and minimum fee must be zero or more.")


def full_cost(lang, words, rates):
    """Whole game + store page: max(min_fee, (words + store_page_words) x rate) x (1 + qa_overhead)."""
    return round(max(rates.min_fee, (words + rates.store_page_words) * rates.per_word[lang])
                 * (1 + rates.qa_overhead), 2)


def store_cost(lang, rates):
    """Store page only: max(min_fee, store_page_words x rate)."""
    return round(max(rates.min_fee, rates.store_page_words * rates.per_word[lang]), 2)


# ---------------------------------------------------------------- demand scores (the backtested model)
def comp_signal(affinity):
    """One look-alike's S1 signal per language: population-weighted mean Qloo affinity over the language's countries
    (NaN where its fan map has none of them). Same as the backtest's lang_scores."""
    out = {}
    for l in LANGS:
        have = [c for c in COUNTRIES[l] if c in affinity]
        out[l] = sum(affinity[c] * POP[c] for c in have) / sum(POP[c] for c in have) if have else np.nan
    return pd.Series(out, dtype=float)


def qloo_lift(signals, base):
    """Per language: the look-alikes' mean signal / the backtest look-alikes' mean signal; 1 where there is no data."""
    if not signals:
        return pd.Series(1.0, index=LANGS)
    return (pd.DataFrame(signals).mean() / base).reindex(LANGS).fillna(1.0)


def demand_shares(prior, lift, alpha=ALPHA):
    """Estimated share of non-English demand per language: prior x lift^alpha, scaled to sum to 1."""
    s = prior.reindex(LANGS) * lift.reindex(LANGS).fillna(1.0) ** alpha
    if s.isna().any() or (s < 0).any() or s.sum() <= 0:
        raise ValueError("prior and lift must be non-negative numbers for every language")
    return s / s.sum()


def rank(scores):
    """Languages by score, highest first; ties in the generic list's order (as in the backtest)."""
    s = scores.reindex(LANGS).fillna(-np.inf)
    return sorted(LANGS, key=lambda l: (-s[l], GENERIC.index(l)))


# ---------------------------------------------------------------- budget optimizer
def best_subset(values, costs, budget):
    """Exact 0/1 knapsack: the keys whose values sum highest with total cost <= budget. Every subset is checked
    (fine up to 20 items). Ties go to the cheaper set. Returns keys in input order."""
    keys = list(values)
    if len(keys) > 20:
        raise ValueError("best_subset checks every subset: at most 20 items")
    # value and cost of every subset, indexed by its bit mask (bit i = keys[i]); added from the highest bit down
    val, cost, masks = np.zeros(1), np.zeros(1), np.zeros(1, dtype=np.int64)
    for i in range(len(keys) - 1, -1, -1):
        val = np.concatenate([val, val + values[keys[i]]])
        cost = np.concatenate([cost, cost + costs[keys[i]]])
        masks = np.concatenate([masks, masks | (1 << i)])
    order = np.argsort(masks)
    val, cost = np.round(val[order], 12), np.round(cost[order], 6)
    fits = cost <= budget + EPS
    fits[0] = True  # the empty set is always allowed (even for a negative budget)
    best = fits & (val == val[fits].max())
    best &= cost == cost[best].min()
    best = int(np.flatnonzero(best)[0])  # remaining ties: the lowest mask, as a scan from the empty set would keep
    return [k for i, k in enumerate(keys) if best >> i & 1]


def allocate(shares, cost_full, cost_store, budget, min_share=MIN_SHARE, supported=()):
    """Split the languages into groups under the budget.

    1. Translate the game: the set of full translations that covers the most estimated demand within the budget.
    2. Store page only: the same, among the remaining languages, with the budget left over.
    3. Skip for now: the rest. Languages under min_share are skipped whatever the budget.
    Languages the game already supports are left out. Returns ({group: languages in rank order}, {language: reason}).
    """
    order = rank(shares)
    eligible = [l for l in order if l not in supported and shares[l] >= min_share and shares[l] > 0]
    full = set(best_subset({l: shares[l] for l in eligible}, {l: cost_full[l] for l in eligible}, budget))
    left = budget - sum(cost_full[l] for l in full)
    rest = [l for l in eligible if l not in full]
    store = set(best_subset({l: shares[l] for l in rest}, {l: cost_store[l] for l in rest}, left))
    left -= sum(cost_store[l] for l in store)
    groups = {"translate_game": [l for l in order if l in full], "store_page_only": [l for l in order if l in store],
              "skip": [l for l in order if l not in supported and l not in full and l not in store],
              "already_supported": [l for l in order if l in supported]}
    reasons = {}
    for l in order:
        if l in supported:
            reasons[l] = "The game already supports this language."
        elif l in full:
            reasons[l] = (f"In the set of full translations that covers the most estimated demand within the budget "
                          f"(${cost_full[l]:,.0f}).")
        elif l in store:
            reasons[l] = (f"A full translation (${cost_full[l]:,.0f}) is not in the best set for this budget; "
                          f"the store page (${cost_store[l]:,.0f}) fits in what is left: a cheap test of this market.")
        elif l not in eligible:
            reasons[l] = f"Estimated demand ({shares[l]:.1%}) is under the {min_share:.1%} threshold."
        else:
            reasons[l] = (f"Not enough budget left (${max(left, 0):,.0f}) for its store page "
                          f"(${cost_store[l]:,.0f}).")
    return groups, reasons


def fit_budget(shares, cost_full, cost_store, budget, min_share=MIN_SHARE, supported=()):
    """The budget-dependent part of a plan: groups, reasons, costs, estimated coverage and status (pure).

    build_plan uses it, and so does POST /fit-budget (the Plan screen's budget slider) with the plan's own unrounded
    shares and costs (its 'allocation' object), so a new budget gives exactly the plan the engine would make for it.
    """
    shares = pd.Series(shares, dtype=float).reindex(LANGS)
    supported = [l for l in LANGS if l in supported]
    groups, reasons = allocate(shares, cost_full, cost_store, budget, min_share, supported)
    spent_full = round(sum(cost_full[l] for l in groups["translate_game"]), 2)
    spent_store = round(sum(cost_store[l] for l in groups["store_page_only"]), 2)
    eligible = [l for l in LANGS if l not in supported and shares[l] >= min_share and shares[l] > 0]
    status, message = _budget_status(groups, eligible, cost_full, cost_store, budget)
    return {
        "status": status, "message": message, "groups": groups, "reasons": reasons,
        "costs": {"translate_game": spent_full, "store_page_only": spent_store,
                  "total": round(spent_full + spent_store, 2), "budget": budget,
                  "unspent": round(budget - spent_full - spent_store, 2)},
        "estimated_coverage": {
            "translate_game": round(float(shares[groups["translate_game"]].sum()), 4),
            "store_page_only": round(float(shares[groups["store_page_only"]].sum()), 4),
            "meaning": "Estimated share of non-English demand in each group's languages; an estimate, not sales. "
                       "A store page alone does not let these players play in their language."},
    }


# ---------------------------------------------------------------- plan + evidence (pure)
def build_plan(game, lookalikes, word_count, budget, prior, base, rates=None, min_share=MIN_SHARE, alpha=ALPHA,
               widened=False, notes=(), n_base=None, discovery=None):
    """The plan and its evidence object from resolved inputs (no I/O).

    game: {'appid', 'name', 'release_date', 'supported': [codes], 'tags': {tag: votes}, 'source'}.
    lookalikes: every look-alike examined, {'appid', 'name', 'qloo_id', 'status', 'overlap'}; valid ones also carry
    'affinity' ({country: Qloo affinity} from their world fan map). prior, base: Series over the 14 languages.
    discovery: how look-alikes were found from a description (babel/describe.py), or None.
    """
    rates = rates or Rates()
    check_inputs(word_count, budget, min_share, alpha)
    rates.check()
    valid = [l for l in lookalikes if l.get("status") == "valid"]
    signals = [comp_signal(l["affinity"]) for l in valid]
    lift = qloo_lift(signals, base)
    own = pd.DataFrame([s / base for s in signals]).reindex(columns=LANGS) if signals else None
    shares = demand_shares(prior, lift, alpha)
    cf = {l: full_cost(l, word_count, rates) for l in LANGS}
    cs = {l: store_cost(l, rates) for l in LANGS}
    supported = [l for l in game.get("supported", []) if l in TARGETS]
    fit = fit_budget(shares, cf, cs, budget, min_share, supported)
    groups, reasons = fit["groups"], fit["reasons"]
    group_of = {l: g for g, ls in groups.items() for l in ls}
    level = "none" if not valid else "low" if len(valid) < 3 else "normal"
    messages = _evidence_messages(level, len(valid), widened, notes) + ([fit["message"]] if fit["message"] else [])

    languages = []
    for i, l in enumerate(rank(shares)):
        has = own[l].dropna() if own is not None else pd.Series(dtype=float)
        languages.append({
            "code": l, "language": LABEL[l], "rank": i + 1, "group": group_of[l], "reason": reasons[l],
            "estimated_share": round(float(shares[l]), 4), "baseline_share": round(float(prior[l]) / prior.sum(), 4),
            "qloo_lift": round(float(lift[l]), 3), "lookalikes_with_data": int(len(has)),
            "lift_range": [round(float(has.min()), 3), round(float(has.max()), 3)] if len(has) else None,
            "cost_full": cf[l], "cost_store_page": cs[l]})
    disagree = [x["code"] for x in languages if x["lift_range"] and x["lift_range"][0] < 1 < x["lift_range"][1]]
    return {
        "status": fit["status"], "messages": messages,
        "game": {"appid": game.get("appid"), "name": game.get("name"), "release_date": game.get("release_date"),
                 "source": game.get("source"), "supported_languages": supported,
                 "top_tags": list(game.get("tags") or {})[:10]},
        "inputs": {"word_count": int(word_count), "budget_usd": budget, "min_share": min_share, "alpha": alpha,
                   "signal": SIGNAL},
        "lookalikes": {"used": [_public(l) for l in valid], "evidence_level": level, "widened_search": widened,
                       "rejected": [_public(l) for l in lookalikes if l.get("status") != "valid"]},
        "groups": groups, "languages": languages, "costs": fit["costs"],
        "estimated_coverage": fit["estimated_coverage"],
        "allocation": {"shares": {l: float(shares[l]) for l in LANGS}, "cost_full": cf, "cost_store_page": cs,
                       "min_share": min_share, "supported": supported,
                       "meaning": "Unrounded estimated shares and the costs the budget optimizer used: send them "
                                  "with a new budget to POST /fit-budget to re-fit the plan exactly "
                                  "(babel.plan.fit_budget)."},
        "rates": asdict(rates), "formulas": _formulas(n_base), "sources": _sources(n_base),
        "uncertainty": {"evidence_level": level, "lookalikes_disagree_on": disagree, "caveats": CAVEATS},
        "discovery": discovery, "track_record": TRACK_RECORD,
    }


def _public(look):
    return {k: look.get(k) for k in ("appid", "name", "qloo_id", "status", "overlap")}


def _evidence_messages(level, n_valid, widened, notes):
    """Plain notes about the evidence behind a plan (the budget's own note comes from _budget_status)."""
    messages = list(notes)
    if level == "none":
        messages.append("No Qloo fan data for games like this: the plan uses the typical language mix of "
                        "English-only indie games.")
    elif level == "low":
        messages.append(f"Based on {n_valid} look-alike game(s) with Qloo fan data (3 is normal): low evidence.")
    if widened:
        messages.append("Look-alikes came from a wider search than the backtest used (12 best tag matches, not 6).")
    return messages


def _budget_status(groups, eligible, cf, cs, budget):
    """(status, note or None): ok / store_pages_only / nothing_affordable / nothing_to_translate."""
    if groups["translate_game"]:
        return "ok", None
    if not eligible:
        return "nothing_to_translate", "Every target language is already supported or under the demand threshold."
    if budget == 0:
        return "nothing_affordable", "The budget is $0: nothing can be translated yet."
    cheapest = min(eligible, key=lambda l: cf[l])
    if groups["store_page_only"]:
        return "store_pages_only", (f"No full translation fits the budget: the cheapest is {LABEL[cheapest]} at "
                                    f"${cf[cheapest]:,.0f}.")
    return "nothing_affordable", (f"The budget (${budget:,.0f}) is under the cheapest store page "
                                  f"(${min(cs[l] for l in eligible):,.0f}).")


def _formulas(n_base):
    ref = f"the {n_base} look-alikes of the Steam backtest" if n_base else "the Steam backtest's look-alikes"
    return {
        "signal": "S1(c, L) = population-weighted mean Qloo affinity over L's countries "
                  "on look-alike c's world fan map",
        "lift": f"lift(L) = mean over look-alikes of S1(c, L) / mean over {ref} of S1(c, L); 1 where there is no data",
        "estimated_share": "share(L) = baseline(L) x lift(L)^alpha / sum over languages, alpha = 1",
        "cost_full": "max(min_fee, (word_count + store_page_words) x rate(L)) x (1 + qa_overhead)",
        "cost_store_page": "max(min_fee, store_page_words x rate(L))",
        "optimizer": "1) full translations: the set with the most estimated share whose cost fits the budget (exact); "
                     "2) store pages: the same among the rest with the budget left; under min_share: skipped",
    }


def _sources(n_base):
    return {
        "baseline": "backtest/data/truth_reviews.csv: mean share of non-English Steam reviews per language, "
                    "114 English-only indie games released 2023+",
        "lift_reference": f"backtest/data/comps.csv: {n_base or 'the'} look-alikes of the Steam backtest set",
        "qloo": "Qloo world heatmaps (urn:heatmap) of the look-alike games",
        "alpha": "backtest/final_report.md: S1 and alpha = 1 chosen on dev games",
        "rates": "Illustrative defaults in babel/plan.py, not quotes",
    }


# ---------------------------------------------------------------- runtime data and resolution (I/O)
def typical_mix(appids=None):
    """Mean share of non-English Steam reviews per target language (one vote per game) over the backtest's
    English-only indie games: all of them, or the given appids."""
    reviews = pd.read_csv(BACKTEST_DATA / "truth_reviews.csv").set_index("appid")
    counts = pd.DataFrame({t: reviews[[f"rev_{c}" for c in codes]].sum(axis=1) for t, codes in TARGETS.items()})
    shares = counts.div(counts.sum(axis=1), axis=0)
    return (shares if appids is None else shares.loc[sorted(appids)]).mean()


def comp_affinity(name, qloo_id):
    """Per-country affinity on a look-alike's world fan map (the API response itself is cached on disk)."""
    return qloo.game_profile(name, qloo_id)["affinity"]


def lift_base():
    """(mean S1 signal per language over the Steam backtest's look-alikes, how many): every lift is relative to it."""
    used = pd.read_csv(BACKTEST_DATA / "comps.csv").drop_duplicates("qloo_id")
    signals = [comp_signal(comp_affinity(r.comp_name, r.qloo_id)) for r in used.itertuples()]
    return pd.DataFrame(signals).mean(), len(used)


def country_reference():
    """Per country: the mean Qloo affinity over the Steam backtest's look-alikes with a score there, and how many have
    one. The same games as the lift reference, one country at a time: the map's 'vs typical games' view (display
    only; the language scores use lift_base)."""
    used = pd.read_csv(BACKTEST_DATA / "comps.csv").drop_duplicates("qloo_id")
    table = pd.DataFrame([comp_affinity(r.comp_name, r.qloo_id) for r in used.itertuples()])
    return {"countries": {cc: {"affinity": float(table[cc].mean()), "lookalikes": int(table[cc].notna().sum())}
                          for cc in table.columns},
            "lookalikes": len(used)}


class Context:
    """Runtime data, loaded lazily: the baseline, the lift reference (and its per-country version for the map), the
    default-map fingerprint and the look-alike pool. Built from the committed backtest data and the API cache (no
    network once cached; about 30 s). babel/runtime.py saves the same data precomputed, loaded in about a second."""
    source = "the API cache"

    @cached_property
    def prior(self):
        return typical_mix()

    @cached_property
    def base(self):
        return lift_base()

    @cached_property
    def country_reference(self):
        return country_reference()

    @cached_property
    def default_map(self):
        return qloo.default_fingerprint()

    @cached_property
    def picker(self):
        return comps.CompPicker(log=lambda *a: None)


_CONTEXT = None


def context():
    """The runtime data, loaded once: the precomputed files in data/runtime/ when they are current, else a Context
    built lazily from the backtest data and the API cache. BABEL_REQUIRE_RUNTIME=1 (a deployment, which carries only
    part of the cache) refuses that fallback, which would mean thousands of live requests."""
    global _CONTEXT
    if _CONTEXT is None:
        from . import runtime  # babel.runtime imports this module
        try:
            _CONTEXT = runtime.load()
        except runtime.Unavailable as e:
            if os.environ.get("BABEL_REQUIRE_RUNTIME", "") in ("1", "true", "yes"):
                raise RuntimeError(f"Precomputed runtime data required (BABEL_REQUIRE_RUNTIME) but not usable: {e}") from e
            print(f"Precomputed runtime data not used: {e}. Loading it from the API cache.", file=sys.stderr)
            _CONTEXT = Context()
    return _CONTEXT


def find_game(name):
    """(Steam appid, approximate?) for a name: an exact title match in the store search, else the top result."""
    items = [i for i in steam.search(name) if i.get("type") == "app"]
    if not items:
        raise PlanError(f"No Steam game found for '{name}'.")
    exact = [i for i in items if qloo.title_key(i["name"]) == qloo.title_key(name)]
    return int((exact or items)[0]["id"]), not exact


def game_info(appid):
    """Name, release date, supported target languages and SteamSpy tags of a Steam game."""
    d = steam.appdetails(appid)
    if not d:
        raise PlanError(f"Steam has no store data for app {appid}.")
    released = steam.release_date(d)
    supported = {STORE_NAME[x] for x in steam.languages(d) if x in STORE_NAME}
    return {"appid": int(appid), "name": d.get("name", ""), "release_date": released.isoformat() if released else None,
            "supported": [l for l in LANGS if l in supported], "tags": comps.spy_tags(appid), "source": "steam",
            "description": d.get("short_description") or ""}


def user_lookalike(appid, default_map):
    """A look-alike the user chose (Steam appid): its name and whether Qloo has a real fan map for it."""
    d = steam.appdetails(appid)
    if not d:
        return {"appid": int(appid), "name": None, "qloo_id": None, "status": "not on Steam", "overlap": None}
    status, qloo_id = comps.qloo_status(d["name"], default_map)
    return {"appid": int(appid), "name": d["name"], "qloo_id": qloo_id, "status": status, "overlap": None}


def examine_lookalikes(picker, tags, exclude=None, top=6):
    """Every look-alike examined among the `top` best tag matches that share at least one tag: up to 3 valid ones
    (best first), then the rejected ones with their Qloo status."""
    keep = 3 + (exclude in picker.weights_of)
    used = [c for c in picker.pick(tags, top=top, keep=keep, min_overlap=0) if c["comp_appid"] != exclude][:3]
    w = picker.weights(tags)
    window = [a for a in sorted(picker.weights_of, key=lambda a: -comps.overlap(w, picker.weights_of[a]))[:top]
              if comps.overlap(w, picker.weights_of[a]) > 0]
    rejected = [{"appid": a, "name": picker.names[a], "qloo_id": picker.status[a][1], "status": picker.status[a][0],
                 "overlap": round(comps.overlap(w, picker.weights_of[a]), 4)}
                for a in window if a != exclude and a in picker.status and picker.status[a][0] != "valid"]
    return [{"appid": c["comp_appid"], "name": c["comp_name"], "qloo_id": c["qloo_id"], "status": "valid",
             "overlap": c["overlap_score"]} for c in used] + rejected


def n_valid(looks):
    return sum(x["status"] == "valid" for x in looks)


def pick_lookalikes(picker, tags, exclude=None):
    """Up to 3 valid look-alikes among the 6 best tag matches (the backtested rule); if fewer than 2, among the 12
    best (a product fallback, not backtested). Returns (every look-alike examined, widened?)."""
    examined = examine_lookalikes(picker, tags, exclude, 6)
    if n_valid(examined) >= 2:
        return examined, False
    wider = examine_lookalikes(picker, tags, exclude, 12)
    return wider, n_valid(wider) > n_valid(examined)


def plan(word_count, budget, appid=None, name=None, lookalikes=None, tags=None, description=None, rates=None,
         min_share=MIN_SHARE, ctx=None):
    """A costed localization plan for one game; returns the evidence object (a JSON-ready dict).

    Give a Steam appid or a game name, and/or your own look-alikes (Steam appids); for a game without a store page,
    Steam-style tags ({tag: weight} or a list) or a free-text description (Claude turns it into tags and candidate
    look-alikes, which code verifies: babel/describe.py). Raises PlanError for invalid input.
    """
    check_inputs(word_count, budget, min_share)
    (rates or Rates()).check()
    if description is not None and describe.description_problem(description):
        raise PlanError(describe.description_problem(description))
    if appid is None and not name and not lookalikes and not tags and not description:
        raise PlanError("Give a Steam app ID, a game name, a description, look-alike games or tags.")
    ctx = ctx or context()
    notes = []
    if appid is None and name:
        appid, approximate = find_game(name)
        if approximate:
            notes.append(f"No exact Steam match for '{name}': using the top search result.")
    game = game_info(appid) if appid is not None else {
        "appid": None, "name": "Your game", "release_date": None, "supported": [], "tags": {}, "source": "input"}
    if tags:
        game["tags"] = dict(tags) if isinstance(tags, dict) else {t: 1 for t in tags}
    widened, discovery = False, None
    if description and appid is None and not tags and not lookalikes:
        discovery = describe.discover(description, ctx.picker)
        looks, widened = discovery.pop("lookalikes"), discovery["widened_search"]
        game.update(name="Your game (from a description)", tags=discovery["tag_weights"], source="description")
        notes += discovery_notes(discovery)
    elif lookalikes:
        looks = [user_lookalike(int(a), ctx.default_map) for a in dict.fromkeys(lookalikes)]
        notes.append("Look-alikes chosen by you.")
    elif game["tags"]:
        looks, widened = pick_lookalikes(ctx.picker, game["tags"], exclude=game["appid"])
    else:
        looks = []
        notes.append("No Steam tags found, so no look-alike games: add tags or pick look-alikes.")
    if description and discovery is None:
        notes.append("Description not used: the plan uses the Steam page, tags or look-alikes you gave.")
    for look in looks:
        if look["status"] == "valid":
            look["affinity"] = comp_affinity(look["name"], look["qloo_id"])
    base, n_base = ctx.base
    return build_plan(game, looks, int(word_count), budget, ctx.prior, base, rates, min_share, ALPHA, widened,
                      notes, n_base, discovery)


def discovery_notes(d):
    """Plain notes about how look-alikes were found from a description, and what to do when evidence is weak."""
    notes = [f"Tags and candidate look-alikes were inferred from your description by Claude, then checked against "
             f"Steam and Qloo. Look-alike confidence: {d['confidence']['level']}."]
    if d["needs_user_choice"]:
        hint = ", ".join(f"{a['name']} ({a['appid']})" for a in d["alternatives"][:4])
        notes.append("Weak evidence: " + " ".join(d["confidence"]["reasons"]) + " Please choose comparable games "
                     "yourself (Steam app IDs with --lookalikes)" + (f"; candidates: {hint}." if hint else "."))
    elif d["confidence"]["reasons"]:
        notes.append("Check the look-alikes: " + " ".join(d["confidence"]["reasons"]))
    return notes


# ---------------------------------------------------------------- CLI
def render(p):
    """The plan as readable text."""
    g, inp, look = p["game"], p["inputs"], p["lookalikes"]
    title = g["name"] + (f" (Steam {g['appid']})" if g["appid"] else "")
    out = [f"{title}: {inp['word_count']:,} words, budget ${inp['budget_usd']:,.0f}"]
    if p.get("discovery"):
        d = p["discovery"]
        out.append(f"Inferred tags: {', '.join(d['inferred_tags']) or 'none'}   [look-alike confidence: "
                   f"{d['confidence']['level']}]")
    out.append("Look-alikes with Qloo fan maps: " + (", ".join(x["name"] for x in look["used"]) or "none")
               + f"   [evidence: {look['evidence_level']}]")
    if look["rejected"]:
        out.append("Skipped look-alikes: " + ", ".join(f"{x['name']} ({x['status']})" for x in look["rejected"]))
    out += ["", f"{'#':>2}  {'Language':<20}{'Est. share':>10}{'Qloo lift':>10}{'Full game':>11}"
            f"{'Store page':>11}  Plan"]
    for x in p["languages"]:
        out.append(f"{x['rank']:>2}  {x['language']:<20}{x['estimated_share']:>10.1%}{x['qloo_lift']:>10.2f}"
                   f"{x['cost_full']:>11,.0f}{x['cost_store_page']:>11,.0f}  {GROUPS[x['group']]}")
    c, cov = p["costs"], p["estimated_coverage"]
    names = lambda key: ", ".join(LABEL[l] for l in p["groups"][key]) or "none"  # noqa: E731
    out += ["", f"Translate the game: {names('translate_game')} (${c['translate_game']:,.0f})",
            f"Store page only:    {names('store_page_only')} (${c['store_page_only']:,.0f})",
            f"Skip for now:       {names('skip')}",
            f"Spent ${c['total']:,.0f} of ${c['budget']:,.0f} (cost estimates). Full translations cover an estimated "
            f"{cov['translate_game']:.0%} of non-English demand; store pages test languages holding another "
            f"{cov['store_page_only']:.0%}. Estimates of demand, not sales."]
    out += [f"Note: {m}" for m in p["messages"]]
    return "\n".join(out)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Babel: a costed localization plan for a Steam game.")
    ap.add_argument("--appid", type=int)
    ap.add_argument("--name")
    ap.add_argument("--lookalikes", help="comma-separated Steam appids of look-alike games")
    ap.add_argument("--tags", help="comma-separated Steam tags, for a game without a store page")
    ap.add_argument("--description", help="free-text description, for a game without a store page")
    ap.add_argument("--words", type=int, help="words to translate in the game")
    ap.add_argument("--budget", type=float, help="translation budget in USD")
    ap.add_argument("--examples", action="store_true", help="plans for three example games")
    ap.add_argument("--description-examples", action="store_true", help="plans for three example descriptions")
    ap.add_argument("--markets", action="store_true", help="add market notes (Qloo audience and local favourites)")
    ap.add_argument("--json", action="store_true", help="print the full evidence object")
    a = ap.parse_args(argv)
    if a.examples:
        runs = [{"appid": i, "word_count": w, "budget": b} for i, w, b in EXAMPLES]
    elif a.description_examples:
        runs = [{"description": d, "word_count": 40_000, "budget": 12_000} for d in describe.EXAMPLES]
    else:
        runs = [{"appid": a.appid, "name": a.name, "word_count": a.words, "budget": a.budget,
                 "lookalikes": [int(x) for x in a.lookalikes.split(",")] if a.lookalikes else None,
                 "tags": [t.strip() for t in a.tags.split(",")] if a.tags else None, "description": a.description}]
    for i, kwargs in enumerate(runs):
        try:
            p = plan(**kwargs)
        except PlanError as e:
            print(f"Error: {e}")
            return 2
        if a.markets:
            p["market_notes"] = markets.market_notes(p)
        text = ("\n" if i else "") + render(p) + (markets.render(p["market_notes"]) if a.markets else "")
        print(json.dumps(p, indent=2, ensure_ascii=False) if a.json else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
