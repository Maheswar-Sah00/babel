"""Precomputed runtime data (babel/runtime.py): synthetic data, temporary folders, no network."""
import json

import pandas as pd
import pytest

from babel import comps, net, qloo, runtime
from babel import plan as P
from babel.languages import GENERIC

JAPAN = [(35.68, 139.69, .9, .8), (34.69, 135.50, .5, .2), (35.18, 136.90, .7, .5), (43.06, 141.35, .2, .1),
         (33.59, 130.40, .6, .4), (38.27, 140.87, .8, .6)]


def cells(points):
    return [{"location": {"latitude": lat, "longitude": lon, "geohash": f"c{i}"},
             "query": {"affinity": a, "popularity": p}} for i, (lat, lon, a, p) in enumerate(points)]


@pytest.fixture(autouse=True)
def clean_preload():
    """Precomputed fan maps are registered globally: start and end every test without any."""
    qloo._PRECOMPUTED.clear()
    qloo.game_sums.cache_clear()
    yield
    qloo._PRECOMPUTED.clear()
    qloo.game_sums.cache_clear()


def files():
    """A tiny but complete set of runtime files, as runtime.build makes them."""
    sums = qloo.country_sums(cells(JAPAN))
    games = [{"appid": 1, "name": "Cozy One", "year": 2019, "image": "https://example.test/1.jpg",
              "tags": {"Cozy": 100, "Farming Sim": 80}, "qloo": {"status": "valid", "id": "Q1"}},
             {"appid": 2, "name": "Gloomy", "year": 2020, "image": None, "tags": {"Horror": 90, "Cozy": 5},
              "qloo": {"status": "default map", "id": "Q2"}},
             {"appid": 3, "name": "Unknown", "year": None, "image": None, "tags": {"Racing": 50},
              "qloo": {"status": "unchecked", "id": None}}]
    return {"baseline.json": {"typical_mix": {"shares": {l: (14 - i) / 105 for i, l in enumerate(GENERIC)}},
                              "lift_reference": {"s1": {l: .5 for l in GENERIC}, "lookalikes": 3},
                              "country_reference": {"countries": {"JP": {"affinity": .4, "lookalikes": 3}},
                                                    "lookalikes": 3},
                              "default_map": "DEFAULT"},
            "pool.json": {"games": games, "candidates": 5},
            "fanmaps.json": {"Q1": {"name": "Cozy One", "request": "heatmap_cozy_one_x", "countries": sums,
                                    "s1": {}}}}


# ---------------------------------------------------------------- cache-only network switch
def test_a_cache_only_build_cannot_reach_the_network(monkeypatch):
    called = []
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: called.append(a))
    token = net.allowed_hosts.set(set())
    try:
        with pytest.raises(net.Offline):
            net.request("https://hackathon.api.qloo.com/search", {})
    finally:
        net.allowed_hosts.reset(token)
    assert called == [] and issubclass(net.Offline, RuntimeError)  # callers already handle RuntimeError


def test_the_switch_also_stops_claude_calls_in_any_thread(monkeypatch, tmp_path):
    """Claude goes through the Anthropic SDK, not net.request: the switch must stop it too, in worker threads as well."""
    import sys
    from babel import llm
    monkeypatch.setattr(llm, "CACHE", tmp_path)  # nothing cached
    monkeypatch.setitem(sys.modules, "anthropic", None)  # importing the SDK would fail loudly: it must not be reached
    token = net.allowed_hosts.set(set())
    try:
        with pytest.raises(net.Offline):
            llm.ask_claude_json("a new prompt", {"type": "object"})
        with pytest.raises(net.Offline):
            llm.ask_claude_many(["one", "two"], {"type": "object"})
    finally:
        net.allowed_hosts.reset(token)


# ---------------------------------------------------------------- the stored sums give the same fan map
def test_stored_country_sums_give_exactly_the_cache_built_profile(monkeypatch):
    sums = qloo.country_sums(cells(JAPAN))
    assert json.loads(json.dumps(sums)) == sums  # exact through JSON
    assert qloo.profile_from_sums(json.loads(json.dumps(sums))) == qloo.country_profile(cells(JAPAN))

    def no_cache(*args):
        raise AssertionError("read the API cache although the fan map was precomputed")
    monkeypatch.setattr(qloo, "world_cells", no_cache)
    qloo.preload_profiles({"Q1": sums})
    assert qloo.game_profile("Any name", "Q1") == qloo.country_profile(cells(JAPAN))


