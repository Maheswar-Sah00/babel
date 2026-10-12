"""Precomputed runtime data (data/runtime/): everything the planner loads at start, built once from the committed
backtest data and the API cache by tools/build_runtime.py, then loaded in about a second (the cache-built
plan.Context takes about 30 s and needs the 1 GB cache).

  baseline.json  the typical language mix, the lift reference (mean S1 per language over the Steam backtest's
                 look-alikes), its per-country version for the map, and the default-map fingerprint
  pool.json      the look-alike pool in pool order: Steam name, release year, header image, SteamSpy tags (votes),
                 and the Qloo check (valid / default map / not in Qloo / unchecked, with the Qloo id)
  fanmaps.json   per Qloo id (the pool's valid games and the backtest's look-alikes): the world fan map summed per
                 country (babel.qloo.country_sums: affinity x popularity, popularity, cells) and S1 per language
  manifest.json  version, build time, SHA-256 of the backtest files it was built from and of each file, counts

The fan maps are stored as the sums babel.qloo.country_profile itself divides, so every score is identical to the
cache-built one. Qloo-derived data stays private like cache/ (git-ignored; docs/DECISIONS.md). Games the build could
not check in Qloo stay 'unchecked' and are checked live when a plan needs them, as before.
"""
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import comps, net, qloo, steam
from . import plan as P

VERSION = 1
DIR = P.ROOT / "data" / "runtime"
FILES = ("baseline.json", "pool.json", "fanmaps.json")
SOURCES = ("backtest/data/truth_reviews.csv", "backtest/data/comps.csv")  # what the baseline is computed from


class Unavailable(Exception):
    """The precomputed data cannot be used (not built, switched off, another version, damaged or out of date)."""


