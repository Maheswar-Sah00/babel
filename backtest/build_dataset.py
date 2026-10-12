"""Step 2: build the Babel backtest dataset. No predictions.

A. Test games: paid, English-only indie games released 2023+ with 500+ reviews -> data/test_games.csv
B. Ground truth: all-time reviews per language (gated on a 2-game sanity check) -> data/truth_reviews.csv
C. Comparable games a dev could pick before launch: top 3 Qloo-valid comps    -> data/comps.csv
D. step2_report.md + data/lang_share.png

Run: python backtest/build_dataset.py   (every response is cached under cache/, so a re-run resumes)
"""
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import MultipleLocator, PercentFormatter  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from babel import net, steam  # noqa: E402
from babel.comps import CompPicker, spy_tags  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)
TARGET, FIRST_BATCH, MAX_CANDIDATES = 200, 800, 4000  # scan past the first 800 candidates only if short of 200
RELEASED_FROM, COMP_RELEASED_BEFORE = date(2023, 1, 1), date(2023, 1, 1)
MIN_REVIEWS, COMP_MIN_REVIEWS, COMP_POOL_SIZE = 500, 5000, 1000
SPY_PREFILTER = 150  # SteamSpy's counts lag Steam's (median 0.77x, 0.57x for 2025), so prefilter low; Steam must say 500+
TOP_COMPS, KEEP_COMPS = 6, 3
LANGS = ["english", "schinese", "tchinese", "japanese", "koreana", "russian", "ukrainian", "brazilian", "spanish",
         "latam", "german", "french", "polish", "turkish", "italian", "thai"]
NON_EN = LANGS[1:]
LABEL = {"schinese": "Simplified Chinese", "tchinese": "Traditional Chinese", "japanese": "Japanese",
         "koreana": "Korean", "russian": "Russian", "ukrainian": "Ukrainian", "brazilian": "Portuguese (Brazil)",
         "spanish": "Spanish (Spain)", "latam": "Spanish (Latin America)", "german": "German", "french": "French",
         "polish": "Polish", "turkish": "Turkish", "italian": "Italian", "thai": "Thai"}


# A. Test games, newest store pages first
print("A. Test games")
steam.get(steam.SPY, {"request": "all", "page": 0})  # SteamSpy allows 'all' once a minute: warm the cache first
indie = steam.spy_tag("Indie")
candidates = sorted((int(a) for a, g in indie.items() if g.get("positive", 0) + g.get("negative", 0) >= SPY_PREFILTER),
                    reverse=True)
STAGES = ["candidates checked", "Steam store data", "type = game", "English only", "released 2023-01-01 or later",
          "not free-to-play", "500+ reviews (Steam, all languages)"]
funnel = Counter()


def test_game_checks(appid):
    """Each filter's result in order; Steam is only called until the first failure."""
    d = steam.appdetails(appid)
    yield bool(d)
    yield d.get("type") == "game"
    yield steam.languages(d) == ["English"]
    yield steam.released_between(d, RELEASED_FROM)
    yield not d.get("is_free")
    yield (steam.review_total(appid) or 0) >= MIN_REVIEWS


test_ids = []
for appid in candidates[:MAX_CANDIDATES]:
    if len(test_ids) >= TARGET:
        break
    funnel[STAGES[0]] += 1
    for stage, ok in zip(STAGES[1:], test_game_checks(appid)):
        if not ok:
            break
        funnel[stage] += 1
    else:
        test_ids.append(appid)
    if funnel[STAGES[0]] % 100 == 0:
        print(f"  checked {funnel[STAGES[0]]}, kept {len(test_ids)}")
test_df = pd.DataFrame([{"appid": a, "name": steam.appdetails(a)["name"],
                         "release_date": steam.release_date(steam.appdetails(a)).isoformat(),
                         "total_reviews": steam.review_total(a), "tags": "|".join(spy_tags(a)),
                         "short_description": steam.appdetails(a).get("short_description", "")} for a in test_ids])
