"""Call Babel's MCP tool with the official MCP client, over HTTP or stdio, and print what an agent would see.

  python tools/mcp_demo.py --http http://127.0.0.1:8000/mcp --appid 3146520 --words 30000 --budget 10000
  python tools/mcp_demo.py --stdio --appid 3146520 --words 30000 --budget 10000
  (also --steam-url, --name, --description, --lookalikes 413150,1135690, --json)
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]


async def session_for(a, body):
    async def on_log(params):
        print(f"  log  {params.data}")
    if a.http:
        transport = streamable_http_client(a.http)
    else:
        transport = stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "babel.mcp_server"],
                                                       cwd=str(ROOT), env=dict(os.environ)))
    async with transport as streams:
        async with ClientSession(streams[0], streams[1], logging_callback=on_log) as session:
            info = await session.initialize()
            tools = await session.list_tools()
            print(f"server: {info.serverInfo.name} {info.serverInfo.version} | transport: "
                  f"{'streamable HTTP ' + a.http if a.http else 'stdio'}")
            for t in tools.tools:
                print(f"tool: {t.name} | required: {t.inputSchema.get('required')} | inputs: "
                      f"{', '.join(t.inputSchema['properties'])}")
            print(f"call: {body}")
            return await session.call_tool("babel_language_plan", body)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # titles and artist names in any script
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--http", help="MCP endpoint, e.g. http://127.0.0.1:8000/mcp")
    where.add_argument("--stdio", action="store_true", help="start `python -m babel.mcp_server` and talk over stdio")
    for flag in ("--steam-url", "--name", "--description"):
        ap.add_argument(flag)
    ap.add_argument("--appid", type=int)
    ap.add_argument("--lookalikes", help="comma-separated Steam app IDs")
    ap.add_argument("--words", type=int, required=True)
    ap.add_argument("--budget", type=float, required=True)
    ap.add_argument("--json", action="store_true", help="print the full structured result")
    a = ap.parse_args()
    body = {k: v for k, v in {"steam_url": a.steam_url, "name": a.name, "description": a.description,
                              "appid": a.appid, "word_count": a.words, "budget": a.budget,
                              "lookalikes": [int(x) for x in a.lookalikes.split(",")] if a.lookalikes else None}.items()
            if v is not None}
    result = asyncio.run(session_for(a, body))
    if result.isError:
        print("error:", result.content[0].text)
        return 1
    out = result.structuredContent
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    s = out["summary"]
    print(f"result: status={out['status']} cached={out['cached']} plan_id={out['plan_id']}")
    print(f"  translate the game: {', '.join(s['translate_game']) or 'none'}")
    print(f"  store page only:    {', '.join(s['store_page_only']) or 'none'}")
    print(f"  skip for now:       {', '.join(s['skip']) or 'none'}")
    print(f"  cost ${s['total_cost_usd']:,.0f} of ${s['budget_usd']:,.0f}; evidence {s['evidence_level']}")
    print(f"  explanation: {s['explanation']}")
    print(f"  caveats: {len(out['caveats'])}; provenance: {len(out['provenance']['evidence_index'])} evidence items, "
          f"{len(out['provenance']['trace'])} trace events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
