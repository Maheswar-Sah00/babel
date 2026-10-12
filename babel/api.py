"""Babel's web API (FastAPI).

  POST /plan              run the agent: its events as Server-Sent Events, then the final plan
                          (?stream=false: one JSON object instead)
  GET  /plans/{plan_id}   a finished plan from the in-process cache
  POST /fit-budget        re-fit a plan to a new budget with the engine's own optimizer (the Plan screen's slider)
  POST /assistant         the in-app assistant: a grounded answer about Babel or the open plan, plus app actions
                          (babel.assistant; numbers and actions checked by code)
  GET  /track-record      the published, verified backtest results (babel.track_record)
  GET  /health            liveness: the process is up (loads no data, calls nothing)
  GET  /health/ready      readiness: runtime data loaded, keys configured (yes/no only), backtest data present

Keys stay server-side (.env). Responses never contain keys, stack traces or cache contents. Settings come from
BABEL_* environment variables (see Settings). External calls go through babel.net with a short retry policy per
request. Run:  uvicorn babel.api:app --host 127.0.0.1 --port 8000
"""
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Optional

from fastapi import FastAPI, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.exceptions import HTTPException

from . import agent, assistant, describe, net
from . import plan as P

VERSION = "0.1.0"
CACHE_VERSION = 2  # bump when the engine changes what a plan contains
RECENT_PLANS = 64  # finished plans (ok or partial) the assistant can read, most recently used kept
log = logging.getLogger("babel.api")
STEAM_URL = re.compile(r"^(?:https?://)?store\.steampowered\.com/app/(\d+)(?:[/?#].*)?$")
PLAN_ID = re.compile(r"^[0-9a-f]{16}$")
WEB = P.ROOT / "web"  # the browser app: index.html + static/ (no build step)
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: https://*.steamstatic.com https://tile.openstreetmap.org; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def _console_logging():
    """One line per request on the console (never keys or bodies): babel's INFO lines go to the root handler that
    uvicorn or the MCP SDK sets up; with no handler anywhere, a plain one on stderr."""
    babel_log = logging.getLogger("babel")
    if babel_log.level == logging.NOTSET:
        babel_log.setLevel(logging.INFO)
    if not logging.getLogger().handlers and not babel_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        babel_log.addHandler(handler)


def _is_asset(path):
    return path == "/" or path.startswith("/static/")


