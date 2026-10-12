"""Final backtest, following PREREGISTRATION.md: does Qloo improve the language recommendation?

Two truths: Steam reviews (Steam set) and Wikipedia pageviews (Wiki set). Dev games choose the Qloo signal and alpha;
test games give the verdict. Every competitor sees only pre-launch info (tags, description, look-alike games).
Run after build_dataset.py and build_wiki_set.py: python backtest/evaluate.py -> final_report.md, data/final_*.csv
"""
import os
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import binomtest, spearmanr  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from babel import llm, net, qloo  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*constant.*")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SEED, ALPHAS, SMOOTH, N_SHUFFLES, N_BOOT, SELF_SAMPLE = 7, [0, 1, 2, 4, 8, 16, 32], 50, 1000, 2000, 100

# ---------------------------------------------------------------- languages, countries, priors
TARGETS = {"schinese": ["schinese"], "japanese": ["japanese"], "koreana": ["koreana"], "brazilian": ["brazilian"],
           "russian": ["russian"], "spanish": ["spanish", "latam"], "turkish": ["turkish"], "german": ["german"],
           "french": ["french"], "tchinese": ["tchinese"], "polish": ["polish"], "italian": ["italian"],
           "ukrainian": ["ukrainian"], "thai": ["thai"]}
LABEL = {"schinese": "Simplified Chinese", "japanese": "Japanese", "koreana": "Korean", "brazilian": "Portuguese-BR",
         "russian": "Russian", "spanish": "Spanish", "turkish": "Turkish", "german": "German", "french": "French",
         "tchinese": "Traditional Chinese", "polish": "Polish", "italian": "Italian", "ukrainian": "Ukrainian",
         "thai": "Thai", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian",
         "es": "Spanish", "tr": "Turkish", "de": "German", "fr": "French", "pl": "Polish", "it": "Italian",
         "uk": "Ukrainian", "th": "Thai"}
GENERIC = ["schinese", "japanese", "koreana", "brazilian", "russian", "spanish", "turkish", "german", "french",
           "tchinese", "polish", "thai", "ukrainian", "italian"]
STEAM_SHARE = {"schinese": 31.39, "russian": 9.05, "spanish": 4.83, "brazilian": 3.70, "german": 2.48, "japanese": 2.41,
               "french": 2.08, "polish": 1.49, "koreana": 1.37, "tchinese": 1.27, "turkish": 1.09, "thai": 0.82,
               "ukrainian": 0.66, "italian": 0.56}  # Steam survey, Sep 2026, % of users
WIKI_OF = {"schinese": "zh", "tchinese": "zh", "japanese": "ja", "koreana": "ko", "brazilian": "pt", "russian": "ru",
           "spanish": "es", "turkish": "tr", "german": "de", "french": "fr", "polish": "pl", "italian": "it",
           "ukrainian": "uk", "thai": "th"}
WIKIS = list(dict.fromkeys(WIKI_OF.values()))
POP = {"CN": 1410, "TW": 23, "HK": 7.5, "MO": 0.7, "JP": 124, "KR": 52, "BR": 216, "PT": 10, "RU": 144, "BY": 9,
       "KZ": 20, "ES": 48, "MX": 129, "AR": 46, "CO": 52, "CL": 19, "PE": 34, "TR": 85, "DE": 84, "AT": 9, "CH": 9,
       "FR": 68, "BE": 12, "PL": 37, "IT": 59, "UA": 37, "TH": 72}  # millions
COUNTRY_NAME = {"CN": "China", "TW": "Taiwan", "HK": "Hong Kong", "MO": "Macau", "JP": "Japan", "KR": "South Korea",
                "BR": "Brazil", "PT": "Portugal", "RU": "Russia", "BY": "Belarus", "KZ": "Kazakhstan", "ES": "Spain",
                "MX": "Mexico", "AR": "Argentina", "CO": "Colombia", "CL": "Chile", "PE": "Peru", "TR": "Turkey",
                "DE": "Germany", "AT": "Austria", "CH": "Switzerland", "FR": "France", "BE": "Belgium", "PL": "Poland",
                "IT": "Italy", "UA": "Ukraine", "TH": "Thailand"}
