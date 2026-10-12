"""Second, platform-neutral test set and a second truth: Wikipedia pageviews by language.

1. Wiki set: notable video games first released 2023+ (Wikidata), with a Steam ID and articles in 3+ of the
   13 target Wikipedias. Unlike the Steam set these may be translated, big-budget, or on several platforms.
2. Their Steam store data, SteamSpy tags and look-alike comps (same rules as the Steam set).
3. Wikipedia pageviews by language, from release to Sep 2026, for every game in both sets -> truth_wiki.csv

Run after build_dataset.py (both use Steam's rate limit): python backtest/build_wiki_set.py
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from babel import net, steam, wiki  # noqa: E402
from babel.comps import CompPicker, spy_tags  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

print("1. Wiki set")
found = wiki.notable_games_since(2023, min_wikis=3, limit=400)
rows = []
for g in found:
    d = steam.appdetails(g["appid"])
    released = steam.release_date(d)
    if d.get("type") != "game" or not released or released < date(2023, 1, 1):
        continue
    rows.append({"appid": g["appid"], "name": d["name"], "release_date": released.isoformat(), "wikis": g["wikis"],
                 "genres": "|".join(x["description"] for x in d.get("genres", [])),
                 "is_indie": any(x["description"] == "Indie" for x in d.get("genres", [])),
                 "supported_languages": "|".join(steam.languages(d)), "tags": "|".join(spy_tags(g["appid"])),
                 "short_description": d.get("short_description", "")})
wiki_games = pd.DataFrame(rows)
print(f"  {len(found)} from Wikidata -> {len(wiki_games)} Steam games released 2023+ ({int(wiki_games.is_indie.sum())} indie)")

print("2. Comps")
picker = CompPicker()
comp_rows = []
for g in wiki_games.itertuples():
    for c in picker.pick(spy_tags(g.appid)):
        comp_rows.append({"test_appid": g.appid, **c})
wiki_comps = pd.DataFrame(comp_rows)
wiki_games.to_csv(DATA / "wiki_games.csv", index=False)
wiki_comps.to_csv(DATA / "wiki_comps.csv", index=False)
per_game = wiki_comps.groupby("test_appid").size().reindex(wiki_games.appid).fillna(0).astype(int)
print(f"  comps per game: {per_game.value_counts().sort_index().to_dict()}")

print("3. Wikipedia pageviews (both sets)")
steam_games = pd.read_csv(DATA / "test_games.csv")
everyone = pd.concat([steam_games.assign(set="steam")[["appid", "name", "release_date", "set"]],
                      wiki_games.assign(set="wiki")[["appid", "name", "release_date", "set"]]]).drop_duplicates("appid")
articles = wiki.articles_by_steam_id(everyone.appid)
truth = []
for g in everyone.itertuples():  # one fixed window (Jan 2023 - Sep 2026) for every game; pre-release months are 0
    views = {w: wiki.pageviews(w, articles.get(g.appid, {})[w]) if w in articles.get(g.appid, {}) else 0
             for w in wiki.WIKIS}
    total = sum(views.values())
    truth.append({"appid": g.appid, "name": g.name, "set": g.set, "articles": len(articles.get(g.appid, {})),
                  "views_total": total, **{f"views_{w}": v for w, v in views.items()},
                  **{f"share_{w}": v / total if total else 0.0 for w, v in views.items()}})
truth = pd.DataFrame(truth)
truth.to_csv(DATA / "truth_wiki.csv", index=False)
for s, grp in truth.groupby("set"):
    print(f"  {s} set: {len(grp)} games, {int((grp.articles > 0).sum())} with >=1 target-language article, "
          f"{int((grp.articles >= 3).sum())} with >=3; median non-English views {grp.views_total.median():.0f}")
print("Calls this run:", {h: n for h, n in net.calls.items()}, "| cached:", dict(net.cache_hits))