def directory():
    """data/runtime/, or BABEL_RUNTIME_DATA (a folder; 'off' to always build the runtime data from the cache)."""
    value = os.environ.get("BABEL_RUNTIME_DATA", "")
    if value.lower() in ("off", "0", "no"):
        raise Unavailable("switched off (BABEL_RUNTIME_DATA=off)")
    return Path(value) if value else DIR


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _number(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


# ---------------------------------------------------------------- build (tools/build_runtime.py)
def fan_map(name, qloo_id):
    """One game's world fan map as stored: country sums, S1 per target language, and its request id (provenance)."""
    sums = qloo.game_sums(name, qloo_id)
    s1 = P.comp_signal(qloo.profile_from_sums(sums)["affinity"])
    return {"name": name, "request": qloo.heatmap_id(name, qloo_id), "countries": sums,
            "s1": {lang: _number(v) for lang, v in s1.items()}}


def qloo_check(picker, appid):
    """(status, qloo id) of a pool game: from the picker or the cache; ('unchecked', None) if that needs a request
    the build may not make (or one that failed)."""
    if appid in picker.status:
        return picker.status[appid]
    try:
        return picker.resolve(appid)
    except RuntimeError:  # net.Offline, or Qloo failing after its retries
        return "unchecked", None


def build(ctx=None, check_qloo=False, log=print):
    """{file name: content} for every runtime file. Cache only (no network) unless check_qloo: then Qloo may be
    called for pool games never checked (about two requests each; mind the quota). Steam is never called."""
    token = net.allowed_hosts.set({qloo.HOST} if check_qloo else set())
    try:
        ctx = ctx or P.Context()
        prior, (base, n_base), picker = ctx.prior, ctx.base, ctx.picker
        games, fanmaps = [], {}
        for i, (appid, name) in enumerate(picker.names.items(), 1):
            d = steam.appdetails(appid)
            released = steam.release_date(d)
            status, qloo_id = qloo_check(picker, appid)
            games.append({"appid": appid, "name": name, "year": released.year if released else None,
                          "image": d.get("header_image"), "tags": comps.spy_tags(appid),
                          "qloo": {"status": status, "id": qloo_id}})
            if status == "valid":
                fanmaps[qloo_id] = fan_map(name, qloo_id)
            if i % 200 == 0:
                log(f"  pool: {i}/{len(picker.names)} games, {len(fanmaps)} fan maps")
        for r in pd.read_csv(P.BACKTEST_DATA / "comps.csv").drop_duplicates("qloo_id").itertuples():
            if r.qloo_id not in fanmaps:
                fanmaps[r.qloo_id] = fan_map(r.comp_name, r.qloo_id)
        baseline = {
            "typical_mix": {"shares": {lang: float(v) for lang, v in prior.items()},
                            "source": "babel.plan.typical_mix() over backtest/data/truth_reviews.csv"},
            "lift_reference": {"s1": {lang: float(v) for lang, v in base.items()}, "lookalikes": n_base,
                               "source": "babel.plan.lift_base() over backtest/data/comps.csv"},
            "country_reference": ctx.country_reference,
            "default_map": ctx.default_map,
        }
        pool = {"games": games, "candidates": picker.pool_checked}
        return {"baseline.json": baseline, "pool.json": pool, "fanmaps.json": fanmaps}
    finally:
        net.allowed_hosts.reset(token)


def counts(files):
    statuses = pd.Series([g["qloo"]["status"] for g in files["pool.json"]["games"]]).value_counts()
    return {"pool_games": len(files["pool.json"]["games"]), **{str(k): int(v) for k, v in statuses.items()},
            "fan_maps": len(files["fanmaps.json"])}


def save(files, out=None, check_qloo=False):
    """Write the runtime files, then the manifest (last, so a half-written build is never loaded)."""
    out = Path(out or DIR)
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    for name in FILES:
        net.save(out / name, json.dumps(files[name], ensure_ascii=False, separators=(",", ":")))
        meta[name] = {"bytes": (out / name).stat().st_size, "sha256": sha256(out / name)}
    manifest = {
        "version": VERSION, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder": "tools/build_runtime.py", "network": "Qloo, for unchecked pool games" if check_qloo else "none",
        "sources": {src: sha256(P.ROOT / src) for src in SOURCES},
        "pool": {"min_reviews": comps.POOL_MIN_REVIEWS, "size": comps.POOL_SIZE,
                 "released_before": comps.RELEASED_BEFORE.isoformat(), "candidates": files["pool.json"]["candidates"]},
        "counts": counts(files), "files": meta,
    }
    net.save(out / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


# ---------------------------------------------------------------- load
class Precomputed:
    """plan.Context's attributes (prior, base, country_reference, default_map, picker) from the runtime files; the
    fan maps are registered with babel.qloo, so game_profile serves them without reading the API cache."""

    def __init__(self, manifest, files):
        baseline, games = files["baseline.json"], files["pool.json"]["games"]
        self.manifest = manifest
        self.source = f"precomputed data/runtime (built {manifest['built_at'][:10]})"
        self.prior = pd.Series(baseline["typical_mix"]["shares"], dtype=float)
        self.base = (pd.Series(baseline["lift_reference"]["s1"], dtype=float), baseline["lift_reference"]["lookalikes"])
        self.country_reference = baseline["country_reference"]
        self.default_map = baseline["default_map"]
        status = {g["appid"]: (g["qloo"]["status"], g["qloo"]["id"]) for g in games
                  if g["qloo"]["status"] != "unchecked"}
        self.picker = comps.CompPicker.from_tags({g["appid"]: g["name"] for g in games},
                                                 {g["appid"]: g["tags"] for g in games}, self.default_map, status)
        self.picker.pool_checked = files["pool.json"]["candidates"]
        self.picker.cards = {g["appid"]: {"name": g["name"], "year": g["year"], "image": g["image"]} for g in games}
        qloo.preload_profiles({qid: m["countries"] for qid, m in files["fanmaps.json"].items()})


def load(folder=None):
    """The precomputed runtime data, checked: Unavailable if it is missing, from another version, damaged, or built
    from other backtest data or pool settings than the code now uses."""
    folder = Path(folder) if folder else directory()
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Unavailable(f"not built ({folder} has no manifest.json): run python tools/build_runtime.py") from None
    if manifest.get("version") != VERSION:
        raise Unavailable(f"version {manifest.get('version')}, the code reads version {VERSION}: rebuild it")
    for src, digest in manifest["sources"].items():
        if sha256(P.ROOT / src) != digest:
            raise Unavailable(f"built from an older {src}: rebuild it")
    pool = manifest["pool"]
    if (pool["min_reviews"], pool["size"], pool["released_before"]) != (
            comps.POOL_MIN_REVIEWS, comps.POOL_SIZE, comps.RELEASED_BEFORE.isoformat()):
        raise Unavailable("built with other look-alike pool settings: rebuild it")
    files = {}
    for name in FILES:
        path = folder / name
        if not path.exists() or sha256(path) != manifest["files"][name]["sha256"]:
            raise Unavailable(f"{name} is missing or does not match the manifest: rebuild it")
        files[name] = json.loads(path.read_text(encoding="utf-8"))
    return Precomputed(manifest, files)
