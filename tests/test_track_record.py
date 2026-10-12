"""GET /track-record serves exactly the published backtest: every number is checked against backtest/final_report.md.

The report's tables and sentences are parsed here, independently of babel/track_record.py's own reader, and never
retyped. Numbers the server recomputes from backtest/data (coverage, hit, Spearman, the sign test, the bootstrap CI,
sample sizes, the AI correlations) must format to the report's own text; numbers it reads from the report (the Qloo
signal correlations) must be passed through unchanged. The exploratory split is checked against docs/DECISIONS.md,
section 10.
"""
import hashlib
import re

import pytest
from fastapi.testclient import TestClient

from babel import api
from babel import plan as P

REPORT = (P.ROOT / "backtest" / "final_report.md").read_text(encoding="utf-8")
DECISIONS = (P.ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
TRUTHS = {"Steam reviews": "steam_reviews", "Wikipedia pageviews": "wikipedia_pageviews"}


# ---------------------------------------------------------------- reading the report
def section(title, text=REPORT):
    """The body of the '## title...' section."""
    m = re.search(rf"^## {re.escape(title)}.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"no section {title!r}"
    return m[1]


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table(text, first):
    """The rows (dicts by header) of the markdown table whose first header cell starts with `first`."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and cells(line)[0].startswith(first):
            head, rows = cells(line), []
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                rows.append(dict(zip(head, cells(row))))
            return rows
    raise AssertionError(f"no table starting with {first!r}")


def primary_line(text):
    m = re.search(r"Babel better on (\d+) games, tie (\d+), worse (\d+); one-sided sign test p = ([\d.]+); mean "
                  r"difference ([+-][\d.]+%) \(95% bootstrap CI ([+-][\d.]+%) to ([+-][\d.]+%)\)", text)
    assert m
    return m.groups()


@pytest.fixture(scope="module")
def served():
    with TestClient(api.create_app(api.Settings(warmup=False))) as c:
        r = c.get("/track-record")
        assert r.status_code == 200
        return r.json()


@pytest.fixture(params=list(TRUTHS))
def truth(request, served):
    """(report section text, the served truth) for each truth."""
    return section(request.param), served["truths"][TRUTHS[request.param]]


# ---------------------------------------------------------------- the pre-registered results
def test_every_method_matches_the_report_table(truth):
    text, tr = truth
    rows = table(text, "Competitor")
    by_name = {c["name"]: c for c in tr["competitors"]}
    assert set(by_name) == {r["Competitor"] for r in rows}
    for r in rows:
        c = by_name[r["Competitor"]]
        assert f"{c['top3_coverage']:.1%}" == r["Top-3 coverage (primary)"], r
        assert f"{c['top3_hit']:.0%}" == r["Top-3 hit"], r
        assert f"{c['spearman_rho']:.2f}" == r["Spearman"], r
        assert f"{c['top3_hit_adjusted']:.0%}" == r["Top-3 hit (adjusted)"], r
        assert c["games"] == len(tr["games"])
    assert [c["key"] for c in tr["competitors"] if c["primary"]] == ["babel"]


def test_the_primary_test_matches_the_report(truth):
    text, tr = truth
    better, tie, worse, p, mean, lo, hi = primary_line(text)
    x = tr["babel_vs_typical_mix"]
    assert (x["better"], x["tie"], x["worse"]) == (int(better), int(tie), int(worse))
    assert f"{x['sign_test_p']:.3f}" == p
    assert f"{x['mean_difference']:+.2%}" == mean
    assert [f"{v:+.2%}" for v in x["ci95"]] == [lo, hi]  # recomputed: 2,000 resamples, as evaluate.py draws them
    assert x["significant"] == (float(p) < 0.05) and x["alpha"] == 0.05
    overall = re.search(rf"^- {re.escape(tr['name'])}: (.+?) \(Babel ([+-][\d.]+%) coverage vs typical mix, "
                        r"p = ([\d.]+)\)\.$", REPORT, re.M)
    assert overall.groups() == (tr["verdict"], mean, p)


def test_sample_sizes_match_the_report(truth):
    text, tr = truth
    dev, test, with_looks = map(int, re.search(r"Dev (\d+) games, test (\d+) games \((\d+) with look-alikes\)",
                                               text).groups())
    s = tr["sample"]
    assert (s["dev_games"], s["test_games"], s["test_games_with_lookalikes"]) == (dev, test, with_looks)
    assert len(tr["games"]) == tr["babel_vs_typical_mix"]["games"] == test
    assert len({g["appid"] for g in tr["games"]}) == test


def test_signal_correlations_match_and_the_ai_ones_recompute(truth):
    text, tr = truth
    rows = table(text, "Signal")
    by_name = {s["name"]: s for s in tr["signals"]}
    assert [s["name"] for s in tr["signals"]] == [r["Signal (test games with look-alikes)"] for r in rows]
    for r in rows:
        s = by_name[r["Signal (test games with look-alikes)"]]
        corr, p = r["Within-language correlation with real over-index"], r["Shuffle p"]
        assert (f"{s['correlation']:+.3f}", f"{s['shuffle_p']:.3f}") == (corr, p)
        if s["key"] in ("ai", "claude"):  # recomputed by the server from backtest/data alone
            assert f"{s['recomputed_correlation']:+.3f}" == corr
        else:
            assert s["recomputed_correlation"] is None  # needs Qloo data: reported, never invented


def test_verdicts_follow_the_pre_registered_rule(truth):
    text, tr = truth
    verdict = re.search(r"\*\*Pre-registered verdict \(.+?\): (.+?)\.\*\*", text)[1]
    d = tr["decision"]
    assert tr["verdict"] == d["verdict"] == d["reported_verdict"] == verdict
    primary = re.search(r"Primary Qloo signal chosen on dev: \*\*(\w+) ", text)[1]
    assert tr["primary_signal"]["id"] == primary and d["primary_signal"].startswith(f"{primary}:")


def test_steam_is_not_significant_and_wikipedia_is(served):
    steam, wiki = served["truths"]["steam_reviews"], served["truths"]["wikipedia_pageviews"]
    assert steam["babel_vs_typical_mix"]["significant"] is False and steam["decision"]["coverage_test_passed"] is False
    assert steam["babel_vs_typical_mix"]["ci95"][0] < 0 < steam["babel_vs_typical_mix"]["ci95"][1]
    assert wiki["babel_vs_typical_mix"]["significant"] is True and wiki["babel_vs_typical_mix"]["ci95"][0] > 0
    assert re.search(r"^## Overall verdict: \*\*(.+?)\*\*", REPORT, re.M)[1] == served["report"]["overall_verdict"]


def test_the_own_map_validity_check_matches_the_report(served):
    rows = table(section("Validity check"), "Truth")
    assert len(rows) == len(served["validity_check"])
    for r, v in zip(rows, served["validity_check"]):
        assert (v["truth"], str(v["sampled"]), str(v["found_in_qloo"]), str(v["default_map"]), str(v["real_map"])) \
            == (r["Truth"], r["Sampled"], r["Found in Qloo"], r["Default (no-data) map"], r["Real map"])
        corr = "n/a" if v["correlation"] is None else f"{v['correlation']:+.3f}"
        assert corr == r["Within-language correlation"]


# ---------------------------------------------------------------- the exploratory re-reading (DECISIONS section 10)
def test_the_exploratory_split_matches_decisions_section_10(served):
    split = table(section("10.", DECISIONS), "Wikipedia test games")
    rows = {r["Wikipedia test games"].split(" (")[0]: r for r in split}
    e = served["exploratory"]
    for label, x in ((f"All {served['truths']['wikipedia_pageviews']['babel_vs_typical_mix']['games']}",
                      served["truths"]["wikipedia_pageviews"]["babel_vs_typical_mix"]),
                     (f"{e['wikipedia_games_with_tags']['games']} with tags", e["wikipedia_games_with_tags"]),
                     (f"{e['wikipedia_games_without_tags']['games']} without tags", e["wikipedia_games_without_tags"])):
        r = rows[label]
        assert r["Babel vs typical mix"] == (f"{x['babel_top3_coverage']:.1%} vs {x['typical_mix_top3_coverage']:.1%} "
                                             f"({x['mean_difference'] * 100:+.1f} pts)").replace("-", "−")
        assert r["Better / tie / worse"] == f"{x['better']} / {x['tie']} / {x['worse']}"
    assert "Exploratory" in e["label"]
    assert e["untagged_lookalikes"] == ["Counter-Strike 2", "Terraria", "Tom Clancy's Rainbow Six Siege"]
    flawed = [g for g in served["truths"]["wikipedia_pageviews"]["games"] if g["untagged"]]
    assert len(flawed) == e["wikipedia_games_without_tags"]["games"]
    assert not any(g["untagged"] for g in served["truths"]["steam_reviews"]["games"])


# ---------------------------------------------------------------- per-game data and provenance
def test_each_games_scores_follow_from_its_observed_shares_and_rankings(served):
    for tr in served["truths"].values():
        label = {l["code"]: l["label"] for l in tr["languages"]}
        for g in tr["games"]:
            shares = g["observed_share"]
            assert set(shares) == set(label) and sum(shares.values()) == pytest.approx(1, abs=1e-3)
            for key, ranking in g["rankings"].items():
                assert sorted(ranking) == sorted(label)
                assert g["scores"][key]["coverage"] == pytest.approx(sum(shares[c] for c in ranking[:3]), abs=5e-4)
            assert g["babel_top3"] == [label[c] for c in g["rankings"]["babel"][:3]]
            assert g["babel_coverage"] == g["scores"]["babel"]["coverage"]
            generic = sum(shares[c] for c in tr["generic_ranking"][:3])
            assert g["scores"]["generic"]["coverage"] == pytest.approx(generic, abs=5e-4)
            assert g["observed_n"] > 0
        mean = sum(g["scores"]["babel"]["coverage"] for g in tr["games"]) / len(tr["games"])
        assert mean == pytest.approx(next(c for c in tr["competitors"] if c["primary"])["top3_coverage"], abs=1e-4)


def test_every_source_file_has_its_hash(served):
    files = served["sources"] + [{"file": served["report"]["file"], "sha256": served["report"]["sha256"]}]
    for f in files:
        assert hashlib.sha256((P.ROOT / f["file"]).read_bytes()).hexdigest() == f["sha256"]
    for tr in served["truths"].values():
        assert tr["source"] in served["sources"]


def test_without_games_the_summary_stays_small():
    with TestClient(api.create_app(api.Settings(warmup=False))) as c:
        r = c.get("/track-record?games=false").json()
    assert all("games" not in tr and "competitors" in tr for tr in r["truths"].values())
