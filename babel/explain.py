"""Plain-English explanation of a plan, grounded only in its evidence.

evidence_index() flattens a plan (and its market notes) into items with stable IDs ('lang:russian',
'lookalike:<appid>', 'formula:lift', 'caveat:1', ...) and display-formatted values. Claude writes a summary and points
from that index, citing IDs. Code keeps a point only if it cites at least one ID, every cited ID exists, and every
number in it appears in the cited items, so Claude can quote numbers but never create or change them. If too little
survives, or Claude is unavailable, a template explanation written by code from the same index is used instead.
"""
import json
import re

from . import llm, qloo
from .languages import LABEL

NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
MIN_POINTS = 2
GROUP_LABEL = {"translate_game": "translate the game", "store_page_only": "store page only", "skip": "skip for now",
               "already_supported": "already supported"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary", "points"], "properties": {
    "summary": {"type": "string"},
    "points": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["text", "evidence"],
        "properties": {"text": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}}}}}


def pct(x):
    return f"{x:.1%}"


def usd(x):
    return f"${x:,.0f}"


def _names(codes):
    return [LABEL[c] for c in codes]


def evidence_index(p, notes=None):
    """{evidence ID: item} for a plan and its market notes, with values formatted the way they may be quoted."""
    g, c, cov = p["groups"], p["costs"], p["estimated_coverage"]
    idx = {
        "plan": {"status": p["status"], "budget": usd(c["budget"]), "word_count": f"{p['inputs']['word_count']:,}",
                 **{GROUP_LABEL[k]: _names(v) for k, v in g.items()}},
        "costs": {"translate the game": usd(c["translate_game"]), "store pages": usd(c["store_page_only"]),
                  "total": usd(c["total"]), "unspent": usd(c["unspent"]), "note": "Cost estimates, not quotes."},
        "coverage": {"full translations": pct(cov["translate_game"]), "store pages": pct(cov["store_page_only"]),
                     "meaning": cov["meaning"]},
        "game": {"name": p["game"]["name"], "steam_appid": p["game"]["appid"], "source": p["game"]["source"],
                 "already supported": _names(p["game"]["supported_languages"]), "top tags": p["game"]["top_tags"]},
    }
    for x in p["lookalikes"]["used"]:
        idx[f"lookalike:{x['appid']}"] = {"name": x["name"], "qloo_fan_map": qloo.heatmap_id(x["name"], x["qloo_id"]),
                                          "tag_overlap": f"{x['overlap']:.2f}" if x.get("overlap") else None}
    for x in p["lookalikes"]["rejected"]:
        idx[f"rejected:{x['appid']}"] = {"name": x["name"], "status": x["status"]}
    look = p["lookalikes"]
    idx["evidence_level"] = {"level": look["evidence_level"], "widened search": look["widened_search"],
                             "look-alikes used": len(look["used"])}
    for x in p["languages"]:
        idx[f"lang:{x['code']}"] = {
            "language": x["language"], "rank": x["rank"], "plan": GROUP_LABEL[x["group"]],
            "estimated share": pct(x["estimated_share"]), "baseline share": pct(x["baseline_share"]),
            "qloo lift": f"{x['qloo_lift']:.2f}", "full translation cost": usd(x["cost_full"]),
            "store page cost": usd(x["cost_store_page"]), "reason": x["reason"]}
    for k, v in p["formulas"].items():
        idx[f"formula:{k}"] = v
    tr = p["track_record"]
    idx["track_record"] = {
        "steam reviews": f"{tr['steam_reviews']['test_games']} small indie games: Babel top-3 coverage "
                         f"{pct(tr['steam_reviews']['babel_top3_coverage'])} vs typical mix "
                         f"{pct(tr['steam_reviews']['typical_mix_top3_coverage'])}, p = "
                         f"{tr['steam_reviews']['sign_test_p']} ({tr['steam_reviews']['verdict']})",
        "wikipedia pageviews": f"{tr['wikipedia_pageviews']['test_games']} notable games: Babel "
                               f"{pct(tr['wikipedia_pageviews']['babel_top3_coverage'])} vs typical mix "
                               f"{pct(tr['wikipedia_pageviews']['typical_mix_top3_coverage'])}, p "
                               f"{tr['wikipedia_pageviews']['sign_test_p']} ({tr['wikipedia_pageviews']['verdict']})",
        "source": tr["source"]}
    for i, caveat in enumerate(p["uncertainty"]["caveats"], 1):
        idx[f"caveat:{i}"] = caveat
    if p["uncertainty"]["lookalikes_disagree_on"]:
        idx["disagreement"] = {"look-alikes disagree on": _names(p["uncertainty"]["lookalikes_disagree_on"])}
    if p.get("discovery"):
        d = p["discovery"]
        idx["discovery"] = {"inferred tags": d["inferred_tags"], "confidence": d["confidence"]["level"],
                            "reasons": d["confidence"]["reasons"],
                            "source": "Tags inferred from a description by Claude"}
    if notes:
        a = notes["audience"]
        idx["audience"] = ({"age skew": {x["band"]: f"{x['skew']:+.2f}" for x in a["age"]},
                            "gender skew": {k: f"{v:+.2f}" for k, v in a["gender"].items()}, "meaning": a["meaning"]}
                           if a["status"] == "ok" else {"unavailable": a["reason"]})
        for m in notes["markets"]:
            idx[f"market:{m['language']}"] = {
                "country": m["country_name"], "why this country": m["country_choice"]["reason"],
                **{f"{d} popular there that these fans also love":
                   [i["name"] for i in r["items"]] if r["status"] == "ok" else f"unavailable: {r['reason']}"
                   for d, r in m["also_loves"].items()},
                "qloo requests": [q for r in m["also_loves"].values() for q in r["requests"]]}
    return idx


