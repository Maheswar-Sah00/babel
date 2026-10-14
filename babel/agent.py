"""Babel's agent: runs the planning workflow step by step and reports every step as a typed event (a live trace).

Event (stable; the API streams them as Server-Sent Events):
  {"v": 1, "seq": n, "type": EVENT_TYPES, "step": STEPS, "status": STATUSES, "message": plain English, "data": {...}}
`message` is written for a game developer (no jargon); method notes for the curious go in data["detail"].
The agent plans, acts (Steam, Qloo, Claude, and the deterministic engine in babel.plan), reflects on what came back
and recovers where it can:
  - sparse SteamSpy tags      -> tags inferred from the store description (Claude suggests, code verifies);
  - < 2 look-alikes with data -> the 12 best tag matches, then the typical language mix, disclosed;
  - default maps, failed Qloo requests -> reported per game and never used; after a request fails all its retries,
    later Qloo steps are skipped and the plan says so (nothing is invented to fill the gap);
  - a market with no Qloo data -> the next recommended market;
builds the Plan screen's data from the fan maps already read (babel.explore: the world map, Babel vs the generic list),
then verifies the result and explains it from the evidence (babel.explain: Claude cites evidence IDs; code checks
every number). All scores, costs and budget decisions come from babel.plan.

  python -m babel.agent --appid 3146520 --words 30000 --budget 10000
  python -m babel.agent --description "A cozy farming game..." --words 40000 --budget 12000
  python -m babel.agent --examples              (add --jsonl for the raw events)
"""
import argparse
import json
import sys

from . import describe, explain, explore, markets, net, qloo
from . import plan as P
from .languages import LABEL, POP

VERSION = 1
EVENT_TYPES = ("plan", "act", "reflect", "verify", "explain", "error", "done")
STEPS = ("goal", "game", "tags", "lookalikes", "fan_maps", "score", "optimize", "markets", "explain", "verify",
         "result")
STATUSES = ("info", "started", "ok", "warning", "needs_input", "failed")
SPARSE_TAGS = 3
WHY_REJECTED = {"default map": "Qloo has no real fan data for it", "not in Qloo": "Qloo doesn't know this game",
                "no heatmap": "Qloo has no fan map for it"}


class Trace:
    """Events in order; each one is also passed to `sink` (an SSE stream, the console) as it happens."""

    def __init__(self, sink=None):
        self.events, self.sink, self.step = [], sink, "goal"

    def emit(self, type_, step, status, message, /, **data):
        assert type_ in EVENT_TYPES and step in STEPS and status in STATUSES, (type_, step, status)
        self.step = step
        event = {"v": VERSION, "seq": len(self.events) + 1, "type": type_, "step": step, "status": status,
                 "message": message, "data": data}
        self.events.append(event)
        if self.sink:
            self.sink(event)
        return event

    def retry(self, host, reason, wait, attempt):
        """Called by babel.net for every failed attempt, so retries show up in the trace."""
        last = attempt + 1 == net.attempts()
        self.emit("reflect", self.step, "warning",
                  f"{host} answered {reason} (attempt {attempt + 1} of {net.attempts()}); "
                  + ("giving up." if last else f"retrying in {wait:.0f} s."), host=host, reason=reason)


def _names(codes):
    """'Russian', 'Russian and Spanish', 'Russian, Spanish and German', or 'none'."""
    names = [LABEL[c] for c in codes]
    return " and ".join(filter(None, [", ".join(names[:-1]), names[-1]])) if names else "none"


def _n(count, word, plural=None):
    """'1 game', '3 games'."""
    return f"{count} {word if count == 1 else plural or word + 's'}"


def _groups(g, costs=None):
    """The budget groups in words: 'translate the game into Russian ($7,366); ...; skip Thai for now'."""
    cost = (lambda k: f" (${costs[k]:,.0f})") if costs else (lambda k: "")
    parts = [f"translate the game into {_names(g['translate_game'])}{cost('translate_game')}"
             if g["translate_game"] else "no full translation",
             f"translate the store page only for {_n(len(g['store_page_only']), 'language')}{cost('store_page_only')}"
             if g["store_page_only"] else None,
             f"skip {_names(g['skip'])} for now" if g["skip"] else None]
    return "; ".join(p for p in parts if p)