COUNTRIES = {"schinese": ["CN"], "tchinese": ["TW", "HK", "MO"], "japanese": ["JP"], "koreana": ["KR"],
             "brazilian": ["BR"], "russian": ["RU", "BY", "KZ"], "spanish": ["ES", "MX", "AR", "CO", "CL", "PE"],
             "turkish": ["TR"], "german": ["DE", "AT", "CH"], "french": ["FR", "BE"], "polish": ["PL"],
             "italian": ["IT"], "ukrainian": ["UA"], "thai": ["TH"],
             "zh": ["CN", "TW", "HK", "MO"], "pt": ["BR", "PT"], "ja": ["JP"], "ko": ["KR"], "ru": ["RU", "BY", "KZ"],
             "es": ["ES", "MX", "AR", "CO", "CL", "PE"], "tr": ["TR"], "de": ["DE", "AT", "CH"], "fr": ["FR", "BE"],
             "pl": ["PL"], "it": ["IT"], "uk": ["UA"], "th": ["TH"]}
SIGNALS = {"S1": "Look-alike fan maps (affinity)", "S2": "Look-alike fan maps (fan mass)",
           "S5": "Look-alike affinity per country (entity insights)"}


class Space:
    """A truth: its languages, per-game shares, sample sizes, and how a 14-target ranking maps onto it."""

    def __init__(self, name, langs, shares, n_eff, to_space):
        self.name, self.langs, self.shares, self.n_eff, self.to_space = name, langs, shares, n_eff, to_space


steam_space = lambda r: list(r)  # noqa: E731
wiki_space = lambda r: list(dict.fromkeys(WIKI_OF[l] for l in r))  # noqa: E731

# ---------------------------------------------------------------- data
HAS_WIKI = (DATA / "truth_wiki.csv").exists()  # the Steam part can run before the Wiki set is built
HAS_CLAUDE = bool(os.environ.get("ANTHROPIC_API_KEY"))  # .env is loaded when babel.llm is imported
steam_comps = pd.read_csv(DATA / "comps.csv")
wiki_comps = pd.read_csv(DATA / "wiki_comps.csv") if HAS_WIKI else steam_comps.iloc[0:0]
games = pd.concat([pd.read_csv(DATA / "test_games.csv").assign(set="steam")] +
                  ([pd.read_csv(DATA / "wiki_games.csv").assign(set="wiki")] if HAS_WIKI else [])
                  ).drop_duplicates("appid").set_index("appid")
comps = pd.concat([steam_comps, wiki_comps]).drop_duplicates(["test_appid", "comp_appid"])
reviews = pd.read_csv(DATA / "truth_reviews.csv").set_index("appid")
counts = pd.DataFrame({t: reviews[[f"rev_{c}" for c in codes]].sum(axis=1) for t, codes in TARGETS.items()})
steam_truth = Space("Steam reviews", list(TARGETS), counts.div(counts.sum(axis=1), axis=0), counts.sum(axis=1),
                    steam_space)
if HAS_WIKI:
    wt = pd.read_csv(DATA / "truth_wiki.csv").set_index("appid")
    wt = wt[(wt.set == "wiki") & (wt.articles >= 3) & (wt.views_total > 0)]
    wiki_truth = Space("Wikipedia pageviews", WIKIS, wt[[f"share_{w}" for w in WIKIS]].set_axis(WIKIS, axis=1),
                       wt.views_total / 100, wiki_space)  # 100 views ~ 1 review for smoothing
dev_steam = set(pd.read_csv(DATA / "dev_test_games_43.csv").appid) & set(steam_truth.shares.index)
wiki_ids = sorted(wiki_truth.shares.index) if HAS_WIKI else []
dev_wiki = set(pd.Series(wiki_ids).sample(frac=0.5, random_state=SEED)) if HAS_WIKI else set()

# ---------------------------------------------------------------- Qloo signals per comp
print("Qloo signals")
comp_ids = sorted(comps.qloo_id.unique())
comp_name = comps.drop_duplicates("qloo_id").set_index("qloo_id").comp_name
profile = {q: qloo.country_profile(qloo.world_cells(comp_name[q], q)) for q in comp_ids}
entity_aff = {q: {} for q in comp_ids}  # S5: affinity of each comp in each country (batched per set: stable cache)
for set_name, set_ids in (("steam", sorted(steam_comps.qloo_id.unique())), ("wiki", sorted(wiki_comps.qloo_id.unique()))):
    for cc, name in COUNTRY_NAME.items():
        for i in range(0, len(set_ids), 50):  # Qloo caps take at 50
            batch = set_ids[i:i + 50]
            status, body = qloo.fetch(f"games_in_{qloo.slug(name)}_{set_name}_{i // 50}", "/v2/insights",
                                      {"filter.type": "urn:entity:videogame", "filter.results.entities": ",".join(batch),
                                       "signal.location.query": name, "take": len(batch)})
            for e in (body.get("results") or {}).get("entities", []) if status == 200 else []:
                entity_aff.setdefault(e["entity_id"], {})[cc] = e["query"]["affinity"]
