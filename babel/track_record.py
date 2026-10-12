"""The published backtest results for the Track record screen, recomputed from the frozen prediction files.

Everything comes from backtest/data (outputs of the pre-registered backtest/evaluate.py); the SHA-256 of each source
file is included so a reader can check them. The exploratory re-reading of the Wikipedia set (docs/DECISIONS.md,
section 10) is included separately and labelled exploratory.

Recomputed here from backtest/data: every competitor's means (top-3 coverage, top-3 hit, Spearman rho, adjusted top-3
hit), the paired sign test, its bootstrap CI, per-game observed shares and rankings, and the within-language
correlation of the two AI rankings. The Qloo signal correlations, the dev-set choices and the own-map validity check
need Qloo fan-map data that is not in backtest/data, so they are read from the published backtest/final_report.md
(with its SHA-256) and labelled as reported.
"""
import hashlib
import re
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.stats import binomtest, spearmanr

from .languages import LABEL, TARGETS
from .plan import BACKTEST_DATA, ROOT, TRACK_RECORD

BABEL, TYPICAL = "Babel: typical x S1 (primary)", "Typical mix (no Qloo)"
REPORT = ROOT / "backtest" / "final_report.md"
ALPHA = 0.05  # significance level of the pre-registered decision rule (backtest/PREREGISTRATION.md)
N_BOOT, SMOOTH = 2000, 50  # as in backtest/evaluate.py: bootstrap resamples; smoothing of the real over-index
WIKI_LABEL = {"zh": "Chinese", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian", "es": "Spanish",
              "tr": "Turkish", "de": "German", "fr": "French", "pl": "Polish", "it": "Italian", "uk": "Ukrainian",
              "th": "Thai"}
TRUTHS = {
    "steam_reviews": {"predictions": "final_predictions_steam.csv", "games": "test_games.csv", "labels": LABEL,
                      "measure": "Share of non-English Steam reviews (English-only indie games)",
                      "report_name": "Steam reviews", "comps": "comps.csv",
                      "games_label": "small English-only indie games",
                      "observed_unit": "non-English Steam reviews in the 14 target languages", "per_review": 1},
    "wikipedia_pageviews": {"predictions": "final_predictions_wiki.csv", "games": "wiki_games.csv",
                            "labels": WIKI_LABEL,
                            "measure": "Share of non-English Wikipedia pageviews (notable games)",
                            "report_name": "Wikipedia pageviews", "comps": "wiki_comps.csv",
                            "games_label": "notable games",
                            "observed_unit": "pageviews in the 13 non-English Wikipedia editions",
                            "per_review": 100},  # evaluate.py: 100 views ~ 1 review for smoothing
}
# report name -> (key, label, kind, what it is); kind: baseline, ai, qloo, babel (the primary) or variant
COMPETITORS = {
    "Generic tier list": ("generic", "Generic tier list", "baseline",
                          "The copy-pasted list most guides give: Chinese, Japanese and Korean first."),
    "Steam user share": ("steam_share", "Steam user share", "baseline",
                         "Languages ranked by their share of Steam users (Steam survey)."),
    TYPICAL: ("typical_mix", "Typical mix (no Qloo)", "baseline",
              "The average language mix of the dev games in the same truth: Babel without Qloo."),
    "AI alone": ("ai", "AI alone (Groq gpt-oss-120b)", "ai",
                 "An LLM ranks the 14 languages from the game's tags, description and look-alikes, never its name."),
    "AI + typical mix": ("ai_typical", "AI + typical mix", "ai", "The same LLM, also shown the typical mix."),
    "Claude alone": ("claude", "Claude Opus 5.5 alone", "ai", "The same prompt, answered by Claude Opus 5.5."),
    "Claude + typical mix": ("claude_typical", "Claude + typical mix", "ai",
                             "Claude Opus 5.5, also shown the typical mix."),
    "Qloo alone": ("qloo", "Qloo alone", "qloo", "Ranked by the look-alikes' Qloo fan maps only."),
    BABEL: ("babel", "Babel (typical mix × Qloo S1)", "babel",
            "The pre-registered method: the typical mix × the Qloo S1 lift of the game's look-alikes."),
    "Babel: typical x S2": ("babel_s2", "Variant: typical mix × S2", "variant",
                            "Another Qloo signal, not the one chosen on dev games; not used for any claim."),
    "Babel: typical x S5": ("babel_s5", "Variant: typical mix × S5", "variant",
                            "Another Qloo signal, not the one chosen on dev games; not used for any claim."),
}
PER_GAME = ("babel", "typical_mix", "claude", "generic")  # competitors whose per-game results the screen shows
SIGNAL_KEY = {"S1": "qloo_s1", "S2": "qloo_s2", "S5": "qloo_s5", "AI alone": "ai", "Claude alone": "claude"}
DECISION_RULE = ("Qloo adds value if, on at least one truth, Babel beats the typical mix on top-3 coverage (one-sided "
                 "paired sign test p < 0.05) and the primary Qloo signal's within-language correlation is positive "
                 "(p < 0.05); a weak signal only if just the correlation test passes.")