test_df.to_csv(DATA / "test_games.csv", index=False)
print(f"  {len(test_df)} test games from {funnel[STAGES[0]]} candidates -> data/test_games.csv")

# B. Ground truth. First prove the language filter works on 2 games, else stop and show the raw JSON
print("B. Reviews per language")
gate = []
for appid in test_ids[:2]:
    counts = {lang: steam.review_total(appid, lang) or 0 for lang in ["all"] + LANGS}
    lang_sum = sum(counts[lang] for lang in LANGS)
    equal_to_all = sum(counts[lang] == counts["all"] for lang in LANGS)
    gate.append((appid, counts["all"], lang_sum, equal_to_all))
    print(f"  gate {appid}: all={counts['all']}, sum of 16 languages={lang_sum} ({lang_sum / counts['all']:.1%})")
    if equal_to_all >= 2 or lang_sum > 1.05 * counts["all"]:
        print("STOP: the language parameter looks ignored. Raw JSON for language=japanese and language=all:")
        for lang in ("japanese", "all"):
            print(json.dumps(steam.get(f"{steam.STORE}/appreviews/{appid}", {"json": 1, "language": lang,
                  "purchase_type": "all", "filter": "all", "num_per_page": 0}), indent=2))
        sys.exit(1)
truth_rows = []
for i, appid in enumerate(test_ids, 1):
    counts = {lang: steam.review_total(appid, lang) or 0 for lang in LANGS}
    total = steam.review_total(appid) or 0
    non_en = total - counts["english"]
    truth_rows.append({"appid": appid, "name": steam.appdetails(appid)["name"], "total_reviews": total,
                       **{f"rev_{lang}": counts[lang] for lang in LANGS}, "non_english": non_en,
                       **{f"share_{lang}": counts[lang] / non_en if non_en > 0 else 0.0 for lang in NON_EN}})
    if i % 25 == 0:
        print(f"  {i}/{len(test_ids)} games")
truth_df = pd.DataFrame(truth_rows)
truth_df.to_csv(DATA / "truth_reviews.csv", index=False)

# C. Comparable games: well-known games released before 2023, ranked by IDF-weighted tag overlap (babel/comps.py)
print("C. Comparable games")
picker = CompPicker(released_before=COMP_RELEASED_BEFORE, pool_size=COMP_POOL_SIZE, min_reviews=COMP_MIN_REVIEWS)
comp_rows, comps_per_game = [], Counter()
for appid in test_ids:
    picked = picker.pick(spy_tags(appid), top=TOP_COMPS, keep=KEEP_COMPS)
    comp_rows += [{"test_appid": appid, **c} for c in picked]
    comps_per_game[len(picked)] += 1
comps_df = pd.DataFrame(comp_rows)
comps_df.to_csv(DATA / "comps.csv", index=False)

# D. Report
print("D. Report")
avg_share = truth_df[[f"share_{lang}" for lang in NON_EN]].mean().rename(lambda c: LABEL[c[6:]]).sort_values()
fig, ax = plt.subplots(figsize=(7.5, 5.2), dpi=150)
fig.patch.set_facecolor("#fcfcfb")
ax.set_facecolor("#fcfcfb")
ax.barh(avg_share.index, avg_share.values, height=0.62, color="#2a78d6")
for i, v in list(enumerate(avg_share.values))[-5:]:  # label only the five largest
    ax.text(v + avg_share.max() * 0.01, i, f"{v:.1%}", va="center", fontsize=9, color="#0b0b0b")
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color("#d9d8d4")
ax.xaxis.set_major_locator(MultipleLocator(0.05))
ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
ax.grid(axis="x", color="#e6e5e1", linewidth=0.8)
ax.set_axisbelow(True)
ax.tick_params(colors="#52514e", length=0, labelsize=9)
ax.set_title("Average share of non-English reviews, by language", loc="left", fontsize=12, color="#0b0b0b", pad=22)
ax.text(0, 1.02, f"{len(truth_df)} English-only indie games released 2023+, all-time Steam reviews",
        transform=ax.transAxes, fontsize=9, color="#52514e")