s5_coverage = np.mean([len(entity_aff[q]) / len(COUNTRY_NAME) for q in comp_ids])
print(f"  {len(comp_ids)} comps; S5 country coverage {s5_coverage:.0%}")


def lang_scores(country, langs, additive=False):
    out = {}
    for l in langs:
        have = [c for c in COUNTRIES[l] if c in country]
        if additive:
            out[l] = sum(country[c] for c in have) if have else np.nan
        else:
            out[l] = sum(country[c] * POP[c] for c in have) / sum(POP[c] for c in have) if have else np.nan
    s = pd.Series(out, dtype=float)
    return s / s.sum() if additive else s


def comp_signal(q, sig, langs):
    if sig == "S1":
        return lang_scores(profile[q]["affinity"], langs)
    if sig == "S2":
        return lang_scores(profile[q]["mass"], langs, additive=True)
    return lang_scores(entity_aff.get(q, {}), langs)


def lifts(space, ids, sig):
    """Per game: mean of its comps' signal / mean over every comp used by these games (no truth involved)."""
    used = comps[comps.test_appid.isin(ids)]
    per_comp = {q: comp_signal(q, sig, space.langs) for q in used.qloo_id.unique()}
    base = pd.DataFrame(per_comp).T.mean()
    out = {}
    for g in ids:
        qs = used[used.test_appid == g].qloo_id
        raw = pd.DataFrame([per_comp[q] for q in qs]).mean() if len(qs) else pd.Series(dtype=float)
        out[g] = (raw.reindex(space.langs), (raw / base).reindex(space.langs).fillna(1.0))
    return out


# ---------------------------------------------------------------- AI competitor
def ai_prompt(g, prior=None):
    """The one prompt both AI competitors (Groq and Claude) get: tags, description, look-alikes; never the name."""
    gm = games.loc[g]
    names = ", ".join(comps[comps.test_appid == g].comp_name) or "none found"
    context = ("" if prior is None else "For reference, the typical share of non-English reviews for English-only indie "
               "games is: " + ", ".join(f"{l} {v:.1%}" for l, v in prior.sort_values(ascending=False).items()) +
               ". Adjust this for THIS game.\n")
    prompt = ("You advise indie game developers on which languages to translate a Steam game into. "
              + ("The game is released in English only.\n" if gm.set == "steam" else "\n") +
              f"Steam tags: {str(gm.tags).replace('|', ', ')}\nStore description: {gm.short_description}\n"
              f"Similar well-known games: {names}\n{context}"
              "Rank these translation targets from most to least expected player demand for THIS game: "
              + ", ".join(f"{l} ({LABEL[l]})" for l in TARGETS) +
              '.\nAnswer only with JSON: {"ranking": [all 14 codes, most demand first]}')
    return prompt


def complete(ranking):
    """Keep valid codes once each, then fill any missing ones in generic order."""
    ranked = list(dict.fromkeys(l for l in ranking if l in TARGETS))
    return ranked + [l for l in GENERIC if l not in ranked]


def ai_rank(g, prior=None):
    return complete(llm.ask_json(ai_prompt(g, prior)).get("ranking", []))


CLAUDE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ranking"],
                 "properties": {"ranking": {"type": "array", "items": {"type": "string", "enum": list(TARGETS)}}}}


def claude_ranks(ids, prior=None):
    """Claude Opus 5.5 rankings for many games at once (same prompt as the Groq AI, JSON-schema output)."""
    answers = llm.ask_claude_many([ai_prompt(g, prior) for g in ids], CLAUDE_SCHEMA)
    return {g: complete(a.get("ranking", [])) for g, a in zip(ids, answers)}


# ---------------------------------------------------------------- metrics
def rank_by(scores, space):
    s = scores.reindex(space.langs).fillna(-np.inf)
    order = space.to_space(GENERIC)
    return sorted(space.langs, key=lambda l: (-s[l], order.index(l)))


def coverage(rank, t):
    return float(t[rank[:3]].sum())


def hit3(rank, t):
    return len(set(rank[:3]) & set(t.nlargest(3).index)) / 3


def rho(rank, t):
    return spearmanr([-rank.index(l) for l in t.index], t.values)[0]


