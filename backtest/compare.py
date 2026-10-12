"""Step 3 (mini): who best predicts each test game's real top non-English languages?

Every competitor sees only what a developer knows before launch (tags, store description, look-alike games), never
the game's name or reviews. Babel's one knob (alpha: how strongly to trust Qloo) is chosen by leave-one-out: tuned on
the other games, then scored on the held-out game. The same goes for the "typical mix" prior.
Run after build_dataset.py: python backtest/compare.py -> step3_report.md, data/predictions.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from babel import llm, net, qloo  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
# Translation targets -> Steam review languages (Spanish = Spain + Latin America: one translation decision)
TARGETS = {"schinese": ["schinese"], "japanese": ["japanese"], "koreana": ["koreana"], "brazilian": ["brazilian"],
           "russian": ["russian"], "spanish": ["spanish", "latam"], "turkish": ["turkish"], "german": ["german"],
           "french": ["french"], "tchinese": ["tchinese"], "polish": ["polish"], "italian": ["italian"],
           "ukrainian": ["ukrainian"], "thai": ["thai"]}
LANGS = list(TARGETS)
LABEL = {"schinese": "Simplified Chinese", "japanese": "Japanese", "koreana": "Korean", "brazilian": "Portuguese-BR",
         "russian": "Russian", "spanish": "Spanish", "turkish": "Turkish", "german": "German", "french": "French",
         "tchinese": "Traditional Chinese", "polish": "Polish", "italian": "Italian", "ukrainian": "Ukrainian",
         "thai": "Thai"}
# The standard tier list (SC JA KO / PT-BR RU ES TR / DE FR TC PL), then the rest by Steam share
GENERIC = ["schinese", "japanese", "koreana", "brazilian", "russian", "spanish", "turkish", "german", "french",
           "tchinese", "polish", "thai", "ukrainian", "italian"]
# Steam Hardware & Software Survey, September 2026: share of Steam users by language (%)
STEAM = pd.Series({"schinese": 31.39, "russian": 9.05, "spanish": 4.08 + 0.75, "brazilian": 3.70, "german": 2.48,
                   "japanese": 2.41, "french": 2.08, "polish": 1.49, "koreana": 1.37, "tchinese": 1.27, "turkish": 1.09,
                   "thai": 0.82, "ukrainian": 0.66, "italian": 0.56})
# Countries counted for each language, weighted by population (millions)
COUNTRIES = {"schinese": {"CN": 1410}, "tchinese": {"TW": 23, "HK": 7.5, "MO": 0.7}, "japanese": {"JP": 124},
             "koreana": {"KR": 52}, "brazilian": {"BR": 216}, "russian": {"RU": 144, "BY": 9, "KZ": 20},
             "spanish": {"ES": 48, "MX": 129, "AR": 46, "CO": 52, "CL": 19, "PE": 34}, "turkish": {"TR": 85},
             "german": {"DE": 84, "AT": 9, "CH": 9}, "french": {"FR": 68, "BE": 12}, "polish": {"PL": 37},
             "italian": {"IT": 59}, "ukrainian": {"UA": 37}, "thai": {"TH": 72}}
ALPHAS = [0, 1, 2, 4, 8, 16, 32]  # alpha = 0 means "ignore Qloo"
SMOOTH = 50  # pseudo-reviews of the typical mix blended into the adjusted truth, so tiny languages can't swing it

games = pd.read_csv(DATA / "test_games.csv").set_index("appid")
raw = pd.read_csv(DATA / "truth_reviews.csv").set_index("appid")
comps = pd.read_csv(DATA / "comps.csv")
counts = pd.DataFrame({t: raw[[f"rev_{c}" for c in codes]].sum(axis=1) for t, codes in TARGETS.items()})
truth = counts.div(counts.sum(axis=1), axis=0)
ids = list(truth.index)
total = truth.sum()


def typical(exclude=()):
    """Average language mix of English-only games, leaving out the given games."""
    return (total - truth.loc[list(exclude)].sum()) / (len(ids) - len(exclude))


def rank_by(scores):
    """Languages by score, highest first; missing scores last; ties keep the generic order."""
    s = scores.reindex(LANGS).fillna(-np.inf)
    return sorted(LANGS, key=lambda l: (-s[l], GENERIC.index(l)))


def top3(rank, t):
    return len(set(rank[:3]) & set(t.nlargest(3).index)) / 3


def rho(rank, t):
    return spearmanr([-rank.index(l) for l in LANGS], t[LANGS])[0]


# Qloo: each look-alike's fan map -> per-language score; a game's score = mean over its look-alikes
def language_scores(country):
    out = {}
    for lang, weights in COUNTRIES.items():
        have = {c: w for c, w in weights.items() if c in country}
        out[lang] = sum(country[c] * w for c, w in have.items()) / sum(have.values()) if have else np.nan
    return pd.Series(out)


comp_scores = {c.qloo_id: language_scores(qloo.country_scores(qloo.world_cells(c.comp_name, c.qloo_id)))
               for c in comps.drop_duplicates("qloo_id").itertuples()}
baseline = pd.DataFrame(comp_scores).T.mean()  # average fan map over all look-alikes (no test-game data in it)
game_q = {g: pd.DataFrame([comp_scores[q] for q in comps[comps.test_appid == g].qloo_id]).mean()
          if (comps.test_appid == g).any() else pd.Series(dtype=float) for g in ids}
lift = {g: (game_q[g] / baseline).reindex(LANGS).fillna(1.0) for g in ids}


def choose_alpha(g, prior):
    """Alpha with the best mean top-3 hit on every game except g (ties -> the smaller alpha)."""
    return max(ALPHAS, key=lambda a: np.mean([top3(rank_by(prior(h, (g, h)) * lift[h] ** a), truth.loc[h])
                                              for h in ids if h != g]))


def ai_rank(g, prior=None):
    gm = games.loc[g]
    names = ", ".join(comps[comps.test_appid == g].comp_name) or "none found"
    context = ("" if prior is None else "For reference, the typical share of non-English reviews for English-only indie "
               "games is: " + ", ".join(f"{l} {v:.1%}" for l, v in prior.sort_values(ascending=False).items()) +
               ". Adjust this for THIS game.\n")
    prompt = ("You advise indie game developers on which languages to translate a Steam game into. "
              "The game is released in English only.\n"
              f"Steam tags: {str(gm.tags).replace('|', ', ')}\nStore description: {gm.short_description}\n"
              f"Similar well-known games: {names}\n{context}"
              "Rank these translation targets from most to least expected player demand for THIS game: "
              + ", ".join(f"{l} ({LABEL[l]})" for l in LANGS) +
              '.\nAnswer only with JSON: {"ranking": [all 14 codes, most demand first]}')
    ranked = list(dict.fromkeys(l for l in llm.ask_json(prompt).get("ranking", []) if l in LANGS))
    return ranked + [l for l in GENERIC if l not in ranked], len(ranked) == len(LANGS)


rows, alphas, ai_ok = [], {"typ": [], "steam": []}, 0
for i, g in enumerate(ids, 1):
    prior = typical((g,))
    a_typ = choose_alpha(g, lambda h, ex: typical(ex))
    a_steam = choose_alpha(g, lambda h, ex: STEAM)
    alphas["typ"].append(a_typ)
    alphas["steam"].append(a_steam)
    ai_plain, ok1 = ai_rank(g)
    ai_prior, ok2 = ai_rank(g, prior)
    ai_ok += ok1 + ok2
    rankings = {
        "Generic tier list": GENERIC,
        "Steam size": rank_by(STEAM),
        "Typical mix (no Qloo)": rank_by(prior),
        "AI alone": ai_plain,
        "AI + typical mix": ai_prior,
        "Qloo alone": rank_by(game_q[g]) if len(game_q[g]) else GENERIC,
        "Babel: typical mix x Qloo": rank_by(prior * lift[g] ** a_typ),
        "Babel: Steam size x Qloo": rank_by(STEAM * lift[g] ** a_steam),
    }
    # adjusted truth: how much more (or less) this game gets each language than a typical English-only game
    n = counts.loc[g].sum()
    adj = ((truth.loc[g] * n + SMOOTH * prior) / (n + SMOOTH)) / prior
    for comp, rank in rankings.items():
        rows.append({"appid": g, "game": raw.loc[g, "name"], "competitor": comp, "ranking": "|".join(rank),
                     "top3_raw": top3(rank, truth.loc[g]), "rho_raw": rho(rank, truth.loc[g]),
                     "top3_adj": top3(rank, adj), "rho_adj": rho(rank, adj)})
    if i % 10 == 0:
        print(f"  {i}/{len(ids)} games")
pred = pd.DataFrame(rows)
pred.to_csv(DATA / "predictions.csv", index=False)
summary = pred.groupby("competitor", sort=False)[["top3_raw", "rho_raw", "top3_adj", "rho_adj"]].mean()


def paired(a, b, col):
    x = pred[pred.competitor == a].set_index("appid")[col] - pred[pred.competitor == b].set_index("appid")[col]
    w, l = int((x > 0).sum()), int((x < 0).sum())
    p = binomtest(w, w + l).pvalue if w + l else 1.0
    return f"| {a} | {b} | {col.replace('top3_', 'top-3 ')} | {w} | {int((x == 0).sum())} | {l} | {p:.2f} |"


# Sensitive test: within each language, across games, does a competitor's signal track the real over-index?
# (mean Spearman over languages; p-value from shuffling games within each language)
adj_all = pd.DataFrame({g: ((truth.loc[g] * counts.loc[g].sum() + SMOOTH * typical((g,)))
                            / (counts.loc[g].sum() + SMOOTH)) / typical((g,)) for g in ids}).T
with_comps = [g for g in ids if (comps.test_appid == g).any()]
rng = np.random.default_rng(0)


def within_language(signal, n_shuffles=500):
    def stat(m):
        rs = [spearmanr(m[l], adj_all.loc[with_comps, l])[0] for l in LANGS if m[l].nunique() > 1]
        return float(np.mean(rs))
    m = signal.loc[with_comps]
    obs = stat(m)
    null = [stat(m.apply(lambda c: pd.Series(rng.permutation(c.values), index=c.index))) for _ in range(n_shuffles)]
    return obs, float(np.mean(np.array(null) >= obs))


def rank_scores(comp):
    r = pred[pred.competitor == comp].set_index("appid").ranking
    return pd.DataFrame({g: {l: -r[g].split("|").index(l) for l in LANGS} for g in ids}).T


signals = {"Qloo lift (look-alike fan maps)": pd.DataFrame(lift).T, "AI alone (its ranking)": rank_scores("AI alone"),
           "AI + typical mix (its ranking)": rank_scores("AI + typical mix")}
sensitive = {name: within_language(s) for name, s in signals.items()}
per_lang = {l: spearmanr(pd.DataFrame(lift).T.loc[with_comps, l], adj_all.loc[with_comps, l])[0] for l in LANGS}
n_comps = comps.groupby("test_appid").size().reindex(ids).fillna(0).astype(int)
out = ["# Step 3 (mini): who picks the right languages?", "",
       f"{len(ids)} English-only indie games released 2024+ (development set). Truth = each game's share of non-English "
       "reviews over 14 translation targets (Spanish = Spain + Latin America). **Raw** = which languages wrote the most "
       "reviews. **Adjusted** = which languages this game over-indexes on versus a typical English-only game "
       f"(smoothed with {SMOOTH} typical reviews), i.e. the game-specific part only. Top-3 hit = how many of the real "
       "top 3 a competitor's top 3 contains.", "",
       "| Competitor | Top-3 hit (raw) | Spearman (raw) | Top-3 hit (adjusted) | Spearman (adjusted) |",
       "|---|---|---|---|---|"]
out += [f"| {c} | {r.top3_raw:.0%} | {r.rho_raw:.2f} | {r.top3_adj:.0%} | {r.rho_adj:.2f} |" for c, r in summary.iterrows()]
out += ["", "## Head to head (per game)", "", "| A | B | Measure | A better | Tie | B better | Sign test p |",
        "|---|---|---|---|---|---|---|",
        paired("Babel: typical mix x Qloo", "Typical mix (no Qloo)", "top3_raw"),
        paired("Babel: typical mix x Qloo", "Typical mix (no Qloo)", "top3_adj"),
        paired("Babel: typical mix x Qloo", "AI + typical mix", "top3_raw"),
        paired("Qloo alone", "AI alone", "top3_adj"),
        paired("Babel: typical mix x Qloo", "Generic tier list", "top3_raw"),
        "", "## Sensitive test: does the signal track which games over-index on which language?", "",
        f"Within each language, Spearman across the {len(with_comps)} games with look-alikes between the signal and the "
        "real over-index, averaged over languages. p = share of 500 within-language shuffles that score as high.", "",
        "| Signal | Mean within-language correlation | p |", "|---|---|---|"]
out += [f"| {name} | {r:+.3f} | {p:.3f} |" for name, (r, p) in sensitive.items()]
out += ["", "Qloo lift per language: " + ", ".join(f"{LABEL[l]} {v:+.2f}" for l, v in per_lang.items()),
        "", "## Settings and data",
        "", f"- Alpha chosen by leave-one-out (typical-mix Babel): {pd.Series(alphas['typ']).value_counts().to_dict()}; "
        f"(Steam-size Babel): {pd.Series(alphas['steam']).value_counts().to_dict()}. Alpha 0 = Qloo ignored.",
        f"- Look-alikes per game: {n_comps.value_counts().sort_index().to_dict()} (games without any fall back to the prior).",
        f"- AI answers that ranked all 14 languages: {ai_ok} of {2 * len(ids)} (gaps filled in generic order).",
        f"- API calls this run: Groq {net.calls['api.groq.com']} (cached {net.cache_hits['api.groq.com']}), "
        f"Qloo {net.calls['hackathon.api.qloo.com']} (cached {net.cache_hits['hackathon.api.qloo.com']}).",
        "", "## Per game (top 3)", "",
        "| Game | Real | Typical mix | Babel (typical x Qloo) | AI + typical | AI alone | Qloo alone |", "|---|---|---|---|---|---|---|"]
short = lambda r: ", ".join(LABEL[l] for l in r.split("|")[:3])  # noqa: E731
for g in ids:
    p = pred[pred.appid == g].set_index("competitor").ranking
    out.append(f"| {raw.loc[g, 'name']} | {', '.join(LABEL[l] for l in truth.loc[g].nlargest(3).index)} | "
               f"{short(p['Typical mix (no Qloo)'])} | {short(p['Babel: typical mix x Qloo'])} | "
               f"{short(p['AI + typical mix'])} | {short(p['AI alone'])} | {short(p['Qloo alone'])} |")
(HERE / "step3_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out[: out.index("## Per game (top 3)")]))
