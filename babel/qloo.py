"""Qloo hackathon API: cached requests, world heatmaps, the no-data fingerprint and robust country scores."""
import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import reverse_geocoder as rg
from dotenv import load_dotenv

from . import net

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "qloo"
CACHE.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / ".env")
BASE = "https://hackathon.api.qloo.com"
HOST = BASE.split("/")[2]
WORLD = "POLYGON((-180 -85, 180 -85, 180 85, -180 85, -180 -85))"  # heatmaps require a location; this one is global
MIN_CELLS = 5  # a country needs this many heatmap cells to get a score


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def request_id(name, path, params):
    """A request's cache key, '<name>_<hash>': cache/qloo/<id>.json holds its raw response (provenance)."""
    return f"{name}_{hashlib.md5(f'{path}{json.dumps(params, sort_keys=True)}'.encode()).hexdigest()[:8]}"


def fetch(name, path, params):
    """Cached GET: cache/qloo/<name>_<hash>.json, never re-requested. Returns (status, body)."""
    cached = CACHE / f"{request_id(name, path, params)}.json"
    if cached.exists():
        net.cache_hits[HOST] += 1
        d = json.loads(cached.read_text(encoding="utf-8"))
        return d["status"], d["body"]
    status, body = net.request(BASE + path, params, {"X-Api-Key": os.environ["QLOO_API_KEY"]})
    net.save(cached, json.dumps({"status": status, "path": path, "params": params, "body": body},
                                indent=2, ensure_ascii=False))
    return status, body


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
EDITION = re.compile(r"\s*[-:–]?\s*\b(definitive|game of the year|goty|enhanced|complete|anniversary|deluxe|classic)"
                     r"\b( edition)?.*$", re.I)


def title_key(name):
    """Store-title-insensitive key: no ®/™, trailing (year) or edition suffix, and Roman numerals as digits."""
    s = EDITION.sub("", re.sub(r"\s*\((19|20)\d\d\)", "", re.sub(r"[®™©]", "", name or "")))
    return norm(" ".join(ROMAN.get(w, w) for w in re.split(r"[\s:]+", s.lower())))


def find_game(name):
    """(the Qloo video game with this name or None, HTTP status of the search that decided it).

    Exact match (ignoring case and punctuation) among the top 3 first; failing that, one more search for the
    cleaned title, matched by title_key among the top 10
    (so 'Original Sin 2 - Definitive Edition' finds 'Original Sin II').
    """
    status, body = fetch(f"search_{slug(name)}", "/search",
                         {"query": name, "types": "urn:entity:videogame", "take": 3})
    hit = next((h for h in (body.get("results", []) if status == 200 else []) if norm(h["name"]) == norm(name)), None)
    if hit or status != 200:
        return hit, status
    cleaned = EDITION.sub("", re.sub(r"\s*\((19|20)\d\d\)", "", re.sub(r"[®™©]", "", name))).strip()
    status, body = fetch(f"search_{slug(cleaned)}", "/search",
                         {"query": cleaned, "types": "urn:entity:videogame", "take": 10})
    return next((h for h in (body.get("results", []) if status == 200 else [])
                 if title_key(h["name"]) == title_key(name)), None), status


def search_game(name):
    """The Qloo video game with this name, else None (see find_game)."""
    return find_game(name)[0]


def heatmap(name, entity_id, **location):
    return fetch(f"heatmap_{slug(name)}", "/v2/insights",
                 {"filter.type": "urn:heatmap", "signal.interests.entities": entity_id, **location})


def cells_of(body):
    res = body.get("results")
    return res.get("heatmap", []) if isinstance(res, dict) else []


def world_cells(name, entity_id):
    status, body = heatmap(name, entity_id, **{"filter.location": WORLD})
    return cells_of(body) if status == 200 else []


def heatmap_id(name, entity_id):
    """Request id (cache key) of a game's world fan map, for provenance."""
    return request_id(f"heatmap_{slug(name)}", "/v2/insights", {
        "filter.type": "urn:heatmap", "signal.interests.entities": entity_id, "filter.location": WORLD})


def fingerprint(cells):
    """Hash of every cell (geohash + affinity): identical maps for different games mean Qloo has no data."""
    return hashlib.md5(json.dumps([(c["location"]["geohash"], round(c["query"]["affinity"], 6))
                                   for c in cells]).encode()).hexdigest()


def default_fingerprint():
    """The no-data default map found in the kill check (Lethal Company = Content Warning = Manor Lords)."""
    return fingerprint(world_cells("Lethal Company", search_game("Lethal Company")["entity_id"]))


def _by_country(cells):
    """Per country: sum of affinity x popularity, sum of popularity, cell count (countries with >= MIN_CELLS cells)."""
    cc = [r["cc"] for r in rg.search([(c["location"]["latitude"], c["location"]["longitude"]) for c in cells],
                                     mode=1, verbose=False)]
    d = pd.DataFrame({"cc": cc, "aff": [c["query"]["affinity"] for c in cells],
                      "pop": [c["query"]["popularity"] for c in cells]})
    g = d.assign(w=d.aff * d["pop"]).groupby("cc").agg(w=("w", "sum"), pop=("pop", "sum"), n=("aff", "size"))
    return g[(g.n >= MIN_CELLS) & (g["pop"] > 0)]


def country_scores(cells):
    """Robust per-country score: popularity-weighted mean cell affinity, countries with >= MIN_CELLS cells."""
    if not cells:
        return {}
    g = _by_country(cells)
    return (g.w / g["pop"]).to_dict()


def country_sums(cells):
    """{country: [sum of affinity x popularity, sum of popularity, cell count]} for countries with >= MIN_CELLS cells:
    everything country_profile needs, as stored in the precomputed runtime data (babel/runtime.py)."""
    if not cells:
        return {}
    g = _by_country(cells)
    return {cc: [float(w), float(pop), int(n)] for cc, w, pop, n in zip(g.index, g.w, g["pop"], g.n)}


def profile_from_sums(sums):
    """Per-country views of a fan map from country_sums: 'affinity' (popularity-weighted mean cell affinity: how
    over-represented fans are), 'mass' (affinity x popularity summed: roughly how many fans), 'popularity' (mean cell
    popularity: the weights) and 'cells' (cell count)."""
    return {"affinity": {cc: w / pop for cc, (w, pop, n) in sums.items()},
            "mass": {cc: w for cc, (w, pop, n) in sums.items()},
            "popularity": {cc: pop / n for cc, (w, pop, n) in sums.items()},
            "cells": {cc: n for cc, (w, pop, n) in sums.items()}}


def country_profile(cells):
    """profile_from_sums(country_sums(cells)): every per-country view of a fan map, from one reverse-geocoding pass."""
    return profile_from_sums(country_sums(cells))


_PRECOMPUTED = {}  # Qloo entity id -> country_sums, from the precomputed runtime data (preload_profiles)


def preload_profiles(sums_by_entity):
    """Serve these games' fan maps from precomputed country sums instead of reading and geocoding cached heatmaps."""
    _PRECOMPUTED.update(sums_by_entity)
    game_sums.cache_clear()


@lru_cache(maxsize=None)
def game_sums(name, entity_id):
    """country_sums of a game's world fan map, memoised: from the precomputed runtime data when it has the game, else
    from the API response (cached on disk)."""
    if entity_id in _PRECOMPUTED:
        return _PRECOMPUTED[entity_id]
    return country_sums(world_cells(name, entity_id))


def game_profile(name, entity_id):
    """country_profile of a game's world fan map (see game_sums)."""
    return profile_from_sums(game_sums(name, entity_id))
