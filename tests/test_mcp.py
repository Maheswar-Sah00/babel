"""The MCP tool babel_language_plan: discovery, valid calls, invalid input, errors, the same plan as the API, and the
two transports (streamable HTTP on the web app, stdio as a subprocess) through the official MCP client."""
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from babel import api, mcp_server
from live_server import serve

ROOT = Path(__file__).resolve().parents[1]
GAME = {"steam_url": "https://store.steampowered.com/app/3146520/WEBFISHING/", "word_count": 30_000, "budget": 10_000}


class FakeAgent:
    """Has babel.agent.run's signature; returns a small plan-shaped result."""

    def __init__(self, status="ok", crash=None):
        self.status, self.crash, self.calls = status, crash, []

    def __call__(self, kwargs, ctx, sink):
        self.calls.append(kwargs)
        events = [{"v": 1, "seq": 1, "type": "plan", "step": "goal", "status": "info", "message": "Goal: a plan.",
                   "data": {}}]
        sink(events[0])
        if self.crash:
            raise self.crash
        if self.status == "failed":
            events.append({"v": 1, "seq": 2, "type": "error", "step": "game", "status": "failed",
                           "message": f"Steam has no store data for app {kwargs['appid']}.", "data": {}})
            sink(events[-1])
            return {"status": "failed", "result": None, "events": events}
        plan = {"groups": {"translate_game": ["russian", "spanish"], "store_page_only": ["german"], "skip": ["thai"],
                           "already_supported": []},
                "costs": {"total": 7400.0, "budget": kwargs["budget"]}, "estimated_coverage": {"translate_game": 0.3},
                "lookalikes": {"evidence_level": "normal"}, "uncertainty": {"caveats": ["Estimates, not sales."]},
                "track_record": {"source": "backtest/final_report.md"}, "inputs": kwargs}
        notes = {"caveats": ["Aggregate taste, never an individual."], "markets": []}
        result = {"plan": plan, "market_notes": notes, "explanation": {"summary": "Translate Russian and Spanish."},
                  "evidence_index": {"plan": {"budget": "$10,000"}}}
        events.append({"v": 1, "seq": 2, "type": "done", "step": "result", "status": "ok", "message": "Plan ready.",
                       "data": {"status": "ok", "result": result}})
        sink(events[-1])
        return {"status": "ok", "result": result, "events": events}


def make(fake=None, ready=True, **settings):
    app = api.create_app(api.Settings(warmup=False, **settings), runner=fake or FakeAgent())
    state = app.state.babel
    if ready:
        state.ctx = "CTX"
        state.ready.set()
    return app


def call(app, arguments, logs=None):
    """List the tools and call babel_language_plan through an in-memory MCP client."""
    async def go():
        async def on_log(params):
            if logs is not None:
                logs.append(params.data)
        async with create_connected_server_and_client_session(app.state.mcp, logging_callback=on_log) as session:
            tools = await session.list_tools()
            return tools, await session.call_tool(mcp_server.TOOL, arguments)
    return asyncio.run(go())


# ---------------------------------------------------------------- discovery and valid calls
def test_the_tool_is_discoverable_with_a_clear_input_schema():
    tools, _ = call(make(), GAME)
    (tool,) = tools.tools
    schema = tool.inputSchema
    assert tool.name == "babel_language_plan" and tool.annotations.readOnlyHint
    assert schema["required"] == ["word_count", "budget"]
    assert {"steam_url", "description", "name", "appid", "lookalikes"} <= set(schema["properties"])
    assert all(p.get("description") for p in schema["properties"].values())
    assert "estimates" in tool.description and tool.outputSchema is not None


def test_a_valid_call_returns_the_structured_plan_and_streams_the_trace():
    fake, logs = FakeAgent(), []
    _, result = call(make(fake), {**GAME, "lookalikes": [413150]}, logs)
    out = result.structuredContent
    assert not result.isError and out["status"] == "ok" and not out["cached"]
    assert out["summary"]["translate_game"] == ["Russian", "Spanish"] and out["summary"]["total_cost_usd"] == 7400.0
    assert {"plan", "market_notes", "explanation", "caveats", "provenance"} <= set(out)
    assert out["caveats"] == ["Estimates, not sales.", "Aggregate taste, never an individual."]
    assert out["provenance"]["evidence_index"] and out["provenance"]["trace"][0]["type"] == "plan"
    assert json.loads(result.content[0].text) == out  # the same result as text, for clients without structured output
    assert fake.calls[0]["appid"] == 3146520 and fake.calls[0]["lookalikes"] == [413150]
    assert logs == ["[plan/goal] Goal: a plan.", "[done/result] Plan ready."]