def _sha256(name):
    return hashlib.sha256((BACKTEST_DATA / name).read_bytes()).hexdigest()


def _num(x, digits=4):
    """A rounded float, or None for NaN (JSON has no NaN)."""
    return None if x is None or pd.isna(x) else round(float(x), digits)


def _truth_shares():
    """{truth: DataFrame of real shares per game (rows) and language (columns)}."""
    reviews = pd.read_csv(BACKTEST_DATA / "truth_reviews.csv").set_index("appid")
    counts = pd.DataFrame({t: reviews[[f"rev_{c}" for c in codes]].sum(axis=1) for t, codes in TARGETS.items()})
    wiki = pd.read_csv(BACKTEST_DATA / "truth_wiki.csv").set_index("appid")
    return {"steam_reviews": counts.div(counts.sum(axis=1), axis=0),
            "wikipedia_pageviews": wiki[[f"share_{w}" for w in WIKI_LABEL]].set_axis(list(WIKI_LABEL), axis=1)}


def _truth_sizes():
    """{truth: (observed demand per game, the games eligible for that truth)}, as backtest/evaluate.py defines them."""
    reviews = pd.read_csv(BACKTEST_DATA / "truth_reviews.csv").set_index("appid")
    counts = pd.DataFrame({t: reviews[[f"rev_{c}" for c in codes]].sum(axis=1) for t, codes in TARGETS.items()})
    wiki = pd.read_csv(BACKTEST_DATA / "truth_wiki.csv").set_index("appid")
    eligible = wiki[(wiki.set == "wiki") & (wiki.articles >= 3) & (wiki.views_total > 0)]
    return {"steam_reviews": (counts.sum(axis=1), list(counts.index)),
            "wikipedia_pageviews": (wiki.views_total, list(eligible.index))}


def _paired(cov, ids):
    d = cov.loc[ids, BABEL] - cov.loc[ids, TYPICAL]
    better, worse = int((d > 1e-12).sum()), int((d < -1e-12).sum())
    return {"games": len(ids), "babel_top3_coverage": round(float(cov.loc[ids, BABEL].mean()), 4),
            "typical_mix_top3_coverage": round(float(cov.loc[ids, TYPICAL].mean()), 4),
            "better": better, "tie": len(ids) - better - worse, "worse": worse,
            "sign_test_p": float(f"{binomtest(better, better + worse, alternative='greater').pvalue:.3g}")
            if better + worse else None, "mean_difference": round(float(d.mean()), 4)}


def _bootstrap_ci(d):
    """95% CI of the mean per-game difference: the same resamples as backtest/evaluate.py (pandas sample with
    random_state 0..1999 draws RandomState(b).choice), so the interval matches the report."""
    v, rs, means = d.to_numpy(), np.random.RandomState(0), []
    for b in range(N_BOOT):
        rs.seed(b)
        means.append(v[rs.choice(len(v), len(v), replace=True)].mean())
    return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]