# ---------------------------------------------------------------- settings
@dataclass(frozen=True)
class Settings:
    """Safe defaults; each one can be set with an environment variable (BABEL_<NAME>)."""
    cors_origins: tuple = ()          # BABEL_CORS_ORIGINS="https://a.example,https://b.example" (none: no CORS)
    plan_rate: tuple = (10, 60.0)     # BABEL_PLAN_RATE="10/60": POST /plan per client per 60 s
    lookup_rate: tuple = (30, 60.0)   # BABEL_LOOKUP_RATE: POST /lookalikes and GET /games/{appid} (may call Steam/Qloo)
    mcp_rate: tuple = (60, 60.0)      # BABEL_MCP_RATE: requests to /mcp (one tool call is several MCP requests)
    read_rate: tuple = (120, 60.0)    # BABEL_READ_RATE: other GETs (not /health)
    compute_rate: tuple = (300, 60.0)  # BABEL_COMPUTE_RATE: POST /fit-budget (pure computation, no external calls)
    assistant_rate: tuple = (20, 60.0)  # BABEL_ASSISTANT_RATE: POST /assistant (each message may call Claude)
    mcp_allowed_hosts: tuple = ()     # BABEL_MCP_ALLOWED_HOSTS="babel.example.com": public Host names for /mcp
                                      # (localhost is always allowed; others are refused: DNS-rebinding protection)
    max_body_bytes: int = 16_384      # BABEL_MAX_BODY_BYTES
    plan_timeout: float = 120.0       # BABEL_PLAN_TIMEOUT seconds for one plan
    max_concurrent: int = 4           # BABEL_MAX_CONCURRENT plans running at once
    cache_size: int = 256             # BABEL_CACHE_SIZE finished plans kept in memory
    upstream_attempts: int = 3        # BABEL_UPSTREAM_ATTEMPTS per external request
    upstream_max_wait: float = 5.0    # BABEL_UPSTREAM_MAX_WAIT seconds between attempts
    upstream_timeout: float = 30.0    # BABEL_UPSTREAM_TIMEOUT seconds per external request
    trust_proxy: bool = False         # BABEL_TRUST_PROXY=1: client IP from X-Forwarded-For (behind a proxy only)
    warmup: bool = True               # BABEL_WARMUP=0: do not load runtime data at startup

    @classmethod
    def from_env(cls, env=None):
        env, d = os.environ if env is None else env, cls()

        def rate(name, default):
            value = env.get(name)
            if not value:
                return default
            count, _, seconds = value.partition("/")
            return int(count), float(seconds or 60)

        def num(name, cast, default):
            return cast(env[name]) if env.get(name) else default
        return cls(
            cors_origins=tuple(o.strip() for o in env.get("BABEL_CORS_ORIGINS", "").split(",") if o.strip()),
            plan_rate=rate("BABEL_PLAN_RATE", d.plan_rate), read_rate=rate("BABEL_READ_RATE", d.read_rate),
            mcp_rate=rate("BABEL_MCP_RATE", d.mcp_rate), lookup_rate=rate("BABEL_LOOKUP_RATE", d.lookup_rate),
            compute_rate=rate("BABEL_COMPUTE_RATE", d.compute_rate),
            assistant_rate=rate("BABEL_ASSISTANT_RATE", d.assistant_rate),
            mcp_allowed_hosts=tuple(h.strip() for h in env.get("BABEL_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()),
            max_body_bytes=num("BABEL_MAX_BODY_BYTES", int, d.max_body_bytes),
            plan_timeout=num("BABEL_PLAN_TIMEOUT", float, d.plan_timeout),
            max_concurrent=num("BABEL_MAX_CONCURRENT", int, d.max_concurrent),
            cache_size=num("BABEL_CACHE_SIZE", int, d.cache_size),
            upstream_attempts=num("BABEL_UPSTREAM_ATTEMPTS", int, d.upstream_attempts),
            upstream_max_wait=num("BABEL_UPSTREAM_MAX_WAIT", float, d.upstream_max_wait),
            upstream_timeout=num("BABEL_UPSTREAM_TIMEOUT", float, d.upstream_timeout),
            trust_proxy=env.get("BABEL_TRUST_PROXY", "") in ("1", "true", "yes"),
            warmup=env.get("BABEL_WARMUP", "1") not in ("0", "false", "no"))


# ---------------------------------------------------------------- schemas
class PlanRequest(BaseModel):
    """One game (a Steam URL, app ID, name or description) plus word count and budget; optionally your own
    look-alike games (Steam app IDs)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    steam_url: Optional[str] = Field(None, max_length=300, examples=["https://store.steampowered.com/app/3146520/"])
    appid: Optional[int] = Field(None, ge=1, le=2_000_000_000, strict=True)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=describe.MAX_CHARS)
    word_count: int = Field(..., ge=1, le=P.MAX_WORDS, strict=True, examples=[30000])
    budget: float = Field(..., ge=0, le=10_000_000, allow_inf_nan=False, strict=True, examples=[10000])
    lookalikes: Optional[list[Annotated[int, Field(strict=True)]]] = Field(
        None, max_length=10, description="Steam app IDs of look-alike games")
    markets: bool = Field(True, description="Add market notes (Qloo audience and local favourites)")
    explain: bool = Field(True, description="Add Claude's explanation, checked against the evidence")

    @model_validator(mode="after")
    def one_game(self):
        if self.steam_url:
            match = STEAM_URL.match(self.steam_url)
            if not match:
                raise ValueError("steam_url must look like https://store.steampowered.com/app/<id>/")
            if self.appid not in (None, int(match.group(1))):
                raise ValueError("Give either steam_url or appid, not both.")
        if (self.steam_url or self.appid) and self.name:
            raise ValueError("Give either a Steam game (steam_url or appid) or a name, not both.")
        if self.description is not None and describe.description_problem(self.description):
            raise ValueError(describe.description_problem(self.description))
        if any(a < 1 for a in self.lookalikes or []):
            raise ValueError("lookalikes must be Steam app IDs (positive numbers).")
        if not (self.steam_url or self.appid or self.name or self.description or self.lookalikes):
            raise ValueError("Give a Steam URL, an app ID, a game name, a description or look-alike games.")
        return self

    def game_appid(self):
        return int(STEAM_URL.match(self.steam_url).group(1)) if self.steam_url else self.appid

    def agent_kwargs(self):
        return {"appid": self.game_appid(), "name": self.name, "description": self.description,
                "lookalikes": self.lookalikes, "word_count": self.word_count, "budget": self.budget,
                "with_markets": self.markets, "with_explanation": self.explain}

    def plan_id(self):
        """Same request, same id: the key of the in-process plan cache."""
        key = json.dumps({**self.agent_kwargs(), "v": CACHE_VERSION, "agent": agent.VERSION}, sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class GameRequest(BaseModel):
    """Exactly one game: a Steam URL, app ID, name, or a description (for a game without a store page)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    steam_url: Optional[str] = Field(None, max_length=300)
    appid: Optional[int] = Field(None, ge=1, le=2_000_000_000, strict=True)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=describe.MAX_CHARS)

    @model_validator(mode="after")
    def one_game(self):
        if self.steam_url and not STEAM_URL.match(self.steam_url):
            raise ValueError("steam_url must look like https://store.steampowered.com/app/<id>/")
        if sum(bool(x) for x in (self.steam_url or self.appid, self.name, self.description)) != 1:
            raise ValueError("Give exactly one of: a Steam URL or app ID, a game name, or a description.")
        if self.description is not None and describe.description_problem(self.description):
            raise ValueError(describe.description_problem(self.description))
        return self

    def game_appid(self):
        return int(STEAM_URL.match(self.steam_url).group(1)) if self.steam_url else self.appid


class Allocation(BaseModel):
    """A plan's 'allocation' object, unchanged: its unrounded estimated shares and the costs the optimizer used."""
    model_config = ConfigDict(extra="forbid")
    shares: dict[str, Annotated[float, Field(ge=0, allow_inf_nan=False)]]
    cost_full: dict[str, Annotated[float, Field(gt=0, le=1e9, allow_inf_nan=False)]]
    cost_store_page: dict[str, Annotated[float, Field(gt=0, le=1e9, allow_inf_nan=False)]]
    min_share: float = Field(P.MIN_SHARE, ge=0, lt=1, allow_inf_nan=False)
    supported: list[str] = Field(default_factory=list, max_length=len(P.LANGS))
    meaning: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def fourteen_languages(self):
        for name in ("shares", "cost_full", "cost_store_page"):
            if set(getattr(self, name)) != set(P.LANGS):
                raise ValueError(f"{name} must give exactly the 14 target languages: {', '.join(P.LANGS)}.")
        if sum(self.shares.values()) <= 0:
            raise ValueError("shares must not all be zero.")
        if not set(self.supported) <= set(P.LANGS):
            raise ValueError("supported must list target language codes only.")
        return self


class FitBudgetRequest(BaseModel):
    """A new budget for a finished plan: send the plan's `allocation` object unchanged."""
    model_config = ConfigDict(extra="forbid")
    budget: float = Field(..., ge=0, le=10_000_000, allow_inf_nan=False, strict=True, examples=[15000])
    allocation: Allocation


class FitBudget(BaseModel):
    """The budget-dependent part of the plan for the new budget (babel.plan.fit_budget, the engine's optimizer)."""
    status: Literal["ok", "store_pages_only", "nothing_affordable", "nothing_to_translate"]
    message: Optional[str]
    groups: dict[str, list[str]]
    reasons: dict[str, str]
    costs: dict[str, float]
    estimated_coverage: dict[str, Any]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    text: str = Field(..., min_length=1, max_length=2000)


class AssistantView(BaseModel):
    """What the user is looking at: the screen, the open plan and the Plan screen's current budget and selections."""
    model_config = ConfigDict(extra="forbid")
    view: Optional[Literal["start", "working", "plan", "track", "report"]] = None
    plan_id: Optional[str] = Field(None, pattern=PLAN_ID.pattern, description="The open plan (16 hex characters)")
    budget: Optional[float] = Field(None, ge=0, le=10_000_000, allow_inf_nan=False, strict=True,
                                    description="The budget now on the Plan screen (USD); the plan is re-fitted to it")
    metric: Optional[Literal["relative", "affinity", "demand", "plan"]] = None
    country: Optional[str] = Field(None, pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alpha-2, e.g. JP")
    language: Optional[str] = Field(None, pattern=f"^({'|'.join(P.LANGS)})$",
                                    description="One of the 14 target language codes, e.g. russian")
    lookalike: Optional[str] = Field(None, pattern=r"^(all|[1-9][0-9]{0,9})$",
                                     description="The map's filter: 'all' or one comparable game's Steam app ID")


class AssistantRequest(BaseModel):
    """The conversation so far (oldest first, the last message the user's) and what the user is looking at."""
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=12)
    context: AssistantView = Field(default_factory=AssistantView)

    @model_validator(mode="after")
    def users_turn(self):
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be the user's.")
        return self


class DroppedAction(BaseModel):
    type: str
    reason: str


class AssistantReply(BaseModel):
    """reply: plain text. kind: llm_text (Claude, every number checked) or fallback (written by code). checked: false
    only when Claude's reply quoted a number found neither in the evidence nor in the user's messages and was replaced.
    actions: {type, label (written by code), ...its arguments}, each checked against Babel's data. sources: evidence
    IDs the reply relies on (plan IDs as in result.evidence_index, or product:*, map, view, ...)."""
    reply: str
    kind: Literal["llm_text", "fallback"]
    checked: bool
    actions: list[dict[str, Any]]
    dropped_actions: list[DroppedAction]
    sources: list[str]


class Card(BaseModel):
    """A comparable game: usable only when Qloo has a real fan map for it (status 'valid')."""
    appid: Optional[int]
    name: str
    status: str
    usable: bool
    qloo_id: Optional[str] = None
    overlap: Optional[float] = Field(None, description="IDF-weighted Steam tag overlap with your game (0 to 1)")
    why: Optional[str] = None
    year: Optional[int] = None
    image: Optional[str] = None


class Suggestions(BaseModel):
    game: dict[str, Any]
    source: Literal["steam_tags", "store_description", "description"]
    lookalikes: list[Card] = Field(description="The comparable games the plan would use (send them unchanged, or "
                                               "swap some and send their app IDs as `lookalikes`)")
    alternatives: list[Card]
    rejected: list[Card]
    widened_search: bool
    notes: list[str]
    confidence: Optional[dict[str, Any]] = None


class SearchResults(BaseModel):
    results: list[Card]


class Event(BaseModel):
    """One agent event (stable, version 1); the same values as babel.agent's EVENT_TYPES, STEPS and STATUSES."""
    v: int
    seq: int
    type: Literal["plan", "act", "reflect", "verify", "explain", "error", "done"]
    step: Literal["goal", "game", "tags", "lookalikes", "fan_maps", "score", "optimize", "markets", "explain",
                  "verify", "result"]
    status: Literal["info", "started", "ok", "warning", "needs_input", "failed"]
    message: str
    data: dict[str, Any]


class PlanResponse(BaseModel):
    plan_id: str
    status: Literal["ok", "partial", "failed"]
    cached: bool
    result: Optional[dict[str, Any]] = Field(description="plan, market_notes, explanation, evidence_index")
    events: list[Event]


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    uptime_s: float


class Ready(BaseModel):
    ready: bool
    checks: dict[str, Any]


class ErrorBody(BaseModel):
    error: str
    message: str
    request_id: str
    details: Optional[list[dict[str, str]]] = None


# ---------------------------------------------------------------- runtime pieces
class Cancelled(BaseException):
    """Raised inside the agent's thread to stop it (client gone or time out); BaseException so no step catches it."""


class RateLimiter:
    """Sliding-window request counts per client and bucket (in process)."""

    def __init__(self):
        self.hits, self.lock = defaultdict(deque), threading.Lock()

    def retry_after(self, key, limit, window, now=None):
        """0 if the request may go ahead (and count it), else seconds until it may."""
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return max(1, math.ceil(q[0] + window - now))
            q.append(now)
            return 0


class PlanCache:
    """Finished plans (status ok only) by plan id, least recently used dropped first."""

    def __init__(self, size):
        self.size, self.items, self.lock = size, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
            return None

    def put(self, key, value):
        with self.lock:
            self.items[key] = value
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)


