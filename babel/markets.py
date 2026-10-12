"""Market notes for a plan: who the look-alikes' fans are, and what local films and music they also love.

Every item says what kind of evidence it is (KINDS) and where it came from:
  - audience: Qloo urn:demographics for the look-alike games together (aggregate skew vs the average Qloo audience);
  - per recommended market: the country of the language area where the look-alikes have the most Qloo fan mass;
    its Steam user share (external: Steam survey); Babel's estimated share (estimate);
  - "also loves", in two steps so results stay tied to the country: (1) what is popular there, from the location
    signal alone (it can include international titles), (2) that pool re-ranked by the look-alikes' fans
    (filter.results.entities + signal.interests.entities, no location: a location signal there silently drops
    entities). Only entities from the country's pool are kept;
  - an optional note per market written by Claude from that evidence only (llm_text), checked by code.
Every Qloo request is cached on disk (babel.qloo.fetch); its id is the cache file name, so each result can be traced.
"""
import json
import re

from . import llm, qloo
from .languages import COUNTRIES, COUNTRY_NAME, LABEL, POP, STEAM_SHARE

DOMAINS = {"films": "urn:entity:movie", "music": "urn:entity:artist"}
MAX_MARKETS, POOL_TAKE, SHOW = 3, 30, 4
AGES = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]
KINDS = {"qloo_measured": "Measured by Qloo", "external": "External observation", "estimate": "Babel estimate",
         "llm_text": "Written by Claude from the Qloo evidence above (check before use)"}
CAVEATS = [
    "Qloo data describes the aggregate taste of fans of similar games, never an individual player.",
    "'Also loves' lists are titles popular in a country (local or international) re-ranked by fans of the look-alike "
    "games: cultural context for marketing, not proof of what any player in that country likes.",
    "Audience and taste data is never used to infer ethnicity or other protected traits, and none of it feeds the "
    "language scores.",
]
NOTE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["notes"], "properties": {"notes": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["country", "note"],
                               "properties": {"country": {"type": "string"}, "note": {"type": "string"}}}}}}
PERSONAL = re.compile(r"\b(ethnic\w*|race|racial|religio\w*|gender|female|male|women|men|girls?|boys?|age[sd]?|"
                      r"older|younger)\b", re.I)


def _unavailable(reason, kind="qloo_measured", **extra):
    return {"kind": kind, "status": "unavailable", "reason": reason, **extra}


def audience(qloo_ids):
    """Age and gender skew of fans of these games together, vs the average Qloo audience (aggregate)."""
    source = {"api": "Qloo /v2/insights filter.type=urn:demographics", "request": None}
    if not qloo_ids:
        return _unavailable("No look-alike games with Qloo data, so there is no audience to describe.", source=source)
    params = {"filter.type": "urn:demographics", "signal.interests.entities": ",".join(sorted(qloo_ids))}
    source["request"] = qloo.request_id("demographics", "/v2/insights", params)
    status, body = qloo.fetch("demographics", "/v2/insights", params)
    if status != 200:
        return _unavailable(f"Qloo answered HTTP {status}.", source=source)
    query = ((body.get("results") or {}).get("demographics") or [{}])[0].get("query") or {}
    age, gender = query.get("age") or {}, query.get("gender") or {}
    if not age and not gender:
        return _unavailable("Qloo has no audience data for these games.", source=source)
    return {"kind": "qloo_measured", "status": "ok", "reason": None, "source": source,
            "age": [{"band": a.replace("_", " "), "skew": round(float(age[a]), 2)} for a in AGES if a in age],
            "gender": {g: round(float(v), 2) for g, v in sorted(gender.items())},
            "meaning": "How fans of the look-alike games differ from the average Qloo audience (positive = more than "
                       "average). Aggregate data about groups; not used in the language scores."}


def market_country(lang, masses):
    """(country, {'kind', 'reason'}): the country of the language area where the look-alikes have the most Qloo fan
    mass; the most populous one without fan data."""
    countries = COUNTRIES[lang]
    if len(countries) == 1:
        return countries[0], {"kind": "external", "reason": "The language's main country."}
    total = {c: sum(m.get(c, 0.0) for m in masses) for c in countries}
    if any(v > 0 for v in total.values()):
        return max(countries, key=lambda c: (total[c], POP[c])), {
            "kind": "qloo_measured", "reason": "Most Qloo fan mass for the look-alike games in this language area."}
    return max(countries, key=POP.get), {
        "kind": "external", "reason": "Most populous country of this language area (no Qloo fan mass data)."}