def adjusted(space, g, prior):
    n = space.n_eff[g]
    return ((space.shares.loc[g] * n + SMOOTH * prior) / (n + SMOOTH)) / prior


def within_language(signal, adj, n_shuffles=0, rng=None):
    """Mean over languages of the Spearman across games between a signal and the real over-index (+ shuffle p)."""
    def stat(m):
        rs = [spearmanr(m[l], adj[l])[0] for l in adj.columns if m[l].nunique() > 1 and adj[l].nunique() > 1]
        return float(np.mean(rs)) if rs else np.nan
    obs = stat(signal)
    if not n_shuffles or np.isnan(obs):
        return obs, None
    null = [stat(signal.apply(lambda c: pd.Series(rng.permutation(c.values), index=c.index))) for _ in range(n_shuffles)]
    return obs, float(np.mean(np.array(null) >= obs))


def evaluate(space, dev, test, ai_typical=False):
    rng = np.random.default_rng(SEED)
    dev, test = sorted(dev), sorted(test)
    T = space.shares
    sig_lifts = {s: lifts(space, dev + test, s) for s in SIGNALS}
    with_comps = lambda ids: [g for g in ids if (comps.test_appid == g).any()]  # noqa: E731

    # --- choices on dev (leave-one-out prior)
    loo = {g: T.loc[[h for h in dev if h != g]].mean() for g in dev}
    adj_dev = pd.DataFrame({g: adjusted(space, g, loo[g]) for g in dev}).T
    dev_corr = {s: within_language(pd.DataFrame({g: sig_lifts[s][g][1] for g in with_comps(dev)}).T,
                                   adj_dev.loc[with_comps(dev)])[0] for s in SIGNALS}
    primary = max(SIGNALS, key=lambda s: -np.inf if np.isnan(dev_corr[s]) else dev_corr[s])
    alpha = {s: max(ALPHAS, key=lambda a: np.mean([coverage(rank_by(loo[g] * sig_lifts[s][g][1] ** a, space), T.loc[g])
                                                   for g in dev])) for s in SIGNALS}

    # --- verdict on test (prior = dev mean)
    prior = T.loc[dev].mean()
    adj_test = pd.DataFrame({g: adjusted(space, g, prior) for g in test}).T
    claude = claude_ranks(test) if HAS_CLAUDE else {}
    claude_typ = claude_ranks(test, prior) if HAS_CLAUDE and ai_typical else {}
    rows = []
    for i, g in enumerate(test, 1):
        q_raw = sig_lifts[primary][g][0]
        ranks = {"Generic tier list": space.to_space(GENERIC),
                 "Steam user share": rank_by(pd.Series({l: sum(STEAM_SHARE[t] for t in TARGETS if space.to_space([t])[0] == l)
                                                        for l in space.langs}), space),
                 "Typical mix (no Qloo)": rank_by(prior, space),
                 "AI alone": space.to_space(ai_rank(g))}
        if ai_typical:
            ranks["AI + typical mix"] = space.to_space(ai_rank(g, prior))
        if claude:
            ranks["Claude alone"] = space.to_space(claude[g])
        if claude_typ:
            ranks["Claude + typical mix"] = space.to_space(claude_typ[g])
        ranks["Qloo alone"] = rank_by(q_raw, space) if q_raw.notna().any() else space.to_space(GENERIC)
        for s in SIGNALS:
            label = f"Babel: typical x {s}" + (" (primary)" if s == primary else "")
            ranks[label] = rank_by(prior * sig_lifts[s][g][1] ** alpha[s], space)
        for comp, r in ranks.items():
            rows.append({"appid": g, "competitor": comp, "ranking": "|".join(r), "coverage": coverage(r, T.loc[g]),
                         "hit3": hit3(r, T.loc[g]), "rho": rho(r, T.loc[g]), "hit3_adj": hit3(r, adj_test.loc[g])})
        if i % 50 == 0:
            print(f"  {space.name}: {i}/{len(test)} test games")
    res = pd.DataFrame(rows)
    babel = f"Babel: typical x {primary} (primary)"
    x = res[res.competitor == babel].set_index("appid").coverage - \
        res[res.competitor == "Typical mix (no Qloo)"].set_index("appid").coverage
    wins, losses = int((x > 1e-12).sum()), int((x < -1e-12).sum())
    sign_p = binomtest(wins, wins + losses, alternative="greater").pvalue if wins + losses else 1.0
    boot = [x.sample(frac=1, replace=True, random_state=b).mean() for b in range(N_BOOT)]
    tc = with_comps(test)
    sens = {f"{s}: {SIGNALS[s]}": within_language(pd.DataFrame({g: sig_lifts[s][g][1] for g in tc}).T,
                                                  adj_test.loc[tc], N_SHUFFLES, rng) for s in SIGNALS}
    ai_scores = pd.DataFrame({g: {l: -r.split("|").index(l) for l in space.langs} for g, r in
                              res[res.competitor == "AI alone"].set_index("appid").ranking.items()}).T
    sens["AI alone (its ranking)"] = within_language(ai_scores.loc[tc], adj_test.loc[tc], N_SHUFFLES, rng)
    if claude:
        cl_scores = pd.DataFrame({g: {l: -r.split("|").index(l) for l in space.langs} for g, r in
                                  res[res.competitor == "Claude alone"].set_index("appid").ranking.items()}).T
        sens["Claude alone (its ranking)"] = within_language(cl_scores.loc[tc], adj_test.loc[tc], N_SHUFFLES, rng)
    corr_p = sens[f"{primary}: {SIGNALS[primary]}"][1]
    corr_ok = corr_p is not None and corr_p < 0.05
    verdict = ("Qloo adds value" if sign_p < 0.05 and corr_ok else
               "Qloo adds a weak signal only" if corr_ok else "No measurable value from Qloo")
    return {"space": space, "dev": dev, "test": test, "res": res, "primary": primary, "alpha": alpha,
            "dev_corr": dev_corr, "wins": wins, "ties": len(x) - wins - losses, "losses": losses, "sign_p": sign_p,
            "diff": x.mean(), "ci": (np.percentile(boot, 2.5), np.percentile(boot, 97.5)), "sens": sens,
            "verdict": verdict, "n_with_comps": len(tc), "lifts": sig_lifts, "prior": prior}


