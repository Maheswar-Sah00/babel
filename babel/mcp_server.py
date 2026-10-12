"""Babel as an MCP tool, `babel_language_plan`, built with the official Python MCP SDK (mcp 1.x, FastMCP).

Two transports, one tool:
  - Streamable HTTP, mounted on the web API at /mcp (stateless, so any instance can answer any request). It shares
    POST /plan's validation, rate limits, plan cache, readiness gate, concurrency limit and agent.
        uvicorn babel.api:app   ->  MCP endpoint http://127.0.0.1:8000/mcp
  - stdio, for MCP clients that start the server themselves:
        python -m babel.mcp_server
The tool validates its input with the same schema as POST /plan (babel.api.PlanRequest), runs the same agent
(babel.agent -> babel.plan) and returns the same plan, plus a short summary, market evidence, caveats and provenance.
It exposes nothing else: no files, cache contents, keys or other operations. Each agent step is also sent to the
client as an MCP log message while the plan runs.
"""
import asyncio
import threading
from typing import Annotated, Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from . import api
from .languages import LABEL

TOOL = "babel_language_plan"
READY_WAIT = 60.0  # seconds a call waits for the server's data to finish loading
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
INSTRUCTIONS = ("Babel plans which languages to translate an indie Steam game into, within a budget, using Qloo fan "
                "maps of look-alike games. Call babel_language_plan with a steam_url (or a description for a game "
                "without a store page), the game's word count and the translation budget in USD.")
DESCRIPTION = (
    "A costed translation plan for a Steam game: every one of 14 target languages is put in 'translate the game', "
    "'store page only' or 'skip for now', with estimated costs, the evidence behind each decision (Qloo fan maps of "
    "look-alike games, the typical language mix, a pre-registered backtest), market notes and caveats. Give exactly "
    "one of steam_url, appid, name or description (a description is for games without a store page), plus "
    "word_count and budget. Shares are estimates of where non-English demand is, not sales; costs are estimates "
    "from editable per-word rates, not quotes. Identical inputs return the identical plan.")


def build(state, allowed_hosts=(), allowed_origins=()):
    """The FastMCP server for an api.State (shared with the web API, or its own for stdio)."""
    security = TransportSecuritySettings(  # DNS-rebinding protection: only these Host / Origin headers are served
        enable_dns_rebinding_protection=True, allowed_hosts=LOCAL_HOSTS + list(allowed_hosts),
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"] + list(allowed_origins))
    server = FastMCP("babel", instructions=INSTRUCTIONS, stateless_http=True, streamable_http_path="/mcp",
                     transport_security=security, log_level="WARNING")
    server._mcp_server.version = api.VERSION  # report Babel's version, not the SDK's (FastMCP has no option for it)

    @server.tool(name=TOOL, title="Babel: which languages to translate a Steam game into", description=DESCRIPTION,
                 annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True))
    async def babel_language_plan(
            word_count: Annotated[int, Field(description="Words to translate in the game (1 to 5,000,000)")],
            budget: Annotated[float, Field(description="Translation budget in USD (0 or more)")],
            steam_url: Annotated[Optional[str], Field(
                description="Steam store link, e.g. https://store.steampowered.com/app/3146520/")] = None,
            description: Annotated[Optional[str], Field(
                description="Free-text description, for a game without a store page (10 to 4,000 characters)")] = None,
            name: Annotated[Optional[str], Field(description="Game name to look up on Steam")] = None,
            appid: Annotated[Optional[int], Field(description="Steam app ID")] = None,
            lookalikes: Annotated[Optional[list[int]], Field(
                description="Your own comparable games: up to 10 Steam app IDs")] = None,
            include_market_notes: Annotated[bool, Field(
                description="Add Qloo audience data and what fans love in the top markets")] = True,
            include_explanation: Annotated[bool, Field(
                description="Add a plain-English explanation, checked against the evidence")] = True,
            ctx: Context = None) -> dict[str, Any]:
        return await run_tool(state, {
            "word_count": word_count, "budget": budget, "steam_url": steam_url, "description": description,
            "name": name, "appid": appid, "lookalikes": lookalikes, "markets": include_market_notes,
            "explain": include_explanation}, ctx)

    return server


