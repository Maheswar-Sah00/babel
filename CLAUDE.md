# Babel (Qloo Agentic Hackathon 2026)

Babel tells indie Steam developers which languages to translate their game into, as a costed plan, using Qloo fan maps
of look-alike games. Full context, evidence, architecture and the task list: **[docs/BABEL_BRIEF.md](docs/BABEL_BRIEF.md)**.
What we may and may not claim, and the fallback for Qloo's default maps: **[docs/DECISIONS.md](docs/DECISIONS.md)**.
Task prompts arrive as `TASK <n>: ...` (format in the brief, section 9); the task numbers match the brief's section 8.

Deadline: 30 Oct 2026, 11:45 pm ET. Feature freeze 25 Oct.

## Architecture

| Path | Role |
|---|---|
| `babel/net.py` | The only HTTP layer: per-host throttle, retries (429, 5xx, network, null body), call counters; `allowed_hosts` cache-only switch (`Offline`) |
| `babel/qloo.py` | Cached Qloo client: `WORLD` polygon, `search_game`, `world_cells`, `fingerprint` / `default_fingerprint`, `country_scores` / `country_profile` |
| `babel/steam.py` | Cached Steam store + SteamSpy (`appdetails`, `review_total`, `languages`, `release_date`) |
| `babel/wiki.py` | Wikidata (Steam ID → articles) + Wikipedia pageviews |
| `babel/llm.py` | Cached Groq JSON calls; cached Claude JSON-schema calls (`ask_claude_json`, `ask_claude_many`) |
| `babel/comps.py` | `CompPicker`: look-alike pool, IDF-weighted tag overlap, Qloo validity (`qloo_status`, `resolve`, `pick`) |
| `babel/runtime.py` | Precomputed runtime data in `data/runtime/` (git-ignored, Qloo-derived): baseline, pool (tags, Qloo checks, card info), fan maps as `qloo.country_sums`, manifest with source hashes; `plan.context()` loads it in ~0.2 s, else falls back to `plan.Context` (~30 s from the cache) |
| `babel/languages.py` | The 14 targets, language → countries, population weights (copied from `evaluate.py`; a test guards it); `OFFICIAL_IN` (display only) |
| `babel/plan.py` | Planning engine: scoring, costs (`Rates`), exact budget optimizer (`fit_budget`: also the budget slider's), three groups, evidence object (with `allocation` for re-fitting), CLI |
| `babel/describe.py` | Description → tags + look-alikes: Claude (schema JSON, pool tags only) proposes; code verifies on Steam/Qloo, selects by tag overlap, rates confidence |
| `babel/api.py` | FastAPI app: `POST /plan` (SSE or `?stream=false`), `GET /plans/{id}`, `POST /fit-budget`, `/track-record`, `/health`, `/health/ready`; `Settings` from `BABEL_*` env; rate limits, body limit, plan cache, short upstream retry policy (`net.policy`) |
| `babel/explore.py` | The Plan screen's data, from fan maps already read: per-country Qloo scores (mean of `country_profile` over look-alikes, vs the backtest's per-country reference), each language's full calculation (equals the plan; the agent verifies it), official-language relationships, Babel vs the generic list, cost breakdown |
| `web/` | Browser app (no build): `index.html`, `static/app.css`; `static/theme.js` (light/dark: a classic script in `<head>`; dark colours live only under `@media screen` on `:root[data-theme="dark"]`, so print stays light), `static/hero.js` (the Start screen's dot-matrix world map with the language pins, from `static/world-hero.json`; decorative), `static/app.js` (Start + Working; SSE via fetch; view switching), `static/plan.js` (Plan screen), `static/charts.js` + `charts.css` (the Plan screen's four charts), `static/map.js` (D3 world map), `static/streets.js` (a country's street map: OpenStreetMap tiles, opened by zooming onto a country until it fills the view; context only), `static/mapdata.js` (pure map transforms), `static/report.js` + `report.css` (one-page A4 report, print / PDF), `static/track.js` + `track.css` (Track record), `static/tour.js` + `tour.css` (guided walkthrough over the real UI),
`static/assistant.js` + `assistant.css` (the side launcher and chat panel; performs validated actions),
`static/actions.js` (named app actions: `register` / `perform`, used by the assistant and the tour), `static/ui.js`
(helpers); DOM built without innerHTML; `static/vendor/d3.min.js` (pinned), `static/world.json` (Natural Earth, `tools/build_world.py`); served at `/` and `/static/` with a strict CSP |
| `babel/suggest.py` | Start-screen look-alikes: the planner's own picks (unchanged cards = same plan), alternatives, pool search, single-game Qloo check |
| `babel/mcp_server.py` | MCP tool `babel_language_plan` (official SDK, mcp 1.x FastMCP): streamable HTTP mounted at `/mcp` on the API (shares its state), or stdio via `python -m babel.mcp_server`; same validation and agent as `POST /plan` |
| `babel/track_record.py` | Track record recomputed from `backtest/data` (SHA-256 of each file): every method's metrics, paired tests with bootstrap CIs, per-game observed shares and rankings; figures that need Qloo data are read from `final_report.md` and marked "reported"; the labelled exploratory note |
| `babel/agent.py` | The agent: runs the steps, emits typed events (`v`, `seq`, `type`, `step`, `status`, `message`, `data`; stable for SSE), reflects/recovers, verifies; CLI `python -m babel.agent` |
| `babel/assistant.py` | `POST /assistant`: answers questions about Babel and the open plan from an evidence context (the plan re-fitted at the budget on screen, map summary, market notes, track record headline); every number in Claude's reply checked against it (else a fallback); actions (`run_plan`, `set_budget`, `show_country`, ...) validated against Babel's own data and labelled by code |
| `babel/explain.py` | Evidence index with stable IDs; Claude's explanation must cite IDs and quote only numbers found in them (code-checked), else a template written by code |
| `babel/markets.py` | Market notes: Qloo demographics of the look-alikes; per market, two-step "also loves" (country pool by location only, then re-rank by fans with no location); every item has a `kind` and a request id; Claude notes checked by code |
| `tests/` | Unit tests on synthetic data / fake APIs (`test_plan.py`, `test_explore.py`, `test_runtime.py`, `test_agent.py`, `test_api.py`, `test_track_record.py` (vs `final_report.md`), ...; `synthetic.py` builds a full plan result); Playwright: `test_web.py`, `test_report.py`, `test_track_web.py`, `test_tour.py`, `test_assistant_web.py`, `test_hero_web.py`, `test_theme_web.py`, `test_charts_web.py`, `test_dark_mode_web.py` (no blue in dark mode), `test_nav_web.py`; `test_assistant.py`
(the endpoint, fake Claude); needing `cache/`: `test_plan_backtest.py`, `test_journey.py` (the whole user journey, network refused) |
| `backtest/` | Pre-registered backtest: builders, `evaluate.py`, reports, frozen data in `backtest/data/` |
| `killcheck/` | Day-1 kill check |
| `tools/check_secrets.py` | Pre-publication secret scan |
| `tools/build_world.py`, `tools/screenshots.py` | Map outlines (`web/static/world.json`; `--hero`: `web/static/world-hero.json`, 1:50m, small islands as points); README screenshots from a running server |
| `tools/build_runtime.py` | Builds `data/runtime/` from the cache with no network (`--check-qloo`: also check unchecked pool games in Qloo) |
| `tools/precache_demos.py` | Runs the four demo buttons through the API as the browser does; `--offline` proves they need no live call |
| `cache/` | Every API response (git-ignored, about 1 GB; never delete: it costs calls and hours) |

Planned (brief, section 6): deployment (Task 12; local gate in `docs/LOCAL_RELEASE_READINESS.md`), usability test,
Devpost text.

## Commands

```bash
pip install -r requirements.txt                       # Python 3.12; keys go in .env (template: .env.example)
python -c "import babel.qloo, babel.steam, babel.wiki, babel.llm, babel.comps"   # import check
python -m pytest                                      # engine tests (pip install -r requirements-dev.txt)
python -m babel.plan --examples                       # plans for three example games (add --json for evidence)
python -m babel.agent --examples                      # the agent's live trace + grounded explanation (--jsonl: raw events)
uvicorn babel.api:app --host 127.0.0.1 --port 8000    # the web API (docs at /docs); settings: BABEL_* in .env.example
python tools/mcp_demo.py --http http://127.0.0.1:8000/mcp --appid 3146520 --words 30000 --budget 10000   # MCP check
python -m pytest tests/test_web.py                    # browser tests (once: python -m playwright install chromium)
python tools/screenshots.py --base http://127.0.0.1:8000   # docs/screenshots from a running server
python backtest/market_insights.py                    # cached run, 0 network calls
python backtest/evaluate.py                           # full backtest: only when a task asks
python tools/build_runtime.py                         # precomputed runtime data -> data/runtime/ (cache only, ~1 min)
python tools/precache_demos.py --offline              # the demo buttons need no live API call (exit 1 if they do)
python tools/build_world.py                           # rebuild the map outlines web/static/world.json (rarely)
python tools/build_world.py --hero                    # the Start screen's 1:50m outlines web/static/world-hero.json
python tools/check_secrets.py                         # must print OK before any commit is pushed
```

## Security rules

- Keys live only in `.env` (`QLOO_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`). Never print, log, commit or ship
  them; nothing secret in a frontend bundle.
- `.env`, `cache/` and `data/runtime/` are git-ignored. Do not un-ignore them. (`spike/`, the abandoned Crossover
  experiments, now lives outside the repo in `../Oloo-archive/spike/`.)
- Run `python tools/check_secrets.py` before any push. If it finds something, stop and report; never print the value.
- Never push, create a remote or change the GitHub account or git identity without the user's confirmation.
- No personal data to Qloo; describe segments by taste, never by ethnicity or other protected traits.

## Working rules

- Reuse `babel/`. Every external call goes through it and is cached in `cache/`.
- Qloo: `take` ≤ 50; heatmaps need a location (use `qloo.WORLD`); check `fingerprint` against `default_fingerprint()`;
  aggregate cells with `country_scores` / `country_profile`; tag-signal heatmaps return nothing on this key.
- Numbers come from code, never from an LLM. Claude only turns descriptions into tags or look-alikes and writes
  explanations from the evidence object.
- Claims in UI, README and Devpost text must match `docs/DECISIONS.md` (sections 3 and 4); label estimates as estimates.
- Do not change `backtest/PREREGISTRATION.md` decisions or the backtest data; do not re-run the full backtest unless a
  task asks.
- Keep the repo's style: short docstrings, small functions, no heavy frameworks unless a task needs them.

## Workflow

1. One `TASK <n>` per prompt. Read the files it names; ask the user when a decision is theirs (hosting, model, account).
2. Run on Windows (Git Bash / PowerShell), Python 3.12. End every task with a verifiable check (a command, a test or a
   screenshot) and report its output.
3. Commit only when the user asks. Run the secret scan first. Commits are authored by Maheswar-Sah00 only: no
   `Co-Authored-By` or "generated with" lines in commits or PR descriptions. Remote: `github.com/Maheswar-Sah00/babel`.