# ---------------------------------------------------------------- save and load
def test_saved_files_load_as_a_context(tmp_path):
    f = files()
    manifest = runtime.save(f, tmp_path)
    assert manifest["counts"] == {"pool_games": 3, "valid": 1, "default map": 1, "unchecked": 1, "fan_maps": 1}
    assert set(manifest["files"]) == set(runtime.FILES) and manifest["network"] == "none"
    ctx = runtime.load(tmp_path)
    assert ctx.prior.equals(pd.Series(f["baseline.json"]["typical_mix"]["shares"]))
    assert ctx.base[0].equals(pd.Series(.5, index=GENERIC)) and ctx.base[1] == 3
    assert ctx.country_reference == f["baseline.json"]["country_reference"] and ctx.default_map == "DEFAULT"
    expected = comps.CompPicker.from_tags({1: "Cozy One", 2: "Gloomy", 3: "Unknown"},
                                          {g["appid"]: g["tags"] for g in f["pool.json"]["games"]}, "DEFAULT")
    assert ctx.picker.names == expected.names and ctx.picker.weights_of == expected.weights_of
    assert ctx.picker.status == {1: ("valid", "Q1"), 2: ("default map", "Q2")}  # 'unchecked' is checked live
    assert ctx.picker.pool_checked == 5 and ctx.picker.cards[1]["image"] == "https://example.test/1.jpg"
    assert qloo.game_profile("Cozy One", "Q1")["cells"] == {"JP": 6}
    assert "precomputed" in ctx.source


@pytest.mark.parametrize("damage, reason", [
    (lambda d: (d / "manifest.json").unlink(), "not built"),
    (lambda d: _manifest(d, version=99), "version 99"),
    (lambda d: _manifest(d, sources={"backtest/data/comps.csv": "0" * 64}), "older backtest/data/comps.csv"),
    (lambda d: _manifest(d, pool={"min_reviews": 1, "size": 1, "released_before": "2000-01-01", "candidates": 1}),
     "pool settings"),
    (lambda d: (d / "pool.json").write_text("{}", encoding="utf-8"), "pool.json is missing or does not match"),
])
def test_missing_stale_or_damaged_data_is_refused(tmp_path, damage, reason):
    runtime.save(files(), tmp_path)
    damage(tmp_path)
    with pytest.raises(runtime.Unavailable, match=reason):
        runtime.load(tmp_path)


def _manifest(folder, **changes):
    path = folder / "manifest.json"
    path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), **changes}), encoding="utf-8")


def test_pool_cards_need_no_steam_request(monkeypatch, tmp_path):
    from babel import steam, suggest

    def no_steam(appid):
        raise AssertionError("asked Steam for a pool game the runtime data already has")
    runtime.save(files(), tmp_path)
    ctx = runtime.load(tmp_path)
    monkeypatch.setattr(steam, "appdetails", no_steam)
    card = suggest.card(1, "Cozy One", "valid", .3, None, "Q1", ctx.picker.cards)
    assert (card["name"], card["year"], card["image"], card["usable"]) == (
        "Cozy One", 2019, "https://example.test/1.jpg", True)


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("BABEL_RUNTIME_DATA", "off")
    with pytest.raises(runtime.Unavailable, match="switched off"):
        runtime.load()


def test_the_planner_falls_back_to_the_cache_when_it_is_unusable(monkeypatch, tmp_path):
    monkeypatch.setenv("BABEL_RUNTIME_DATA", str(tmp_path))  # an empty folder: not built
    monkeypatch.setattr(P, "_CONTEXT", None)
    ctx = P.context()
    assert isinstance(ctx, P.Context) and ctx.source == "the API cache"
    runtime.save(files(), tmp_path)
    monkeypatch.setattr(P, "_CONTEXT", None)
    assert isinstance(P.context(), runtime.Precomputed)
