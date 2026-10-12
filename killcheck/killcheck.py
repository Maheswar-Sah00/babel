"""Day-1 kill check: does Qloo have usable, genre-specific global heatmap data for video games?

Usage:
  python killcheck/killcheck.py --inspect   # Step 1 + print one raw heatmap response
  python killcheck/killcheck.py             # full run -> games_x_countries.csv, report.md
Every raw response is cached in cache/qloo/ and never re-requested (see babel/qloo.py).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from babel.qloo import WORLD, cells_of, country_scores, fetch, fingerprint, heatmap, norm, slug  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
GAMES = {
    "Cozy": ["Stardew Valley", "Unpacking", "A Short Hike"],
    "Roguelike": ["Slay the Spire", "Balatro", "Inscryption"],
    "Strategy": ["Hearts of Iron IV", "Total War: Warhammer III", "Manor Lords"],
    "Horror co-op": ["Phasmophobia", "Lethal Company", "Content Warning"],
    "Anime/VN": ["Doki Doki Literature Club", "Danganronpa", "Steins;Gate"],
}

# Step 1: resolve games
resolved = {}  # name -> (genre, entity)
print("Step 1: resolve games")
for genre, names in GAMES.items():
    for name in names:
        status, body = fetch(f"search_{slug(name)}", "/search",
                             {"query": name, "types": "urn:entity:videogame", "take": 3})
        hits = body.get("results", []) if status == 200 else []
        top = hits[0] if hits else None
        ok = bool(top) and (norm(name) in norm(top["name"]) or norm(top["name"]) in norm(name))
        flag = "" if ok else ("  <-- MISMATCH" if top else f"  <-- NOT FOUND (HTTP {status})")
        print(f"  [{genre}] {name} -> {top['name'] if top else '-'} {top['entity_id'] if top else ''}{flag}")
        if ok:
            resolved[name] = (genre, top)

if "--inspect" in sys.argv:
    name, (genre, ent) = next(iter(resolved.items()))
    for loc in ({}, {"filter.location.query": "Japan"}, {"filter.location": WORLD}):
        status, body = heatmap(name, ent["entity_id"], **loc)
        cells = (body.get("results") or {}).get("heatmap") if isinstance(body.get("results"), dict) else None
        print(f"\nRaw heatmap for {name} {loc or '(no location)'}: HTTP {status}, top-level keys {list(body)}, "
              f"results keys {list(body['results']) if isinstance(body.get('results'), dict) else '-'}, "
              f"cells {len(cells) if cells is not None else '-'}")
        print(json.dumps(body, indent=2, ensure_ascii=False)[:1500])
    sys.exit()

import pandas as pd  # noqa: E402  (only needed past --inspect)
import reverse_geocoder as rg  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

FALLBACK = {"US": "United States", "CN": "China", "JP": "Japan", "KR": "South Korea", "BR": "Brazil", "RU": "Russia",
            "DE": "Germany", "FR": "France", "PL": "Poland", "ES": "Spain", "TR": "Turkey", "MX": "Mexico"}
KEY_MARKETS = ["CN", "JP", "KR", "BR", "RU", "PL", "DE"]


def top_signature(cells, n=50):
    return [(c["location"]["geohash"], round(c["query"]["affinity"], 4)) for c in cells[:n]]


def geo_rho(a, b):
    """Spearman of cell affinities over geohashes both heatmaps share."""
    a = {c["location"]["geohash"]: c["query"]["affinity"] for c in a}
    b = {c["location"]["geohash"]: c["query"]["affinity"] for c in b}
    shared = sorted(a.keys() & b.keys())
    return spearmanr([a[g] for g in shared], [b[g] for g in shared])[0], len(shared)


# Step 2: one global heatmap per game (world polygon); per-country queries only if that comes back empty
print("\nStep 2: heatmaps")
heat = {}
for name, (genre, ent) in resolved.items():
    status, body = heatmap(name, ent["entity_id"], **{"filter.location": WORLD})
    cells, source = (cells_of(body) if status == 200 else []), "world polygon"
    if not cells:
        source = "per-country fallback"
        for country in FALLBACK.values():
            s, b = heatmap(name, ent["entity_id"], **{"filter.location.query": country})
            cells += cells_of(b) if s == 200 else []
    heat[name] = (source, cells)
    print(f"  {name}: {len(cells)} cells via {source}")

# Sanity: are params honored? (a) same game, extra demographic signal; (b) same location, different game
first = next(iter(resolved))
base = heat[first][1]
_, varied_body = heatmap(first, resolved[first][1]["entity_id"],
                         **{"filter.location": WORLD, "signal.demographics.age": "35_and_younger"})
age_changed = top_signature(base) != top_signature(cells_of(varied_body))
other = next(n for n, (g, _) in resolved.items() if g != resolved[first][0])
rho_games, n_shared = geo_rho(base, heat[other][1])
sanity = [f"Same game ({first}), + `signal.demographics.age=35_and_younger`: top-50 cells "
          f"{'CHANGED (param honored)' if age_changed else 'IDENTICAL (param silently ignored?)'}",
          f"Same world polygon, {first} vs {other}: cell-affinity Spearman {rho_games:.2f} "
          f"over {n_shared} shared cells "
          f"({'game signal drives the map' if rho_games < 0.95 else 'near-identical: game signal may be ignored'})"]
print("\n".join("  " + s for s in sanity))

# Step 3: reverse-geocode every cell, country score = mean affinity of its cells
print("\nStep 3: aggregate")
all_cells = [(name, c) for name, (_, cells) in heat.items() for c in cells]
ccs = rg.search([(c["location"]["latitude"], c["location"]["longitude"]) for _, c in all_cells], mode=1)
long = pd.DataFrame({"game": [n for n, _ in all_cells], "country": [r["cc"] for r in ccs],
                     "affinity": [c["query"]["affinity"] for _, c in all_cells],
                     "popularity": [c["query"]["popularity"] for _, c in all_cells]})
wide = long.groupby(["game", "country"])["affinity"].mean().unstack()
wide.insert(0, "genre", [resolved[g][0] for g in wide.index])
wide.to_csv(HERE / "games_x_countries.csv")
scores = wide.drop(columns="genre")
print(f"  {scores.shape[0]} games x {scores.shape[1]} countries -> killcheck/games_x_countries.csv")

# Data quality: games whose heatmap is byte-identical to another game's carry no game-specific signal
by_map = {}
for name, (_, cells) in heat.items():
    by_map.setdefault(fingerprint(cells), []).append(name)
dupes = sorted(g for group in by_map.values() if len(group) > 1 for g in group)
# Robust variant: no duplicate-map games, countries with >= MIN_CELLS cells, popularity-weighted mean affinity
robust = pd.DataFrame.from_dict({name: country_scores(cells) for name, (_, cells) in heat.items() if name not in dupes},
                                orient="index").sort_index().sort_index(axis=1)


# Step 4: verdict
def evaluate(scores, n_resolved):
    n_countries = scores.notna().sum(axis=1)
    market_games = {m: int(scores[m].notna().sum()) if m in scores else 0 for m in KEY_MARKETS}
    missing = [m for m, n in market_games.items() if n * 2 < len(scores)]  # present = data for >= half the games
    within, between = [], []
    games = list(scores.index)
    for i, a in enumerate(games):
        for b in games[i + 1:]:
            pair = scores.loc[[a, b]].T.dropna()
            if len(pair) >= 10:
                (within if resolved[a][0] == resolved[b][0] else between).append(spearmanr(pair[a], pair[b])[0])
    w = sum(within) / len(within) if within else float("nan")
    bt = sum(between) / len(between) if between else float("nan")
    checks = [
        ("1. Coverage", "≥12/15 games resolved", f"{n_resolved}/15", n_resolved >= 12),
        ("2. Global reach", "median game in ≥20 countries", f"median {n_countries.median():.0f} countries",
         n_countries.median() >= 20),
        ("3. Key markets", "CN JP KR BR RU PL DE each in ≥half the games",
         "missing: " + (", ".join(missing) or "none"), not missing),
        ("4. Genre signal", "within − between Spearman ≥ 0.15",
         f"within {w:.2f} ({len(within)} pairs), between {bt:.2f} ({len(between)} pairs), diff {w - bt:+.2f}",
         w - bt >= 0.15),
    ]
    top5 = {g: ", ".join(f"{cc} {v:.3f}"
                         for cc, v in scores.loc[g].dropna().sort_values(ascending=False).head(5).items())
            for g in games}
    return {"checks": checks, "pass": all(c[3] for c in checks), "n_countries": n_countries,
            "markets": market_games, "missing": missing, "w": w, "bt": bt, "top5": top5}


def verdict_table(ev):
    return ["| Check | Criterion | Result | Verdict |", "|---|---|---|---|"] + [
        f"| {a} | {b} | {c} | {'PASS' if d else 'FAIL'} |" for a, b, c, d in ev["checks"]]


def top5_table(ev, label):
    return [f"| Game | Genre | Top 5 ({label}) |", "|---|---|---|"] + [
        f"| {g} | {resolved[g][0]} | {t} |" for g, t in ev["top5"].items()]


spec = evaluate(scores, len(resolved))
rob = evaluate(robust, len(resolved) - len(dupes))
out = ["# Video game heatmap kill check", "",
       "Qloo heatmaps require a location (`filter.location` or `filter.location.query`); "
       "'global' = a world WKT polygon. "
       "Country = reverse-geocoded cell centre (cells are geohash-3, ~156 km).", "",
       "## Step 1: games", "", "| Genre | Query | Qloo match | Entity ID |", "|---|---|---|---|"]
out += [f"| {g} | {n} | {resolved[n][1]['name'] if n in resolved else 'NOT RESOLVED'} | "
        f"{resolved[n][1]['entity_id'] if n in resolved else ''} |" for g, names in GAMES.items() for n in names]
out += ["", "## Sanity checks", ""] + [f"- {s}" for s in sanity]
out += [f"- Identical heatmaps across different games (no game-specific data): {', '.join(dupes) or 'none'}"]
out += ["", "## Verdict (spec: country score = mean cell affinity, all games)", ""] + verdict_table(spec)
out += ["", "Key market coverage (games with data): "
        + ", ".join(f"{m} {n}/{len(scores)}" for m, n in spec["markets"].items()),
        "", "## Robust verdict (duplicate-map games dropped, countries with ≥5 cells, "
        "popularity-weighted affinity)", ""]
out += verdict_table(rob)
out += ["", "## Top 5 countries per game (spec)", ""] + top5_table(spec, "mean cell affinity")
out += ["", "## Top 5 countries per game (robust)", ""] + top5_table(rob, "popularity-weighted, ≥5 cells")
summary = [f"Data: {len(resolved)}/15 games resolved, but {len(dupes)} share one identical heatmap "
           f"({', '.join(dupes) or '-'}).",
           f"Spec verdict {'PASS' if spec['pass'] else 'FAIL'}: genre diff {spec['w'] - spec['bt']:+.2f}, "
           f"median {spec['n_countries'].median():.0f} countries; key markets "
           f"{'all present' if not spec['missing'] else 'missing ' + ', '.join(spec['missing'])}.",
           f"Robust verdict {'PASS' if rob['pass'] else 'FAIL'}: genre diff {rob['w'] - rob['bt']:+.2f} "
           f"(within {rob['w']:.2f} vs between {rob['bt']:.2f}), median {rob['n_countries'].median():.0f} countries."]
out += ["", f"## OVERALL: {'PASS' if spec['pass'] and rob['pass'] else 'FAIL'} "
        f"(spec {'PASS' if spec['pass'] else 'FAIL'}, robust {'PASS' if rob['pass'] else 'FAIL'})", ""] + summary
(HERE / "report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n" + "\n".join(out[out.index("## Sanity checks"):]))