class _Run:
    def __init__(self, trace, ctx, rates, min_share):
        self.t, self.ctx, self.rates, self.min_share = trace, ctx, rates, min_share
        self.notes, self.discovery, self.widened, self.qloo_ok, self.reported = [], None, False, True, set()

    # ------------------------------------------------------------ steps
    def go(self, word_count, budget, appid, name, lookalikes, tags, description, with_markets, with_explanation):
        t = self.t
        try:
            P.check_inputs(word_count, budget, self.min_share)
            (self.rates or P.Rates()).check()
            if description is not None and describe.description_problem(description):
                raise P.PlanError(describe.description_problem(description))
            if appid is None and not name and not lookalikes and not tags and not description:
                raise P.PlanError("Give a Steam app ID, a game name, a description, similar games or tags.")
        except P.PlanError as e:
            t.emit("error", "goal", "failed", str(e))
            return self.finish("failed", "No plan: please check what you entered.")
        todo = (["find your game", "find well-known games like it", "see where their fans are",
                 "rank 14 languages", "fit your budget"] + ["add notes on your top markets"] * with_markets
                + ["explain the plan"] * with_explanation + ["double-check it"])
        t.emit("plan", "goal", "info",
               f"Making a translation plan for {int(word_count):,} words and a ${budget:,.0f} budget. Babel will "
               + ", ".join(todo[:-1]) + f" and {todo[-1]}.",
               steps=["game", "lookalikes", "fan_maps", "score", "optimize"] + ["markets"] * with_markets
               + ["explain"] * with_explanation + ["verify"])
        self.ctx = self.ctx or P.context()
        game = self.resolve_game(appid, name, tags, description, lookalikes)
        if game is None:
            return self.finish("failed", "No plan: the game could not be found.")
        looks = self.find_lookalikes(game, lookalikes, tags, description)
        self.read_fan_maps(looks)
        geo = self.map_data(looks)
        p = self.build(game, looks, word_count, budget)
        notes = self.market_notes(p) if with_markets else None
        idx = explain.evidence_index(p, notes)
        exp = self.explain(p, idx) if with_explanation else None
        verified = self.verify(p, exp, idx, geo)
        g = p["groups"]
        result = {"plan": p, "market_notes": notes, "explanation": exp, "evidence_index": idx,
                  "explore": {"map": geo, "versus_generic": explore.versus_generic(p, self.ctx.prior),
                              "costs": explore.cost_breakdown(p)}}
        status = "ok" if verified and not any(e["type"] == "error" for e in t.events) else "partial"
        return self.finish(status, f"Plan ready: {_groups(g)}.", result)

    def finish(self, status, message, result=None):
        self.t.emit("done", "result", {"ok": "ok", "partial": "warning"}.get(status, "failed"), message,
                    status=status, result=result)
        return {"status": status, "result": result, "events": self.t.events}

    def resolve_game(self, appid, name, tags, description, lookalikes):
        t = self.t
        if appid is None and not name:
            game = {"appid": None, "name": "Your game", "release_date": None, "supported": [], "tags": {},
                    "source": "input", "description": ""}
            source = ("your tags" if tags else "the similar games you picked" if lookalikes else "your description")
            t.emit("act", "game", "ok", f"No Steam page, so Babel plans from {source}.")
        else:
            t.emit("act", "game", "started", "Looking up your game on Steam.")
            try:
                if appid is None:
                    appid, approximate = P.find_game(name)
                    if approximate:
                        self.notes.append(f"No exact Steam match for '{name}': using the top search result.")
                        t.emit("reflect", "game", "warning", f"No game on Steam is called exactly '{name}', so Babel "
                                                             "used the closest search result.")
                game = P.game_info(appid)
            except P.PlanError as e:
                t.emit("error", "game", "failed", str(e))
                return None
            except RuntimeError as e:
                t.emit("error", "game", "failed", f"Steam didn't answer after {net.attempts()} attempts, so Babel "
                                                  "couldn't look up the game. Try again in a minute.", detail=str(e))
                return None
            have = (f"It's already translated into {_names(game['supported'])}." if game["supported"] else
                    "It isn't translated into any of the 14 languages Babel plans for yet.")
            t.emit("act", "game", "ok", f"Found {game['name']} on Steam, with {_n(len(game['tags']), 'tag')}. {have}",
                   appid=game["appid"], name=game["name"], top_tags=list(game["tags"])[:8],
                   supported=game["supported"], detail=f"Steam app {game['appid']}; tags from SteamSpy.")
        if tags:
            game["tags"] = dict(tags) if isinstance(tags, dict) else {x: 1 for x in tags}
            t.emit("act", "tags", "ok", f"Using your {_n(len(game['tags']), 'tag')}: {', '.join(game['tags'])}.")
        if description and (game["appid"] is not None or tags or lookalikes):
            self.notes.append("Description not used: the plan uses the Steam page, tags or look-alikes you gave.")
        return game

    def find_lookalikes(self, game, lookalikes, tags, description):
        t = self.t
        if lookalikes:
            t.emit("act", "lookalikes", "started", "Checking whether Qloo has fan data for the "
                                                   f"{_n(len(lookalikes), 'game')} you picked.")
            looks = []
            for appid in dict.fromkeys(int(a) for a in lookalikes):
                unchecked = {"appid": appid, "name": str(appid), "qloo_id": None, "overlap": None,
                             "status": "not checked: a request failed"}
                looks.append(self.guard("lookalikes", lambda: P.user_lookalike(appid, self.ctx.default_map), unchecked)
                             if self.qloo_ok else unchecked)
            self.notes.append("Look-alikes chosen by you.")
        elif description and game["appid"] is None and not tags:
            looks = self.discover(game, description, "your description", as_game=True)
        elif game["source"] == "steam" and not tags and len(game["tags"]) < SPARSE_TAGS:
            t.emit("reflect", "tags", "warning", f"Steam lists only {_n(len(game['tags']), 'tag')} for this game: too "
                                                 "few to find similar games reliably.", detail="Tags from SteamSpy.")
            if not describe.description_problem(game.get("description")):
                self.notes.append(f"SteamSpy had only {len(game['tags'])} tag(s), so tags were inferred from the store "
                                  "description by an LLM.")
                looks = self.discover(game, game["description"], "the store description")
            else:
                t.emit("reflect", "tags", "needs_input", "There is no store description to read tags from either. "
                                                         "Add tags, or pick similar games yourself.")
                looks = self.search(game) if game["tags"] else []
        elif game["tags"]:
            looks = self.search(game)
        else:
            looks = []
            self.notes.append("No Steam tags found, so no look-alike games: add tags or pick look-alikes.")
        self.report(looks)
        self.assess(looks)
        return looks

    def discover(self, game, text, source, as_game=False):
        t = self.t
        t.emit("act", "tags", "started", f"An LLM is reading {source} and suggesting Steam tags and similar games; "
                                         "Babel checks each one on Steam and Qloo.")
        try:
            d = describe.discover(text, self.ctx.picker)
        except RuntimeError as e:
            self.failed("tags", e)
            return []
        except Exception as e:  # the LLM unavailable (no key, API error): report it, never invent tags
            self.notes.append(f"The LLM could not read {source}, so no tags or look-alikes were inferred.")
            t.emit("error", "tags", "failed", f"The LLM couldn't read {source}, so Babel has no tags or similar games "
                                              "to work from.", detail=type(e).__name__)
            return []
        looks, self.discovery, self.widened = d.pop("lookalikes"), d, d["widened_search"]
        game["tags"] = d["tag_weights"]
        if as_game:
            game.update(name="Your game (from a description)", source="description")
        named, shown = d["named_by_claude"], ", ".join(d["inferred_tags"][:6])
        more = ", ..." if len(d["inferred_tags"]) > 6 else ""
        t.emit("act", "tags", "ok", f"The LLM suggested {_n(len(d['inferred_tags']), 'tag')} ({shown}{more}) and named "
                                    f"{_n(len(named), 'similar game')}: {sum(r['in_pool'] for r in named)} of them are "
                                    "among the well-known games Babel compares with, "
                                    f"{sum(r['status'] == 'valid' for r in named)} with real Qloo fan data.",
               inferred_tags=d["inferred_tags"], unknown_tags=d["unknown_tags"],
               named=[{k: r[k] for k in ("claude_name", "status", "appid")} for r in named])
        if d["problems"]:
            t.emit("reflect", "tags", "warning", "Part of the LLM's answer couldn't be used: " + " ".join(d["problems"]))
        conf = d["confidence"]
        if d["needs_user_choice"]:
            hint = ", ".join(a["name"] for a in d["alternatives"][:4])
            t.emit("reflect", "lookalikes", "needs_input", "Babel isn't sure these games are like yours: "
                   + " ".join(conf["reasons"]) + " Pick similar games yourself"
                   + (f"; for example {hint}." if hint else "."), alternatives=d["alternatives"])
        elif conf["reasons"]:
            t.emit("reflect", "lookalikes", "warning", f"Check these games (Babel is only fairly sure they are like "
                   f"yours; confidence: {conf['level']}). " + " ".join(conf["reasons"]))
        self.notes += P.discovery_notes(d)
        return looks

    def search(self, game):
        t, picker = self.t, self.ctx.picker
        t.emit("act", "lookalikes", "started", f"Comparing your game's Steam tags with {len(picker.weights_of):,} "
                                               "well-known games (rare tags count more), then checking the 6 closest "
                                               "in Qloo.", detail="IDF-weighted tag overlap (weighted Jaccard); the "
                                                                  "6 best tag matches are checked, as in the backtest.")

        def look():
            looks = P.examine_lookalikes(picker, game["tags"], game["appid"], 6)
            if P.n_valid(looks) >= 2:
                return looks
            self.report(looks)
            n = P.n_valid(looks)
            t.emit("reflect", "lookalikes", "warning", ("None" if n == 0 else f"Only {n}") + " of these games has Qloo "
                   "fan data (Babel needs at least 2), so it is also checking the next closest matches (12 in all). "
                   "Babel's track record doesn't cover this wider search.",
                   detail="Widened to the 12 best tag matches: a fallback the backtest did not cover.")
            wider = P.examine_lookalikes(picker, game["tags"], game["appid"], 12)
            self.widened = P.n_valid(wider) > P.n_valid(looks)
            return wider
        return self.guard("lookalikes", look, [])

    def report(self, looks):
        t = self.t
        valid = [x for x in looks if x["status"] == "valid"]
        t.emit("act", "lookalikes", "ok", "Games like yours with real Qloo fan data: "
               + (", ".join(x["name"] for x in valid) or "none") + ".",
               used=[{k: x.get(k) for k in ("appid", "name", "qloo_id", "overlap")} for x in valid])
        for x in looks:
            if x["status"] == "valid" or x["appid"] in self.reported:
                continue
            self.reported.add(x["appid"])
            if "failed" in x["status"] or "unreachable" in x["status"]:
                t.emit("error", "lookalikes", "failed", f"{x['name']}: the check with Qloo failed, so it isn't used.",
                       appid=x["appid"], status=x["status"], detail=x["status"])
            else:
                why = WHY_REJECTED.get(x["status"], x["status"])
                t.emit("reflect", "lookalikes", "warning", f"{x['name']}: {why}, so it isn't used.",
                       appid=x["appid"], status=x["status"])

    def assess(self, looks):
        n = P.n_valid(looks)
        if n == 0:
            self.t.emit("reflect", "lookalikes", "needs_input", "None of the games like yours has Qloo fan data, so "
                        "the plan uses what English-only indie games usually see, with no adjustment from Qloo. To "
                        "add Qloo's fan data, pick similar games yourself.",
                        detail="Fallback: the typical language mix of English-only indie games (Qloo lift 1).")
        elif n < 3:
            self.t.emit("reflect", "lookalikes", "warning", f"Only {_n(n, 'game')} like yours "
                        f"{'has' if n == 1 else 'have'} Qloo fan data (Babel normally uses 3), so the ranking rests "
                        "on less evidence than usual.")

    def read_fan_maps(self, looks):
        for x in [x for x in looks if x["status"] == "valid"]:
            if not self.qloo_ok:
                x["status"] = "not read: Qloo unreachable in this run"
                self.t.emit("reflect", "fan_maps", "warning", f"{x['name']}: skipped, because Qloo couldn't be "
                                                              "reached earlier in this run; not used.")
                continue
            affinity = self.guard("fan_maps", lambda: P.comp_affinity(x["name"], x["qloo_id"]), None)
            if affinity is None:
                x["status"] = "Qloo heatmap failed (unreachable)"
                continue
            x["affinity"] = affinity
            covered = sorted(c for c in affinity if c in POP)
            self.t.emit("act", "fan_maps", "ok", f"{x['name']}: read Qloo's fan map. It has data for {len(covered)} "
                                                 f"of the {len(POP)} countries Babel uses for its 14 languages.",
                        request=qloo.heatmap_id(x["name"], x["qloo_id"]), countries=covered,
                        detail="Qloo world heatmap (affinity per map cell), cached.")

    def map_data(self, looks):
        """The world map's data from the fan maps read above (no new requests); None, reported, if it fails."""
        try:
            geo = explore.map_data(looks, self.ctx.prior, self.ctx.base[0],
                                   getattr(self.ctx, "country_reference", None), P.ALPHA)
        except Exception as e:  # display data only: say so; the plan itself does not depend on it
            self.t.emit("error", "fan_maps", "failed", "The world map couldn't be built from this data; the plan "
                                                       "itself is unaffected.", detail=type(e).__name__)
            return None
        if geo["status"] == "ok":
            n = sum(x["usable"] for x in geo["lookalikes"])
            self.t.emit("act", "fan_maps", "ok", f"World map: Qloo has fan data for {geo['countries_with_score']} "
                                                 f"countries, from {_n(n, 'game')} like yours.",
                        countries=geo["countries_with_score"],
                        detail=f"Each country's score is the popularity-weighted mean affinity of its map cells (at "
                               f"least {qloo.MIN_CELLS} cells per country), averaged over the fan maps.")
        return geo

    def build(self, game, looks, word_count, budget):
        t = self.t
        base, n_base = self.ctx.base
        self.args = (game, looks, int(word_count), budget, self.ctx.prior, base, self.rates, self.min_share, P.ALPHA,
                     self.widened, list(self.notes), n_base, self.discovery)
        p = P.build_plan(*self.args)
        top = p["languages"][:5]
        t.emit("act", "score", "ok", "Ranked the 14 languages: Babel starts from what English-only indie games usually "
                                     "see and adjusts it with Qloo's fan data. Top 5, as estimated shares of your "
                                     "likely non-English players: "
               + ", ".join(f"{x['language']} {x['estimated_share']:.1%}" for x in top) + ". Estimates, not sales.",
               top=[{k: x[k] for k in ("code", "estimated_share", "baseline_share", "qloo_lift")} for x in top],
               formula=p["formulas"]["estimated_share"],
               detail="The backtested model: typical language mix × Qloo lift of the look-alikes (alpha 1).")
        if p["uncertainty"]["lookalikes_disagree_on"]:
            t.emit("reflect", "score", "warning", "For " + _names(p["uncertainty"]["lookalikes_disagree_on"])
                   + ", the games like yours point different ways (more fans than usual for some, fewer for others), "
                     "so those estimates are less certain.")
        g, c = p["groups"], p["costs"]
        t.emit("act", "optimize", "ok", f"Picked the best mix that fits your ${c['budget']:,.0f} budget: "
                                        f"{_groups(g, c)}. Costs are estimates, not quotes.", groups=g, costs=c,
               detail="Exact budget optimiser (full translations first, then store pages), from babel.plan.")
        if p["status"] != "ok":
            t.emit("reflect", "optimize", "warning", p["messages"][-1], plan_status=p["status"])
        return p

    def market_notes(self, p):
        t = self.t
        t.emit("act", "markets", "started", "Reading who these fans are and, for your top markets, the films and music "
                                            "they also like there (Qloo data about many fans together, not about any "
                                            "one player).",
               detail="Qloo demographics of the look-alikes; per market, two Qloo steps: the country's favourites by "
                      "location, then re-ranked by the look-alikes' fans.")
        if not self.qloo_ok:
            t.emit("reflect", "markets", "warning", "Market notes skipped: Qloo couldn't be reached earlier in this "
                                                    "run.")
            return None
        return self.guard("markets", lambda: self._market_notes(p), None)

    def _market_notes(self, p):
        t = self.t
        used, ids, masses = markets.lookalike_signals(p)
        aud = markets.audience(ids)
        if aud["status"] == "ok":
            top = max(aud["age"], key=lambda a: a["skew"])
            t.emit("act", "markets", "ok", "Who these fans are: compared with Qloo's average audience, the age group "
                                           f"most over-represented is {top['band']}.",
                   request=aud["source"]["request"],
                   detail=f"Qloo demographics of the look-alikes' fans: age band {top['band']} skew {top['skew']:+.2f}.")
        else:
            t.emit("reflect", "markets", "warning", f"No audience data from Qloo: {aud['reason']}")
        entries, skipped = [], []
        for lang in markets.candidates(p):
            if len(entries) == markets.MAX_MARKETS:
                break
            e = markets.market_entry(lang, p, ids, masses)
            if ids and not markets.has_data(e):
                skipped.append(e)
                t.emit("reflect", "markets", "warning", f"No Qloo market data for {e['country_name']}, so Babel tries "
                                                        "the next market.", language=lang,
                       detail="; ".join(r["reason"] for r in e["also_loves"].values()))
                continue
            entries.append(e)
            if ids:
                t.emit("act", "markets", "ok", f"{e['language_name']}, in {e['country_name']}. Popular there with fans "
                                               "of games like yours: " + "; ".join(
                    f"{d}: {', '.join(i['name'] for i in r['items']) if r['status'] == 'ok' else 'no data'}"
                    for d, r in e["also_loves"].items()) + ".", language=lang, country=e["country"],
                       requests=[q for r in e["also_loves"].values() for q in r["requests"]])
                for d, r in e["also_loves"].items():
                    if r["status"] != "ok":
                        t.emit("reflect", "markets", "warning", f"{e['country_name']}: no {d} data from Qloo "
                                                                f"({r['reason']})")
        if not ids:
            t.emit("reflect", "markets", "warning", "No game like yours has Qloo fan data, so there are no notes on "
                                                    "who the fans are or what else they like; the markets are listed "
                                                    "with that reason.")
        return markets.assemble(aud, entries + skipped[:markets.MAX_MARKETS - len(entries)], used)

    def explain(self, p, idx):
        t = self.t
        t.emit("act", "explain", "started", "Writing a plain-words explanation of the plan, using only the plan's "
                                            f"own facts ({len(idx)} of them). Babel checks every number in it.",
               detail="Each point must cite evidence IDs; every number is checked against the cited items.")
        exp = explain.explain(p, idx)
        for d in exp["dropped"]:
            t.emit("verify", "explain", "warning", f"Left out of the explanation: {d['reason'].rstrip('.')}.",
                   text=d["text"])
        if exp["status"] != "ok":
            t.emit("error" if "unavailable" in exp["reason"] else "reflect", "explain",
                   "failed" if "unavailable" in exp["reason"] else "warning",
                   f"The first explanation wasn't usable ({exp['reason']}), so Babel wrote a simpler one from the same "
                   "facts.")
        t.emit("explain", "explain", "ok", exp["summary"], kind=exp["kind"], points=exp["points"],
               source=exp["source"])
        return exp

    def verify(self, p, exp, idx, geo=None):
        c = p["costs"]
        checks = [
            (c["total"] <= c["budget"] + 1e-6, f"Stays within your budget: ${c['total']:,.0f} of ${c['budget']:,.0f}.",
             None),
            (sorted(l for ls in p["groups"].values() for l in ls) == sorted(P.LANGS),
             "Each language is in exactly one group.", None),
            (P.build_plan(*self.args) == p, "Worked the plan out again from the same inputs: same result.", None),
            (True, "Babel's code worked out every share, cost and budget choice. An LLM only suggested tags and similar "
                   "games and wrote text.", "Every score, cost and budget decision came from babel.plan."),
        ]
        if exp:
            grounded = all(pt["evidence"] and all(e in idx for e in pt["evidence"])
                           and not explain.unsupported(pt["text"], [idx[e] for e in pt["evidence"]])
                           for pt in exp["points"])
            checks.append((grounded, f"Explanation: all {len(exp['points'])} points rest on the plan's facts and "
                                     f"use only numbers found there; {len(exp['dropped'])} left out by these checks.",
                           f"Explanation kind {exp['kind']}: every point cites existing evidence IDs and quotes only "
                           "numbers found in them."))
        if geo is not None:
            rows = {x["code"]: x for x in p["languages"]}
            same = all(geo["languages"][l]["lift"] == rows[l]["qloo_lift"]
                       and geo["languages"][l]["estimated_share"] == rows[l]["estimated_share"] for l in P.LANGS)
            checks.append((same, "World map: worked out again from the same fan maps, every language's Qloo "
                                 "adjustment and estimated share match the plan.",
                           "World map data: Qloo lift and estimated share per language, recomputed."))
        errors = sum(e["type"] == "error" for e in self.t.events)
        checks.append((True, f"{errors} failed request(s) or error(s), each shown above." if errors else
                       "No failed requests.", None))
        for ok, message, detail in checks:
            self.t.emit("verify", "verify", "ok" if ok else "failed", message, **({"detail": detail} if detail else {}))
        return all(ok for ok, _, _ in checks)

    def failed(self, step, e):
        """A request failed all its retries: report it, stop calling Qloo in this run, and say so in the plan."""
        self.qloo_ok = False
        self.notes.append("A request failed after retries, so part of this plan has no Qloo evidence; see the trace.")
        self.t.emit("error", step, "failed", f"A request failed after {net.attempts()} attempts, so Babel carries on "
                                             "without that data and says so in the plan.", detail=str(e))

    def guard(self, step, fn, fallback):
        """Run a step; return `fallback` (never invented data) if a request fails all its retries."""
        try:
            return fn()
        except RuntimeError as e:
            self.failed(step, e)
            return fallback


