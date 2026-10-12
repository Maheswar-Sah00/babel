"""Wikidata + Wikipedia pageviews: an independent, platform-neutral measure of interest in a game by language."""
import hashlib
import json
import urllib.parse
from pathlib import Path

from . import net

CACHE = Path(__file__).resolve().parent.parent / "cache" / "wiki"
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "BabelBacktest/0.1 (Qloo hackathon research project; non-commercial)"}
# Wikipedia editions for each translation target (one Chinese and one Portuguese wiki serve both variants)
WIKIS = ["zh", "ja", "ko", "pt", "ru", "es", "tr", "de", "fr", "pl", "it", "uk", "th"]
SITES = " ".join(f"<https://{w}.wikipedia.org/>" for w in WIKIS)


def _get(url, params=None):
    cached = CACHE / f"{hashlib.md5(f'{url}{json.dumps(params, sort_keys=True)}'.encode()).hexdigest()[:12]}.json"
    if cached.exists():
        net.cache_hits[url.split("/")[2]] += 1
        return json.loads(cached.read_text(encoding="utf-8"))
    status, body = net.request(url, params, UA)
    data = body if status == 200 else {"_status": status}
    net.save(cached, json.dumps(data, ensure_ascii=False))
    return data


def sparql(query):
    return _get("https://query.wikidata.org/sparql",
                {"query": query, "format": "json"}).get("results", {}).get("bindings", [])


def articles_by_steam_id(appids):
    """{appid: {wiki: article title}} for the 13 target Wikipedias, via Wikidata's Steam application ID (P1733)."""
    out = {}
    appids = [str(a) for a in appids]
    for i in range(0, len(appids), 150):
        values = " ".join(f'"{a}"' for a in appids[i:i + 150])
        rows = sparql(f"""SELECT ?appid ?site ?title WHERE {{ VALUES ?appid {{ {values} }} ?item wdt:P1733 ?appid .
            ?a schema:about ?item ; schema:isPartOf ?site ; schema:name ?title . VALUES ?site {{ {SITES} }} }}""")
        for r in rows:
            wiki = r["site"]["value"].split("//")[1].split(".")[0]
            out.setdefault(int(r["appid"]["value"]), {})[wiki] = r["title"]["value"]
    return out


def notable_games_since(year, min_wikis=3, limit=400):
    """Video games first released in `year` or later, with a Steam ID and articles in >= min_wikis target Wikipedias."""
    rows = sparql(f"""SELECT ?appid (SAMPLE(?label) AS ?name) (MIN(?date) AS ?released) (COUNT(DISTINCT ?site) AS ?n) WHERE {{
        ?item wdt:P31 wd:Q7889 ; wdt:P1733 ?appid ; wdt:P577 ?date .
        ?a schema:about ?item ; schema:isPartOf ?site . VALUES ?site {{ {SITES} }}
        OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) = "en") }}
    }} GROUP BY ?appid HAVING (MIN(?date) >= "{year}-01-01T00:00:00Z"^^xsd:dateTime && COUNT(DISTINCT ?site) >= {min_wikis})
    ORDER BY DESC(?n) LIMIT {limit}""")
    return [{"appid": int(r["appid"]["value"]), "name": r.get("name", {}).get("value", ""),
             "released": r["released"]["value"][:10], "wikis": int(r["n"]["value"])}
            for r in rows if r["appid"]["value"].isdigit()]


def pageviews(wiki, title, start="20230101", end="20260930"):
    """Monthly human pageviews summed over [start, end] (0 if the article has no data)."""
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    body = _get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{wiki}.wikipedia.org/all-access/user/"
                f"{t}/monthly/{start}/{end}")
    return sum(i["views"] for i in body.get("items", []))
