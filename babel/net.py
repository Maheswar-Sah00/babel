"""Throttled HTTP shared by every Babel data source, with per-host counters for reports."""
import contextvars
import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import requests

GAP = {"hackathon.api.qloo.com": 0.5, "store.steampowered.com": 1.1, "steamspy.com": 1.1,
       "api.groq.com": 2.0, "query.wikidata.org": 1.0, "wikimedia.org": 1.0}  # min seconds between calls
ATTEMPTS = 6
calls = Counter()       # network requests made, by host
cache_hits = Counter()  # responses served from cache, by host
on_retry = contextvars.ContextVar("on_retry", default=None)  # f(host, reason, wait, attempt): live traces
# Retry policy for the current context. Scripts keep the patient default (6 attempts, waits up to 8 min); the web API
# sets a short one per request so a plan never hangs for minutes.
policy = contextvars.ContextVar("policy", default={"attempts": ATTEMPTS, "max_wait": None, "timeout": 180})
# Hosts that may be requested: None means any. A cache-only build sets an empty set (or just the hosts it may call), so
# anything not already cached raises Offline instead of reaching the network.
allowed_hosts = contextvars.ContextVar("allowed_hosts", default=None)
_last = {}


class Offline(RuntimeError):
    """A request that is not in the cache while network use is switched off for its host."""
_lock = threading.Lock()


def attempts():
    return policy.get()["attempts"]


def check_allowed(host):
    """Raise Offline when network use is switched off for this host (also used by the Claude SDK calls in llm)."""
    if allowed_hosts.get() is not None and host not in allowed_hosts.get():
        raise Offline(f"{host} is not cached for this request, and network use is off")


def _retrying(host, reason, wait, attempt):
    """Report a failed attempt (console and live trace), then wait before the next one (not after the last)."""
    last = attempt + 1 == attempts()
    wait = min(wait, policy.get()["max_wait"]) if policy.get()["max_wait"] is not None else wait
    print(f"  {host} {reason}, " + ("giving up" if last else f"retrying in {wait:.0f}s"), file=sys.stderr,
          flush=True)  # stderr: stdout may be a protocol channel (the MCP stdio transport)
    if on_retry.get():
        on_retry.get()(host, reason, 0 if last else wait, attempt)
    if not last:
        time.sleep(wait)


def request(url, params=None, headers=None, json_body=None):
    """GET (or POST when json_body is given) with per-host throttling.

    Retries network errors, 429, 5xx and Steam's rate-limit `null` body with backoff (see `policy`).

    Returns (status, body). Anything returned is final (2xx or a deterministic 4xx), so callers may cache it.
    Raises RuntimeError when every attempt failed.
    """
    host, timeout = url.split("/")[2], policy.get()["timeout"]
    check_allowed(host)
    for attempt in range(attempts()):  # default backoff 15s .. 8min, about 16 minutes in total
        with _lock:
            pause = max(0.0, GAP[host] - (time.time() - _last.get(host, 0.0)))
            _last[host] = time.time() + pause
        time.sleep(pause)
        calls[host] += 1
        try:
            r = (requests.post(url, json=json_body, headers=headers, timeout=timeout) if json_body is not None
                 else requests.get(url, params=params, headers=headers, timeout=timeout))
        except (requests.ConnectionError, requests.Timeout) as exc:
            _retrying(host, type(exc).__name__, 15 * 2 ** attempt, attempt)
            continue
        try:
            body = r.json()
        except ValueError:
            body = {"text": r.text[:2000]}
        if r.status_code == 429 or r.status_code >= 500 or (r.status_code == 200 and body is None):
            _retrying(host, f"HTTP {r.status_code}", float(r.headers.get("Retry-After") or 15 * 2 ** attempt), attempt)
            continue
        return r.status_code, body
    raise RuntimeError(f"{url} kept failing after {attempts()} attempts")


def save(path, text):
    """Write a cache file atomically (temp file + rename), so concurrent requests never see half a file."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