def run(word_count, budget, appid=None, name=None, lookalikes=None, tags=None, description=None, rates=None,
        min_share=P.MIN_SHARE, ctx=None, with_markets=True, with_explanation=True, sink=None):
    """Run the agent. Returns {'status': ok / partial / failed, 'result', 'events'}; bad input and failed requests
    become error events instead of exceptions."""
    trace = Trace(sink)
    token = net.on_retry.set(trace.retry)
    try:
        return _Run(trace, ctx, rates, min_share).go(word_count, budget, appid, name, lookalikes, tags, description,
                                                     with_markets, with_explanation)
    finally:
        net.on_retry.reset(token)


# ---------------------------------------------------------------- CLI
def render_event(e):
    return f"{e['seq']:>3}  {e['type']:<8}{e['step']:<11}{e['status']:<12}{e['message']}"


def render_explanation(exp):
    by = "Claude, checked against the evidence" if exp["kind"] == "llm_text" else "written by code"
    out = [f"Explanation ({by}):", f"  {exp['summary']}"]
    out += [f"  - {pt['text']}  [{', '.join(pt['evidence'])}]" for pt in exp["points"]]
    return "\n".join(out)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Babel agent: a costed localization plan with a live trace.")
    ap.add_argument("--appid", type=int)
    ap.add_argument("--name")
    ap.add_argument("--lookalikes", help="comma-separated Steam appids of look-alike games")
    ap.add_argument("--tags", help="comma-separated Steam tags")
    ap.add_argument("--description", help="free-text description, for a game without a store page")
    ap.add_argument("--words", type=int)
    ap.add_argument("--budget", type=float)
    ap.add_argument("--examples", action="store_true", help="the three demo games")
    ap.add_argument("--no-markets", action="store_true")
    ap.add_argument("--no-explain", action="store_true")
    ap.add_argument("--jsonl", action="store_true", help="print the raw events as JSON lines (as streamed)")
    a = ap.parse_args(argv)
    runs = ([{"appid": i, "word_count": w, "budget": b} for i, w, b in P.EXAMPLES] if a.examples else
            [{"appid": a.appid, "name": a.name, "word_count": a.words, "budget": a.budget, "description": a.description,
              "lookalikes": [int(x) for x in a.lookalikes.split(",")] if a.lookalikes else None,
              "tags": [x.strip() for x in a.tags.split(",")] if a.tags else None}])
    status = 0
    for i, kwargs in enumerate(runs):
        if i and not a.jsonl:
            print()
        sink = (lambda e: print(json.dumps(e, ensure_ascii=False))) if a.jsonl else (lambda e: print(render_event(e)))
        out = run(**kwargs, with_markets=not a.no_markets, with_explanation=not a.no_explain, sink=sink)
        exp = (out["result"] or {}).get("explanation")
        if exp and not a.jsonl:
            print(render_explanation(exp))
        status = max(status, {"ok": 0, "partial": 1, "failed": 2}[out["status"]])
    return status


if __name__ == "__main__":
    sys.exit(main())