def local_pool(country, domain):
    """Step 1: what is popular in the country in a domain, from the location signal alone.
    Returns ({id: name}, request id, HTTP status)."""
    params = {"filter.type": DOMAINS[domain], "signal.location.query": country, "take": POOL_TAKE}
    name = f"local_{qloo.slug(country)}_{DOMAINS[domain].split(':')[-1]}"
    status, body = qloo.fetch(name, "/v2/insights", params)
    entities = (body.get("results") or {}).get("entities", []) if status == 200 else []
    return {e["entity_id"]: e["name"] for e in entities}, qloo.request_id(name, "/v2/insights", params), status


def also_loved(country, domain, qloo_ids):
    """Step 2: the country's pool re-ranked by fans of the look-alike games; only entities from the pool are kept."""
    out = {"kind": "qloo_measured", "status": "unavailable", "reason": None, "items": [], "requests": [],
           "meaning": f"{domain.capitalize()} popular in {country}, ranked by how much fans of the look-alike games "
                      "like them (aggregate taste)."}
    if not qloo_ids:
        out["reason"] = f"No look-alike games with Qloo data to rank what is popular in {country} by."
        return out
    pool, request, status = local_pool(country, domain)
    out["requests"].append(request)
    if not pool:
        out["reason"] = f"Qloo returned no {domain} popular in {country}" + (
            f" (HTTP {status})." if status != 200 else ".")
        return out
    params = {"filter.type": DOMAINS[domain], "filter.results.entities": ",".join(pool),
              "signal.interests.entities": ",".join(sorted(qloo_ids)), "take": POOL_TAKE}
    name = f"fans_{qloo.slug(country)}_{DOMAINS[domain].split(':')[-1]}"
    status, body = qloo.fetch(name, "/v2/insights", params)
    out["requests"].append(qloo.request_id(name, "/v2/insights", params))
    ranked = [e for e in ((body.get("results") or {}).get("entities", []) if status == 200 else [])
              if e.get("entity_id") in pool]
    if not ranked:
        out["reason"] = (f"Qloo answered HTTP {status}." if status != 200 else
                         f"Qloo ranked none of the {domain} popular in {country} for these fans.")
        return out
    out.update(status="ok", items=[{"name": pool[e["entity_id"]], "qloo_id": e["entity_id"]} for e in ranked[:SHOW]],
               local_pool_size=len(pool), ranked=len(ranked))
    return out


def candidates(p):
    """The plan's recommended languages (full translations, then store pages, in rank order); the top-ranked
    languages when the plan recommends none."""
    picked = p["groups"]["translate_game"] + p["groups"]["store_page_only"]
    return picked or [x["code"] for x in p["languages"] if x["group"] == "skip"]


def lookalike_signals(p):
    """(look-alikes with Qloo ids, their ids, their per-country fan mass) from a plan's evidence object."""
    used = [x for x in p["lookalikes"]["used"] if x.get("qloo_id")]
    return used, [x["qloo_id"] for x in used], [qloo.game_profile(x["name"], x["qloo_id"])["mass"] for x in used]


def market_entry(lang, p, ids, masses):
    """One market's notes: its country, the plan's estimate, the Steam survey share and the Qloo 'also loves'."""
    row = next(x for x in p["languages"] if x["code"] == lang)
    cc, choice = market_country(lang, masses)
    country = COUNTRY_NAME[cc]
    return {
        "language": lang, "language_name": LABEL[lang], "group": row["group"],
        "in_plan": row["group"] in ("translate_game", "store_page_only"),
        "country": cc, "country_name": country, "country_choice": choice,
        "estimated_share": {"kind": "estimate", "value": row["estimated_share"],
                            "source": "Babel plan: typical language mix x Qloo lift (estimate, not sales)"},
        "steam_users": {"kind": "external", "value": round(STEAM_SHARE[lang] / 100, 4),
                        "source": "Steam Hardware & Software Survey, Sep 2026: share of Steam users by language"},
        "also_loves": {d: also_loved(country, d, ids) for d in DOMAINS},
        "note": _unavailable("Notes were not requested.", kind="llm_text")}


def has_data(entry):
    return any(r["status"] == "ok" for r in entry["also_loves"].values())


def assemble(audience_, entries, used):
    """The market notes object from its parts (JSON-ready)."""
    return {"audience": audience_, "markets": entries, "lookalikes": [x["name"] for x in used],
            "kinds": KINDS, "caveats": CAVEATS,
            "method": "Two Qloo steps per market and domain: what is popular in the country (location signal only), "
                      "then that pool re-ranked by fans of the look-alike games (no location signal); only entities "
                      "from the country's pool are kept."}


def market_notes(p, explain=True):
    """Market notes for a plan's evidence object (see the module docstring): the first MAX_MARKETS candidates."""
    used, ids, masses = lookalike_signals(p)
    entries = [market_entry(lang, p, ids, masses) for lang in candidates(p)[:MAX_MARKETS]]
    if explain:
        for m, note in zip(entries, explain_markets(entries)):
            m["note"] = note
    return assemble(audience(ids), entries, used)