class State:
    def __init__(self, settings, runner, loader):
        self.settings, self.runner, self.loader = settings, runner, loader
        self.ready, self.data_status, self.data_source, self.ctx = threading.Event(), "not loaded", None, None
        self.cache, self.limiter = PlanCache(settings.cache_size), RateLimiter()
        self.recent = PlanCache(RECENT_PLANS)  # ok and partial plans, for the assistant (GET /plans serves ok only)
        self.active, self.active_lock, self.started = 0, threading.Lock(), time.monotonic()

    def finished(self, plan_id, body):
        """Keep a finished plan: ok ones in the plan cache (GET /plans, cache hits); ok and partial ones for the
        assistant."""
        if body["status"] in ("ok", "partial"):
            self.recent.put(plan_id, body)
        if body["status"] == "ok":
            self.cache.put(plan_id, body)

    def plan_body(self, plan_id):
        """A finished plan this server produced (ok or partial), or None."""
        return self.recent.get(plan_id) or self.cache.get(plan_id)

    def warm_up(self):
        """Load the runtime data (look-alike pool, baseline, lift reference) once; readiness waits for it."""
        self.data_status = "loading"
        try:
            self.ctx = self.loader()
            self.data_status = "ready"
            self.data_source = getattr(self.ctx, "source", "custom")
            self.ready.set()
        except Exception as exc:  # reported by /health/ready; details go to the server log only
            log.exception("warm-up failed")
            self.data_status = f"failed ({type(exc).__name__})"
            return
        try:  # the Track record screen's data (about 1 s to compute; cached after this)
            from .track_record import track_record
            track_record()
        except Exception:
            log.exception("track record pre-computation failed (it is computed on the first request instead)")

    def claim(self):
        with self.active_lock:
            if self.active >= self.settings.max_concurrent:
                return False
            self.active += 1
            return True

    def release(self):
        with self.active_lock:
            self.active -= 1


