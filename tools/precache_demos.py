"""Run the browser's demo games through the real API exactly as the browser does (POST /lookalikes, then POST /plan
with the default 30,000 words and $10,000 budget, look-alikes unchanged), so everything they need is in the cache.

  python tools/precache_demos.py --offline   # check only: no request at all; lists what would still be fetched
  python tools/precache_demos.py             # fetch what is missing (normally a handful of Qloo and Claude calls)

--offline exits 1 if any demo would need a live call or does not come back 'ok': the check that the demos run from the
cache alone. The description demo's text is read from web/index.html, so it always matches the button.
"""
import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402

from babel import api, net  # noqa: E402

WORDS, BUDGET = 30_000, 10_000  # the browser's defaults (web/index.html)


def demos():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    description = re.search(r'data-demo-description="([^"]+)"', html).group(1)
    return [("WEBFISHING", {"appid": 3146520}), ("Dawnsbury Days", {"appid": 2693730}),
            ("Never Second in Rome", {"appid": 3169580}), ("A cozy farming idea", {"description": description})]


def go_offline(blocked):
    """Refuse every request (recording its host) and every Claude call; nothing reaches the network."""
    import anthropic

    def refuse(url, *args, **kwargs):
        blocked[url.split("/")[2]] += 1
        raise net.Offline(f"{url.split('/')[2]} not cached")

    def no_claude(*args, **kwargs):
        blocked["api.anthropic.com"] += 1
        raise RuntimeError("Claude refused in --offline mode")
    net.request = refuse
    anthropic.Anthropic = no_claude


def run(client, name, game):
    started, before = time.perf_counter(), Counter(net.calls)
    looks = client.post("/lookalikes", json=game)
    plan = client.post("/plan?stream=false", json={**game, "word_count": WORDS, "budget": BUDGET})
    body = plan.json() if plan.status_code == 200 else {}
    errors = [e["message"] for e in body.get("events", []) if e["type"] == "error"]
    return {"demo": name, "lookalikes": looks.status_code, "plan": plan.status_code, "status": body.get("status"),
            "errors": errors, "calls": dict(Counter(net.calls) - before), "seconds": time.perf_counter() - started}


def main():
    ap = argparse.ArgumentParser(description="Pre-cache (or check) the browser's demo games.")
    ap.add_argument("--offline", action="store_true", help="make no request; report what would be fetched")
    a = ap.parse_args()
    blocked = Counter()
    if a.offline:
        go_offline(blocked)
    with TestClient(api.create_app(api.Settings(warmup=True, plan_rate=(100, 60), lookup_rate=(100, 60)))) as client:
        state = client.app.state.babel
        if not state.ready.wait(300):
            print(f"Not ready: {state.data_status}")
            return 1
        print(f"Runtime data: {state.data_source}")
        results = []
        for name, game in demos():
            seen = Counter(blocked)
            r = run(client, name, game)
            r["blocked"] = dict(Counter(blocked) - seen)
            results.append(r)
            live = r["blocked"] if a.offline else r["calls"]
            print(f"{name:<22} lookalikes {r['lookalikes']}  plan {r['plan']} {r['status']:<8} "
                  f"{'would fetch' if a.offline else 'fetched'}: {live or 'nothing'}  ({r['seconds']:.1f} s)")
            for message in r["errors"]:
                print(f"    error: {message[:160]}")
    ok = all(r["status"] == "ok" and not (r["blocked"] if a.offline else {}) for r in results)
    print("All demos run from the cache alone." if ok and a.offline else
          "Done." if not a.offline else "Some demos still need live calls (run without --offline to fetch them).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