def _invalid(e):
    problems = "; ".join(f"{'.'.join(str(x) for x in err['loc']) or 'input'}: "
                         f"{err['msg'].removeprefix('Value error, ')}" for err in e.errors())
    return ToolError(f"Invalid input ({problems}). Give exactly one of steam_url, appid, name or description, plus "
                     "word_count (1 to 5,000,000) and budget (USD, 0 or more).")


async def run_tool(state, args, ctx=None):
    """Validate, then answer from the plan cache or run the agent (same path as POST /plan); errors are ToolErrors
    with a message the caller can act on, never internals."""
    try:
        req = api.PlanRequest.model_validate({k: v for k, v in args.items() if v is not None})
    except ValidationError as e:
        raise _invalid(e) from None
    wait = min(READY_WAIT, state.settings.plan_timeout)
    if not state.ready.is_set() and not await asyncio.to_thread(state.ready.wait, wait):
        raise ToolError("Babel is still loading its data; try again in about 30 seconds.")
    plan_id, cached = req.plan_id(), True
    body = state.cache.get(plan_id)
    if body is None:
        if not state.claim():
            raise ToolError("Babel is busy with other plans; try again in a few seconds.")
        job, cached = api.Job(state, req, asyncio.get_running_loop()), False
        job.start()
        body = await _finish(job, state, ctx)
    if body["status"] == "failed":
        errors = [e["message"] for e in body["events"] if e["type"] == "error"]
        raise ToolError("Babel could not plan this game: " + (" ".join(errors) or "see the trace."))
    return output(plan_id, body, cached)


async def _finish(job, state, ctx):
    """Collect the agent's events (forwarding each to the client as a log message) until it ends."""
    loop, events = asyncio.get_running_loop(), []
    deadline = loop.time() + state.settings.plan_timeout
    try:
        while True:
            try:
                kind, event = await asyncio.wait_for(job.queue.get(), max(0.0, deadline - loop.time()))
            except asyncio.TimeoutError:
                raise ToolError(f"The plan took longer than {state.settings.plan_timeout:.0f} s and was stopped; "
                                "try again later.") from None
            if kind == "event":
                events.append(api._public(event))
                if ctx is not None:
                    await ctx.info(f"[{event['type']}/{event['step']}] {event['message']}")
                continue
            if job.failed or job.out is None:
                raise ToolError("The plan could not be finished because of an internal error; try again later.")
            body = {"status": job.out["status"], "result": job.out["result"], "events": events}
            state.finished(job.req.plan_id(), body)  # ok: the plan cache; ok or partial: readable by the assistant
            return body
    finally:
        job.cancelled.set()  # time out, cancelled call or finished: a still-running agent stops at its next step


def output(plan_id, body, cached):
    """The tool's structured result. `plan` is the same object POST /plan and the CLI return."""
    r = body["result"]
    p, notes, exp = r["plan"], r["market_notes"], r["explanation"]
    labels = {g: [LABEL[c] for c in codes] for g, codes in p["groups"].items()}
    return {
        "plan_id": plan_id, "status": body["status"], "cached": cached,
        "summary": {**labels, "total_cost_usd": p["costs"]["total"], "budget_usd": p["costs"]["budget"],
                    "estimated_coverage": p["estimated_coverage"], "evidence_level": p["lookalikes"]["evidence_level"],
                    "explanation": exp["summary"] if exp else None},
        "plan": p, "market_notes": notes, "explanation": exp,
        "caveats": p["uncertainty"]["caveats"] + (notes["caveats"] if notes else []),
        "provenance": {
            "engine": "babel.plan (deterministic; every number from code) run by babel.agent",
            "model": "typical language mix x Qloo S1 lift of look-alike games, alpha 1 (pre-registered backtest)",
            "track_record": p["track_record"], "evidence_index": r["evidence_index"],
            "trace": [{k: e[k] for k in ("seq", "type", "step", "status", "message")} for e in body["events"]]},
    }


def main():
    """stdio transport: this process is the MCP server; its own data warms up in the background."""
    state = api.State(api.Settings.from_env(), api.run_agent, api.load_context)
    if state.settings.warmup:
        threading.Thread(target=state.warm_up, name="warm-up", daemon=True).start()
    build(state).run("stdio")


if __name__ == "__main__":
    main()
