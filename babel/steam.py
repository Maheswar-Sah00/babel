"""Public Steam store and SteamSpy data: cached in cache/steam/ (never re-requested), <= 1 request/sec per host."""
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

from . import net

CACHE = Path(__file__).resolve().parent.parent / "cache" / "steam"
CACHE.mkdir(parents=True, exist_ok=True)
STORE = "https://store.steampowered.com"
SPY = "https://steamspy.com/api.php"


def get(url, params):
    """Cached GET returning the body; a non-200 answer is cached as {'_status': code, '_body': body}."""
    cached = CACHE / f"{hashlib.md5(f'{url}{json.dumps(params, sort_keys=True)}'.encode()).hexdigest()[:12]}.json"
    if cached.exists():
        net.cache_hits[url.split("/")[2]] += 1
        return json.loads(cached.read_text(encoding="utf-8"))
    status, body = net.request(url, params)
    data = body if status == 200 else {"_status": status, "_body": body}
    net.save(cached, json.dumps(data, ensure_ascii=False))
    return data


def appdetails(appid):
    """Store data for an app ({} if Steam has none)."""
    body = get(f"{STORE}/api/appdetails", {"appids": int(appid), "l": "english"})
    return (body.get(str(appid)) or {}).get("data") or {}


def search(term):
    """Store search results for a name, best match first: [{'id', 'name', 'type', ...}]."""
    body = get(f"{STORE}/api/storesearch/", {"term": term, "l": "english", "cc": "US"})
    return body.get("items") or []


def review_total(appid, language="all"):
    """All-time review count for one review language ('all' = every language)."""
    body = get(f"{STORE}/appreviews/{int(appid)}",
               {"json": 1, "language": language, "purchase_type": "all", "filter": "all", "num_per_page": 0})
    return (body.get("query_summary") or {}).get("total_reviews")


def spy_tag(tag):
    return get(SPY, {"request": "tag", "tag": tag})


def spy_app(appid):
    return get(SPY, {"request": "appdetails", "appid": int(appid)})


def languages(details):
    """Supported languages from the store's HTML list, e.g. ['English']."""
    text = re.sub(r"<[^>]+>", " ", details.get("supported_languages") or "").replace(
        "languages with full audio support", "")
    return [x.strip(" *") for x in text.split(",") if x.strip(" *")]


def release_date(details):
    """Release date, or None if unreleased or unparseable."""
    rd = details.get("release_date") or {}
    if rd.get("coming_soon"):
        return None
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(rd.get("date", ""), fmt).date()
        except ValueError:
            pass
    return None


def released_between(details, start=date.min, end=date.max):
    d = release_date(details)
    return d is not None and start <= d < end