def load_context():
    ctx = P.context()
    ctx.prior, ctx.base, ctx.country_reference, ctx.default_map, ctx.picker  # noqa: B018 (load it all now)
    return ctx


def run_agent(kwargs, ctx, sink):
    return agent.run(**kwargs, ctx=ctx, sink=sink)


class Job:
    """One agent run in a worker thread; its events go to an asyncio queue as they happen."""

    def __init__(self, state, req, loop):
        self.state, self.req, self.loop = state, req, loop
        self.queue, self.cancelled, self.out, self.failed = asyncio.Queue(), threading.Event(), None, False

    def _put(self, item):
        """Hand an item to the request's event loop; False if that loop is gone (the request ended)."""
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)
            return True
        except RuntimeError:
            return False

    def sink(self, event):
        if self.cancelled.is_set() or not self._put(("event", event)):
            raise Cancelled()

    def work(self):
        s = self.state.settings
        token = net.policy.set({"attempts": s.upstream_attempts, "max_wait": s.upstream_max_wait,
                                "timeout": s.upstream_timeout})
        try:
            self.out = self.state.runner(self.req.agent_kwargs(), self.state.ctx, self.sink)
        except Cancelled:
            log.info("plan %s stopped (client gone or timed out)", self.req.plan_id())
        except Exception:  # the client gets a generic error event; the traceback stays in the server log
            log.exception("plan %s failed", self.req.plan_id())
            self.failed = True
        finally:
            net.policy.reset(token)
            self.state.release()
            self._put(("end", None))

    def start(self):
        threading.Thread(target=self.work, name=f"plan-{self.req.plan_id()}", daemon=True).start()