def self_check(space, ids):
    """Validity check: does the game's OWN Qloo fan map (post-launch data) track its real over-index?"""
    rng = np.random.default_rng(SEED)
    sample = sorted(pd.Series(sorted(ids)).sample(min(SELF_SAMPLE, len(ids)), random_state=SEED))
    default = qloo.default_fingerprint()
    base = pd.DataFrame([comp_signal(q, "S1", space.langs) for q in comp_ids]).mean()
    own, found, default_maps = {}, 0, 0
    for g in sample:
        hit = qloo.search_game(games.loc[g, "name"])
        cells = qloo.world_cells(games.loc[g, "name"], hit["entity_id"]) if hit else []
        found += bool(hit)
        default_maps += bool(cells) and qloo.fingerprint(cells) == default
        if cells and qloo.fingerprint(cells) != default:
            own[g] = (lang_scores(qloo.country_scores(cells), space.langs) / base).fillna(1.0)
    counts_ = {"sampled": len(sample), "found": found, "default": default_maps, "real": len(own)}
    if len(own) < 10:
        return counts_, (np.nan, None)
    prior = space.shares.loc[sorted(ids)].mean()
    adj = pd.DataFrame({g: adjusted(space, g, prior) for g in own}).T
    return counts_, within_language(pd.DataFrame(own).T, adj, N_SHUFFLES, rng)


# ---------------------------------------------------------------- run
print("Steam truth")
steam_res = evaluate(steam_truth, dev_steam, set(steam_truth.shares.index) - dev_steam, ai_typical=True)
results = [steam_res]
if HAS_WIKI:
    print("Wikipedia truth")
    results.append(evaluate(wiki_truth, dev_wiki, set(wiki_ids) - dev_wiki))
print("Validity checks")
selfs = [("Steam reviews", self_check(steam_truth, steam_truth.shares.index))]
if HAS_WIKI:
    selfs.append(("Wikipedia pageviews", self_check(wiki_truth, wiki_ids)))
for r, tag in zip(results, ("steam", "wiki")):
    r["res"].to_csv(DATA / f"final_predictions_{tag}.csv", index=False)

