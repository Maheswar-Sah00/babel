"""Look-alike suggestions for the Start screen: the comparable games the plan would use, alternatives to swap in, a
search over the look-alike pool, and a check of any game the user picks.

The suggested three are exactly the ones the planner would choose by itself (plan.pick_lookalikes, or describe.discover
for a description / sparse SteamSpy tags), so leaving them unchanged gives the same plan. Alternatives are the other
pool games among the best tag matches that have a real Qloo fan map. Every card says why it is (or is not) usable.
"""
from . import comps, describe, steam
from . import plan as P

SPARSE_TAGS = 3   # same rule as the agent
WINDOW = 9        # tag matches examined for alternatives
SEARCH_LIMIT = 8


def card(appid, name, status, overlap=None, why=None, qloo_id=None, known=None):
    """A comparable-game card: Steam name and header image, Qloo status (usable only with a real fan map). `known`:
    the pool's precomputed {appid: {'name', 'year', 'image'}} (babel/runtime.py), so pool games need no Steam call."""
    if known and appid in known:
        info = known[appid]
    else:
        d = steam.appdetails(appid) if appid else {}
        released = steam.release_date(d) if d else None
        info = {"name": d.get("name"), "year": released.year if released else None, "image": d.get("header_image")}
    return {"appid": appid, "name": info["name"] or name, "status": status, "usable": status == "valid",
            "qloo_id": qloo_id, "overlap": round(overlap, 3) if overlap is not None else None, "why": why,
            "year": info["year"], "image": info["image"]}


def _shared_tags(picker, tags, appid, n=3):
    mine = picker.weights(tags)
    theirs = picker.weights_of.get(appid, {})
    shared = sorted(set(mine) & set(theirs), key=lambda t: -(mine[t] + theirs[t]))[:n]
    return "Shared Steam tags: " + ", ".join(shared) if shared else None


def _from_tags(picker, tags, exclude):
    """(chosen, alternatives, rejected, widened) with the planner's own rule for the chosen three."""
    looks, widened = P.pick_lookalikes(picker, tags, exclude)
    chosen = [x for x in looks if x["status"] == "valid"]
    w = picker.weights(tags)
    window = [a for a in sorted(picker.weights_of, key=lambda a: -comps.overlap(w, picker.weights_of[a]))[:WINDOW]
              if a != exclude and comps.overlap(w, picker.weights_of[a]) > 0]
    taken = {x["appid"] for x in chosen}
    alternatives, rejected = [], [x for x in looks if x["status"] != "valid"]
    for a in window:
        status, qloo_id = picker.resolve(a)
        if a in taken:
            continue
        entry = {"appid": a, "name": picker.names[a], "status": status, "qloo_id": qloo_id,
                 "overlap": comps.overlap(w, picker.weights_of[a])}
        (alternatives if status == "valid" else rejected).append(entry)
    rejected = list({x["appid"]: x for x in rejected}.values())
    return chosen, alternatives, rejected, widened


def suggest(ctx, appid=None, name=None, description=None):
    """Suggestions for one game (a Steam app id or name, or a description). Raises plan.PlanError."""
    picker, notes, discovery, game = ctx.picker, [], None, None
    if appid is not None or name:
        if appid is None:
            appid, approximate = P.find_game(name)
            if approximate:
                notes.append(f"No game on Steam is called exactly '{name}', so Babel used the closest search result. "
                             "Check that it is your game.")
        game = P.game_info(appid)
        if len(game["tags"]) < SPARSE_TAGS and not describe.description_problem(game.get("description")):
            discovery = describe.discover(game["description"], picker)
    else:
        discovery = describe.discover(description, picker)
    if discovery is not None:
        looks = discovery.pop("lookalikes")
        chosen = [x for x in looks if x["status"] == "valid"]
        rejected = [x for x in looks if x["status"] != "valid"]
        alternatives = [{**a, "status": "valid", "qloo_id": None} for a in discovery["alternatives"]]
        tags, widened = discovery["tag_weights"], discovery["widened_search"]
        why = {r["appid"]: r["claude_reason"] for r in discovery["named_by_claude"] if r.get("appid")}
    else:
        tags = game["tags"]
        chosen, alternatives, rejected, widened = (_from_tags(picker, tags, game["appid"]) if tags
                                                   else ([], [], [], False))
        why = {}

    def to_card(x):
        return card(x["appid"], x["name"], x["status"], x.get("overlap"),
                    why.get(x["appid"]) or _shared_tags(picker, tags, x["appid"]), x.get("qloo_id"), picker.cards)
    if not chosen:
        notes.append("Babel found no similar game with Qloo fan data. Add some yourself, or the plan will use what "
                     "English-only indie games usually see.")
    return {
        "game": ({"appid": game["appid"], "name": game["name"], "release_date": game["release_date"],
                  "supported_languages": game["supported"], "top_tags": list(game["tags"])[:8],
                  "image": steam.appdetails(game["appid"]).get("header_image")} if game else
                 {"appid": None, "name": "Your game", "release_date": None, "supported_languages": [],
                  "top_tags": discovery["inferred_tags"][:8], "image": None}),
        "source": "description" if game is None else "store_description" if discovery else "steam_tags",
        "lookalikes": [to_card(x) for x in chosen], "alternatives": [to_card(x) for x in alternatives],
        "rejected": [card(x["appid"], x["name"], x["status"], x.get("overlap"), known=picker.cards)
                     for x in rejected if x.get("appid")],
        "widened_search": widened, "notes": notes,
        "confidence": discovery["confidence"] if discovery else None,
    }


def search(ctx, query, limit=SEARCH_LIMIT):
    """Pool games whose name contains the query (names starting with it first). In memory: no external calls."""
    q = query.casefold().strip()
    picker = ctx.picker
    hits = [a for a, n in picker.names.items() if q in n.casefold()]
    hits.sort(key=lambda a: (not picker.names[a].casefold().startswith(q), picker.names[a].casefold()))
    return [card(a, picker.names[a], picker.status[a][0] if a in picker.status else "unchecked",
                 qloo_id=picker.status[a][1] if a in picker.status else None, known=picker.cards)
            for a in hits[:limit]]


def check(ctx, appid):
    """One game the user picked: its Steam data and whether Qloo has a real fan map for it."""
    look = P.user_lookalike(int(appid), ctx.default_map)
    if look["status"] == "not on Steam":
        raise P.PlanError(f"Steam has no store data for app {appid}.")
    return card(look["appid"], look["name"], look["status"], qloo_id=look["qloo_id"], known=ctx.picker.cards)