def _norm(token):
    return token.replace("$", "").replace(",", "")


def numbers(text):
    """Normalised numbers in a text: '$7,366' -> '7366', '20.2%' -> '20.2%'."""
    return {_norm(t) for t in NUMBER.findall(text)}


def unsupported(text, items):
    """Numbers in `text` that appear in none of `items`. Plain integers up to 20 ('top 3', '5th') are allowed;
    money and percentages never are."""
    allowed = numbers(json.dumps(items, ensure_ascii=False))
    return sorted({_norm(t) for t in NUMBER.findall(text) if _norm(t) not in allowed
                   and not (t.isdigit() and int(t) <= 20)})


def check(raw, idx):
    """(summary or None, kept points, dropped points with reasons) from Claude's raw answer."""
    if not isinstance(raw, dict) or not raw:
        return None, [], [{"text": "", "reason": "Claude gave no usable answer."}]
    kept, dropped = [], []
    for pt in raw.get("points") if isinstance(raw.get("points"), list) else []:
        text = pt.get("text") if isinstance(pt, dict) and isinstance(pt.get("text"), str) else ""
        cited = [e for e in pt.get("evidence", []) if isinstance(e, str)] if isinstance(pt, dict) else []
        if not text.strip():
            continue
        unknown = [e for e in cited if e not in idx]
        extra = unsupported(text, [idx[e] for e in cited if e in idx])
        reason = ("cites no evidence" if not cited else f"cites unknown evidence {unknown}" if unknown else
                  f"numbers not in the cited evidence: {extra}" if extra else None)
        point = {"text": text.strip(), "evidence": cited}
        (dropped if reason else kept).append({**point, "reason": reason} if reason else point)
    summary = raw.get("summary") if isinstance(raw.get("summary"), str) and raw.get("summary").strip() else None
    if summary and unsupported(summary, idx):
        dropped.append({"text": summary, "evidence": [], "reason": f"summary numbers not in the evidence: "
                                                                   f"{unsupported(summary, idx)}"})
        summary = None
    return summary, kept, dropped


def prompt(idx):
    return ("You explain a translation plan to an indie game developer in plain English. Use ONLY the evidence "
            "below; every item has an ID. Write a one-sentence summary and 3 to 6 short points; each point lists the "
            "IDs of the evidence it relies on. Quote numbers exactly as they appear in the cited items (for example "
            "'20.2%' or '$3,508'): never compute, round or change a number, never add a language or a recommendation "
            "the plan does not make, and say that shares are estimates, not sales. If the evidence is weak or "
            "missing (caveats, discovery, rejected look-alikes, unavailable market data), say so plainly.\n"
            "Evidence: " + json.dumps(idx, ensure_ascii=False))


def template(p, idx):
    """An explanation written by code from the evidence index (used when Claude's is unavailable or fails checks)."""
    g = p["groups"]
    full, store = g["translate_game"], g["store_page_only"]
    summary = (f"Translate {', '.join(_names(full))} in full ({idx['costs']['translate the game']})" if full else
               "No full translation fits the budget") + (
        f" and translate only the store page for {len(store)} more languages ({idx['costs']['store pages']})"
        if store else "") + "."
    points = [{"text": f"{idx[f'lang:{l}']['language']} ranks {idx[f'lang:{l}']['rank']}: an estimated "
                       f"{idx[f'lang:{l}']['estimated share']} of non-English demand (baseline "
                       f"{idx[f'lang:{l}']['baseline share']} x Qloo lift {idx[f'lang:{l}']['qloo lift']}); "
                       f"full translation {idx[f'lang:{l}']['full translation cost']}.",
               "evidence": [f"lang:{l}", "formula:estimated_share", "formula:cost_full"]} for l in full]
    looks = [k for k in idx if k.startswith("lookalike:")]
    points.append({"text": ("Qloo fan maps of " + ", ".join(idx[k]["name"] for k in looks)
                            + " adjust the typical language mix of English-only indie games.") if looks else
                   "No look-alike game has Qloo fan data, so the plan is the typical language mix of English-only "
                   "indie games.", "evidence": looks or ["evidence_level", "formula:lift"]})
    points.append({"text": f"Full translations cover an estimated {idx['coverage']['full translations']} of "
                           "non-English demand; this is an estimate, not sales.", "evidence": ["coverage", "caveat:1"]})
    points.append({"text": "In the backtest, Qloo's improvement on small English-only indie games was small and not "
                           "significant; it was significant on notable games.",
                   "evidence": ["track_record", "caveat:3"]})
    return summary, points


def explain(p, idx):
    """The explanation: Claude's, if it passes the checks, else the template. Never raises."""
    error = None
    try:
        raw = llm.ask_claude_json(prompt(idx), SCHEMA)
    except Exception as exc:  # no key, network, API error: report it and fall back
        raw, error = None, f"Claude unavailable ({type(exc).__name__})"
    summary, kept, dropped = check(raw, idx)
    if error:
        dropped = []  # nothing came back to drop; the error itself is reported
    if error is None and summary and len(kept) >= MIN_POINTS:
        return {"kind": "llm_text", "status": "ok", "reason": None, "summary": summary, "points": kept,
                "dropped": dropped, "source": f"Claude ({llm.CLAUDE_MODEL}), from the evidence index; every number "
                                              "checked against the cited evidence"}
    reason = error or ("Claude gave no usable answer" if not isinstance(raw, dict) or not raw else
                       "Claude's summary did not pass the checks" if not summary else
                       f"only {len(kept)} of Claude's points passed the checks")
    summary, points = template(p, idx)
    return {"kind": "template", "status": "fallback", "reason": reason, "summary": summary, "points": points,
            "dropped": dropped, "source": "Written by code from the evidence index"}