def _primary_test(cov):
    """The pre-registered test (Babel vs the typical mix, paired by game) with its bootstrap CI and significance."""
    out = _paired(cov, list(cov.index))
    out.update({"ci95": _bootstrap_ci(cov[BABEL] - cov[TYPICAL]), "bootstrap_resamples": N_BOOT, "alpha": ALPHA,
                "significant": out["sign_test_p"] is not None and out["sign_test_p"] < ALPHA,
                "test": "One-sided paired sign test on top-3 coverage (ties dropped)"})
    return out


def _ai_correlation(rank, shares, n_eff, prior, ids):
    """Within-language correlation of an AI's ranking with the real over-index (backtest/evaluate.py's measure)."""
    n = n_eff.loc[ids].to_numpy()[:, None]
    adj = (shares.loc[ids] * n + SMOOTH * prior) / (n + SMOOTH) / prior
    score = pd.DataFrame([[-rank[g].split("|").index(l) for l in shares.columns] for g in ids], index=ids,
                         columns=shares.columns)
    rs = [spearmanr(score[l], adj[l])[0] for l in adj.columns if score[l].nunique() > 1 and adj[l].nunique() > 1]
    return round(float(np.mean(rs)), 6) if rs else None


# ---------------------------------------------------------------- the published report (read, never retyped)
def _tables(text):
    """Every markdown table in the text: a list of rows (header first, separator dropped), each a list of cells."""
    tables, rows = [], []
    for line in text.splitlines() + [""]:
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif rows:
            tables.append([rows[0]] + rows[2:])
            rows = []
    return tables


def _sections(text):
    return {s.split("\n", 1)[0].strip(): s for s in re.split(r"^## ", text, flags=re.M)[1:]}


def _signals(section):
    table = next(t for t in _tables(section) if t[0][0].startswith("Signal"))
    out = []
    for name, corr, p in table[1:]:
        sid = name.split(":")[0] if name[:1] == "S" else name.split(" (")[0]
        out.append({"key": SIGNAL_KEY.get(sid, sid), "name": name, "correlation": _report_float(corr),
                    "shuffle_p": _report_float(p), "reported_as": [corr, p]})
    return out


def _report_float(text):
    return None if text.startswith("n/a") else float(text)


@lru_cache(maxsize=1)
def _report():
    """What the published report says that backtest/data alone cannot reproduce (needs Qloo data)."""
    text = REPORT.read_text(encoding="utf-8")
    sections, out = _sections(text), {}
    for truth, spec in TRUTHS.items():
        sec = sections[spec["report_name"]]
        m = re.search(r"Dev (\d+) games, test (\d+) games \((\d+) with look-alikes\)\. Primary Qloo signal chosen on "
                      r"dev: \*\*(\w+) \((.+?)\)\*\*; dev correlations: (.+?); alpha: (.+?)\.\s*$", sec, re.M)
        pairs = lambda s: {k: v for k, v in (x.split(" ") for x in s.split(", "))}  # noqa: E731
        out[truth] = {"dev_games": int(m[1]), "test_games": int(m[2]), "test_games_with_lookalikes": int(m[3]),
                      "primary_signal": {"id": m[4], "name": m[5],
                                         "dev_correlations": {k: float(v) for k, v in pairs(m[6]).items()},
                                         "alpha": {k: int(v) for k, v in pairs(m[7]).items()}},
                      "signals": _signals(sec),
                      "verdict": re.search(r"\*\*Pre-registered verdict \(.+?\): (.+?)\.\*\*", sec)[1]}
    validity = next(v for k, v in sections.items() if k.startswith("Validity check"))
    _, *rows = _tables(validity)[0]
    out["validity_check"] = [{"truth": r[0], "sampled": int(r[1]), "found_in_qloo": int(r[2]),
                              "default_map": int(r[3]), "real_map": int(r[4]), "correlation": _report_float(r[5]),
                              "shuffle_p": _report_float(r[6])} for r in rows]
    out["overall_verdict"] = re.search(r"^## Overall verdict: \*\*(.+?)\*\*", text, re.M)[1]
    out["sha256"] = hashlib.sha256(REPORT.read_bytes()).hexdigest()
    return out