fig.tight_layout()
fig.savefig(DATA / "lang_share.png", facecolor=fig.get_facecolor())

status_counts = Counter(s for s, _ in picker.status.values())
hosts = {"Qloo": "hackathon.api.qloo.com", "Steam store": "store.steampowered.com", "SteamSpy": "steamspy.com"}
out = ["# Step 2: backtest dataset", "",
       f"Files: `data/test_games.csv` ({len(test_df)} games), `data/truth_reviews.csv`, `data/comps.csv` "
       f"({len(comps_df)} rows), `data/lang_share.png`.", "",
       "## A. Test games: games left after each filter", "", "| Filter | Games left |", "|---|---|"]
out += [f"| {s} | {funnel[s]} |" for s in STAGES]
out += ["", f"Candidates: SteamSpy Indie tag with {SPY_PREFILTER}+ SteamSpy reviews ({len(candidates)}; SteamSpy lags "
        f"Steam, so Steam's own count decides the {MIN_REVIEWS} cut), newest store pages first. "
        f"Scanning stops at {TARGET} games; the first {FIRST_BATCH} candidates "
        f"{'were enough' if funnel[STAGES[0]] <= FIRST_BATCH else f'were not enough, so it continued to {funnel[STAGES[0]]}'}"
        f"{'' if len(test_df) >= TARGET else f' and found only {len(test_df)} (cap {MAX_CANDIDATES})'}.", "",
        "## B. Ground truth", "", "Sanity check: do the 16 per-language totals add up to the all-language total?", "",
        "| Game | All languages | Sum of 16 languages | Coverage | Languages equal to total |", "|---|---|---|---|---|"]
out += [f"| {truth_df.set_index('appid').loc[a, 'name']} | {al} | {s} | {s / al:.1%} | {eq} |" for a, al, s, eq in gate]
out += ["", f"Passed: the language filter works (the remainder is languages outside the 16). Median non-English share "
        f"of reviews: {(truth_df.non_english / truth_df.total_reviews).median():.0%}.", "",
        "![Average share of non-English reviews](data/lang_share.png)", "",
        "| Language | Average share of non-English reviews |", "|---|---|"]
out += [f"| {lang} | {v:.1%} |" for lang, v in avg_share.sort_values(ascending=False).items()]
out += ["", "## C. Comparable games", "",
        f"Pool: SteamSpy top-owned + Indie games with {COMP_MIN_REVIEWS:,}+ reviews, the {COMP_POOL_SIZE} most reviewed, "
        f"released before {COMP_RELEASED_BEFORE}: {len(picker.names)} games. Ranked by IDF-weighted tag overlap; "
        f"the top {TOP_COMPS} are tried in order until {KEEP_COMPS} have a valid Qloo heatmap.", "",
        f"- Games with {KEEP_COMPS} valid comps: **{comps_per_game[KEEP_COMPS]} / {len(test_ids)}** "
        f"(2: {comps_per_game[2]}, 1: {comps_per_game[1]}, 0: {comps_per_game[0]})",
        f"- Comps checked in Qloo: {len(picker.status)} unique; " + ", ".join(f"{k}: {v}" for k, v in status_counts.items()),
        f"- Unique comps used: {comps_df.comp_appid.nunique() if len(comps_df) else 0}", "",
        "## D. API usage", "", "| Source | Network calls this run | Served from cache | Responses used |", "|---|---|---|---|"]
out += [f"| {k} | {net.calls[h]} | {net.cache_hits[h]} | {net.calls[h] + net.cache_hits[h]} |" for k, h in hosts.items()]
(HERE / "step2_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
