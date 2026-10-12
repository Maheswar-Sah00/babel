"""Look-alike ("comp") games: well-known Steam games released before a cutoff, matched by IDF-weighted tag overlap,
kept only when Qloo has a real (non-default) world fan map for them."""
import math
from collections import Counter
from datetime import date

from . import qloo, steam

POOL_MIN_REVIEWS, POOL_SIZE, RELEASED_BEFORE = 5000, 1000, date(2023, 1, 1)


def spy_tags(appid):
    """SteamSpy user tags {tag: votes}, most-voted first (SteamSpy sends [] when a game has none)."""
    tags = steam.spy_app(appid).get("tags")
    return dict(sorted(tags.items(), key=lambda kv: -kv[1])) if isinstance(tags, dict) else {}


def qloo_status(name, default_map):
    """(status, qloo_id) for a game name: 'valid', 'default map', 'no heatmap', 'not in Qloo', or
    'Qloo search failed (HTTP n)' / 'Qloo heatmap failed (HTTP n)' when Qloo answered with an error."""
    hit, status = qloo.find_game(name)
    if status != 200:
        return f"Qloo search failed (HTTP {status})", None
    if not hit:
        return "not in Qloo", None
    status, body = qloo.heatmap(name, hit["entity_id"], **{"filter.location": qloo.WORLD})
    if status != 200:
        return f"Qloo heatmap failed (HTTP {status})", hit["entity_id"]
    cells = qloo.cells_of(body)
    return ("no heatmap" if not cells else "default map" if qloo.fingerprint(cells) == default_map
            else "valid"), hit["entity_id"]


def overlap(a, b):
    """Weighted Jaccard: sum of min weights over sum of max weights."""
    keys = a.keys() | b.keys()
    den = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys) / den if den else 0.0


class CompPicker:
    def __init__(self, released_before=RELEASED_BEFORE, pool_size=POOL_SIZE, min_reviews=POOL_MIN_REVIEWS, log=print):
        src = {**steam.get(steam.SPY, {"request": "all", "page": 0}), **steam.spy_tag("Indie")}
        pool = sorted((int(a) for a, g in src.items() if g.get("positive", 0) + g.get("negative", 0) >= min_reviews),
                      key=lambda a: -(src[str(a)]["positive"] + src[str(a)]["negative"]))[:pool_size]
        self.pool_checked = len(pool)
        self.names = {}
        for i, appid in enumerate(pool, 1):
            d = steam.appdetails(appid)
            if d.get("type") == "game" and steam.released_between(d, end=released_before):
                self.names[appid] = d["name"]
            if i % 200 == 0:
                log(f"  pool: checked {i}/{len(pool)}, kept {len(self.names)}")
        self._index(self.names, {a: spy_tags(a) for a in self.names}, qloo.default_fingerprint())

    @classmethod
    def from_tags(cls, names, pool_tags, default_map, status=None):
        """A picker over a given pool ({appid: name}, {appid: {tag: votes}}) with no Steam calls (tests, saved data);
        `status` pre-fills Qloo validity ({appid: (status, qloo_id)})."""
        picker = cls.__new__(cls)
        picker.pool_checked = len(names)
        picker._index(dict(names), pool_tags, default_map)
        picker.status.update(status or {})
        return picker

    def _index(self, names, pool_tags, default_map):
        self.names = names
        doc_freq = Counter(t for tags in pool_tags.values() for t in tags)
        self.idf = {t: math.log(len(pool_tags) / n) for t, n in doc_freq.items()}
        self.max_idf = math.log(len(pool_tags))
        self.weights_of = {a: self.weights(t) for a, t in pool_tags.items()}
        self.default_map = default_map
        self.status = {}  # pool appid -> (status, qloo_id)
        self.cards = {}  # pool appid -> {'name', 'year', 'image'} when precomputed (babel/runtime.py): no Steam call

    def weights(self, tags):
        """Share of the game's tag votes, times how rare the tag is in the pool (so 'Indie' counts for little)."""
        total = sum(tags.values()) or 1
        return {t: v / total * self.idf.get(t, self.max_idf) for t, v in tags.items()}

    def resolve(self, appid):
        if appid not in self.status:
            self.status[appid] = qloo_status(self.names[appid], self.default_map)
        return self.status[appid]

    def pick(self, tags, top=6, keep=3, min_overlap=None):
        """Up to `keep` valid comps from the `top` best tag matches, best first. With `min_overlap`, candidates must
        overlap more than it (the planner passes 0, so a game shares at least one tag; the backtest builders did not,
        which gave games without SteamSpy tags the same arbitrary comps)."""
        w, out = self.weights(tags), []
        for comp in sorted(self.weights_of, key=lambda a: -overlap(w, self.weights_of[a]))[:top]:
            if min_overlap is not None and overlap(w, self.weights_of[comp]) <= min_overlap:
                break
            status, qloo_id = self.resolve(comp)
            if status == "valid":
                out.append({"comp_appid": comp, "comp_name": self.names[comp], "qloo_id": qloo_id,
                            "overlap_score": round(overlap(w, self.weights_of[comp]), 4)})
                if len(out) == keep:
                    break
        return out