# ---------------------------------------------------------------- per truth
def _competitors(pred):
    cols = ["coverage", "hit3", "rho", "hit3_adj"]
    means = pred.groupby("competitor", sort=False)[cols].mean()
    out = []
    for c in sorted(means.index, key=lambda c: -means.loc[c, "coverage"]):
        key, label, kind, about = COMPETITORS.get(c, (c, c, "other", ""))
        # 6 decimals: a display rounded to 0.1% must round the same way as the report (no double rounding)
        out.append({"name": c, "top3_coverage": _num(means.loc[c, "coverage"], 6),
                    "top3_hit": _num(means.loc[c, "hit3"], 6), "key": key, "label": label, "kind": kind,
                    "about": about, "primary": c == BABEL, "spearman_rho": _num(means.loc[c, "rho"], 6),
                    "top3_hit_adjusted": _num(means.loc[c, "hit3_adj"], 6),
                    "games": int(pred[pred.competitor == c].appid.nunique())})
    return out


def _lookalikes(spec):
    out = {}
    for r in pd.read_csv(BACKTEST_DATA / spec["comps"]).itertuples():
        out.setdefault(r.test_appid, []).append({"name": r.comp_name, "overlap": round(float(r.overlap_score), 4)})
    return out


def _game(appid, spec, shares, n, info, rows, lookalikes):
    """One test game: observed shares and size, rankings and per-game scores (rows: {metric: {competitor: value}})."""
    label, rank = spec["labels"], rows["ranking"]
    shown = {COMPETITORS[c][0]: c for c in rank if COMPETITORS.get(c, ("",))[0] in PER_GAME}
    real = shares.loc[appid].sort_values(ascending=False).index[:3]
    looks = lookalikes.get(appid, [])
    return {"appid": int(appid), "name": str(info.name.get(appid, appid)),
            "real_top3": [label[l] for l in real],
            "babel_top3": [label[l] for l in rank[BABEL].split("|")[:3]],
            "typical_mix_top3": [label[l] for l in rank[TYPICAL].split("|")[:3]],
            "babel_coverage": round(float(rows["coverage"][BABEL]), 4),
            "typical_mix_coverage": round(float(rows["coverage"][TYPICAL]), 4),
            "released": str(info.release_date.get(appid, "")) or None, "observed_n": int(n[appid]),
            "observed_share": {l: _num(v) for l, v in shares.loc[appid].items()},
            "rankings": {k: rank[c].split("|") for k, c in shown.items() if k != "generic"},
            "scores": {k: {m: _num(rows[m][c]) for m in ("coverage", "hit3", "rho")} for k, c in shown.items()},
            "lookalikes": looks, "untagged": bool(looks) and all(x["overlap"] == 0 for x in looks)}


def _truth(truth, spec, shares, sizes, report):
    pred = pd.read_csv(BACKTEST_DATA / spec["predictions"])
    info = pd.read_csv(BACKTEST_DATA / spec["games"]).drop_duplicates("appid").set_index("appid")
    pivots = {v: pred.pivot_table(index="appid", columns="competitor", values=v, aggfunc="first")
              for v in ("coverage", "hit3", "rho", "ranking")}
    cov, rank = pivots["coverage"], pivots["ranking"]
    per_game = {v: p.to_dict("index") for v, p in pivots.items()}
    n, eligible = sizes
    test = list(cov.index)
    dev = [g for g in eligible if g not in set(test)]
    looks = _lookalikes(spec)
    games = [_game(a, spec, shares, n, info, {v: d[a] for v, d in per_game.items()}, looks) for a in test]
    with_looks = [g for g in test if g in looks]
    prior = shares.loc[dev].mean()
    signals = [dict(s) for s in report["signals"]]
    for s in signals:
        comp = {"ai": "AI alone", "claude": "Claude alone"}.get(s["key"])
        s["source"] = "backtest/final_report.md"
        s["recomputed_correlation"] = (_ai_correlation(rank[comp], shares, n / spec["per_review"], prior, with_looks)
                                       if comp in rank.columns else None)
    test_result = _primary_test(cov)
    primary = next(s for s in signals if s["key"] == SIGNAL_KEY[report["primary_signal"]["id"]])
    signal_ok = primary["shuffle_p"] is not None and primary["shuffle_p"] < ALPHA and primary["correlation"] > 0
    obs = n.loc[test]
    return {
        "measure": spec["measure"], "verdict": TRACK_RECORD[truth]["verdict"],
        "competitors": _competitors(pred), "babel_vs_typical_mix": test_result, "games": games,
        "source": {"file": f"backtest/data/{spec['predictions']}", "sha256": _sha256(spec["predictions"])},
        "name": spec["report_name"], "games_label": spec["games_label"], "observed_unit": spec["observed_unit"],
        "languages": [{"code": l, "label": spec["labels"][l]} for l in shares.columns],
        "generic_ranking": rank["Generic tier list"].iloc[0].split("|"),
        "sample": {"test_games": len(test), "dev_games": len(dev), "test_games_with_lookalikes": len(with_looks),
                   "observed_n": {"min": int(obs.min()), "median": float(obs.median()), "max": int(obs.max())},
                   "indie_test_games": int(info.loc[test, "is_indie"].sum()) if "is_indie" in info else None,
                   "small_sample_below": SMOOTH * spec["per_review"]},
        "primary_signal": report["primary_signal"], "signals": signals,
        "decision": {"coverage_test_passed": test_result["significant"], "signal_test_passed": signal_ok,
                     "primary_signal": primary["name"],
                     "verdict": ("Qloo adds value" if test_result["significant"] and signal_ok else
                                 "Qloo adds a weak signal only" if signal_ok else "No measurable value from Qloo"),
                     "reported_verdict": report["verdict"]},
    }


