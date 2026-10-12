"""Product-side Qloo insights for Babel's plan screen ("market notes"), for three example kinds of game:

1. Audience profile of the game's fans (Qloo demographics: age and gender skew).
2. Top markets: the target-language countries where the fan map is strongest (fan mass).
3. Per top market, what those fans also love (films, music), found in two steps so results stay local:
   a local pool from the location alone, then re-ranked by the game's fans.
Run: python backtest/market_insights.py -> market_insights.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from babel import net, qloo  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
HERE = Path(__file__).resolve().parent
EXAMPLES = {"Cozy farming": "Stardew Valley", "Grand strategy": "Hearts of Iron IV", "Anime visual novel": "Steins;Gate"}
MARKETS = {"CN": "China", "JP": "Japan", "KR": "South Korea", "BR": "Brazil", "RU": "Russia", "ES": "Spain",
           "MX": "Mexico", "TR": "Turkey", "DE": "Germany", "FR": "France", "PL": "Poland", "IT": "Italy",
           "TW": "Taiwan", "UA": "Ukraine", "TH": "Thailand"}
DOMAINS = {"Films": "urn:entity:movie", "Music": "urn:entity:artist"}


def also_loved(game_id, game, country, etype, n=4):
    """Local favourites of this domain in the country, re-ranked by the game's fans (two-step, stays local)."""
    s, body = qloo.fetch(f"local_{qloo.slug(country)}_{etype.split(':')[-1]}", "/v2/insights",
                         {"filter.type": etype, "signal.location.query": country, "take": 30})
    pool = [e["entity_id"] for e in (body.get("results") or {}).get("entities", [])] if s == 200 else []
    if not pool:
        return []
    s, body = qloo.fetch(f"fans_{qloo.slug(game)}_{qloo.slug(country)}_{etype.split(':')[-1]}", "/v2/insights",
                         {"filter.type": etype, "filter.results.entities": ",".join(pool),
                          "signal.interests.entities": game_id, "signal.location.query": country, "take": 30})
    return [e["name"] for e in (body.get("results") or {}).get("entities", [])][:n] if s == 200 else []


out = ["# Market insights from Qloo (examples for Babel's plan screen)", "",
       "Audience = how the fans differ from the average person (positive = over-represented). Markets = the "
       "target-language countries with the most fan mass on the game's world fan map. 'Also loves' = that country's "
       "local favourites, re-ranked by the game's fans (aggregate taste, not individuals).", ""]
for kind, game in EXAMPLES.items():
    ent = qloo.search_game(game)
    s, body = qloo.fetch(f"demographics_{qloo.slug(game)}", "/v2/insights",
                         {"filter.type": "urn:demographics", "signal.interests.entities": ent["entity_id"]})
    demo = ((body.get("results") or {}).get("demographics") or [{}])[0].get("query", {}) if s == 200 else {}
    ages = sorted((demo.get("age") or {}).items(), key=lambda kv: -kv[1])
    gender = demo.get("gender") or {}
    profile = qloo.country_profile(qloo.world_cells(game, ent["entity_id"]))
    markets = sorted((cc for cc in MARKETS if cc in profile["mass"]), key=lambda cc: -profile["mass"][cc])[:3]
    out += [f"## {kind}: {game}", "",
            f"- Audience (vs the average person): age {', '.join(f'{a.replace('_', ' ')} {v:+.2f}' for a, v in ages)}; "
            f"gender {', '.join(f'{k} {v:+.2f}' for k, v in gender.items())}.",
            f"- Top markets by fan mass: {', '.join(MARKETS[cc] for cc in markets)}.", "",
            "| Market | " + " | ".join(f"{d} these fans also love" for d in DOMAINS) + " |", "|---|---|---|"]
    for cc in markets:
        out.append(f"| {MARKETS[cc]} | " + " | ".join(", ".join(also_loved(ent["entity_id"], game, MARKETS[cc], t)) or "-"
                                                     for t in DOMAINS.values()) + " |")
    out.append("")
out += [f"Qloo calls this run: {net.calls['hackathon.api.qloo.com']} (cached {net.cache_hits['hackathon.api.qloo.com']})."]
(HERE / "market_insights.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