# ---------------------------------------------------------------- notes written by Claude, checked by code
def note_prompt(evidence):
    return ("You write short market notes for an indie game developer deciding where to translate their game. "
            "Use ONLY the evidence below: for each country, films and music popular there (local or international) "
            "that fans of similar games also love, measured by Qloo. For each country, write one or two plain "
            "sentences on how these touchpoints could inform the game's store page or marketing there. Rules: "
            "titles may be repeated exactly as given, but add no other numbers; do not mention age, gender, "
            "ethnicity, religion or any personal trait; speak of 'fans of similar games in <country>', never of "
            "individual players; add no facts that are not in the evidence; use the country names exactly as given."
            "\nEvidence: " + json.dumps(evidence, ensure_ascii=False))


def explain_markets(markets):
    """One note per market, written by Claude from that market's Qloo evidence and checked by code."""
    evidence = {m["country_name"]: {d: [i["name"] for i in m["also_loves"][d]["items"]] for d in DOMAINS}
                for m in markets}
    evidence = {c: e for c, e in evidence.items() if any(e.values())}
    raw = (llm.ask_claude_json(note_prompt([{"country": c, **e} for c, e in evidence.items()]), NOTE_SCHEMA)
           if evidence else {})
    names = {c: [n for d in DOMAINS for n in e[d]] for c, e in evidence.items()}
    return check_notes(raw, [m["country_name"] for m in markets], names)


def check_notes(raw, countries, evidence):
    """Claude's notes per country, in order. evidence: {country: [names Claude was given]}. A note is kept only if
    its country had evidence and, outside those names, it has no numbers and no personal traits; else a reason."""
    source = (f"Claude ({llm.CLAUDE_MODEL}), from the Qloo evidence for this market; may add general knowledge "
              "(e.g. a genre) that is not in the evidence: check before use")
    written = {}
    for item in raw.get("notes", []) if isinstance(raw, dict) and isinstance(raw.get("notes"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("note"), str) and item.get("country") in evidence:
            written.setdefault(item["country"], item["note"].strip())
    out = []
    for c in countries:
        text = written.get(c)
        bare = text or ""
        for name in sorted(evidence.get(c, []), key=len, reverse=True):
            bare = bare.replace(name, " ")  # titles like '25 km/h' or 'Little Women' are evidence, not claims
        problem = ("No Qloo evidence for this market, so no note." if c not in evidence else
                   "Claude wrote no note for this market." if not text else
                   "Dropped: the note contained numbers." if re.search(r"\d", bare) else
                   "Dropped: the note mentioned a personal trait." if PERSONAL.search(bare) else
                   "Dropped: the note was too long." if len(text) > 700 else None)
        out.append({"kind": "llm_text", "status": "ok", "reason": None, "text": text, "source": source}
                   if problem is None else _unavailable(problem, kind="llm_text", source=source))
    return out


def render(notes):
    """Market notes as readable text, each line labelled with its kind of evidence."""
    a = notes["audience"]
    out = ["", f"Market notes (fans of {', '.join(notes['lookalikes']) or 'no look-alikes'}):"]
    if a["status"] == "ok":
        out.append("  [Qloo] Audience vs the average: " + ", ".join(f"{x['band']} {x['skew']:+.2f}" for x in a["age"])
                   + "; " + ", ".join(f"{g} {v:+.2f}" for g, v in a["gender"].items()))
    else:
        out.append(f"  [Qloo] Audience: unavailable. {a['reason']}")
    for m in notes["markets"]:
        choice = m["country_choice"]
        out.append(f"  {m['language_name']} -> {m['country_name']} "
                   f"[{'Qloo' if choice['kind'] == 'qloo_measured' else 'external'}: {choice['reason']}]")
        out.append(f"    [estimate] Estimated share of non-English demand {m['estimated_share']['value']:.1%}; "
                   f"[Steam survey] {m['steam_users']['value']:.1%} of Steam users use this language")
        for d, res in m["also_loves"].items():
            out.append(f"    [Qloo] {d.capitalize()} popular in {m['country_name']} that these fans also love: "
                       + (", ".join(i["name"] for i in res["items"]) if res["status"] == "ok"
                          else f"unavailable. {res['reason']}"))
        note = m["note"]
        if note["status"] == "ok":
            out.append(f"    [AI note by Claude, from the evidence above; check before use] {note['text']}")
        elif note["reason"] != "Notes were not requested.":
            out.append(f"    [AI note] {note['reason']}")
    out += [f"  Note: {c}" for c in notes["caveats"][:2]]
    return "\n".join(out)