@lru_cache(maxsize=1)
def track_record():
    """The full track record (JSON-ready): per truth, every competitor's results, the pre-registered Babel vs
    typical-mix test, and each test game's predicted and real top 3."""
    shares, sizes, report, out = _truth_shares(), _truth_sizes(), _report(), {}
    for truth, spec in TRUTHS.items():
        out[truth] = _truth(truth, spec, shares[truth], sizes[truth], report[truth])
    wiki_cov = pd.read_csv(BACKTEST_DATA / "final_predictions_wiki.csv").pivot_table(
        index="appid", columns="competitor", values="coverage")
    comps = pd.read_csv(BACKTEST_DATA / "wiki_comps.csv")
    untagged = set(comps[comps.overlap_score == 0].test_appid)
    files = ["final_predictions_steam.csv", "final_predictions_wiki.csv", "truth_reviews.csv", "truth_wiki.csv",
             "test_games.csv", "wiki_games.csv", "dev_test_games_43.csv", "comps.csv", "wiki_comps.csv"]
    return {
        "method": "Pre-registered (backtest/PREREGISTRATION.md): methods fixed on dev games, scored once on test "
                  "games. Top-3 coverage = share of a game's real non-English demand in the 3 recommended languages.",
        "truths": out,
        "exploratory": {
            "label": "Exploratory, post hoc (docs/DECISIONS.md, section 10); not part of the pre-registered result.",
            "note": "Wikipedia test games without SteamSpy tags all got the same three look-alikes; results for the "
                    "games whose look-alikes share tags with them:",
            "wikipedia_games_with_tags": _paired(wiki_cov, [a for a in wiki_cov.index if a not in untagged]),
            "wikipedia_games_without_tags": _paired(wiki_cov, [a for a in wiki_cov.index if a in untagged]),
            "untagged_lookalikes": sorted(comps[comps.overlap_score == 0].comp_name.unique())},
        "caveats": ["Measures are proxies (reviews of English-only games; Wikipedia attention), not sales.",
                    "Both proxies under-count Chinese, Japanese and Korean audiences.",
                    "Claude Opus 5.5 alone was about as accurate as Babel; combining them was not tested."],
        "decision_rule": DECISION_RULE, "alpha": ALPHA,
        "report": {"file": "backtest/final_report.md", "sha256": report["sha256"],
                   "overall_verdict": report["overall_verdict"],
                   "note": "Qloo signal correlations, dev-set choices and the own-map check need Qloo data that is "
                           "not in backtest/data, so they are read from this report (labelled as reported)."},
        "validity_check": report["validity_check"],
        "sources": [{"file": f"backtest/data/{f}", "sha256": _sha256(f)} for f in files],
    }
