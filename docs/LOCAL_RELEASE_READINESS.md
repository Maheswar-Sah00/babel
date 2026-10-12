# Babel: local release readiness

Gate run on 11 Oct 2026, on Windows 11 with Python 3.12.0. **Local only.** Nothing was deployed, pushed or published,
and no infrastructure was provisioned. No test is marked as passing unless it was run; anything not run is listed in
[section 7](#7-not-run).

## Decision: PASS for local use

The whole user journey passes in a real browser against the real app, with every network request from the server
refused. There are no critical defects. Two of the three major defects were fixed during the gate. The third (M3) only
affects deployment and needs your decision; it does not affect running Babel locally.

**Not yet approved: deployment.** It needs the decisions in [section 8](#8-decisions-needed-before-deployment).

## 1. Start Babel locally

These are the commands that were run for this gate; the results are below each block.

```powershell
# 1. Install (Python 3.12). The lock file pins every dependency to the versions the clean-environment run passed with.
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt -c requirements-lock.txt
python -m playwright install chromium          # only needed for the browser tests

# 2. Keys: copy .env.example to .env and fill in QLOO_API_KEY and ANTHROPIC_API_KEY (GROQ_API_KEY: backtest only).

# 3. Runtime data. This needs the local API cache (cache/, private, about 1.1 GB): about a minute, no network.
python tools/build_runtime.py
python tools/precache_demos.py --offline       # must print "All demos run from the cache alone."

# 4. Run
uvicorn babel.api:app --host 127.0.0.1 --port 8000
# then open http://127.0.0.1:8000  (readiness: curl http://127.0.0.1:8000/health/ready)
```

Results:
- **`tools/build_runtime.py`:** 58 s, **0 network requests**. Pool of 844 games: 356 with a real Qloo fan map, 73 with
  only the default map, 125 not in Qloo, 290 never checked; 352 fan maps. Loads in 0.2 s.
- **`tools/precache_demos.py --offline`:** "All demos run from the cache alone." All four demo buttons gave status
  `ok` with 0 requests: WEBFISHING, Dawnsbury Days, Never Second in Rome, and "A cozy farming idea".
- **`uvicorn babel.api:app`:** `/health/ready` gave 200 with `runtime_source` "precomputed data/runtime". Warm-up
  takes 0.1–0.2 s. Each request logs exactly one line from `babel.api` plus uvicorn's access line.

## 2. Test results (all executed)

| Suite | Command | Result | Time |
|---|---|---|---|
| Full suite, real repo (cache present) | `python -m pytest -q -rs` | **294 passed, 0 failed, 0 skipped** | 5 min 24 s |
| Fresh-clone copy: 110 publishable files, new venv, no `.env`, no keys, no cache, no `data/runtime` | `.venv\Scripts\python -m pytest -q -rs` | **270 passed, 24 skipped, 0 failed**. Every skip is "needs the local API cache". | 4 min 11 s |
| User journey, real backend, server network refused | `python -m pytest tests/test_journey.py` | **4 passed** | 41 s |

Tests per file in the full suite:

| File | Tests | What it covers |
|---|---|---|
| `test_plan.py` | 57 | Planning engine: formulas, costs, exact optimizer, groups |
| `test_api.py` | 44 | API: SSE, JSON mode, validation, limits, rate limits, errors, `/fit-budget`, readiness |
| `test_web.py` | 26 | Browser: Start, Working and Plan screens, map interactions, error states, phone layout, real backend |
| `test_explore.py` | 26 | Map data: country aggregation, language calculations, missing/default maps, re-fitting the budget |
| `test_describe.py` | 22 | Description input (Claude proposes, code verifies) |
| `test_markets.py` | 19 | Market notes, two-step "also loves", checked Claude notes |
| `test_plan_backtest.py` | 18 | Offline against the backtest and cache: rankings reproduced for 71/71 games, demo games, map evidence, precomputed data giving identical plans, MCP = API = CLI |
| `test_mcp.py` | 18 | MCP tool over stdio and streamable HTTP |
| `test_agent.py` | 17 | Agent trace, retries, failures, recovery, grounded explanation, map-data verification |
| `test_track_record.py` | 16 | Track record numbers parsed from `backtest/final_report.md` and compared |
| `test_runtime.py` | 11 | Precomputed runtime data: cache-only build, exact round trip, stale or damaged data refused, fallback |
| `test_report.py` | 9 | One-page report: contents, budget change, print hides everything else, exactly one A4 PDF page |
| `test_track_web.py` | 7 | Track record screen: figures equal the report, Steam not significant, game picker, phone, failed load |
| `test_journey.py` | 4 | The whole journey (below) |

## 3. Feature checklist

| Requirement | Status | Evidence |
|---|---|---|
| **Journey:** game input (Steam link, name, description) | Pass | `test_web`: main workflow, description by keyboard, unknown game; `test_journey` |
| **Journey:** comparable games, swap | Pass | `test_web`: swap, search and check, swap by keyboard |
| **Journey:** live agent trace | Pass | `test_web` sees a step "running" while the run is going; `test_journey` waits for real steps |
| **Journey:** localization plan | Pass | `test_journey`: WEBFISHING gives "Translate Russian and Spanish." for $7,996 of $10,000 |
| **Journey:** interactive map (zoom, pan, reset, metrics, legend) | Pass | `test_web`: search/zoom/pan/reset, metrics and legend; map evidence for the 3 demo games in `test_plan_backtest` |
| **Journey:** country exploration | Pass | `test_journey` (Japan); `test_web` (Brazil, Canada, Russia; language highlighting) |
| **Journey:** budget adjustment | Pass | `test_web`: the re-fit equals the engine's own plan; `test_journey`: $4,000 then back to $10,000 |
| **Journey:** evidence inspection | Pass | "Why?" dialog with every value; evidence IDs; comparable games with their Qloo status |
| **Journey:** report export | Pass | `test_report`; sample [docs/samples/report-webfishing.pdf](samples/report-webfishing.pdf), 1 page |
| **Journey:** track record | Pass | `test_track_web`, `test_journey` |
| All three demo games | Pass | `test_journey` (all 3); `precache_demos --offline` (all 4 demo buttons, 0 live calls) |
| Description-only input | Pass | `test_journey` description demo; `test_web`; `test_describe` |
| Invalid input | Pass | `test_web` (caught before any request; server 404); `test_api` (422s) |
| Missing Qloo data | Pass | `test_web` no-data map state; `test_explore`; `test_agent` (typical mix, disclosed) |
| Default maps | Pass | `test_web` shows "default map, not used"; `test_explore`; evidence badges |
| Upstream API failures | Pass | `test_agent` (503 retries, give up, never invent data); `test_api` (failures streamed and not cached); `test_web` (failed run and retry, partial result, rate limit, map that fails to load) |
| Backtest metrics match the published report | Pass | `test_track_record` parses `final_report.md`. Steam: 48.9% vs 47.7%, 23/26/22, p = 0.500, CI −2.46% to +5.00%, **not significant**. Wikipedia: 60.1% vs 57.4%, 87/66/33, p < 0.001, CI +0.06% to +5.42%. Claude alone: 45.5% / 59.1%. |
| Responsive layout | Pass | No sideways scroll at 390 px on Start, Plan, report and track record (`test_web`, `test_report`, `test_track_web`) |
| Keyboard | Pass | Mode tabs, swap dialog, map keys, country list arrows, "Why?" dialog returns focus, track record game picker |
| Useful error states | Pass | Loading and failure banners, failed run with request ID, rate-limit countdown, map load failure with retry, track record retry |
| Setup from a clean environment | Pass (local) | The fresh-clone copy installs, imports, passes its tests and serves the page. It cannot plan without the cache (M3). |
| No secrets exposed | Pass | [Section 5](#5-secrets) |
| No unnecessary live calls for demo games | Pass | [Section 4](#4-live-api-calls) |

## 4. Live API calls

- **`python tools/precache_demos.py --offline`** (final run) refuses every request: **4 of 4 demo buttons ok with 0
  requests**. The three CLI examples (`plan.EXAMPLES`) also need 0 requests (gate audit).
- **Calls this gate made**, counted from new cache files:
  - **Qloo:** 9, from the pre-cache fix M2;
  - **Claude:** 3: 2 from M2, plus 1 for the screenshot run's deliberately fresh plan;
  - **Steam:** 0.
- **Live calls are still expected** when a user enters a new game, swaps comparable games or changes the inputs. Babel
  then plans something not yet cached: a Claude explanation, and possibly Qloo market data. Moving the budget slider
  on the Plan screen makes no external calls.

## 5. Secrets

- **`python tools/check_secrets.py`:** "Scanned 113 publishable files and 0 history blobs against 3 .env values and 10
  key patterns. OK: no secrets found."
- **A scan for the 3 `.env` values and key formats** (only names and counts printed) found **0 matches** in:
  - the frontend bundle `web/` (16 files);
  - the server and agent logs (16 files);
  - the task outputs (40);
  - `docs/` (19), `README.md` and `tests/` (16).
- **Git:** there is no history yet (`git log --all` is empty). `.env`, `cache/`, `data/runtime/` and `spike/` are
  git-ignored (`git check-ignore -v`).
- **Keys stay on the server:** the browser talks only to its own server, and responses never include keys.

## 6. Defects

| ID | Severity | Defect | Status |
|---|---|---|---|
| — | Critical | None found | — |
| M1 | Major | On a fresh clone, 24 browser tests failed without a `QLOO_API_KEY`. Readiness requires one, and the test site never set it. | **Fixed:** the test site sets a placeholder. The fresh-clone copy then passed 270 with 0 failures. |
| M2 | Major | Never Second in Rome and the description demo were not fully cached at the browser's defaults. They needed Qloo and Claude calls and came back partial when offline. | **Fixed:** `tools/precache_demos.py` fetched 9 Qloo and 2 Claude answers. `--offline` now passes for all 4 demos. |
| M3 | Major (deployment) | A clean clone cannot plan: `cache/` and `data/runtime/` are private and git-ignored. Rebuilding the pool from nothing takes about 2,000 Steam and Qloo requests (at least about 34 minutes). | **Open:** needs your decision on how the server gets the data ([section 8](#8-decisions-needed-before-deployment)). It does not affect local use. |
| m1 | Minor | The trace said "Claude gave no usable answer.." (doubled full stop) even when Claude was simply unreachable | **Fixed** |
| m2 | Minor | Swapping in the same comparable games needs a live Claude call, because the evidence differs from the cached plan | Expected; documented here |
| m3 | Minor | The API's per-request log line never appeared under plain uvicorn | **Fixed:** one line per request, no duplicates |
| m4 | Minor | Dependencies of dependencies were not pinned (66 resolved packages) | **Fixed:** `requirements-lock.txt` |
| m5 | Minor | There is no git history yet, so the "pre-registration unchanged" claim rests on checksums | **Open:** commit when you say. The SHA-256 of `backtest/PREREGISTRATION.md` and `backtest/data/*` were unchanged through the gate (e.g. `PREREGISTRATION.md` 84150d48…). |

Known limitations, not defects:
- **290 of the 844 pool games** have never been checked in Qloo. They are checked live when a plan needs them.
  Checking them all now (`tools/build_runtime.py --check-qloo`, about 580 Qloo calls) waits for the quota to be
  confirmed.
- **A startup warning** from a dependency, pydantic-settings (`IncompleteFieldDefinitionWarning: Field 'lifespan'`). It
  is harmless.
- **Rotate the keys after the hackathon:** the Qloo, Groq and Anthropic keys appeared in chat.

## 7. Not run

- A manual screen-reader pass (NVDA or VoiceOver). Keyboard and ARIA behaviour is covered by the automated tests only.
- Setup on macOS or Linux, and a pip install with a cold download cache (this machine's pip cache was warm).
- Planning or warm-up in the fresh-clone copy: forbidden, because it would make thousands of live requests.
- A usability test with people (brief task 13), and a re-run of `backtest/evaluate.py` (not asked).

## 8. Decisions needed before deployment

1. **Approval to deploy at all**, and to which always-on host (brief section 10, item 2). Nothing has been deployed.
2. **How the server gets its data (M3).** Either copy `data/runtime/` and the demo cache entries to the server
   privately, or commit `data/runtime/` (about 2 MB of Qloo-derived data). The latter would publish Qloo data, which
   `docs/DECISIONS.md` currently keeps private.
3. **First commit and push** to `github.com/Maheswar-Sah00/babel`, authored by Maheswar-Sah00 only, and whether
   `spike/` stays private.
4. **The Claude model and a spend cap** for the live app, and whether to run `--check-qloo` once the quota is known.

## Addendum, later on 11 Oct: guided tour and AI assistant

Two features were added after the gate and re-checked with the same rules. Decision unchanged: **PASS for local use**.

- **Guided tour** ("Take the tour" in the nav): 19 steps over the real UI. It runs the WEBFISHING demo for real from
  the cache; nothing is simulated, and the tour's own text contains no numbers.
- **The Babel assistant** (the logo button at the side):
  - **Endpoint:** `POST /assistant`, rate bucket `BABEL_ASSISTANT_RATE` (20 per minute).
  - **Answers:** Claude answers from the open plan's evidence, re-fitted at the budget on screen. Code checks every
    number in the reply, and an unverifiable answer is replaced by a fallback written by code.
  - **Actions:** checked against Babel's own data and labelled by code; the browser then performs them through the
    same functions as the buttons.

| Check | Result |
|---|---|
| Full suite: `python -m pytest -q -rs` | **431 passed, 0 failed** (4 min 28 s). New: `test_assistant.py` 111, `test_assistant_web.py` 16, `test_tour.py` 10. |
| Demo buttons: `python tools/precache_demos.py --offline` | All 4 ok, 0 live requests |
| Secrets: `python tools/check_secrets.py` | OK: no secrets found |
| Live assistant check: real panel, real backend, real Claude, WEBFISHING plan | 3 questions, answered in about 6 s each. Every number was found in the evidence; the actions ran (budget re-fitted, Japan shown, "Why?" opened, map view switched). 3 Claude calls, about $0.10. |

Defects found and fixed in this round:

| Severity | Defect | Fix |
|---|---|---|
| Major | When the assistant opened "Why?", the modal dialog blocked the docked chat with no explanation | The chat notes "close it (Esc) to keep chatting"; on close the note goes and focus returns to the chat input (regression test added) |
| Minor | The "Why?" dialog rendered 560 px wide instead of 780 px (CSS order) | `.dialog.dialog-wide` |
| Minor | Scrolls triggered by actions were smooth even under reduced motion | `behavior` follows `prefers-reduced-motion` |

Notes:
- **Cost:** each new assistant question costs about $0.02–0.04 (Opus 5.5, low effort); identical questions come from
  the cache.
- **Stored text:** the cache keeps Claude's answers, which can echo user text, on the server's disk (`cache/llm`,
  private).
- **Screen reader:** not tested manually for the tour or the assistant (see section 7).