# ---------------------------------------------------------------- chart: test-set coverage by competitor
fig, axes = plt.subplots(1, len(results), figsize=(5.5 * len(results), 4.8), dpi=150, sharex=True, squeeze=False)
fig.patch.set_facecolor("#fcfcfb")
for ax, r in zip(axes[0], results):
    m = r["res"].groupby("competitor", sort=False).coverage.mean().sort_values()
    colors = ["#eb6834" if (c.startswith("Babel") or c == "Qloo alone") else "#2a78d6" for c in m.index]
    ax.set_facecolor("#fcfcfb")
    ax.barh(m.index, m.values, height=0.62, color=colors)
    for i, v in enumerate(m.values):
        ax.text(v + 0.01, i, f"{v:.0%}", va="center", fontsize=8, color="#0b0b0b")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#d9d8d4")
    ax.grid(axis="x", color="#e6e5e1", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors="#52514e", length=0, labelsize=8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title(f"{r['space'].name}: {len(r['test'])} test games", loc="left", fontsize=10, color="#0b0b0b")
fig.suptitle("Share of real non-English demand covered by each method's top 3 languages", x=0.01, ha="left",
             fontsize=12, color="#0b0b0b")
fig.legend(handles=[matplotlib.patches.Patch(color="#2a78d6", label="Without Qloo"),
                    matplotlib.patches.Patch(color="#eb6834", label="With Qloo")], loc="upper right", frameon=False,
           fontsize=9)
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(DATA / "final_coverage.png", facecolor=fig.get_facecolor())

# ---------------------------------------------------------------- report
def section(r):
    s = r["space"]
    m = r["res"].groupby("competitor", sort=False)[["coverage", "hit3", "rho", "hit3_adj"]].mean()
    out = [f"## {s.name}", "",
           f"Dev {len(r['dev'])} games, test {len(r['test'])} games ({r['n_with_comps']} with look-alikes). "
           f"Primary Qloo signal chosen on dev: **{r['primary']} ({SIGNALS[r['primary']]})**; dev correlations: "
           + ", ".join(f"{k} {v:+.3f}" for k, v in r["dev_corr"].items()) + "; alpha: "
           + ", ".join(f"{k} {v}" for k, v in r["alpha"].items()) + ".", "",
           "| Competitor | Top-3 coverage (primary) | Top-3 hit | Spearman | Top-3 hit (adjusted) |", "|---|---|---|---|---|"]
    out += [f"| {c} | {v.coverage:.1%} | {v.hit3:.0%} | {v.rho:.2f} | {v.hit3_adj:.0%} |" for c, v in m.iterrows()]
    lo, hi = r["ci"]
    out += ["", f"**Primary test, Babel vs typical mix (coverage):** Babel better on {r['wins']} games, tie {r['ties']}, "
            f"worse {r['losses']}; one-sided sign test p = {r['sign_p']:.3f}; mean difference {r['diff']:+.2%} "
            f"(95% bootstrap CI {lo:+.2%} to {hi:+.2%}).", "",
            "| Signal (test games with look-alikes) | Within-language correlation with real over-index | Shuffle p |",
            "|---|---|---|"]
    out += [f"| {k} | {v[0]:+.3f} | {v[1]:.3f} |" if v[1] is not None else f"| {k} | n/a (no data) | n/a |"
            for k, v in r["sens"].items()]
    out += ["", f"**Pre-registered verdict ({s.name}): {r['verdict']}.**", ""]
    return out


both = {r["verdict"] for r in results}
overall = ("Qloo adds value" if "Qloo adds value" in both else
           "Qloo adds a weak signal only" if "Qloo adds a weak signal only" in both else "No measurable value from Qloo")
out = ["# Babel final backtest", "", "Follows [PREREGISTRATION.md](PREREGISTRATION.md). Coverage = share of the game's "
       "real non-English demand that falls in the 3 recommended languages.", "",
       f"## Overall verdict: **{overall}**", ""]
out += [f"- {r['space'].name}: {r['verdict']} (Babel {r['diff']:+.2%} coverage vs typical mix, p = {r['sign_p']:.3f})."
        for r in results]
out += ["", "![Coverage by method](data/final_coverage.png)", ""]
for r in results:
    out += section(r)
out += ["## Validity check: the game's own Qloo fan map (post-launch, not a competitor)", "",
        "| Truth | Sampled | Found in Qloo | Default (no-data) map | Real map | Within-language correlation | Shuffle p |",
        "|---|---|---|---|---|---|---|"]
for name, (c, (r, p)) in selfs:
    out.append(f"| {name} | {c['sampled']} | {c['found']} | {c['default']} | {c['real']} | "
               f"{'n/a' if p is None else f'{r:+.3f}'} | {'n/a' if p is None else f'{p:.3f}'} |")
out += ["", "## API usage this run", "", "| Host | Network calls | From cache |", "|---|---|---|"]
out += [f"| {h} | {net.calls[h]} | {net.cache_hits[h]} |" for h in sorted(set(net.calls) | set(net.cache_hits))]
(HERE / "final_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
