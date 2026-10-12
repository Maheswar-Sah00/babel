"""Cached LLM calls (Groq, JSON mode): the 'AI alone' competitor and, later, description -> tags."""
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from . import net

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "llm"
CACHE.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / ".env")
URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"


def ask_json(prompt, model=MODEL):
    """One chat completion in JSON mode, cached by request body. Returns the parsed JSON, or {} if it isn't JSON."""
    body = {"model": model, "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    cached = CACHE / f"{hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]}.json"
    if cached.exists():
        net.cache_hits[URL.split("/")[2]] += 1
        resp = json.loads(cached.read_text(encoding="utf-8"))
    else:
        status, resp = net.request(URL, headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                                   json_body=body)
        resp = resp if status == 200 else {"_status": status, "_body": resp}
        net.save(cached, json.dumps(resp, ensure_ascii=False))
    try:
        return json.loads(resp["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        return {}


CLAUDE_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000


def ask_claude_json(prompt, schema, model=CLAUDE_MODEL, effort="medium", max_tokens=MAX_TOKENS):
    """One Claude call whose answer must match `schema`, cached by request. Returns the parsed JSON, or {}.
    max_tokens (thinking + answer) is part of the cache key only when it is not the default, so older cache entries
    keep their keys."""
    spec = {"model": model, "effort": effort, "schema": schema, "prompt": prompt}
    if max_tokens != MAX_TOKENS:
        spec["max_tokens"] = max_tokens
    key = json.dumps(spec, sort_keys=True)
    cached = CACHE / f"claude_{hashlib.md5(key.encode()).hexdigest()[:12]}.json"
    if cached.exists():
        net.cache_hits["api.anthropic.com"] += 1
        resp = json.loads(cached.read_text(encoding="utf-8"))
    else:
        net.check_allowed("api.anthropic.com")  # the SDK bypasses net.request, so the cache-only switch is checked here
        import anthropic  # reads ANTHROPIC_API_KEY (loaded from .env above); retries 429/5xx itself
        net.calls["api.anthropic.com"] += 1
        msg = anthropic.Anthropic().beta.messages.create(
            model=model, max_tokens=max_tokens,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",  # re-run refused requests server-side
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}])
        resp = msg.model_dump(mode="json")
        net.save(cached, json.dumps(resp, ensure_ascii=False))
    if resp.get("stop_reason") == "refusal":
        return {}
    try:
        return json.loads(next(b["text"] for b in resp.get("content", []) if b.get("type") == "text"))
    except (StopIteration, ValueError):
        return {}


def ask_claude_many(prompts, schema, workers=8, **kw):
    """ask_claude_json for many prompts in parallel (results in input order). Each call runs in a copy of the
    caller's context, so net's cache-only switch and retry policy apply in the worker threads too."""
    import contextvars
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(contextvars.copy_context().run, ask_claude_json, p, schema, **kw) for p in prompts]
        return [f.result() for f in futures]