def test_the_mcp_plan_is_the_api_plan():
    via_api = TestClient(make()).post("/plan?stream=false", json=GAME).json()
    _, via_mcp = call(make(), GAME)
    assert via_mcp.structuredContent["plan"] == via_api["result"]["plan"]
    assert via_mcp.structuredContent["plan_id"] == via_api["plan_id"]
    shared = make()
    TestClient(shared).post("/plan?stream=false", json=GAME)
    _, again = call(shared, GAME)  # same server: the plan cache is shared with POST /plan
    assert again.structuredContent["cached"] and again.structuredContent["plan"] == via_api["result"]["plan"]


# ---------------------------------------------------------------- invalid input and errors
@pytest.mark.parametrize("arguments, expected", [
    ({"word_count": 30_000, "budget": -5, "appid": 1}, "budget"),
    ({"word_count": 0, "budget": 100, "appid": 1}, "word_count"),
    ({"word_count": 30_000, "budget": 100}, "Give a Steam URL"),
    ({**GAME, "steam_url": "https://example.com/app/1"}, "steam_url must look like"),
    ({**GAME, "name": "WEBFISHING"}, "not both"),
    ({"word_count": 30_000, "budget": 100, "description": "tiny"}, "at least 10 characters"),
    ({**GAME, "lookalikes": list(range(1, 13))}, "lookalikes"),
    ({"budget": 100, "appid": 1}, "word_count"),
    ({"word_count": "many", "budget": 100, "appid": 1}, "word_count"),
])
def test_invalid_input_gets_an_actionable_error(arguments, expected):
    fake = FakeAgent()
    _, result = call(make(fake), arguments)
    assert result.isError and expected in result.content[0].text and fake.calls == []


def test_errors_never_reveal_internals():
    _, crashed = call(make(FakeAgent(crash=ValueError("C:/babel/cache/qloo secret"))), GAME)
    assert crashed.isError and "internal error" in crashed.content[0].text
    assert "secret" not in crashed.content[0].text and "Traceback" not in crashed.content[0].text


def test_a_game_the_agent_cannot_plan_returns_its_reason():
    _, result = call(make(FakeAgent(status="failed")), {**GAME, "steam_url": None, "appid": 999_999_999})
    assert result.isError and "Steam has no store data for app 999999999" in result.content[0].text


def test_busy_and_not_ready_are_reported():
    _, busy = call(make(max_concurrent=0), GAME)
    assert busy.isError and "busy" in busy.content[0].text
    _, loading = call(make(ready=False, plan_timeout=0.2), GAME)
    assert loading.isError and "still loading" in loading.content[0].text


# ---------------------------------------------------------------- streamable HTTP on the web app
def test_streamable_http_transport_end_to_end():
    async def go(url):
        async with streamable_http_client(f"{url}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                tools = await session.list_tools()
                return info, tools, await session.call_tool(mcp_server.TOOL, GAME)
    with serve(make()) as url:
        info, tools, result = asyncio.run(go(url))
    assert info.serverInfo.name == "babel" and [t.name for t in tools.tools] == ["babel_language_plan"]
    assert not result.isError and result.structuredContent["summary"]["translate_game"] == ["Russian", "Spanish"]


def test_http_transport_refuses_unknown_hosts():
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with serve(make(mcp_allowed_hosts=("babel.example",))) as url:
        evil = httpx.post(f"{url}/mcp", json=init, headers={**headers, "Host": "evil.example"})
        allowed = httpx.post(f"{url}/mcp", json=init, headers={**headers, "Host": "babel.example"})
    assert evil.status_code >= 400 and "Invalid Host" in evil.text
    assert allowed.status_code == 200


# ---------------------------------------------------------------- stdio transport (a real subprocess)
def test_stdio_transport_lists_and_validates():
    params = StdioServerParameters(command=sys.executable, args=["-m", "babel.mcp_server"], cwd=str(ROOT),
                                   env={**os.environ, "BABEL_WARMUP": "0"})

    async def go():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return tools, await session.call_tool(mcp_server.TOOL, {"word_count": 1, "budget": -1, "appid": 1})
    tools, invalid = asyncio.run(asyncio.wait_for(go(), 60))
    assert [t.name for t in tools.tools] == ["babel_language_plan"]
    assert invalid.isError and "budget" in invalid.content[0].text