def _public(event):
    """An agent event as streamed: the 'done' event without the full result (that comes in the 'result' event)."""
    if event["type"] == "done":
        return {**event, "data": {k: v for k, v in event["data"].items() if k != "result"}}
    return event


def _api_error(seq, message, request_id):
    return {"v": agent.VERSION, "seq": seq, "type": "error", "step": "result", "status": "failed",
            "message": message, "data": {"request_id": request_id}}


def _sse(name, payload, event_id=None):
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------- the app
def create_app(settings=None, runner=run_agent, loader=load_context, lookup=None):
    """The app. `runner` runs a plan (babel.agent), `loader` loads the runtime data, `lookup` answers the Start
    screen's look-alike questions (babel.suggest); tests pass fakes with the same signatures."""
    from . import mcp_server, suggest
    settings = settings or Settings.from_env()
    state = State(settings, runner, loader)
    lookup = lookup or suggest
    mcp = mcp_server.build(state, settings.mcp_allowed_hosts, settings.cors_origins)
    _console_logging()  # after the MCP SDK has configured logging
    mcp_routes = mcp.streamable_http_app().routes  # POST/GET/DELETE /mcp (streamable HTTP transport)

    @asynccontextmanager
    async def lifespan(app):
        if settings.warmup:
            threading.Thread(target=state.warm_up, name="warm-up", daemon=True).start()
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Babel API", version=VERSION, lifespan=lifespan,
                  description="Costed translation plans for indie Steam games, with Qloo evidence. See "
                              "docs/BABEL_BRIEF.md.")
    app.state.babel = state
    app.state.mcp = mcp
    app.router.routes.extend(mcp_routes)

    def error(status, code, message, request, details=None, headers=None):
        body = ErrorBody(error=code, message=message, request_id=request.state.request_id, details=details)
        return JSONResponse(body.model_dump(exclude_none=True), status_code=status, headers=headers)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        """Request id, body-size limit, rate limits, safe headers and one log line per request."""
        request.state.request_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > settings.max_body_bytes):
            return error(413, "too_large", f"The request body is limited to {settings.max_body_bytes} bytes.",
                         request)
        if request.method == "POST" and length is None and request.url.path in ("/plan", "/mcp", "/assistant"):
            body = await request.body()  # chunked upload: measure it before anything parses it
            if len(body) > settings.max_body_bytes:
                return error(413, "too_large", f"The request body is limited to {settings.max_body_bytes} bytes.",
                             request)
        path = request.url.path
        if not path.startswith("/health") and request.method != "OPTIONS" and not _is_asset(path):
            bucket = (path if path in ("/plan", "/mcp") else
                      "lookup" if path == "/lookalikes" or (path.startswith("/games/") and path != "/games/search")
                      else "compute" if path == "/fit-budget" else "assistant" if path == "/assistant" else "read")
            limit, window = {"/plan": settings.plan_rate, "/mcp": settings.mcp_rate, "lookup": settings.lookup_rate,
                             "compute": settings.compute_rate,
                             "assistant": settings.assistant_rate}.get(bucket, settings.read_rate)
            client = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() if settings.trust_proxy
                      else "") or (request.client.host if request.client else "unknown")
            wait = state.limiter.retry_after((client, bucket), limit, window)
            if wait:
                return error(429, "rate_limited", f"Too many requests; try again in {wait} s.", request,
                             headers={"Retry-After": str(wait)})
        response = await call_next(request)
        response.headers.update({"X-Request-ID": request.state.request_id, "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer"})
        if response.headers.get("content-type", "").startswith("text/html") and not path.startswith(("/docs",
                                                                                                    "/redoc")):
            response.headers.update({"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})
        if path == "/" or path.startswith("/static/"):  # browsers re-check (a cheap 304), so a reload shows edits
            response.headers.setdefault("Cache-Control", "no-cache")
        log.info("%s %s %s %.0fms %s", request.method, request.url.path, response.status_code,
                 (time.monotonic() - started) * 1000, request.state.request_id)
        return response

    if settings.cors_origins:  # added last, so it is the outermost layer: error responses carry CORS headers too
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type"], max_age=600,
                           expose_headers=["X-Request-ID", "X-Babel-Cache", "Retry-After"])

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(x) for x in e["loc"] if x != "body") or "body",
                    "message": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]
        return error(422, "invalid_request", "The request is not valid.", request, details)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error(exc.status_code, code, str(exc.detail), request)

    @app.exception_handler(Exception)
    async def crash(request: Request, exc: Exception):
        log.error("unhandled error %s", request.state.request_id, exc_info=exc)
        return error(500, "internal_error", "Something went wrong. Quote the request ID if you report it.", request)

    # ------------------------------------------------------------ endpoints
    @app.get("/health", response_model=Health, tags=["health"])
    def health():
        """Liveness: the process answers. Loads no data and calls no external service."""
        return Health(status="ok", version=VERSION, uptime_s=round(time.monotonic() - state.started, 1))

    @app.get("/health/ready", response_model=Ready, tags=["health"],
             responses={503: {"model": Ready, "description": "Not ready yet (or warm-up failed)"}})
    def ready():
        """Readiness: runtime data loaded, keys configured (yes/no only), backtest data present."""
        checks = {"runtime_data": state.data_status, "runtime_source": state.data_source,
                  "qloo_key_configured": bool(os.environ.get("QLOO_API_KEY")),
                  "anthropic_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
                  "backtest_data": all((P.BACKTEST_DATA / f).exists() for f in (
                      "truth_reviews.csv", "comps.csv", "final_predictions_steam.csv", "final_predictions_wiki.csv")),
                  "plans_running": state.active, "plans_cached": len(state.cache.items)}
        ok = state.ready.is_set() and checks["qloo_key_configured"] and checks["backtest_data"]
        return JSONResponse(Ready(ready=ok, checks=checks).model_dump(), status_code=200 if ok else 503)

    @app.get("/track-record", tags=["evidence"])
    def track_record(games: bool = Query(True, description="Include every test game's predicted and real top 3")):
        """The published, verified backtest results (pre-registered), recomputed from backtest/data."""
        from .track_record import track_record as compute
        record = compute()
        if games:
            return record
        return {**record, "truths": {k: {kk: vv for kk, vv in v.items() if kk != "games"}
                                     for k, v in record["truths"].items()}}

    # ------------------------------------------------------------ Start screen: comparable games
    async def _lookup(request, fn):
        """Run a look-up that may call Steam, Qloo or Claude, in a worker thread with the short retry policy."""
        if not state.ready.is_set():
            return error(503, "not_ready", "The server is still loading its data; try again shortly.", request,
                         headers={"Retry-After": "10"})

        def call():
            token = net.policy.set({"attempts": settings.upstream_attempts, "max_wait": settings.upstream_max_wait,
                                    "timeout": settings.upstream_timeout})
            try:
                return fn(state.ctx)
            finally:
                net.policy.reset(token)
        try:
            return await asyncio.wait_for(asyncio.to_thread(call), settings.plan_timeout)
        except P.PlanError as e:
            return error(404, "not_found", str(e), request)
        except asyncio.TimeoutError:
            return error(504, "timeout", "Looking up the game took too long; try again.", request)
        except Exception:  # Steam / Qloo after retries, or Claude: logged here, a plain message for the client
            log.exception("look-up failed %s", request.state.request_id)
            return error(502, "upstream_error", "The game could not be looked up right now (Steam, Qloo or Claude "
                                                "did not answer); try again in a minute.", request)

    @app.post("/lookalikes", response_model=Suggestions, tags=["start"],
              responses={404: {"model": ErrorBody}, 422: {"model": ErrorBody}, 429: {"model": ErrorBody},
                         502: {"model": ErrorBody}, 503: {"model": ErrorBody}, 504: {"model": ErrorBody}})
    async def lookalikes(req: GameRequest, request: Request):
        """The comparable games the plan would use for this game, alternatives to swap in, and rejected ones."""
        return await _lookup(request, lambda ctx: lookup.suggest(ctx, appid=req.game_appid(), name=req.name,
                                                                 description=req.description))

    @app.get("/games/search", response_model=SearchResults, tags=["start"])
    async def games_search(request: Request, q: str = Query(..., min_length=2, max_length=80)):
        """Well-known games in the look-alike pool whose name contains `q` (no external calls)."""
        return await _lookup(request, lambda ctx: {"results": lookup.search(ctx, q)})

    @app.get("/games/{appid}", response_model=Card, tags=["start"],
             responses={404: {"model": ErrorBody}, 502: {"model": ErrorBody}})
    async def game_check(request: Request, appid: int = Path(..., ge=1, le=2_000_000_000)):
        """One game's Steam data and whether Qloo has a real fan map for it (can it be a comparable game?)."""
        return await _lookup(request, lambda ctx: lookup.check(ctx, appid))

    # ------------------------------------------------------------ the browser app
    if WEB.exists():
        app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/plans/{plan_id}", response_model=PlanResponse, tags=["plans"],
             responses={404: {"model": ErrorBody}})
    def get_plan(plan_id: str, request: Request):
        """A finished plan from this server's in-process cache."""
        hit = state.cache.get(plan_id) if PLAN_ID.match(plan_id) else None
        if hit is None:
            return error(404, "not_found", "No finished plan with that id on this server.", request)
        return PlanResponse(plan_id=plan_id, cached=True, **hit)

    @app.post("/fit-budget", response_model=FitBudget, tags=["plans"],
              responses={422: {"model": ErrorBody}, 429: {"model": ErrorBody}})
    def fit_budget(req: FitBudgetRequest):
        """Re-fit a finished plan to a new budget with the engine's own optimizer (no external calls, no LLM): the
        groups, reasons, costs and coverage the engine would give for that budget. Scores do not change."""
        a = req.allocation
        return P.fit_budget(a.shares, a.cost_full, a.cost_store_page, req.budget, a.min_share, a.supported)

    @app.post("/assistant", response_model=AssistantReply, tags=["assistant"],
              responses={413: {"model": ErrorBody}, 422: {"model": ErrorBody}, 429: {"model": ErrorBody}})
    async def ask_assistant(req: AssistantRequest):
        """Babel's assistant: a short answer about Babel or the open plan (at the budget on screen), from evidence only;
        Claude may quote only numbers found in that evidence or in the user's messages (checked by code), and the app
        actions it proposes are checked against Babel's data and labelled by code. Without Claude: a fallback reply
        (200, kind 'fallback', no actions). Works before the runtime data is loaded; plan questions need a plan this
        server produced."""
        view = req.context.model_dump()
        body = state.plan_body(view["plan_id"]) if view["plan_id"] else None
        messages = [m.model_dump() for m in req.messages]
        missing = view["plan_id"] is not None and body is None
        try:
            return await asyncio.wait_for(asyncio.to_thread(assistant.answer, messages, view, body, missing),
                                          settings.plan_timeout)
        except asyncio.TimeoutError:
            return assistant.unavailable()

    @app.post("/plan", tags=["plans"], response_model=PlanResponse,
              responses={200: {"content": {"text/event-stream": {}}, "description":
                               "Server-Sent Events: meta, then the agent's events (plan, act, reflect, verify, "
                               "explain, error, done), then result {plan_id, status, cached, result}."},
                         422: {"model": ErrorBody}, 429: {"model": ErrorBody}, 503: {"model": ErrorBody},
                         504: {"model": ErrorBody}})
    async def post_plan(req: PlanRequest, request: Request,
                        stream: bool = Query(True, description="false: one JSON response instead of SSE")):
        """Run the agent for one game and stream its progress, then the final plan."""
        plan_id = req.plan_id()
        if not state.ready.is_set():
            return error(503, "not_ready", "The server is still loading its data; try again shortly.", request,
                         headers={"Retry-After": "10"})
        hit = state.cache.get(plan_id)
        if hit is not None:
            state.recent.put(plan_id, hit)  # the plan this browser now has open: readable by the assistant
        if hit is None and not state.claim():
            return error(503, "busy", "Too many plans are running; try again shortly.", request,
                         headers={"Retry-After": "5"})
        headers = {"X-Babel-Cache": "hit" if hit else "miss", "Cache-Control": "no-cache",
                   "X-Accel-Buffering": "no"}
        job = None
        if hit is None:
            job = Job(state, req, asyncio.get_running_loop())
            job.start()
        if not stream:
            return await _json_result(request, state, plan_id, hit, job, headers)
        return StreamingResponse(_stream(request, state, plan_id, hit, job), media_type="text/event-stream",
                                 headers=headers)

    async def _json_result(request, state, plan_id, hit, job, headers):
        if hit:
            return JSONResponse(PlanResponse(plan_id=plan_id, cached=True, **hit).model_dump(), headers=headers)
        deadline = asyncio.get_running_loop().time() + state.settings.plan_timeout
        events = []
        while True:
            try:
                kind, event = await asyncio.wait_for(job.queue.get(), deadline - asyncio.get_running_loop().time())
            except (asyncio.TimeoutError, ValueError):
                job.cancelled.set()
                return error(504, "timeout", f"The plan took longer than {state.settings.plan_timeout:.0f} s.",
                             request)
            if kind == "event":
                events.append(_public(event))
                continue
            if job.failed or job.out is None:
                return error(500, "internal_error", "The plan could not be finished. Quote the request ID if you "
                                                    "report it.", request)
            body = {"status": job.out["status"], "result": job.out["result"], "events": events}
            state.finished(plan_id, body)
            return JSONResponse(PlanResponse(plan_id=plan_id, cached=False, **body).model_dump(), headers=headers)

    async def _stream(request, state, plan_id, hit, job):
        request_id = request.state.request_id
        yield _sse("meta", {"plan_id": plan_id, "cache": "hit" if hit else "miss", "request_id": request_id})
        if hit:
            for event in hit["events"]:
                yield _sse(event["type"], event, event["seq"])
            yield _sse("result", {"plan_id": plan_id, "status": hit["status"], "cached": True, "result": hit["result"]})
            return
        loop, events = asyncio.get_running_loop(), []
        deadline, last_sent = loop.time() + state.settings.plan_timeout, loop.time()
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    job.cancelled.set()
                    yield _sse("error", _api_error(len(events) + 1, f"The plan took longer than "
                                                   f"{state.settings.plan_timeout:.0f} s and was stopped.", request_id))
                    return
                try:
                    kind, event = await asyncio.wait_for(job.queue.get(), min(remaining, 1.0))
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        return
                    if loop.time() - last_sent > 15:
                        last_sent = loop.time()
                        yield ": keep-alive\n\n"
                    continue
                last_sent = loop.time()
                if kind == "event":
                    events.append(_public(event))
                    yield _sse(event["type"], events[-1], event["seq"])
                    continue
                if job.failed or job.out is None:
                    yield _sse("error", _api_error(len(events) + 1, "The plan could not be finished. Quote the "
                                                                    "request ID if you report it.", request_id))
                    return
                body = {"status": job.out["status"], "result": job.out["result"], "events": events}
                state.finished(plan_id, body)
                yield _sse("result", {"plan_id": plan_id, "status": body["status"], "cached": False,
                                      "result": body["result"]})
                return
        finally:
            job.cancelled.set()  # client gone, time out or finished: a still-running agent stops at its next step

    return app


app = create_app()
